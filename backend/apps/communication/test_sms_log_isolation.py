from rest_framework.test import APITestCase, APIRequestFactory, force_authenticate
from apps.accounts.models import Role, User
from apps.accounts.test_access import make_user
from apps.communication.models import SMSLog
from apps.communication.sms_views import SMSLogListView
from apps.schools.models import School


class SMSLogIsolationTests(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Logs A", code="SMSLOG-A")
        other = School.objects.create(name="Logs B", code="SMSLOG-B")
        self.admin = make_user("smslog-admin", Role.ADMIN, self.school)
        self.accountant = make_user("smslog-acct", Role.ACCOUNTANT, self.school)
        foreign = make_user("smslog-foreign", Role.ADMIN, other)
        self.own = SMSLog.objects.create(institution=self.school, sent_by=self.admin, phone_number="0300000001", message="Own", status="sent")
        self.colleague = SMSLog.objects.create(institution=self.school, sent_by=self.accountant, phone_number="0300000002", message="Colleague", status="failed")
        self.foreign = SMSLog.objects.create(institution=other, sent_by=foreign, phone_number="0300000003", message="Private foreign", status="sent")
        SMSLog.objects.create(phone_number="0300000004", message="Unscoped private", status="sent")

    def test_school_admin_list_and_counts_are_scoped(self):
        self.client.force_login(self.admin)
        response = self.client.get("/api/communication/sms/logs/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 2)
        self.assertEqual({row["id"] for row in response.json()["results"]}, {self.own.pk, self.colleague.pk})
        filtered = self.client.get("/api/communication/sms/logs/?status=sent")
        self.assertEqual(filtered.json()["count"], 1)
        self.assertEqual(filtered.json()["results"][0]["id"], self.own.pk)

    def test_non_global_user_keeps_sender_restriction(self):
        self.client.force_login(self.accountant)
        response = self.client.get("/api/communication/sms/logs/")
        self.assertEqual({row["id"] for row in response.json()["results"]}, {self.colleague.pk})

    def test_missing_school_returns_no_private_logs(self):
        request = APIRequestFactory().get("/")
        request.institution = None
        force_authenticate(request, user=self.admin)
        response = SMSLogListView.as_view()(request)
        self.assertEqual(response.data["count"], 0)

    def test_platform_superadmin_retains_all_school_logs(self):
        platform = User.objects.create_superuser("smslog-platform", "smslog-platform@test.edu", "TestPass123!")
        self.client.force_login(platform)
        response = self.client.get("/api/communication/sms/logs/")
        self.assertIn(self.foreign.pk, {row["id"] for row in response.json()["results"]})
