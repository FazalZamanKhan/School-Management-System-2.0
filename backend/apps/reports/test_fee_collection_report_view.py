from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import InstitutionMembership, Role, RoleAssignment, StaffProfile
from apps.schools.models import Campus, School


class FeeCollectionReportViewTests(APITestCase):
    def setUp(self):
        school = School.objects.create(
            name="Fee Collection School",
            code="FCS-001",
            institution_type="school",
            status="active",
        )
        campus = Campus.objects.create(
            school=school,
            name="Main Campus",
            status="active",
        )
        user = get_user_model().objects.create_user(
            username="fee_collection_accountant",
            password="pass",
            email="fee_collection_accountant@test.edu",
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

    def test_monthly_period_is_handled_as_a_report_option(self):
        response = self.client.get("/api/reports/fees/collection/?period=monthly")

        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertEqual(response.json()["summary"]["period"], "monthly")
