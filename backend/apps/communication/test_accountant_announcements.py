from rest_framework.test import APITestCase
from apps.accounts.models import Role, StaffProfile
from apps.accounts.test_access import make_user
from apps.communication.models import Announcement
from apps.schools.models import School, Campus


class AccountantAnnouncementTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Announcements A", code="ANN-ACCT-A")
        self.main = Campus.objects.create(school=self.school, name="Main")
        self.north = Campus.objects.create(school=self.school, name="North")
        actor = make_user("announcement-accountant", Role.ACCOUNTANT, self.school)
        StaffProfile.objects.create(user=actor, institution=self.school, primary_campus=self.main, employee_number="ANN", first_name="Notice", last_name="Accountant", gender="male")
        self.client.force_login(actor)
        self.schoolwide = Announcement.objects.create(institution=self.school, title="School-wide", message="Everyone", status="published")
        self.own = Announcement.objects.create(institution=self.school, campus=self.main, title="Main", message="Main only", status="published", audience_roles=["accountant"])
        self.draft = Announcement.objects.create(institution=self.school, title="Draft", message="Draft", status="draft")
        self.teacher_only = Announcement.objects.create(institution=self.school, title="Teachers", message="Teachers only", status="published", audience_roles=["teacher"])
        self.north_only = Announcement.objects.create(institution=self.school, campus=self.north, title="North", message="North only", status="published")
        foreign_school = School.objects.create(name="Foreign announcements", code="FOREIGN-ANN-ACCT")
        self.foreign = Announcement.objects.create(institution=foreign_school, title="Foreign", message="Foreign only", status="published")

    def test_published_unrestricted_and_accountant_notices_are_visible(self):
        response = self.client.get("/api/communication/announcements/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["id"] for row in response.json()["results"]}, {self.schoolwide.pk, self.own.pk})

    def test_direct_detail_respects_status_audience_campus_and_school(self):
        for notice in (self.draft, self.teacher_only, self.north_only, self.foreign):
            with self.subTest(notice=notice.title):
                self.assertEqual(self.client.get(f"/api/communication/announcements/{notice.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/communication/announcements/{self.schoolwide.pk}/").status_code, 200)
