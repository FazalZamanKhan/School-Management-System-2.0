"""Campus- and institution-isolation regression tests (PART 2 hardening).

These exercise the real API endpoints through the full middleware chain
(ActiveInstitution -> CampusAccess) and assert that a non-global manager
(CAMPUS_ADMIN at campus A) never sees records belonging to campus B, while a
GLOBAL (SUPER_ADMIN) user sees everything within the active institution.

Endpoints covered (all previously identified as leaky or hardened in PART 2):
  - /api/students/<pk>/              (detail gap fixed)
  - /api/students/                   (list)
  - /api/dashboard/overview|finance|exams
  - /api/documents/ + upload/
  - /api/search/?q=
  - /api/finance/categories/ + invoices/
  - /api/exams/results/
"""

from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import (
    InstitutionMembership,
    Role,
    RoleAssignment,
    StaffProfile,
)
from apps.exams.models import Exam, ExamSubject, StudentResult
from apps.finance.models import FeeCategory, Invoice
from apps.schools.models import (
    AcademicUnit,
    AcademicYear,
    Campus,
    Class,
    School,
    Section,
    Subject,
    SubjectOffering,
)
from apps.students.models import Enrollment, Guardian, Student, StudentDocument

from .test_access import make_user


def _make_campus_admin(username, campus, employee_number):
    """A CAMPUS_ADMIN manager whose staff profile pins them to one campus."""
    user = make_user(username, Role.CAMPUS_ADMIN, campus.school)
    membership = InstitutionMembership.objects.get(
        user=user, institution=campus.school
    )
    RoleAssignment.objects.create(
        membership=membership,
        role=Role.CAMPUS_ADMIN,
        campus=campus,
    )
    StaffProfile.objects.create(
        user=user,
        employee_number=employee_number,
        first_name="Campus",
        last_name="Admin",
        gender="male",
        primary_campus=campus,
    )
    return user


class CampusIsolationBase(TestCase):
    """Shared two-campus school fixture used by every isolation test."""

    PASSWORD = "TestPass123!"

    def setUp(self):
        self.school = School.objects.create(name="Northfield Academy")
        self.other_school = School.objects.create(name="Southfield Academy")

        self.campus_a = Campus.objects.create(
            school=self.school, name="Campus A"
        )
        self.campus_b = Campus.objects.create(
            school=self.school, name="Campus B"
        )

        self.unit_a = AcademicUnit.objects.create(
            campus=self.campus_a, name="Lower A"
        )
        self.unit_b = AcademicUnit.objects.create(
            campus=self.campus_b, name="Lower B"
        )

        self.class_a = Class.objects.create(unit=self.unit_a, name="Grade 1A")
        self.class_b = Class.objects.create(unit=self.unit_b, name="Grade 1B")

        self.section_a = Section.objects.create(
            class_obj=self.class_a, name="A"
        )
        self.section_b = Section.objects.create(
            class_obj=self.class_b, name="B"
        )

        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )

        self.super_admin = make_user(
            "sadmin", Role.SUPER_ADMIN, self.school
        )
        self.campus_admin = _make_campus_admin(
            "cadmin-a", self.campus_a, "STF-A-001"
        )

        self.guardian = Guardian.objects.create(
            name="Ada Parent", relationship="Mother", phone="555-4000"
        )

        self.student_a = self._make_student(
            "ADM-A-001", "Alan", "Kid", self.campus_a, self.section_a
        )
        self.student_b = self._make_student(
            "ADM-B-001", "Bella", "Kid", self.campus_b, self.section_b
        )

        self.client = APIClient()

    def _make_student(self, admission, first, last, campus, section):
        student = Student.objects.create(
            institution=self.school,
            admission_number=admission,
            first_name=first,
            last_name=last,
            gender="male",
            status="active",
            primary_campus=campus,
            guardian=self.guardian,
        )
        Enrollment.objects.create(
            student=student,
            academic_year=self.year,
            campus=campus,
            class_obj=section.class_obj,
            section=section,
            status="active",
        )
        return student

    def _make_exam(self, name, campus, class_obj):
        return Exam.objects.create(
            name=name,
            exam_type="midterm",
            academic_year=self.year,
            campus=campus,
            class_obj=class_obj,
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 20),
            status="completed",
        )

    def _as(self, user):
        """Authenticate through the Django-session + DRF double layer.

        The ActiveInstitutionMiddleware reads ``request.user`` as set by
        Django's AuthenticationMiddleware, so ``force_authenticate`` alone
        would leave ``request.institution`` unset. Logging the user into the
        session mirrors real production traffic while DRF auth still works.
        """
        self.client.force_authenticate(user=None)
        self.assertTrue(
            self.client.login(
                username=user.username,
                password=self.PASSWORD,
            ), f"login failed for {user.username}",
        )
        self.client.force_authenticate(user=user)
        return self.client

    def _body(self, response):
        data = response.json()
        if isinstance(data, list):
            return data
        return data.get("results", data)


# =============================================================================
# STUDENTS
# =============================================================================

class StudentIsolationTests(CampusIsolationBase):
    def test_campus_admin_can_read_own_campus_student(self):
        response = self._as(self.campus_admin).get(
            f"/api/students/{self.student_a.pk}/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Alan", response.json()["first_name"])

    def test_campus_admin_cannot_read_other_campus_student(self):
        response = self._as(self.campus_admin).get(
            f"/api/students/{self.student_b.pk}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_campus_admin_list_only_own_campus_students(self):
        response = self._as(self.campus_admin).get("/api/students/")
        self.assertEqual(response.status_code, 200)
        names = [
            item.get("full_name") or item.get("admission_number")
            for item in self._body(response)
        ]
        self.assertIn("Alan Kid", names)
        self.assertNotIn("Bella Kid", names)

    def test_super_admin_can_read_any_campus_student(self):
        response = self._as(self.super_admin).get(
            f"/api/students/{self.student_b.pk}/"
        )
        self.assertEqual(response.status_code, 200)


# =============================================================================
# DASHBOARD
# =============================================================================

class DashboardIsolationTests(CampusIsolationBase):
    def test_campus_admin_overview_scoped_to_campus(self):
        response = self._as(self.campus_admin).get("/api/dashboard/overview/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["students"]["total"], 1)
        self.assertEqual(data["campuses"], 1)
        self.assertEqual(data["classes"], 1)
        self.assertEqual(data["sections"], 1)
        self.assertEqual(data["enrollments"], 1)

    def test_super_admin_overview_sees_all_campuses(self):
        response = self._as(self.super_admin).get("/api/dashboard/overview/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["students"]["total"], 2)
        self.assertEqual(data["campuses"], 2)
        self.assertEqual(data["classes"], 2)
        self.assertEqual(data["sections"], 2)
        self.assertEqual(data["enrollments"], 2)

    def test_campus_admin_rejected_for_foreign_campus_param(self):
        response = self._as(self.campus_admin).get(
            f"/api/dashboard/overview/?campus={self.campus_b.pk}"
        )
        self.assertEqual(response.status_code, 403)

    def test_campus_admin_dashboard_exams_exclude_other_campus(self):
        self._make_exam("Midterm B", self.campus_b, self.class_b)

        response = self._as(self.campus_admin).get("/api/dashboard/exams/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["exams"], 0)

        response = self._as(self.super_admin).get("/api/dashboard/exams/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["exams"], 1)

    def test_campus_admin_dashboard_finance_is_callable(self):
        self._make_invoice(
            "INV-A-001", self.student_a, self.campus_a
        )
        self._make_invoice(
            "INV-B-001", self.student_b, self.campus_b
        )

        response = self._as(self.campus_admin).get(
            "/api/dashboard/finance/"
        )
        self.assertEqual(response.status_code, 200)

    def _make_invoice(self, number, student, campus):
        enrollment = student.enrollments.get(status="active")
        Invoice.objects.create(
            institution=self.school,
            invoice_number=number,
            student=student,
            enrollment=enrollment,
            academic_year=self.year,
            issue_date=date(2026, 8, 10),
            due_date=date(2026, 9, 10),
            status="issued",
        )


# =============================================================================
# DOCUMENTS
# =============================================================================

class DocumentIsolationTests(CampusIsolationBase):
    def _make_document(self, student, title):
        return StudentDocument.objects.create(
            institution=self.school,
            student=student,
            document_type="birth_certificate",
            title=title,
            file=SimpleUploadedFile("file.pdf", b"pdf-bytes"),
        )

    def test_campus_admin_lists_only_own_campus_documents(self):
        self._make_document(self.student_a, "Doc for Campus A")
        self._make_document(self.student_b, "Doc for Campus B")

        response = self._as(self.campus_admin).get("/api/documents/")
        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.json()]
        self.assertIn("Doc for Campus A", titles)
        self.assertNotIn("Doc for Campus B", titles)

    def test_campus_admin_cannot_upload_for_other_campus_student(self):
        response = self._as(self.campus_admin).post(
            "/api/documents/upload/",
            {
                "entity_type": "student",
                "entity_id": str(self.student_b.pk),
                "file": SimpleUploadedFile("x.pdf", b"x"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 404)

    def test_campus_admin_can_upload_for_own_campus_student(self):
        response = self._as(self.campus_admin).post(
            "/api/documents/upload/",
            {
                "entity_type": "student",
                "entity_id": str(self.student_a.pk),
                "file": SimpleUploadedFile("x.pdf", b"x"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)


# =============================================================================
# SEARCH
# =============================================================================

class SearchIsolationTests(CampusIsolationBase):
    def _make_staff(self, username, first, last, campus, employee_number):
        user = make_user(username, Role.STAFF, self.school)
        user.first_name = first
        user.last_name = last
        user.save()
        StaffProfile.objects.create(
            user=user,
            employee_number=employee_number,
            first_name=first,
            last_name=last,
            gender="female",
            primary_campus=campus,
        )
        return user

    def setUp(self):
        super().setUp()
        self._make_staff(
            "alpha", "Asha", "Kweli", self.campus_a, "STF-A-500"
        )
        self._make_staff(
            "beta", "Ben", "Kweli", self.campus_b, "STF-B-500"
        )

        self.subject_a = Subject.objects.create(
            institution=self.school, name="Algebra A", code="ALG-A"
        )
        self.subject_b = Subject.objects.create(
            institution=self.school, name="Algebra B", code="ALG-B"
        )
        SubjectOffering.objects.create(
            academic_year=self.year,
            class_obj=self.class_a,
            subject=self.subject_a,
        )
        SubjectOffering.objects.create(
            academic_year=self.year,
            class_obj=self.class_b,
            subject=self.subject_b,
        )

    def test_campus_admin_search_sees_only_own_campus_staff(self):
        response = self._as(self.campus_admin).get(
            "/api/search/?q=Kweli"
        )
        self.assertEqual(response.status_code, 200)
        names = [
            item["name"] for item in response.json()["results"]
            if item["type"] == "user"
        ]
        self.assertIn("Asha Kweli", names)
        self.assertNotIn("Ben Kweli", names)

    def test_super_admin_search_sees_all_campus_staff(self):
        response = self._as(self.super_admin).get(
            "/api/search/?q=Kweli"
        )
        self.assertEqual(response.status_code, 200)
        names = [
            item["name"] for item in response.json()["results"]
            if item["type"] == "user"
        ]
        self.assertIn("Asha Kweli", names)
        self.assertIn("Ben Kweli", names)

    def test_campus_admin_search_excludes_other_campus_subjects(self):
        response = self._as(self.campus_admin).get(
            "/api/search/?q=Algebra"
        )
        self.assertEqual(response.status_code, 200)
        subjects = [
            item["name"] for item in response.json()["results"]
            if item["type"] == "subject"
        ]
        self.assertEqual(subjects, ["Algebra A"])

    def test_super_admin_search_sees_all_subjects(self):
        response = self._as(self.super_admin).get(
            "/api/search/?q=Algebra"
        )
        self.assertEqual(response.status_code, 200)
        subjects = [
            item["name"] for item in response.json()["results"]
            if item["type"] == "subject"
        ]
        self.assertEqual(sorted(subjects), ["Algebra A", "Algebra B"])

    def test_campus_admin_search_excludes_other_campus_students(self):
        response = self._as(self.campus_admin).get("/api/search/?q=Kid")
        self.assertEqual(response.status_code, 200)
        names = [
            item["name"] for item in response.json()["results"]
            if item["type"] == "student"
        ]
        self.assertIn("Alan Kid", names)
        self.assertNotIn("Bella Kid", names)


# =============================================================================
# FINANCE
# =============================================================================

class FinanceIsolationTests(CampusIsolationBase):
    def setUp(self):
        super().setUp()
        self.category = FeeCategory.objects.create(
            name="Tuition", frequency="monthly", institution=self.school
        )
        self.foreign_category = FeeCategory.objects.create(
            name="Foreign Fee", frequency="monthly",
            institution=self.other_school,
        )
        self.invoice_a = self._make_invoice(
            "INV-A-100", self.student_a, self.campus_a
        )
        self.invoice_b = self._make_invoice(
            "INV-B-100", self.student_b, self.campus_b
        )

    def _make_invoice(self, number, student, campus):
        enrollment = student.enrollments.get(status="active")
        return Invoice.objects.create(
            institution=self.school,
            invoice_number=number,
            student=student,
            enrollment=enrollment,
            academic_year=self.year,
            issue_date=date(2026, 8, 10),
            due_date=date(2026, 9, 10),
            status="issued",
        )

    def test_campus_admin_sees_only_own_campus_invoices(self):
        response = self._as(self.campus_admin).get("/api/finance/invoices/")
        self.assertEqual(response.status_code, 200)
        numbers = [
            item["invoice_number"] for item in self._body(response)
        ]
        self.assertIn("INV-A-100", numbers)
        self.assertNotIn("INV-B-100", numbers)

    def test_super_admin_sees_all_invoices(self):
        response = self._as(self.super_admin).get("/api/finance/invoices/")
        self.assertEqual(response.status_code, 200)
        numbers = [
            item["invoice_number"] for item in self._body(response)
        ]
        self.assertIn("INV-A-100", numbers)
        self.assertIn("INV-B-100", numbers)

    def test_categories_scoped_to_active_institution(self):
        response = self._as(self.campus_admin).get("/api/finance/categories/")
        self.assertEqual(response.status_code, 200)
        names = [item["name"] for item in response.json()]
        self.assertIn("Tuition", names)
        self.assertNotIn("Foreign Fee", names)


# =============================================================================
# EXAMS / RESULTS
# =============================================================================

class ExamResultIsolationTests(CampusIsolationBase):
    def setUp(self):
        super().setUp()
        self.exam_b = self._make_exam(
            "Midterm B", self.campus_b, self.class_b
        )
        subject_b = Subject.objects.create(
            institution=self.school, name="Math B", code="MATH-B"
        )
        SubjectOffering.objects.create(
            subject=subject_b,
            class_obj=self.class_b,
            academic_year=self.year,
        )
        self.exam_subject_b = ExamSubject.objects.create(
            exam=self.exam_b,
            subject=subject_b,
            maximum_marks=100,
            passing_marks=40,
        )
        self.result_b = StudentResult.objects.create(
            exam=self.exam_b,
            student=self.student_b,
            exam_subject=self.exam_subject_b,
            obtained_marks=70,
        )

    def test_campus_admin_results_exclude_other_campus(self):
        response = self._as(self.campus_admin).get("/api/exams/results/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._body(response), [])

    def test_super_admin_sees_other_campus_results(self):
        response = self._as(self.super_admin).get("/api/exams/results/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self._body(response)), 1)