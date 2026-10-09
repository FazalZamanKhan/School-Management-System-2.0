from datetime import date

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.schools.models import AcademicUnit, AcademicYear, Campus, Class, School
from apps.students.models import AdmissionApplication


class PublicAdmissionApplyTests(TestCase):
	def setUp(self):
		self.school = School.objects.create(name="Public Admissions School")
		self.campus = Campus.objects.create(school=self.school, name="Main Campus")
		unit = AcademicUnit.objects.create(campus=self.campus, name="Primary")
		self.class_obj = Class.objects.create(unit=unit, name="Grade 1")
		AcademicYear.objects.create(
			school=self.school,
			name="2026-2027",
			start_date=date(2026, 1, 1),
			end_date=date(2027, 12, 31),
			status="active",
		)
		self.client = APIClient()
		self.payload = {
			"first_name": "Amina",
			"last_name": "Test",
			"gender": "female",
			"date_of_birth": "2014-02-02",
			"guardian_name": "QA Guardian",
			"guardian_phone": "03000000001",
			"campus": self.campus.pk,
			"class_obj": self.class_obj.pk,
		}

	def test_duplicate_public_application_returns_conflict(self):
		first = self.client.post(
			"/api/students/admissions/public/apply/",
			self.payload,
			format="json",
		)
		second = self.client.post(
			"/api/students/admissions/public/apply/",
			self.payload,
			format="json",
		)

		self.assertEqual(first.status_code, status.HTTP_201_CREATED)
		self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
		self.assertEqual(AdmissionApplication.objects.count(), 1)
		self.assertEqual(
			second.data["application_number"],
			first.data["application_number"],
		)

	def test_different_birth_date_is_not_treated_as_duplicate(self):
		first = self.client.post(
			"/api/students/admissions/public/apply/",
			self.payload,
			format="json",
		)
		second_payload = {**self.payload, "date_of_birth": "2014-02-03"}
		second = self.client.post(
			"/api/students/admissions/public/apply/",
			second_payload,
			format="json",
		)

		self.assertEqual(first.status_code, status.HTTP_201_CREATED)
		self.assertEqual(second.status_code, status.HTTP_201_CREATED)
		self.assertEqual(AdmissionApplication.objects.count(), 2)
