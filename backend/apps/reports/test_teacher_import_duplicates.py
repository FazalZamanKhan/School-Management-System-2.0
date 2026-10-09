from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from apps.accounts.models import Role
from apps.accounts.test_access import make_user
from apps.schools.models import School, Campus
from apps.teachers.models import Teacher


class TeacherImportDuplicateTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Teacher import", code="TCH-IMPORT")
        Campus.objects.create(school=self.school, name="Main")
        self.client.force_login(make_user("teacher-import-admin", Role.ADMIN, self.school))

    def upload(self, route="commit", rows="T1,First,Teacher,male,2\n"):
        rows = "".join(line + ",Main\n" for line in rows.splitlines())
        file = SimpleUploadedFile("teachers.csv", ("employee_number,first_name,last_name,gender,experience_years,campus\n" + rows).encode(), content_type="text/csv")
        return self.client.post(f"/api/reports/import/{route}/?key=teachers", {"file": file}, format="multipart")

    def test_reimport_skips_existing_teacher_and_preview_reports_duplicate(self):
        first = self.upload()
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["teachers_created"], 1)
        preview = self.upload("preview")
        self.assertFalse(preview.json()["can_commit"])
        self.assertEqual(preview.json()["error_rows"], 1)
        second = self.upload()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["teachers_created"], 0)
        self.assertEqual(second.json()["teachers_skipped_duplicates"], 1)
        self.assertEqual(Teacher.objects.filter(institution=self.school).count(), 1)

    def test_foreign_school_employee_number_does_not_block_import(self):
        other = School.objects.create(name="Other teacher import", code="OTHER-TCH-IMPORT")
        Teacher.objects.create(institution=other, employee_number="T1", first_name="Foreign", last_name="Teacher", gender="male")
        response = self.upload()
        self.assertEqual(response.json()["teachers_created"], 1)

    def test_mixed_existing_and_new_rows_imports_only_new_teacher(self):
        self.upload()
        response = self.upload(rows="T1,First,Teacher,male,2\nT2,Second,Teacher,female,3\n")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["teachers_created"], 1)
        self.assertEqual(response.json()["teachers_skipped_duplicates"], 1)

    def test_soft_deleted_teacher_is_still_a_duplicate(self):
        self.upload()
        Teacher.objects.get(institution=self.school, employee_number="T1").delete()
        response = self.upload()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["teachers_skipped_duplicates"], 1)
