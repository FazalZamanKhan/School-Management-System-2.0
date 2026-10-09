from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import InstitutionMembership, Role, RoleAssignment

from .models import (
	AcademicUnit,
	AcademicYear,
	Campus,
	Class,
	School,
	SchoolSettings,
	Section,
	Subject,
	SubjectOffering,
)


class AcademicStructureModelTests(TestCase):
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
		self.subject = Subject.objects.create(
			institution=self.school,
			name="English",
			code="ENG-SCHOOL",
		)

	def test_section_names_are_unique_within_a_class(self):
		duplicate = Section(class_obj=self.class_obj, name="A")

		with self.assertRaises(ValidationError):
			duplicate.full_clean()

	def test_subject_offering_is_unique_for_class_and_year(self):
		SubjectOffering.objects.create(
			subject=self.subject,
			class_obj=self.class_obj,
			academic_year=self.year,
		)
		duplicate = SubjectOffering(
			subject=self.subject,
			class_obj=self.class_obj,
			academic_year=self.year,
		)

		with self.assertRaises(ValidationError):
			duplicate.full_clean()


class AcademicYearSingleActiveInvariantTests(TestCase):
	"""Regression: at most one AcademicYear may be 'active' per school.

	AcademicYearActionView already enforced this on the dedicated
	/activate/ action, but plain create/update could bypass it entirely
	(status defaults to "active" on the model, and neither
	AcademicYearListView.perform_create nor
	AcademicYearDetailView.perform_update deactivated any sibling year).
	"""

	def setUp(self):
		self.school = School.objects.create(name="Single Active School")
		self.user = get_user_model().objects.create_user(
			username="single-active-admin",
			email="single-active-admin@test.edu",
			password="TestPass123!",
		)
		membership = InstitutionMembership.objects.create(
			user=self.user,
			institution=self.school,
		)
		RoleAssignment.objects.create(membership=membership, role=Role.ADMIN)
		self.client = APIClient()
		self.client.login(username="single-active-admin", password="TestPass123!")

	def test_creating_a_second_active_year_completes_the_first(self):
		first = AcademicYear.objects.create(
			school=self.school,
			name="Year One",
			start_date=date(2025, 8, 1),
			end_date=date(2026, 7, 31),
			status="active",
		)

		response = self.client.post(
			"/api/schools/academic-years/",
			{
				"name": "Year Two",
				"start_date": "2026-08-01",
				"end_date": "2027-07-31",
				"status": "active",
			},
			format="json",
		)

		self.assertEqual(response.status_code, 201)
		first.refresh_from_db()
		self.assertEqual(first.status, "completed")

		active_count = AcademicYear.objects.filter(
			school=self.school, status="active",
		).count()
		self.assertEqual(active_count, 1)

	def test_updating_a_year_to_active_completes_others(self):
		first = AcademicYear.objects.create(
			school=self.school,
			name="Year One",
			start_date=date(2025, 8, 1),
			end_date=date(2026, 7, 31),
			status="active",
		)
		second = AcademicYear.objects.create(
			school=self.school,
			name="Year Two",
			start_date=date(2026, 8, 1),
			end_date=date(2027, 7, 31),
			status="upcoming",
		)

		response = self.client.patch(
			f"/api/schools/academic-years/{second.pk}/",
			{"status": "active"},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		first.refresh_from_db()
		self.assertEqual(first.status, "completed")

		active_count = AcademicYear.objects.filter(
			school=self.school, status="active",
		).count()
		self.assertEqual(active_count, 1)

	def test_creating_a_non_active_year_does_not_touch_existing_active_year(self):
		first = AcademicYear.objects.create(
			school=self.school,
			name="Year One",
			start_date=date(2025, 8, 1),
			end_date=date(2026, 7, 31),
			status="active",
		)

		response = self.client.post(
			"/api/schools/academic-years/",
			{
				"name": "Year Two",
				"start_date": "2026-08-01",
				"end_date": "2027-07-31",
				"status": "upcoming",
			},
			format="json",
		)

		self.assertEqual(response.status_code, 201)
		first.refresh_from_db()
		self.assertEqual(first.status, "active")


class TenantBrandingApiTests(TestCase):
	def setUp(self):
		self.school_a = School.objects.create(name="School A", code="school-a")
		self.school_b = School.objects.create(name="School B", code="school-b")
		self.user = get_user_model().objects.create_user(
			username="admin-a",
			email="admin-a@test.edu",
			password="TestPass123!",
		)
		membership = InstitutionMembership.objects.create(
			user=self.user,
			institution=self.school_a,
		)
		RoleAssignment.objects.create(membership=membership, role=Role.ADMIN)
		self.client = APIClient()

	def test_branding_is_resolved_from_authenticated_tenant(self):
		self.client.login(username="admin-a", password="TestPass123!")
		response = self.client.get("/api/schools/branding/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["school_code"], "school-a")
		self.assertEqual(response.data["school_name"], "School A")

	def test_branding_update_cannot_touch_another_tenant(self):
		self.client.login(username="admin-a", password="TestPass123!")
		response = self.client.put(
			"/api/schools/branding/",
			{"school_name": "Changed A"},
			format="multipart",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(School.objects.get(pk=self.school_a.pk).name, "Changed A")
		self.assertEqual(School.objects.get(pk=self.school_b.pk).name, "School B")

	def test_public_config_requires_a_valid_active_code(self):
		response = self.client.get(
			"/api/schools/tenant-config/?school_code=school-b"
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["school_name"], "School B")

		missing = self.client.get(
			"/api/schools/tenant-config/?school_code=missing"
		)
		self.assertEqual(missing.status_code, 404)


class ThemeColorBrandingApiTests(TestCase):
	"""Theme color API: validation, persistence, isolation, fail-closed."""

	def _login(self, user):
		self.client.force_login(user)

	def setUp(self):
		self.school_a = School.objects.create(name="School A", code="school-a")
		self.school_b = School.objects.create(name="School B", code="school-b")
		self.school_c = School.objects.create(
			name="School Inactive", code="school-c", status="inactive",
		)

		self.admin_a = get_user_model().objects.create_user(
			username="admin-a2", email="admin-a2@test.edu", password="TestPass123!",
		)
		membership_a = InstitutionMembership.objects.create(
			user=self.admin_a, institution=self.school_a,
		)
		RoleAssignment.objects.create(membership=membership_a, role=Role.ADMIN)

		self.admin_b = get_user_model().objects.create_user(
			username="admin-b2", email="admin-b2@test.edu", password="TestPass123!",
		)
		membership_b = InstitutionMembership.objects.create(
			user=self.admin_b, institution=self.school_b,
		)
		RoleAssignment.objects.create(membership=membership_b, role=Role.ADMIN)

		self.admin_c = get_user_model().objects.create_user(
			username="admin-c2", email="admin-c2@test.edu", password="TestPass123!",
		)
		membership_c = InstitutionMembership.objects.create(
			user=self.admin_c, institution=self.school_c,
		)
		RoleAssignment.objects.create(membership=membership_c, role=Role.ADMIN)

		self.teacher_a = get_user_model().objects.create_user(
			username="teacher-a", email="teacher-a@test.edu", password="TestPass123!",
		)
		membership_t = InstitutionMembership.objects.create(
			user=self.teacher_a, institution=self.school_a,
		)
		RoleAssignment.objects.create(membership=membership_t, role=Role.TEACHER)

		self.client = APIClient()

	def test_theme_color_has_safe_default(self):
		self._login(self.admin_a)
		response = self.client.get("/api/schools/branding/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["theme_color"], "#1a73e8")

	def test_theme_color_saves_valid_preset_and_custom_hex(self):
		self._login(self.admin_a)

		for color in ("#7c3aed", "#7C3AED"):
			with self.subTest(color=color):
				response = self.client.put(
					"/api/schools/branding/",
					{"theme_color": color},
					format="multipart",
				)

				self.assertEqual(response.status_code, 200)
				self.assertEqual(response.data["theme_color"], color)

				got = self.client.get("/api/schools/branding/")
				self.assertEqual(got.data["theme_color"], color)

		row = SchoolSettings.objects.get(school=self.school_a)
		self.assertEqual(row.theme_color, "#7C3AED")

	def test_invalid_theme_color_rejected_and_existing_preserved(self):
		self._login(self.admin_a)

		valid = self.client.put(
			"/api/schools/branding/", {"theme_color": "#7c3aed"}, format="multipart",
		)
		self.assertEqual(valid.status_code, 200)

		for bad in ("red", "#fff", "123456", "##7c3aed", "#7c3aed00", "#7c3ae", "##", "", "# 7c3aed"):
			with self.subTest(bad=bad):
				response = self.client.put(
					"/api/schools/branding/",
					{"theme_color": bad},
					format="multipart",
				)

				self.assertEqual(response.status_code, 400)
				self.assertEqual(
					response.data["detail"],
					"theme_color must be a valid hex color, e.g. #RRGGBB.",
				)

		row = SchoolSettings.objects.get(school=self.school_a)
		self.assertEqual(row.theme_color, "#7c3aed", "invalid input must not overwrite a saved theme")

	def test_theme_color_is_scoped_to_own_school(self):
		self._login(self.admin_a)
		self.client.put(
			"/api/schools/branding/", {"theme_color": "#7c3aed"}, format="multipart",
		)

		self._login(self.admin_b)
		response = self.client.get("/api/schools/branding/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["school_code"], "school-b")
		self.assertEqual(response.data["theme_color"], "#1a73e8")

	def test_foreign_active_school_context_rejected_fail_closed(self):
		self._login(self.admin_a)

		def _assert_foreign_context():
			# The middleware self-heals the session after a rejected request,
			# so the stale/foreign context must be re-asserted before EACH call
			# (same pattern as the hostel allocation tests).
			session = self.client.session
			session["active_institution_id"] = self.school_b.pk
			session.save()

		_assert_foreign_context()
		got = self.client.get("/api/schools/branding/")
		self.assertEqual(got.status_code, 403)

		_assert_foreign_context()
		put = self.client.put(
			"/api/schools/branding/",
			{"theme_color": "#e11d48"},
			format="multipart",
		)
		self.assertEqual(put.status_code, 403)
		self.assertFalse(
			SchoolSettings.objects.filter(school=self.school_b, theme_color="#e11d48").exists(),
			"a stale context must not be able to write another school's branding",
		)

	def test_multi_membership_user_sees_theme_per_active_school(self):
		# Same Super Admin of both schools: the served theme must follow the
		# active school every time — School A purple / School B green with no
		# crosstalk. (Normal users are bound to exactly one school; only the
		# platform Super Admin may hold multiple memberships.)
		dual = get_user_model().objects.create_superuser(
			username="dual-a-b", email="dual-ab@test.edu", password="TestPass123!",
		)
		for school in (self.school_a, self.school_b):
			membership = InstitutionMembership.objects.create(
				user=dual, institution=school,
			)
			RoleAssignment.objects.create(membership=membership, role=Role.ADMIN)

		self._login(dual)

		# Active school = A (explicitly, the way the shell sets it).
		session = self.client.session
		session["active_institution_id"] = self.school_a.pk
		session.save()

		self.client.put(
			"/api/schools/branding/", {"theme_color": "#7c3aed"}, format="multipart",
		)
		self.assertEqual(
			SchoolSettings.objects.get(school=self.school_a).theme_color, "#7c3aed",
		)

		# Switch active school to B (as the shell does on school change).
		session = self.client.session
		session["active_institution_id"] = self.school_b.pk
		session.save()

		got_b = self.client.get("/api/schools/branding/")
		self.assertEqual(got_b.status_code, 200)
		self.assertEqual(got_b.data["school_code"], "school-b")
		self.assertEqual(got_b.data["theme_color"], "#1a73e8")

		# And back to A without reloading anything else.
		session = self.client.session
		session["active_institution_id"] = self.school_a.pk
		session.save()

		got_a = self.client.get("/api/schools/branding/")
		self.assertEqual(got_a.status_code, 200)
		self.assertEqual(got_a.data["school_code"], "school-a")
		self.assertEqual(got_a.data["theme_color"], "#7c3aed")

		# School B must still be untouched.
		self.assertEqual(
			SchoolSettings.objects.get(school=self.school_b).theme_color, "#1a73e8",
		)

	def test_invalid_active_school_context_rejected(self):
		self._login(self.admin_a)

		session = self.client.session
		session["active_institution_id"] = 999999
		session.save()

		response = self.client.get("/api/schools/branding/")
		self.assertEqual(response.status_code, 403)

	def test_missing_active_school_fails_closed(self):
		platform = get_user_model().objects.create_superuser(
			username="platform-a",
			email="platform-a@test.edu",
			password="TestPass123!",
		)
		self._login(platform)

		got = self.client.get("/api/schools/branding/")
		self.assertEqual(got.status_code, 404)

		put = self.client.put(
			"/api/schools/branding/", {"theme_color": "#16a34a"}, format="multipart",
		)
		self.assertEqual(put.status_code, 404)

	def test_inactive_school_theme_fails_closed(self):
		self._login(self.admin_c)
		response = self.client.get("/api/schools/branding/")
		self.assertEqual(response.status_code, 403)

	def test_non_admin_can_read_but_not_modify(self):
		self._login(self.teacher_a)

		got = self.client.get("/api/schools/branding/")
		self.assertEqual(got.status_code, 200)
		self.assertEqual(got.data["theme_color"], "#1a73e8")

		put = self.client.put(
			"/api/schools/branding/", {"theme_color": "#dc2626"}, format="multipart",
		)
		self.assertEqual(put.status_code, 403)
		self.assertEqual(
			SchoolSettings.objects.get(school=self.school_a).theme_color,
			"#1a73e8",
		)

	def test_put_echoes_confirmed_persisted_payload(self):
		self._login(self.admin_a)
		response = self.client.put(
			"/api/schools/branding/",
			{"theme_color": "#059669", "school_name": "School A Renamed"},
			format="multipart",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["theme_color"], "#059669")
		self.assertEqual(response.data["school_name"], "School A Renamed")
		self.assertEqual(response.data["school_code"], "school-a")


class SectionDetailApiTests(TestCase):
	def setUp(self):
		self.school_a = School.objects.create(name="School A")
		self.campus_a = Campus.objects.create(school=self.school_a, name="Campus A")
		self.unit_a = AcademicUnit.objects.create(campus=self.campus_a, name="Unit A")
		self.class_a = Class.objects.create(unit=self.unit_a, name="Grade 1")
		self.section_a = Section.objects.create(class_obj=self.class_a, name="A")

		self.school_b = School.objects.create(name="School B")
		self.campus_b = Campus.objects.create(school=self.school_b, name="Campus B")
		self.unit_b = AcademicUnit.objects.create(campus=self.campus_b, name="Unit B")
		self.class_b = Class.objects.create(unit=self.unit_b, name="Grade 1")
		self.section_b = Section.objects.create(class_obj=self.class_b, name="A")

		self.user = get_user_model().objects.create_user(
			username="admin-a",
			email="admin-a@test.edu",
			password="TestPass123!",
		)
		membership = InstitutionMembership.objects.create(
			user=self.user,
			institution=self.school_a,
		)
		RoleAssignment.objects.create(membership=membership, role=Role.ADMIN)
		self.client = APIClient()
		self.client.login(username="admin-a", password="TestPass123!")

	def test_update_section(self):
		response = self.client.patch(
			f"/api/schools/sections/{self.section_a.pk}/",
			{"capacity": 45},
			format="json",
		)
		self.assertEqual(response.status_code, 200)
		self.section_a.refresh_from_db()
		self.assertEqual(self.section_a.capacity, 45)

	def test_update_enforces_unique_name_within_class(self):
		other = Section.objects.create(class_obj=self.class_a, name="B")
		response = self.client.patch(
			f"/api/schools/sections/{other.pk}/",
			{"name": "A"},
			format="json",
		)
		self.assertEqual(response.status_code, 400)
		self.section_a.refresh_from_db()
		other.refresh_from_db()
		self.assertEqual(other.name, "B")

	def test_delete_section(self):
		section_to_delete = Section.objects.create(class_obj=self.class_a, name="C")
		response = self.client.delete(
			f"/api/schools/sections/{section_to_delete.pk}/"
		)
		self.assertEqual(response.status_code, 204)
		self.assertFalse(
			Section.objects.filter(pk=section_to_delete.pk).exists()
		)

	def test_cannot_access_section_from_another_tenant(self):
		for method, kwargs in [
			("get", {}),
			("patch", {"capacity": 30}),
			("delete", {}),
		]:
			response = getattr(self.client, method)(
				f"/api/schools/sections/{self.section_b.pk}/",
				**kwargs,
			)
			self.assertEqual(
				response.status_code,
				404,
				f"{method} on foreign section",
			)
