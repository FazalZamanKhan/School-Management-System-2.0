from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import InstitutionMembership, Role, RoleAssignment, StaffProfile
from apps.hr.models import Employee, LeaveRequest, LeaveType
from apps.schools.models import Campus, School


class HRLeaveReportViewTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Leave Report School",
            code="LRS-001",
            institution_type="school",
            status="active",
        )
        self.campus = Campus.objects.create(
            school=self.school,
            name="Main Campus",
            status="active",
        )
        user = get_user_model().objects.create_user(
            username="leave_accountant",
            password="pass",
            email="leave_accountant@test.edu",
        )
        membership = InstitutionMembership.objects.create(
            user=user,
            institution=self.school,
            status="active",
        )
        RoleAssignment.objects.create(membership=membership, role=Role.ACCOUNTANT)
        StaffProfile.objects.create(
            user=user,
            membership=membership,
            institution=self.school,
            primary_campus=self.campus,
            employee_number="ACC-001",
            first_name="Leave",
            last_name="Accountant",
            gender="female",
        )

        employee_profile = StaffProfile.objects.create(
            institution=self.school,
            primary_campus=self.campus,
            employee_number="STAFF-001",
            first_name="Ayesha",
            last_name="Khan",
            gender="female",
        )
        employee = Employee.objects.create(
            institution=self.school,
            staff_profile=employee_profile,
            employee_number="EMP-001",
            primary_campus=self.campus,
        )
        leave_type = LeaveType.objects.create(
            institution=self.school,
            name="Annual Leave",
            code="ANNUAL",
            category="annual",
        )
        LeaveRequest.objects.create(
            employee=employee,
            leave_type=leave_type,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 2),
            reason="Family event",
            status="approved",
        )
        self.client.force_authenticate(user=user)

    def test_leave_report_uses_current_employee_and_leave_fields(self):
        response = self.client.get("/api/reports/hr/leave/")

        self.assertEqual(response.status_code, 200, response.content[:500])
        body = response.json()
        self.assertEqual(body["summary"]["total_requests"], 1)
        self.assertEqual(Decimal(body["summary"]["total_days"]), Decimal("2"))
        self.assertEqual(body["results"][0]["employee"], "Ayesha Khan")
        self.assertEqual(Decimal(body["results"][0]["days"]), Decimal("2"))
