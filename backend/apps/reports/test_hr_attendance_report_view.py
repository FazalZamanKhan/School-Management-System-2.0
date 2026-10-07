from datetime import date, time

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import (
    InstitutionMembership,
    Role,
    RoleAssignment,
    StaffAttendance,
    StaffProfile,
)
from apps.hr.models import Employee
from apps.schools.models import Campus, School


class HRAttendanceReportViewTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="HR Attendance School",
            code="HRA-001",
            institution_type="school",
            status="active",
        )
        self.campus = Campus.objects.create(
            school=self.school,
            name="Main Campus",
            status="active",
        )
        user = get_user_model().objects.create_user(
            username="attendance_accountant",
            password="pass",
            email="attendance_accountant@test.edu",
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
            first_name="Attendance",
            last_name="Accountant",
            gender="male",
        )

        employee_profile = StaffProfile.objects.create(
            institution=self.school,
            primary_campus=self.campus,
            employee_number="STAFF-001",
            first_name="Omar",
            last_name="Ali",
            gender="male",
        )
        self.employee = Employee.objects.create(
            institution=self.school,
            staff_profile=employee_profile,
            employee_number="EMP-001",
            primary_campus=self.campus,
        )
        StaffAttendance.objects.create(
            institution=self.school,
            staff=employee_profile,
            date=date(2026, 10, 7),
            status="present",
            check_in=time(8, 0),
            check_out=time(16, 0),
        )
        self.client.force_authenticate(user=user)

    def test_hr_attendance_route_returns_current_employee_attendance(self):
        response = self.client.get(
            f"/api/reports/hr/attendance/?employee={self.employee.id}"
        )

        self.assertEqual(response.status_code, 200, response.content[:500])
        body = response.json()
        self.assertEqual(body["summary"]["total_records"], 1)
        self.assertEqual(body["summary"]["present"], 1)
        self.assertEqual(body["results"][0]["employee_id"], "EMP-001")
        self.assertEqual(body["results"][0]["employee"], "Omar Ali")
        self.assertEqual(body["results"][0]["campus"], "Main Campus")
