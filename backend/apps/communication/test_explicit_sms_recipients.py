from unittest.mock import patch
from rest_framework.test import APITestCase
from apps.accounts.models import Role, StaffProfile
from apps.accounts.test_access import make_user
from apps.schools.models import School, Campus
from apps.communication.models import SMSLog


class ExplicitSMSRecipientTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="SMS A", code="SMS-A")
        self.campus = Campus.objects.create(school=self.school, name="Main")
        self.admin = make_user("sms-admin", Role.ADMIN, self.school)
        self.recipient = make_user("sms-recipient", Role.GUARD, self.school)
        self.recipient.phone = "0300000001"
        self.recipient.save(update_fields=["phone"])
        StaffProfile.objects.create(user=self.recipient, institution=self.school, primary_campus=self.campus, employee_number="SMS1", first_name="SMS", last_name="Recipient", gender="male")
        self.client.force_login(self.admin)

    @patch("apps.communication.sms_views.send_sms", return_value=(True, ""))
    def test_own_school_recipient_sends_once_and_logs(self, send):
        response = self.client.post("/api/communication/sms/send/", {"message": "Hello", "recipient_ids": [self.recipient.pk, self.recipient.pk]}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["sent"], 1)
        send.assert_called_once_with("0300000001", "Hello")
        self.assertEqual(SMSLog.objects.get().institution_id, self.school.pk)

    @patch("apps.communication.sms_views.send_sms")
    def test_foreign_and_missing_recipients_rejected_without_any_send(self, send):
        other = School.objects.create(name="SMS B", code="SMS-B")
        foreign = make_user("sms-foreign", Role.ADMIN, other)
        for pk in (foreign.pk, 999999):
            response = self.client.post("/api/communication/sms/send/", {"message": "Hello", "recipient_ids": [self.recipient.pk, pk]}, format="json")
            self.assertEqual(response.status_code, 403)
        send.assert_not_called()
        self.assertEqual(SMSLog.objects.count(), 0)

    @patch("apps.communication.sms_views.send_sms")
    def test_malformed_recipient_ids_rejected(self, send):
        for value in ("1", ["bad"], [True]):
            response = self.client.post("/api/communication/sms/send/", {"message": "Hello", "recipient_ids": value}, format="json")
            self.assertEqual(response.status_code, 400)
        send.assert_not_called()

    @patch("apps.communication.sms_views.send_sms")
    def test_campus_filter_rejects_recipient_in_other_campus(self, send):
        north = Campus.objects.create(school=self.school, name="North")
        response = self.client.post("/api/communication/sms/send/", {"message": "Hello", "recipient_ids": [self.recipient.pk], "campus_id": north.pk}, format="json")
        self.assertEqual(response.status_code, 403)
        send.assert_not_called()

    @patch("apps.communication.sms_views.send_sms", return_value=(True, ""))
    def test_student_recipient_resolves_guardian_phone(self, send):
        from apps.ai.helpers import make_structure, make_student

        student = make_student(self.school, make_structure(self.school, campus_name="Students"))
        actor = make_user("sms-student", Role.STUDENT, self.school)
        student.user = actor
        student.membership = actor.memberships.get(institution=self.school)
        student.save()
        response = self.client.post("/api/communication/sms/send/", {"message": "Guardian notice", "recipient_ids": [actor.pk]}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        send.assert_called_once_with(student.guardian.phone, "Guardian notice")
