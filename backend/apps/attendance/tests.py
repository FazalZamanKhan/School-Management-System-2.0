from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import InstitutionMembership, Role, RoleAssignment
from apps.schools.models import AcademicUnit, AcademicYear, Campus, Class, Section, School
from apps.students.models import Enrollment, Guardian, Student

from .models import Attendance


class AttendanceModelTests(TestCase):
	def setUp(self):
		self.school = School.objects.create(name="Test School")
		self.campus = Campus.objects.create(school=self.school, name="Main Campus")
		unit = AcademicUnit.objects.create(campus=self.campus, name="Primary")
		self.class_obj = Class.objects.create(unit=unit, name="Grade 1")
		self.section = Section.objects.create(class_obj=self.class_obj, name="A")
		self.year = AcademicYear.objects.create(
			school=self.school,
			name="2026-2027",
			start_date=date(2026, 8, 1),
			end_date=date(2027, 7, 31),
		)
		guardian = Guardian.objects.create(
			name="Test Parent",
			relationship="Father",
			phone="03000000000",
		)
		self.student = Student.objects.create(
			admission_number="ADM-ATT-001",
			first_name="Ali",
			gender="male",
			guardian=guardian,
		)
		self.enrollment = Enrollment.objects.create(
			student=self.student,
			academic_year=self.year,
			campus=self.campus,
			class_obj=self.class_obj,
			section=self.section,
		)

	def test_attendance_rejects_student_mismatch(self):
		other_student = Student.objects.create(
			admission_number="ADM-ATT-002",
			first_name="Sara",
			gender="female",
			guardian=self.student.guardian,
		)
		attendance = Attendance(
			student=other_student,
			enrollment=self.enrollment,
			academic_year=self.year,
			campus=self.campus,
			class_obj=self.class_obj,
			section=self.section,
			date=date(2026, 9, 1),
		)

		with self.assertRaises(ValidationError):
			attendance.full_clean()

	def test_attendance_allows_one_record_per_student_per_day(self):
		attendance_data = {
			"student": self.student,
			"enrollment": self.enrollment,
			"academic_year": self.year,
			"campus": self.campus,
			"class_obj": self.class_obj,
			"section": self.section,
			"date": date(2026, 9, 1),
		}
		Attendance.objects.create(**attendance_data)

		with self.assertRaises(ValidationError):
			Attendance.objects.create(**attendance_data)


	def test_all_supported_statuses_are_valid(self):
		from apps.attendance.models import Attendance as A

		expected = {
			"present",
			"absent",
			"late",
			"leave",
			"excused",
			"half_day",
		}
		self.assertEqual(
			expected,
			{code for code, _label in A.STATUS_CHOICES},
		)
		for code in expected:
			Attendance(
				student=self.student,
				enrollment=self.enrollment,
				academic_year=self.year,
				campus=self.campus,
				class_obj=self.class_obj,
				section=self.section,
				date=date(2026, 9, 1),
				status=code,
			).full_clean()

	def test_attendance_can_be_marked_excused_and_half_day(self):
		Attendance.objects.create(
			student=self.student,
			enrollment=self.enrollment,
			academic_year=self.year,
			campus=self.campus,
			class_obj=self.class_obj,
			section=self.section,
			date=date(2026, 9, 1),
			status="excused",
		).full_clean()

		# Duplicate (student, date) still blocked for the second status.
		with self.assertRaises(ValidationError):
			Attendance.objects.create(
				student=self.student,
				enrollment=self.enrollment,
				academic_year=self.year,
				campus=self.campus,
				class_obj=self.class_obj,
				section=self.section,
				date=date(2026, 9, 1),
				status="half_day",
			)

	def test_attendance_rejects_cross_campus_class(self):
		other_campus = Campus.objects.create(
			school=self.school,
			name="Second Campus",
		)
		other_unit = AcademicUnit.objects.create(
			campus=other_campus,
			name="Other Unit",
		)
		other_class = Class.objects.create(
			unit=other_unit,
			name="Grade 2",
		)
		other_section = Section.objects.create(
			class_obj=other_class,
			name="A",
		)

		attendance = Attendance(
			student=self.student,
			enrollment=self.enrollment,
			academic_year=self.year,
			campus=self.campus,
			class_obj=other_class,
			section=other_section,
			date=date(2026, 9, 2),
		)

		with self.assertRaises(ValidationError):
			attendance.full_clean()

	def test_attendance_rejects_invalid_enrollment_assignment(self):
		other_student = Student.objects.create(
			admission_number="ADM-ATT-003",
			first_name="Omar",
			gender="male",
			guardian=self.student.guardian,
		)
		attendance = Attendance(
			student=other_student,
			enrollment=self.enrollment,
			academic_year=self.year,
			campus=self.campus,
			class_obj=self.class_obj,
			section=self.section,
			date=date(2026, 9, 2),
		)

		with self.assertRaises(ValidationError):
			attendance.full_clean()


class AttendanceBulkMarkApiTests(TestCase):
	def setUp(self):
		self.school = School.objects.create(name="Bulk Attendance School")
		self.campus = Campus.objects.create(school=self.school, name="Main Campus")
		unit = AcademicUnit.objects.create(campus=self.campus, name="Primary")
		self.class_obj = Class.objects.create(unit=unit, name="Grade 1")
		self.section = Section.objects.create(class_obj=self.class_obj, name="A")
		self.year = AcademicYear.objects.create(
			school=self.school,
			name="2026-2027",
			start_date=date(2026, 1, 1),
			end_date=date(2027, 12, 31),
		)
		guardian = Guardian.objects.create(
			name="Test Parent",
			relationship="Parent",
			phone="03000000000",
		)
		self.student = Student.objects.create(
			institution=self.school,
			admission_number="ADM-BULK-001",
			first_name="Test",
			gender="male",
			guardian=guardian,
		)
		self.enrollment = Enrollment.objects.create(
			student=self.student,
			academic_year=self.year,
			campus=self.campus,
			class_obj=self.class_obj,
			section=self.section,
		)
		user = get_user_model().objects.create_user(
			username="attendance-admin",
			email="attendance-admin@test.edu",
			password="TestPass123!",
		)
		membership = InstitutionMembership.objects.create(
			user=user,
			institution=self.school,
		)
		RoleAssignment.objects.create(membership=membership, role=Role.ADMIN)
		self.client = APIClient()
		self.client.force_authenticate(user=user)

	def test_bulk_mark_accepts_iso_date_string(self):
		response = self.client.post(
			"/api/attendance/bulk/",
			{
				"academic_year": self.year.pk,
				"campus": self.campus.pk,
				"class": self.class_obj.pk,
				"section": self.section.pk,
				"date": date.today().isoformat(),
				"records": [{"student": self.student.pk, "status": "present"}],
			},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["created"], 1)
		self.assertEqual(Attendance.objects.count(), 1)

	def test_bulk_mark_returns_validation_error_for_invalid_date(self):
		response = self.client.post(
			"/api/attendance/bulk/",
			{
				"academic_year": self.year.pk,
				"campus": self.campus.pk,
				"class": self.class_obj.pk,
				"section": self.section.pk,
				"date": "not-a-date",
				"records": [{"student": self.student.pk, "status": "present"}],
			},
			format="json",
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn("date", response.data)

class AttendanceCorrectionModelTests(TestCase):
	def setUp(self):
		from apps.attendance.models import Attendance as A

		self.school = School.objects.create(name="Test School")
		self.campus = Campus.objects.create(school=self.school, name="Main Campus")
		unit = AcademicUnit.objects.create(campus=self.campus, name="Primary")
		self.class_obj = Class.objects.create(unit=unit, name="Grade 1")
		self.section = Section.objects.create(class_obj=self.class_obj, name="A")
		self.year = AcademicYear.objects.create(
			school=self.school,
			name="2026-2027",
			start_date=date(2026, 8, 1),
			end_date=date(2027, 7, 31),
		)
		guardian = Guardian.objects.create(
			name="Test Parent",
			relationship="Father",
			phone="03000000000",
		)
		self.student = Student.objects.create(
			admission_number="ADM-ATT-100",
			first_name="Ali",
			gender="male",
			guardian=guardian,
		)
		self.enrollment = Enrollment.objects.create(
			student=self.student,
			academic_year=self.year,
			campus=self.campus,
			class_obj=self.class_obj,
			section=self.section,
		)
		self.attendance = Attendance.objects.create(
			student=self.student,
			enrollment=self.enrollment,
			academic_year=self.year,
			campus=self.campus,
			class_obj=self.class_obj,
			section=self.section,
			date=date(2026, 9, 1),
			status="absent",
		)

	def test_correction_preserves_before_and_after_status(self):
		from apps.attendance.models import AttendanceCorrection

		correction = AttendanceCorrection.objects.create(
			attendance=self.attendance,
			student=self.student,
			from_status="absent",
			to_status="excused",
			reason="Doctor's note",
		)

		self.assertEqual(correction.from_status, "absent")
		self.assertEqual(correction.to_status, "excused")
		self.assertEqual(correction.attendance.pk, self.attendance.pk)
		self.assertIsNotNone(correction.corrected_at)

	def test_multiple_corrections_kept_as_history(self):
		from apps.attendance.models import AttendanceCorrection

		AttendanceCorrection.objects.create(
			attendance=self.attendance,
			student=self.student,
			from_status="absent",
			to_status="excused",
		)
		AttendanceCorrection.objects.create(
			attendance=self.attendance,
			student=self.student,
			from_status="excused",
			to_status="present",
		)

		self.assertEqual(self.attendance.corrections.count(), 2)
