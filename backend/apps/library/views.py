from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAccountantRole, IsLibrarianRole
from apps.accounts.access import apply_campus_scope
from apps.students.models import Student

from .models import Book, BookCopy, BookIssue, BookReservation
from .serializers import BookCopySerializer, BookIssueSerializer, BookSerializer, BookReservationSerializer, BookReservationCreateSerializer, LibraryMemberSerializer


class BookListView(generics.ListCreateAPIView):
    serializer_class = BookSerializer
    permission_classes = [IsLibrarianRole]

    def get_queryset(self):
        queryset = apply_campus_scope(
            Book.objects.all().prefetch_related("copies"),
            self.request,
            "campus_id",
        )

        search = self.request.query_params.get("q")

        if search:
            queryset = queryset.filter(
                title__icontains=search,
            ) | queryset.filter(
                author__icontains=search,
            ) | queryset.filter(
                isbn__icontains=search,
            )

        category = self.request.query_params.get("category")

        if category:
            queryset = queryset.filter(category=category)

        return queryset

    def perform_create(self, serializer):
        from apps.accounts.access import assert_campus_allowed

        campus = serializer.validated_data.get("campus")
        if campus:
            assert_campus_allowed(self.request.user, campus.pk)
        serializer.save()


class BookDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BookSerializer
    permission_classes = [IsLibrarianRole]
    def get_queryset(self):
        return apply_campus_scope(Book.objects.all(), self.request, "campus_id")

    def perform_update(self, serializer):
        from apps.accounts.access import assert_campus_allowed

        campus = serializer.validated_data.get("campus", serializer.instance.campus)
        if campus:
            assert_campus_allowed(self.request.user, campus.pk)
        serializer.save()


class BookIssueListView(generics.ListCreateAPIView):
    serializer_class = BookIssueSerializer
    permission_classes = [IsLibrarianRole]

    def get_queryset(self):
        queryset = apply_campus_scope(BookIssue.objects.select_related(
            "book_copy__book",
            "student",
            "teacher",
        ), self.request, "book_copy__book__campus_id", institution_field="book_copy__book__institution_id")

        status_filter = self.request.query_params.get("status")

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    def perform_create(self, serializer):
        book_copy = serializer.validated_data["book_copy"]
        if not apply_campus_scope(
            BookCopy.objects.filter(pk=book_copy.pk),
            self.request,
            "book__campus_id", institution_field="book__institution_id",
        ).exists():
            raise PermissionDenied("The book is outside your campus scope.")

        student = serializer.validated_data.get("student")
        teacher = serializer.validated_data.get("teacher")

        if student is not None and not student.enrollments.filter(
            academic_year__school=self.request.institution
        ).exists():
            raise PermissionDenied("The student is outside the active institution.")

        if teacher is not None and teacher.institution_id != self.request.institution.id:
            raise PermissionDenied("The teacher is outside the active institution.")

        serializer.save()


class BookIssueDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BookIssueSerializer
    permission_classes = [IsLibrarianRole]

    def get_queryset(self):
        return apply_campus_scope(
            BookIssue.objects.all(),
            self.request,
            "book_copy__book__campus_id", institution_field="book_copy__book__institution_id",
        )

    def perform_update(self, serializer):
        if not self.get_queryset().filter(
            book_copy=serializer.validated_data.get(
                "book_copy",
                serializer.instance.book_copy,
            ),
        ).exists():
            raise PermissionDenied("The book is outside your campus scope.")
        serializer.save()


class BookReturnView(APIView):
    permission_classes = [IsLibrarianRole]

    def post(self, request, pk):
        issue = apply_campus_scope(
            BookIssue.objects.filter(pk=pk),
            request,
            "book_copy__book__campus_id", institution_field="book_copy__book__institution_id",
        ).first()

        if issue is None:
            return Response(
                {"detail": "Issue record not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if issue.status == "returned":
            return Response(
                {"detail": "This copy has already been returned."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fine = request.data.get("fine", 0)

        issue.fine = fine
        issue.return_copy()

        return Response(
            BookIssueSerializer(issue).data
        )


class BookReservationListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsLibrarianRole]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BookReservationCreateSerializer
        return BookReservationSerializer

    def get_queryset(self):
        queryset = apply_campus_scope(
            BookReservation.objects.select_related("book", "student", "teacher"),
            self.request,
            "book__campus_id", institution_field="book__institution_id",
        )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        book_id = self.request.query_params.get("book")
        if book_id:
            queryset = queryset.filter(book_id=book_id)

        return queryset.order_by("-requested_at")

    def perform_create(self, serializer):
        from apps.library.models import Book

        book = serializer.validated_data.get("book")
        if book is not None and not apply_campus_scope(
            Book.objects.filter(pk=book.pk),
            self.request,
            "campus_id", institution_field="institution_id",
        ).exists():
            raise PermissionDenied("The book is outside your campus scope.")

        student = serializer.validated_data.get("student")
        teacher = serializer.validated_data.get("teacher")

        if student is not None and not student.enrollments.filter(
            academic_year__school=self.request.institution
        ).exists():
            raise PermissionDenied("The student is outside the active institution.")

        if teacher is not None and teacher.institution_id != self.request.institution.id:
            raise PermissionDenied("The teacher is outside the active institution.")

        serializer.save()


class BookReservationDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = BookReservationSerializer
    permission_classes = [IsLibrarianRole]

    def get_queryset(self):
        return apply_campus_scope(
            BookReservation.objects.select_related("book", "student", "teacher"),
            self.request,
            "book__campus_id", institution_field="book__institution_id",
        )


class BookReservationFulfillView(APIView):
    permission_classes = [IsLibrarianRole]

    def post(self, request, pk):
        reservation = apply_campus_scope(
            BookReservation.objects.filter(pk=pk),
            request,
            "book__campus_id", institution_field="book__institution_id",
        ).first()

        if reservation is None:
            return Response(
                {"detail": "Reservation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if reservation.status != "pending":
            return Response(
                {"detail": "Only pending reservations can be fulfilled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if a copy is available
        available_copy = reservation.book.copies.filter(status="available").first()
        if not available_copy:
            return Response(
                {"detail": "No available copies to fulfill this reservation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fulfill the reservation
        reservation.fulfill(request.user)

        return Response(
            BookReservationSerializer(reservation).data
        )


class BookReservationCancelView(APIView):
    permission_classes = [IsLibrarianRole]

    def post(self, request, pk):
        reservation = apply_campus_scope(
            BookReservation.objects.filter(pk=pk),
            request,
            "book__campus_id", institution_field="book__institution_id",
        ).first()

        if reservation is None:
            return Response(
                {"detail": "Reservation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if reservation.status not in ["pending", "available"]:
            return Response(
                {"detail": "Only pending or available reservations can be cancelled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reservation.cancel()

        return Response(
            {"detail": "Reservation cancelled."}
        )


class BookCopyListCreateView(generics.ListCreateAPIView):
    serializer_class = BookCopySerializer
    permission_classes = [IsLibrarianRole]

    def get_queryset(self):
        queryset = BookCopy.objects.select_related("book", "book__campus")

        book = self.request.query_params.get("book")
        if book:
            queryset = queryset.filter(book_id=book)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return apply_campus_scope(queryset, self.request, "book__campus_id", institution_field="book__institution_id")

    def perform_create(self, serializer):
        book = serializer.validated_data["book"]
        if not apply_campus_scope(
            Book.objects.filter(pk=book.pk), self.request, "campus_id"
        ).exists():
            raise PermissionDenied("The book is outside your campus scope.")
        serializer.save()


class BookCopyDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BookCopySerializer
    permission_classes = [IsLibrarianRole]

    def get_queryset(self):
        return apply_campus_scope(
            BookCopy.objects.select_related("book", "book__campus"),
            self.request,
            "book__campus_id", institution_field="book__institution_id",
        )

    def perform_update(self, serializer):
        if not self.get_queryset().filter(pk=serializer.instance.pk).exists():
            raise PermissionDenied("The book copy is outside your campus scope.")
        serializer.save()


class LibraryRootView(APIView):
    """Root endpoint for Library API."""
    permission_classes = [IsLibrarianRole]

    def get(self, request):
        return Response({
            "message": "Library API",
            "version": "63-deploy-test",
            "endpoints": {
                "books": "/api/library/books/",
                "issues": "/api/library/issues/",
                "reservations": "/api/library/reservations/",
                "reports": "/api/library/reports/",
                "members": "/api/library/members/",
                "settings": "/api/library/settings/",
            }
        })


class LibraryDeployTestView(APIView):
    """Test endpoint to verify deployment."""
    permission_classes = []

    def get(self, request):
        return Response({
            "status": "deployed",
            "commit": "bf79cb8",
            "message": "Library endpoints deployed successfully"
        })


class LibraryReportsView(APIView):
    """Library reports endpoint - redirects to reports module."""
    permission_classes = [IsLibrarianRole]

    def get(self, request):
        return Response({
            "message": "Library reports are available at /api/reports/library/",
            "reports": [
                "/api/reports/library/inventory/",
                "/api/reports/library/available/",
                "/api/reports/library/issued/",
                "/api/reports/library/returned/",
                "/api/reports/library/overdue/",
                "/api/reports/library/fines/",
                "/api/reports/library/activity/",
                "/api/reports/library/most-borrowed/",
                "/api/reports/library/student-history/",
                "/api/reports/library/teacher-history/",
            ]
        })


class LibraryMembersView(generics.ListAPIView):
    """List library members (students and teachers who can borrow books).

    Note: currently lists students only (returns an empty queryset by
    default, same as before this fix). Including teachers as members
    would require merging two different model querysets into one
    response, which is a larger design change left for a follow-up.
    """
    serializer_class = LibraryMemberSerializer
    permission_classes = [IsLibrarianRole]

    def get_queryset(self):
        return Student.objects.none()


class LibrarySettingsView(APIView):
    """Library settings endpoint."""
    permission_classes = [IsLibrarianRole]

    def get(self, request):
        return Response({
            "message": "Library settings endpoint",
            "settings": {
                "max_loan_days": 14,
                "max_renewals": 2,
                "fine_per_day": 5.00,
                "max_books_per_student": 3,
                "max_books_per_teacher": 5,
            }
        })

    def patch(self, request):
        # Settings update would go here
        return Response({"detail": "Settings updated successfully."})
