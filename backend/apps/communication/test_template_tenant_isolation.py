from rest_framework.test import APITestCase, APIRequestFactory, force_authenticate

from apps.accounts.models import Role, User
from apps.accounts.test_access import make_user
from apps.communication.models import MessageTemplate
from apps.communication.template_views import MessageTemplateListView
from apps.schools.models import School


class TemplateTenantIsolationTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Template A", code="TPL-A")
        other = School.objects.create(name="Template B", code="TPL-B")
        self.admin = make_user("template-admin", Role.ADMIN, self.school)
        self.own = MessageTemplate.objects.create(institution=self.school, name="Own", body="Hi {name}")
        self.foreign = MessageTemplate.objects.create(institution=other, name="Private B", body="Private")
        self.shared = MessageTemplate.objects.create(name="Shared", body="Shared")
        self.client.force_login(self.admin)

    def test_list_includes_own_and_shared_but_not_foreign(self):
        response = self.client.get("/api/communication/templates/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["id"] for row in response.json()}, {self.own.pk, self.shared.pk})

    def test_foreign_detail_preview_update_and_delete_are_denied(self):
        url = f"/api/communication/templates/{self.foreign.pk}/"
        for method, path, payload in (
            ("get", url, None), ("post", url + "preview/", {"context": {}}),
            ("put", url, {"body": "Hacked"}), ("delete", url, None),
        ):
            with self.subTest(method=method):
                response = getattr(self.client, method)(path, data=payload, format="json")
                self.assertEqual(response.status_code, 404)
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.body, "Private")

    def test_own_template_remains_editable_and_previewable(self):
        url = f"/api/communication/templates/{self.own.pk}/"
        self.assertEqual(self.client.put(url, {"body": "Hello {name}"}, format="json").status_code, 200)
        response = self.client.post(url + "preview/", {"context": {"name": "A"}}, format="json")
        self.assertEqual(response.json()["body"], "Hello A")

    def test_school_admin_cannot_modify_shared_template(self):
        url = f"/api/communication/templates/{self.shared.pk}/"
        self.assertEqual(self.client.put(url, {"body": "Changed"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_missing_school_fails_closed_for_list_and_create(self):
        factory = APIRequestFactory()
        for request in (factory.get("/"), factory.post("/", {"name": "New", "body": "Text"}, format="json")):
            request.institution = None
            force_authenticate(request, user=self.admin)
            response = MessageTemplateListView.as_view()(request)
            if request.method == "GET":
                self.assertEqual(response.data, [])
            else:
                self.assertEqual(response.status_code, 400)

    def test_platform_admin_retains_cross_school_management(self):
        platform = User.objects.create_superuser("template-platform", "template-platform@test.edu", "TestPass123!")
        self.client.force_login(platform)
        session = self.client.session
        session["active_institution_id"] = self.school.pk
        session.save()
        response = self.client.get("/api/communication/templates/")
        self.assertEqual({row["id"] for row in response.json()}, {self.own.pk, self.shared.pk, self.foreign.pk})
