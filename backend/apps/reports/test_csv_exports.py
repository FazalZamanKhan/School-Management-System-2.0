import csv
import io

from rest_framework.test import APITestCase

from apps.accounts.models import Role
from apps.accounts.test_access import make_user
from apps.ai.helpers import make_school, make_structure, make_student
from apps.teachers.models import Teacher
from apps.schools.models import Subject


class CSVExportTests(APITestCase):
    def setUp(self):
        self.school = make_school("CSV School", "CSV-SCHOOL")
        self.structure = make_structure(self.school)
        make_student(self.school, self.structure, name="CSV Student")
        self.teacher = Teacher.objects.create(
            institution=self.school, primary_campus=self.structure["campus"],
            employee_number="CSV-TEACHER", first_name="CSV", last_name="Teacher",
            gender="male", email="csv.teacher@example.com",
        )
        self.user = make_user("csv-admin", Role.ADMIN, self.school)
        self.client.force_login(self.user)
        self.client.force_authenticate(user=self.user)

    def test_affected_csv_downloads_contain_data(self):
        for key in ("teachers", "enrollments", "subjects"):
            with self.subTest(export=key):
                response = self.client.get(f"/api/reports/export/{key}/?format=csv")
                self.assertEqual(response.status_code, 200, response.content)
                self.assertIn("text/csv", response["Content-Type"])
                self.assertIn(f"{key}_export.csv", response["Content-Disposition"])
                rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
                self.assertEqual(len(rows), 1)
                if key == "teachers":
                    self.assertEqual(rows[0]["email"], "csv.teacher@example.com")

    def test_teacher_employee_number_search(self):
        response = self.client.get(
            "/api/reports/export/teachers/?format=csv&search=CSV-TEACHER"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"CSV-TEACHER", response.content)

    def test_subject_export_excludes_foreign_school(self):
        other = make_school("Foreign CSV School", "FOREIGN-CSV")
        Subject.objects.create(institution=other, code="FOREIGN", name="Foreign Subject")
        response = self.client.get("/api/reports/export/subjects/?format=json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertNotIn("Foreign Subject", response.content.decode())

    def test_unknown_export_remains_404(self):
        self.assertEqual(self.client.get("/api/reports/export/unknown/?format=csv").status_code, 404)
