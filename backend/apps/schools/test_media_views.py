"""F8 remediation: protected media — missing imports, get_institution misuse, branch coverage."""

import os
import io
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
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
    Subject,
)
from apps.students.models import (
    Enrollment,
    Guardian,
    Student,
    StudentDocument,
    StudentGuardian,
)
from apps.hr.models import Employee, EmployeeDocument
from apps.teachers.models import Teacher, TeacherAssignment
from apps.accounts.models import StaffProfile

# Use a unique temp location per test run
TEST_MEDIA_ROOT = "/tmp/test_media_f8"


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ProtectedMediaAccessTests(TestCase):
    """Test media authorization branches with real files on disk."""

    PASSWORD = "TestPass123!"

    def setUp(self):
        self.school = School.objects.create(name="Northfield Academy")
        self.campus = Campus.objects.create(school=self.school, name="Main Campus")
        self.unit = AcademicUnit.objects.create(campus=self.campus, name="Lower")
        self.class_obj = Class.objects.create(unit=self.unit, name="Grade 6")
        self.section = Section.objects.create(class_obj=self.class_obj, name="A")
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )
        self.guardian = Guardian.objects.create(
            name="Ada Parent", relationship="Mother", phone="555-4000"
        )
        self.student = Student.objects.create(
            institution=self.school,
            admission_number="ADM-001",
            first_name="Alan",
            last_name="Kid",
            gender="male",
            status="active",
            primary_campus=self.campus,
            guardian=self.guardian,
        )
        Enrollment.objects.create(
            student=self.student,
            academic_year=self.year,
            campus=self.campus,
            class_obj=self.class_obj,
            section=self.section,
            status="active",
        )

        # Create StudentGuardian link for parent access
        StudentGuardian.objects.create(
            student=self.student,
            guardian=self.guardian,
            is_primary=True,
        )

        # Create a teacher linked to the student
        self.teacher = Teacher.objects.create(
            institution=self.school,
            employee_number="TCH-001",
            first_name="Anna",
            last_name="Teacher",
            gender="female",
            primary_campus=self.campus,
        )

        # Teacher assignment: class_teacher of the student's class/section
        subject = Subject.objects.create(institution=self.school, name="Test Subject", code="TS")
        TeacherAssignment.objects.create(
            teacher=self.teacher,
            campus=self.campus,
            class_obj=self.class_obj,
            section=self.section,
            subject=subject,
            academic_year=self.year,
            role="class_teacher",
            status="active",
        )

        # Create users
        self.student_user = make_user("student", Role.STUDENT, self.school)
        self.student.user = self.student_user
        self.student.save()

        self.teacher_user = make_user("teacher", Role.TEACHER, self.school)
        self.teacher.user = self.teacher_user
        self.teacher.save()

        self.parent_user = make_user("parent", Role.PARENT, self.school)
        self.parent_user.guardian_profile = self.guardian
        self.parent_user.save()

        self.manager_user = make_user("manager", Role.CAMPUS_ADMIN, self.school)
        from apps.accounts.models import RoleAssignment
        RoleAssignment.objects.filter(
            membership__user=self.manager_user,
            role=Role.CAMPUS_ADMIN,
        ).update(campus=self.campus)

        self.admin_user = make_user("admin", Role.SUPER_ADMIN, self.school)

        # Create directories for all media paths
        os.makedirs(os.path.join(TEST_MEDIA_ROOT, "students/documents"), exist_ok=True)
        os.makedirs(os.path.join(TEST_MEDIA_ROOT, "hr/documents"), exist_ok=True)
        os.makedirs(os.path.join(TEST_MEDIA_ROOT, "profiles/students"), exist_ok=True)
        os.makedirs(os.path.join(TEST_MEDIA_ROOT, "profiles/teachers"), exist_ok=True)
        os.makedirs(os.path.join(TEST_MEDIA_ROOT, "profiles/staff"), exist_ok=True)
        os.makedirs(os.path.join(TEST_MEDIA_ROOT, "school/branding"), exist_ok=True)

        # Create a test PDF file for student documents
        self.test_pdf_content = b"%PDF test content"
        student_doc_path = os.path.join(TEST_MEDIA_ROOT, "students/documents/test.pdf")
        with open(student_doc_path, "wb") as f:
            f.write(self.test_pdf_content)

        # Create a test PDF file for employee documents
        hr_doc_path = os.path.join(TEST_MEDIA_ROOT, "hr/documents/test.pdf")
        with open(hr_doc_path, "wb") as f:
            f.write(self.test_pdf_content)

        # Create test image for profile photos
        self._create_test_image()

        # Create student profile image directory and file
        student_profile_dir = os.path.join(TEST_MEDIA_ROOT, "profiles/students", str(self.student.pk))
        os.makedirs(student_profile_dir, exist_ok=True)
        self.student_profile_path = os.path.join(student_profile_dir, "photo.jpg")
        with open(self.student_profile_path, "wb") as f:
            f.write(self.test_image_bytes)
        self.student.photo.name = f"profiles/students/{self.student.pk}/photo.jpg"
        self.student.save(update_fields=["photo"])

        # Create teacher profile image directory and file
        teacher_profile_dir = os.path.join(TEST_MEDIA_ROOT, "profiles/teachers", str(self.teacher.pk))
        os.makedirs(teacher_profile_dir, exist_ok=True)
        self.teacher_profile_path = os.path.join(teacher_profile_dir, "photo.jpg")
        with open(self.teacher_profile_path, "wb") as f:
            f.write(self.test_image_bytes)
        self.teacher.photo.name = f"profiles/teachers/{self.teacher.pk}/photo.jpg"
        self.teacher.save(update_fields=["photo"])

        # Create staff profile image directory and file (for manager)
        from apps.accounts.models import StaffProfile
        staff = StaffProfile.objects.create(
            user=self.manager_user,
            institution=self.school,
            employee_number="STF-001",
            first_name="Staff",
            last_name="User",
            gender="male",
            primary_campus=self.campus,
        )
        self.staff = staff
        staff_profile_dir = os.path.join(TEST_MEDIA_ROOT, "profiles/staff", str(staff.pk))
        os.makedirs(staff_profile_dir, exist_ok=True)
        self.staff_profile_path = os.path.join(staff_profile_dir, "photo.jpg")
        with open(self.staff_profile_path, "wb") as f:
            f.write(self.test_image_bytes)
        staff.photo.name = f"profiles/staff/{staff.pk}/photo.jpg"
        staff.save(update_fields=["photo"])

        # Create public branding image
        from PIL import Image
        img = Image.new('RGB', (10, 10), color='yellow')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        branding_path = os.path.join(TEST_MEDIA_ROOT, "school/branding/logo.png")
        with open(branding_path, "wb") as f:
            f.write(img_bytes.read())

        self.client = APIClient()

    def tearDown(self):
        import shutil
        if os.path.exists(TEST_MEDIA_ROOT):
            shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def _create_test_image(self):
        """Create a minimal valid JPEG for profile photos."""
        from PIL import Image
        img = Image.new('RGB', (10, 10), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        self.test_image_bytes = img_bytes.getvalue()

    def _as(self, user):
        """Authenticate as user using the same pattern as existing media tests."""
        self.client.force_authenticate(user=None)
        self.assertTrue(
            self.client.login(username=user.username, password=self.PASSWORD),
            f"login failed for {user.username}"
        )
        self.client.force_authenticate(user=user)
        return self.client

    def _get_media(self, client, path):
        """Request a media file via the protected media endpoint."""
        return client.get(f"/media/{path}")

    def test_student_document_uploader_access(self):
        """Uploader of a student document can access it."""
        doc = StudentDocument.objects.create(
            institution=self.school,
            student=self.student,
            file="students/documents/test.pdf",
            uploaded_by=self.student_user,
        )
        client = self._as(self.student_user)

        response = self._get_media(client, "students/documents/test.pdf")

        self.assertEqual(response.status_code, 200)

    def test_student_document_parent_access(self):
        """Parent of the student can access the document."""
        doc = StudentDocument.objects.create(
            institution=self.school,
            student=self.student,
            file="students/documents/test.pdf",
            uploaded_by=self.admin_user,
        )
        client = self._as(self.parent_user)

        response = self._get_media(client, "students/documents/test.pdf")

        self.assertEqual(response.status_code, 200)

    def test_student_document_student_self_access(self):
        """Student can access their own document."""
        doc = StudentDocument.objects.create(
            institution=self.school,
            student=self.student,
            file="students/documents/test.pdf",
            uploaded_by=self.admin_user,
        )
        client = self._as(self.student_user)

        response = self._get_media(client, "students/documents/test.pdf")

        self.assertEqual(response.status_code, 200)

    def test_student_document_teacher_access(self):
        """Teacher of the student can access the document."""
        doc = StudentDocument.objects.create(
            institution=self.school,
            student=self.student,
            file="students/documents/test.pdf",
            uploaded_by=self.admin_user,
        )
        client = self._as(self.teacher_user)

        response = self._get_media(client, "students/documents/test.pdf")

        self.assertEqual(response.status_code, 200)

    def test_student_document_manager_access(self):
        """Manager can access any document in their school."""
        doc = StudentDocument.objects.create(
            institution=self.school,
            student=self.student,
            file="students/documents/test.pdf",
            uploaded_by=self.admin_user,
        )
        client = self._as(self.manager_user)

        response = self._get_media(client, "students/documents/test.pdf")

        self.assertEqual(response.status_code, 200)

    def test_student_document_cross_campus_denied(self):
        """Teacher from different campus cannot access (if not global)."""
        campus_b = Campus.objects.create(school=self.school, name="Campus B")
        unit_b = AcademicUnit.objects.create(campus=campus_b, name="Upper")
        class_b = Class.objects.create(unit=unit_b, name="Grade 7")
        section_b = Section.objects.create(class_obj=class_b, name="B")
        teacher_b = Teacher.objects.create(
            institution=self.school,
            employee_number="TCH-002",
            first_name="Bob",
            last_name="Teacher",
            gender="male",
            primary_campus=campus_b,
        )
        teacher_b_user = make_user("teacher_b", Role.TEACHER, self.school)
        teacher_b_user.teacher_profile = teacher_b
        teacher_b_user.save()

        doc = StudentDocument.objects.create(
            institution=self.school,
            student=self.student,
            file="students/documents/test.pdf",
            uploaded_by=self.admin_user,
        )
        client = self._as(teacher_b_user)

        response = self._get_media(client, "students/documents/test.pdf")

        # Teacher from different campus, not global -> 404
        self.assertEqual(response.status_code, 404)

    def test_employee_document_self_access(self):
        """Employee can access their own document."""
        # Employee links to Teacher
        employee = Employee.objects.create(
            institution=self.school,
            employee_number="EMP-001",
            teacher=self.teacher,
            primary_campus=self.campus,
        )
        doc = EmployeeDocument.objects.create(
            employee=employee,
            campus=self.campus,
            file="hr/documents/test.pdf",
            uploaded_by=self.admin_user,
        )
        client = self._as(self.teacher_user)

        response = self._get_media(client, "hr/documents/test.pdf")

        self.assertEqual(response.status_code, 200)

    def test_employee_document_uploader_access(self):
        """Uploader can access employee document."""
        employee = Employee.objects.create(
            institution=self.school,
            employee_number="EMP-001",
            teacher=self.teacher,
            primary_campus=self.campus,
        )
        doc = EmployeeDocument.objects.create(
            employee=employee,
            campus=self.campus,
            file="hr/documents/test.pdf",
            uploaded_by=self.teacher_user,
        )
        client = self._as(self.teacher_user)

        response = self._get_media(client, "hr/documents/test.pdf")

        self.assertEqual(response.status_code, 200)

    def test_employee_document_manager_access(self):
        """Manager can access employee document."""
        employee = Employee.objects.create(
            institution=self.school,
            employee_number="EMP-001",
            teacher=self.teacher,
            primary_campus=self.campus,
        )
        doc = EmployeeDocument.objects.create(
            employee=employee,
            campus=self.campus,
            file="hr/documents/test.pdf",
            uploaded_by=self.admin_user,
        )
        client = self._as(self.manager_user)

        response = self._get_media(client, "hr/documents/test.pdf")

        self.assertEqual(response.status_code, 200)

    def test_profile_student_image_self_access(self):
        """Student can access their own profile image."""
        student_profile_path = f"profiles/students/{self.student.pk}/photo.jpg"
        client = self._as(self.student_user)

        response = self._get_media(client, student_profile_path)

        self.assertEqual(response.status_code, 200)

    def test_profile_student_image_parent_access(self):
        """Parent can access their child's profile image."""
        student_profile_path = f"profiles/students/{self.student.pk}/photo.jpg"
        client = self._as(self.parent_user)

        response = self._get_media(client, student_profile_path)

        self.assertEqual(response.status_code, 200)

    def test_profile_student_image_teacher_access(self):
        """Teacher of the student can access profile image."""
        student_profile_path = f"profiles/students/{self.student.pk}/photo.jpg"
        client = self._as(self.teacher_user)

        response = self._get_media(client, student_profile_path)

        self.assertEqual(response.status_code, 200)

    def test_profile_student_image_manager_access(self):
        """Manager can access student profile image."""
        student_profile_path = f"profiles/students/{self.student.pk}/photo.jpg"
        client = self._as(self.manager_user)

        response = self._get_media(client, student_profile_path)

        self.assertEqual(response.status_code, 200)

    def test_profile_student_image_manager_cannot_cross_campus(self):
        other_campus = Campus.objects.create(school=self.school, name="Other Campus")
        self.student.primary_campus = other_campus
        self.student.save(update_fields=["primary_campus"])

        response = self._get_media(
            self._as(self.manager_user), self.student.photo.name
        )
        self.assertEqual(response.status_code, 404)

    def test_profile_image_requires_exact_database_file_match(self):
        path = os.path.join(TEST_MEDIA_ROOT, "profiles/students/unlinked.jpg")
        with open(path, "wb") as file:
            file.write(self.test_image_bytes)

        response = self._get_media(self._as(self.manager_user), "profiles/students/unlinked.jpg")
        self.assertEqual(response.status_code, 404)

    def test_profile_image_uses_model_upload_path(self):
        path = os.path.join(TEST_MEDIA_ROOT, "profiles/students/photo.jpg")
        with open(path, "wb") as file:
            file.write(self.test_image_bytes)
        self.student.photo.name = "profiles/students/photo.jpg"
        self.student.save(update_fields=["photo"])

        response = self._get_media(self._as(self.student_user), self.student.photo.name)
        self.assertEqual(response.status_code, 200)

    def test_profile_student_image_cross_campus_denied(self):
        """Teacher from different campus cannot access student profile."""
        campus_b = Campus.objects.create(school=self.school, name="Campus B")
        teacher_b = Teacher.objects.create(
            institution=self.school,
            employee_number="TCH-002",
            first_name="Bob",
            last_name="Teacher",
            gender="male",
            primary_campus=campus_b,
        )
        teacher_b_user = make_user("teacher_b", Role.TEACHER, self.school)
        teacher_b_user.teacher_profile = teacher_b
        teacher_b_user.save()

        student_profile_path = f"profiles/students/{self.student.pk}/photo.jpg"
        client = self._as(teacher_b_user)

        response = self._get_media(client, student_profile_path)

        self.assertEqual(response.status_code, 404)

    def test_profile_teacher_image_self_access(self):
        """Teacher can access their own profile image."""
        teacher_profile_path = f"profiles/teachers/{self.teacher.pk}/photo.jpg"
        client = self._as(self.teacher_user)

        response = self._get_media(client, teacher_profile_path)

        self.assertEqual(response.status_code, 200)

    def test_profile_teacher_image_manager_access(self):
        """Manager can access teacher profile image."""
        teacher_profile_path = f"profiles/teachers/{self.teacher.pk}/photo.jpg"
        client = self._as(self.manager_user)

        response = self._get_media(client, teacher_profile_path)

        self.assertEqual(response.status_code, 200)

    def test_profile_staff_image_self_access(self):
        """Staff can access their own profile image."""
        staff_profile_path = f"profiles/staff/{self.staff.pk}/photo.jpg"
        client = self._as(self.manager_user)

        response = self._get_media(client, staff_profile_path)

        self.assertEqual(response.status_code, 200)

    def test_public_branding_image_access_without_auth(self):
        """Branding images are accessible without authentication."""
        client = APIClient()  # NO auth
        response = self._get_media(client, "school/branding/logo.png")

        self.assertEqual(response.status_code, 200)

    def test_public_branding_non_image_denied(self):
        """Non-image files under branding prefix are denied."""
        txt_path = os.path.join(TEST_MEDIA_ROOT, "school/branding/readme.txt")
        with open(txt_path, "wb") as f:
            f.write(b"text file")

        client = APIClient()
        response = self._get_media(client, "school/branding/readme.txt")

        self.assertEqual(response.status_code, 404)

    def test_non_existent_file_404(self):
        """Non-existent files return 404."""
        client = self._as(self.student_user)
        response = self._get_media(client, "students/documents/doesnotexist.pdf")
        self.assertEqual(response.status_code, 404)
