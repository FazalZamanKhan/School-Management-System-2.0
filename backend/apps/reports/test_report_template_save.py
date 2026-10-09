from rest_framework.test import APITestCase
from apps.accounts.models import Role
from apps.accounts.test_access import make_user
from apps.schools.models import School
from apps.reports.models import ReportTemplate


class ReportTemplateSaveTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Report Builder", code="RPT-BUILDER")
        self.admin = make_user("builder-admin", Role.ADMIN, self.school)
        self.client.force_login(self.admin)

    def test_create_list_read_update_and_delete_persist_options(self):
        payload = {"name": "Fees", "report_type": "fees", "filters": {"status": "issued"}, "columns": ["invoice_number"]}
        response = self.client.post("/api/reports/templates/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        pk = response.json()["id"]
        template = ReportTemplate.objects.get(pk=pk)
        self.assertEqual(template.filters, payload["filters"])
        self.assertEqual(template.columns, payload["columns"])
        self.assertEqual(self.client.get("/api/reports/templates/").json()[0]["filters"], payload["filters"])
        url = f"/api/reports/templates/{pk}/"
        self.assertEqual(self.client.get(url).json()["columns"], payload["columns"])
        self.assertEqual(self.client.put(url, {"filters": {"status": "paid"}, "columns": []}, format="json").status_code, 200)
        template.refresh_from_db()
        self.assertEqual(template.filters, {"status": "paid"})
        self.assertEqual(template.columns, [])
        self.assertEqual(self.client.delete(url).status_code, 200)

    def test_other_user_cannot_read_or_modify_template(self):
        template = ReportTemplate.objects.create(name="Private", report_type="fees", created_by=self.admin)
        other = make_user("other-builder-admin", Role.ADMIN, self.school)
        self.client.force_login(other)
        url = f"/api/reports/templates/{template.pk}/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.put(url, {"name": "Changed"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_existing_template_defaults_remain_readable(self):
        ReportTemplate.objects.create(name="Existing", report_type="fees", created_by=self.admin)
        response = self.client.get("/api/reports/templates/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["filters"], {})
        self.assertEqual(response.json()[0]["columns"], [])
