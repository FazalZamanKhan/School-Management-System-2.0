from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import InstitutionMembership, Role, RoleAssignment
from apps.schools.models import Campus, School

from .models import SupportTicket, TicketCategory, TicketMessage


class HelpdeskBase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.school = School.objects.create(name="Helpdesk School")
        self.campus = Campus.objects.create(
            school=self.school,
            name="Main Campus",
        )
        self.other_campus = Campus.objects.create(
            school=self.school,
            name="North Campus",
        )

        self.admin = self._make_user("admin", Role.ADMIN)
        self.teacher = self._make_user("teacher", Role.TEACHER)
        self.student = self._make_user("student", Role.STUDENT)

    def _make_user(self, username, role):
        user = get_user_model().objects.create_user(
            username=username,
            email=f"{username}@test.edu",
            password="TestPass123!",
        )
        membership = InstitutionMembership.objects.create(
            user=user,
            institution=self.school,
        )
        RoleAssignment.objects.create(
            membership=membership,
            role=role,
        )
        return user

    def login(self, user):
        self.client.force_login(user)

    def create_ticket(self, **overrides):
        data = {
            "subject": "Laptop not working",
            "description": "Screen flickers.",
            "campus": self.campus.id,
        }
        data.update(overrides)
        response = self.client.post(
            "/api/helpdesk/tickets/",
            data,
            format="json",
        )
        return response

    def create_category(self):
        return TicketCategory.objects.create(
            institution=self.school,
            name="IT",
        )


class HelpdeskStaffTests(HelpdeskBase):
    def test_requires_authentication(self):
        response = self.client.get("/api/helpdesk/tickets/")
        self.assertEqual(response.status_code, 403)

    def test_staff_can_create_and_list_tickets(self):
        self.login(self.admin)

        response = self.create_ticket()
        self.assertEqual(response.status_code, 201)

        data = response.json()
        self.assertEqual(data["created_by"], self.admin.id)
        self.assertEqual(data["status"], "open")

        listing = self.client.get("/api/helpdesk/tickets/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()), 1)

    def test_non_staff_teacher_cannot_create_via_admin_flow(self):
        # Teacher is not a manager of the helpdesk desk view.
        self.login(self.student)
        # Explicit: use the self-service endpoint instead.
        response = self.client.post(
            "/api/helpdesk/tickets/",
            {"subject": "Hijack"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_resolve_and_reopen_flow(self):
        self.login(self.admin)
        ticket_id = self.create_ticket().json()["id"]

        resolve = self.client.post(
            f"/api/helpdesk/tickets/{ticket_id}/resolve/",
            {"resolution_notes": "Replaced the panel."},
            format="json",
        )
        self.assertEqual(resolve.status_code, 200)
        self.assertEqual(resolve.json()["status"], "resolved")
        self.assertEqual(resolve.json()["resolution_notes"], "Replaced the panel.")
        self.assertIsNotNone(resolve.json()["resolved_at"])

        reopen = self.client.post(
            f"/api/helpdesk/tickets/{ticket_id}/reopen/",
            {},
            format="json",
        )
        self.assertEqual(reopen.status_code, 200)
        self.assertEqual(reopen.json()["status"], "open")
        self.assertIsNone(reopen.json()["resolved_at"])

    def test_assign_sets_in_progress(self):
        self.login(self.admin)
        ticket_id = self.create_ticket().json()["id"]

        response = self.client.post(
            f"/api/helpdesk/tickets/{ticket_id}/assign/",
            {"assignee": self.teacher.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["assignee"], self.teacher.id)
        self.assertEqual(response.json()["status"], "in_progress")

    def test_messages_bump_ticket_to_in_progress(self):
        self.login(self.admin)
        ticket_id = self.create_ticket().json()["id"]

        response = self.client.post(
            f"/api/helpdesk/tickets/{ticket_id}/messages/",
            {"body": "Checking this now."},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        ticket = SupportTicket.objects.get(pk=ticket_id)
        self.assertEqual(ticket.status, "in_progress")

    def test_campus_scope_for_campus_admin(self):
        self.login(self.admin)
        self.create_ticket(campus=self.campus.id)
        self.create_ticket(subject="North issue", campus=self.other_campus.id)

        north_admin = self._make_user("northadmin", Role.CAMPUS_ADMIN)
        from apps.accounts.models import StaffProfile, RoleAssignment

        RoleAssignment.objects.filter(
            membership__user=north_admin, role=Role.CAMPUS_ADMIN
        ).update(campus=self.other_campus)

        StaffProfile.objects.create(
            user=north_admin,
            institution=self.school,
            primary_campus=self.other_campus,
            status="active",
        )
        self.login(north_admin)

        response = self.client.get("/api/helpdesk/tickets/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["campus"], self.other_campus.id)


class HelpdeskSelfServiceTests(HelpdeskBase):
    def test_student_can_raise_ticket(self):
        self.login(self.student)

        response = self.client.post(
            "/api/helpdesk/my/tickets/create/",
            {
                "subject": "Fee receipt missing",
                "description": "Need a copy.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["created_by"], self.student.id)
        self.assertEqual(response.json()["status"], "open")

    def test_student_only_sees_own_tickets(self):
        self.login(self.admin)
        self.create_ticket(subject="Admin ticket")
        self.login(self.student)
        self.client.post(
            "/api/helpdesk/my/tickets/create/",
            {"subject": "My ticket"},
            format="json",
        )

        response = self.client.get("/api/helpdesk/my/tickets/")
        self.assertEqual(response.status_code, 200)
        tickets = response.json()
        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0]["subject"], "My ticket")

    def test_internal_message_hidden_from_reporter(self):
        self.login(self.admin)
        ticket_id = self.create_ticket().json()["id"]
        self.client.post(
            f"/api/helpdesk/tickets/{ticket_id}/messages/",
            {"body": "Visible reply", "is_internal": False},
            format="json",
        )
        self.client.post(
            f"/api/helpdesk/tickets/{ticket_id}/messages/",
            {"body": "Private note", "is_internal": True},
            format="json",
        )

        response = self.client.get(f"/api/helpdesk/tickets/{ticket_id}/")
        bodies = [
            m["body"]
            for m in response.json()["messages"]
        ]
        self.assertIn("Visible reply", bodies)
        self.assertIn("Private note", bodies)

        self.login(self.student)
        # The reporter is the admin here — create a ticket as the student
        # so self-service detail reflects public messages only.
        student_ticket = self.client.post(
            "/api/helpdesk/my/tickets/create/",
            {"subject": "Student ticket"},
            format="json",
        ).json()
        TicketMessage.objects.create(
            ticket_id=student_ticket["id"],
            author=self.admin,
            body="Public answer",
            is_internal=False,
        )
        TicketMessage.objects.create(
            ticket_id=student_ticket["id"],
            author=self.admin,
            body="Internal only",
            is_internal=True,
        )

        detail = self.client.get(
            f"/api/helpdesk/my/tickets/{student_ticket['id']}/"
        )
        bodies = [m["body"] for m in detail.json()["messages"]]
        self.assertIn("Public answer", bodies)
        self.assertNotIn("Internal only", bodies)
