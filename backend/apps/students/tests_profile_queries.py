"""Profile query performance for StudentListCreateView"""
import time
from django.test import TestCase
from django.db import connection, reset_queries
from django.test import RequestFactory
from django.contrib.auth import get_user_model

from apps.students.views import StudentListCreateView
from apps.accounts.managers import get_current_institution

User = get_user_model()


class StudentQueryProfileTest(TestCase):
    databases = {'default'}

    def setUp(self):
        # Create test data
        from apps.accounts.models import InstitutionMembership, Role, assign_role_safely
        from apps.schools.models import School, AcademicYear, Campus, AcademicUnit, Class, Section
        from apps.students.models import Student, Enrollment, Guardian
        
        # Create school
        school = School.objects.create(name="Test School", code="TS", status="active")
        
        # Create campus
        campus = Campus.objects.create(school=school, name="Main Campus", status="active")
        
        # Create academic year
        from datetime import date
        ay = AcademicYear.objects.create(school=school, name="2026-2027", start_date=date(2026, 1, 1), end_date=date(2027, 12, 31), status="active")
        
        # Create class and section
        academic_unit = AcademicUnit.objects.create(campus=campus, name="Primary")
        unit = Class.objects.create(unit=academic_unit, name="Grade 1", status="active")
        section = Section.objects.create(class_obj=unit, name="A", status="active")
        
        # Create admin user
        self.admin = User.objects.create_superuser('Flora', 'flora@test.com', 'testpass123')
        
        # Create institution membership
        membership = InstitutionMembership.objects.create(user=self.admin, institution=school, status="active")
        assign_role_safely(membership, Role.SUPER_ADMIN)

        guardian = Guardian.objects.create(
            institution=school, name="Test Parent", relationship="Parent", phone="0300000000"
        )
        
        # Create test students
        for i in range(5):
            student = Student.objects.create(
                institution=school,
                admission_number=f"TS-ST-{i:04d}",
                first_name=f"Student{i}",
                last_name="Test",
                gender="male",
                date_of_birth=date(2015, 1, 1),
                phone="0300000000",
                address="Test Address",
                status="active",
                admission_date=date(2026, 1, 1),
                primary_campus=campus,
                guardian=guardian,
            )
            # Create enrollment
            Enrollment.objects.create(
                student=student,
                academic_year=ay,
                campus=campus,
                class_obj=unit,
                section=section,
                status="active",
            )
        
        # Set up institution context
        from apps.accounts.managers import set_current_institution
        set_current_institution(school)
        self.addCleanup(set_current_institution, None)

    def test_profile_student_list_queries(self):
        """Profile the number of queries for student list"""
        from apps.accounts.managers import get_current_institution
        
        admin = self.admin
        inst = get_current_institution()
        self.assertIsNotNone(inst, "Institution not found")

        from rest_framework.request import Request
        request = Request(RequestFactory().get('/api/students/'))
        request.user = admin
        request.institution = inst

        # Warm up
        view = StudentListCreateView()
        view.request = request
        queryset = view.get_queryset()
        list(queryset)

        # Now profile
        reset_queries()
        t0 = time.time()
        view = StudentListCreateView()
        view.request = request
        queryset = view.get_queryset()
        results = list(queryset)
        self.assertEqual(len(results), 5)
        dt = time.time() - t0

        print("\n=== Query Profile ===")
        print("Results:", len(results))
        print("Python time:", dt)
        print("DB queries:", len(connection.queries))
        total_db = sum(float(q['time']) for q in connection.queries)
        print("Total DB time:", total_db)

        for i, q in enumerate(connection.queries):
            t = float(q['time'])
            sql = q['sql'][:200]
            print(f"  {t:.4f}s: {sql[:200]}...")

        print("Total DB time:", total_db)

        # Should be fast
        self.assertLess(total_db, 0.5, "DB queries too slow")
