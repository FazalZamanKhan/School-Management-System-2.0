from datetime import date, time

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Role
from apps.accounts.test_access import make_user
from apps.schools.models import AcademicUnit, AcademicYear, Campus, Class, School, Section

from .generate_views import TimetableGenerateView
from .models import Period


class TimetableGenerateApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Timetable School")
        self.campus = Campus.objects.create(school=self.school, name="Main")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026-27", status="active",
            start_date=date(2026, 8, 1), end_date=date(2027, 7, 31),
        )
        unit = AcademicUnit.objects.create(campus=self.campus, name="Primary")
        self.class_obj = Class.objects.create(unit=unit, name="Grade 1")
        self.section = Section.objects.create(class_obj=self.class_obj, name="A")
        self.user = make_user("timetable-api-admin", Role.ADMIN, self.school)

    def generate(self, data):
        request = APIRequestFactory().post(
            "/api/timetable/generate/",
            {"campus": self.campus.pk, "confirm": True, **data},
            format="json",
        )
        force_authenticate(request, self.user)
        request.institution = self.school
        response = TimetableGenerateView.as_view()(request)
        response.render()
        return response

    def test_foreign_periods_do_not_count_as_school_periods(self):
        other = School.objects.create(name="Other Timetable School")
        Period.objects.create(
            institution=other, name="Foreign period", number=1,
            start_time=time(8, 0), end_time=time(8, 45),
        )
        response = self.generate({"lessons_per_subject": 5})
        self.assertEqual(response.status_code, 400)
        self.assertIn("No teaching periods configured for this school", response.data["detail"])

    def test_lesson_count_outside_declared_range_is_rejected(self):
        for value in (0, 21, "abc", 1.5):
            with self.subTest(value=value):
                response = self.generate({"lessons_per_subject": value})
                self.assertEqual(response.status_code, 400)
                self.assertIn("Lessons per subject", response.data["detail"])

    def test_class_and_section_use_the_selected_campus_path(self):
        response = self.generate({
            "class_id": self.class_obj.pk,
            "section_id": self.section.pk,
            "lessons_per_subject": 5,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("No teaching periods configured", response.data["detail"])
