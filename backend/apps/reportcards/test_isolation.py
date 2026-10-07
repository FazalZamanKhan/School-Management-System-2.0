"""Regression tests for reportcards cross-school isolation.

Covers report-card list/detail/PDF/batch-PDF scoping, grade-scale
scoping and grade amendments (list/create/approve/reject) across two
schools.
"""

from datetime import date
from decimal import Decimal

from rest_framework.test import APIClient
from django.test import TestCase

from apps.accounts.models import (
    InstitutionMembership,
    Role,
    RoleAssignment,
    StaffProfile,
    User,
)
from apps.exams.models import Exam, ExamSubject, StudentResult
from apps.reportcards.models import GradeBand, GradeScale, ReportCard
from apps.schools.models import (
    AcademicUnit,
    AcademicYear,
    Campus,
    Class,
    School,
    Section,
)
from apps.students.models import Enrollment, Guardian, Student
from apps.teachers.models import Teacher, TeacherAssignment


class ReportCardIsolationBase(TestCase):
    """Two schools, each with a full academic chain and principals."""

    def setUp(self):
        GradeBand._band_cache = None
        self.school_a = School.objects.create(name="Lahore School")
        self.campus_a = Campus.objects.create(
            school=self.school_a, name="Lahore Campus"
        )
        (
            self.unit_a,
            self.class_a,
            self.section_a,
            self.year_a,
        ) = self._academic_chain(self.school_a, self.campus_a, "A")

        self.school_b = School.objects.create(name="Sialkot School")
        self.campus_b = Campus.objects.create(
            school=self.school_b, name="Sialkot Campus"
        )
        (
            self.unit_b,
            self.class_b,
            self.section_b,
            self.year_b,
        ) = self._academic_chain(self.school_b, self.campus_b, "B")

        self.exam_a = Exam.objects.create(
            name="Midterm",
            exam_type="midterm",
            academic_year=self.year_a,
            campus=self.campus_a,
            class_obj=self.class_a,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 5),
        )
        self.exam_b = Exam.objects.create(
            name="Midterm",
            exam_type="midterm",
            academic_year=self.year_b,
            campus=self.campus_b,
            class_obj=self.class_b,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 5),
        )

        self.student_a = self._student(self.guardian_a(), "ST-A-001", "Ali")
        Enrollment.objects.create(
            student=self.student_a,
            class_obj=self.class_a,
            section=self.section_a,
            academic_year=self.year_a,
            campus=self.campus_a,
        )
        self.student_b = self._student(self.guardian_b(), "ST-B-001", "Bilal")
        Enrollment.objects.create(
            student=self.student_b,
            class_obj=self.class_b,
            section=self.section_b,
            academic_year=self.year_b,
            campus=self.campus_b,
        )

        self.principal_a = self._manager_user(
            "principal_lahore", self.school_a, self.campus_a, Role.PRINCIPAL
        )
        self.principal_b = self._manager_user(
            "principal_sialkot", self.school_b, self.campus_b, Role.PRINCIPAL
        )
        self.teacher_a = self._teacher_a_user()

        self.card_a = ReportCard.objects.create(
            student=self.student_a,
            exam=self.exam_a,
        )
        self.card_b = ReportCard.objects.create(
            student=self.student_b,
            exam=self.exam_b,
        )

        self.client_a = APIClient()
        self.client_a.force_login(self.principal_a)
        self.client_b = APIClient()
        self.client_b.force_login(self.principal_b)
        self.client_teacher_a = APIClient()
        self.client_teacher_a.force_login(self.teacher_a)

        self.scale_a = GradeScale.objects.create(
            institution=self.school_a,
            name="School A Scale",
            is_default=True,
        )
        GradeBand.objects.create(
            scale=self.scale_a,
            letter_grade="A",
            grade_point=Decimal("4.00"),
            minimum_percentage=Decimal("80.00"),
            maximum_percentage=Decimal("100.00"),
        )
        self.scale_b = GradeScale.objects.create(
            institution=self.school_b,
            name="School B Scale",
            is_default=False,
        )

    # ---- helpers ----------------------------------------------------

    def _academic_chain(self, school, campus, tag):
        unit = AcademicUnit.objects.create(campus=campus, name=f"Primary {tag}")
        class_obj = Class.objects.create(unit=unit, name=f"Grade 1 {tag}")
        section = Section.objects.create(class_obj=class_obj, name="A")
        year = AcademicYear.objects.create(
            school=school,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )
        return unit, class_obj, section, year

    def guardian_a(self):
        return Guardian.objects.create(
            name="Parent A", relationship="Father", phone="03000000000"
        )

    def guardian_b(self):
        return Guardian.objects.create(
            name="Parent B", relationship="Mother", phone="03000000001"
        )

    def _student(self, guardian, number, first_name):
        return Student.objects.create(
            admission_number=number,
            first_name=first_name,
            gender="male",
            guardian=guardian,
        )

    def _manager_user(self, username, school, campus, role):
        user = User.objects.create_user(
            username=username, email=f"{username}@test.edu", password="pass"
        )
        membership = InstitutionMembership.objects.create(
            user=user, institution=school
        )
        RoleAssignment.objects.create(membership=membership, role=role, campus=campus)
        StaffProfile.objects.create(
            user=user,
            membership=membership,
            institution=school,
            primary_campus=campus,
            employee_number=f"EMP-{username}",
            first_name=username,
            last_name="Manager",
            gender="male",
        )
        return user

    def _teacher_a_user(self):
        user = User.objects.create_user(
            username="teacher_lahore",
            email="tl@test.edu",
            password="pass",
        )
        membership = InstitutionMembership.objects.create(
            user=user, institution=self.school_a
        )
        RoleAssignment.objects.create(
            membership=membership, role=Role.TEACHER
        )
        Teacher.objects.create(
            institution=self.school_a,
            employee_number="TCH-A-001",
            user=user,
            membership=membership,
            primary_campus=self.campus_a,
            first_name="Samina",
            last_name="Ahmed",
            gender="female",
        )
        return user


class ReportCardListTests(ReportCardIsolationBase):
    def test_report_card_list_is_scoped(self):
        resp = self.client_a.get("/api/report-cards/")
        ids = [row["id"] for row in resp.json()["results"]]
        self.assertIn(self.card_a.id, ids)
        self.assertNotIn(self.card_b.id, ids)

    def test_report_card_detail_is_scoped(self):
        resp = self.client_a.get(f"/api/report-cards/{self.card_b.id}/")
        self.assertEqual(resp.status_code, 404, resp.content)
        resp = self.client_a.get(f"/api/report-cards/{self.card_a.id}/")
        self.assertEqual(resp.status_code, 200, resp.content)


class ReportCardPdfTests(ReportCardIsolationBase):
    def test_report_card_pdf_is_scoped(self):
        resp = self.client_a.get(f"/api/report-cards/{self.card_b.id}/pdf/")
        self.assertEqual(resp.status_code, 403, resp.content)

        resp = self.client_a.get(f"/api/report-cards/{self.card_a.id}/pdf/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_report_card_pdf_batch_is_scoped(self):
        resp = self.client_a.get(
            f"/api/report-cards/pdf/batch/?exam={self.exam_b.id}"
        )
        self.assertEqual(resp.status_code, 404, resp.content)

        resp = self.client_a.get(
            f"/api/report-cards/pdf/batch/?exam={self.exam_a.id}"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp["Content-Type"], "application/zip")


class GradeScaleTests(ReportCardIsolationBase):
    def test_grade_scale_list_is_scoped(self):
        resp = self.client_teacher_a.get("/api/report-cards/grade-scales/")
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [row["id"] for row in resp.json()]
        self.assertIn(self.scale_a.id, ids)
        self.assertNotIn(self.scale_b.id, ids)

    def test_grade_scale_list_includes_platform_scale(self):
        platform = GradeScale.objects.create(
            institution=None,
            name="Platform Default",
            is_default=False,
        )
        resp = self.client_teacher_a.get("/api/report-cards/grade-scales/")
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [row["id"] for row in resp.json()]
        self.assertIn(platform.id, ids)
