"""Regression tests for exams cross-school isolation and known marks.

Known-marks contract: 80 + 70 + 90 = 240. Each subject out of 100 with
the canonical A/B/C/F scale (A: 80-100, B: 60-80, C: 40-60, F: 0-40).

Covers:
  - MarksService.overall totals, percentage, grade, pass/fail
  - ReportCard.total_marks aggregation
  - API create + read round trip for a subject result (percentage/grade)
  - cross-school isolation for exam subjects, results, practical marks and
    grade amendments (list/detail/create/approve/reject)
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import (
    InstitutionMembership,
    Role,
    RoleAssignment,
    StaffProfile,
    User,
)
from apps.exams.models import (
    Exam,
    ExamSubject,
    GradeAmendment,
    PracticalResult,
    StudentResult,
)
from apps.exams.services import MarksService
from apps.reportcards.models import GradeBand, GradeScale, ReportCard
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
from apps.teachers.models import Teacher, TeacherAssignment


class ExamIsolationBase(TestCase):
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

        # Subjects + offerings for School A
        self.subject_math = Subject.objects.create(
            name="Mathematics", code="MATH", institution=self.school_a
        )
        self.subject_eng = Subject.objects.create(
            name="English", code="ENG", institution=self.school_a
        )
        self.subject_sci = Subject.objects.create(
            name="Science", code="SCI", institution=self.school_a
        )
        for subj in (self.subject_math, self.subject_eng, self.subject_sci):
            SubjectOffering.objects.create(
                subject=subj,
                class_obj=self.class_a,
                academic_year=self.year_a,
            )

        self.subject_b = Subject.objects.create(
            name="Mathematics", code="MATH-B", institution=self.school_b
        )
        SubjectOffering.objects.create(
            subject=self.subject_b,
            class_obj=self.class_b,
            academic_year=self.year_b,
        )
        self.subject_b2 = Subject.objects.create(
            name="English", code="ENG-B", institution=self.school_b
        )
        SubjectOffering.objects.create(
            subject=self.subject_b2,
            class_obj=self.class_b,
            academic_year=self.year_b,
        )

        # Exams
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

        self.es_math = self._exam_subject(self.exam_a, self.subject_math)
        self.es_eng = self._exam_subject(self.exam_a, self.subject_eng)
        self.es_sci = self._exam_subject(self.exam_a, self.subject_sci)
        self.es_b = self._exam_subject(self.exam_b, self.subject_b)
        self.es_b2 = self._exam_subject(self.exam_b, self.subject_b2)

        # Students
        self.guardian_a = Guardian.objects.create(
            name="Parent A", relationship="Father", phone="03000000000"
        )
        self.student_a = Student.objects.create(
            admission_number="ST-A-001",
            first_name="Ali",
            gender="male",
            guardian=self.guardian_a,
        )
        Enrollment.objects.create(
            student=self.student_a,
            class_obj=self.class_a,
            section=self.section_a,
            academic_year=self.year_a,
            campus=self.campus_a,
        )

        self.guardian_b = Guardian.objects.create(
            name="Parent B", relationship="Mother", phone="03000000001"
        )
        self.student_b = Student.objects.create(
            admission_number="ST-B-001",
            first_name="Bilal",
            gender="male",
            guardian=self.guardian_b,
        )
        Enrollment.objects.create(
            student=self.student_b,
            class_obj=self.class_b,
            section=self.section_b,
            academic_year=self.year_b,
            campus=self.campus_b,
        )

        # Users / managers
        self.principal_a = self._principal_user_a()
        self.principal_b = self._principal_user_b()

        self.result_a = StudentResult.objects.create(
            exam=self.exam_a,
            student=self.student_a,
            exam_subject=self.es_math,
            obtained_marks=Decimal("80.00"),
        )
        self.result_b = StudentResult.objects.create(
            exam=self.exam_b,
            student=self.student_b,
            exam_subject=self.es_b,
            obtained_marks=Decimal("60.00"),
        )
        self.practical_a = PracticalResult.objects.create(
            exam=self.exam_a,
            student=self.student_a,
            exam_subject=self.es_math,
            obtained_marks=Decimal("40.00"),
        )
        self.practical_b = PracticalResult.objects.create(
            exam=self.exam_b,
            student=self.student_b,
            exam_subject=self.es_b,
            obtained_marks=Decimal("40.00"),
        )
        self.amendment_a = GradeAmendment.objects.create(
            student_result=self.result_a,
            requested_by=self.principal_a,
            original_grade=self.result_a.grade,
            original_marks=self.result_a.obtained_marks,
            original_is_pass=self.result_a.is_pass,
            requested_grade="A+",
            requested_marks=Decimal("85.00"),
            requested_is_pass=True,
            reason="Recheck found extra marks.",
        )
        self.amendment_b = GradeAmendment.objects.create(
            student_result=self.result_b,
            requested_by=self.principal_b,
            original_grade=self.result_b.grade,
            original_marks=self.result_b.obtained_marks,
            original_is_pass=self.result_b.is_pass,
            requested_grade="A",
            requested_marks=Decimal("75.00"),
            requested_is_pass=True,
            reason="Recheck.",
        )

        # Clients
        self.client_a = APIClient()
        self.client_a.force_login(self.principal_a)
        self.client_b = APIClient()
        self.client_b.force_login(self.principal_b)

        self.teacher_user = self._teacher_a_user()
        self.client_teacher_a = APIClient()
        self.client_teacher_a.force_login(self.teacher_user)

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

    def _exam_subject(self, exam, subject):
        return ExamSubject.objects.create(
            exam=exam,
            subject=subject,
            maximum_marks=100,
            passing_marks=40,
        )

    def _principal_user_a(self):
        return self._manager_user(
            "principal_lahore", self.school_a, self.campus_a, Role.PRINCIPAL
        )

    def _principal_user_b(self):
        return self._manager_user(
            "principal_sialkot", self.school_b, self.campus_b, Role.PRINCIPAL
        )

    def _manager_user(self, username, school, campus, role):
        user = User.objects.create_user(
            username=username, email=f"{username}@test.edu", password="pass"
        )
        membership = InstitutionMembership.objects.create(
            user=user, institution=school
        )
        RoleAssignment.objects.create(
            membership=membership,
            role=role,
            campus=campus if role in (Role.PRINCIPAL, Role.VICE_PRINCIPAL, Role.CAMPUS_ADMIN) else None,
        )
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
        teacher = Teacher.objects.create(
            institution=self.school_a,
            employee_number="TCH-A-001",
            user=user,
            membership=membership,
            primary_campus=self.campus_a,
            first_name="Samina",
            last_name="Ahmed",
            gender="female",
        )
        TeacherAssignment.objects.create(
            teacher=teacher,
            campus=self.campus_a,
            class_obj=self.class_a,
            section=self.section_a,
            subject=self.subject_math,
            academic_year=self.year_a,
            role="subject_teacher",
            status="active",
        )
        return user


class KnownMarksTests(ExamIsolationBase):
    """80 + 70 + 90 → 240 contract for totals, percentages, grades."""

    def setUp(self):
        super().setUp()
        GradeBand._band_cache = None
        self.scale = GradeScale.objects.create(
            institution=self.school_a,
            name="Deterministic (A-F)",
            is_default=True,
        )
        for letter, gpa, lo, hi in [
            ("A", "4.00", 80, 100),
            ("B", "3.00", 60, 80),
            ("C", "2.00", 40, 60),
            ("F", "0.00", 0, 40),
        ]:
            GradeBand.objects.create(
                scale=self.scale,
                letter_grade=letter,
                grade_point=gpa,
                minimum_percentage=lo,
                maximum_percentage=hi,
            )

    def _add_eng_sci(self):
        results = [self.result_a]
        for exam_subject, obtained in [
            (self.es_eng, 70),
            (self.es_sci, 90),
        ]:
            results.append(
                StudentResult.objects.create(
                    exam=self.exam_a,
                    student=self.student_a,
                    exam_subject=exam_subject,
                    obtained_marks=Decimal(str(obtained)),
                )
            )
        return results

    def test_marks_service_overall_totals(self):
        overall = MarksService(
            institution=self.school_a
        ).overall(self._add_eng_sci())

        self.assertEqual(overall["total_marks"], Decimal("240"))
        self.assertEqual(overall["maximum_marks"], Decimal("300"))
        self.assertEqual(overall["percentage"], Decimal("80.00"))
        self.assertEqual(overall["grade"], "A")
        self.assertTrue(overall["is_pass"])
        self.assertEqual(overall["overall_result"], "Pass")
        self.assertEqual(overall["subject_count"], 3)

    def test_report_card_total_marks(self):
        self._add_eng_sci()
        report_card = ReportCard.objects.create(
            student=self.student_a,
            exam=self.exam_a,
        )
        self.assertEqual(report_card.total_marks, Decimal("240.00"))

    def test_api_create_and_read_round_trip(self):
        resp = self.client_a.post(
            "/api/exams/results/",
            {
                "exam": self.exam_a.id,
                "student": self.student_a.id,
                "exam_subject": self.es_sci.id,
                "obtained_marks": "90.00",
                "is_absent": False,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        result = StudentResult.objects.get(
            exam_subject=self.es_sci,
            student=self.student_a,
        )
        resp = self.client_a.get(
            f"/api/exams/results/{result.pk}/"
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["obtained_marks"], "90.00")
        self.assertEqual(float(payload["percentage"]), 90.0)
        self.assertEqual(payload["grade"], "A")
        self.assertTrue(payload["is_pass"])


class CrossSchoolIsolationTests(ExamIsolationBase):
    """Principals of school A must never see or mutate school B exam data."""

    def test_exam_subject_list_is_scoped(self):
        resp = self.client_a.get("/api/exams/subjects/")
        ids = [row["id"] for row in resp.json()]
        self.assertIn(self.es_math.id, ids)
        self.assertNotIn(self.es_b.id, ids)

    def test_exam_subject_detail_is_scoped(self):
        resp = self.client_a.get(f"/api/exams/subjects/{self.es_b.id}/")
        self.assertEqual(resp.status_code, 404)
        resp = self.client_a.get(f"/api/exams/subjects/{self.es_math.id}/")
        self.assertEqual(resp.status_code, 200)

    def test_exam_subject_create_for_other_school_is_denied(self):
        subject_virgin = Subject.objects.create(
            name="Biology", code="BIO-B", institution=self.school_b
        )
        resp = self.client_a.post(
            "/api/exams/subjects/",
            {
                "exam": self.exam_b.id,
                "subject": subject_virgin.id,
                "maximum_marks": 100,
                "passing_marks": 40,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_result_list_is_scoped(self):
        resp = self.client_a.get("/api/exams/results/")
        ids = [row["id"] for row in resp.json()["results"]]
        self.assertIn(self.result_a.id, ids)
        self.assertNotIn(self.result_b.id, ids)

    def test_result_detail_is_scoped(self):
        resp = self.client_a.get(f"/api/exams/results/{self.result_b.id}/")
        self.assertEqual(resp.status_code, 404)
        resp = self.client_a.get(f"/api/exams/results/{self.result_a.id}/")
        self.assertEqual(resp.status_code, 200)

    def test_result_create_for_other_school_is_denied(self):
        resp = self.client_a.post(
            "/api/exams/results/",
            {
                "exam": self.exam_b.id,
                "student": self.student_b.id,
                "exam_subject": self.es_b2.id,
                "obtained_marks": "70.00",
                "is_absent": False,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_practical_list_is_scoped(self):
        resp = self.client_a.get("/api/exams/practical/")
        ids = [row["id"] for row in resp.json()["results"]]
        self.assertIn(self.practical_a.id, ids)
        self.assertNotIn(self.practical_b.id, ids)

    def test_practical_detail_is_scoped(self):
        resp = self.client_a.get(
            f"/api/exams/practical/{self.practical_b.id}/"
        )
        self.assertEqual(resp.status_code, 404)
        resp = self.client_a.get(
            f"/api/exams/practical/{self.practical_a.id}/"
        )
        self.assertEqual(resp.status_code, 200)

    def test_practical_create_for_other_school_is_denied(self):
        resp = self.client_a.post(
            "/api/exams/practical/",
            {
                "exam": self.exam_b.id,
                "student": self.student_b.id,
                "exam_subject": self.es_b2.id,
                "obtained_marks": "40.00",
                "is_absent": False,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_amendment_list_is_scoped(self):
        resp = self.client_a.get("/api/exams/amendments/")
        ids = [row["id"] for row in resp.json()["results"]]
        self.assertIn(self.amendment_a.id, ids)
        self.assertNotIn(self.amendment_b.id, ids)

    def test_amendment_create_for_other_school_is_denied(self):
        resp = self.client_a.post(
            "/api/exams/amendments/",
            {
                "student_result": self.result_b.id,
                "requested_grade": "A",
                "requested_marks": "75.00",
                "requested_is_pass": True,
                "reason": "Recheck.",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_amendment_approve_for_other_school_is_denied(self):
        resp = self.client_a.post(
            f"/api/exams/amendments/{self.amendment_b.id}/approve/"
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_amendment_reject_for_other_school_is_denied(self):
        resp = self.client_a.post(
            f"/api/exams/amendments/{self.amendment_b.id}/reject/",
            {"rejection_reason": "No"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_amendment_approve_own_school_updates_result(self):
        resp = self.client_a.post(
            f"/api/exams/amendments/{self.amendment_a.id}/approve/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.result_a.refresh_from_db()
        self.assertEqual(self.result_a.obtained_marks, Decimal("85.00"))
        self.assertEqual(self.result_a.grade, "A+")

    def test_teacher_sees_only_own_subject_amendments(self):
        resp = self.client_teacher_a.get("/api/exams/amendments/")
        ids = [row["id"] for row in resp.json()["results"]]
        self.assertIn(self.amendment_a.id, ids)
        self.assertNotIn(self.amendment_b.id, ids)
