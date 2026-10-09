from rest_framework.test import APITestCase

from apps.accounts.models import Role
from apps.accounts.test_access import make_user
from apps.ai.helpers import make_school, make_structure, make_student


class PopulatedBackupTests(APITestCase):
    def setUp(self):
        self.school = make_school("Populated backup", "POP-BACKUP")
        structure = make_structure(self.school)
        self.student = make_student(self.school, structure, name="Backup Student")
        self.student.primary_campus = structure["campus"]
        self.student.save()
        other = make_school("Foreign backup", "FOREIGN-BACKUP")
        self.foreign = make_student(other, make_structure(other), name="Foreign Student")
        self.client.force_login(make_user("pop-backup-admin", Role.ADMIN, self.school))

    def test_backup_traverses_enrollments_without_calling_related_manager(self):
        response = self.client.get("/api/reports/backup/")
        self.assertEqual(response.status_code, 200, response.content[:500])
        rows = response.json()["student_status"]["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], str(self.student.pk))
        self.assertEqual(rows[0]["class_name"], "Grade 6")

    def test_individual_json_and_csv_student_status_exports(self):
        for format_ in ("json", "csv"):
            with self.subTest(format=format_):
                response = self.client.get(f"/api/reports/export/student_status/?format={format_}")
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"Grade 6", response.content)
                self.assertNotIn(b"Foreign Student", response.content)
