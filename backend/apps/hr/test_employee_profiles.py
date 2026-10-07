from rest_framework.test import APITestCase

from apps.accounts.models import Role, StaffProfile
from apps.accounts.test_access import make_user
from apps.hr.models import Employee
from apps.schools.models import School, Campus
from apps.teachers.models import Teacher


class EmployeeProfileTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="HR Profiles", code="HR-PROFILES")
        self.campus = Campus.objects.create(school=self.school, name="Main")
        self.user = make_user("hr-profile-admin", Role.ADMIN, self.school)
        self.client.force_login(self.user)
        self.client.force_authenticate(user=self.user)
        self.staff = StaffProfile.objects.create(
            institution=self.school, primary_campus=self.campus, employee_number="S1",
            first_name="Available", last_name="Staff", gender="female",
        )
        self.teacher = Teacher.objects.create(
            institution=self.school, primary_campus=self.campus, employee_number="T1",
            first_name="Available", last_name="Teacher", gender="male",
        )

    def test_eligible_profiles_can_be_selected_and_created(self):
        for kind, profile, field in (
            ("staff", self.staff, "staff_profile"), ("teacher", self.teacher, "teacher")
        ):
            with self.subTest(profile_type=kind):
                response = self.client.get(f"/api/hr/employees/profiles/?profile_type={kind}")
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual([item["id"] for item in response.json()], [profile.pk])
                response = self.client.post("/api/hr/employees/", {field: profile.pk}, format="json")
                self.assertEqual(response.status_code, 201, response.content)
                self.assertEqual(response.json()["primary_campus"], self.campus.pk)
                self.assertEqual(self.client.get(
                    f"/api/hr/employees/profiles/?profile_type={kind}"
                ).json(), [])

    def test_other_school_profiles_are_excluded_and_rejected_on_creation(self):
        other = School.objects.create(name="Other HR", code="OTHER-HR")
        foreign = StaffProfile.objects.create(
            institution=other, employee_number="FOREIGN", first_name="Foreign",
            last_name="Staff", gender="male",
        )
        data = self.client.get("/api/hr/employees/profiles/").json()
        self.assertEqual([item["id"] for item in data], [self.staff.pk])
        response = self.client.post("/api/hr/employees/", {"staff_profile": foreign.pk}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Employee.objects.filter(staff_profile=foreign).exists())

    def test_duplicate_employee_is_a_validation_error(self):
        Employee.objects.create(institution=self.school, staff_profile=self.staff, employee_number="E1")
        response = self.client.post("/api/hr/employees/", {"staff_profile": self.staff.pk}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_search_finds_legacy_profile_in_active_school(self):
        legacy = StaffProfile.objects.create(
            primary_campus=self.campus, employee_number="LEGACY-1",
            first_name="Legacy", last_name="Staff", gender="female",
        )
        response = self.client.get("/api/hr/employees/profiles/?profile_type=staff&search=LEGACY-1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [legacy.pk])
        created = self.client.post("/api/hr/employees/", {"staff_profile": legacy.pk}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["primary_campus"], self.campus.pk)
