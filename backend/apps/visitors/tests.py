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
from apps.visitors.models import Visitor


class VisitorsTestsBase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.school = School.objects.create(name="Test School")
        self.campus = Campus.objects.create(
            school=self.school,
            name="Main Campus",
        )
        self.north = Campus.objects.create(
            school=self.school,
            name="North Campus",
        )

        self.admin = self._make_user("admin", Role.ADMIN)
        self.guard = self._make_user("guard", Role.GUARD, self.campus)
        self.student = self._make_user("student", Role.STUDENT)
        self.campus_admin = self._make_user(
            "northadmin",
            Role.CAMPUS_ADMIN,
            self.north,
        )

    def _make_user(self, username, role, campus=None):
        user = get_user_model().objects.create_user(
            username=username,
            email=f"{username}@test.edu",
            password="TestPass123!",
        )
        membership = InstitutionMembership.objects.create(
            user=user,
            institution=self.school,
        )
        RoleAssignment.objects.create(
            membership=membership,
            role=role,
            campus=campus if role == Role.CAMPUS_ADMIN else None,
        )
        if campus is not None:
            StaffProfile.objects.create(
                user=user,
                institution=self.school,
                employee_number=f"EMP-{username.upper()}",
                first_name=username,
                last_name="User",
                gender="male",
                primary_campus=campus,
                status="active",
            )
        return user

    def login(self, username):
        self.client.force_login(get_user_model().objects.get(username=username))

    def _check_in(self, **kwargs):
        values = {
            "campus": self.campus.pk,
            "full_name": "Ahmed Raza",
            "phone": "03001112222",
            "purpose": "Meeting",
            "meeting_party": "Principal",
        }
        values.update(kwargs)
        return self.client.post(
            "/api/visitors/visitors/",
            values,
            format="json",
        )


class GateTests(VisitorsTestsBase):
    def test_guard_checks_in_visitor_with_badge(self):
        self.login("guard")

        response = self._check_in()

        self.assertEqual(response.status_code, 201, response.content)
        visitor = Visitor.objects.get()
        self.assertEqual(visitor.status, "checked_in")
        self.assertTrue(visitor.badge_number.startswith("VST-"))
        self.assertEqual(visitor.campus_id, self.campus.pk)
        self.assertIsNotNone(visitor.check_in)
        self.assertIsNone(visitor.check_out)

    def test_checkout_flow(self):
        self.login("guard")
        visitor_id = self._check_in().json()["id"]

        response = self.client.post(
            f"/api/visitors/visitors/{visitor_id}/checkout/"
        )

        self.assertEqual(response.status_code, 200, response.content)
        visitor = Visitor.objects.get(pk=visitor_id)
        self.assertEqual(visitor.status, "checked_out")
        self.assertIsNotNone(visitor.check_out)

    def test_stats_endpoint(self):
        self.login("guard")
        self._check_in()

        response = self.client.get("/api/visitors/visitors/stats/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["checked_in_now"], 1)
        self.assertEqual(response.data["today"], 1)

    def test_student_role_denied(self):
        self.login("student")

        response = self._check_in()

        self.assertEqual(response.status_code, 403)

    def test_campus_admin_only_sees_own_campus(self):
        self.login("admin")
        self._check_in()
        self._check_in(
            full_name="Zainab",
            campus=self.north.pk,
        )

        self.login("northadmin")
        response = self.client.get("/api/visitors/visitors/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["campus_name"], "North Campus")
