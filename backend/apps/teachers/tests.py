import json
from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.test_access import make_user
from apps.schools.models import AcademicUnit, AcademicYear, Campus, Class, Section, School, Subject

from .models import Teacher, TeacherAssignment
from .views import TeacherDetailView, TeacherListCreateView


class TeacherAssignmentModelTests(TestCase):
    def setUp(self):
        school = School.objects.create(name="Test School")
        campus = Campus.objects.create(school=school, name="Main Campus")
        unit = AcademicUnit.objects.create(campus=campus, name="Primary")
        class_obj = Class.objects.create(unit=unit, name="Grade 1")
        section = Section.objects.create(class_obj=class_obj, name="A")
        year = AcademicYear.objects.create(
            school=school,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )
        teacher = Teacher.objects.create(
            employee_number="T-001",
            first_name="Ayesha",
            last_name="Khan",
            gender="female",
        )
        subject = Subject.objects.create(name="English", code="ENG-TEACHER")
        self.assignment_data = {
            "teacher": teacher,
            "campus": campus,
            "class_obj": class_obj,
            "section": section,
            "subject": subject,
            "academic_year": year,
        }

    def test_assignment_rejects_class_from_another_campus(self):
        other_campus = Campus.objects.create(school=self.assignment_data["campus"].school, name="North Campus")
        other_unit = AcademicUnit.objects.create(campus=other_campus, name="Secondary")
        other_class = Class.objects.create(unit=other_unit, name="Grade 2")
        other_section = Section.objects.create(class_obj=other_class, name="A")
        assignment_data = self.assignment_data.copy()
        assignment_data["class_obj"] = other_class
        assignment_data["section"] = other_section
        assignment = TeacherAssignment(**assignment_data)

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_duplicate_assignment_is_rejected(self):
        TeacherAssignment.objects.create(**self.assignment_data)

        with self.assertRaises(ValidationError):
            TeacherAssignment.objects.create(**self.assignment_data)


class TeacherAPIRegressionTests(TestCase):
    """Regression: teachers created through the API must be stamped with the
    active institution so the list/detail querysets include them, and campus
    choices must stay inside the active school.
    """

    def setUp(self):
        self.school_a = School.objects.create(name="School A")
        self.campus_a = Campus.objects.create(
            school=self.school_a,
            name="Campus A",
        )
        self.school_b = School.objects.create(name="School B")
        self.campus_b = Campus.objects.create(
            school=self.school_b,
            name="Campus B",
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
            "employee_number": "T-REG-001",
            "create_account": False,
        }
        if payload:
            data.update(payload)
        request = self._make_request(
            "post",
            "/api/teachers/",
            user,
            institution,
            data=data,
        )
        response = TeacherListCreateView.as_view()(request)
        response.render()
        return response

    def _list(self, user, institution):
        request = self._make_request(
            "get", "/api/teachers/", user, institution
        )
        response = TeacherListCreateView.as_view()(request)
        response.render()
        data = json.loads(response.content)
        return response, data["results"]

    def test_create_teacher_is_visible_in_list_and_detail(self):
        response = self._create(self.admin_a, self.school_a)
        self.assertEqual(response.status_code, 201)
        teacher_id = json.loads(response.content)["id"]

        _, results = self._list(self.admin_a, self.school_a)
        self.assertIn(teacher_id, [t["id"] for t in results])

        search_request = self._make_request(
            "get",
            "/api/teachers/?search=Zara",
            self.admin_a,
            self.school_a,
        )
        search_response = TeacherListCreateView.as_view()(search_request)
        search_response.render()
        search_data = json.loads(search_response.content)
        self.assertIn(
            teacher_id,
            [t["id"] for t in search_data["results"]],
        )

        detail_request = self._make_request(
            "get",
            f"/api/teachers/{teacher_id}/",
            self.admin_a,
            self.school_a,
        )
        detail_response = TeacherDetailView.as_view()(
            detail_request, pk=teacher_id
        )
        detail_response.render()
        self.assertEqual(detail_response.status_code, 200)

    def test_create_teacher_requires_active_institution(self):
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

    def test_teacher_api_rejects_symbol_only_names(self):
        response = self._create(
            self.admin_a,
            self.school_a,
            payload={
                "first_name": "!!!",
                "last_name": "@@@",
            },
        )
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertIn("first_name", body)
        self.assertIn("last_name", body)

    def test_teacher_is_not_visible_to_other_schools(self):
        response = self._create(self.admin_a, self.school_a)
        self.assertEqual(response.status_code, 201)
        teacher_id = json.loads(response.content)["id"]

        _, results = self._list(self.admin_b, self.school_b)
        self.assertNotIn(teacher_id, [t["id"] for t in results])

        detail_request = self._make_request(
            "get",
            f"/api/teachers/{teacher_id}/",
            self.admin_b,
            self.school_b,
        )
        detail_response = TeacherDetailView.as_view()(
            detail_request, pk=teacher_id
        )
        detail_response.render()
        self.assertEqual(detail_response.status_code, 404)

    def test_update_preserves_institution_and_delete_removes_from_list(self):
        response = self._create(self.admin_a, self.school_a)
        teacher_id = json.loads(response.content)["id"]

        patch_request = self._make_request(
            "patch",
            f"/api/teachers/{teacher_id}/",
            self.admin_a,
            self.school_a,
            data={"designation": "Head Teacher"},
        )
        patch_response = TeacherDetailView.as_view()(
            patch_request, pk=teacher_id
        )
        patch_response.render()
        self.assertEqual(patch_response.status_code, 200)

        delete_request = self._make_request(
            "delete",
            f"/api/teachers/{teacher_id}/",
            self.admin_a,
            self.school_a,
        )
        delete_response = TeacherDetailView.as_view()(
            delete_request, pk=teacher_id
        )
        delete_response.render()
        self.assertEqual(delete_response.status_code, 204)

        _, results = self._list(self.admin_a, self.school_a)
        self.assertNotIn(teacher_id, [t["id"] for t in results])

    def test_detail_fails_closed_without_active_institution(self):
        response = self._create(self.admin_a, self.school_a)
        self.assertEqual(response.status_code, 201)
        teacher_id = json.loads(response.content)["id"]

        non_manager = make_user("t_nonmgr", "teacher", self.school_a)

        for user in (self.admin_a, non_manager):
            request = self._make_request(
                "get",
                f"/api/teachers/{teacher_id}/",
                user,
                None,
            )
            detail_response = TeacherDetailView.as_view()(
                request, pk=teacher_id
            )
            detail_response.render()
            self.assertEqual(detail_response.status_code, 404)
