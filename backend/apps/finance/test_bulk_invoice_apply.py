from rest_framework.test import APITestCase
from apps.accounts.models import Role, StaffProfile
from apps.accounts.test_access import make_user
from apps.ai.helpers import make_school, make_structure, make_student
from apps.finance.models import FeeCategory, FeeStructure, Invoice


class BulkInvoiceApplyTests(APITestCase):
    def setUp(self):
        self.school = make_school("Bulk invoices", "BULK-INVOICE")
        self.main = make_structure(self.school)
        self.student = make_student(self.school, self.main)
        self.north = make_structure(self.school, campus_name="North", year_name="North year")
        self.north_student = make_student(self.school, self.north)
        self.foreign = make_structure(make_school("Foreign bulk", "FOREIGN-BULK"))
        self.foreign_student = make_student(self.foreign["year"].school, self.foreign)
        category = FeeCategory.objects.create(institution=self.school, name="Tuition")
        FeeStructure.objects.create(academic_year=self.main["year"], campus=self.main["campus"], class_obj=self.main["class_obj"], category=category, amount=250)
        actor = make_user("bulk-accountant", Role.ACCOUNTANT, self.school)
        StaffProfile.objects.create(user=actor, institution=self.school, primary_campus=self.main["campus"], employee_number="BULK", first_name="Bulk", last_name="Accountant", gender="male")
        self.client.force_login(actor)
        self.payload = {"academic_year": self.main["year"].pk, "campus": self.main["campus"].pk, "class_obj": self.main["class_obj"].pk, "category": category.pk, "due_date": "2026-12-31"}

    def test_apply_creates_intended_invoice_and_skips_it_on_repeat(self):
        response = self.client.post("/api/finance/invoices/bulk/", self.payload, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["skipped"], 0)
        invoice = Invoice.objects.get(pk=response.json()["invoice_ids"][0])
        self.assertEqual(invoice.campus_id, self.main["campus"].pk)
        self.assertEqual(invoice.student_id, self.student.pk)
        self.assertEqual(invoice.institution_id, self.school.pk)
        self.assertEqual(float(invoice.total_amount), 250)
        self.assertFalse(Invoice.objects.filter(student__in=[self.north_student, self.foreign_student]).exists())
        repeat = self.client.post("/api/finance/invoices/bulk/", self.payload, format="json")
        self.assertEqual(repeat.json()["created"], 0)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_foreign_and_other_campus_operations_are_denied(self):
        for campus in (self.north["campus"], self.foreign["campus"]):
            response = self.client.post("/api/finance/invoices/bulk/", {**self.payload, "campus": campus.pk}, format="json")
            self.assertEqual(response.status_code, 403)
        self.assertEqual(Invoice.objects.count(), 0)
