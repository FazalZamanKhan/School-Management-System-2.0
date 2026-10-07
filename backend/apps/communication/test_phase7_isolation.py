"""Communication Phase 7 isolation tests."""

from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.schools.models import (
    AcademicUnit,
    AcademicYear,
    Campus,
    Class,
    School,
    Section,
    Subject,
    SubjectOffering,
)
from apps.students.models import Enrollment, Student
from apps.teachers.models import Teacher
from apps.communication.models import (
    Announcement,
    Message,
    MessageTemplate,
    Notification,
    EmailLog,
    SMSLog,
)

from apps.accounts.test_access import make_user


def _make_campus_admin(username, campus, employee_number):
    user = make_user(username, Role.CAMPUS_ADMIN, campus.school, campus=campus)
    from apps.accounts.models import StaffProfile
    StaffProfile.objects.create(
        user=user,
        employee_number=employee_number,
        first_name="Campus",
        last_name="Admin",
        gender="male",
        primary_campus=campus,
    )
    return user


class CommunicationPhase7Base(TestCase):
    """Two-school fixture for communication isolation tests."""

    PASSWORD = "TestPass123!"

    def setUp(self):
        self.school_a = School.objects.create(name="Northfield Academy")
        self.school_b = School.objects.create(name="Southfield Academy")

        self.campus_a1 = Campus.objects.create(
            school=self.school_a, name="Campus A1"
        )
        self.campus_a2 = Campus.objects.create(
            school=self.school_a, name="Campus A2"
        )
        self.campus_b1 = Campus.objects.create(
            school=self.school_b, name="Campus B1"
        )

        self.unit_a1 = AcademicUnit.objects.create(
            campus=self.campus_a1, name="Lower A1"
        )
        self.unit_a2 = AcademicUnit.objects.create(
            campus=self.campus_a2, name="Lower A2"
        )
        self.unit_b1 = AcademicUnit.objects.create(
            campus=self.campus_b1, name="Lower B1"
        )

        self.class_a1 = Class.objects.create(unit=self.unit_a1, name="Grade 1A1")
        self.class_a2 = Class.objects.create(unit=self.unit_a2, name="Grade 1A2")
        self.class_b1 = Class.objects.create(unit=self.unit_b1, name="Grade 1B1")

        self.section_a1 = Section.objects.create(
            class_obj=self.class_a1, name="A1"
        )
        self.section_a2 = Section.objects.create(
            class_obj=self.class_a2, name="A2"
        )
        self.section_b1 = Section.objects.create(
            class_obj=self.class_b1, name="B1"
        )

        self.year = AcademicYear.objects.create(
            school=self.school_a,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )

        self.super_admin = make_user(
            "sadmin", Role.SUPER_ADMIN, self.school_a
        )
        self.campus_admin_a1 = _make_campus_admin(
            "cadmin-a1", self.campus_a1, "STF-A1-001"
        )
        self.campus_admin_a2 = _make_campus_admin(
            "cadmin-a2", self.campus_a2, "STF-A2-001"
        )
        self.campus_admin_b1 = _make_campus_admin(
            "cadmin-b1", self.campus_b1, "STF-B1-001"
        )

        self.client = APIClient()

    def _as(self, user):
        self.client.force_authenticate(user=None)
        self.assertTrue(
            self.client.login(
                username=user.username,
                password=self.PASSWORD,
            ), f"login failed for {user.username}"
        )
        self.client.force_authenticate(user=user)
        return self.client

    def _body(self, response):
        data = response.json()
        if isinstance(data, list):
            return data
        return data.get("results", data)


class AnnouncementIsolationTests(CommunicationPhase7Base):
    def setUp(self):
        super().setUp()
        # Announcements
        self.ann_school_wide_a = Announcement.objects.create(
            institution=self.school_a,
            title="School Wide A",
            message="For all school A",
            status="published",
        )
        self.ann_campus_a1 = Announcement.objects.create(
            institution=self.school_a,
            campus=self.campus_a1,
            title="Campus A1",
            message="For campus A1",
            status="published",
        )
        self.ann_campus_a2 = Announcement.objects.create(
            institution=self.school_a,
            campus=self.campus_a2,
            title="Campus A2",
            message="For campus A2",
            status="published",
        )
        self.ann_school_b = Announcement.objects.create(
            institution=self.school_b,
            title="School B Wide",
            message="For school B",
            status="published",
        )

    def test_campus_admin_a1_sees_school_wide_and_own_campus(self):
        response = self._as(self.campus_admin_a1).get("/api/communication/announcements/")
        self.assertEqual(response.status_code, 200)
        anns = self._body(response)
        titles = {a["title"] for a in anns}
        self.assertIn("School Wide A", titles)
        self.assertIn("Campus A1", titles)
        self.assertNotIn("Campus A2", titles)
        self.assertNotIn("School B Wide", titles)

    def test_campus_admin_a2_sees_school_wide_and_own_campus(self):
        response = self._as(self.campus_admin_a2).get("/api/communication/announcements/")
        self.assertEqual(response.status_code, 200)
        anns = self._body(response)
        titles = {a["title"] for a in anns}
        self.assertIn("School Wide A", titles)
        self.assertIn("Campus A2", titles)
        self.assertNotIn("Campus A1", titles)
        self.assertNotIn("School B Wide", titles)

    def test_super_admin_sees_all_school_a_announcements(self):
        response = self._as(self.super_admin).get("/api/communication/announcements/")
        self.assertEqual(response.status_code, 200)
        anns = self._body(response)
        titles = {a["title"] for a in anns}
        self.assertIn("School Wide A", titles)
        self.assertIn("Campus A1", titles)
        self.assertIn("Campus A2", titles)
        self.assertNotIn("School B Wide", titles)

    def test_announcement_create_stamps_institution(self):
        response = self._as(self.campus_admin_a1).post(
            "/api/communication/announcements/",
            {"title": "Test", "message": "Test msg", "status": "draft"},
        )
        self.assertEqual(response.status_code, 201)
        ann = Announcement.objects.get(pk=response.json()["id"])
        self.assertEqual(ann.institution_id, self.school_a.id)

    def test_announcement_cross_school_notify_no_leak(self):
        """Publishing school-wide announcement from school A does not notify school B users."""
        # Create user in school B
        user_b = make_user("userb", Role.TEACHER, self.school_b)
        user_b.refresh_from_db()

        # Publish school-wide announcement from school A via API
        response = self._as(self.campus_admin_a1).post(
            "/api/communication/announcements/",
            {"title": "School A Wide", "message": "Test", "status": "published"},
        )
        self.assertEqual(response.status_code, 201)

        # Check notifications: school B user should not have notification
        notifications_b = Notification.objects.filter(recipient=user_b)
        self.assertEqual(notifications_b.count(), 0)


class AnnouncementTargetUserIdsTests(CommunicationPhase7Base):
    """Direct model method tests for target_user_ids institution scoping."""

    def test_target_user_ids_school_wide_scoped_to_institution(self):
        ann = Announcement.objects.create(
            institution=self.school_a,
            title="School Wide",
            message="All school A",
            status="published",
            audience_roles=[],
        )
        user_ids = ann.target_user_ids()
        # All users should belong to school_a via membership
        from apps.accounts.models import InstitutionMembership
        membership_schools = InstitutionMembership.objects.filter(
            user_id__in=user_ids, status="active"
        ).values_list("institution_id", flat=True).distinct()
        self.assertEqual(set(membership_schools), {self.school_a.id})

    def test_target_user_ids_campus_scoped(self):
        """Campus-scoped announcement filters by campus and institution."""
        ann = Announcement.objects.create(
            institution=self.school_a,
            campus=self.campus_a1,
            title="Campus A1",
            message="Campus A1",
            status="published",
        )
        user_ids = ann.target_user_ids()
        # With no enrollments, returns empty list (correctly filtered)
        self.assertEqual(user_ids, [])


class MessageTemplateIsolationTests(CommunicationPhase7Base):
    def setUp(self):
        super().setUp()
        self.template_a = MessageTemplate.objects.create(
            name="Template A",
            channel="sms",
            subject="Test",
            body="Body A",
            institution=self.school_a,
            created_by=self.super_admin,
        )
        self.template_b = MessageTemplate.objects.create(
            name="Template B",
            channel="sms",
            subject="Test",
            body="Body B",
            institution=self.school_b,
            created_by=self.super_admin,
        )
        self.template_global = MessageTemplate.objects.create(
            name="Global Template",
            channel="email",
            subject="Test",
            body="Global",
            institution=None,
            created_by=self.super_admin,
        )

    def test_campus_admin_sees_own_school_and_global_templates(self):
        response = self._as(self.campus_admin_a1).get("/api/communication/templates/")
        self.assertEqual(response.status_code, 200)
        templates = response.json()
        names = {t["name"] for t in templates}
        self.assertIn("Template A", names)
        self.assertIn("Global Template", names)
        self.assertNotIn("Template B", names)

    def test_campus_admin_detail_other_school_404(self):
        response = self._as(self.campus_admin_a1).get(
            f"/api/communication/templates/{self.template_b.pk}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_campus_admin_update_other_school_404(self):
        response = self._as(self.campus_admin_a1).put(
            f"/api/communication/templates/{self.template_b.pk}/",
            {"name": "Hacked"},
        )
        self.assertEqual(response.status_code, 404)

    def test_campus_admin_delete_other_school_404(self):
        response = self._as(self.campus_admin_a1).delete(
            f"/api/communication/templates/{self.template_b.pk}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_campus_admin_preview_other_school_404(self):
        response = self._as(self.campus_admin_a1).post(
            f"/api/communication/templates/{self.template_b.pk}/preview/",
            {"context": {}},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_super_admin_sees_all(self):
        response = self._as(self.super_admin).get("/api/communication/templates/")
        self.assertEqual(response.status_code, 200)
        templates = response.json()
        names = {t["name"] for t in templates}
        self.assertIn("Template A", names)
        self.assertIn("Template B", names)
        self.assertIn("Global Template", names)

    def test_create_stamps_institution(self):
        response = self._as(self.campus_admin_a1).post(
            "/api/communication/templates/",
            {"name": "New A", "channel": "sms", "subject": "S", "body": "B"},
        )
        self.assertEqual(response.status_code, 201)
        tpl = MessageTemplate.objects.get(pk=response.json()["id"])
        self.assertEqual(tpl.institution_id, self.school_a.id)


class EmailLogIsolationTests(CommunicationPhase7Base):
    def setUp(self):
        super().setUp()
        self.log_a = EmailLog.objects.create(
            institution=self.school_a,
            recipient_email="a@test.edu",
            subject="From A",
            body="Body A",
            status="sent",
        )
        self.log_b = EmailLog.objects.create(
            institution=self.school_b,
            recipient_email="b@test.edu",
            subject="From B",
            body="Body B",
            status="sent",
        )

    def test_campus_admin_sees_only_own_institution_logs(self):
        response = self._as(self.campus_admin_a1).get("/api/communication/email/logs/")
        self.assertEqual(response.status_code, 200)
        logs = response.json()
        subjects = {l["subject"] for l in logs}
        self.assertIn("From A", subjects)
        self.assertNotIn("From B", subjects)

    def test_super_admin_sees_all_logs(self):
        response = self._as(self.super_admin).get("/api/communication/email/logs/")
        self.assertEqual(response.status_code, 200)
        logs = response.json()
        subjects = {l["subject"] for l in logs}
        self.assertIn("From A", subjects)
        self.assertIn("From B", subjects)

def test_broadcast_stamps_institution(self):
        # Broadcast is global-only, but verify institution stamping
        from django.test import override_settings
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            response = self._as(self.super_admin).post(
                "/api/communication/email/send/",
                {"subject": "Test", "message": "Test", "role": "all"},
            )
            self.assertEqual(response.status_code, 200)
            log = EmailLog.objects.latest("created_at")
            self.assertEqual(log.institution_id, self.school_a.id)


class MessageIsolationTests(CommunicationPhase7Base):
    def setUp(self):
        super().setUp()
        # Create users for messaging
        self.user_a = make_user("usera", Role.TEACHER, self.school_a)
        self.user_b = make_user("userb", Role.TEACHER, self.school_b)

    def test_send_message_cross_school_denied(self):
        """Sending message to user in other school returns 403."""
        response = self._as(self.user_a).post(
            "/api/communication/messages/",
            {"recipient_id": self.user_b.pk, "subject": "Hi", "body": "Cross school"},
        )
        self.assertEqual(response.status_code, 403)

    def test_send_message_same_school_allowed(self):
        """Sending message to same-school staff is allowed."""
        # Create another teacher in same school
        user_a2 = make_user("usera2", Role.TEACHER, self.school_a)
        response = self._as(self.user_a).post(
            "/api/communication/messages/",
            {"recipient_id": user_a2.pk, "subject": "Hi", "body": "Same school"},
        )
        self.assertEqual(response.status_code, 201)

    def test_message_detail_cross_school_404(self):
        """Viewing other school's message returns 404."""
        msg = Message.objects.create(
            sender=self.user_a,
            recipient=self.user_a,
            subject="Test",
            body="Test",
            institution=self.school_a,
        )
        # Another user in same school can view (as sender/recipient)
        response = self._as(self.user_a).get(f"/api/communication/messages/{msg.pk}/")
        self.assertEqual(response.status_code, 200)

        # User in other school cannot
        response = self._as(self.user_b).get(f"/api/communication/messages/{msg.pk}/")
        self.assertEqual(response.status_code, 404)


class NotificationIsolationTests(CommunicationPhase7Base):
    def test_mark_read_cross_school_404(self):
        user_b = make_user("userb", Role.STUDENT, self.school_b)
        notif = Notification.objects.create(
            recipient=user_b,
            title="Test",
            message="Test",
            notification_type="announcement",
        )
        response = self._as(self.campus_admin_a1).post(
            f"/api/communication/notifications/{notif.pk}/mark-read/"
        )
        self.assertEqual(response.status_code, 404)
