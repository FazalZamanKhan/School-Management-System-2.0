import json
from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.accounts.test_access import make_user
from apps.accounts.models import InstitutionMembership, Role, RoleAssignment, User
from apps.dashboard.views import dashboard_overview
from apps.schools.models import AcademicUnit, AcademicYear, Campus, Class, School, Section

from .models import (
    AdmissionApplication,
    AcademicHistory,
    Guardian,
    Enrollment,
    Student,
    StudentGuardian,
    StudentLeaveRequest,
    StudentLifecycleEvent,
    Inquiry,
    TransferCertificate,
)
from .views import StudentListCreateView


class StudentLifecycleModelTests(TestCase):
	def setUp(self):
		self.school = School.objects.create(name="Test School")
		self.campus = Campus.objects.create(school=self.school, name="Main Campus")
		unit = AcademicUnit.objects.create(campus=self.campus, name="Primary")
		self.class_obj = Class.objects.create(unit=unit, name="Grade 1")
		self.section = Section.objects.create(class_obj=self.class_obj, name="A")
		self.year = AcademicYear.objects.create(
			school=self.school,
			name="2026-2027",
			start_date=date(2026, 8, 1),
			end_date=date(2027, 7, 31),
		)
		self.guardian = Guardian.objects.create(
			name="Test Parent",
			relationship="Father",
			phone="03000000000",
		)
		self.student = Student.objects.create(
			admission_number="ADM-001",
			first_name="Ali",
			gender="male",
			guardian=self.guardian,
		)
		self.admin = User.objects.create_user(
			username="academic-admin",
			email="academic-admin@example.com",
			password="test-password",
		)
		membership = InstitutionMembership.objects.create(
			user=self.admin,
			institution=self.school,
		)
		RoleAssignment.objects.create(
			membership=membership,
			role=Role.ADMIN,
		)

	def test_admission_application_exposes_applicant_name(self):
		application = AdmissionApplication.objects.create(
			application_number="APP-001",
			first_name="Sara",
			last_name="Khan",
			gender="female",
			guardian=self.guardian,
			campus=self.campus,
			academic_year=self.year,
			class_obj=self.class_obj,
			section=self.section,
		)

		self.assertEqual(application.applicant_name, "Sara Khan")

	def test_admission_application_rejects_wrong_section(self):
		other_class = Class.objects.create(unit=self.class_obj.unit, name="Grade 2")
		other_section = Section.objects.create(class_obj=other_class, name="A")
		application = AdmissionApplication(
			application_number="APP-002",
			first_name="Sara",
			gender="female",
			campus=self.campus,
			academic_year=self.year,
			class_obj=self.class_obj,
			section=other_section,
		)

		with self.assertRaises(ValidationError):
			application.full_clean()

	def test_student_can_have_multiple_guardians_but_not_duplicate_links(self):
		second_guardian = Guardian.objects.create(
			name="Test Mother",
			relationship="Mother",
			phone="03111111111",
		)
		StudentGuardian.objects.create(
			student=self.student,
			guardian=self.guardian,
			relationship="Father",
			is_primary=True,
		)
		StudentGuardian.objects.create(
			student=self.student,
			guardian=second_guardian,
			relationship="Mother",
		)

		self.assertEqual(self.student.guardian_links.count(), 2)
		with self.assertRaises(IntegrityError):
			StudentGuardian.objects.create(
				student=self.student,
				guardian=self.guardian,
				relationship="Father",
			)

	def test_lifecycle_event_preserves_reason_and_student(self):
		event = StudentLifecycleEvent.objects.create(
			student=self.student,
			event_type="withdrawn",
			effective_date=date(2026, 9, 1),
			reason="Family relocation",
		)

		self.assertEqual(event.student, self.student)
		self.assertEqual(event.reason, "Family relocation")

	def test_leave_request_rejects_reverse_date_range(self):
		leave = StudentLeaveRequest(
			student=self.student,
			start_date=date(2026, 9, 10),
			end_date=date(2026, 9, 9),
			reason="Medical appointment",
		)

		with self.assertRaises(ValidationError):
			leave.full_clean()

	def test_enrollment_rejects_class_from_another_campus(self):
		other_campus = Campus.objects.create(
			school=self.school,
			name="North Campus",
		)
		other_unit = AcademicUnit.objects.create(
			campus=other_campus,
			name="Secondary",
		)
		other_class = Class.objects.create(unit=other_unit, name="Grade 2")
		other_section = Section.objects.create(class_obj=other_class, name="A")
		enrollment = Enrollment(
			student=self.student,
			academic_year=self.year,
			campus=self.campus,
			class_obj=other_class,
			section=other_section,
		)

		with self.assertRaises(ValidationError):
			enrollment.full_clean()

	def test_enrollment_allows_only_one_record_per_student_and_year(self):
		Enrollment.objects.create(
			student=self.student,
			academic_year=self.year,
			campus=self.campus,
			class_obj=self.class_obj,
			section=self.section,
			roll_number="18",
		)

		with self.assertRaises(ValidationError):
			Enrollment.objects.create(
				student=self.student,
				academic_year=self.year,
				campus=self.campus,
				class_obj=self.class_obj,
				section=self.section,
			)

		self.assertEqual(
			Enrollment.objects.get(
				student=self.student,
				academic_year=self.year,
			).roll_number,
			"18",
		)

	def test_admission_application_rejects_year_from_another_school(self):
		other_school = School.objects.create(name="Other School")
		other_year = AcademicYear.objects.create(
			school=other_school,
			name="2026-2027",
			start_date=date(2026, 8, 1),
			end_date=date(2027, 7, 31),
		)
		application = AdmissionApplication(
			application_number="APP-003",
			first_name="Hamza",
			gender="male",
			campus=self.campus,
			academic_year=other_year,
			class_obj=self.class_obj,
			section=self.section,
		)

		with self.assertRaises(ValidationError):
			application.full_clean()

	def test_admission_acceptance_creates_student_guardian_link_and_enrollment(self):
		application = AdmissionApplication.objects.create(
			application_number="APP-ACCEPT-001",
			first_name="Sara",
			last_name="Khan",
			gender="female",
			guardian=self.guardian,
			campus=self.campus,
			academic_year=self.year,
			class_obj=self.class_obj,
			section=self.section,
			status="submitted",
		)
		self.client.force_login(self.admin)

		response = self.client.post(
			f"/api/students/admissions/{application.pk}/accept/",
			{"admission_number": "ADM-ACCEPT-001"},
		)

		self.assertEqual(response.status_code, 201)
		application.refresh_from_db()
		self.assertEqual(application.status, "accepted")
		student = Student.objects.get(admission_number="ADM-ACCEPT-001")
		self.assertTrue(
			StudentGuardian.objects.filter(
				student=student,
				guardian=self.guardian,
				is_primary=True,
			).exists()
		)
		self.assertTrue(
			Enrollment.objects.filter(
				student=student,
				academic_year=self.year,
				status="active",
			).exists()
		)

	def test_guardian_my_endpoint_returns_linked_parent_profile(self):
		parent = User.objects.create_user(
			username="parent-user",
			email="parent@example.com",
			password="test-password",
		)
		self.guardian.user = parent
		self.guardian.save(update_fields=["user", "updated_at"])
		membership = InstitutionMembership.objects.create(
			user=parent,
			institution=self.school,
		)
		RoleAssignment.objects.create(
			membership=membership,
			role=Role.PARENT,
		)
		self.client.force_login(parent)

		response = self.client.get("/api/students/guardians/me/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["id"], self.guardian.pk)


# =============================================================================
# STUDENT 360 TESTS
# =============================================================================

class Student360ModelTests(TestCase):
    """Test Student model methods used by Student 360."""
    
    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus = Campus.objects.create(school=self.school, name="Main Campus")
        unit = AcademicUnit.objects.create(campus=self.campus, name="Primary")
        self.class_obj = Class.objects.create(unit=unit, name="Grade 1")
        self.section = Section.objects.create(class_obj=self.class_obj, name="A")
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )
        self.guardian = Guardian.objects.create(
            name="Test Parent",
            relationship="Father",
            phone="03000000000",
        )
        self.student = Student.objects.create(
            admission_number="ADM-001",
            first_name="Ali",
            last_name="Khan",
            date_of_birth=date(2010, 1, 1),
            gender="male",
            guardian=self.guardian,
        )
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@test.edu",
            password="test-password",
        )
        membership = InstitutionMembership.objects.create(
            user=self.admin,
            institution=self.school,
        )
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.ADMIN,
        )

    def test_student_age_property(self):
        """Test student age calculation."""
        self.student.date_of_birth = date(2010, 1, 1)
        self.student.save()
        self.assertEqual(self.student.age, 16)  # Assuming current year is 2026

    def test_student_full_name_property(self):
        """Test student full name property."""
        self.student.first_name = "Ali"
        self.student.middle_name = "Ahmed"
        self.student.last_name = "Khan"
        self.assertEqual(self.student.full_name, "Ali Ahmed Khan")
        
        self.student.middle_name = ""
        self.assertEqual(self.student.full_name, "Ali Khan")

    def test_student_can_transition_to(self):
        """Test status transition validation."""
        # active -> inactive
        self.student.status = "active"
        self.assertTrue(self.student.can_transition_to("inactive"))
        
        # inactive -> active
        self.student.status = "inactive"
        self.assertTrue(self.student.can_transition_to("active"))
        
        # active -> graduated
        self.student.status = "active"
        self.assertTrue(self.student.can_transition_to("graduated"))
        
        # graduated -> anything (terminal)
        self.student.status = "graduated"
        self.assertFalse(self.student.can_transition_to("active"))
        self.assertFalse(self.student.can_transition_to("inactive"))
        self.assertFalse(self.student.can_transition_to("withdrawn"))

    def test_student_transition_status_creates_lifecycle_event(self):
        """Test that transition_status creates a lifecycle event."""
        event = self.student.transition_status("inactive", self.admin, "Medical leave")
        self.assertEqual(event.event_type, "inactive")
        self.assertEqual(event.student, self.student)
        self.assertEqual(event.reason, "Medical leave")
        self.assertEqual(event.recorded_by, self.admin)
        self.assertEqual(self.student.status, "inactive")


class Student360SerializerTests(TestCase):
    """Test Student360Serializer."""
    
    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus = Campus.objects.create(school=self.school, name="Main Campus")
        unit = AcademicUnit.objects.create(campus=self.campus, name="Primary")
        self.class_obj = Class.objects.create(unit=unit, name="Grade 1")
        self.section = Section.objects.create(class_obj=self.class_obj, name="A")
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )
        self.guardian = Guardian.objects.create(
            name="Test Parent",
            relationship="Father",
            phone="03000000000",
        )
        self.student = Student.objects.create(
            admission_number="ADM-001",
            first_name="Ali",
            last_name="Khan",
            date_of_birth=date(2010, 1, 1),
            gender="male",
            guardian=self.guardian,
        )
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@test.edu",
            password="test-password",
        )
        membership = InstitutionMembership.objects.create(
            user=self.admin,
            institution=self.school,
        )
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.ADMIN,
        )

    def test_student360_serializer_basic_fields(self):
        """Test Student360Serializer basic field serialization."""
        from apps.students.serializers import Student360Serializer
        
        serializer = Student360Serializer(self.student)
        data = serializer.data
        
        self.assertEqual(data["admission_number"], "ADM-001")
        self.assertEqual(data["first_name"], "Ali")
        self.assertEqual(data["last_name"], "Khan")
        self.assertEqual(data["full_name"], "Ali Khan")
        self.assertEqual(data["gender"], "male")
        self.assertIn("photo_url", data)
        self.assertIn("age", data)


class Student360APITests(TestCase):
    """Test Student 360 API endpoints."""
    
    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus = Campus.objects.create(school=self.school, name="Main Campus")
        unit = AcademicUnit.objects.create(campus=self.campus, name="Primary")
        self.class_obj = Class.objects.create(unit=unit, name="Grade 1")
        self.section = Section.objects.create(class_obj=self.class_obj, name="A")
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )
        self.guardian = Guardian.objects.create(
            name="Test Parent",
            relationship="Father",
            phone="03000000000",
        )
        self.student = Student.objects.create(
            admission_number="ADM-001",
            first_name="Ali",
            last_name="Khan",
            date_of_birth=date(2010, 1, 1),
            gender="male",
            guardian=self.guardian,
            institution=self.school,
        )
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@test.edu",
            password="Admin123!",
        )
        membership = InstitutionMembership.objects.create(
            user=self.admin,
            institution=self.school,
        )
        RoleAssignment.objects.create(
            membership=membership,
            role=Role.ADMIN,
        )
        self.client = APIClient()

    def test_student_360_requires_admin(self):
        """Test that Student 360 endpoint requires admin role."""
        self.client.post("/api/auth/csrf/", {}, format="json")
        self.client.post("/api/auth/login/", {
            "username": "admin",
            "password": "Admin123!",
        }, format="json")
        
        response = self.client.get(f"/api/students/{self.student.pk}/360/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["admission_number"], "ADM-001")
        self.assertEqual(data["full_name"], "Ali Khan")
        self.assertIn("current_enrollment", data)
        self.assertIn("enrollments", data)
        self.assertIn("academic_history", data)
        self.assertIn("attendance_summary", data)
        self.assertIn("exam_results", data)
        self.assertIn("invoices", data)
        self.assertIn("payments", data)
        self.assertIn("fee_balance", data)
        self.assertIn("book_issues", data)
        self.assertIn("transport_assignment", data)
        self.assertIn("discipline_incidents", data)
        self.assertIn("discipline_summary", data)
        self.assertIn("documents", data)
        self.assertIn("transfer_certificates", data)

    def test_student_360_teacher_denied(self):
        """Test that Student 360 endpoint denies teacher access to unrelated students."""
        teacher = User.objects.create_user(username="teacher", email="teacher@test.edu", password="Test123!")
        membership = InstitutionMembership.objects.create(user=teacher, institution=self.school)
        RoleAssignment.objects.create(membership=membership, role=Role.TEACHER)

        self.client.post("/api/auth/logout/")
        self.client.post("/api/auth/csrf/", {}, format="json")
        self.client.post("/api/auth/login/", {
            "username": "teacher",
            "password": "Test123!",
        }, format="json")
        
        response = self.client.get(f"/api/students/{self.student.pk}/360/")
        self.assertEqual(response.status_code, 403)

    def test_student_360_parent_access_own_child(self):
        """Test that parent can access their own child's 360."""
        parent = User.objects.create_user(username="parent", email="parent@test.edu", password="Parent123!")
        membership = InstitutionMembership.objects.create(user=parent, institution=self.school)
        RoleAssignment.objects.create(membership=membership, role=Role.PARENT)
        
        # Link parent to student
        StudentGuardian.objects.create(
            student=self.student,
            guardian=self.guardian,
            relationship="Father",
            is_primary=True,
        )
        self.guardian.user = parent
        self.guardian.save()
        
        self.client.post("/api/auth/csrf/", {}, format="json")
        self.client.post("/api/auth/login/", {
            "username": "parent",
            "password": "Parent123!",
        }, format="json")
        
        response = self.client.get(f"/api/students/{self.student.pk}/360/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["admission_number"], "ADM-001")

    def test_student_360_student_access_own_profile(self):
        """Test that student can access their own 360."""
        self.student.user = self.student.user or User.objects.create_user(
            username="student", email="student@test.edu", password="Student123!"
        )
        self.student.save()
        
        membership = InstitutionMembership.objects.create(
            user=self.student.user, institution=self.school
        )
        RoleAssignment.objects.create(membership=membership, role=Role.STUDENT)
        
        self.client.post("/api/auth/csrf/", {}, format="json")
        self.client.post("/api/auth/login/", {
            "username": "student",
            "password": "Student123!",
        }, format="json")
        
        response = self.client.get(f"/api/students/{self.student.pk}/360/")
        self.assertEqual(response.status_code, 200)

    def test_student_360_denied_other_student(self):
        """Test that student cannot access another student's 360."""
        other_student = Student.objects.create(
            admission_number="ADM-002",
            first_name="Other",
            last_name="Student",
            gender="female",
            guardian=self.guardian,
            institution=self.school,
        )
        
        self.student.user = User.objects.create_user(
            username="student", email="student@test.edu", password="Student123!"
        )
        self.student.save()
        membership = InstitutionMembership.objects.create(
            user=self.student.user, institution=self.school
        )
        RoleAssignment.objects.create(membership=membership, role=Role.STUDENT)
        
        self.client.post("/api/auth/csrf/", {}, format="json")
        self.client.post("/api/auth/login/", {
            "username": "student",
            "password": "Student123!",
        }, format="json")
        
        response = self.client.get(f"/api/students/{other_student.pk}/360/")
        self.assertEqual(response.status_code, 403)

    def test_student_360_unauthenticated_denied(self):
        """Test that unauthenticated access is denied."""
        response = self.client.get(f"/api/students/{self.student.pk}/360/")
        self.assertEqual(response.status_code, 403)


class StudentCreationInstitutionRegressionTests(TestCase):
    """Regression: students created through the API must be stamped with the
    active institution so the dashboard overview includes them, and campus
    choices must stay inside the active school (mirrors the teacher fix).
    """

    def setUp(self):
        self.school_a = School.objects.create(name="School A")
        self.campus_a = Campus.objects.create(
            school=self.school_a, name="Campus A"
        )
        self.school_b = School.objects.create(name="School B")
        self.campus_b = Campus.objects.create(
            school=self.school_b, name="Campus B"
        )
        self.admin_a = make_user("admin_a", "admin", self.school_a)
        self.admin_b = make_user("admin_b", "admin", self.school_b)

    def _make_request(self, method, path, user, institution, data=None):
        factory = getattr(APIRequestFactory(), method)
        django_request = factory(
            path,
            data=data,
            format="json" if data is not None else None,
        )
        force_authenticate(django_request, user)
        if institution is not None:
            django_request.institution = institution
        return django_request

    def _create(self, user, institution, payload=None):
        data = {
            "first_name": "Zara",
            "last_name": "Shah",
            "gender": "female",
            "guardian_name": "Zara Guardian",
            "guardian_relationship": "Mother",
            "guardian_phone": "03000000111",
            "create_account": False,
        }
        if payload:
            data.update(payload)
        request = self._make_request(
            "post",
            "/api/students/",
            user,
            institution,
            data=data,
        )
        response = StudentListCreateView.as_view()(request)
        response.render()
        return response

    def _dashboard_total_students(self, user, institution):
        request = self._make_request(
            "get", "/api/dashboard/overview/", user, institution
        )
        response = dashboard_overview(request)
        return json.loads(response.content)["students"]["total"]

    def test_created_student_is_stamped_with_institution(self):
        response = self._create(self.admin_a, self.school_a)
        self.assertEqual(response.status_code, 201)
        student = Student.objects.get(pk=json.loads(response.content)["id"])
        self.assertEqual(student.institution_id, self.school_a.id)

    def test_created_student_increases_dashboard_overview(self):
        before = self._dashboard_total_students(self.admin_a, self.school_a)
        response = self._create(self.admin_a, self.school_a)
        self.assertEqual(response.status_code, 201)
        after = self._dashboard_total_students(self.admin_a, self.school_a)
        self.assertEqual(after, before + 1)

    def test_created_student_not_counted_for_other_school(self):
        self._create(self.admin_a, self.school_a)
        self.assertEqual(
            self._dashboard_total_students(self.admin_a, self.school_a),
            1,
        )
        self.assertEqual(
            self._dashboard_total_students(self.admin_b, self.school_b),
            0,
        )

    def test_create_student_requires_active_institution(self):
        response = self._create(self.admin_a, None)
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertIn("institution", body)

    def test_primary_campus_must_belong_to_active_school(self):
        response = self._create(
            self.admin_a,
            self.school_a,
            payload={"primary_campus": self.campus_b.id},
        )
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertIn("primary_campus", body)

    def test_student_api_rejects_future_date_of_birth(self):
        response = self._create(
            self.admin_a,
            self.school_a,
            payload={"date_of_birth": "2030-02-01"},
        )
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertIn("date_of_birth", body)

    def test_student_api_rejects_admission_date_before_birth(self):
        response = self._create(
            self.admin_a,
            self.school_a,
            payload={
                "date_of_birth": "2015-02-01",
                "admission_date": "2010-02-01",
            },
        )
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertIn("admission_date", body)
