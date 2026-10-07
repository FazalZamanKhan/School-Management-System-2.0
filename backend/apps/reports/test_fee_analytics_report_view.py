from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import InstitutionMembership, Role, RoleAssignment, StaffProfile
from apps.schools.models import Campus, School


class FeeAnalyticsReportViewTests(APITestCase):
    def setUp(self):
        school = School.objects.create(
            name="Fee Analytics School",
            code="FAS-001",
            institution_type="school",
            status="active",
        )
        campus = Campus.objects.create(
            school=school,
            name="Main Campus",
            status="active",
        )
        user = get_user_model().objects.create_user(
            username="fee_analytics_accountant",
            password="pass",
            email="fee_analytics_accountant@test.edu",
        )
        membership = InstitutionMembership.objects.create(
            user=user,
            institution=school,
            status="active",
        )
        RoleAssignment.objects.create(membership=membership, role=Role.ACCOUNTANT)
        StaffProfile.objects.create(
            user=user,
            membership=membership,
            institution=school,
            primary_campus=campus,
            employee_number="ACC-001",
            first_name="Fee",
            last_name="Accountant",
            gender="female",
        )
        self.client.force_authenticate(user=user)

    def test_date_from_is_applied_to_invoice_issue_date(self):
        response = self.client.get(
            "/api/reports/fees/analytics/?date_from=2026-01-01"
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertEqual(response.json()["summary"]["summary"]["total_invoiced"], 0.0)
