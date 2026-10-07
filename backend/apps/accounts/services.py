"""Centralized account services.

Two platforms problems are solved here with one coherent model:

School-aware logins
    The same username may legitimately exist in different schools (``0001`` in
    Lahore and ``0001`` in Sialkot). Authentication is therefore scoped to a
    school (``school_code`` or a white-label host) and *ambiguous* unscoped
    logins are refused instead of picking an arbitrary account.

Concurrency-safe username generation
    Usernames are unique per ``(institution, username)`` (partial unique
    constraint on ``accounts.User``). Generation is scoped per institution and
    the database is treated as the arbiter: a race loser raises
    ``IntegrityError`` and simply retries with the next candidate.
"""
import re
import string
import time
import os

from django.contrib.auth import get_user_model
from django.db import IntegrityError, OperationalError, transaction
from django.utils.crypto import get_random_string

User = get_user_model()

USERNAME_MAX_ATTEMPTS = 50
LOCK_MAX_RETRIES = 20


# ---------------------------------------------------------------------------
# School-aware lookup helpers
# ---------------------------------------------------------------------------


def scoped_user_queryset(identifier, school_code=None, institution=None):
    """User queryset matching ``identifier`` (username or email), scoped to a
    school when one is known.

    Scoping is by *active membership* first and the denormalized
    ``institution`` FK as a fallback, so both normal users and super-admin
    bootstrap accounts resolve inside their school.
    """
    from django.db.models import Q

    qs = User.objects.all()

    if institution is not None:
        qs = qs.filter(
            Q(institution=institution)
            | Q(
                memberships__institution=institution,
                memberships__status="active",
            )
        ).distinct()

    if school_code:
        school_code = str(school_code).strip().lower()
        qs = qs.filter(
            Q(institution__code__iexact=school_code)
            | Q(
                memberships__institution__code__iexact=school_code,
                memberships__status="active",
            )
        ).distinct()

    return qs.filter(
        Q(email__iexact=identifier) | Q(username=identifier)
    ).distinct()


def login_candidate_count(identifier):
    """Number of distinct accounts bearing ``identifier`` (username or email).

    Used to refuse ambiguous unscoped logins before any password check: a count
    above 1 means the same username exists in more than one school and the
    client must declare its school.
    """
    return scoped_user_queryset(identifier).count()


# ---------------------------------------------------------------------------
# Concurrency-safe, per-institution username generation
# ---------------------------------------------------------------------------


def normalize_username(value):
    """Normalize a username base (whitespace collapse), preserving digits."""
    return re.sub(r"\s+", "", str(value or "")).strip()


def fallback_email(username, institution=None):
    """Deterministic placeholder email for accounts created without one.

    Includes the resolved username (already unique per institution when
    generated via ``create_user_with_username``) and, when known, the school
    code, so two placeholder accounts can never collide on the globally-unique
    ``email`` column.
    """
    username = normalize_username(username)
    institution_code = (
        getattr(institution, "code", "") if institution is not None else ""
    )
    local_part = username
    if institution_code:
        local_part = f"{username}.{str(institution_code).lower()}"
    return f"{local_part}@perfectfoundation.local"


def username_candidate(base, attempt):
    """``base``, then ``base1``, ``base2`` ... for subsequent attempts."""
    if attempt == 0:
        return base
    return f"{base}{attempt}"


def _username_exists(candidate, institution):
    queryset = User.objects.filter(username=candidate)
    if institution is not None:
        queryset = queryset.filter(institution=institution)
    else:
        queryset = queryset.filter(institution__isnull=True)
    return queryset.exists()


def generate_username(base, institution=None, max_attempts=USERNAME_MAX_ATTEMPTS):
    """Pick a per-institution-unique username without creating the user.

    Best-effort guard only: the partial unique constraint ``(institution,
    username)`` is the real arbiter. Cooperative creation should use
    ``create_user_with_username`` which retries on ``IntegrityError``.
    """
    base = normalize_username(base)
    for attempt in range(max_attempts):
        candidate = username_candidate(base, attempt)
        if not _username_exists(candidate, institution):
            return candidate

    return f"{base}{get_random_string(6, allowed_chars=string.ascii_lowercase + string.digits)}"


def _is_lock_error(exc):
    """True for transient SQLite/SQLAlchemy-style table/busy lock failures."""
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "database is locked",
            "database table is locked",
            "database is busy",
        )
    )


def create_user_with_username(
    base,
    institution=None,
    *,
    email=None,
    password=None,
    first_name="",
    last_name="",
    must_change_password=None,
    max_attempts=USERNAME_MAX_ATTEMPTS,
):
    """Create a user with a per-institution-unique username, safe under
    concurrency.

    The ``(institution, username)`` partial unique constraint arbitrates races:
    an ``IntegrityError`` means another writer won the slot (or the email is
    taken), so the loser retries with the next candidate. Email conflicts are
    terminal and re-raised - a new username can never fix them.

    When ``password`` is None a secure random temporary password is generated
    and ``must_change_password`` defaults to True so it must be changed on first
    login (temporary credentials are returned exactly once, never logged).
    When ``email`` is blank a deterministic placeholder is derived from the
    resolved username (unique per institution, never colliding across schools).

    Returns ``(user, username, password)``.
    """
    if must_change_password is None:
        must_change_password = password is None

    base = normalize_username(base)
    email = (email or "").strip()
    generated_password = password or get_random_string(length=14)

    attempt = 0
    lock_retries = 0
    while attempt < max_attempts:
        candidate = username_candidate(base, attempt)
        instance_email = email or fallback_email(candidate, institution)
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=candidate,
                    email=instance_email,
                    password=generated_password,
                    first_name=first_name,
                    last_name=last_name,
                    institution=institution,
                    must_change_password=must_change_password,
                )
            # Optional best-effort verification email for explicitly provided
            # addresses when EMAIL_VERIFY_ON_PROVISION is enabled (default off).
            if email and os.environ.get("EMAIL_VERIFY_ON_PROVISION"):
                try:
                    from .email_verify_views import send_verification_email
                    send_verification_email(user)
                except Exception:
                    pass
            return user, candidate, generated_password
        except IntegrityError:
            # Another writer won the (institution, username) slot; a new
            # username can never fix an email conflict, so that one is terminal.
            if User.objects.filter(email__iexact=instance_email).exists():
                raise
            attempt += 1
            continue
        except OperationalError as exc:
            # Transient DB lock (e.g. SQLite concurrent-writer table lock):
            # retry the SAME candidate briefly before giving up.
            if not _is_lock_error(exc) or lock_retries >= LOCK_MAX_RETRIES:
                raise
            lock_retries += 1
            time.sleep(min(0.02 * lock_retries, 0.25))
            continue

    raise RuntimeError(
        f"Could not allocate a unique username for base '{base}' "
        f"after {max_attempts} attempts."
    )


def provision_school_with_admin(school_data, admin_data=None):
    """Create a school together with its School Admin, atomically.

    A school is only usable once it has a working admin user, so both must
    succeed or neither may. Within one transaction this creates:

      * the ``School`` (from validated create data; ``code`` auto-generated
        when blank),
      * its ``SchoolSettings`` row (white-label / branding defaults),
      * the admin ``User`` — per-school unique username, hash-verified
        password (a temporary one when none is supplied),
      * an active ``InstitutionMembership`` plus a ``Role.ADMIN`` assignment
        binding the admin to *this* school only (a foreign ``institution``
        value in the payload is ignored — there is no cross-school branch).

    ``create_user_with_username`` uses nested savepoints, so an "undo
    transaction" bug is impossible: any ``IntegrityError`` /
    ``ValidationError`` / ``RuntimeError`` (e.g. duplicate username base,
    email conflict, exhausted candidates) rolls the whole operation back —
    no orphaned school, user, membership or role.

    Returns ``(school, admin_user, admin_username, password)`` where
    ``password`` is the plaintext password in force. The caller may return it
    to the user exactly once; it is never persisted here beyond the hash and
    is never written to audit logs.
    """
    from apps.accounts.models import (
        InstitutionMembership,
        Role,
        RoleAssignment,
    )
    from apps.schools.models import School, SchoolSettings

    admin_data = admin_data or {}
    with transaction.atomic():
        school = School.objects.create(**school_data)
        SchoolSettings.objects.get_or_create(school=school)

        base = admin_data.get("username") or f"admin-{school.code.lower()}"
        admin_user, admin_username, password = create_user_with_username(
            base,
            institution=school,
            email=admin_data.get("email") or None,
            password=admin_data.get("password") or None,
            first_name=admin_data.get("first_name", "School"),
            last_name=admin_data.get("last_name", school.name),
        )
        if admin_data.get("phone"):
            admin_user.phone = admin_data["phone"]
            admin_user.save(update_fields=["phone"])

        membership = InstitutionMembership.objects.create(
            user=admin_user,
            institution=school,
            status="active",
        )
        RoleAssignment.objects.create(membership=membership, role=Role.ADMIN)
        return school, admin_user, admin_username, password

def provision_campus_with_admin(campus_data, admin_data=None, school=None):
    """Create a campus together with its Campus Admin, atomically.

    A campus is only usable once it has a working admin user, so both must
    succeed or neither may. Within one transaction this creates:

      * the ``Campus`` (from validated create data; ``code`` auto-generated
        when blank),
      * an active ``InstitutionMembership`` plus a ``Role.CAMPUS_ADMIN``
        assignment binding the admin to *this* campus only (a foreign
        ``institution`` value in the payload is ignored — there is no
        cross-campus branch).

    The ``admin_data`` dict supports the same fields as
    ``provision_school_with_admin``. The ``school`` argument is retained for
    callers, but the campus's school is always authoritative.

    Returns ``(campus, admin_user, admin_username, password)`` where
    ``password`` is the plaintext password in force. The caller may return
    it to the user exactly once; it is never persisted here beyond the hash
    and is never written to audit logs.
    """
    from django.db import transaction
    from apps.accounts.models import (
        InstitutionMembership,
        Role,
        RoleAssignment,
    )
    from apps.schools.models import Campus, SchoolSettings

    admin_data = admin_data or {}
    with transaction.atomic():
        campus = Campus.objects.create(**campus_data)
        SchoolSettings.objects.get_or_create(school=campus.school)

        institution = campus.school
        if institution is None:
            raise ValueError("Campus must be associated with a School.")

        base = admin_data.get("username") or f"admin-{campus.name.lower().replace(' ', '-')}"
        admin_user, admin_username, password = create_user_with_username(
            base,
            institution=institution,
            email=admin_data.get("email") or None,
            password=admin_data.get("password") or None,
            first_name=admin_data.get("first_name", "Campus"),
            last_name=admin_data.get("last_name", campus.name),
        )
        if admin_data.get("phone"):
            admin_user.phone = admin_data["phone"]
            admin_user.save(update_fields=["phone"])

        membership = InstitutionMembership.objects.create(
            user=admin_user,
            institution=institution,
            status="active",
        )
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.CAMPUS_ADMIN,
            campus=campus,
        )

    return campus, admin_user, admin_username, password


# ---------------------------------------------------------------------------
# Canonical designation -> role resolution
# ---------------------------------------------------------------------------
# StaffProfile carries a free-text ``designation``. When an employee's login
# account is auto-provisioned, the designation is resolved to a canonical
# application role. Only designations with a recognised role are mapped; every
# other designation resolves to the generic ``staff`` role so no employee is
# ever silently granted a specialised role. New roles are added here with a
# matching entry in ``accounts.models.Role`` / ``ROLE_RANK``.

DESIGNATION_ROLE_MAP = {
    "counsellor": "counsellor",
    "security guard": "guard",
    "nurse": "nurse",
    "lady health worker": "nurse",
    "administrative officer": "administrative_officer",
    "librarian": "librarian",
}


def role_for_designation(designation):
    """Return the canonical role value for a StaffProfile ``designation``.

    Matching is case-insensitive and collapses whitespace so ``" Security
    Guard "`` resolves to ``guard``. Unrecognised designations always resolve
    to the generic ``staff`` role (never elevated, never invented).
    """
    from apps.accounts.models import Role

    normalized = " ".join((designation or "").strip().lower().split())
    role_value = DESIGNATION_ROLE_MAP.get(normalized, Role.STAFF)
    return Role(role_value)
