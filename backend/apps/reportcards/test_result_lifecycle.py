from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError as ModelValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.managers import (
    clear_current_institution,
    set_current_institution,
)
from apps.accounts.models import (
    InstitutionMembership,
    Role,
    RoleAssignment,
    StaffProfile,
)
from apps.exams.models import Exam, ExamSubject, PracticalResult, StudentResult
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
from apps.students.models import Enrollment, Guardian, Student

from .models import ReportCard


def make_student(school, year, campus, class_obj, section, admission):
    guardian = Guardian.objects.create(
        name="Parent",
        relationship="Father",
        phone="03000000000",
    )
    student = Student.objects.create(
        admission_number=admission,
        first_name="Ali",
        gender="male",
        guardian=guardian,
    )
    Enrollment.objects.create(
        student=student,
        academic_year=year,
        campus=campus,
        class_obj=class_obj,
        section=section,
    )
    return student


def make_report_card(school, admission):
    """Build a full report card fixture; returns identifiers/dict."""
    campus = Campus.objects.create(school=school, name="Main Campus")
    unit = AcademicUnit.objects.create(campus=campus, name="Primary")
    class_obj = Class.objects.create(unit=unit, name="Grade 1")
    section = Section.objects.create(class_obj=class_obj, name="A")
    year = AcademicYear.objects.create(
        school=school,
        name="2026-2027",
        start_date=date(2026, 8, 1),
        end_date=date(2027, 7, 31),
    )
    student = make_student(
        school, year, campus, class_obj, section, admission
    )
    exam = Exam.objects.create(
        name="Final",
        exam_type="final",
        academic_year=year,
        campus=campus,
        class_obj=class_obj,
        start_date=date(2027, 3, 1),
        end_date=date(2027, 3, 5),
    )
    subject = Subject.objects.create(
        name="English",
        code=f"ENG-{admission[-3:]}",
        institution=school,
    )
    SubjectOffering.objects.create(
        subject=subject,
        class_obj=class_obj,
        academic_year=year,
    )
    exam_subject = ExamSubject.objects.create(
        exam=exam,
        subject=subject,
        maximum_marks=100,
        passing_marks=40,
    )
    report_card = ReportCard.objects.create(
        student=student,
        exam=exam,
    )
    return {
        "campus": campus,
        "class_obj": class_obj,
        "section": section,
        "year": year,
        "student": student,
        "exam": exam,
        "exam_subject": exam_subject,
        "report_card": report_card,
    }


class ResultLifecycleModelTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Lifecycle School")
        self.fx = make_report_card(self.school, "ADM-LC-001")

    def test_full_lifecycle_transitions(self):
        card = self.fx["report_card"]

        self.assertEqual(card.status, "draft")
        self.assertTrue(card.can_edit)

        card.submit()
        self.assertEqual(card.status, "submitted")
        self.assertTrue(card.can_edit)

        card.approve()
        self.assertEqual(card.status, "approved")
        self.assertFalse(card.can_edit)

        card.publish()
        self.assertEqual(card.status, "published")
        self.assertFalse(card.can_edit)

        card.lock()
        self.assertEqual(card.status, "locked")
        self.assertFalse(card.can_edit)

        card.unlock()
        self.assertEqual(card.status, "draft")
        self.assertTrue(card.can_edit)

    def test_cannot_submit_an_approved_card(self):
        card = self.fx["report_card"]
        card.submit()
        card.approve()
        with self.assertRaises(ModelValidationError):
            card.submit()

    def test_cannot_unlock_a_submitted_card(self):
        card = self.fx["report_card"]
        card.submit()
        with self.assertRaises(ModelValidationError):
            card.unlock()

    def test_cannot_publish_a_locked_card(self):
        card = self.fx["report_card"]
        card.publish()
        card.lock()
        with self.assertRaises(ModelValidationError):
            card.publish()

    def test_can_edit_reflects_lifecycle(self):
        card = self.fx["report_card"]
        self.assertTrue(card.can_edit)      # draft

        card.submit()
        self.assertTrue(card.can_edit)      # submitted

        card.approve()
        self.assertFalse(card.can_edit)     # approved

        card.publish()
        self.assertFalse(card.can_edit)     # published

        card.lock()
        self.assertFalse(card.can_edit)     # locked


class ResultLockingModelTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Lock School")
        self.fx = make_report_card(self.school, "ADM-LK-001")

    def test_result_editable_in_draft(self):
        StudentResult.objects.create(
            exam=self.fx["exam"],
            student=self.fx["student"],
            exam_subject=self.fx["exam_subject"],
            obtained_marks=Decimal("75.00"),
        )
        PracticalResult.objects.create(
            exam=self.fx["exam"],
            student=self.fx["student"],
            exam_subject=self.fx["exam_subject"],
            obtained_marks=Decimal("20.00"),
            maximum_marks=50,
            passing_marks=20,
        )

    def test_locked_result_cannot_be_edited(self):
        card = self.fx["report_card"]
        card.publish()
        card.lock()

        with self.assertRaises(ModelValidationError):
            StudentResult.objects.create(
                exam=self.fx["exam"],
                student=self.fx["student"],
                exam_subject=self.fx["exam_subject"],
                obtained_marks=Decimal("75.00"),
            )

        with self.assertRaises(ModelValidationError):
            PracticalResult.objects.create(
                exam=self.fx["exam"],
                student=self.fx["student"],
                exam_subject=self.fx["exam_subject"],
                obtained_marks=Decimal("20.00"),
                maximum_marks=50,
                passing_marks=20,
            )

    def test_approved_result_cannot_be_edited_directly(self):
        card = self.fx["report_card"]
        card.submit()
        card.approve()

        with self.assertRaises(ModelValidationError):
            StudentResult.objects.create(
                exam=self.fx["exam"],
                student=self.fx["student"],
                exam_subject=self.fx["exam_subject"],
                obtained_marks=Decimal("75.00"),
            )


class ResultLifecycleApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.school = School.objects.create(name="API School")
        self.fx = make_report_card(self.school, "ADM-API-001")
        self.card = self.fx["report_card"]

        self.user = self._make_staff_user(
            "apiuser",
            Role.ACADEMIC,
            self.fx["campus"],
        )
        self.teacher = self._make_staff_user(
            "apiteacher",
            Role.TEACHER,
            self.fx["campus"],
        )

    def _make_staff_user(self, username, role, campus):
        from django.contrib.auth import get_user_model

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
            campus=campus if role in (Role.PRINCIPAL, Role.VICE_PRINCIPAL, Role.CAMPUS_ADMIN) else None,
        )
        StaffProfile.objects.create(
            user=user,
            membership=membership,
            institution=self.school,
            primary_campus=campus,
            employee_number=f"EMP-{username}",
            first_name="Test",
            last_name=username,
            gender="male",
        )
        return user

    def tearDown(self):
        clear_current_institution()

    def test_teacher_cannot_change_status(self):
        set_current_institution(self.school)
        self.client.force_authenticate(user=self.teacher)
        response = self.client.post(
            f"/api/report-cards/{self.card.pk}/status/",
            {"status": "approved"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_academic_admin_can_advance_lifecycle(self):
        set_current_institution(self.school)
        self.client.force_authenticate(user=self.user)

        for expected in ["submitted", "approved", "published", "locked"]:
            response = self.client.post(
                f"/api/report-cards/{self.card.pk}/status/",
                {"status": expected},
                format="json",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["status"], expected)

    def test_invalid_transition_returns_400(self):
        set_current_institution(self.school)
        self.client.force_authenticate(user=self.user)

        # Submitted card cannot be "unlocked" back to draft directly.
        first = self.client.post(
            f"/api/report-cards/{self.card.pk}/status/",
            {"status": "submitted"},
            format="json",
        )
        self.assertEqual(first.status_code, 200)

        response = self.client.post(
            f"/api/report-cards/{self.card.pk}/status/",
            {"status": "unlock"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class ResultLifecycleIsolationApiTests(TestCase):
    """Campus isolation (IDOR): a campus-scoped reviewer cannot touch
    report cards of another campus, even with valid credentials."""

    def setUp(self):
        self.client = APIClient()
        self.school_a = School.objects.create(name="School A")
        self.school_b = School.objects.create(name="School B")

        self.fx_a = make_report_card(self.school_a, "ADM-ISO-A")
        self.fx_b = make_report_card(self.school_b, "ADM-ISO-B")

        self.campus_admin_a = self._make_campus_admin(
            "campadmina",
            self.school_a,
            self.fx_a["campus"],
        )

    def _make_campus_admin(self, username, school, campus):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(
            username=username,
            email=f"{username}@test.edu",
            password="TestPass123!",
        )
        membership = InstitutionMembership.objects.create(
            user=user,
            institution=school,
        )
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.CAMPUS_ADMIN,
            campus=campus,
        )
        StaffProfile.objects.create(
            user=user,
            membership=membership,
            institution=school,
            primary_campus=campus,
            employee_number=f"EMP-{username}",
            first_name="Test",
            last_name=username,
            gender="male",
        )
        return user

    def tearDown(self):
        clear_current_institution()

    def test_campus_admin_cannot_advance_report_card_of_other_campus(self):
        set_current_institution(self.school_a)
        self.client.force_authenticate(user=self.campus_admin_a)

        # The card belongs to a different campus (school B); it must not leak.
        response = self.client.post(
            f"/api/report-cards/{self.fx_b['report_card'].pk}/status/",
            {"status": "published"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_campus_admin_can_advance_report_card_of_own_campus(self):
        set_current_institution(self.school_a)
        self.client.force_authenticate(user=self.campus_admin_a)

        response = self.client.post(
            f"/api/report-cards/{self.fx_a['report_card'].pk}/status/",
            {"status": "published"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
