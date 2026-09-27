"""Read-only diagnostic for school-scoped login failures (Phase 154).

For each admin-like account it prints the fields that decide scoped login:
``institution`` FK, membership rows/statuses, roles, and active flags, and it
runs the very ``scoped_user_queryset`` the login backend uses to report
exactly why ``scoped`` resolution finds or misses the account.

The command never writes, never prints password hashes, tokens, secrets or
backup codes. ``-`` is printed for any field not set.

Usage:
    python manage.py diagnose_login_access
    python manage.py diagnose_login_access --username 12345,XYZ
    python manage.py diagnose_login_access --school-alp
    python manage.py diagnose_login_access --json
"""
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import Role
from apps.schools.models import School

User = get_user_model()

TARGET_ROLES = {
    Role.ADMIN,
    Role.CAMPUS_ADMIN,
    Role.PRINCIPAL,
    Role.VICE_PRINCIPAL,
    Role.ORG_ADMIN,
    Role.HEAD_OFFICE,
    Role.ACADEMIC,
    Role.SUPER_ADMIN,
}


class Command(BaseCommand):
    help = "Diagnose why an admin account fails or succeeds school-scoped login."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="",
            help="Comma-separated usernames to inspect (case-insensitive).",
        )
        parser.add_argument(
            "--school",
            default=None,
            help="Only inspect accounts whose home institution code starts with this.",
        )
        parser.add_argument(
            "--include-superusers",
            action="store_true",
            help="Also report is_superuser=True accounts (FrostFire etc.).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit JSON instead of the human-readable report.",
        )

    @staticmethod
    def _mask_email(email):
        if not email:
            return "-"
        local, _, host = email.partition("@")
        if len(local) <= 3:
            return "***@" + host
        return f"{local[:3]}{'*' * (len(local) - 3)}@{host}"

    @staticmethod
    def _memberships(user):
        """Sorted (code, school_name, status, created_at) rows."""
        rows = []
        for m in user.memberships.select_related("institution").order_by(
            "institution__code"
        ):
            rows.append(
                {
                    "code": m.institution.code,
                    "school": m.institution.name,
                    "status": m.status,
                    "created": str(m.created_at)[:19] if m.created_at else "-",
                }
            )
        return rows

    @staticmethod
    def _roles(user):
        from apps.accounts.models import RoleAssignment

        rows = []
        for ra in RoleAssignment.objects.filter(
            membership__user=user, membership__status="active"
        ).select_related("membership__institution"):
            rows.append(
                {
                    "role": ra.role,
                    "code": ra.membership.institution.code,
                    "campus": ra.campus.name if ra.campus_id else "-",
                }
            )
        return rows

    def handle(self, *args, **options):
        from django.db.models import Q

        from apps.accounts.services import login_candidate_count, scoped_user_queryset

        usernames = [u.strip().lower() for u in options["username"].split(",") if u.strip()]
        school_filter = (options["school"] or "").lower()
        include_super = options["include_superusers"]
        as_json = options["json"]

        schools = list(
            School.objects.order_by("id").values("id", "name", "code", "status")
        )

        role_ids = set(
            User.objects.filter(
                memberships__role_assignments__role__in=TARGET_ROLES,
                memberships__role_assignments__membership__status="active",
            ).distinct().values_list("id", flat=True)
        )
        membership_user_ids = set(
            User.objects.filter(memberships__isnull=False).distinct().values_list("id", flat=True)
        )

        q = Q(id__in=(role_ids | membership_user_ids))
        if usernames:
            q &= Q(username__iregex="^(" + "|".join(usernames) + ")$")
        if not include_super:
            q &= Q(is_superuser=False)
        if school_filter:
            q &= Q(institution__code__icontains=school_filter)

        users = (
            User.objects.filter(q)
            .select_related("institution")
            .order_by("username")
        )

        report = []
        flagged = []
        for user in users:
            if usernames:
                needle = user.username.lower()
                if not any(u in needle for u in usernames):
                    continue
            if school_filter and user.institution_id:
                if school_filter not in user.institution.code.lower():
                    continue

            entry = {
                "username": user.username,
                "email": self._mask_email(user.email),
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "must_change_password": user.must_change_password,
                "locked_until": str(user.locked_until)[:19] if user.locked_until else "-",
                "failed_attempts": user.failed_login_attempts,
                "institution_fk": {
                    "id": user.institution_id,
                    "code": user.institution.code if user.institution_id else None,
                    "school": user.institution.name if user.institution_id else None,
                },
                "memberships": self._memberships(user),
                "roles": self._roles(user),
                "scoped_resolution": {},
            }

            # Run the same resolution the login backend performs: scoped by the
            # account's own institution code, then unscoped ambiguity count.
            if user.institution_id:
                entry["scoped_resolution"]["by_institution_code"] = (
                    scoped_user_queryset(
                        user.username, school_code=user.institution.code
                    ).filter(pk=user.pk).exists()
                )
                entry["scoped_resolution"]["candidate_count_in_home_school"] = (
                    scoped_user_queryset(
                        user.username, school_code=user.institution.code
                    ).count()
                )
            entry["scoped_resolution"]["global_candidate_count"] = (
                login_candidate_count(user.username)
            )

            # Flag shapes that yield failures at scoped login.
            reasons = []
            active_codes = {m["code"] for m in entry["memberships"] if m["status"] == "active"}
            fk_code = entry["institution_fk"]["code"]
            if user.institution_id and fk_code and fk_code not in active_codes:
                reasons.append(
                    "institution FK matches school but membership is inactive -> "
                    "login resolves, post-login check returns 'not a member'"
                )
            if user.institution_id is None and not active_codes:
                reasons.append(
                    "no institution FK and no active membership -> "
                    "scoped lookup misses -> 'Invalid credentials.'"
                )
            if user.institution_id and fk_code in active_codes and not user.is_active:
                reasons.append("account is inactive (is_active=False)")
            entry["flags"] = reasons
            if reasons:
                flagged.append(entry)

            report.append(entry)

        if as_json:
            self.stdout.write(json.dumps(
                {"schools": schools, "accounts": report}, indent=2, default=str
            ))
            return

        self.stdout.write("=" * 72)
        self.stdout.write(f"ACTIVE SCHOOLS ({len(schools)})")
        for s in schools:
            self.stdout.write(
                f"  id={s['id']:<4} code={str(s['code'] or '-'):<12} "
                f"status={str(s['status'] or '-'):<8} {s['name']}"
            )

        self.stdout.write("=" * 72)
        self.stdout.write(f"ACCOUNTS ({len(report)})")
        for e in report:
            self.stdout.write(f"\n  username: {e['username']}  email: {e['email']}")
            self.stdout.write(
                f"    active={e['is_active']} superuser={e['is_superuser']} "
                f"must_change={e['must_change_password']} locked_until={e['locked_until']} "
                f"failed={e['failed_attempts']}"
            )
            self.stdout.write(
                f"    institution FK: id={e['institution_fk']['id']} "
                f"code={e['institution_fk']['code']} school={e['institution_fk']['school']}"
            )
            for m in e["memberships"]:
                self.stdout.write(
                    f"    membership: {m['code']:<12} {m['status']:<10} "
                    f"created={m['created']}  ({m['school']})"
                )
            for r in e["roles"]:
                self.stdout.write(
                    f"    role: {r['role']:<14} code={r['code']:<12} campus={r['campus']}"
                )
            sr = e["scoped_resolution"]
            self.stdout.write(
                f"    scoped by home code: {sr.get('by_institution_code')} "
                f"candidates(home)={sr.get('candidate_count_in_home_school')} "
                f"candidates(global)={sr.get('global_candidate_count')}"
            )
            if e["flags"]:
                self.stdout.write(self.style.WARNING("    FLAGS: " + "; ".join(e["flags"])))
            else:
                self.stdout.write(self.style.SUCCESS("    OK: scoped login should work"))

        self.stdout.write("=" * 72)
        if flagged:
            self.stdout.write(
                self.style.ERROR(
                    f"{len(flagged)} account(s) match a shape that produces "
                    '"Invalid credentials." at scoped login.'
                )
            )
            raise SystemExit(2)
        self.stdout.write(
            self.style.SUCCESS(
                "No account matched a known failing shape. If logins still "
                "fail, capture the exact request payload (username / email / "
                "school_code) used."
            )
        )
        raise SystemExit(0)