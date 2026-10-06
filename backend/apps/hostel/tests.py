"""Hostel → Add Room regression and tenant/campus isolation tests.

Covers the confirmed bug: the Add Room hostel selector did not show all
hostels the user is authorized to create Rooms in, because it was fed by the
campus-scoped Hostel-management list. Room management is a school-wide
(institution-scoped) staff function in this codebase, so the selector must be
institution-scoped while the general hostel list stays campus-scoped.
"""

from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role, StaffProfile
from apps.accounts.test_access import make_user
from apps.hostel.models import Allocation, Hostel, Room
from apps.schools.models import Campus, School
from apps.students.models import Guardian, Student

PASSWORD = "TestPass123!"


def _make_campus_admin(username, campus, employee_number):
    """A CAMPUS_ADMIN whose staff profile pins them to a single campus."""
    user = make_user(username, Role.CAMPUS_ADMIN, campus.school, campus=campus)
    StaffProfile.objects.create(
        user=user,
        institution=campus.school,
        employee_number=employee_number,
        first_name="Campus",
        last_name="Admin",
        gender="male",
        primary_campus=campus,
    )
    return user


class HostelAddRoomSetup(TestCase):
    """Two schools; School A has two campuses, School B has one.

    School A -> Campus A1 -> Hostel A1
            -> Campus A2 -> Hostel A2
    School B -> Campus B1 -> Hostel B1
    """

    PASSWORD = PASSWORD

    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(
            name="Hostel School A", code="hstl-a", status="active"
        )
        cls.campus_a1 = Campus.objects.create(
            school=cls.school_a, name="Campus A1", status="active"
        )
        cls.campus_a2 = Campus.objects.create(
            school=cls.school_a, name="Campus A2", status="active"
        )
        cls.school_b = School.objects.create(
            name="Hostel School B", code="hstl-b", status="active"
        )
        cls.campus_b1 = Campus.objects.create(
            school=cls.school_b, name="Campus B1", status="active"
        )

        cls.hostel_a1 = Hostel.objects.create(
            institution=cls.school_a, campus=cls.campus_a1, name="Hostel A1"
        )
        cls.hostel_a2 = Hostel.objects.create(
            institution=cls.school_a, campus=cls.campus_a2, name="Hostel A2"
        )
        cls.hostel_b1 = Hostel.objects.create(
            institution=cls.school_b, campus=cls.campus_b1, name="Hostel B1"
        )

        # a global admin of School A
        cls.admin_a = make_user("hstl-admin-a", Role.ADMIN, cls.school_a)
        # a non-global manager pinned to Campus A1
        cls.campus_admin_a1 = _make_campus_admin(
            "hstl-cadmin-a1", cls.campus_a1, "HSTL-A1-001"
        )

    def setUp(self):
        self.client = APIClient()

    def _as(self, user):
        """Authenticate through the Django-session + DRF double layer.

        ActiveInstitutionMiddleware reads ``request.user`` as set by Django's
        AuthenticationMiddleware, so ``force_authenticate`` is combined with a
        real session login (mirrors test_campus_isolation.py).
        """
        self.client.force_authenticate(user=None)
        self.assertTrue(
            self.client.login(
                username=user.username, password=self.PASSWORD
            ),
            f"login failed for {user.username}",
        )
        self.client.force_authenticate(user=user)
        return self.client

    def _ids(self, url):
        data = self.client.get(url).json()
        body = data if isinstance(data, list) else data.get("results", data)
        return [row["id"] for row in body]


class HostelRoomSelectorTests(HostelAddRoomSetup):
    """Tests 1-4: the selector exposes exactly what Room creation authorizes."""

    def test_authorized_hostel_appears_in_selector(self):
        """Test 1 — the expected hostel is returned by the selector API."""
        response = self._as(self.admin_a).get("/api/hostel/room-hostels/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.json()]
        self.assertIn(self.hostel_a1.pk, ids)
        self.assertIn(self.hostel_a1.name, [row["name"] for row in response.json()])

    def test_add_room_can_use_selector_hostel(self):
        """Test 2 — a Room is created against the selector-provided hostel."""
        self._as(self.admin_a)
        response = self.client.post(
            "/api/hostel/rooms/",
            {
                "hostel": self.hostel_a1.pk,
                "room_number": "101",
                "capacity": 4,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        room = Room.objects.get(pk=response.json()["id"])
        self.assertEqual(room.hostel, self.hostel_a1)
        self.assertEqual(room.room_number, "101")

    def test_cross_school_selector_isolation(self):
        """Test 3 — School A can never see School B hostels."""
        self._as(self.admin_a)
        ids = self._ids("/api/hostel/room-hostels/")
        self.assertIn(self.hostel_a1.pk, ids)
        self.assertNotIn(self.hostel_b1.pk, ids)

    def test_selector_matches_room_management_authorization(self):
        """Test 4 — Room management is school-wide within the institution.

        A Campus-A1-only manager may create Rooms in any hostel of School A
        (the existing Room/Allocation/Vacate write paths are institution-
        scoped, exactly like the sibling unit/class/section parents), so the
        selector exposes Hostel A1 and Hostel A2 — but never Hostel B1.
        """
        self._as(self.campus_admin_a1)
        ids = self._ids("/api/hostel/room-hostels/")
        self.assertIn(self.hostel_a1.pk, ids)
        self.assertIn(self.hostel_a2.pk, ids)
        self.assertNotIn(self.hostel_b1.pk, ids)

    def test_selector_shows_hostel_that_general_list_hides(self):
        """Original failure condition.

        Hostel A2 is authorized for room management but hidden by the
        campus-scoped hostel-management list for a Campus-A1 manager. The
        selector must expose it — this is the exact reference check that
        protects the Add Room form from regressing to the wrong feed.
        """
        self._as(self.campus_admin_a1)

        general_ids = self._ids("/api/hostel/hostels/")
        self.assertIn(self.hostel_a1.pk, general_ids)
        self.assertNotIn(self.hostel_a2.pk, general_ids)
        self.assertNotIn(self.hostel_b1.pk, general_ids)

        selector_ids = self._ids("/api/hostel/room-hostels/")
        self.assertIn(self.hostel_a2.pk, selector_ids)
        self.assertNotIn(self.hostel_b1.pk, selector_ids)

    def test_general_hostel_list_remains_campus_scoped(self):
        """Negative control: the hostel-management list is NOT weakened."""
        self._as(self.admin_a)
        ids = self._ids("/api/hostel/hostels/")
        self.assertIn(self.hostel_a1.pk, ids)
        self.assertIn(self.hostel_a2.pk, ids)
        self.assertNotIn(self.hostel_b1.pk, ids)

        self._as(self.campus_admin_a1)
        ids = self._ids("/api/hostel/hostels/")
        self.assertIn(self.hostel_a1.pk, ids)
        self.assertNotIn(self.hostel_a2.pk, ids)
        self.assertNotIn(self.hostel_b1.pk, ids)


class HostelRoomSecurityTests(HostelAddRoomSetup):
    """Test 5 — direct-ID protection and cross-school write/read blocks."""

    def test_cross_school_room_post_rejected(self):
        """POST Room with another school's hostel id must be rejected."""
        response = self._as(self.admin_a).post(
            "/api/hostel/rooms/",
            {
                "hostel": self.hostel_b1.pk,
                "room_number": "X1",
                "capacity": 4,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "hostel", response.json(),
            "error should name the hostel field",
        )
        self.assertFalse(
            Room.objects.filter(
                room_number="X1", hostel=self.hostel_b1
            ).exists()
        )

    def test_cross_school_hostel_get_patch_delete_blocked(self):
        self._as(self.admin_a)

        response = self.client.get(
            f"/api/hostel/hostels/{self.hostel_b1.pk}/"
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.patch(
            f"/api/hostel/hostels/{self.hostel_b1.pk}/",
            {"warden": "Intruder"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.delete(
            f"/api/hostel/hostels/{self.hostel_b1.pk}/"
        )
        self.assertEqual(response.status_code, 404)

        # The foreign hostel still exists untouched.
        self.assertTrue(Hostel.objects.filter(pk=self.hostel_b1.pk).exists())

    def test_cross_campus_hostel_detail_blocked_for_campus_manager(self):
        """Hostel management is campus-scoped; detail 404s outside scope."""
        response = self._as(self.campus_admin_a1).get(
            f"/api/hostel/hostels/{self.hostel_a2.pk}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_campus_manager_can_create_room_on_other_campus_of_school(self):
        """School-wide room management: Hostel A2 is a valid room target."""
        response = self._as(self.campus_admin_a1).post(
            "/api/hostel/rooms/",
            {
                "hostel": self.hostel_a2.pk,
                "room_number": "202",
                "capacity": 2,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        room = Room.objects.get(pk=response.json()["id"])
        self.assertEqual(room.hostel, self.hostel_a2)

    def test_anonymous_cannot_read_selector_or_rooms(self):
        response = self.client.get("/api/hostel/room-hostels/")
        self.assertEqual(response.status_code, 403)

        response = self.client.get("/api/hostel/rooms/")
        self.assertEqual(response.status_code, 403)

    def test_room_list_is_institution_scoped(self):
        """Rooms of School B are never listed for a School A user."""
        Room.objects.create(
            hostel=self.hostel_b1, room_number="B-1", capacity=4
        )
        self._as(self.admin_a)

        ids = self._ids("/api/hostel/rooms/")
        self.assertNotIn(
            Room.objects.get(room_number="B-1").pk, ids
        )

        response = self.client.get("/api/hostel/rooms/")
        self.assertEqual(response.status_code, 200)


class HostelAddRoomEndToEndTests(HostelAddRoomSetup):
    """Manual E2E equivalent: the full Add Room journey through the API.

    Mirrors the task's manual verification steps (create hostel → hostel on
    page → open selector → room creation → room persists → correct hostel).
    """

    def test_full_add_room_workflow(self):
        client = self._as(self.admin_a)

        # 1. Create Hostel via the API (with its campus).
        created = client.post(
            "/api/hostel/hostels/",
            {
                "name": "EndToEnd Hostel",
                "campus": self.campus_a2.pk,
                "warden": "",
                "gender": "mixed",
                "address": "",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        hostel_id = created.json()["id"]

        # 2. Hostel appears on the hostel-management page endpoint.
        list_response = client.get("/api/hostel/hostels/")
        self.assertIn(
            hostel_id, self._ids("/api/hostel/hostels/")
        )

        # 3. 'Click Add Room' -> open the hostel selector -> hostel appears.
        selector = client.get("/api/hostel/room-hostels/").json()
        self.assertIn(hostel_id, [row["id"] for row in selector])

        # 4. Select hostel, 5. enter room info, 6. save.
        room = client.post(
            "/api/hostel/rooms/",
            {
                "hostel": hostel_id,
                "room_number": "E2E-1",
                "capacity": 4,
            },
            format="json",
        )
        self.assertEqual(room.status_code, 201)
        room_id = room.json()["id"]

        # 7. Confirm the Room appears in the rooms list.
        self.assertIn(room_id, self._ids("/api/hostel/rooms/"))

        # 8+9. 'Refresh page' -> Room still exists.
        self.assertIn(room_id, self._ids("/api/hostel/rooms/"))

        # 10. Room.hostel points to the correct Hostel.
        persisted = Room.objects.get(pk=room_id)
        self.assertEqual(persisted.hostel_id, hostel_id)
        self.assertEqual(persisted.room_number, "E2E-1")


class AllocationActiveSchoolPolicyTests(HostelAddRoomSetup):
    """ACTIVE-SCHOOL FAILURE POLICY regression suite.

    Missing, invalid, unauthorized or unresolved active-school context must
    always fail closed. The hostel endpoints must NEVER fall back to
    ``Student.objects.all()`` / all-room / all-allocation (all-school) data.

    ``force_authenticate`` without a session login leaves ``request.institution``
    unset (documented in test_campus_isolation) while ``IsStaffRole`` still
    passes because the user holds staff roles on an active membership — this is
    exactly the "authorized user, missing active school" state the policy
    targets.
    """

    def _as_no_school(self, user):
        """Authenticated staff user with NO active school context."""
        self.client.force_authenticate(user=None)
        self.client.force_authenticate(user=user)
        return self.client

    def _make_student(self, school, campus, admission_number):
        guardian = Guardian.objects.create(
            name=f"Guardian {admission_number}",
            relationship="Father",
            phone=f"555-{admission_number}",
        )
        return Student.objects.create(
            institution=school,
            admission_number=admission_number,
            first_name="Alloc",
            last_name=admission_number,
            gender="male",
            status="active",
            primary_campus=campus,
            guardian=guardian,
        )

    def _make_allocation(self, hostel, room_number, student):
        room = Room.objects.create(
            hostel=hostel, room_number=room_number, capacity=4
        )
        return Allocation.objects.create(
            room=room,
            student=student,
            start_date=date(2026, 9, 1),
        )

    def _set_active_school(self, school_id):
        session = self.client.session
        session["active_institution_id"] = school_id
        session.save()
        return self.client

    def test_allocations_are_institution_scoped(self):
        """A School-A user only ever sees School-A allocations."""
        student_a = self._make_student(
            self.school_a, self.campus_a1, "ALLOC-A-001"
        )
        student_b = self._make_student(
            self.school_b, self.campus_b1, "ALLOC-B-001"
        )
        alloc_a = self._make_allocation(
            self.hostel_a1, "A-ALLOC-1", student_a
        )
        alloc_b = self._make_allocation(
            self.hostel_b1, "B-ALLOC-1", student_b
        )

        self._as(self.admin_a)
        body = self._ids("/api/hostel/allocations/")
        self.assertIn(alloc_a.pk, body)
        self.assertNotIn(alloc_b.pk, body)

    def test_missing_active_school_allocation_list_fails_closed(self):
        """No active school → allocations request is EMPTY, never all-school."""
        student_a = self._make_student(
            self.school_a, self.campus_a1, "ALLOC-A-002"
        )
        alloc = self._make_allocation(
            self.hostel_a1, "A-ALLOC-2", student_a
        )
        self.assertTrue(Allocation.objects.filter(pk=alloc.pk).exists())

        self._as_no_school(self.admin_a)
        response = self.client.get("/api/hostel/allocations/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(alloc.pk, self._ids("/api/hostel/allocations/"))

    def test_missing_active_school_rooms_fails_closed(self):
        """No active school → the Add Room feed is empty, not all rooms."""
        Room.objects.create(
            hostel=self.hostel_a1, room_number="FAIL-OPEN-1", capacity=4
        )
        self.assertTrue(Room.objects.exists())

        self._as_no_school(self.admin_a)
        response = self.client.get("/api/hostel/rooms/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._ids("/api/hostel/rooms/"), [])

    def test_missing_active_school_room_post_rejected(self):
        Room.objects.create(
            hostel=self.hostel_a1, room_number="FAIL-OPEN-2", capacity=4
        )
        self._as_no_school(self.admin_a)
        response = self.client.post(
            "/api/hostel/rooms/",
            {
                "hostel": self.hostel_a1.pk,
                "room_number": "NOPE-1",
                "capacity": 4,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_active_school_allocation_post_rejected(self):
        student_a = self._make_student(
            self.school_a, self.campus_a1, "ALLOC-A-003"
        )
        room = Room.objects.create(
            hostel=self.hostel_a1, room_number="A-ALLOC-3", capacity=4
        )
        self._as_no_school(self.admin_a)
        response = self.client.post(
            "/api/hostel/allocations/",
            {
                "room": room.pk,
                "student": student_a.pk,
                "start_date": "2026-09-01",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            Allocation.objects.filter(room=room).exists()
        )

    def test_missing_active_school_vacate_fails_closed(self):
        student_a = self._make_student(
            self.school_a, self.campus_a1, "ALLOC-A-004"
        )
        alloc = self._make_allocation(
            self.hostel_a1, "A-ALLOC-4", student_a
        )
        self._as_no_school(self.admin_a)
        response = self.client.post(
            f"/api/hostel/allocations/{alloc.pk}/vacate/"
        )
        self.assertEqual(response.status_code, 404)
        alloc.refresh_from_db()
        self.assertEqual(alloc.status, "active")

    def test_cross_school_allocation_create_rejected(self):
        """School A user must never allocate a School B student or room."""
        student_b = self._make_student(
            self.school_b, self.campus_b1, "ALLOC-B-002"
        )
        student_a = self._make_student(
            self.school_a, self.campus_a1, "ALLOC-A-005"
        )
        room_a = Room.objects.create(
            hostel=self.hostel_a1, room_number="A-ALLOC-5", capacity=4
        )
        room_b = Room.objects.create(
            hostel=self.hostel_b1, room_number="B-ALLOC-2", capacity=4
        )
        self._as(self.admin_a)

        # Foreign room + foreign student.
        response = self.client.post(
            "/api/hostel/allocations/",
            {
                "room": room_b.pk,
                "student": student_b.pk,
                "start_date": "2026-09-01",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "room", response.json(),
            "error should name the room field",
        )

        # Active-school student but foreign room.
        response = self.client.post(
            "/api/hostel/allocations/",
            {
                "room": room_b.pk,
                "student": student_a.pk,
                "start_date": "2026-09-01",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        # Active-school room but foreign student.
        response = self.client.post(
            "/api/hostel/allocations/",
            {
                "room": room_a.pk,
                "student": student_b.pk,
                "start_date": "2026-09-01",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "student", response.json(),
            "error should name the student field",
        )

        # No allocation row was created for School B.
        self.assertFalse(
            Allocation.objects.filter(room=room_b).exists()
        )

    def test_cross_school_allocation_vacate_rejected(self):
        student_b = self._make_student(
            self.school_b, self.campus_b1, "ALLOC-B-003"
        )
        alloc_b = self._make_allocation(
            self.hostel_b1, "B-ALLOC-3", student_b
        )
        self._as(self.admin_a)
        response = self.client.post(
            f"/api/hostel/allocations/{alloc_b.pk}/vacate/"
        )
        self.assertEqual(response.status_code, 404)
        alloc_b.refresh_from_db()
        self.assertEqual(alloc_b.status, "active")

    def test_stale_or_invalid_active_school_fails_closed(self):
        """Stale/invalid session school → 403, zero data, no silent fallback.

        The session explicitly points at a school the user is NOT authorized
        for (School B — they only belong to School A) or at a nonexistent
        school. Per §5A "Unauthorized school must never become a fallback"
        the request must be REJECTED (403), never silently re-served against
        the user's first membership.
        """
        student_a = self._make_student(
            self.school_a, self.campus_a1, "ALLOC-A-006"
        )
        student_b = self._make_student(
            self.school_b, self.campus_b1, "ALLOC-B-004"
        )
        self._make_allocation(
            self.hostel_a1, "A-ALLOC-6", student_a
        )
        self._make_allocation(
            self.hostel_b1, "B-ALLOC-4", student_b
        )

        self._as(self.admin_a)

        for stale_id in (self.school_b.pk, 999999):
            with self.subTest(stale_id=stale_id):
                # The middleware self-heals the session after a rejected
                # request, so re-assert the stale context before EACH call.
                self._set_active_school(stale_id)
                response = self.client.get("/api/hostel/allocations/")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json().get("results", []), [],
                    "a stale context must not fall back to any school's data",
                )

                self._set_active_school(stale_id)
                response = self.client.get("/api/students/?page_size=1000")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json().get("results", []), [],
                    "the allocation student selector must reject a stale context",
                )

                self._set_active_school(stale_id)
                response = self.client.get("/api/hostel/rooms/")
                self.assertEqual(response.status_code, 403)

    def test_stale_active_school_allocation_create_rejected(self):
        """Stale/unauthorized context rejects writes too — never a silent fallback."""
        student_a = self._make_student(
            self.school_a, self.campus_a1, "ALLOC-A-008"
        )
        room_a = Room.objects.create(
            hostel=self.hostel_a1, room_number="A-ALLOC-8", capacity=4
        )

        self._as(self.admin_a)
        self._set_active_school(self.school_b.pk)

        response = self.client.post(
            "/api/hostel/allocations/",
            {
                "room": room_a.pk,
                "student": student_a.pk,
                "start_date": "2026-09-01",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Allocation.objects.filter(room=room_a).exists()
        )

    def test_inactive_school_selector_fails_closed(self):
        """An inactive school can never feed the allocation student selector.

        `get_active_memberships()` filters the membership row only, so the
        inactive school still resolves to ``request.institution``; the
        selector must reject it with 403 rather than serve its students
        (ModuleAccessMiddleware covers /api/hostel/* but /api/students/* is
        core SIS, so the guard must live in the view).
        """
        school_c = School.objects.create(
            name="Inactive Hostel School", code="hstl-c", status="inactive"
        )
        campus_c = Campus.objects.create(
            school=school_c, name="Campus C", status="active"
        )
        member_c = make_user("hstl-inactive-mgr", Role.ADMIN, school_c)

        self._make_student(school_c, campus_c, "ALLOC-C-001")
        self._make_student(self.school_a, self.campus_a1, "ALLOC-A-009")

        self._as(member_c)
        self._set_active_school(school_c.pk)

        response = self.client.get("/api/students/?page_size=1000")
        self.assertEqual(response.status_code, 403)

        response = self.client.get("/api/hostel/allocations/")
        self.assertEqual(response.status_code, 403)

    def test_students_selector_fails_closed_without_active_school(self):
        """The allocation student selector never returns all-school students."""
        self._make_student(self.school_a, self.campus_a1, "ALLOC-A-007")
        self._make_student(self.school_b, self.campus_b1, "ALLOC-B-005")

        self._as_no_school(self.admin_a)
        data = self.client.get("/api/students/?page_size=1000").json()
        body = data.get("results", data)
        self.assertEqual([], body)
