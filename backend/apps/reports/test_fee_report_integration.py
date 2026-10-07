from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import InstitutionMembership, Role, RoleAssignment, StaffProfile
from apps.finance.models import Invoice, InvoiceItem, Payment, PaymentRefund
from apps.finance.tests import create_base_school


class FeeReportIntegrationReviewTests(APITestCase):
    def setUp(self):
        base = create_base_school()
        self.base = base
        user = get_user_model().objects.create_user(
            username="report_integration_reviewer", password="pass",
            email="report_integration_reviewer@test.edu",
        )
        membership = InstitutionMembership.objects.create(
            user=user, institution=base["school"], status="active",
        )
        RoleAssignment.objects.create(membership=membership, role=Role.ACCOUNTANT)
        StaffProfile.objects.create(
            user=user, membership=membership, institution=base["school"],
            primary_campus=base["campus"], employee_number="ACC-REVIEW",
            first_name="Report", last_name="Reviewer", gender="female",
        )
        today = timezone.localdate()
        self.invoice = Invoice.objects.create(
            institution=base["school"], campus=base["campus"],
            invoice_number="INV-REVIEW-STATUS", student=base["student"],
            enrollment=base["enrollment"], academic_year=base["year"],
            issue_date=today - timedelta(days=10),
            due_date=today - timedelta(days=1), status="overdue",
        )
        InvoiceItem.objects.create(
            invoice=self.invoice, category=base["category"],
            description="Tuition", amount=Decimal("1000.00"),
        )
        self.client.force_authenticate(user=user)

    def test_status_filter_returns_matching_invoice(self):
        response = self.client.get("/api/reports/fees/status/?status_type=overdue")
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertEqual(response.json()["summary"]["total_invoices"], 1)
        self.assertEqual(response.json()["results"][0]["invoice_number"], self.invoice.invoice_number)

    def test_analytics_date_filter_excludes_earlier_invoice(self):
        cutoff = timezone.localdate() - timedelta(days=5)
        response = self.client.get(f"/api/reports/fees/analytics/?date_from={cutoff}")
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertEqual(response.json()["summary"]["summary"]["total_invoiced"], 0)
        earlier = timezone.localdate() - timedelta(days=15)
        response = self.client.get(f"/api/reports/fees/analytics/?date_from={earlier}")
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertEqual(response.json()["summary"]["summary"]["total_invoiced"], 1000)

    def test_collection_report_uses_payment_after_refund(self):
        payment = Payment.objects.create(
            institution=self.base["school"], campus=self.base["campus"],
            receipt_number="RCPT-REVIEW-COLLECTION", invoice=self.invoice,
            amount=Decimal("600.00"), payment_date=timezone.localdate(),
            payment_method="cash", status="completed",
        )
        PaymentRefund.objects.create(
            institution=self.base["school"], campus=self.base["campus"],
            payment=payment, amount=Decimal("100.00"), reason="Review",
        )

        response = self.client.get("/api/reports/fees/collection/?period=monthly")

        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertEqual(response.json()["summary"]["total_payments"], 1)
        self.assertEqual(
            Decimal(str(response.json()["summary"]["total_collected"])),
            Decimal("500"),
        )
        self.assertEqual(
            Decimal(str(response.json()["results"][0]["net_amount"])),
            Decimal("500"),
        )
