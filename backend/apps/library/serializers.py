from rest_framework import serializers

from apps.students.models import Student

from .models import Book, BookCopy, BookIssue, BookReservation


class BookCopySerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source="book.title", read_only=True)
    campus_name = serializers.CharField(source="book.campus.name", read_only=True, default="")

    class Meta:
        model = BookCopy
        fields = ["id", "book", "book_title", "barcode", "status", "campus_name", "created_at"]
        read_only_fields = ["barcode", "created_at"]

    def create(self, validated_data):
        book_copy = BookCopy.objects.create(**validated_data)
        if not book_copy.barcode:
            book_copy.barcode = f"{book_copy.book.pk:04d}-{book_copy.pk or ''}".rstrip("-")
            book_copy.save(update_fields=["barcode"])
        return book_copy


class BookSerializer(serializers.ModelSerializer):
    campus_name = serializers.CharField(
        source="campus.name",
        read_only=True,
        default="",
    )
    available_copies = serializers.IntegerField(read_only=True)
    issued_copies = serializers.IntegerField(read_only=True)
    copies = BookCopySerializer(many=True, read_only=True)
    category_display = serializers.CharField(
        source="get_category_display",
        read_only=True,
    )

    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "campus",
            "campus_name",
            "author",
            "isbn",
            "publisher",
            "publication_year",
            "category",
            "category_display",
            "description",
            "total_copies",
            "available_copies",
            "issued_copies",
            "copies",
        ]

    def create(self, validated_data):
        total_copies = validated_data.pop("total_copies", 1)
        book = Book.objects.create(total_copies=total_copies, **validated_data)

        for _ in range(total_copies):
            BookCopy.objects.create(book=book)

        return book

    def update(self, instance, validated_data):
        total_copies = validated_data.pop("total_copies", None)

        for key, value in validated_data.items():
            setattr(instance, key, value)

        instance.save()

        if total_copies is not None:
            existing = instance.copies.count()

            if total_copies > existing:
                for _ in range(total_copies - existing):
                    BookCopy.objects.create(book=instance)
            elif total_copies < existing:
                instance.copies.filter(status="available")[:existing - total_copies].delete()

        return instance


class BookIssueSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(
        source="book_copy.book.title",
        read_only=True,
    )
    barcode = serializers.CharField(
        source="book_copy.barcode",
        read_only=True,
    )
    student_name = serializers.CharField(
        source="student.full_name",
        read_only=True,
        default="",
    )
    teacher_name = serializers.CharField(
        source="teacher.full_name",
        read_only=True,
        default="",
    )
    borrower = serializers.CharField(read_only=True)

    class Meta:
        model = BookIssue
        fields = [
            "id",
            "book_copy",
            "book_title",
            "barcode",
            "student",
            "student_name",
            "teacher",
            "teacher_name",
            "borrower",
            "issue_date",
            "due_date",
            "return_date",
            "fine",
            "status",
        ]
        read_only_fields = ["issue_date", "status"]


class BookReservationSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source="book.title", read_only=True)
    borrower_name = serializers.SerializerMethodField()
    borrower_type = serializers.SerializerMethodField()
    queue_position = serializers.IntegerField(read_only=True)

    class Meta:
        model = BookReservation
        fields = [
            "id",
            "book",
            "book_title",
            "student",
            "teacher",
            "borrower_name",
            "borrower_type",
            "status",
            "requested_at",
            "fulfilled_at",
            "expires_at",
            "queue_position",
            "pickup_deadline",
        ]
        read_only_fields = ["id", "status", "requested_at", "fulfilled_at", "queue_position"]

    def get_borrower_name(self, obj):
        if obj.student_id:
            return obj.student.full_name
        if obj.teacher_id:
            return obj.teacher.full_name
        return ""

    def get_borrower_type(self, obj):
        if obj.student_id:
            return "student"
        if obj.teacher_id:
            return "teacher"
        return ""


class BookReservationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookReservation
        fields = ["book", "student", "teacher"]

    def validate(self, attrs):
        student = attrs.get("student")
        teacher = attrs.get("teacher")

        if student and teacher:
            raise serializers.ValidationError(
                "Reservation must be for either a student or a teacher, not both."
            )
        if not student and not teacher:
            raise serializers.ValidationError(
                "Reservation must be for a student or a teacher."
            )
        return attrs

    def create(self, validated_data):
        # Check if there's already a pending reservation for this user/book
        book = validated_data["book"]
        student = validated_data.get("student")
        teacher = validated_data.get("teacher")

        existing = BookReservation.objects.filter(
            book=book,
            status="pending",
        )
        if student:
            existing = existing.filter(student=student)
        elif teacher:
            existing = existing.filter(teacher=teacher)

        if existing.exists():
            raise serializers.ValidationError(
                "You already have a pending reservation for this book."
            )

        validated_data["status"] = "pending"
        return super().create(validated_data)


class LibraryMemberSerializer(serializers.ModelSerializer):
    """Minimal identity fields for a library member listing.

    Deliberately narrow: this only exposes what's needed to identify a
    borrower (matches the fields already used for this purpose elsewhere,
    e.g. BookIssueSerializer.student_name / admission_number), not the
    full Student record (guardians, documents, enrollments, etc.).
    """

    class Meta:
        model = Student
        fields = ["id", "full_name", "admission_number"]
