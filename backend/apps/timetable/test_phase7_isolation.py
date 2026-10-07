"""Timetable Phase 7 isolation + conflict rejection tests."""

from datetime import date, time

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role
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
from apps.students.models import Enrollment, Student
from apps.teachers.models import Teacher
from apps.timetable.models import Period, TimetableEntry

from apps.accounts.test_access import make_user


def _make_campus_admin(username, campus, employee_number):
    user = make_user(username, Role.CAMPUS_ADMIN, campus.school, campus=campus)
    from apps.accounts.models import StaffProfile
    StaffProfile.objects.create(
        user=user,
        employee_number=employee_number,
        first_name="Campus",
        last_name="Admin",
        gender="male",
        primary_campus=campus,
    )
    return user


class TimetablePhase7Base(TestCase):
    """Two-campus school fixture for timetable isolation tests."""

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

        self.subject_math = Subject.objects.create(
            institution=self.school,
            name="Mathematics", code="MATH-1A"
        )
        self.subject_eng = Subject.objects.create(
            institution=self.school,
            name="English", code="ENG-1A"
        )

        SubjectOffering.objects.create(
            institution=self.school,
            campus=self.campus_a,
            academic_year=self.year,
            subject=self.subject_math, class_obj=self.class_a
        )
        SubjectOffering.objects.create(
            institution=self.school,
            campus=self.campus_a,
            academic_year=self.year,
            subject=self.subject_eng, class_obj=self.class_a
        )
        SubjectOffering.objects.create(
            institution=self.school,
            campus=self.campus_b,
            academic_year=self.year,
            subject=self.subject_math, class_obj=self.class_b
        )
        SubjectOffering.objects.create(
            institution=self.school,
            campus=self.campus_b,
            academic_year=self.year,
            subject=self.subject_eng, class_obj=self.class_b
        )

        # Periods
        self.period_1 = Period.objects.create(
            institution=self.school,
            number=1,
            name="Period 1",
            start_time=time(8, 0),
            end_time=time(8, 45),
            is_break=False,
        )
        self.period_2 = Period.objects.create(
            institution=self.school,
            number=2,
            name="Period 2",
            start_time=time(8, 45),
            end_time=time(9, 30),
            is_break=False,
        )
        # Platform-wide period (no institution)
        self.period_global = Period.objects.create(
            institution=None,
            number=99,
            name="Global Period",
            start_time=time(10, 0),
            end_time=time(10, 45),
            is_break=True,
        )

        # Teachers
        self.teacher_a = Teacher.objects.create(
            institution=self.school,
            employee_number="TCH-A-001",
            first_name="Anna",
            last_name="Teacher",
            gender="female",
            primary_campus=self.campus_a,
        )
        self.teacher_b = Teacher.objects.create(
            institution=self.school,
            employee_number="TCH-B-001",
            first_name="Bob",
            last_name="Teacher",
            gender="male",
            primary_campus=self.campus_b,
        )

        # Timetable entries
        self.entry_a = TimetableEntry.objects.create(
            academic_year=self.year,
            campus=self.campus_a,
            class_obj=self.class_a,
            section=self.section_a,
            subject=self.subject_math,
            teacher=self.teacher_a,
            period=self.period_1,
            day="monday",
        )
        self.entry_b = TimetableEntry.objects.create(
            academic_year=self.year,
            campus=self.campus_b,
            class_obj=self.class_b,
            section=self.section_b,
            subject=self.subject_math,
            teacher=self.teacher_b,
            period=self.period_1,
            day="monday",
        )

        self.super_admin = make_user(
            "sadmin", Role.SUPER_ADMIN, self.school
        )
        self.campus_admin = _make_campus_admin(
            "cadmin-a", self.campus_a, "STF-A-001"
        )

        self.client = APIClient()

    def _as(self, user):
        self.client.force_authenticate(user=None)
        self.assertTrue(
            self.client.login(
                username=user.username,
                password=self.PASSWORD,
            ), f"login failed for {user.username}"
        )
        self.client.force_authenticate(user=user)
        return self.client

    def _body(self, response):
        data = response.json()
        if isinstance(data, list):
            return data
        return data.get("results", data)


class TimetablePeriodIsolationTests(TimetablePhase7Base):
    def test_campus_admin_sees_own_institution_periods_and_global(self):
        """Campus admin sees school periods + global periods (institution null)."""
        response = self._as(self.campus_admin).get("/api/timetable/periods/")
        self.assertEqual(response.status_code, 200)
        periods = response.json()
        numbers = [p["number"] for p in periods]
        self.assertIn(1, numbers)  # school period
        self.assertIn(99, numbers)  # global period

    def test_campus_admin_does_not_see_other_school_periods(self):
        """Periods from other school are not visible."""
        # Create period for other school
        Period.objects.create(
            institution=self.other_school,
            number=3,
            name="Other School Period",
            start_time=time(8, 0),
            end_time=time(8, 45),
        )
        response = self._as(self.campus_admin).get("/api/timetable/periods/")
        self.assertEqual(response.status_code, 200)
        periods = response.json()
        names = [p["name"] for p in periods]
        self.assertNotIn("Other School Period", names)


class TimetableEntryIsolationTests(TimetablePhase7Base):
    def test_campus_admin_sees_only_own_campus_entries(self):
        response = self._as(self.campus_admin).get("/api/timetable/entries/")
        self.assertEqual(response.status_code, 200)
        entries = self._body(response)
        campus_ids = {e["campus"] for e in entries}
        self.assertEqual(campus_ids, {self.campus_a.id})

    def test_super_admin_sees_all_campus_entries(self):
        response = self._as(self.super_admin).get("/api/timetable/entries/")
        self.assertEqual(response.status_code, 200)
        entries = self._body(response)
        campus_ids = {e["campus"] for e in entries}
        self.assertEqual(campus_ids, {self.campus_a.id, self.campus_b.id})


class TimetableConflictsIsolationTests(TimetablePhase7Base):
    def test_conflicts_year_other_school_returns_404(self):
        """Academic year from other school is not accessible."""
        other_year = AcademicYear.objects.create(
            school=self.other_school,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )
        response = self._as(self.campus_admin).get(
            f"/api/timetable/conflicts/?year={other_year.pk}"
        )
        self.assertEqual(response.status_code, 404)

    def test_conflicts_campus_other_campus_denied(self):
        """Campus admin cannot query conflicts for other campus."""
        response = self._as(self.campus_admin).get(
            f"/api/timetable/conflicts/?year={self.year.pk}&campus={self.campus_b.pk}"
        )
        self.assertEqual(response.status_code, 403)

    def test_conflicts_campus_a_returns_only_campus_a_conflicts(self):
        response = self._as(self.campus_admin).get(
            f"/api/timetable/conflicts/?year={self.year.pk}&campus={self.campus_a.pk}"
        )
        self.assertEqual(response.status_code, 200)
        conflicts = response.json()["conflicts"]
        campus_ids = {c["campus_id"] for c in conflicts}
        self.assertTrue(all(cid == self.campus_a.id for cid in campus_ids))

    def test_super_admin_sees_all_conflicts(self):
        """Super admin can query conflicts endpoint without campus filter."""
        response = self._as(self.super_admin).get(
            f"/api/timetable/conflicts/?year={self.year.pk}"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("conflicts", data)
        # With no actual conflicts, list is empty but accessible
        self.assertIsInstance(data["conflicts"], list)

    def test_conflict_record_includes_campus_id(self):
        response = self._as(self.campus_admin).get(
            f"/api/timetable/conflicts/?year={self.year.pk}&campus={self.campus_a.pk}"
        )
        self.assertEqual(response.status_code, 200)
        conflicts = response.json()["conflicts"]
        self.assertTrue(all("campus_id" in c for c in conflicts))


class TimetableConflictRejectionTests(TimetablePhase7Base):
    """Model-level conflict rejection via full_clean on save."""

    def test_teacher_double_booking_rejected(self):
        """Same teacher, same period, same day on another class -> ValidationError."""
        with self.assertRaises(ValidationError):
            TimetableEntry(
                academic_year=self.year,
                campus=self.campus_a,
                class_obj=self.class_a,
                section=self.section_a,
                subject=self.subject_eng,
                teacher=self.teacher_a,  # same teacher
                period=self.period_1,    # same period
                day="monday",           # same day
            ).full_clean()

    def test_section_double_booking_rejected(self):
        """Same section, same period, same day -> ValidationError."""
        with self.assertRaises(ValidationError):
            TimetableEntry(
                academic_year=self.year,
                campus=self.campus_a,
                class_obj=self.class_a,
                section=self.section_a,  # same section
                subject=self.subject_eng,
                teacher=self.teacher_b,
                period=self.period_1,    # same period
                day="monday",
            ).full_clean()

    def test_room_double_booking_not_enforced_at_model(self):
        """Room conflict not in model clean (no room field). Placeholder."""
        pass

    def test_break_period_rejected(self):
        """Entry with break period type rejected."""
        with self.assertRaises(ValidationError):
            TimetableEntry(
                academic_year=self.year,
                campus=self.campus_a,
                class_obj=self.class_a,
                section=self.section_a,
                subject=self.subject_math,
                teacher=self.teacher_a,
                period=self.period_global,  # break period
                day="monday",
            ).full_clean()

    def test_same_teacher_section_period_unique_constraint(self):
        """Model clean catches teacher+period+day double-booking."""
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            TimetableEntry.objects.create(
                academic_year=self.year,
                campus=self.campus_a,
                class_obj=self.class_a,
                section=self.section_a,
                subject=self.subject_eng,
                teacher=self.teacher_a,
                period=self.period_1,
                day="monday",
            )

    def test_same_section_period_day_unique_constraint(self):
        """Model clean catches section+period+day double-booking."""
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            TimetableEntry.objects.create(
                academic_year=self.year,
                campus=self.campus_a,
                class_obj=self.class_a,
                section=self.section_a,
                subject=self.subject_eng,
                teacher=self.teacher_b,
                period=self.period_1,
                day="monday",
            )
