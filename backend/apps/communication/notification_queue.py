"""Consolidated notification outbox: scheduling, delivery and retry.

All outbound notifications flow through this module. Callers either

* ``enqueue(...)`` a row for later processing (dispatch scheduler), or
* ``send_now(...)`` for immediate, synchronous sends (kept for legacy
  callers such as the fee/absence cron jobs and broadcast views).

``process_due_notifications`` is the scheduler/worker entry point: it
claims queued rows whose ``next_attempt_at`` has passed, delivers them,
writes the audit logs (``SMSLog`` / ``EmailLog`` / in-app ``Notification``)
and the idempotency ledger (``NotificationDispatch``), and on failure
reschedules with exponential backoff until ``max_attempts`` is exhausted.

Backoff (in minutes) is ``BASE * (2 ** (attempts - 1))`` and defaults to
5, 10, 20, 40 … unless overridden via ``NOTIFICATION_BACKOFF_BASE_MINUTES``.
``NOTIFICATION_MAX_ATTEMPTS`` sets the default attempt budget.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    EmailLog,
    Notification,
    NotificationDispatch,
    QueuedNotification,
    SMSLog,
)

IN_APP_TYPE_BY_KIND = {
    "fee_reminder": "payment",
    "absence_alert": "attendance",
    "result_published": "result",
    "announcement": "announcement",
}


def _backoff_base_minutes():
    return int(
        getattr(settings, "NOTIFICATION_BACKOFF_BASE_MINUTES", 5)
    )


def _default_max_attempts():
    return int(getattr(settings, "NOTIFICATION_MAX_ATTEMPTS", 3))


def _dispatch_exists(kind, reference, channel):
    return bool(
        kind
        and reference
        and NotificationDispatch.objects.filter(
            kind=kind,
            reference=reference,
            channel=channel,
        ).exists()
    )


def _record_dispatch(kind, reference, channel, recipient):
    if kind and reference:
        NotificationDispatch.objects.get_or_create(
            kind=kind,
            reference=reference,
            channel=channel,
            defaults={"recipient": recipient},
        )


def _guardian_contacts(student):
    """Return ({'sms': [phones], 'email': [emails]}, pref_user)."""
    guardian = student.guardian

    phones = set()
    emails = set()

    if guardian is None:
        return {"sms": [], "email": []}, None

    for phone in (guardian.phone, guardian.alternate_phone):
        if phone and phone.strip():
            phones.add(phone.strip())

    user = getattr(guardian, "user", None)

    email = (getattr(guardian, "email", "") or "").strip()

    if email:
        emails.add(email)

    if user and (user.email or "").strip():
        emails.add(user.email.strip())

    return {"sms": list(phones), "email": list(emails)}, user


def _prefs_allow(user, channel, flag):
    """Guardian channel preference check; default allow."""
    if user is None:
        return True

    prefs = getattr(user, "notification_preferences", None)

    if prefs is None:
        return True

    if not bool(getattr(prefs, f"{channel}_enabled", True)):
        return False

    return bool(getattr(prefs, flag, True))


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def deliver_sms(to_address, body):
    from .sms import send_sms

    return send_sms(to_address, body)


def deliver_email(to_address, subject, body,
                  from_name=None, from_address=None, connection=None):
    from .email_service import send_email_message

    return send_email_message(
        to_address,
        subject,
        body,
        from_name=from_name,
        from_address=from_address,
        connection=connection,
    )


def _deliver(item, connection=None):
    """Deliver one outbox row in-app.

    Returns ``(ok, skipped, error)``. ``skipped`` means the channel was
    suppressed by the user's preferences (treated as delivered).
    """
    if item.channel == "sms":
        if not item.to_address:
            return False, False, "No phone number provided."

        ok, err = deliver_sms(item.to_address, item.body)

        SMSLog.objects.create(
            institution=item.institution,
            recipient=item.recipient,
            phone_number=item.to_address,
            message=item.body,
            status="sent" if ok else "failed",
            error=err or "",
        )

        return ok, False, err or ""

    if item.channel == "email":
        if not item.to_address:
            return False, False, "No email address provided."

        payload = item.payload or {}
        ok, err = deliver_email(
            item.to_address,
            item.subject,
            item.body,
            from_name=payload.get("from_name"),
            from_address=payload.get("from_address"),
        )

        EmailLog.objects.create(
            institution=item.institution,
            recipient_email=item.to_address,
            subject=item.subject,
            body=item.body,
            status="sent" if ok else "failed",
            error=err or "",
        )

        return ok, False, err or ""

    if item.channel == "in_app":
        if item.recipient is None:
            return False, False, "No recipient for in-app notification."

        prefs = getattr(item.recipient, "notification_preferences", None)

        if prefs is not None and not prefs.push_enabled:
            return True, True, ""

        notification_type = IN_APP_TYPE_BY_KIND.get(
            item.kind, "system"
        )

        Notification.objects.create(
            institution=item.institution,
            recipient=item.recipient,
            title=item.subject or "Notification",
            message=item.body,
            notification_type=notification_type,
            link=(item.payload or {}).get("link", ""),
        )

        return True, False, ""

    return False, False, f"Unsupported channel: {item.channel}"


def _finish_delivery(item, ok, skipped, error):
    """Persist the outcome on a queued row and record idempotency."""
    if ok:
        item.status = "sent"
        item.processed_at = timezone.now()
        item.last_error = ""

        if not skipped:
            address = item.to_address or (
                item.recipient.username if item.recipient else ""
            )
            _record_dispatch(item.kind, item.reference, item.channel, address)
    else:
        item.attempts += 1

        if item.attempts >= item.max_attempts:
            item.status = "failed"
            item.processed_at = timezone.now()
        else:
            item.status = "queued"
            minutes = _backoff_base_minutes() * (
                2 ** (item.attempts - 1)
            )
            item.next_attempt_at = timezone.now() + timedelta(minutes=minutes)

        item.last_error = error

    item.save(
        update_fields=[
            "status",
            "attempts",
            "next_attempt_at",
            "processed_at",
            "last_error",
            "updated_at",
        ]
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enqueue(channel, *, kind="", reference="", recipient=None,
            to_address="", subject="", body="", institution=None,
            scheduled_at=None, payload=None, max_attempts=None):
    """Queue a notification for later delivery by the scheduler.

    Returns the ``QueuedNotification`` row, or ``None`` when an equivalent
    row already exists (same kind/reference/channel) or when the success
    ledger (:class:`NotificationDispatch`) already records it.
    """
    if channel not in dict(QueuedNotification.CHANNEL_CHOICES):
        raise ValueError(f"Unsupported channel: {channel}")

    if _dispatch_exists(kind, reference, channel):
        return None

    existing = QueuedNotification.objects.filter(
        kind=kind,
        reference=reference,
        channel=channel,
    ).exclude(status="sent")

    if kind and reference and existing.exists():
        return None

    return QueuedNotification.objects.create(
        institution=institution,
        channel=channel,
        kind=kind or "",
        reference=reference or "",
        recipient=recipient,
        to_address=to_address or "",
        subject=subject or "",
        body=body or "",
        payload=payload or {},
        scheduled_at=scheduled_at or timezone.now(),
        next_attempt_at=scheduled_at or timezone.now(),
        max_attempts=max_attempts or _default_max_attempts(),
    )


def send_now(channel, *, kind="", reference="", recipient=None,
             to_address="", subject="", body="", institution=None,
             from_name=None, from_address=None, connection=None):
    """Send immediately (synchronously).

    Returns an ``(outcome, error)`` tuple where outcome is one of
    ``"sent"``, ``"skipped"`` (already dispatched) or ``"failed"``.
    A ``QueuedNotification`` row is written for audit + retry bookkeeping.
    """
    if _dispatch_exists(kind, reference, channel):
        return "skipped", ""

    if channel == "email" and not to_address:
        return "failed", "No email address provided."

    if channel == "sms" and not to_address:
        return "failed", "No phone number provided."

    item = QueuedNotification.objects.create(
        institution=institution,
        channel=channel,
        kind=kind or "",
        reference=reference or "",
        recipient=recipient,
        to_address=to_address or "",
        subject=subject or "",
        body=body or "",
        payload={
            "from_name": from_name or "",
            "from_address": from_address or "",
        } if channel == "email" else {},
        next_attempt_at=timezone.now(),
        max_attempts=_default_max_attempts(),
    )

    ok, skipped, error = _deliver(item, connection=connection)
    _finish_delivery(item, ok, skipped, error)

    return ("sent" if ok else "failed"), error


@transaction.atomic
def process_due_notifications(limit=50, now=None):
    """Deliver every queued row that is due.

    Rows are claimed with row locking so overlapping scheduler runs do not
    double-send. Returns a summary dict.
    """
    if now is None:
        now = timezone.now()

    due = list(
        QueuedNotification.objects.filter(
            status="queued",
            next_attempt_at__lte=now,
        )
        .select_for_update(of=("self",), skip_locked=True)
        .select_related("recipient", "institution")
        .order_by("next_attempt_at", "created_at")[:limit]
    )

    summary = {
        "processed": len(due),
        "sent": 0,
        "skipped": 0,
        "failed": 0,
        "permanent_failures": 0,
        "errors": [],
    }

    for item in due:
        ok, skipped, error = _deliver(item)
        _finish_delivery(item, ok, skipped, error)

        if ok:
            if skipped:
                summary["skipped"] += 1
            else:
                summary["sent"] += 1
        elif item.status == "failed" and item.attempts >= item.max_attempts:
            summary["permanent_failures"] += 1
            summary["errors"].append(
                f"{item.get_channel_display()} {item.id}: {error}"
            )
        else:
            summary["failed"] += 1

    return summary


def retry_failed(limit=100, kind=None, now=None):
    """Requeue failed rows so the scheduler attempts them again."""
    if now is None:
        now = timezone.now()

    queryset = QueuedNotification.objects.filter(status="failed")

    if kind:
        queryset = queryset.filter(kind=kind)

    count = 0

    for item in queryset[:limit]:
        item.status = "queued"
        item.next_attempt_at = now
        item.last_error = ""
        item.save(
            update_fields=[
                "status",
                "next_attempt_at",
                "last_error",
                "updated_at",
            ]
        )
        count += 1

    return count


def queue_status():
    """Counts by status and channel for monitoring / admin."""
    rows = QueuedNotification.objects.all()
    due = QueuedNotification.objects.filter(
        status="queued",
        next_attempt_at__lte=timezone.now(),
    ).count()

    return {
        "queued": rows.filter(status="queued").count(),
        "sent": rows.filter(status="sent").count(),
        "failed": rows.filter(status="failed").count(),
        "due_now": due,
        "by_channel": {
            channel: rows.filter(channel=channel).count()
            for channel, _ in QueuedNotification.CHANNEL_CHOICES
        },
    }


def notify_result_published(report_card, user=None):
    """Enqueue parent notifications when a report card is published.

    The ``result_published`` dispatch kind was previously defined but never
    wired; this is its first consumer. Delivery is scheduled and retried by
    the outbox processor, gated by ``result_notifications`` preferences.
    """
    student = report_card.student
    guardian = getattr(student, "guardian", None)

    if guardian is None:
        return 0

    contacts, pref_user = _guardian_contacts(student)

    school = None
    campus = getattr(student, "primary_campus", None)

    if campus is not None:
        school = campus.school

    if school is None:
        school = getattr(report_card, "institution", None)

    try:
        from apps.schools.branding_context import get_school_branding

        brand = get_school_branding(school) if school else {
            "name": "School",
            "short_name": "",
            "email_from_name": "",
            "email_from_address": "",
        }
        display = brand["short_name"] or brand["name"]
        from_name = brand["email_from_name"] or brand["name"]
        from_address = brand["email_from_address"]
    except Exception:
        display = "School"
        from_name = None
        from_address = None

    sms_text = (
        f"[{display}] Results for {student.full_name} "
        f"({report_card.exam.name}) are now published. "
        f"Please check the portal to view the report card."
    )

    enqueued = 0

    if contacts["sms"] and _prefs_allow(pref_user, "sms", "result_notifications"):
        item = enqueue(
            "sms",
            kind="result_published",
            reference=f"result:{report_card.pk}",
            recipient=pref_user,
            to_address=contacts["sms"][0],
            body=sms_text,
            institution=school,
        )

        if item is not None:
            enqueued += 1

    if contacts["email"] and _prefs_allow(pref_user, "email", "result_notifications"):
        email_body = (
            f"Dear Guardian,\n\nResults for {student.full_name} "
            f"({report_card.exam.name}) have been published and are "
            f"now available in the portal.\n\n"
            f"- {display}"
        )

        item = enqueue(
            "email",
            kind="result_published",
            reference=f"result:{report_card.pk}",
            recipient=pref_user,
            to_address=contacts["email"][0],
            subject=f"Results published - {student.full_name}",
            body=email_body,
            institution=school,
            payload={
                "from_name": from_name,
                "from_address": from_address,
            },
        )

        if item is not None:
            enqueued += 1

    return enqueued
