from rest_framework.test import APITestCase
from apps.accounts.models import Role, StaffProfile
from apps.accounts.test_access import make_user
from apps.ai.helpers import make_school, make_structure, make_student
from apps.events.models import Event, EventAudience


class EventAudienceVisibilityTests(APITestCase):
    def setUp(self):
        self.school = make_school("Event audiences", "EVENT-AUDIENCE")
        self.structure = make_structure(self.school)
        self.student = make_student(self.school, self.structure)
        self.student_user = make_user("event-student", Role.STUDENT, self.school)
        self.student.user = self.student_user
        self.student.membership = self.student_user.memberships.get(institution=self.school)
        self.student.primary_campus = self.structure["campus"]
        self.student.save()
        self.guard = make_user("event-guard", Role.GUARD, self.school)
        StaffProfile.objects.create(user=self.guard, institution=self.school, primary_campus=self.structure["campus"], employee_number="EG", first_name="Event", last_name="Guard", gender="male")
        self.admin = make_user("event-admin", Role.ADMIN, self.school)
        self.public = self.event("Unrestricted")
        self.students = self.event("Students", "students")
        self.staff = self.event("Staff", "staff")
        self.teacher_only = self.event("Teachers", "teachers")
        self.guard_only = self.event("Guard role", "role", role="guard")
        self.class_event = self.event("Class", "class", class_obj=self.structure["class_obj"])
        self.draft = self.event("Draft", status="draft")
        foreign = make_school("Foreign audience", "FOREIGN-EVENT-AUD")
        self.foreign = self.event("Foreign", school=foreign)

    def event(self, title, audience=None, status="published", school=None, **kwargs):
        event = Event.objects.create(school=school or self.school, title=title, start_datetime="2026-12-01T09:00:00Z", end_datetime="2026-12-01T15:00:00Z", status=status)
        if audience:
            EventAudience.objects.create(event=event, audience_type=audience, **kwargs)
        return event

    def ids(self, user):
        self.client.force_login(user)
        response = self.client.get("/api/events/")
        self.assertEqual(response.status_code, 200)
        return {row["id"] for row in response.json()}

    def test_guard_sees_only_public_staff_and_guard_targeted_events(self):
        self.assertEqual(self.ids(self.guard), {self.public.pk, self.staff.pk, self.guard_only.pk})
        self.assertEqual(self.client.get(f"/api/events/{self.students.pk}/").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/events/{self.students.pk}/", {"title": "Changed"}, format="json").status_code, 404)

    def test_student_sees_public_student_and_own_class_audiences(self):
        self.assertEqual(self.ids(self.student_user), {self.public.pk, self.students.pk, self.class_event.pk})

    def test_admin_manages_all_own_school_audiences_but_not_foreign(self):
        ids = self.ids(self.admin)
        self.assertIn(self.students.pk, ids)
        self.assertIn(self.draft.pk, ids)
        self.assertNotIn(self.foreign.pk, ids)

    def test_multiple_matching_audiences_do_not_duplicate_rows(self):
        EventAudience.objects.create(event=self.staff, audience_type="role", role="guard")
        self.assertEqual(self.ids(self.guard), {self.public.pk, self.staff.pk, self.guard_only.pk})

    def test_rsvp_uses_same_audience_restrictions(self):
        self.client.force_login(self.guard)
        response = self.client.post(f"/api/events/{self.students.pk}/rsvp/", {"response": "yes"}, format="json")
        self.assertEqual(response.status_code, 404)
        self.client.force_login(self.student_user)
        response = self.client.post(f"/api/events/{self.students.pk}/rsvp/", {"response": "yes"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.students.rsvps.count(), 1)
