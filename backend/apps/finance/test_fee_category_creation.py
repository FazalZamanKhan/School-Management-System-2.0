from rest_framework.test import APITestCase, APIRequestFactory, force_authenticate

from apps.accounts.models import Role
from apps.accounts.test_access import make_user
from apps.finance.models import FeeCategory
from apps.schools.models import School


class FeeCategoryCreationTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Fee Categories", code="FEE-CATEGORIES")
        self.user = make_user("fee-category-admin", Role.ADMIN, self.school)
        self.client.force_login(self.user)
        self.client.force_authenticate(user=self.user)

    def test_create_category_and_refresh_list(self):
        response = self.client.post("/api/finance/categories/", {
            "name": "Tuition", "frequency": "monthly", "description": "Monthly tuition",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        category = FeeCategory.objects.get(pk=response.json()["id"])
        self.assertEqual(category.institution_id, self.school.pk)
        self.assertEqual(category.status, "active")
        self.assertEqual(self.client.get("/api/finance/categories/").json()[0]["id"], category.pk)

    def test_invalid_fields_and_duplicate_name_return_validation_errors(self):
        FeeCategory.objects.create(institution=self.school, name="Tuition")
        for payload in ({"name": " "}, {"name": "Tuition"}, {"name": " tuition "}, {"name": "New", "frequency": "bad"}):
            with self.subTest(payload=payload):
                response = self.client.post("/api/finance/categories/", payload, format="json")
                self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(FeeCategory.objects.count(), 1)

    def test_same_name_in_other_school_is_allowed_and_institution_is_server_owned(self):
        other = School.objects.create(name="Other Fee School", code="OTHER-FEE")
        FeeCategory.objects.create(institution=other, name="Tuition")
        response = self.client.post("/api/finance/categories/", {
            "name": "Tuition", "institution": other.pk,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(FeeCategory.objects.get(pk=response.json()["id"]).institution_id, self.school.pk)
        self.assertEqual(len(self.client.get("/api/finance/categories/").json()), 1)

    def test_teacher_cannot_create_category(self):
        self.client.force_authenticate(user=make_user("fee-category-teacher", Role.TEACHER, self.school))
        response = self.client.post("/api/finance/categories/", {"name": "Tuition"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_missing_school_returns_validation_error(self):
        from apps.finance.views import FeeCategoryListView

        request = APIRequestFactory().post("/api/finance/categories/", {"name": "Tuition"}, format="json")
        request.institution = None
        force_authenticate(request, user=self.user)
        response = FeeCategoryListView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("institution", response.data)

    def test_concurrent_duplicate_returns_validation_error(self):
        from unittest.mock import patch
        from django.db import IntegrityError

        with patch("apps.finance.serializers.FeeCategorySerializer.create", side_effect=IntegrityError):
            response = self.client.post("/api/finance/categories/", {"name": "New category"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.json())
