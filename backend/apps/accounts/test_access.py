from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone
from rest_framework.request import Request as DRFRequest
from rest_framework.test import (
    APIRequestFactory,
    APIClient,
    force_authenticate,
)

from apps.accounts.models import (
    InstitutionMembership,
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
    StaffProfile,
    UserPermission,
)
from apps.accounts.access import (
    assert_campus_allowed,
    campus_access,
    is_global,
    user_allowed_campus_ids,
)
from apps.schools.models import Campus, School

from apps.students.models import Guardian, Student
from apps.teachers.models import Teacher


def make_user(username, role, school, extra_roles=None, campus=None):
    user = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@test.edu",
        password="TestPass123!",
    )
    membership = InstitutionMembership.objects.create(
        user=user,
        institution=school,
    )
    RoleAssignment.objects.create(
        membership=membership,
        role=role,
        campus=campus,
    )
    for extra in extra_roles or []:
        RoleAssignment.objects.create(
            membership=membership,
            role=extra,
        )
    return user


def seed_default_permissions():
    """Insert the default permission catalog into the test database.

    The demo-data seeder normally populates these rows; tests that exercise
    the permission APIs or superuser bypass must create them explicitly.
    """
    for codename, name, category, action in Permission.get_default_permissions():
        Permission.objects.get_or_create(
            codename=codename,
            defaults={
                "name": name,
                "action": action,
                "category": category,
            },
        )


def make_request(user, path="/api/events/"):
    factory = APIRequestFactory()
    django_request = factory.get(path)
    force_authenticate(django_request, user)
    # Simulate ActiveInstitutionMiddleware: the resolved active school is the
    # user's primary institution (no session/context switching in unit tests).
    django_request.institution = user.primary_institution
    return DRFRequest(django_request)


class IsGlobalTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus = Campus.objects.create(
            school=self.school,
            name="Main Campus",
        )

    def test_superuser_is_global(self):
        user = get_user_model().objects.create_superuser(
            username="root",
            email="root@test.edu",
            password="TestPass123!",
        )
        self.assertTrue(is_global(user))

    def test_global_roles(self):
        for role in (Role.SUPER_ADMIN, Role.ADMIN, Role.ACADEMIC):
            with self.subTest(role=role):
                user = make_user(f"g-{role}", role, self.school)
                self.assertTrue(is_global(user))

    def test_non_global_roles(self):
        for role in (
            Role.CAMPUS_ADMIN,
            Role.PRINCIPAL,
            Role.ACCOUNTANT,
            Role.TEACHER,
            Role.STAFF,
            Role.STUDENT,
            Role.PARENT,
        ):
            with self.subTest(role=role):
                user = make_user(f"ng-{role}", role, self.school)
                self.assertFalse(is_global(user))


class UserAllowedCampusTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus_a = Campus.objects.create(
            school=self.school,
            name="Campus A",
        )
        self.campus_b = Campus.objects.create(
            school=self.school,
            name="Campus B",
        )

    def test_super_admin_gets_every_active_campus(self):
        user = make_user("sadmin", Role.SUPER_ADMIN, self.school)
        self.assertEqual(
            user_allowed_campus_ids(user),
            {self.campus_a.pk, self.campus_b.pk},
        )

    def test_inactive_campus_excluded_for_global(self):
        Campus.objects.create(
            school=self.school,
            name="Closed Campus",
            status="inactive",
        )
        user = make_user("sadmin2", Role.SUPER_ADMIN, self.school)
        self.assertEqual(
            user_allowed_campus_ids(user),
            {self.campus_a.pk, self.campus_b.pk},
        )

    def test_campus_admin_scoped_to_primary_campus(self):
        user = make_user("cadmin", Role.CAMPUS_ADMIN, self.school)
        # Campus admin must have explicit RoleAssignment.campus (FAIL CLOSED)
        membership = InstitutionMembership.objects.get(user=user, institution=self.school)
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.CAMPUS_ADMIN,
            campus=self.campus_a,
        )
        StaffProfile.objects.create(
            user=user,
            employee_number="STF-001",
            first_name="Campus",
            last_name="Admin",
            gender="male",
            primary_campus=self.campus_a,
        )
        self.assertEqual(
            user_allowed_campus_ids(user),
            {self.campus_a.pk},
        )

    def test_teacher_scoped_to_primary_campus(self):
        user = make_user("teacher", Role.TEACHER, self.school)
        Teacher.objects.create(
            user=user,
            employee_number="TCH-001",
            first_name="Teach",
            last_name="Er",
            gender="female",
            primary_campus=self.campus_a,
        )
        self.assertEqual(
            user_allowed_campus_ids(user),
            {self.campus_a.pk},
        )

    def test_student_scoped_to_primary_campus(self):
        user = make_user("student", Role.STUDENT, self.school)
        guardian = Guardian.objects.create(
            name="Guardian One",
            relationship="Father",
            phone="555-0200",
        )
        Student.objects.create(
            user=user,
            admission_number="STU-001",
            first_name="Stud",
            last_name="Ent",
            gender="male",
            primary_campus=self.campus_a,
            guardian=guardian,
        )
        self.assertEqual(
            user_allowed_campus_ids(user),
            {self.campus_a.pk},
        )

    def test_parent_scoped_via_children(self):
        user = make_user("parent", Role.PARENT, self.school)
        guardian = Guardian.objects.create(
            user=user,
            name="Parent One",
            relationship="Mother",
            phone="555-0100",
        )
        Student.objects.create(
            admission_number="STU-002",
            first_name="Child",
            last_name="One",
            gender="female",
            primary_campus=self.campus_b,
            guardian=guardian,
        )
        self.assertEqual(
            user_allowed_campus_ids(user),
            {self.campus_b.pk},
        )

    def test_user_with_no_profile_gets_empty_scope(self):
        user = make_user("nobody", Role.STAFF, self.school)
        self.assertEqual(user_allowed_campus_ids(user), set())

    def test_global_user_in_campusless_school_fails_closed(self):
        """A global user whose active school has no campuses must NOT get the
        campuses of other schools (fail closed, never cross-school)."""
        campusless_school = School.objects.create(name="Campusless School")
        other_school = School.objects.create(name="Other School")
        other_campus = Campus.objects.create(
            school=other_school,
            name="Other Campus",
        )
        user = make_user("sadm-empty", Role.ADMIN, campusless_school)

        self.assertEqual(user_allowed_campus_ids(user), set())
        self.assertNotIn(other_campus.pk, user_allowed_campus_ids(user))

    def test_global_user_scope_locked_to_own_school(self):
        """user_allowed_campus_ids never returns another school's campuses."""
        other_school = School.objects.create(name="Other School")
        other_campus = Campus.objects.create(
            school=other_school,
            name="Other Campus",
        )

        school_b = School.objects.create(name="Second School")
        campus_b1 = Campus.objects.create(
            school=school_b,
            name="B Campus 1",
        )
        user = make_user("sadm-scope", Role.ADMIN, school_b)

        self.assertEqual(
            user_allowed_campus_ids(user),
            {campus_b1.pk},
        )
        self.assertNotIn(other_campus.pk, user_allowed_campus_ids(user))

    def test_principal_without_profile_gets_institution_campuses(self):
        """A principal heads the whole school with explicit campus assignments.

        A principal must have explicit RoleAssignment.campus for each campus
        they administer (FAIL CLOSED). This test verifies that a principal
        with explicit campus assignments can access all assigned campuses.
        """
        user = make_user("prin", Role.PRINCIPAL, self.school)
        membership = InstitutionMembership.objects.get(user=user, institution=self.school)
        # Principal must have explicit RoleAssignment.campus for each campus
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.PRINCIPAL,
            campus=self.campus_a,
        )
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.PRINCIPAL,
            campus=self.campus_b,
        )

        self.assertFalse(is_global(user))
        self.assertEqual(
            user_allowed_campus_ids(user),
            {self.campus_a.pk, self.campus_b.pk},
        )

    def test_vice_principal_without_profile_gets_institution_campuses(self):
        user = make_user("vprin", Role.VICE_PRINCIPAL, self.school)
        membership = InstitutionMembership.objects.get(user=user, institution=self.school)
        # Vice Principal must have explicit RoleAssignment.campus for each campus
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.VICE_PRINCIPAL,
            campus=self.campus_a,
        )
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.VICE_PRINCIPAL,
            campus=self.campus_b,
        )
        self.assertEqual(
            user_allowed_campus_ids(user),
            {self.campus_a.pk, self.campus_b.pk},
        )

    def test_principal_scope_locked_to_own_institution(self):
        """A principal must never see another school's campus."""
        other_school = School.objects.create(name="Other School")
        other_campus = Campus.objects.create(
            school=other_school,
            name="Other Campus",
        )
        user = make_user("prin-scope", Role.PRINCIPAL, self.school)
        membership = InstitutionMembership.objects.get(user=user, institution=self.school)
        # Principal must have explicit campus assignments
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.PRINCIPAL,
            campus=self.campus_a,
        )
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.PRINCIPAL,
            campus=self.campus_b,
        )

        allowed = user_allowed_campus_ids(user)

        self.assertEqual(allowed, {self.campus_a.pk, self.campus_b.pk})
        self.assertNotIn(other_campus.pk, allowed)

    def test_principal_gets_no_campuses_for_foreign_institution(self):
        """Leadership widening only applies to the resolved institution."""
        other_school = School.objects.create(name="Other School")
        Campus.objects.create(school=other_school, name="Other Campus")
        user = make_user("prin-foreign", Role.PRINCIPAL, self.school)

        self.assertEqual(
            user_allowed_campus_ids(user, institution=other_school),
            set(),
        )

    def test_campus_admin_without_profile_keeps_empty_scope(self):
        """Campus-level roles stay profile-scoped — not school-wide."""
        user = make_user("cadmin-none", Role.CAMPUS_ADMIN, self.school)
        self.assertEqual(user_allowed_campus_ids(user), set())


class CampusAccessTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus_a = Campus.objects.create(
            school=self.school,
            name="Campus A",
        )
        self.campus_b = Campus.objects.create(
            school=self.school,
            name="Campus B",
        )
        self.admin = make_user("cadmin", Role.CAMPUS_ADMIN, self.school)
        # Campus admin must have explicit RoleAssignment.campus (FAIL CLOSED)
        membership = InstitutionMembership.objects.get(user=self.admin, institution=self.school)
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.CAMPUS_ADMIN,
            campus=self.campus_a,
        )
        StaffProfile.objects.create(
            user=self.admin,
            employee_number="STF-002",
            first_name="Campus",
            last_name="Admin",
            gender="male",
            primary_campus=self.campus_a,
        )

    def test_campus_admin_can_request_own_campus(self):
        request = make_request(self.admin, f"/?campus={self.campus_a.pk}")
        result = campus_access(request)
        self.assertFalse(result["global"])
        self.assertEqual(
            result["requested"],
            self.campus_a.pk,
        )

    def test_campus_admin_denied_foreign_campus(self):
        request = make_request(self.admin, f"/?campus={self.campus_b.pk}")
        with self.assertRaises(PermissionDenied):
            campus_access(request)

    def test_campus_admin_without_param_scoped_to_own(self):
        request = make_request(self.admin, "/")
        result = campus_access(request)
        self.assertEqual(
            result["allowed_ids"],
            {self.campus_a.pk},
        )
        self.assertIsNone(result["requested"])

    def test_global_user_requesting_foreign_campus_allowed(self):
        admin = make_user("sadmin", Role.SUPER_ADMIN, self.school)
        request = make_request(admin, f"/?campus={self.campus_b.pk}")
        result = campus_access(request)
        self.assertTrue(result["global"])
        self.assertEqual(result["requested"], self.campus_b.pk)

    def test_global_user_denied_unknown_campus(self):
        admin = make_user("sadmin2", Role.SUPER_ADMIN, self.school)
        request = make_request(admin, "/?campus=9999")
        with self.assertRaises(PermissionDenied):
            campus_access(request)

    def test_global_user_denied_foreign_school_campus(self):
        """A global user must not address a campus of another school."""
        other_school = School.objects.create(name="Other School")
        other_campus = Campus.objects.create(
            school=other_school,
            name="Other Campus",
        )
        admin = make_user("sadmin-x", Role.SUPER_ADMIN, self.school)
        request = make_request(admin, f"/?campus={other_campus.pk}")
        with self.assertRaises(PermissionDenied):
            campus_access(request)

    def test_principal_without_profile_can_request_own_school_campus(self):
        principal = make_user("prin-campus", Role.PRINCIPAL, self.school)
        # Principal must have explicit RoleAssignment.campus
        membership = InstitutionMembership.objects.get(user=principal, institution=self.school)
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.PRINCIPAL,
            campus=self.campus_a,
        )
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.PRINCIPAL,
            campus=self.campus_b,
        )
        request = make_request(principal, f"/?campus={self.campus_a.pk}")

        result = campus_access(request)

        self.assertFalse(result["global"])
        self.assertEqual(result["requested"], self.campus_a.pk)
        self.assertEqual(
            result["allowed_ids"],
            {self.campus_a.pk, self.campus_b.pk},
        )


class AssertCampusAllowedTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus_a = Campus.objects.create(
            school=self.school,
            name="Campus A",
        )
        self.campus_b = Campus.objects.create(
            school=self.school,
            name="Campus B",
        )
        self.admin = make_user("cadmin", Role.CAMPUS_ADMIN, self.school)
        # Campus admin must have explicit RoleAssignment.campus (FAIL CLOSED)
        membership = InstitutionMembership.objects.get(user=self.admin, institution=self.school)
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.CAMPUS_ADMIN,
            campus=self.campus_a,
        )
        StaffProfile.objects.create(
            user=self.admin,
            employee_number="STF-003",
            first_name="Campus",
            last_name="Admin",
            gender="male",
            primary_campus=self.campus_a,
        )

    def test_foreign_campus_rejected(self):
        with self.assertRaises(PermissionDenied):
            assert_campus_allowed(self.admin, self.campus_b.pk)

    def test_invalid_id_rejected(self):
        with self.assertRaises(PermissionDenied):
            assert_campus_allowed(self.admin, "not-an-id")

    def test_global_user_accepts_any_campus_of_active_school(self):
        admin = make_user("sadmin", Role.SUPER_ADMIN, self.school)
        assert_campus_allowed(admin, self.campus_b.pk, request=make_request(admin))

    def test_global_user_rejects_unknown_campus(self):
        admin = make_user("sadmin2", Role.SUPER_ADMIN, self.school)
        with self.assertRaises(PermissionDenied):
            assert_campus_allowed(
                admin,
                9999,
                request=make_request(admin),
            )

    def test_global_user_rejects_foreign_school_campus(self):
        other_school = School.objects.create(name="Other School")
        other_campus = Campus.objects.create(
            school=other_school,
            name="Other Campus",
        )
        admin = make_user("sadmin-y", Role.SUPER_ADMIN, self.school)
        with self.assertRaises(PermissionDenied):
            assert_campus_allowed(
                admin,
                other_campus.pk,
                request=make_request(admin),
            )

    def test_global_user_without_institution_context_uses_own_scope(self):
        """No explicit institution context -> validated against the user's own
        school's campuses; a campus of another school is still rejected."""
        admin = make_user("sadm-z", Role.SUPER_ADMIN, self.school)
        assert_campus_allowed(admin, self.campus_b.pk)

        other_school = School.objects.create(name="Other School")
        other_campus = Campus.objects.create(
            school=other_school,
            name="Other Campus",
        )
        with self.assertRaises(PermissionDenied):
            assert_campus_allowed(admin, other_campus.pk)


class CampusIsolatedEventListTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus_a = Campus.objects.create(
            school=self.school,
            name="Campus A",
        )
        self.campus_b = Campus.objects.create(
            school=self.school,
            name="Campus B",
        )

        self.now = timezone.now()

        self.super_admin = make_user(
            "sadmin",
            Role.SUPER_ADMIN,
            self.school,
        )

        self.campus_admin = make_user(
            "cadmin",
            Role.CAMPUS_ADMIN,
            self.school,
        )
        # Campus admin must have explicit RoleAssignment.campus (FAIL CLOSED)
        membership = InstitutionMembership.objects.get(user=self.campus_admin, institution=self.school)
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.CAMPUS_ADMIN,
            campus=self.campus_a,
        )
        StaffProfile.objects.create(
            user=self.campus_admin,
            employee_number="STF-004",
            first_name="Campus",
            last_name="Admin",
            gender="male",
            primary_campus=self.campus_a,
        )

        self.event_a = self._make_event("Event A", self.campus_a)
        self.event_b = self._make_event("Event B", self.campus_b)

        self.client = APIClient()

    def _make_event(self, title, campus):
        from apps.events.models import Event

        return Event.objects.create(
            school=self.school,
            campus=campus,
            title=title,
            start_datetime=self.now,
            end_datetime=self.now + timezone.timedelta(hours=1),
            status="published",
            created_by=self.super_admin,
        )

    def _as(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def test_campus_admin_only_sees_own_campus(self):
        client = self._as(self.campus_admin)

        response = client.get("/api/events/")

        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.json()]
        self.assertEqual(titles, ["Event A"])

    def test_campus_admin_denied_foreign_campus_param(self):
        client = self._as(self.campus_admin)

        response = client.get(
            f"/api/events/?campus={self.campus_b.pk}"
        )

        self.assertEqual(response.status_code, 403)

    def test_super_admin_sees_all_events(self):
        client = self._as(self.super_admin)

        response = client.get("/api/events/")

        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.json()]
        self.assertEqual(
            sorted(titles),
            ["Event A", "Event B"],
        )

    def test_super_admin_can_filter_by_campus(self):
        client = self._as(self.super_admin)

        response = client.get(
            f"/api/events/?campus={self.campus_b.pk}"
        )

        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.json()]
        self.assertEqual(titles, ["Event B"])


# =============================================================================
# GRANULAR PERMISSIONS TESTS
# =============================================================================

class PermissionModelTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School")

    def test_default_permissions_created(self):
        """Test that default permissions are defined."""
        perms = Permission.get_default_permissions()
        self.assertGreater(len(perms), 100)
        
        # Check structure
        for codename, name, category, action in perms:
            self.assertIn(".", codename)
            self.assertTrue(name)
            self.assertIn(category, dict(Permission.CATEGORY_CHOICES))
            self.assertIn(action, dict(Permission.ACTION_CHOICES))

    def test_permission_codename_format(self):
        """Test permission codenames follow <resource>.<action> format."""
        for codename, name, category, action in Permission.get_default_permissions():
            parts = codename.split(".")
            self.assertGreaterEqual(len(parts), 2)
            self.assertEqual(parts[-1], action)


class RolePermissionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus = Campus.objects.create(school=self.school, name="Main Campus")

    def test_assign_permission_to_role(self):
        user = make_user("admin", Role.ADMIN, self.school)
        
        # Create a permission
        perm = Permission.objects.get(codename="student.view")
        
        # Assign to role
        role_perm = RolePermission.objects.create(
            role=Role.ADMIN,
            permission=perm,
            institution=self.school,
            granted_by=user,
        )
        
        self.assertEqual(role_perm.role, Role.ADMIN)
        self.assertEqual(role_perm.permission, perm)
        self.assertEqual(role_perm.institution, self.school)
        self.assertEqual(role_perm.granted_by, user)

    def test_role_permission_unique_per_institution(self):
        """Test unique constraint on role+permission+institution."""
        user = make_user("admin", Role.ADMIN, self.school)
        perm = Permission.objects.get(codename="student.view")
        
        RolePermission.objects.create(
            role=Role.ADMIN,
            permission=perm,
            institution=self.school,
            granted_by=user,
        )
        
        # Duplicate should fail
        with self.assertRaises(Exception):
            RolePermission.objects.create(
                role=Role.ADMIN,
                permission=perm,
                institution=self.school,
                granted_by=user,
            )

    def test_role_permission_isolation_per_institution(self):
        """Test role permissions are scoped to institution."""
        other_school = School.objects.create(name="Other School")
        
        perm = Permission.objects.get(codename="student.view")
        
        # Create role permission for first school
        RolePermission.objects.create(
            role=Role.ADMIN,
            permission=perm,
            institution=self.school,
        )
        
        # Same role/permission for other school should be allowed
        rp2 = RolePermission.objects.create(
            role=Role.ADMIN,
            permission=perm,
            institution=other_school,
        )
        
        self.assertEqual(rp2.institution, other_school)


class UserPermissionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus = Campus.objects.create(school=self.school, name="Main Campus")
        
        self.admin_user = make_user("admin", Role.ADMIN, self.school)
        self.target_user = make_user("teacher", Role.TEACHER, self.school)

    def test_grant_allow_permission(self):
        perm = Permission.objects.get(codename="student.create")
        
        user_perm = UserPermission.objects.create(
            user=self.target_user,
            permission=perm,
            institution=self.school,
            effect="allow",
            granted_by=self.admin_user,
        )
        
        self.assertEqual(user_perm.effect, "allow")
        self.assertTrue(user_perm.is_active())

    def test_grant_deny_permission(self):
        perm = Permission.objects.get(codename="student.delete")
        
        user_perm = UserPermission.objects.create(
            user=self.target_user,
            permission=perm,
            institution=self.school,
            effect="deny",
            granted_by=self.admin_user,
        )
        
        self.assertEqual(user_perm.effect, "deny")

    def test_user_permission_expiration(self):
        perm = Permission.objects.get(codename="student.view")
        
        # Expired permission
        expired = UserPermission.objects.create(
            user=self.target_user,
            permission=perm,
            institution=self.school,
            effect="allow",
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        
        self.assertFalse(expired.is_active())
        
        # Same (user, permission, institution) row is unique — flip it valid
        UserPermission.objects.filter(pk=expired.pk).update(
            expires_at=timezone.now() + timezone.timedelta(days=1),
        )
        expired.refresh_from_db()
        
        self.assertTrue(expired.is_active())

    def test_user_permission_unique_per_institution(self):
        perm = Permission.objects.get(codename="student.view")
        
        UserPermission.objects.create(
            user=self.target_user,
            permission=perm,
            institution=self.school,
            effect="allow",
        )
        
        # Duplicate should fail
        with self.assertRaises(Exception):
            UserPermission.objects.create(
                user=self.target_user,
                permission=perm,
                institution=self.school,
                effect="deny",
            )


class UserPermissionEffectiveTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus = Campus.objects.create(school=self.school, name="Main Campus")
        
        self.admin_user = make_user("admin", Role.ADMIN, self.school)
        self.teacher_user = make_user("teacher", Role.TEACHER, self.school)

    def test_role_based_permissions(self):
        """Test permissions granted via role."""
        perm = Permission.objects.get(codename="student.view")
        
        # Assign permission to TEACHER role
        RolePermission.objects.create(
            role=Role.TEACHER,
            permission=perm,
            institution=self.school,
        )
        
        # Teacher should have the permission
        self.assertTrue(self.teacher_user.has_permission("student.view", self.school))
        
        # Non-teacher should not have it
        other_user = make_user("staff", Role.STAFF, self.school)
        self.assertFalse(other_user.has_permission("student.view", self.school))

    def test_user_allow_override(self):
        """Test user-specific allow overrides role."""
        perm = Permission.objects.get(codename="student.create")
        
        # Teacher role doesn't have create permission by default
        self.assertFalse(self.teacher_user.has_permission("student.create", self.school))
        
        # Grant user-specific allow
        UserPermission.objects.create(
            user=self.teacher_user,
            permission=perm,
            institution=self.school,
            effect="allow",
        )
        
        # Now teacher should have it
        self.assertTrue(self.teacher_user.has_permission("student.create", self.school))

    def test_user_deny_override(self):
        """Test user-specific deny overrides role."""
        perm = Permission.objects.get(codename="student.view")
        
        # Assign to TEACHER role
        RolePermission.objects.create(
            role=Role.TEACHER,
            permission=perm,
            institution=self.school,
        )
        
        # Teacher has permission via role
        self.assertTrue(self.teacher_user.has_permission("student.view", self.school))
        
        # Deny for this specific user
        UserPermission.objects.create(
            user=self.teacher_user,
            permission=perm,
            institution=self.school,
            effect="deny",
        )
        
        # Now teacher should NOT have it
        self.assertFalse(self.teacher_user.has_permission("student.view", self.school))

    def test_deny_overrides_allow(self):
        """Test deny takes precedence over allow."""
        perm = Permission.objects.get(codename="student.edit")
        
        # Grant allow
        UserPermission.objects.create(
            user=self.teacher_user,
            permission=perm,
            institution=self.school,
            effect="allow",
        )
        
        self.assertTrue(self.teacher_user.has_permission("student.edit", self.school))
        
        # Then deny (should override)
        UserPermission.objects.filter(
            user=self.teacher_user,
            permission=perm,
            institution=self.school,
        ).update(effect="deny")
        
        self.assertFalse(self.teacher_user.has_permission("student.edit", self.school))

    def test_expired_permissions_not_counted(self):
        perm = Permission.objects.get(codename="student.view")
        
        # Expired allow permission
        UserPermission.objects.create(
            user=self.teacher_user,
            permission=perm,
            institution=self.school,
            effect="allow",
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        
        # Should not have permission
        self.assertFalse(self.teacher_user.has_permission("student.view", self.school))

    def test_superuser_has_all_permissions(self):
        seed_default_permissions()

        superuser = get_user_model().objects.create_superuser(
            username="root",
            email="root@test.edu",
            password="TestPass123!",
        )
        
        perm = Permission.objects.create(
            codename="any.permission",
            name="Any Permission",
            action="view",
            category="system",
        )
        
        # DB-defined permissions are all granted to a superuser
        self.assertTrue(superuser.has_permission("student.view", self.school))
        self.assertTrue(superuser.has_permission("finance.invoice.create", self.school))
        self.assertTrue(superuser.has_permission("any.permission", self.school))

    def test_has_any_permission(self):
        perm1 = Permission.objects.get(codename="student.view")
        perm2 = Permission.objects.get(codename="student.create")
        
        RolePermission.objects.create(
            role=Role.TEACHER,
            permission=perm1,
            institution=self.school,
        )
        
        self.assertTrue(self.teacher_user.has_any_permission(
            ["student.view", "student.create"], self.school
        ))
        self.assertTrue(self.teacher_user.has_any_permission(
            ["student.view"], self.school
        ))
        self.assertFalse(self.teacher_user.has_any_permission(
            ["student.create"], self.school
        ))

    def test_has_all_permissions(self):
        perm1 = Permission.objects.get(codename="student.view")
        perm2 = Permission.objects.get(codename="student.create")
        
        RolePermission.objects.create(
            role=Role.TEACHER,
            permission=perm1,
            institution=self.school,
        )
        
        self.assertTrue(self.teacher_user.has_all_permissions(
            ["student.view"], self.school
        ))
        self.assertFalse(self.teacher_user.has_all_permissions(
            ["student.view", "student.create"], self.school
        ))

    def test_get_permissions_returns_set(self):
        perm = Permission.objects.get(codename="student.view")
        
        RolePermission.objects.create(
            role=Role.TEACHER,
            permission=perm,
            institution=self.school,
        )
        
        perms = self.teacher_user.get_permissions(self.school)
        self.assertIsInstance(perms, set)
        self.assertIn("student.view", perms)


class PermissionAPITests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus = Campus.objects.create(school=self.school, name="Main Campus")
        
        self.admin_user = make_user("admin", Role.ADMIN, self.school)
        self.teacher_user = make_user("teacher", Role.TEACHER, self.school)
        
        self.client = APIClient()
        
        seed_default_permissions()
        
        # Login admin
        self.client.post("/api/auth/csrf/", {}, format="json")
        self.client.post("/api/auth/login/", {
            "username": "admin",
            "password": "TestPass123!",
        }, format="json")

    def test_permission_list_requires_admin(self):
        """Test that permission list requires admin role."""
        # Logout and login as teacher
        self.client.post("/api/auth/logout/")
        self.client.post("/api/auth/csrf/", {}, format="json")
        self.client.post("/api/auth/login/", {
            "username": "teacher",
            "password": "TestPass123!",
        }, format="json")
        
        response = self.client.get("/api/auth/permissions/")
        self.assertEqual(response.status_code, 403)

    def test_permission_list_as_admin(self):
        response = self.client.get("/api/auth/permissions/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Check grouped by category
        self.assertIn("student", data)
        self.assertIn("teacher", data)
        self.assertIn("finance", data)
        
        # Check structure
        for category, perms in data.items():
            for perm in perms:
                self.assertIn("codename", perm)
                self.assertIn("name", perm)
                self.assertIn("action", perm)
                self.assertIn("category", perm)

    def test_role_permission_list(self):
        response = self.client.get("/api/auth/role-permissions/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Initially empty
        self.assertEqual(data, {})

    def test_role_permission_create(self):
        perm = Permission.objects.get(codename="student.create")

        response = self.client.post("/api/auth/role-permissions/create/", {
            "role": Role.TEACHER,
            "permission": perm.pk,
            "institution": self.school.pk,
        }, format="json")
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["role"], Role.TEACHER)
        self.assertEqual(data["permission"], perm.pk)

    def test_role_permission_delete(self):
        # Catalog permissions are system rows (immutable in roles); use a
        # custom, non-system permission for the revoke flow.
        perm = Permission.objects.create(
            codename="custom.role.revocable.view",
            name="Revocable Role Permission",
            action="view",
            category="permission",
        )

        rp = RolePermission.objects.create(
            role=Role.TEACHER,
            permission=perm,
            institution=self.school,
        )
        
        response = self.client.delete(f"/api/auth/role-permissions/{rp.pk}/")
        self.assertEqual(response.status_code, 200)
        
        # Verify deleted
        self.assertFalse(RolePermission.objects.filter(pk=rp.pk).exists())

    def test_role_permission_cannot_delete_system(self):
        perm = Permission.objects.create(
            codename="custom.system.audit.view",
            name="View Audit Logs",
            action="view",
            category="system",
            is_system=True,
        )

        rp = RolePermission.objects.create(
            role=Role.TEACHER,
            permission=perm,
            institution=self.school,
        )
        
        response = self.client.delete(f"/api/auth/role-permissions/{rp.pk}/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("system permission", response.json()["detail"].lower())

    def test_user_permission_list(self):
        response = self.client.get("/api/auth/user-permissions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_user_permission_create_allow(self):
        perm = Permission.objects.get(codename="student.create")

        target_user = make_user("staff1", Role.STAFF, self.school)
        
        response = self.client.post("/api/auth/user-permissions/create/", {
            "user": target_user.pk,
            "permission": perm.pk,
            "institution": self.school.pk,
            "effect": "allow",
            "reason": "Needs to create students for testing",
        }, format="json")
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["effect"], "allow")
        self.assertEqual(data["user"], target_user.pk)

    def test_user_permission_create_deny(self):
        perm = Permission.objects.get(codename="student.delete")

        target_user = make_user("staff2", Role.STAFF, self.school)
        
        response = self.client.post("/api/auth/user-permissions/create/", {
            "user": target_user.pk,
            "permission": perm.pk,
            "institution": self.school.pk,
            "effect": "deny",
        }, format="json")
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["effect"], "deny")

    def test_user_permission_delete(self):
        perm = Permission.objects.get(codename="student.view")

        target_user = make_user("staff3", Role.STAFF, self.school)
        up = UserPermission.objects.create(
            user=target_user,
            permission=perm,
            institution=self.school,
            effect="allow",
        )
        
        response = self.client.delete(f"/api/auth/user-permissions/{up.pk}/")
        self.assertEqual(response.status_code, 200)
        
        self.assertFalse(UserPermission.objects.filter(pk=up.pk).exists())

    def test_user_permissions_summary(self):
        perm1 = Permission.objects.get(codename="student.view")
        perm2 = Permission.objects.get(codename="student.create")

        # Grant role permission
        RolePermission.objects.create(
            role=Role.TEACHER,
            permission=perm1,
            institution=self.school,
        )
        
        # Grant user-specific allow
        UserPermission.objects.create(
            user=self.teacher_user,
            permission=perm2,
            institution=self.school,
            effect="allow",
        )
        
        # Get summary as admin
        response = self.client.get(f"/api/auth/user-permissions/summary/{self.teacher_user.pk}/")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["user_id"], self.teacher_user.pk)
        self.assertEqual(len(data["effective_permissions"]), 2)
        self.assertIn("student.view", data["effective_permissions"])
        self.assertIn("student.create", data["effective_permissions"])
        self.assertEqual(len(data["role_permissions"]), 1)
        self.assertEqual(len(data["user_allow_permissions"]), 1)

    def test_user_can_view_own_permissions(self):
        # Login as teacher
        self.client.post("/api/auth/logout/")
        self.client.post("/api/auth/csrf/", {}, format="json")
        self.client.post("/api/auth/login/", {
            "username": "teacher",
            "password": "TestPass123!",
        }, format="json")
        
        response = self.client.get(f"/api/auth/user-permissions/summary/{self.teacher_user.pk}/")
        self.assertEqual(response.status_code, 200)

    def test_user_cannot_view_others_permissions(self):
        # Login as teacher
        self.client.post("/api/auth/logout/")
        self.client.post("/api/auth/csrf/", {}, format="json")
        self.client.post("/api/auth/login/", {
            "username": "teacher",
            "password": "TestPass123!",
        }, format="json")
        
        # Try to view admin's permissions
        response = self.client.get(f"/api/auth/user-permissions/summary/{self.admin_user.pk}/")
        self.assertEqual(response.status_code, 403)
