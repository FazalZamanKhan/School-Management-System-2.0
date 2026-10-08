from datetime import date

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Role
from apps.accounts.test_access import make_user
from apps.schools.models import AcademicUnit, AcademicYear, Campus, Class, School

from .models import Inquiry
from .views import InquiryListCreateView


class InquiryCreationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Inquiry School")
        self.campus = Campus.objects.create(school=self.school, name="Main")
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026-27",
            start_date=date(2026, 8, 1), end_date=date(2027, 7, 31),
        )
        unit = AcademicUnit.objects.create(campus=self.campus, name="Primary")
        self.class_obj = Class.objects.create(unit=unit, name="Grade 1")
        self.user = make_user("inquiry-admin", Role.ADMIN, self.school)

    def create_inquiry(self, data):
        request = APIRequestFactory().post("/api/students/inquiries/", data, format="json")
        force_authenticate(request, self.user)
        request.institution = self.school
        response = InquiryListCreateView.as_view()(request)
        response.render()
        return response

    def test_minimal_inquiry_gets_server_generated_number(self):
        response = self.create_inquiry({"first_name": "QAInquiryMinimal"})
        self.assertEqual(response.status_code, 201, response.content)
        inquiry = Inquiry.objects.get()
        self.assertEqual(inquiry.institution, self.school)
        self.assertTrue(inquiry.inquiry_number.startswith("INQ-"))
        self.assertEqual(response.data["inquiry_number"], inquiry.inquiry_number)

    def test_inquiry_with_optional_fields_and_school_choices(self):
        response = self.create_inquiry({
            "first_name": "Ayesha", "phone": "03000000000", "guardian_phone": "",
            "campus": self.campus.pk, "academic_year": self.year.pk,
            "class_obj": self.class_obj.pk,
        })
        self.assertEqual(response.status_code, 201, response.content)

    def test_foreign_school_choices_are_rejected(self):
        other = School.objects.create(name="Other Inquiry School")
        other_campus = Campus.objects.create(school=other, name="Other")
        response = self.create_inquiry({"first_name": "Ayesha", "campus": other_campus.pk})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Inquiry.objects.exists())
