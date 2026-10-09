from rest_framework.test import APITestCase
from apps.accounts.models import Role, StaffProfile
from apps.accounts.test_access import make_user
from apps.ai.helpers import make_school, make_structure, make_student
from apps.finance.models import FeeCategory, FeeStructure, Invoice


class BulkFeePreviewTests(APITestCase):
    def setUp(self):
        self.school = make_school("Bulk preview", "BULK-PREVIEW")
        self.structure = make_structure(self.school)
        self.student = make_student(self.school, self.structure)
        actor = make_user("preview-accountant", Role.ACCOUNTANT, self.school)
        StaffProfile.objects.create(user=actor, institution=self.school, primary_campus=self.structure["campus"], employee_number="PREVIEW", first_name="Preview", last_name="Accountant", gender="male")
        self.client.force_login(actor)
        self.payload = {"academic_year": self.structure["year"].pk, "campus": self.structure["campus"].pk, "class_obj": self.structure["class_obj"].pk}

    def test_no_structure_returns_warning_without_creating_invoice(self):
        response = self.client.post("/api/finance/fee-assignment/preview/", self.payload, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["total_students"], 1)
        self.assertIn("warning", response.json()["preview"][0])
        self.assertEqual(Invoice.objects.count(), 0)

    def test_structure_amount_appears_in_dry_run(self):
        category = FeeCategory.objects.create(institution=self.school, name="Tuition")
        FeeStructure.objects.create(academic_year=self.structure["year"], campus=self.structure["campus"], class_obj=self.structure["class_obj"], category=category, amount=250)
        response = self.client.post("/api/finance/fee-assignment/preview/", self.payload, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(float(response.json()["total_amount"]), 250)
        self.assertEqual(response.json()["preview"][0]["student_id"], self.student.pk)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_foreign_school_year_and_class_are_rejected(self):
        foreign = make_structure(make_school("Foreign preview", "FOREIGN-PREVIEW"))
        for field, value in (("academic_year", foreign["year"].pk), ("class_obj", foreign["class_obj"].pk), ("campus", foreign["campus"].pk)):
            with self.subTest(field=field):
                response = self.client.post("/api/finance/fee-assignment/preview/", {**self.payload, field: value}, format="json")
                self.assertIn(response.status_code, (403, 404))
