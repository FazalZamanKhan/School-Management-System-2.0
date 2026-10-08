from django.core.exceptions import ValidationError
from django.db import models  # type: ignore[import]

from apps.core.models import SoftDeleteMixin, SoftDeleteManager
from apps.schools.models import School


class Teacher(SoftDeleteMixin):
    objects = SoftDeleteManager()
    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    institution = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="teachers",
        null=True,
        blank=True,
    )

    employee_number = models.CharField(
        max_length=50,
    )

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teacher_profile",
    )

    membership = models.OneToOneField("accounts.InstitutionMembership", on_delete=models.SET_NULL, null=True, blank=True, related_name="teacher_profile")
    primary_campus = models.ForeignKey("schools.Campus", on_delete=models.SET_NULL, null=True, blank=True, related_name="primary_teachers")

    photo = models.ImageField(
        upload_to="profiles/teachers/",
        blank=True,
        null=True,
    )

    first_name = models.CharField(
        max_length=100,
    )

    last_name = models.CharField(
        max_length=100,
    )

    gender = models.CharField(
        max_length=20,
        choices=GENDER_CHOICES,
    )

    date_of_birth = models.DateField(
        null=True,
        blank=True,
    )

    phone = models.CharField(
        max_length=30,
        blank=True,
    )

    email = models.EmailField(
        blank=True,
    )

    campus = models.CharField(
        max_length=150,
        blank=True,
    )

    joining_date = models.DateField(
        null=True,
        blank=True,
    )

    designation = models.CharField(
        max_length=100,
        default="Teacher",
    )

    department = models.CharField(
        max_length=100,
        blank=True,
    )

    qualification = models.CharField(
        max_length=200,
        blank=True,
    )

    experience_years = models.PositiveIntegerField(
        default=0,
    )

    address = models.TextField(
        blank=True,
    )

    bank_name = models.CharField(
        max_length=120,
        blank=True,
    )

    account_number = models.CharField(
        max_length=40,
        blank=True,
        help_text="Bank account number or IBAN for payroll transfers.",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["first_name", "last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "employee_number"],
                name="unique_teacher_employee_number_per_institution",
            )
        ]
        indexes = [
            models.Index(
                fields=["institution", "status"],
                name="teacher_inst_status_idx",
            ),
            models.Index(
                fields=["primary_campus", "status"],
                name="teacher_campus_status_idx",
            ),
            models.Index(
                fields=["last_name", "first_name"],
                name="teacher_name_idx",
            ),
        ]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_number})"

    def clean(self):
        errors = {}
        for field in ("first_name", "last_name"):
            value = getattr(self, field, "")
            if value and not any(char.isalpha() for char in value):
                errors[field] = "Enter a name containing at least one letter."
        if self.membership_id and self.user_id and self.membership.user_id != self.user_id:
            errors["membership"] = "Membership must belong to this user."
        if self.membership_id and self.primary_campus_id and self.primary_campus.school_id != self.membership.institution_id:
            errors["primary_campus"] = "Campus must belong to the membership institution."
        if errors:
            raise ValidationError(errors)


class TeacherAssignment(models.Model):
    """Links a teacher to a campus/class/section/subject for a year.

    The ``role`` field decides what the assignment means:

    - ``class_teacher``: the teacher is the homeroom/class teacher for the
      section. This is the "his class" used to scope what a teacher can see.
    - ``subject_teacher``: the teacher teaches the subject in that section.
    - ``coordinator``: extra responsibility.
    """

    ROLE_CHOICES = [
        ("subject_teacher", "Subject Teacher"),
        ("class_teacher", "Class Teacher"),
        ("coordinator", "Coordinator"),
    ]

    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name="assignments",
    )

    campus = models.ForeignKey(
        "schools.Campus",
        on_delete=models.PROTECT,
        related_name="teacher_assignments",
    )

    class_obj = models.ForeignKey(
        "schools.Class",
        on_delete=models.PROTECT,
        related_name="teacher_assignments",
    )

    section = models.ForeignKey(
        "schools.Section",
        on_delete=models.PROTECT,
        related_name="teacher_assignments",
    )

    subject = models.ForeignKey(
        "schools.Subject",
        on_delete=models.PROTECT,
        related_name="teacher_assignments",
    )

    academic_year = models.ForeignKey(
        "schools.AcademicYear",
        on_delete=models.PROTECT,
        related_name="teacher_assignments",
    )

    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default="subject_teacher",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["class_obj", "section", "subject"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "teacher",
                    "class_obj",
                    "section",
                    "subject",
                    "academic_year",
                ],
                name="unique_teacher_assignment",
            )
        ]
        indexes = [
            models.Index(
                fields=["teacher", "academic_year", "status"],
                name="tassign_teacher_yr_status_idx",
            ),
            models.Index(
                fields=["campus", "class_obj", "section", "status"],
                name="tassign_campus_cls_sec_idx",
            ),
            models.Index(
                fields=["academic_year", "status"],
                name="tassign_year_status_idx",
            ),
        ]

    def clean(self):
        errors = {}

        if self.class_obj_id and self.campus_id:
            if self.class_obj.unit.campus_id != self.campus_id:
                errors["class_obj"] = (
                    "The selected class does not belong to the selected campus."
                )

        if self.section_id and self.class_obj_id:
            if self.section.class_obj_id != self.class_obj_id:
                errors["section"] = (
                    "The selected section does not belong to the selected class."
                )

        if self.academic_year_id and self.campus_id:
            if (
                self.academic_year.school_id
                != self.campus.school_id
            ):
                errors["academic_year"] = (
                    "The academic year does not belong "
                    "to the campus school."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.teacher} - {self.get_role_display()} - "
            f"{self.class_obj.name} - {self.section.name}"
        )
