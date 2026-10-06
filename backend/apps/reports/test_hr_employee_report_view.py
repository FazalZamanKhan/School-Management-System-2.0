from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import InstitutionMembership, Role, RoleAssignment, StaffProfile
from apps.hr.models import Employee
from apps.payroll.models import SalaryStructure
from apps.schools.models import Campus, School


class EmployeeMasterReportViewTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Employee Report School",
            code="ERS-001",
            institution_type="school",
            status="active",
        )
        self.campus = Campus.objects.create(
            school=self.school,
            name="Main Campus",
            status="active",
        )
        user = get_user_model().objects.create_user(
            username="employee_accountant",
            password="pass",
            email="employee_accountant@test.edu",
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
            first_name="Employee",
            last_name="Accountant",
            gender="male",
        )

        employee_profile = StaffProfile.objects.create(
            institution=self.school,
            primary_campus=self.campus,
            employee_number="STAFF-001",
            first_name="Sara",
            last_name="Ahmed",
            gender="female",
            email="sara@example.com",
            phone="555-0100",
        )
        employee = Employee.objects.create(
            institution=self.school,
            staff_profile=employee_profile,
            employee_number="EMP-001",
            primary_campus=self.campus,
            employment_type="permanent",
        )
        SalaryStructure.objects.create(
            institution=self.school,
            employee=employee,
            name="Standard Salary",
            code="STD-001",
            basic_salary=Decimal("75000.00"),
            effective_date=date(2026, 1, 1),
        )
        self.client.force_authenticate(user=user)

    def test_employee_report_uses_current_profile_and_campus_fields(self):
        response = self.client.get("/api/reports/hr/employees/")

        self.assertEqual(response.status_code, 200, response.content[:500])
        body = response.json()
        self.assertEqual(body["summary"]["total_employees"], 1)
        self.assertEqual(
            body["summary"]["by_campus"],
            [{"primary_campus__name": "Main Campus", "count": 1}],
        )
        self.assertEqual(body["results"][0]["employee_id"], "EMP-001")
        self.assertEqual(body["results"][0]["full_name"], "Sara Ahmed")
        self.assertEqual(body["results"][0]["email"], "sara@example.com")
        self.assertEqual(body["results"][0]["phone"], "555-0100")
        self.assertEqual(body["results"][0]["campus"], "Main Campus")
        self.assertEqual(body["results"][0]["employment_type"], "Permanent")
        self.assertEqual(Decimal(body["results"][0]["basic_salary"]), Decimal("75000"))
