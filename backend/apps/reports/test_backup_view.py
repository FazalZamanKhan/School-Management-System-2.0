from rest_framework.test import APITestCase

from apps.accounts.models import Role, StaffProfile
from apps.accounts.test_access import make_user
from apps.reports.export_views import EXPORT_CONFIGS
from apps.schools.models import School, Subject


class DataBackupViewTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Backup School", code="BACKUP")
        self.user = make_user("backup-admin", Role.ADMIN, self.school)
        self.client.force_login(self.user)
        self.client.force_authenticate(user=self.user)

    def test_empty_backup_includes_every_dataset(self):
        response = self.client.get("/api/reports/backup/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(set(response.json()), set(EXPORT_CONFIGS))
        self.assertIn("full_backup.json", response["Content-Disposition"])

    def test_backup_uses_current_schema_and_excludes_other_schools(self):
        own = StaffProfile.objects.create(
            institution=self.school, employee_number="STAFF-B", first_name="Backup",
            last_name="Staff", gender="female", email="backup@example.com",
        )
        subject = Subject.objects.create(institution=self.school, code="MATH", name="Math")
        other = School.objects.create(name="Other School", code="OTHER-BACKUP")
        Subject.objects.create(institution=other, code="MATH", name="Foreign Math")
        response = self.client.get("/api/reports/backup/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["staff"]["rows"][0]["id"], str(own.pk))
        self.assertEqual(data["staff"]["rows"][0]["email"], "backup@example.com")
        self.assertEqual(data["subjects"]["count"], 1)
        self.assertEqual(data["subjects"]["rows"][0]["id"], str(subject.pk))

    def test_non_admin_cannot_download_backup(self):
        self.client.force_authenticate(user=make_user("backup-teacher", Role.TEACHER, self.school))
        self.assertEqual(self.client.get("/api/reports/backup/").status_code, 403)
