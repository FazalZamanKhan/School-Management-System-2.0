"""Regression tests for campus creation with optional admin provisioning.

Covers the Phase 154 regression: POST /api/schools/campuses/ with an ``admin``
block crashed with an ``UnboundLocalError`` (``campus`` referenced before the
``self.get_object()`` assignment) and produced an HTML 500 that the frontend
surfaced as "Request failed.".
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import (
    InstitutionMembership,
    Role,
    RoleAssignment,
    StaffProfile,
)
from apps.schools.models import Campus, School

User = get_user_model()


class CampusAdminProvisioningTests(TestCase):
    @staticmethod
    def _make_school(name, code):
        return School.objects.create(name=name, code=code, status="active")

    @staticmethod
    def _make_logged_in_admin(school, username="campus-admin-a"):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@test.edu",
            password="TestPass123!",
            first_name=username.title(),
            institution=school,
        )
        membership = InstitutionMembership.objects.create(
            user=user, institution=school, status="active"
        )
        RoleAssignment.objects.create(membership=membership, role=Role.ADMIN)
        return user

    def setUp(self):
        self.school = self._make_school("Provisioning School", "prov")
        self.other_school = self._make_school("Other School", "oth")
        self.admin = self._make_logged_in_admin(self.school)

        self.client = APIClient(enforce_csrf_checks=False)
        response = self.client.post(
            "/api/auth/login/",
            data={"username": "campus-admin-a", "password": "TestPass123!"},
            format="json",
        )
        assert response.status_code == 200, f"Login failed: {response.data}"

    def _create_campus(self, payload):
        return self.client.post(
            "/api/schools/campuses/",
            data=payload,
            format="json",
        )

    def test_create_campus_without_admin_block_succeeds(self):
        response = self._create_campus({
            "name": "Main Campus",
            "city": "Lahore",
        })
        self.assertEqual(response.status_code, 201, response.data)
        campus = Campus.objects.get(pk=response.data["id"])
        self.assertEqual(campus.school, self.school)
        self.assertEqual(campus.name, "Main Campus")
        self.assertNotIn("admin_username", response.data)
        self.assertEqual(
            User.objects.filter(memberships__institution=self.school).count(),
            1,  # only the school admin
        )

    def test_create_campus_with_admin_block_succeeds_and_provisions_user(self):
        response = self._create_campus({
            "name": "North Wing",
            "city": "Lahore",
            "admin": {
                "email": "north.principal@example.com",
                "first_name": "Noreen",
                "last_name": "Khan",
                "position": "principal",
            },
        })
        self.assertEqual(response.status_code, 201, response.data)

        campus = Campus.objects.get(pk=response.data["id"])
        self.assertEqual(campus.school, self.school)

        # Auto-generated username carries the campus name.
        self.assertTrue(
            response.data["admin_username"].startswith("principal-north-wing"),
            response.data,
        )
        # Auto-generated credential is returned exactly once and is non-blank.
        self.assertEqual(response.data["admin_email"], "north.principal@example.com")
        self.assertTrue(response.data["admin_password"])

        user = User.objects.get(username=response.data["admin_username"])
        self.assertEqual(user.email, "north.principal@example.com")
        self.assertEqual(user.institution, self.school)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.must_change_password)

        membership = InstitutionMembership.objects.get(user=user)
        self.assertEqual(membership.institution, self.school)
        self.assertEqual(membership.status, "active")

        assignment = RoleAssignment.objects.get(membership=membership)
        self.assertEqual(assignment.role, Role.PRINCIPAL)
        self.assertEqual(assignment.campus, campus)

        profile = StaffProfile.objects.get(user=user)
        self.assertEqual(profile.primary_campus, campus)
        self.assertEqual(profile.institution, self.school)

        # The provisioned principal can log in with the returned credential.
        principal_client = APIClient(enforce_csrf_checks=False)
        login = principal_client.post(
            "/api/auth/login/",
            data={
                "username": user.username,
                "password": response.data["admin_password"],
            },
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.data)

    def test_create_campus_admin_with_provided_username_password(self):
        response = self._create_campus({
            "name": "East Campus",
            "city": "Karachi",
            "admin": {
                "username": "east-camp-manager",
                "email": "east.manager@example.com",
                "password": "Provided#Pass99",
                "position": "campus_admin",
            },
        })
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["admin_username"], "east-camp-manager")
        self.assertEqual(response.data["admin_password"], "Provided#Pass99")

        user = User.objects.get(username="east-camp-manager")
        self.assertFalse(user.must_change_password)

        membership = InstitutionMembership.objects.get(user=user)
        assignment = RoleAssignment.objects.get(membership=membership)
        self.assertEqual(assignment.role, Role.CAMPUS_ADMIN)
        self.assertEqual(
            assignment.campus, Campus.objects.get(pk=response.data["id"])
        )

    def test_non_platform_admin_cannot_target_foreign_school(self):
        # A `school` key targeting another school is ignored for a normal
        # school admin: the campus still belongs to the admin's institution.
        response = self._create_campus({
            "name": "Tied Campus",
            "city": "Lahore",
            "school": self.other_school.id,
        })
        self.assertEqual(response.status_code, 201, response.data)
        campus = Campus.objects.get(pk=response.data["id"])
        self.assertEqual(campus.school, self.school)
        self.assertTrue(
            Campus.objects.filter(school=self.other_school, name="Tied Campus").count() == 0
        )

    def test_vice_principal_position_provisions_role(self):
        response = self._create_campus({
            "name": "West Campus",
            "city": "Lahore",
            "admin": {
                "email": "west.vp@example.com",
                "position": "vice_principal",
            },
        })
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username=response.data["admin_username"])
        membership = InstitutionMembership.objects.get(user=user)
        assignment = RoleAssignment.objects.get(membership=membership)
        self.assertEqual(assignment.role, Role.VICE_PRINCIPAL)

    def test_non_admin_cannot_create_campus(self):
        teacher = User.objects.create_user(
            username="plain-teacher",
            email="plain.teacher@test.edu",
            password="TestPass123!",
            institution=self.school,
        )
        membership = InstitutionMembership.objects.create(
            user=teacher, institution=self.school, status="active"
        )
        RoleAssignment.objects.create(membership=membership, role=Role.TEACHER)

        self.client = APIClient(enforce_csrf_checks=False)
        login = self.client.post(
            "/api/auth/login/",
            data={"username": "plain-teacher", "password": "TestPass123!"},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.data)

        response = self._create_campus({
            "name": "Forbidden Campus",
            "city": "Lahore",
        })
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(
            Campus.objects.filter(name="Forbidden Campus").exists()
        )