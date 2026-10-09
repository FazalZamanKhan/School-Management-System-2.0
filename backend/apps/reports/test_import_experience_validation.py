from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from apps.accounts.models import Role
from apps.accounts.test_access import make_user
from apps.schools.models import School, Campus
from apps.teachers.models import Teacher


class ImportExperienceValidationTests(APITestCase):
    def setUp(self):
        school = School.objects.create(name="Experience import", code="EXP-IMPORT")
        Campus.objects.create(school=school, name="Main")
        self.client.force_login(make_user("experience-admin", Role.ADMIN, school))

    def upload(self, route, value):
        file = SimpleUploadedFile("teachers.csv", f"employee_number,first_name,last_name,gender,campus,experience_years\nT1,Test,Teacher,male,Main,{value}\n".encode(), content_type="text/csv")
        return self.client.post(f"/api/reports/import/{route}/?key=teachers", {"file": file}, format="multipart")

    def test_negative_noninteger_and_malformed_values_are_rejected(self):
        for value in ("-3", "1.5", "abc"):
            with self.subTest(value=value):
                preview = self.upload("preview", value)
                self.assertEqual(preview.status_code, 200)
                self.assertFalse(preview.json()["can_commit"])
                self.assertEqual(preview.json()["error_rows"], 1)
                commit = self.upload("commit", value)
                self.assertEqual(commit.json()["teachers_created"], 0)
                self.assertEqual(commit.json()["rows_with_errors"], 1)
        self.assertEqual(Teacher.objects.count(), 0)

    def test_zero_positive_and_blank_preview_values_are_valid(self):
        for value in ("0", "3", ""):
            with self.subTest(value=value):
                self.assertTrue(self.upload("preview", value).json()["can_commit"])

    def test_valid_value_is_preserved_on_commit(self):
        self.assertEqual(self.upload("commit", "3").json()["teachers_created"], 1)
        self.assertEqual(Teacher.objects.get(employee_number="T1").experience_years, 3)
