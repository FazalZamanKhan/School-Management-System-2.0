"""PROMPT-6: super-admin-only school creation, atomic admin provisioning, RBAC.

Covers:
  * Super Admin creating a school with a provisioned School Admin
  * Non-Super-Admin roles being denied school creation
  * Auto-generated admin username / school code / temporary credentials
  * Explicit password + credentials returned exactly once (never audited)
  * No cross-school / foreign-institution assignment possible
  * Transaction rollback when admin provisioning fails (no orphaned school,
    user, membership or role)
  * Duplicate school-code handling
  * RBAC enforcement (school admin cannot switch schools, cannot escalate to
    super_admin; accountant is school-limited)
  * Switching active institution does NOT deactivate the previous school
"""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import (
    InstitutionMembership,
    Role,
    RoleAssignment,
)
from apps.audit.models import AuditLog
from apps.schools.models import School, SchoolSettings
from apps.schools.services import school_code_for_name
from apps.accounts.access import user_allowed_campus_ids
from apps.accounts.services import provision_campus_with_admin

User = get_user_model()

SUPER_PASSWORD = "Sa#Pass!!123"
MEMBER_PASSWORD = "TestPass123!"

CREATE_URL = "/api/auth/super-admin/schools/create/"
LIST_URL = "/api/auth/super-admin/schools/"
SWITCH_URL = "/api/auth/super-admin/switch/"
ACTIVE_INSTITUTION_URL = "/api/auth/active-institution/"


class CampusAdminProvisioningTests(TestCase):
    def test_provisioned_admin_can_access_own_campus(self):
        school = School.objects.create(name="Campus Provisioning School")
        other_school = School.objects.create(name="Other School")
        campus, admin, _, _ = provision_campus_with_admin(
            {"school": school, "name": "Main Campus"},
            {"email": "campus-admin@example.test"},
            school=other_school,
        )

        self.assertTrue(
            RoleAssignment.objects.filter(
                membership__user=admin,
                role=Role.CAMPUS_ADMIN,
                campus=campus,
            ).exists()
        )
        self.assertTrue(
            InstitutionMembership.objects.filter(user=admin, institution=school).exists()
        )
        self.assertEqual(user_allowed_campus_ids(admin, institution=school), {campus.pk})


class ProvisioningBase(TestCase):
    def setUp(self):
        self.hq = School.objects.create(name="Perfect HQ", code="HQ-PLATFORM")
        self.other = School.objects.create(name="Sialkot School", code="SKT-900")

        self.super_admin = User.objects.create_superuser(
            username="platform-sa",
            email="platform@perfectfoundation.local",
            password=SUPER_PASSWORD,
        )
        self.sa_membership = InstitutionMembership.objects.create(
            user=self.super_admin,
            institution=self.hq,
            status="active",
        )
        RoleAssignment.objects.create(
            membership=self.sa_membership,
            role=Role.SUPER_ADMIN,
        )

        self.super_client = APIClient()
        self._login(self.super_client, self.super_admin.username, SUPER_PASSWORD)

    def _role_user(self, username, role, school):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@test.edu",
            password=MEMBER_PASSWORD,
        )
        if school is not None:
            membership = InstitutionMembership.objects.create(
                user=user,
                institution=school,
                status="active",
            )
            RoleAssignment.objects.create(membership=membership, role=role)
        return user

    def _login(self, client, username, password, school_code=None):
        client.post("/api/auth/csrf/", {}, format="json")
        payload = {"username": username, "password": password}
        if school_code:
            payload["school_code"] = school_code
        return client.post("/api/auth/login/", payload, format="json")

    def _create(self, client, **overrides):
        payload = {
            "name": "Lahore School",
            "institution_type": "school",
            "city": "Lahore",
        }
        payload.update(overrides)
        return client.post(CREATE_URL, payload, format="json")


class SchoolCreationTests(ProvisioningBase):
    def test_super_admin_creates_school_with_provisioned_admin(self):
        resp = self._create(
            self.super_client,
            code="LHR-001",
            admin_username="lhr-admin",
            admin_email="lhr@test.edu",
        )
        self.assertEqual(resp.status_code, 201)

        data = resp.json()
        school = School.objects.get(code="LHR-001")
        self.assertEqual(school.status, "active")
        self.assertTrue(SchoolSettings.objects.filter(school=school).exists())

        admin = User.objects.get(username="lhr-admin")
        self.assertEqual(admin.institution_id, school.pk)
        self.assertTrue(admin.must_change_password)

        creds = data["admin_credentials"]
        self.assertEqual(creds["school_code"], "LHR-001")
        self.assertTrue(admin.check_password(creds["password"]))
        self.assertEqual(len(creds["password"]), 14)

        membership = InstitutionMembership.objects.get(
            user=admin, institution=school
        )
        self.assertEqual(membership.status, "active")
        self.assertTrue(
            RoleAssignment.objects.filter(
                membership=membership, role=Role.ADMIN
            ).exists()
        )
        self.assertEqual(data["school"]["status"], "active")

    def test_super_admin_creates_school_with_auto_admin_and_code(self):
        resp = self._create(self.super_client, name="Multan School")
        self.assertEqual(resp.status_code, 201)

        data = resp.json()
        school = School.objects.get(name="Multan School")
        # Code is now name-derived (first letters of the meaningful words),
        # not a fixed PF- prefix. A numeric suffix is appended if the bare
        # prefix is already taken by another school in the DB.
        self.assertTrue(school.code)
        self.assertTrue(school.code.startswith("MS"))
        self.assertEqual(
            data["admin_credentials"]["username"],
            f"admin-{school.code.lower()}",
        )
        self.assertTrue(data["admin_credentials"]["password"])

    def test_auto_generated_school_has_usable_settings_and_admin_role(self):
        resp = self._create(self.super_client, name="Quetta School")
        self.assertEqual(resp.status_code, 201)
        school = School.objects.get(name="Quetta School")
        admin = User.objects.get(username=f"admin-{school.code.lower()}")
        self.assertEqual(admin.get_roles(school), [Role.ADMIN])


class AuthorizationTests(ProvisioningBase):
    def test_every_non_super_admin_role_cannot_create_schools(self):
        school = self.other
        for role in (
            Role.ADMIN,
            Role.ACCOUNTANT,
            Role.TEACHER,
            Role.STUDENT,
            Role.STAFF,
        ):
            user = self._role_user(f"deny-{role}", role, school)
            client = APIClient()
            self.assertEqual(self._login(client, user.username, MEMBER_PASSWORD).status_code, 200, role)
            resp = self._create(client, name=f"Blocked {role}")
            self.assertEqual(resp.status_code, 403, role)

    def test_unauthenticated_create_denied(self):
        resp = APIClient().post(
            CREATE_URL, {"name": "No Auth School"}, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_school_admin_cannot_access_super_admin_endpoints(self):
        self._role_user("sadmn", Role.ADMIN, self.other)
        client = APIClient()
        self._login(client, "sadmn", MEMBER_PASSWORD)

        self.assertEqual(client.get(LIST_URL).status_code, 403)
        resp = client.post(
            SWITCH_URL, {"institution_id": self.hq.pk}, format="json"
        )
        self.assertEqual(resp.status_code, 403)
        resp = self._create(client, name="Escalation School")
        self.assertEqual(resp.status_code, 403)

    def test_school_admin_cannot_switch_school_via_active_institution(self):
        self._role_user("sadmn2", Role.ADMIN, self.other)
        client = APIClient()
        self._login(client, "sadmn2", MEMBER_PASSWORD)

        base_switch = client.post(
            ACTIVE_INSTITUTION_URL,
            {"institution_id": self.hq.pk},
            format="json",
        )
        self.assertEqual(base_switch.status_code, 403)
        self.assertEqual(
            client.session.get("active_institution_id"), self.other.pk
        )

    def test_accountant_is_school_limited(self):
        self._role_user("sact", Role.ACCOUNTANT, self.other)
        client = APIClient()
        self._login(client, "sact", MEMBER_PASSWORD)

        resp = self._create(client, name="Accountant School")
        self.assertEqual(resp.status_code, 403)
        resp = client.post(
            ACTIVE_INSTITUTION_URL,
            {"institution_id": self.hq.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_school_admin_cannot_become_super_admin(self):
        admin = self._role_user("climber", Role.ADMIN, self.other)
        membership = admin.memberships.get(institution=self.other)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RoleAssignment.objects.create(
                    membership=membership,
                    role=Role.SUPER_ADMIN,
                )
        admin.refresh_from_db()
        self.assertFalse(admin.is_superuser)
        self.assertEqual(
            set(admin.get_roles(self.other)), {Role.ADMIN}
        )


class AssignmentIntegrityTests(ProvisioningBase):
    def test_admin_is_bound_to_new_school_only(self):
        resp = self._create(
            self.super_client,
            code="LHR-002",
            admin_username="bound-admin",
            admin_email="bound@test.edu",
            institution=self.other.pk,
            admin_institution=self.other.pk,
        )
        self.assertEqual(resp.status_code, 201)
        school = School.objects.get(code="LHR-002")
        admin = User.objects.get(username="bound-admin")
        self.assertEqual(admin.institution_id, school.pk)
        self.assertNotEqual(admin.institution_id, self.other.pk)
        membership = admin.memberships.get()
        self.assertEqual(membership.institution_id, school.pk)

    def test_per_school_admin_usernames_are_independent(self):
        resp_a = self._create(
            self.super_client,
            code="LHR-100",
            admin_username="cap",
            admin_email="cap-a@test.edu",
        )
        resp_b = self._create(
            self.super_client,
            code="LHR-101",
            admin_username="cap",
            admin_email="cap-b@test.edu",
        )
        self.assertEqual(resp_a.status_code, 201)
        self.assertEqual(resp_b.status_code, 201)

        a_users = User.objects.filter(username="cap")
        self.assertEqual(a_users.count(), 2)
        self.assertEqual(
            set(a_users.values_list("institution_id", flat=True)),
            set(School.objects.filter(code__in=["LHR-100", "LHR-101"]).values_list("pk", flat=True)),
        )

    def test_admin_provisioning_failure_rolls_back_entire_school(self):
        school_count = School.objects.count()
        user_count = User.objects.count()
        membership_count = InstitutionMembership.objects.count()
        assignment_count = RoleAssignment.objects.count()

        resp = self._create(
            self.super_client,
            name="Rollback School",
            admin_email="platform@perfectfoundation.local",
        )
        self.assertEqual(resp.status_code, 400)

        self.assertEqual(School.objects.count(), school_count)
        self.assertEqual(User.objects.count(), user_count)
        self.assertEqual(InstitutionMembership.objects.count(), membership_count)
        self.assertEqual(RoleAssignment.objects.count(), assignment_count)

    def test_weak_admin_password_rejected_before_provisioning(self):
        school_count = School.objects.count()
        resp = self._create(
            self.super_client,
            code="LHR-777",
            admin_username="weak",
            admin_password="12345678",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(School.objects.count(), school_count)
        self.assertFalse(User.objects.filter(username="weak").exists())

    def test_duplicate_school_code_rejected(self):
        first = self._create(
            self.super_client,
            code="DUP-001",
            admin_username="dupa",
            admin_email="dupa@test.edu",
        )
        self.assertEqual(first.status_code, 201)

        second = self._create(
            self.super_client,
            code="DUP-001",
            admin_username="dupb",
            admin_email="dupb@test.edu",
        )
        self.assertEqual(second.status_code, 400)
        self.assertEqual(School.objects.filter(code="DUP-001").count(), 1)
        self.assertFalse(User.objects.filter(username="dupb").exists())


class CredentialSecurityTests(ProvisioningBase):
    def test_explicit_password_used_and_credentials_not_leaked(self):
        resp = self._create(
            self.super_client,
            code="LHR-300",
            admin_username="explicit-adm",
            admin_password="Explicit!Pass123",
            admin_email="explicit@test.edu",
        )
        self.assertEqual(resp.status_code, 201)

        data = resp.json()
        creds = data["admin_credentials"]
        self.assertEqual(creds["password"], "Explicit!Pass123")

        admin = User.objects.get(username="explicit-adm")
        self.assertFalse(admin.must_change_password)
        self.assertTrue(admin.check_password("Explicit!Pass123"))
        self.assertFalse(admin.password.startswith("Explicit!"))

        audit = AuditLog.objects.get(
            action="school_create",
            object_id=str(admin.institution_id),
        )
        self.assertNotIn("password", audit.details)

        list_data = self.super_client.get(LIST_URL).json()
        for school_payload in list_data:
            self.assertNotIn("admin_credentials", school_payload)

    def test_provisioned_admin_can_login_access_own_school_only(self):
        resp = self._create(
            self.super_client,
            code="LHR-301",
            admin_username="fresh-admin",
            admin_email="fresh@test.edu",
        )
        self.assertEqual(resp.status_code, 201)
        creds = resp.json()["admin_credentials"]

        client = APIClient()
        login = self._login(
            client,
            creds["username"],
            creds["password"],
            school_code=creds["school_code"],
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("primary_role", login.json())
        self.assertEqual(login.json()["primary_role"], Role.ADMIN)

        active = client.get(ACTIVE_INSTITUTION_URL)
        self.assertEqual(active.status_code, 200)
        self.assertIn(Role.ADMIN, active.json()["roles"])

        blocked = client.post(
            ACTIVE_INSTITUTION_URL,
            {"institution_id": self.hq.pk},
            format="json",
        )
        self.assertEqual(blocked.status_code, 403)


class SwitchSemanticsTests(ProvisioningBase):
    def test_super_admin_switch_does_not_deactivate_previous_school(self):
        first = self._create(self.super_client, code="SWT-001").json()["school"]
        second = self._create(self.super_client, code="SWT-002").json()["school"]

        resp = self.super_client.post(
            SWITCH_URL, {"institution_id": second["id"]}, format="json"
        )
        self.assertEqual(resp.status_code, 200)

        first_school = School.objects.get(pk=first["id"])
        second_school = School.objects.get(pk=second["id"])
        self.assertEqual(first_school.status, "active")
        self.assertEqual(second_school.status, "active")
        self.assertEqual(
            self.super_client.session.get("active_institution_id"),
            second["id"],
        )
