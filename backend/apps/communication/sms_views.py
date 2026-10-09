"""API views for SMS sending, logs, and notification preferences."""

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import get_institution, is_global, assert_campus_allowed
from apps.accounts.middleware import require_active_school
from apps.students.models import Student
from apps.teachers.models import Teacher

from .models import NotificationPreference, SMSLog
from .sms import send_sms

User = get_user_model()


def _collect_phones(user_ids):
    """Return a list of unique non-empty phone numbers for user ids."""
    phones = set()
    users = User.objects.filter(id__in=user_ids).values_list(
        "phone", flat=True
    )
    for p in users:
        if p and p.strip():
            phones.add(p.strip())
    return list(phones)


def _parent_phones_for_students(student_ids):
    """Get phone numbers of guardians for given students."""
    phones = set()
    guardians = Student.objects.filter(
        id__in=student_ids
    ).values_list(
        "guardian__phone", "guardian__alternate_phone"
    )
    for phone, alt in guardians:
        if phone and phone.strip():
            phones.add(phone.strip())
        if alt and alt.strip():
            phones.add(alt.strip())
    return list(phones)


class SMSBroadcastView(APIView):
    """POST to send SMS to selected recipients.

    Body:
        message: str (required)
        recipient_ids: list[int] (optional) - specific user ids
        role: str (optional) - e.g. "parent", "teacher", "student"
        campus_id: int (optional) - filter by campus
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        if not is_global(user):
            return Response(
                {"detail": "Only admin users can send SMS."},
                status=status.HTTP_403_FORBIDDEN,
            )

        message = (request.data.get("message") or "").strip()
        if not message:
            return Response(
                {"detail": "Message is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        recipient_ids = request.data.get("recipient_ids") or []
        role = (request.data.get("role") or "").strip()
        campus_id = request.data.get("campus_id")

        institution = get_institution(request)

        phone_numbers = set()

        if recipient_ids:
            institution = require_active_school(request)
            if institution is None:
                return Response({"detail": "Select a school before sending SMS."}, status=400)
            if not isinstance(recipient_ids, list) or any(
                isinstance(pk, bool) or not str(pk).isdigit() for pk in recipient_ids
            ):
                return Response({"detail": "recipient_ids must be a list of user IDs."}, status=400)
            requested_ids = {int(pk) for pk in recipient_ids}
            recipients = User.objects.filter(
                pk__in=requested_ids, is_active=True,
                memberships__institution=institution, memberships__status="active",
            ).distinct()
            if campus_id:
                assert_campus_allowed(user, campus_id, request=request)
                recipients = recipients.filter(
                    Q(staff_profile__primary_campus_id=campus_id)
                    | Q(teacher_profile__primary_campus_id=campus_id)
                    | Q(student_profile__enrollments__campus_id=campus_id,
                        student_profile__enrollments__status="active")
                ).distinct()
            allowed_ids = set(recipients.values_list("pk", flat=True))
            if allowed_ids != requested_ids:
                return Response({"detail": "One or more recipients are outside the selected school or campus."}, status=403)
            phone_numbers.update(_collect_phones(allowed_ids))

            student_ids = list(
                User.objects.filter(
                    id__in=allowed_ids,
                    student_profile__isnull=False,
                ).values_list("student_profile__id", flat=True)
            )
            if student_ids:
                phone_numbers.update(
                    _parent_phones_for_students(student_ids)
                )

        elif role:
            if role == "all":
                users_qs = User.objects.filter(
                    memberships__status="active"
                ).distinct()

                if institution:
                    users_qs = users_qs.filter(memberships__institution=institution)

                phone_numbers.update(_collect_phones(users_qs.values_list("id", flat=True)))
                student_ids = Student.objects.filter(
                    enrollment__status="active",
                )
                if institution:
                    student_ids = student_ids.filter(
                        enrollment__campus__school=institution
                    )
                student_ids = student_ids.values_list("id", flat=True)
                phone_numbers.update(_parent_phones_for_students(student_ids))

            elif role == "parent":
                users_qs = User.objects.filter(
                    guardian_profile__isnull=False
                )

                if institution:
                    users_qs = users_qs.filter(memberships__institution=institution)

                if campus_id:
                    student_ids = Student.objects.filter(
                        enrollment__campus_id=campus_id,
                        enrollment__status="active",
                    ).values_list("id", flat=True)
                    users_qs = users_qs.filter(
                        guardian_profile__students__id__in=student_ids
                    )
                phone_numbers.update(_collect_phones(users_qs.values_list("id", flat=True)))
                phone_numbers.update(
                    _parent_phones_for_students(
                        Student.objects.filter(
                            guardian__in=users_qs
                        ).values_list("id", flat=True)
                    )
                )

            elif role == "student":
                users_qs = User.objects.filter(
                    memberships__status="active",
                    student_profile__isnull=False,
                ).distinct()

                if institution:
                    users_qs = users_qs.filter(memberships__institution=institution)

                if campus_id:
                    users_qs = users_qs.filter(
                        student_profile__enrollment__campus_id=campus_id,
                        student_profile__enrollment__status="active",
                    )
                phone_numbers.update(_collect_phones(users_qs.values_list("id", flat=True)))

            elif role == "teacher":
                users_qs = User.objects.filter(
                    memberships__status="active",
                    teacher_profile__isnull=False,
                ).distinct()

                if institution:
                    users_qs = users_qs.filter(memberships__institution=institution)

                if campus_id:
                    users_qs = users_qs.filter(
                        teacher_profile__primary_campus_id=campus_id,
                    )
                phone_numbers.update(_collect_phones(users_qs.values_list("id", flat=True)))

            else:
                from apps.accounts.models import RoleAssignment
                role_user_ids = RoleAssignment.objects.filter(
                    role=role,
                    membership__status="active",
                ).values_list("membership__user_id", flat=True)

                if institution:
                    role_user_ids = role_user_ids.filter(
                        membership__institution=institution
                    )

                if campus_id:
                    role_user_ids = User.objects.filter(
                        id__in=role_user_ids,
                        memberships__status="active",
                    ).filter(
                        Q(staff_profile__primary_campus_id=campus_id)
                        | Q(teacher_profile__primary_campus_id=campus_id)
                        | Q(student_profile__enrollment__campus_id=campus_id)
                    ).values_list("id", flat=True)
                phone_numbers.update(_collect_phones(role_user_ids))

        if not phone_numbers:
            return Response(
                {"detail": "No recipients with phone numbers found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sent = 0
        failed = 0

        for phone in phone_numbers:
            ok, err = send_sms(phone, message)
            SMSLog.objects.create(
                phone_number=phone,
                message=message,
                status="sent" if ok else "failed",
                error=err or "",
                sent_by=user,
                institution=institution,
            )
            if ok:
                sent += 1
            else:
                failed += 1

        return Response(
            {
                "sent": sent,
                "failed": failed,
                "total_recipients": len(phone_numbers),
            }
        )


class SMSLogListView(APIView):
    """GET list of SMS logs."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        institution = get_institution(request)
        qs = SMSLog.objects.select_related("recipient", "sent_by").all()

        if not is_global(user):
            qs = qs.filter(sent_by=user)

        if institution is not None and not is_global(user):
            qs = qs.filter(
                Q(institution=institution) | Q(institution__isnull=True)
            )

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        page_size = 20
        page = int(request.query_params.get("page", 1))
        total = qs.count()
        start = (page - 1) * page_size
        logs = qs[start : start + page_size]

        results = []
        for log in logs:
            results.append({
                "id": log.id,
                "phone_number": log.phone_number,
                "message": log.message[:200],
                "status": log.status,
                "error": log.error[:200] if log.error else "",
                "recipient_name": (
                    log.recipient.get_full_name()
                    if log.recipient
                    else None
                ),
                "sent_by_name": (
                    log.sent_by.get_full_name()
                    if log.sent_by
                    else None
                ),
                "created_at": log.created_at.isoformat(),
            })

        return Response({
            "count": total,
            "results": results,
        })


class NotificationPreferenceView(APIView):
    """GET/PUT current user notification preferences."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        pref, _ = NotificationPreference.objects.get_or_create(
            user=request.user
        )
        return Response({
            "sms_enabled": pref.sms_enabled,
            "email_enabled": pref.email_enabled,
            "push_enabled": pref.push_enabled,
            "attendance_alerts": pref.attendance_alerts,
            "payment_reminders": pref.payment_reminders,
            "result_notifications": pref.result_notifications,
            "announcement_sms": pref.announcement_sms,
        })

    def put(self, request):
        pref, _ = NotificationPreference.objects.get_or_create(
            user=request.user
        )

        for field in [
            "sms_enabled",
            "email_enabled",
            "push_enabled",
            "attendance_alerts",
            "payment_reminders",
            "result_notifications",
            "announcement_sms",
        ]:
            if field in request.data:
                setattr(pref, field, bool(request.data[field]))

        pref.save()

        return Response({
            "sms_enabled": pref.sms_enabled,
            "email_enabled": pref.email_enabled,
            "push_enabled": pref.push_enabled,
            "attendance_alerts": pref.attendance_alerts,
            "payment_reminders": pref.payment_reminders,
            "result_notifications": pref.result_notifications,
            "announcement_sms": pref.announcement_sms,
        })
