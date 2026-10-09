from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import StaffProfile
from apps.accounts.test_access import make_user
from apps.schools.models import Campus, School

from .models import Employee, EmploymentContract, PerformanceReview
from .views import EmployeeListCreateView, EmployeeDetailView


class HRModelTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus = Campus.objects.create(school=self.school, name="Main Campus")
        self.reviewer = get_user_model().objects.create_user(
            username="reviewer",
            password="test-pass",
        )
        self.staff = StaffProfile.objects.create(
            employee_number="STF-001",
            first_name="Ayesha",
            last_name="Khan",
            gender="female",
            primary_campus=self.campus,
        )

    def test_employee_requires_a_profile(self):
        employee = Employee(
            institution=self.school,
            employee_number="EMP-001",
        )
        with self.assertRaises(ValidationError):
            employee.full_clean()

    def test_employee_rejects_foreign_campus(self):
        other_school = School.objects.create(name="Other School")
        other_campus = Campus.objects.create(school=other_school, name="Other Campus")
        employee = Employee(
            institution=self.school,
            staff_profile=self.staff,
            employee_number="EMP-001",
            primary_campus=other_campus,
        )
        with self.assertRaises(ValidationError):
            employee.full_clean()

    def test_contract_rejects_reverse_dates(self):
        employee = Employee.objects.create(
            institution=self.school,
            staff_profile=self.staff,
            employee_number="EMP-001",
            primary_campus=self.campus,
        )
        contract = EmploymentContract(
            employee=employee,
            contract_number="CON-001",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 8, 31),
            salary=Decimal("50000.00"),
        )
        with self.assertRaises(ValidationError):
            contract.full_clean()

    def test_review_rating_is_bounded(self):
        employee = Employee.objects.create(
            institution=self.school,
            staff_profile=self.staff,
            employee_number="EMP-001",
            primary_campus=self.campus,
        )
        review = PerformanceReview(
            employee=employee,
            reviewer=self.reviewer,
            period="2026 annual",
            rating=6,
        )
        with self.assertRaises(ValidationError):
            review.full_clean()


class EmployeeAccessControlTests(TestCase):
    """Regression: GET /api/hr/employees/ must require an HR/admin-tier
    role. It previously used IsAdminOrReadOnly, which allows any
    authenticated user (including teacher and student accounts) to read
    every employee record, including nested performance reviews, loans,
    advances and salary revisions via EmployeeDetailView.
    """

    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus = Campus.objects.create(school=self.school, name="Main Campus")
        self.staff = StaffProfile.objects.create(
            institution=self.school,
            employee_number="STF-001",
            first_name="Ayesha",
            last_name="Khan",
            gender="female",
            primary_campus=self.campus,
        )
        self.employee = Employee.objects.create(
            institution=self.school,
            staff_profile=self.staff,
            employee_number="EMP-001",
            primary_campus=self.campus,
        )
        self.teacher_user = make_user("teacher_x", "teacher", self.school)
        self.student_user = make_user("student_x", "student", self.school)
        self.accountant_user = make_user("accountant_x", "accountant", self.school)

    def _get(self, user, view, path="/api/hr/employees/", pk=None):
        request = APIRequestFactory().get(path)
        force_authenticate(request, user)
        request.institution = self.school
        if pk is not None:
            response = view.as_view()(request, pk=pk)
        else:
            response = view.as_view()(request)
        response.render()
        return response

    def test_teacher_cannot_list_employees(self):
        response = self._get(self.teacher_user, EmployeeListCreateView)
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_list_employees(self):
        response = self._get(self.student_user, EmployeeListCreateView)
        self.assertEqual(response.status_code, 403)

    def test_teacher_cannot_retrieve_employee_detail(self):
        response = self._get(
            self.teacher_user,
            EmployeeDetailView,
            path=f"/api/hr/employees/{self.employee.pk}/",
            pk=self.employee.pk,
        )
        self.assertEqual(response.status_code, 403)

    def test_accountant_can_list_employees(self):
        response = self._get(self.accountant_user, EmployeeListCreateView)
        self.assertEqual(response.status_code, 200)
