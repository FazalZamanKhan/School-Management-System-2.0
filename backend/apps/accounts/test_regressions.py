"""Regression tests for reported production bugs.

Covers:
  * Teacher list/detail no longer 500s (broken ``institutionmembership``
    lookup) and remains school-scoped, enabling teacher profile + delete.
  * Staff leave creation accepts a request without a `staff` field (derived
    from the authenticated staff profile) and staff attendance mark uses the
    effective staff member.
  * Health record campus is derived from the student's active enrollment and
    cannot be set arbitrarily by the client.
  * HR employee creation endpoint works.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import (
    InstitutionMembership,
    Role,
    RoleAssignment,
    StaffAttendance,
    StaffLeave,
    StaffProfile,
)
from apps.health.models import HealthRecord
from apps.hr.models import Employee
from apps.schools.models import (
    AcademicUnit,
    AcademicYear,
    Campus,
    Class,
    Section,
    School,
    Subject,
)
from apps.students.models import Enrollment, Student, Guardian
from apps.teachers.models import Teacher

PASSWORD = "Test#Strong2026"


def _school(name, code):
    return School.objects.create(
        name=name,
        code=code,
        institution_type="school",
        status="active",
    )


def _member(user, school, role=Role.ADMIN):
    membership = InstitutionMembership.objects.create(
        user=user,
        institution=school,
        status="active",
    )
    RoleAssignment.objects.create(
        membership=membership,
        role=role,
    )
    return membership


class StaffPortalRegressionTests(TestCase):
    def setUp(self):
        self.school = _school("Riverdale High", "RIV")
        self.campus = Campus.objects.create(
            school=self.school, name="Main Campus", status="active"
        )

        self.admin = self._make_user("admin.riv", Role.ADMIN)
        self.hr = self._make_user("hr.riv", Role.HR)
        self.staff_member = self._make_user("staff.riv", Role.STAFF)

        self.staff_profile = StaffProfile.objects.create(
            user=self.staff_member,
            institution=self.school,
            employee_number="STF-001",
            first_name="Ayesha",
            last_name="Khan",
            gender="female",
            primary_campus=self.campus,
        )

        self.client = APIClient()

    def _make_user(self, username, role):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(
            username=username,
            email=f"{username}@test.edu",
            password=PASSWORD,
            institution=self.school,
        )
        _member(user, self.school, role)
        return user

    def _login(self, user):
        self.client.force_login(user)
        # Bind the session to the active school like the middleware does.
        session = self.client.session
        session["active_institution_id"] = self.school.id
        session.save()

    def test_staff_can_submit_own_leave_without_staff_field(self):
        self._login(self.staff_member)
        response = self.client.post(
            "/api/staff/leave/",
            {
                "leave_type": "casual",
                "start_date": "2026-09-05",
                "end_date": "2026-09-05",
                "reason": "Family errand",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        leave = StaffLeave.objects.get()
        self.assertEqual(leave.staff, self.staff_profile)
        self.assertEqual(leave.institution, self.school)

    def test_admin_can_create_attendance_for_selected_staff(self):
        self._login(self.admin)
        response = self.client.post(
            "/api/staff/attendance/",
            {
                "staff": self.staff_profile.id,
                "date": "2026-09-05",
                "status": "present",
                "check_in": "08:00:00",
                "check_out": "16:00:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        record = StaffAttendance.objects.get()
        self.assertEqual(record.staff, self.staff_profile)
        self.assertEqual(record.marked_by, self.admin)

    def test_attendance_register_loads_without_error(self):
        self._login(self.admin)
        response = self.client.get("/api/staff/attendance/?date=2026-09-05")
        self.assertEqual(response.status_code, 200, response.content)

    def test_leave_register_remains_school_scoped(self):
        other = _school("Other School", "OTH")
        other_campus = Campus.objects.create(
            school=other, name="Other Campus", status="active"
        )
        other_user = self._make_user("staff.oth", Role.STAFF)
        StaffProfile.objects.create(
            user=other_user,
            institution=other,
            employee_number="STF-OTH-1",
            first_name="Zara",
            last_name="Malik",
            gender="female",
            primary_campus=other_campus,
        )

        self._login(self.admin)
        response = self.client.get("/api/staff/leave/")
        self.assertEqual(response.status_code, 200, response.content)
        # School B staff cannot create leave in school A via this admin.
        response = self.client.post(
            "/api/staff/leave/",
            {
                "staff": other_user.staff_profile.id,
                "leave_type": "casual",
                "start_date": "2026-09-05",
                "end_date": "2026-09-06",
                "reason": "Cross-school attempt",
            },
            format="json",
        )
        self.assertIn(response.status_code, (400, 404), response.content)


class TeacherDetailRegressionTests(TestCase):
    def setUp(self):
        self.school = _school("Riverdale High", "RIV")
        self.admin = self._make_admin()
        self.campus = Campus.objects.create(
            school=self.school, name="Main Campus", status="active"
        )
        self.teacher = Teacher.objects.create(
            institution=self.school,
            employee_number="T-001",
            first_name="Ayesha",
            last_name="Khan",
            gender="female",
            primary_campus=self.campus,
        )
        self.client = APIClient()
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_institution_id"] = self.school.id
        session.save()

    def _make_admin(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(
            username="admin.teacher",
            email="admin.teacher@test.edu",
            password=PASSWORD,
            institution=self.school,
        )
        _member(user, self.school, Role.ADMIN)
        return user

    def test_teacher_detail_no_longer_500s(self):
        response = self.client.get(f"/api/teachers/{self.teacher.id}/")
        self.assertEqual(response.status_code, 200, response.content)

    def test_teacher_delete_soft_deletes(self):
        response = self.client.delete(f"/api/teachers/{self.teacher.id}/")
        self.assertEqual(response.status_code, 204, response.content)
        self.teacher.refresh_from_db()
        self.assertIsNotNone(self.teacher.deleted_at)

    def test_teacher_list_is_school_scoped(self):
        other = _school("Other School", "OTH")
        Teacher.objects.create(
            institution=other,
            employee_number="T-OTH",
            first_name="Zara",
            last_name="Malik",
            gender="female",
        )
        response = self.client.get("/api/teachers/")
        self.assertEqual(response.status_code, 200, response.content)
        ids = [row["id"] for row in response.data.get("results", [])]
        self.assertEqual(ids, [self.teacher.id])


class HealthRecordCampusFromEnrollmentTests(TestCase):
    def setUp(self):
        self.school = _school("Riverdale High", "RIV")
        self.campus = Campus.objects.create(
            school=self.school, name="Main Campus", status="active"
        )
        self.academic_year = AcademicYear.objects.create(
            school=self.school,
            name="2026-2027",
            start_date="2026-08-01",
            end_date="2027-07-31",
        )
        unit = AcademicUnit.objects.create(
            campus=self.campus, name="Primary"
        )
        class_obj = Class.objects.create(unit=unit, name="Grade 1")
        section = Section.objects.create(class_obj=class_obj, name="A")
        self.subject = Subject.objects.create(name="English", code="ENG-1")

        self.health_user = self._make_user("nurse.riv", Role.STAFF)
        StaffProfile.objects.create(
            user=self.health_user,
            institution=self.school,
            employee_number="STF-NURSE-1",
            first_name="Sana",
            last_name="Nurse",
            gender="female",
            primary_campus=self.campus,
        )
        self.guardian = Guardian.objects.create(
            institution=self.school,
            name="Imran Raza",
            relationship="Father",
            phone="0300-0000000",
        )
        self.student = Student.objects.create(
            admission_number="STU-001",
            first_name="Ali",
            last_name="Raza",
            gender="male",
            guardian=self.guardian,
        )
        Enrollment.objects.create(
            student=self.student,
            campus=self.campus,
            class_obj=class_obj,
            section=section,
            academic_year=self.academic_year,
            status="active",
        )

        self.client = APIClient()

    def _make_user(self, username, role):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(
            username=username,
            email=f"{username}@test.edu",
            password=PASSWORD,
            institution=self.school,
        )
        _member(user, self.school, role)
        return user

    def _login(self):
        self.client.force_login(self.health_user)
        session = self.client.session
        session["active_institution_id"] = self.school.id
        session.save()

    def test_campus_derived_from_active_enrollment(self):
        self._login()
        response = self.client.post(
            "/api/health-records/records/",
            {
                "student": self.student.id,
                "record_type": "checkup",
                "record_date": "2026-09-05",
                "notes": "Routine checkup",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        record = HealthRecord.objects.get()
        self.assertEqual(record.campus, self.campus)
        self.assertEqual(record.institution, self.school)


class HREmployeeCreationTests(TestCase):
    def setUp(self):
        self.school = _school("Riverdale High", "RIV")
        self.campus = Campus.objects.create(
            school=self.school, name="Main Campus", status="active"
        )
        self.admin = self._make_user("admin.hr", Role.ADMIN)
        self.client = APIClient()
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_institution_id"] = self.school.id
        session.save()

    def _make_user(self, username, role):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(
            username=username,
            email=f"{username}@test.edu",
            password=PASSWORD,
            institution=self.school,
        )
        _member(user, self.school, role)
        return user

    def test_create_employee_from_staff_profile(self):
        staff_user = self._make_user("staff.hr", Role.STAFF)
        profile = StaffProfile.objects.create(
            user=staff_user,
            institution=self.school,
            employee_number="STF-001",
            first_name="Ayesha",
            last_name="Khan",
            gender="female",
            primary_campus=self.campus,
        )

        response = self.client.post(
            "/api/hr/employees/",
            {
                "staff_profile": profile.id,
                "employment_type": "permanent",
                "status": "active",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        employee = Employee.objects.get()
        self.assertEqual(employee.institution, self.school)
        self.assertEqual(employee.staff_profile, profile)
        self.assertTrue(employee.employee_number)

    def test_employee_creation_requires_profile_link(self):
        response = self.client.post(
            "/api/hr/employees/",
            {
                "employment_type": "permanent",
                "status": "active",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)


"""Phase 84: Designation -> Role Mapping Regression Tests

Covers the fix for Phase 83 root cause: StaffProfile auto-provisioning
used to hardcode Role.STAFF for ALL designations. Now:
- Counsellor -> Role.COUNSELLOR (new canonical role)
- Security Guard -> Role.GUARD
- Nurse -> Role.NURSE
- Administrative Officer -> Role.ADMINISTRATIVE_OFFICER (new canonical role)
- Librarian -> Role.LIBRARIAN
- Unknown designations -> Role.STAFF (generic, never silently elevated)
- Known-good roles (super_admin, principal, teacher, student, staff) unchanged
"""


class DesignationRoleMappingRegressionTests(TestCase):
    """Verify StaffProfile creation + account provisioning maps designations correctly."""

    def setUp(self):
        self.school = _school("Phase84 Test School", "P84")
        self.campus = Campus.objects.create(
            school=self.school, name="Main Campus", status="active"
        )

    def _make_user(self, username, role):
        """Create a user with given role (for permission context)."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(
            username=username, password=PASSWORD, email=f"{username}@example.test"
        )
        membership = InstitutionMembership.objects.create(
            user=user, institution=self.school, status="active"
        )
        RoleAssignment.objects.create(membership=membership, role=role)
        return user

    def _provision_staff_with_designation(self, designation, email=""):
        """Create StaffProfile with designation and auto-provision account."""
        from apps.accounts.serializers import StaffProfileCRUDSerializer
        sequence = StaffProfile.objects.filter(institution=self.school).count() + 1
        serializer = StaffProfileCRUDSerializer(data={
            "employee_number": f"EMP-{sequence}",
            "first_name": "Test",
            "last_name": "User",
            "designation": designation,
            "department": "Test",
            "primary_campus": self.campus.id,
            "gender": "female",
            "joining_date": "2024-01-01",
            "status": "active",
            "create_account": True,
            "email": email or f"test.{sequence}@example.test",
            "password": "TempPass123!",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        staff = serializer.save(institution=self.school)
        return staff

    def _get_user_role(self, user):
        """Return the canonical role value for the user at this school."""
        roles = user.get_roles(institution=self.school)
        # Return the highest-ranked role (first in priority order)
        from apps.accounts.models import ROLE_RANK
        if not roles:
            return None
        return max(roles, key=lambda r: ROLE_RANK.get(r, 0))

    def test_counsellor_maps_to_counsellor_role(self):
        """Counsellor designation -> canonical counsellor role (NEW)."""
        staff = self._provision_staff_with_designation("Counsellor")
        user = staff.user
        self.assertIsNotNone(user)
        role = self._get_user_role(user)
        self.assertEqual(role, "counsellor",
            "Counsellor designation must resolve to canonical 'counsellor' role, not 'staff'")

    def test_security_guard_maps_to_guard_role(self):
        """Security Guard designation -> guard role."""
        staff = self._provision_staff_with_designation("Security Guard")
        user = staff.user
        self.assertIsNotNone(user)
        role = self._get_user_role(user)
        self.assertEqual(role, "guard",
            "Security Guard designation must resolve to 'guard' role")

    def test_nurse_maps_to_nurse_role(self):
        """Nurse designation -> nurse role."""
        staff = self._provision_staff_with_designation("Nurse")
        user = staff.user
        self.assertIsNotNone(user)
        role = self._get_user_role(user)
        self.assertEqual(role, "nurse",
            "Nurse designation must resolve to 'nurse' role")

    def test_lady_health_worker_maps_to_nurse_role(self):
        """Lady Health Worker (girls' campus nurse synonym) -> nurse role."""
        staff = self._provision_staff_with_designation("Lady Health Worker")
        user = staff.user
        self.assertIsNotNone(user)
        role = self._get_user_role(user)
        self.assertEqual(role, "nurse",
            "Lady Health Worker synonym must resolve to 'nurse' role")

    def test_administrative_officer_maps_to_administrative_officer_role(self):
        """Administrative Officer designation -> canonical administrative_officer role (NEW)."""
        staff = self._provision_staff_with_designation("Administrative Officer")
        user = staff.user
        self.assertIsNotNone(user)
        role = self._get_user_role(user)
        self.assertEqual(role, "administrative_officer",
            "Administrative Officer designation must resolve to canonical 'administrative_officer' role, not 'staff'")

    def test_librarian_maps_to_librarian_role(self):
        """Librarian designation -> librarian role."""
        staff = self._provision_staff_with_designation("Librarian")
        user = staff.user
        self.assertIsNotNone(user)
        role = self._get_user_role(user)
        self.assertEqual(role, "librarian",
            "Librarian designation must resolve to 'librarian' role")

    def test_unknown_designation_falls_back_to_staff(self):
        """Unknown designations -> generic staff (never silent elevation)."""
        for designation in ["Janitor", "Clerk", "Driver", "Cook", "Cleaner", "Unknown Role"]:
            with self.subTest(designation=designation):
                staff = self._provision_staff_with_designation(designation)
                user = staff.user
                self.assertIsNotNone(user)
                role = self._get_user_role(user)
                self.assertEqual(role, "staff",
                    "Unknown designation '%s' must fall back to generic 'staff' role" % designation)

    def test_known_good_roles_unaffected(self):
        """Known-good roles (super_admin, principal, teacher, student, staff) unchanged."""
        # These roles are NOT created via StaffProfile serializer _build_user_account
        # so they should be completely unaffected by the designation mapping change.
        # This test documents the expectation.
        from apps.accounts.models import Role
        known_good = [Role.SUPER_ADMIN, Role.PRINCIPAL, Role.TEACHER, Role.STUDENT, Role.STAFF]
        for role in known_good:
            with self.subTest(role=role.value):
                # Create user with explicit role assignment (not via StaffProfile)
                user = self._make_user("test.%s" % role.value, role)
                roles = user.get_roles(institution=self.school)
                self.assertIn(role.value, roles,
                    "Known-good role %s must remain assignable and functional" % role.value)

    def test_case_insensitive_designation_matching(self):
        """Designation matching is case/whitespace-insensitive."""
        variants = [
            ("counsellor", "counsellor"),
            ("COUNSELLOR", "counsellor"),
            (" Security Guard ", "guard"),
            ("SECURITY GUARD", "guard"),
            (" nurse ", "nurse"),
            (" Administrative Officer ", "administrative_officer"),
            (" LIBRARIAN ", "librarian"),
        ]
        for designation, expected_role in variants:
            with self.subTest(designation=designation):
                staff = self._provision_staff_with_designation(designation)
                user = staff.user
                role = self._get_user_role(user)
                self.assertEqual(role, expected_role,
                    "Designation '%s' must resolve to '%s' case-insensitively" % (designation, expected_role))
