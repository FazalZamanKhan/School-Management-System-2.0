"""F12 remediation: student transfer tenant isolation tests."""

from datetime import date

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.test_access import make_user
from apps.accounts.models import Role
from apps.schools.models import (
    AcademicUnit,
    AcademicYear,
    Campus,
    Class,
    School,
    Section,
)
from apps.students.models import (
    Enrollment,
    Guardian,
    Student,
)
from apps.accounts.models import StudentTransfer

TEST_MEDIA_ROOT = "/tmp/test_media_f12"


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class StudentTransferTenantIsolationTests(TestCase):
    """F12 remediation: StudentTransferCreateView tenant isolation."""

    PASSWORD = "TestPass123!"

    def setUp(self):
        # School A
        self.school_a = School.objects.create(name="Northfield Academy")
        self.campus_a1 = Campus.objects.create(school=self.school_a, name="Campus A1")
        self.campus_a2 = Campus.objects.create(school=self.school_a, name="Campus A2")

        # School B
        self.school_b = School.objects.create(name="Southfield Academy")
        self.campus_b1 = Campus.objects.create(school=self.school_b, name="Campus B1")

        # Academic setup for School A
        self.unit_a1 = AcademicUnit.objects.create(campus=self.campus_a1, name="Lower A1")
        self.class_a1 = Class.objects.create(unit=self.unit_a1, name="Grade 6A")
        self.section_a1 = Section.objects.create(class_obj=self.class_a1, name="A")
        self.year_a = AcademicYear.objects.create(
            school=self.school_a,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )

        # Academic setup for School B
        self.unit_b1 = AcademicUnit.objects.create(campus=self.campus_b1, name="Lower B1")
        self.class_b1 = Class.objects.create(unit=self.unit_b1, name="Grade 6B")
        self.section_b1 = Section.objects.create(class_obj=self.class_b1, name="B")
        self.year_b = AcademicYear.objects.create(
            school=self.school_b,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )

        # Guardian and Student in School A
        self.guardian = Guardian.objects.create(
            name="Ada Parent", relationship="Mother", phone="555-4000"
        )
        self.student_a = Student.objects.create(
            institution=self.school_a,
            admission_number="ADM-A-001",
            first_name="Alan",
            last_name="Kid",
            gender="male",
            status="active",
            primary_campus=self.campus_a1,
            guardian=self.guardian,
        )
        Enrollment.objects.create(
            student=self.student_a,
            academic_year=self.year_a,
            campus=self.campus_a1,
            class_obj=self.class_a1,
            section=self.section_a1,
            status="active",
        )

        # Student in School B
        self.student_b = Student.objects.create(
            institution=self.school_b,
            admission_number="ADM-B-001",
            first_name="Bob",
            last_name="Kid",
            gender="male",
            status="active",
            primary_campus=self.campus_b1,
            guardian=self.guardian,
        )
        Enrollment.objects.create(
            student=self.student_b,
            academic_year=self.year_b,
            campus=self.campus_b1,
            class_obj=self.class_b1,
            section=self.section_b1,
            status="active",
        )

        # Users
        self.campus_admin_a1 = make_user(
            "cadmin_a1", Role.CAMPUS_ADMIN, self.school_a, campus=self.campus_a1
        )
        from apps.accounts.models import StaffProfile, InstitutionMembership
        membership_a1 = InstitutionMembership.objects.get(user=self.campus_admin_a1, institution=self.school_a)
        StaffProfile.objects.create(
            user=self.campus_admin_a1,
            membership=membership_a1,
            employee_number="CADM-001",
            first_name="Campus",
            last_name="Admin A1",
            gender="male",
            primary_campus=self.campus_a1,
        )
        self.campus_admin_b1 = make_user(
            "cadmin_b1", Role.CAMPUS_ADMIN, self.school_b, campus=self.campus_b1
        )
        membership_b1 = InstitutionMembership.objects.get(user=self.campus_admin_b1, institution=self.school_b)
        StaffProfile.objects.create(
            user=self.campus_admin_b1,
            membership=membership_b1,
            employee_number="CADM-002",
            first_name="Campus",
            last_name="Admin B1",
            gender="male",
            primary_campus=self.campus_b1,
        )
        self.super_admin = make_user("sadmin", Role.SUPER_ADMIN, self.school_a)

        self.client = APIClient()

    def _as(self, user):
        """Authenticate as user using the same pattern as existing media tests."""
        self.client.force_authenticate(user=None)
        self.assertTrue(
            self.client.login(username=user.username, password=self.PASSWORD),
            f"login failed for {user.username}"
        )
        self.client.force_authenticate(user=user)
        return self.client

    def _transfer_url(self):
        return "/api/students/students/transfer/"

    def test_cross_institution_student_transfer_denied(self):
        """Campus admin from School A cannot transfer student from School B."""
        client = self._as(self.campus_admin_a1)

        response = client.post(
            self._transfer_url(),
            {"to_campus_id": self.campus_a1.pk, "student_id": self.student_b.pk, "reason": "test"},
            format="json",
        )

        # Student from School B should not be found when requested by School A admin
        self.assertEqual(response.status_code, 404)

    def test_cross_institution_campus_target_denied(self):
        """Campus admin from School A cannot target campus in School B."""
        client = self._as(self.campus_admin_a1)

        response = client.post(
            self._transfer_url(),
            {"to_campus_id": self.campus_b1.pk, "student_id": self.student_a.pk, "reason": "test"},
            format="json",
        )

        # Campus from School B should not be found when requested by School A admin
        self.assertEqual(response.status_code, 404)

    def test_auto_detect_within_institution_allowed(self):
        """Campus admin can auto-detect student within their institution."""
        client = self._as(self.campus_admin_a1)

        response = client.post(
            self._transfer_url(),
            {"to_campus_id": self.campus_a1.pk, "reason": "test"},
            format="json",
        )

        # Auto-detect should find student in user's institution
        self.assertEqual(response.status_code, 201)
        transfer_id = response.json()["transfer_id"]
        self.assertIsNotNone(transfer_id)

    def test_cross_institution_auto_detect_denied(self):
        """Campus admin from School A cannot auto-detect student from School B when student_id provided."""
        client = self._as(self.campus_admin_a1)

        response = client.post(
            self._transfer_url(),
            {"to_campus_id": self.campus_a1.pk, "student_id": self.student_b.pk, "reason": "test"},
            format="json",
        )

        # Student from School B should not be found when requested by School A admin
        self.assertEqual(response.status_code, 404)

    def test_same_campus_transfer_allowed(self):
        """Campus admin can transfer student within their assigned campus."""
        client = self._as(self.campus_admin_a1)

        response = client.post(
            self._transfer_url(),
            {"to_campus_id": self.campus_a1.pk, "student_id": self.student_a.pk, "reason": "transfer"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        transfer_id = response.json()["transfer_id"]
        self.assertIsNotNone(transfer_id)

    def test_cross_campus_same_institution_denied(self):
        """Campus admin cannot transfer student to a different campus within same institution."""
        client = self._as(self.campus_admin_a1)

        response = client.post(
            self._transfer_url(),
            {"to_campus_id": self.campus_a2.pk, "student_id": self.student_a.pk, "reason": "cross campus"},
            format="json",
        )

        # Campus admin only assigned to Campus A1, so Campus A2 should be denied
        self.assertEqual(response.status_code, 403)

    def test_campus_admin_same_campus_transfer_allowed(self):
        """Campus admin can transfer student within their assigned campus."""
        client = self._as(self.campus_admin_a1)

        response = client.post(
            self._transfer_url(),
            {"to_campus_id": self.campus_a1.pk, "student_id": self.student_a.pk, "reason": "same campus"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)

    def test_campus_admin_cross_campus_same_institution_denied(self):
        """Campus admin from Campus A1 cannot transfer to Campus A2 if not assigned there."""
        # Campus admin A1 is assigned to Campus A1
        # Should be denied when trying to transfer to Campus A2
        client = self._as(self.campus_admin_a1)

        response = client.post(
            self._transfer_url(),
            {"to_campus_id": self.campus_a2.pk, "student_id": self.student_a.pk, "reason": "cross campus"},
            format="json",
        )

        # Campus admin only assigned to A1, so A2 should be denied
        self.assertEqual(response.status_code, 403)

    def test_non_admin_denied(self):
        """Non-admin users cannot create transfers."""
        teacher_user = make_user("teacher", Role.TEACHER, self.school_a)
        client = self._as(teacher_user)

        response = client.post(
            self._transfer_url(),
            {"to_campus_id": self.campus_a1.pk, "student_id": self.student_a.pk, "reason": "test"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_invalid_campus_id_denied(self):
        """Invalid campus ID returns 404."""
        client = self._as(self.campus_admin_a1)

        response = client.post(
            self._transfer_url(),
            {"to_campus_id": 99999, "student_id": self.student_a.pk, "reason": "test"},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_missing_campus_id_denied(self):
        """Missing campus ID returns 400."""
        client = self._as(self.campus_admin_a1)

        response = client.post(
            self._transfer_url(),
            {"student_id": self.student_a.pk, "reason": "test"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_cross_institution_student_campus_mismatch_denied(self):
        """Student from School A, target campus in School B denied."""
        client = self._as(self.campus_admin_a1)

        response = client.post(
            self._transfer_url(),
            {"to_campus_id": self.campus_b1.pk, "student_id": self.student_a.pk, "reason": "test"},
            format="json",
        )

        # Campus B1 is in School B, but user is from School A
        self.assertEqual(response.status_code, 404)









































































































































































