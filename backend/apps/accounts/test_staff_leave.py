from datetime import date

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import StaffProfile
from apps.accounts.test_access import make_user
from apps.accounts.views import StaffLeaveListCreateView
from apps.schools.models import Campus, School


class StaffLeaveSubmissionTests(TestCase):
    """Regression: submitting a staff leave request with no linked
    StaffProfile must fail with a clear 400, not a 404.

    StaffLeaveListCreateView.perform_create previously raised NotFound
    (HTTP 404) when request.user.staff_profile was None -- always true
    for a teacher-role account, since Teacher and StaffProfile are
    separate, unlinked tables. The sibling StaffAttendanceListCreateView
    already used serializers.ValidationError (HTTP 400) for the
    identical condition; this just brings StaffLeave in line with it.
    This does NOT auto-create a StaffProfile for the teacher -- that
    would be a different (and inappropriate) fix.
    """

    def setUp(self):
        self.school = School.objects.create(name="Test School")
        self.campus = Campus.objects.create(school=self.school, name="Main Campus")

    def _post(self, user):
        request = APIRequestFactory().post(
            "/api/staff/leave/",
            {
                "leave_type": "casual",
                "start_date": "2026-11-02",
                "end_date": "2026-11-02",
                "reason": "Test",
            },
            format="json",
        )
        force_authenticate(request, user)
        request.institution = self.school
        response = StaffLeaveListCreateView.as_view()(request)
        response.render()
        return response

    def test_teacher_without_staff_profile_gets_400_not_404(self):
        teacher = make_user("teacher_leave_x", "teacher", self.school)

        response = self._post(teacher)

        self.assertEqual(response.status_code, 400)
        self.assertIn("staff", response.data)

    def test_user_with_staff_profile_can_submit_leave(self):
        staff_user = make_user("staff_leave_x", "staff", self.school)
        StaffProfile.objects.create(
            institution=self.school,
            user=staff_user,
            employee_number="STF-LEAVE-001",
            first_name="Ayesha",
            last_name="Khan",
            gender="female",
            primary_campus=self.campus,
        )

        response = self._post(staff_user)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "pending")
