"""P5 tenant and campus isolation tests.

The AI endpoints must never leak records across schools or across campuses
the user is not allowed to see, even when identifiers collide.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.schools.models import Campus, Class, Section
from apps.students.models import Enrollment

from .helpers import (
    make_member_user,
    make_school,
    make_structure,
    make_student,
    make_staff_profile,
    make_teacher,
)


class AiTenantIsolationTests(TestCase):
    """Two schools must never see each other's data through AI endpoints."""

    def setUp(self):
        self.school_a = make_school("Alpha", "al")
        self.school_b = make_school("Beta", "be")
        self.structure_a = make_structure(self.school_a)
        self.structure_b = make_structure(self.school_b)
        self.student_a = make_student(
            self.school_a,
            self.structure_a,
            name="Zara Alpha",
            admission="ADM-SHARED",
        )
        self.student_b = make_student(
            self.school_b,
            self.structure_b,
            name="Zara Beta",
            admission="ADM-SHARED",
        )
        self.admin_a = make_member_user(self.school_a, "al-admin", Role.ADMIN)
        self.admin_b = make_member_user(self.school_b, "be-admin", Role.ADMIN)

    def _client(self, username):
        client = APIClient()
        self.assertTrue(client.login(username=username, password="TestPass123!"))
        return client

    def test_search_never_leaks_across_schools(self):
        response = self._client("al-admin").get(
            "/api/ai/search/", {"q": "ADM-SHARED"}
        )
        self.assertEqual(response.status_code, 200)
        student_ids = [
            entry["id"]
            for entry in response.json()["entities"]
            if entry["kind"] == "student"
        ]
        self.assertEqual(student_ids, [self.student_a.pk])

    def test_ask_counts_scoped_to_the_active_school(self):
        client = self._client("al-admin")
        response = client.post(
            "/api/ai/ask/", {"query": "how many students"}, format="json"
        )
        self.assertEqual(response.json()["intent"], "counts")
        self.assertEqual(response.json()["digest"]["students"], 1)

    def test_student_insights_excludes_foreign_student_id(self):
        client = self._client("al-admin")
        response = client.get(
            "/api/ai/insights/students/", {"student_id": self.student_b.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["insights"], [])


class AiCampusIsolationTests(TestCase):
    """A campus-scoped principal only sees their own campus."""

    def setUp(self):
        self.school = make_school("Campus Iso", "cis")
        self.structure_main = make_structure(self.school, campus_name="Main", year_name="2025-2026")
        # North campus needs its own class structure with different year name
        self.structure_north = make_structure(self.school, campus_name="North", year_name="2025-2026-North")
        self.north_campus = self.structure_north["campus"]

        self.student_main = make_student(
            self.school,
            self.structure_main,
            name="Main Kid",
            admission="ADM-M1",
        )
        self.student_main.primary_campus = self.structure_main["campus"]
        self.student_main.save()

        self.student_north = make_student(
            self.school,
            self.structure_north,
            name="North Kid",
            admission="ADM-N1",
        )
        self.student_north.primary_campus = self.north_campus
        self.student_north.save()

        self.principal = make_member_user(
            self.school, "cis-principal", Role.PRINCIPAL, campus=self.north_campus
        )
        self.membership = self.principal.memberships.get(institution=self.school)
        make_staff_profile(self.principal, self.membership, self.school, self.north_campus)

    def _client(self):
        client = APIClient()
        self.assertTrue(
            client.login(username="cis-principal", password="TestPass123!")
        )
        return client

    def test_search_only_returns_own_campus_students(self):
        response = self._client().get("/api/ai/search/", {"q": "Kid"})
        self.assertEqual(response.status_code, 200)
        student_ids = [
            entry["id"]
            for entry in response.json()["entities"]
            if entry["kind"] == "student"
        ]
        self.assertEqual(student_ids, [self.student_north.pk])

    def test_insights_only_include_own_campus_students(self):
        response = self._client().get("/api/ai/insights/students/")
        self.assertEqual(response.status_code, 200)
        ids = [entry["id"] for entry in response.json()["insights"]]
        self.assertEqual(ids, [self.student_north.pk])

    def test_requesting_another_campus_is_rejected(self):
        response = self._client().get(
            "/api/ai/insights/students/",
            {"campus": self.structure_main["campus"].pk},
        )
        self.assertEqual(response.status_code, 403)


class AiTeacherSelfScopeTests(TestCase):
    """A teacher's insights stop at their own class."""

    def setUp(self):
        self.school = make_school("Teacher Scope", "tts")
        self.structure = make_structure(self.school)
        self.student = make_student(
            self.school, self.structure, name="My Student", admission="ADM-T1"
        )
        self.student.primary_campus = self.structure["campus"]
        self.student.save()

        grade7 = Class.objects.create(
            unit=self.structure["class_obj"].unit, name="Grade 7"
        )
        section7 = Section.objects.create(class_obj=grade7, name="A")
        self.other = make_student(
            self.school, self.structure, name="Other Student", admission="ADM-T2"
        )
        self.other.primary_campus = self.structure["campus"]
        self.other.save()
        other_enrollment = Enrollment.objects.get(student=self.other, status="active")
        other_enrollment.class_obj = grade7
        other_enrollment.section = section7
        other_enrollment.save()

        self.teacher_user = make_member_user(self.school, "tts-teacher", Role.TEACHER)
        self.membership = self.teacher_user.memberships.get(institution=self.school)
        make_teacher(
            self.teacher_user,
            self.membership,
            self.school,
            self.structure,
            first="Clas",
            last="Teacher",
        )

    def test_teacher_sees_only_assigned_class_students(self):
        client = APIClient()
        self.assertTrue(client.login(username="tts-teacher", password="TestPass123!"))
        response = client.get("/api/ai/insights/students/")
        self.assertEqual(response.status_code, 200)
        ids = [entry["id"] for entry in response.json()["insights"]]
        self.assertEqual(ids, [self.student.pk])

    def test_teacher_search_excludes_other_class(self):
        client = APIClient()
        self.assertTrue(client.login(username="tts-teacher", password="TestPass123!"))
        response = client.get("/api/ai/search/", {"q": "Student"})
        student_ids = [
            entry["id"]
            for entry in response.json()["entities"]
            if entry["kind"] == "student"
        ]
        self.assertEqual(student_ids, [self.student.pk])
