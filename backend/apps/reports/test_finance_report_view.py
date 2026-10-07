from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import Role
from apps.accounts.test_access import make_user
from apps.finance.models import Account, JournalEntry, JournalLine
from apps.schools.models import Campus, School


class FinanceReportViewTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Finance Reports", code="FIN-RPT")
        self.campus = Campus.objects.create(school=self.school, name="Main")
        self.user = make_user("finance-report-admin", Role.ADMIN, self.school)
        self.client.force_authenticate(user=self.user)
        income = Account.objects.create(
            institution=self.school, code="INC", name="Income", account_type="income"
        )
        expense = Account.objects.create(
            institution=self.school, code="EXP", name="Expense", account_type="expense"
        )
        entry = JournalEntry.objects.create(
            institution=self.school, campus=self.campus,
            description="Report fixture", posting_date=date(2026, 1, 10),
        )
        JournalLine.objects.create(entry=entry, account=income, credit=Decimal("100"))
        JournalLine.objects.create(entry=entry, account=expense, debit=Decimal("100"))
        JournalEntry.objects.filter(pk=entry.pk).update(status="posted")

    def test_report_types_return_selected_summary(self):
        expected_fields = {
            "income": "total_income", "expense": "total_expense",
            "pl": "net_profit", "cashflow": "net_cashflow", "ledger": "accounts",
        }
        for report_type, field in expected_fields.items():
            with self.subTest(report_type=report_type):
                response = self.client.get("/api/reports/finance/", {"report_type": report_type})
                self.assertEqual(response.status_code, 200, response.content)
                self.assertIn(field, response.json()["summary"])

    def test_profit_and_loss_totals_and_date_filter(self):
        response = self.client.get("/api/reports/finance/", {"report_type": "pl"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["summary"]["total_income"], 100)
        self.assertEqual(response.json()["summary"]["total_expense"], 100)
        response = self.client.get(
            "/api/reports/finance/", {"report_type": "pl", "date_from": "2026-02-01"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["summary"]["total_income"], 0)

    def test_foreign_campus_is_rejected(self):
        other_school = School.objects.create(name="Other", code="OTHER-RPT")
        other_campus = Campus.objects.create(school=other_school, name="Other")
        response = self.client.get(
            "/api/reports/finance/", {"report_type": "pl", "campus": other_campus.pk}
        )
        self.assertEqual(response.status_code, 403)
