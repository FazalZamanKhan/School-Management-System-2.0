"""Tests for P4 enterprise capabilities added to the schools app.

Covers academic-year / term status workflows and the annotated
class/section headcount endpoints.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status as http_status

from apps.accounts.models import InstitutionMembership, Role, RoleAssignment

from .models import AcademicUnit, AcademicYear, Campus, Class, School, Section, Term

from apps.students.models import Enrollment, Student, Guardian


def _make_school(name, code):
    return School.objects.create(name=name, code=code)


def _make_admin(school, username=None, password="TestPass123!"):
    username = username or f"admin-{school.code}"
    user = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@test.edu",
        password=password,
    )
    membership = InstitutionMembership.objects.create(
        user=user,
        institution=school,
    )
    RoleAssignment.objects.create(membership=membership, role=Role.ADMIN)
    return user, password


class AcademicYearTermWorkflowApiTests(TestCase):
    """Academic-year / term status actions stay in-tenant and roll correctly."""

    def setUp(self):
        self.school_a = _make_school("Workflow A", "wf-a")
        self.school_b = _make_school("Workflow B", "wf-b")
        user_a, password_a = _make_admin(self.school_a, username="wf-admin-a")
        self.client_a = self._login(user_a, password_a)
        user_b, password_b = _make_admin(self.school_b, username="wf-admin-b")
        self.client_b = self._login(user_b, password_b)

        self.year_a1 = AcademicYear.objects.create(
            school=self.school_a,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
            status="active",
        )
        self.year_a2 = AcademicYear.objects.create(
            school=self.school_a,
            name="2027-2028",
            start_date=date(2027, 8, 1),
            end_date=date(2028, 7, 31),
            status="upcoming",
        )
        self.year_b = AcademicYear.objects.create(
            school=self.school_b,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
            status="active",
        )

        self.term_a1 = Term.objects.create(
            academic_year=self.year_a1,
            name="Term 1",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 20),
            status="active",
        )
        self.term_a2 = Term.objects.create(
            academic_year=self.year_a1,
            name="Term 2",
            start_date=date(2027, 1, 10),
            end_date=date(2027, 4, 30),
            status="upcoming",
        )
        self.term_b = Term.objects.create(
            academic_year=self.year_b,
            name="Term B",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 20),
            status="active",
        )

    def _login(self, user, password):
        from rest_framework.test import APIClient
        client = APIClient()
        client.login(username=user.username, password=password)
        return client

    def test_activate_year_completes_other_active_years_in_tenant(self):
        response = self.client_a.post(
            f"/api/schools/academic-years/{self.year_a2.pk}/activate/"
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.year_a1.refresh_from_db()
        self.year_a2.refresh_from_db()
        self.assertEqual(self.year_a1.status, "completed")
        self.assertEqual(self.year_a2.status, "active")
        # The other school's active year is untouched.
        self.year_b.refresh_from_db()
        self.assertEqual(self.year_b.status, "active")

    def test_complete_year(self):
        response = self.client_a.post(
            f"/api/schools/academic-years/{self.year_a1.pk}/complete/"
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.year_a1.refresh_from_db()
        self.assertEqual(self.year_a1.status, "completed")

    def test_create_year_rejects_reversed_date_range(self):
        response = self.client_a.post(
            "/api/schools/academic-years/",
            {
                "name": "Invalid Range",
                "start_date": "2027-06-30",
                "end_date": "2026-10-01",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn("end_date", response.data)

    def test_update_year_rejects_reversed_date_range(self):
        response = self.client_a.patch(
            f"/api/schools/academic-years/{self.year_a1.pk}/",
            {"end_date": "2026-07-31"},
            format="json",
        )

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn("end_date", response.data)

    def test_mark_upcoming_year(self):
        response = self.client_a.post(
            f"/api/schools/academic-years/{self.year_a1.pk}/mark-upcoming/"
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.year_a1.refresh_from_db()
        self.assertEqual(self.year_a1.status, "upcoming")

    def test_invalid_action_rejected(self):
        response = self.client_a.post(
            f"/api/schools/academic-years/{self.year_a1.pk}/explode/"
        )

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_cannot_act_on_another_schools_year(self):
        response = self.client_a.post(
            f"/api/schools/academic-years/{self.year_b.pk}/activate/"
        )

        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_activate_term_completes_sibling_terms(self):
        response = self.client_a.post(
            f"/api/schools/terms/{self.term_a2.pk}/activate/"
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.term_a1.refresh_from_db()
        self.term_a2.refresh_from_db()
        self.assertEqual(self.term_a1.status, "completed")
        self.assertEqual(self.term_a2.status, "active")

    def test_terminate_term(self):
        response = self.client_a.post(
            f"/api/schools/terms/{self.term_a1.pk}/complete/"
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.term_a1.refresh_from_db()
        self.assertEqual(self.term_a1.status, "completed")

    def test_cannot_act_on_another_schools_term(self):
        response = self.client_a.post(
            f"/api/schools/terms/{self.term_b.pk}/activate/"
        )

        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)


class ClassHeadcountApiTests(TestCase):
    """Class/section listings expose accurate, campus-scoped headcounts."""

    def setUp(self):
        self.school = _make_school("Headcount", "hc")
        _, password = _make_admin(self.school, username="hc-admin")
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.client.login(username="hc-admin", password=password)

        self.campus = Campus.objects.create(school=self.school, name="Main")
        self.unit = AcademicUnit.objects.create(campus=self.campus, name="Primary")
        self.class_obj = Class.objects.create(unit=self.unit, name="Grade 1")
        self.section_a = Section.objects.create(class_obj=self.class_obj, name="A")
        self.section_b = Section.objects.create(class_obj=self.class_obj, name="B")
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )

    def _make_student(self, name, section, status="active"):
        guardian = Guardian.objects.create(
            institution=self.school,
            name=f"Guardian {name}",
            phone="0700000000",
            relationship="Parent",
        )
        student = Student.objects.create(
            institution=self.school,
            admission_number=f"ADM-{name.upper()}",
            first_name=name,
            last_name="Student",
            gender="male",
            guardian=guardian,
            phone="0700000001",
        )
        Enrollment.objects.create(
            student=student,
            academic_year=self.year,
            campus=self.campus,
            class_obj=self.class_obj,
            section=section,
            status=status,
        )
        return student

    def test_class_list_reports_student_and_section_counts(self):
        self._make_student("Amy", self.section_a)
        self._make_student("Ben", self.section_a)
        self._make_student("Cid", self.section_b)
        # Inactive enrollment must not inflate headcount.
        self._make_student("Dax", self.section_b, status="withdrawn")

        response = self.client.get("/api/schools/classes/")

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        row = next(r for r in response.data if r["name"] == "Grade 1")
        self.assertEqual(row["section_count"], 2)
        self.assertEqual(row["student_count"], 3)

    def test_section_detail_reports_student_count(self):
        self._make_student("Amy", self.section_a)
        response = self.client.get(f"/api/schools/sections/{self.section_a.pk}/")

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data["student_count"], 1)
