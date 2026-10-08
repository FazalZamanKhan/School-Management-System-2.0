from datetime import date, time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import InstitutionMembership, Role, RoleAssignment
from apps.schools.models import AcademicUnit, AcademicYear, Campus, Class, Section, School, Subject, SubjectOffering
from apps.teachers.models import Teacher, TeacherAssignment

from .conflicts import find_conflicts
from .generator import generate_timetable
from .models import Period, TimetableEntry


class TimetableModelTests(TestCase):
	def setUp(self):
		school = School.objects.create(name="Test School")
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
		subject = Subject.objects.create(institution=school, name="English", code="ENG-TT")
		SubjectOffering.objects.create(
			subject=subject,
			class_obj=class_obj,
			academic_year=year,
		)
		teacher = Teacher.objects.create(
			employee_number="T-TT-001",
			first_name="Ayesha",
			last_name="Khan",
			gender="female",
			campus="Main Campus",
		)
		teacher2 = Teacher.objects.create(
			employee_number="T-TT-002",
			first_name="Bilal",
			last_name="Ahmed",
			gender="male",
			campus="Main Campus",
		)
		period = Period.objects.create(
			name="Period 1",
			number=1,
			start_time=time(8, 0),
			end_time=time(8, 45),
		)
		# Overlaps Period 1 in wall-clock time (8:30 is inside 08:00-08:45).
		period_overlap = Period.objects.create(
			name="Period 2",
			number=3,
			start_time=time(8, 30),
			end_time=time(9, 15),
		)
		# Back-to-back with Period 1: no overlap.
		period_later = Period.objects.create(
			name="Period 3",
			number=4,
			start_time=time(8, 45),
			end_time=time(9, 30),
		)
		self.school = school
		self.campus = campus
		self.unit = unit
		self.class_obj = class_obj
		self.section = section
		self.year = year
		self.subject = subject
		self.teacher = teacher
		self.teacher2 = teacher2
		self.period = period
		self.period_overlap = period_overlap
		self.period_later = period_later
		self.entry_data = {
			"academic_year": year,
			"campus": campus,
			"class_obj": class_obj,
			"section": section,
			"subject": subject,
			"teacher": teacher,
			"period": period,
			"day": "monday",
		}

	def _other_section(self):
		"""A second class + section on the same campus, with offerings."""
		other_class = Class.objects.create(
			unit=self.unit,
			name="Grade 2",
		)
		other_section = Section.objects.create(
			class_obj=other_class,
			name="A",
		)
		SubjectOffering.objects.create(
			subject=self.subject,
			class_obj=other_class,
			academic_year=self.year,
		)
		return other_section

	def _entry(self, **overrides):
		data = dict(self.entry_data)
		data.update(overrides)
		return data

	def test_timetable_rejects_break_period(self):
		self.entry_data["period"] = Period.objects.create(
			name="Break",
			number=2,
			start_time=time(8, 45),
			end_time=time(9, 0),
			is_break=True,
		)

		with self.assertRaises(ValidationError):
			TimetableEntry.objects.create(**self.entry_data)

	def test_timetable_rejects_duplicate_section_period(self):
		TimetableEntry.objects.create(**self.entry_data)

		with self.assertRaises(ValidationError):
			TimetableEntry.objects.create(**self.entry_data)

	def test_timetable_rejects_teacher_overlap(self):
		TimetableEntry.objects.create(**self.entry_data)

		other_section = self._other_section()

		with self.assertRaises(ValidationError):
			TimetableEntry.objects.create(
				**self._entry(
					section=other_section,
					period=self.period_overlap,
				)
			)

	def test_timetable_rejects_section_overlap(self):
		TimetableEntry.objects.create(**self.entry_data)

		with self.assertRaises(ValidationError):
			TimetableEntry.objects.create(
				**self._entry(
					teacher=self.teacher2,
					period=self.period_overlap,
				)
			)

	def test_timetable_rejects_room_conflict(self):
		TimetableEntry.objects.create(
			**self._entry(room="Lab 1")
		)

		other_section = self._other_section()

		with self.assertRaises(ValidationError):
			TimetableEntry.objects.create(
				**self._entry(
					section=other_section,
					teacher=self.teacher2,
					period=self.period_overlap,
					room="Lab 1",
				)
			)

	def test_back_to_back_periods_are_allowed(self):
		TimetableEntry.objects.create(**self.entry_data)

		entry = TimetableEntry.objects.create(
			**self._entry(period=self.period_later)
		)

		self.assertEqual(entry.period, self.period_later)

	def test_updating_to_overlapping_period_ignores_self(self):
		entry = TimetableEntry.objects.create(**self.entry_data)

		# Re-saving the very same row must not trip over itself.
		entry.period = self.period_later
		entry.save()

		entry.refresh_from_db()
		self.assertEqual(entry.period, self.period_later)

	def test_room_conflict_is_scoped_to_campus(self):
		TimetableEntry.objects.create(
			**self._entry(room="Library")
		)

		other_campus = Campus.objects.create(
			school=self.school,
			name="North Campus",
		)
		other_unit = AcademicUnit.objects.create(
			campus=other_campus,
			name="Secondary",
		)
		other_class = Class.objects.create(
			unit=other_unit,
			name="Grade 3",
		)
		other_section = Section.objects.create(
			class_obj=other_class,
			name="A",
		)
		SubjectOffering.objects.create(
			subject=self.subject,
			class_obj=other_class,
			academic_year=self.year,
		)
		other_teacher = Teacher.objects.create(
			employee_number="T-TT-003",
			first_name="Zara",
			last_name="Ali",
			gender="female",
			campus="North Campus",
		)

		entry = TimetableEntry.objects.create(
			**self._entry(
				campus=other_campus,
				class_obj=other_class,
				section=other_section,
				teacher=other_teacher,
				period=self.period_overlap,
				room="Library",
			)
		)

		self.assertEqual(entry.campus, other_campus)

	def test_conflict_scan_reports_overlaps(self):
		other_section = self._other_section()

		# Bypass validation on purpose: realistic damaged data.
		TimetableEntry.objects.bulk_create(
			[
				TimetableEntry(
					**self._entry(section=self.section, room="Lab 1")
				),
				TimetableEntry(
					**self._entry(
						section=other_section,
						period=self.period_overlap,
						room="Lab 1",
					)
				),
				TimetableEntry(
					**self._entry(
						teacher=self.teacher2,
						period=self.period_overlap,
						room="Room 2",
					)
				),
			]
		)

		conflicts = find_conflicts(academic_year=self.year)

		self.assertEqual(len(conflicts), 3)
		self.assertEqual(
			{item["type"] for item in conflicts},
			{"teacher", "section", "room"},
		)

		# Same scan restricted to the campus returns the same rows.
		self.assertEqual(
			len(find_conflicts(campus=self.campus)), 3
		)

		# A campus with nothing booked reports no conflicts.
		empty = Campus.objects.create(
			school=self.school,
			name="North Campus",
		)
		self.assertEqual(find_conflicts(campus=empty), [])

	def test_conflicts_api_reports_and_scopes(self):
		other_section = self._other_section()
		TimetableEntry.objects.bulk_create(
			[
				TimetableEntry(
					**self._entry(section=self.section, room="Lab 1")
				),
				TimetableEntry(
					**self._entry(
						section=other_section,
						period=self.period_overlap,
						room="Lab 1",
					)
				),
			]
		)

		user = get_user_model().objects.create_user(
			username="timetable-admin",
			email="timetable-admin@test.edu",
			password="TestPass123!",
		)
		membership = InstitutionMembership.objects.create(
			user=user,
			institution=self.school,
		)
		RoleAssignment.objects.create(
			membership=membership,
			role=Role.ADMIN,
		)

		client = APIClient()
		client.force_authenticate(user=user)

		response = client.get(
			reverse("timetable-conflicts"),
			{"campus": self.campus.pk},
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["count"], 2)
		types = {item["type"] for item in response.data["conflicts"]}
		self.assertEqual(types, {"teacher", "room"})

		# Out-of-scope / unknown campus is rejected.
		response = client.get(
			reverse("timetable-conflicts"),
			{"campus": 999999},
		)
		self.assertEqual(response.status_code, 404)

	def test_generator_avoids_overlapping_periods(self):
		TeacherAssignment.objects.create(
			teacher=self.teacher,
			campus=self.campus,
			class_obj=self.class_obj,
			section=self.section,
			subject=self.subject,
			academic_year=self.year,
			status="active",
		)

		result = generate_timetable(
			self.campus,
			self.year,
			lessons_per_subject=2,
			days=["monday"],
			seed=7,
		)

		# Period 1 and Period 2 overlap, so only one lesson per day fits.
		self.assertEqual(result["created"], 1)
		self.assertEqual(result["unplaced_count"], 1)
		self.assertEqual(TimetableEntry.objects.count(), 1)
		self.assertFalse(
			find_conflicts(academic_year=self.year)
		)

	def test_generate_api_rejects_lessons_outside_range(self):
		user = get_user_model().objects.create_user(
			username="timetable-generator",
			email="timetable-generator@test.edu",
			password="TestPass123!",
		)
		membership = InstitutionMembership.objects.create(
			user=user,
			institution=self.school,
		)
		RoleAssignment.objects.create(
			membership=membership,
			role=Role.ADMIN,
		)

		client = APIClient()
		client.force_login(user)
		response = client.post(
			reverse("timetable-generate"),
			{
				"campus": self.campus.pk,
				"lessons_per_subject": 21,
				"confirm": True,
			},
			format="json",
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn("lessons_per_subject", response.data)

	def test_generate_api_returns_actionable_error_for_missing_assignments(self):
		user = get_user_model().objects.create_user(
			username="timetable-generator-class",
			email="timetable-generator-class@test.edu",
			password="TestPass123!",
		)
		membership = InstitutionMembership.objects.create(
			user=user,
			institution=self.school,
		)
		RoleAssignment.objects.create(
			membership=membership,
			role=Role.ADMIN,
		)

		client = APIClient()
		client.force_login(user)
		response = client.post(
			reverse("timetable-generate"),
			{
				"campus": self.campus.pk,
				"class_id": self.class_obj.pk,
				"lessons_per_subject": 5,
				"confirm": True,
			},
			format="json",
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn("Assign teachers", response.data["detail"])
