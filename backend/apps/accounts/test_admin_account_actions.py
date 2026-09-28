"""Authorization and side-effect tests for the admin account-action endpoints.

Covers AdminPasswordResetView and AdminUsernameChangeView:
  * unauthenticated / non-admin / cross-institution / cross-campus rejection
  * platform Super Admin is not bound to an institution
  * password reset side effects (hash, must_change_password, password_changed_at,
    session invalidation) and that the plaintext never leaks
  * per-institution username uniqueness, persistence and audit events
  * transaction rollback when a downstream step fails
"""

import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import (
    InstitutionMembership,
    Role,
    RoleAssignment,
    StaffProfile,
    UserSession,
)
from apps.audit.models import AuditLog
from apps.schools.models import Campus, School

User = get_user_model()
PASSWORD = "TestPass123!"


class AdminAccountActionTests(TestCase):
    """Two institutions, two campuses in the first, one actor per role."""

    def setUp(self):
        self.school_a = School.objects.create(name="Northfield Academy")
        self.school_b = School.objects.create(name="Southfield Academy")

        self.campus_a1 = Campus.objects.create(
            school=self.school_a, name="A1", status="active"
        )
        self.campus_a2 = Campus.objects.create(
            school=self.school_a, name="A2", status="active"
        )
        self.campus_b1 = Campus.objects.create(
            school=self.school_b, name="B1", status="active"
        )

        self.inst_admin = self._make_user("inst-admin", Role.ADMIN, self.school_a)
        self.campus_admin = self._make_user(
            "campus-admin", Role.CAMPUS_ADMIN, self.school_a, self.campus_a1
        )
        self.teacher = self._make_user(
            "teacher", Role.TEACHER, self.school_a, self.campus_a1
        )
        self.super_admin = self._make_user("super-admin", Role.SUPER_ADMIN, self.school_a)
        # Platform Super Admins legitimately carry a null institution.
        self.super_admin.institution = None
        self.super_admin.save(update_fields=["institution"])

        self.target_same = self._make_user(
            "target-same", Role.TEACHER, self.school_a, self.campus_a1
        )
        self.target_other_campus = self._make_user(
            "target-othercampus", Role.TEACHER, self.school_a, self.campus_a2
        )
        self.target_other_inst = self._make_user(
            "target-otherinst", Role.TEACHER, self.school_b, self.campus_b1
        )
        self.target_no_campus = self._make_user(
            "target-nocampus", Role.STAFF, self.school_a
        )

    def _make_user(self, username, role, institution, campus=None):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@test.edu",
            password=PASSWORD,
        )
        user.institution = institution
        user.save(update_fields=["institution"])
        membership = InstitutionMembership.objects.create(
            user=user, institution=institution
        )
        RoleAssignment.objects.create(membership=membership, role=role)
        if campus is not None:
            RoleAssignment.objects.create(
                membership=membership, role=role, campus=campus
            )
            StaffProfile.objects.create(
                user=user,
                employee_number=f"EMP-{username}",
                first_name="Test",
                last_name="User",
                gender="male",
                primary_campus=campus,
            )
        return user

    def _client(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_login(user)
        return client

    def _reset_url(self, user):
        return reverse("admin-password-reset", args=[user.pk])

    def _change_url(self, user):
        return reverse("admin-change-username", args=[user.pk])

    def _make_session(self, user, registered=True):
        """Create a real DB-backed session, optionally mirroring UserSession."""
        store = SessionStore()
        store["_auth_user_id"] = str(user.pk)
        store["_auth_user_hash"] = user.get_session_auth_hash()
        store.create()
        if registered:
            UserSession.objects.create(
                user=user,
                session_key=store.session_key,
                ip_address="127.0.0.1",
                expires_at=timezone.now() + timezone.timedelta(days=1),
            )
        return store.session_key

    # ------------------------------------------------------------------
    # Rejection paths
    # ------------------------------------------------------------------

    def test_unauthenticated_password_reset_returns_403(self):
        response = self._client().post(self._reset_url(self.target_same), {})
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_username_change_returns_403(self):
        response = self._client().post(
            self._change_url(self.target_same), {"new_username": "hijacked"}
        )
        self.assertEqual(response.status_code, 403)

    def test_institution_admin_cannot_reset_other_institution(self):
        response = self._client(self.inst_admin).post(
            self._reset_url(self.target_other_inst), {}
        )
        self.assertEqual(response.status_code, 403)
        self.target_other_inst.refresh_from_db()
        self.assertTrue(self.target_other_inst.check_password(PASSWORD))

    def test_campus_admin_cannot_reset_other_campus(self):
        response = self._client(self.campus_admin).post(
            self._reset_url(self.target_other_campus), {}
        )
        self.assertEqual(response.status_code, 403)
        self.target_other_campus.refresh_from_db()
        self.assertTrue(self.target_other_campus.check_password(PASSWORD))

    def test_non_admin_returns_403(self):
        response = self._client(self.teacher).post(
            self._reset_url(self.target_same), {}
        )
        self.assertEqual(response.status_code, 403)
        response = self._client(self.teacher).post(
            self._change_url(self.target_same), {"new_username": "nope"}
        )
        self.assertEqual(response.status_code, 403)

    def test_campus_admin_cannot_reset_target_without_campus(self):
        response = self._client(self.campus_admin).post(
            self._reset_url(self.target_no_campus), {}
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_target_returns_404_for_authorized_actor(self):
        response = self._client(self.inst_admin).post(
            reverse("admin-password-reset", args=[999999]), {}
        )
        self.assertEqual(response.status_code, 404)

    def test_unprivileged_actor_cannot_enumerate_missing_users(self):
        """Role gate runs before the lookup: 403 whether or not the id exists."""
        missing = self._client(self.teacher).post(
            reverse("admin-password-reset", args=[999999]), {}
        )
        existing = self._client(self.teacher).post(
            self._reset_url(self.target_same), {}
        )
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(existing.status_code, 403)

    # ------------------------------------------------------------------
    # Successful password reset
    # ------------------------------------------------------------------

    def test_password_reset_hashes_and_sets_flags(self):
        before = timezone.now()
        response = self._client(self.inst_admin).post(
            self._reset_url(self.target_same), {}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["must_change_password"])

        self.target_same.refresh_from_db()
        self.assertTrue(self.target_same.must_change_password)
        self.assertNotEqual(self.target_same.password, "")
        self.assertIn("$", self.target_same.password)
        self.assertFalse(self.target_same.check_password(PASSWORD))
        self.assertGreaterEqual(self.target_same.password_changed_at, before)

    def test_password_reset_invalidates_existing_sessions(self):
        registered_key = self._make_session(self.target_same, registered=True)
        unregistered_key = self._make_session(
            self.target_same, registered=False
        )
        stale_auth_hash = Session.objects.get(
            session_key=unregistered_key
        ).get_decoded()["_auth_user_hash"]

        response = self._client(self.inst_admin).post(
            self._reset_url(self.target_same), {}
        )
        self.assertEqual(response.status_code, 200)

        self.assertFalse(
            Session.objects.filter(session_key=registered_key).exists()
        )
        self.assertFalse(UserSession.objects.filter(user=self.target_same).exists())

        # An unregistered session survives as a row but can no longer
        # authenticate: the session auth hash no longer matches.
        self.target_same.refresh_from_db()
        self.assertNotEqual(
            stale_auth_hash, self.target_same.get_session_auth_hash()
        )

    def test_temporary_password_absent_from_response_and_audit(self):
        response = self._client(self.inst_admin).post(
            self._reset_url(self.target_same), {}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(
            r"Temporary password: (\S+)", mail.outbox[0].body
        )
        self.assertIsNotNone(match)
        temporary_password = match.group(1)

        audit = AuditLog.objects.filter(action="admin_password_reset").first()
        self.assertIsNotNone(audit)
        self.assertNotIn(temporary_password, repr(response.data))
        self.assertNotIn(temporary_password, repr(audit.details))
        self.assertNotIn(temporary_password, repr(audit.action))
        # The stored hash must not be the plaintext either.
        self.target_same.refresh_from_db()
        self.assertNotEqual(self.target_same.password, temporary_password)

    def test_password_reset_writes_audit_event(self):
        self._client(self.inst_admin).post(self._reset_url(self.target_same), {})
        audit = AuditLog.objects.filter(action="admin_password_reset").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.details["target_user_id"], str(self.target_same.pk))
        self.assertEqual(audit.details["target_username"], "target-same")
        self.assertNotIn("password", audit.details)

    def test_super_admin_can_reset_across_institutions(self):
        """A Super Admin with a null institution is not blocked by scoping."""
        self.assertIsNone(self.super_admin.institution_id)
        response = self._client(self.super_admin).post(
            self._reset_url(self.target_other_inst), {}
        )
        self.assertEqual(response.status_code, 200)
        self.target_other_inst.refresh_from_db()
        self.assertTrue(self.target_other_inst.must_change_password)

    def test_password_reset_rolls_back_when_audit_fails(self):
        original_hash = self.target_same.password
        client = self._client(self.inst_admin)
        client.raise_request_exception = False
        with patch(
            "apps.accounts.views.record_audit",
            side_effect=RuntimeError("audit backend down"),
        ):
            response = client.post(self._reset_url(self.target_same), {})
        self.assertEqual(response.status_code, 500)
        self.target_same.refresh_from_db()
        self.assertEqual(self.target_same.password, original_hash)
        self.assertFalse(self.target_same.must_change_password)
        self.assertEqual(mail.outbox, [])

    # ------------------------------------------------------------------
    # Username change
    # ------------------------------------------------------------------

    def test_duplicate_username_returns_400(self):
        response = self._client(self.inst_admin).post(
            self._change_url(self.target_same), {"new_username": "teacher"}
        )
        self.assertEqual(response.status_code, 400)
        self.target_same.refresh_from_db()
        self.assertEqual(self.target_same.username, "target-same")

    def test_missing_username_returns_400(self):
        response = self._client(self.inst_admin).post(
            self._change_url(self.target_same), {"new_username": "   "}
        )
        self.assertEqual(response.status_code, 400)

    def test_successful_username_change_persists_and_audits(self):
        response = self._client(self.inst_admin).post(
            self._change_url(self.target_same), {"new_username": "renamed-user"}
        )
        self.assertEqual(response.status_code, 200)
        self.target_same.refresh_from_db()
        self.assertEqual(self.target_same.username, "renamed-user")

        audit = AuditLog.objects.filter(action="admin_username_change").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.details["old_username"], "target-same")
        self.assertEqual(audit.details["target_username"], "renamed-user")

    def test_username_same_name_in_other_institution_is_allowed(self):
        """Uniqueness is per institution, matching unique_username_per_institution."""
        response = self._client(self.inst_admin).post(
            self._change_url(self.target_same), {"new_username": "target-otherinst"}
        )
        self.assertEqual(response.status_code, 200)

    def test_username_change_rolls_back_when_audit_fails(self):
        client = self._client(self.inst_admin)
        client.raise_request_exception = False
        with patch(
            "apps.accounts.views.record_audit",
            side_effect=RuntimeError("audit backend down"),
        ):
            response = client.post(
                self._change_url(self.target_same),
                {"new_username": "should-not-persist"},
            )
        self.assertEqual(response.status_code, 500)
        self.target_same.refresh_from_db()
        self.assertEqual(self.target_same.username, "target-same")
