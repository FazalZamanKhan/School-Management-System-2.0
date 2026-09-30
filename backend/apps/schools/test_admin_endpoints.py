"""HTTP-level tests for the School & Campus Admin Management endpoints.

Covers the six contracted routes exercised end-to-end over the wire:
- /api/schools/tenants/{pk}/admins/            GET  list school admins
- /api/schools/tenants/{pk}/assign_admin/      POST assign school admin
- /api/schools/tenants/{pk}/remove_admin/      POST remove school admin
- /api/schools/campuses/{pk}/admin/            GET  list campus admins
- /api/schools/campuses/{pk}/assign_admin/     POST assign campus admin
- /api/schools/campuses/{pk}/remove_admin/     POST remove campus admin

These previously returned Resolver404 because the custom ``@action`` methods
were never wired in apps/schools/urls.py.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import (
    InstitutionMembership,
    Role,
    RoleAssignment,
)
from apps.schools.models import Campus, School

User = get_user_model()


class AdminManagementBase(TestCase):
    """Two schools + a platform super admin and a per-school admin."""

    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(
            name="Admin Mgmt A", code="adm-a", status="active"
        )
        cls.school_b = School.objects.create(
            name="Admin Mgmt B", code="adm-b", status="active"
        )
        cls.campus_a = Campus.objects.create(
            school=cls.school_a, name="Campus A", status="active"
        )
        cls.campus_b = Campus.objects.create(
            school=cls.school_b, name="Campus B", status="active"
        )

        # Platform super admin (can manage any tenant).
        cls.platform = User.objects.create_user(
            username="platform_su",
            email="platform@test.edu",
            password="TestPass123!",
            is_superuser=True,
        )
        # Give the super admin an institution context (school A).
        InstitutionMembership.objects.create(
            user=cls.platform, institution=cls.school_a, status="active"
        )

        # School A admin and a candidate member in school A.
        cls.admin_a = cls._member("admin_a", Role.ADMIN, cls.school_a)
        cls.candidate_a = cls._member("candidate_a", None, cls.school_a)

        # School B admin and candidate member in school B.
        cls.admin_b = cls._member("admin_b", Role.ADMIN, cls.school_b)
        cls.candidate_b = cls._member("candidate_b", None, cls.school_b)

    @classmethod
    def _member(cls, username, role, school):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@test.edu",
            password="TestPass123!",
            first_name=username.title(),
        )
        membership = InstitutionMembership.objects.create(
            user=user, institution=school, status="active"
        )
        if role is not None:
            RoleAssignment.objects.create(
                membership=membership, role=role, campus=None
            )
        return user

    def _client_for(self, username):
        client = APIClient(enforce_csrf_checks=False)
        response = client.post(
            "/api/auth/login/",
            data={"username": username, "password": "TestPass123!"},
            format="json",
        )
        assert response.status_code == 200, f"Login failed: {response.data}"
        return client


class SchoolAdminEndpointTests(AdminManagementBase):
    def test_tenant_admins_lists_seeded_admin(self):
        client = self._client_for("platform_su")
        response = client.get(f"/api/schools/tenants/{self.school_b.pk}/admins/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["admins"][0]["user_id"], self.admin_b.pk)

    def test_tenant_assign_admin_cross_school_from_platform(self):
        client = self._client_for("platform_su")
        response = client.post(
            f"/api/schools/tenants/{self.school_b.pk}/assign_admin/",
            data={"user_id": self.candidate_b.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["username"], "candidate_b")

        # Listed now (admin_b is the seeded admin, candidate_b is new)
        listing = client.get(f"/api/schools/tenants/{self.school_b.pk}/admins/")
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual(listing.data["count"], 2)
        listed_user_ids = [a["user_id"] for a in listing.data["admins"]]
        self.assertIn(self.admin_b.pk, listed_user_ids)
        self.assertIn(self.candidate_b.pk, listed_user_ids)

        # RoleAssignment exists as school-level ADMIN (campus NULL)
        membership = InstitutionMembership.objects.get(
            user=self.candidate_b, institution=self.school_b
        )
        assignment = RoleAssignment.objects.get(
            membership=membership, role=Role.ADMIN, campus__isnull=True
        )
        self.assertIsNotNone(assignment)

    def test_tenant_assign_duplicate_is_rejected(self):
        client = self._client_for("platform_su")
        first = client.post(
            f"/api/schools/tenants/{self.school_b.pk}/assign_admin/",
            data={"user_id": self.candidate_b.pk},
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)
        second = client.post(
            f"/api/schools/tenants/{self.school_b.pk}/assign_admin/",
            data={"user_id": self.candidate_b.pk},
            format="json",
        )
        self.assertEqual(second.status_code, 400, second.data)
        membership = InstitutionMembership.objects.get(
            user=self.candidate_b, institution=self.school_b
        )
        self.assertEqual(
            RoleAssignment.objects.filter(
                membership=membership, role=Role.ADMIN, campus__isnull=True
            ).count(),
            1,
        )

    def test_tenant_assign_rejects_user_without_membership(self):
        no_member = User.objects.create_user(
            username="no_member",
            email="no_member@test.edu",
            password="TestPass123!",
        )
        client = self._client_for("platform_su")
        response = client.post(
            f"/api/schools/tenants/{self.school_b.pk}/assign_admin/",
            data={"user_id": no_member.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

    def test_tenant_remove_admin(self):
        client = self._client_for("platform_su")
        assign = client.post(
            f"/api/schools/tenants/{self.school_b.pk}/assign_admin/",
            data={"user_id": self.candidate_b.pk},
            format="json",
        )
        self.assertEqual(assign.status_code, 201, assign.data)

        remove = client.post(
            f"/api/schools/tenants/{self.school_b.pk}/remove_admin/",
            data={"user_id": self.candidate_b.pk},
            format="json",
        )
        self.assertEqual(remove.status_code, 200, remove.data)
        listing = client.get(f"/api/schools/tenants/{self.school_b.pk}/admins/")
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(
            listing.data["admins"][0]["user_id"], self.admin_b.pk
        )

    def test_tenant_remove_admin_for_non_admin_is_404(self):
        client = self._client_for("platform_su")
        response = client.post(
            f"/api/schools/tenants/{self.school_b.pk}/remove_admin/",
            data={"user_id": self.candidate_b.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 404, response.data)

    def test_cross_tenant_isolation_school_admins(self):
        """School A admin must not read or modify school B's admins."""
        client = self._client_for("admin_a")
        for method, path in [
            ("get", f"/api/schools/tenants/{self.school_b.pk}/admins/"),
            ("post", f"/api/schools/tenants/{self.school_b.pk}/assign_admin/"),
            ("post", f"/api/schools/tenants/{self.school_b.pk}/remove_admin/"),
        ]:
            response = getattr(client, method)(path, data={}, format="json")
            self.assertIn(
                response.status_code, (403, 404),
                f"{method} {path} should be denied, got {response.status_code}",
            )

    def test_own_school_admin_can_manage_own_school_admins(self):
        client = self._client_for("admin_a")
        assign = client.post(
            f"/api/schools/tenants/{self.school_a.pk}/assign_admin/",
            data={"user_id": self.candidate_a.pk},
            format="json",
        )
        self.assertEqual(assign.status_code, 201, assign.data)
        listing = client.get(f"/api/schools/tenants/{self.school_a.pk}/admins/")
        self.assertEqual(listing.data["count"], 2)
        listed_user_ids = [a["user_id"] for a in listing.data["admins"]]
        self.assertIn(self.admin_a.pk, listed_user_ids)
        self.assertIn(self.candidate_a.pk, listed_user_ids)


class CampusAdminEndpointTests(AdminManagementBase):
    def test_campus_admin_list_is_empty_initially(self):
        client = self._client_for("admin_a")
        response = client.get(f"/api/schools/campuses/{self.campus_a.pk}/admin/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 0)

    def test_campus_assign_admin_within_own_school(self):
        client = self._client_for("admin_a")
        response = client.post(
            f"/api/schools/campuses/{self.campus_a.pk}/assign_admin/",
            data={"user_id": self.candidate_a.pk, "role": "campus_admin"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        listing = client.get(f"/api/schools/campuses/{self.campus_a.pk}/admin/")
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["admins"][0]["role"], Role.CAMPUS_ADMIN)

    def test_campus_singleton_conflict_principal(self):
        client = self._client_for("admin_a")
        first = client.post(
            f"/api/schools/campuses/{self.campus_a.pk}/assign_admin/",
            data={"user_id": self.candidate_a.pk, "role": "principal"},
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)

        other = self._member("other_staff", None, self.school_a)
        second = client.post(
            f"/api/schools/campuses/{self.campus_a.pk}/assign_admin/",
            data={"user_id": other.pk, "role": "principal"},
            format="json",
        )
        self.assertEqual(second.status_code, 400, second.data)

    def test_campus_duplicate_role_for_same_user_rejected(self):
        client = self._client_for("admin_a")
        first = client.post(
            f"/api/schools/campuses/{self.campus_a.pk}/assign_admin/",
            data={"user_id": self.candidate_a.pk, "role": "vice_principal"},
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)
        second = client.post(
            f"/api/schools/campuses/{self.campus_a.pk}/assign_admin/",
            data={"user_id": self.candidate_a.pk, "role": "vice_principal"},
            format="json",
        )
        # Two requests produce exactly one campus-level assignment.
        self.assertEqual(second.status_code, 400, second.data)
        membership = InstitutionMembership.objects.get(
            user=self.candidate_a, institution=self.school_a
        )
        self.assertEqual(
            RoleAssignment.objects.filter(
                membership=membership,
                role=Role.VICE_PRINCIPAL,
                campus=self.campus_a,
            ).count(),
            1,
        )

    def test_campus_remove_admin_specific_role(self):
        client = self._client_for("admin_a")
        assign = client.post(
            f"/api/schools/campuses/{self.campus_a.pk}/assign_admin/",
            data={"user_id": self.candidate_a.pk, "role": "campus_admin"},
            format="json",
        )
        self.assertEqual(assign.status_code, 201, assign.data)
        remove = client.post(
            f"/api/schools/campuses/{self.campus_a.pk}/remove_admin/",
            data={"user_id": self.candidate_a.pk, "role": "campus_admin"},
            format="json",
        )
        self.assertEqual(remove.status_code, 200, remove.data)
        listing = client.get(f"/api/schools/campuses/{self.campus_a.pk}/admin/")
        self.assertEqual(listing.data["count"], 0)

    def test_cross_tenant_isolation_campus_admins(self):
        """School A admin must not read or modify school B's campus admins."""
        client = self._client_for("admin_a")
        for method, path in [
            ("get", f"/api/schools/campuses/{self.campus_b.pk}/admin/"),
            ("post", f"/api/schools/campuses/{self.campus_b.pk}/assign_admin/"),
            ("post", f"/api/schools/campuses/{self.campus_b.pk}/remove_admin/"),
        ]:
            response = getattr(client, method)(path, data={}, format="json")
            self.assertIn(
                response.status_code, (403, 404),
                f"{method} {path} should be denied, got {response.status_code}",
            )

    def test_platform_admin_can_manage_any_campus(self):
        client = self._client_for("platform_su")
        assign = client.post(
            f"/api/schools/campuses/{self.campus_b.pk}/assign_admin/",
            data={"user_id": self.candidate_b.pk, "role": "principal"},
            format="json",
        )
        self.assertEqual(assign.status_code, 201, assign.data)
        listing = client.get(f"/api/schools/campuses/{self.campus_b.pk}/admin/")
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["admins"][0]["role"], Role.PRINCIPAL)