from django.test import TestCase

from apps.accounts.models import Role, StaffProfile
from apps.accounts.test_access import make_request, make_user
from apps.library.models import Book
from apps.library.views import BookListView, LibraryMembersView
from apps.schools.models import Campus, School


class BookCampusIsolationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Library School")
        self.campus_a = Campus.objects.create(school=self.school, name="Campus A")
        self.campus_b = Campus.objects.create(school=self.school, name="Campus B")
        self.user = make_user("library-admin", Role.CAMPUS_ADMIN, self.school, campus=self.campus_a)
        StaffProfile.objects.create(
            user=self.user,
            institution=self.school,
            employee_number="LIB-001",
            first_name="Library",
            last_name="Admin",
            gender="female",
            primary_campus=self.campus_a,
        )

    def test_book_list_includes_own_and_school_wide_books_only(self):
        own = Book.objects.create(
            title="Campus A book",
            isbn="LIB-TEST-001",
            campus=self.campus_a,
        )
        Book.objects.create(
            title="Campus B book",
            isbn="LIB-TEST-002",
            campus=self.campus_b,
        )
        school_wide = Book.objects.create(
            title="Shared book",
            isbn="LIB-TEST-003",
        )

        request = make_request(self.user)
        request.institution = self.school
        view = BookListView()
        view.request = request

        qs = view.get_queryset()
        self.assertIn(own, qs)
        self.assertIn(school_wide, qs)
        self.assertFalse(qs.filter(isbn="LIB-TEST-002").exists())


class LibraryMembersViewTests(TestCase):
    """Regression: GET /api/library/members/ must return a valid response
    instead of crashing. It previously had no serializer_class, so DRF's
    ListAPIView raised when trying to serialize the (empty) queryset,
    producing an HTTP 500.
    """

    def setUp(self):
        self.school = School.objects.create(name="Library School")
        self.user = make_user("librarian-x", Role.LIBRARIAN, self.school)

    def test_members_endpoint_returns_200_instead_of_500(self):
        request = make_request(self.user, path="/api/library/members/")
        response = LibraryMembersView.as_view()(request._request)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])
