
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from apps.core.models import SoftDeleteMixin, SoftDeleteManager
from apps.schools.models import AcademicYear, Campus, Class, Section


class Guardian(SoftDeleteMixin):
    objects = SoftDeleteManager()
    institution = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="guardians",
        null=True,
        blank=True,
    )

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guardian_profile",
    )

    name = models.CharField(max_length=200)
    relationship = models.CharField(max_length=50)
    phone = models.CharField(max_length=30)
    alternate_phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.relationship})"


class Inquiry(SoftDeleteMixin):
    """Initial inquiry from prospective parents/students before formal application."""

    STATUS_CHOICES = [
        ("new", "New"),
        ("contacted", "Contacted"),
        ("interested", "Interested"),
        ("application_started", "Application Started"),
        ("converted", "Converted to Application"),
        ("lost", "Lost"),
        ("closed", "Closed"),
    ]

    SOURCE_CHOICES = [
        ("website", "Website"),
        ("walk_in", "Walk-in"),
        ("phone", "Phone"),
        ("email", "Email"),
        ("referral", "Referral"),
        ("social_media", "Social Media"),
        ("event", "Event/Open House"),
        ("other", "Other"),
    ]

    objects = SoftDeleteManager()

    institution = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="inquiries",
        null=True,
        blank=True,
    )

    inquiry_number = models.CharField(max_length=50, unique=True)

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)

    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=10,
        choices=[("male", "Male"), ("female", "Female")],
        blank=True,
    )

    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)

    guardian_name = models.CharField(max_length=200, blank=True)
    guardian_phone = models.CharField(max_length=30, blank=True)
    guardian_email = models.EmailField(blank=True)
    guardian_relationship = models.CharField(max_length=50, blank=True)

    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, null=True, blank=True)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, null=True, blank=True)
    class_obj = models.ForeignKey(Class, on_delete=models.PROTECT, null=True, blank=True)

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="website")
    source_details = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")

    assigned_to = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_inquiries",
    )

    notes = models.TextField(blank=True)

    # Conversion tracking
    admission_application = models.OneToOneField(
        "AdmissionApplication",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_inquiry",
    )

    converted_at = models.DateTimeField(null=True, blank=True)
    converted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="converted_inquiries",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["institution", "status"], name="inquiry_inst_status_idx"),
            models.Index(fields=["status", "created_at"], name="inquiry_status_date_idx"),
            models.Index(fields=["phone", "email"], name="inquiry_contact_idx"),
        ]

    def __str__(self):
        return f"{self.inquiry_number} - {self.applicant_name}"

    @property
    def applicant_name(self):
        return " ".join(
            part for part in [self.first_name, self.middle_name, self.last_name] if part
        )

    def convert_to_application(self, user, **application_data):
        """Convert this inquiry to an AdmissionApplication."""
        if self.status == "converted":
            raise ValidationError("This inquiry has already been converted to an application.")

        if self.admission_application:
            raise ValidationError("This inquiry is already linked to an application.")

        # Create the application
        application = AdmissionApplication.objects.create(
            institution=self.institution,
            first_name=self.first_name,
            middle_name=self.middle_name,
            last_name=self.last_name,
            date_of_birth=self.date_of_birth,
            gender=self.gender,
            phone=self.phone,
            email=self.email,
            address=self.address,
            guardian_name=self.guardian_name,
            guardian_phone=self.guardian_phone,
            guardian_email=self.guardian_email,
            guardian_relationship=self.guardian_relationship,
            campus=self.campus,
            academic_year=self.academic_year,
            class_obj=self.class_obj,
            status="draft",
            **application_data,
        )

        # Link and update
        self.admission_application = application
        self.status = "converted"
        self.converted_at = timezone.now()
        self.converted_by = user
        self.save(update_fields=["admission_application", "status", "converted_at", "converted_by", "updated_at"])

        return application


class StudentGuardian(models.Model):
    student = models.ForeignKey(
        "Student",
        on_delete=models.CASCADE,
        related_name="guardian_links",
    )
    guardian = models.ForeignKey(
        Guardian,
        on_delete=models.CASCADE,
        related_name="guardian_links",
    )
    relationship = models.CharField(max_length=50)
    is_primary = models.BooleanField(default=False)
    can_pick_up = models.BooleanField(default=False)
    is_emergency_contact = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "guardian"],
                name="unique_student_guardian_link",
            ),
        ]
        ordering = ["-is_primary", "guardian__name"]

    def __str__(self):
        return f"{self.student.full_name} - {self.guardian.name}"


class AdmissionApplication(models.Model):
    institution = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="admission_applications_tenant",
        null=True,
        blank=True,
    )

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("under_review", "Under review"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("withdrawn", "Withdrawn"),
    ]

    application_number = models.CharField(max_length=50, unique=True)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=10,
        choices=[
            ("male", "Male"),
            ("female", "Female"),
        ],
    )
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    guardian = models.ForeignKey(
        Guardian,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="admission_applications",
    )
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT)
    class_obj = models.ForeignKey(Class, on_delete=models.PROTECT)
    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_admission_applications",
    )
    review_notes = models.TextField(blank=True)
    student = models.OneToOneField(
        "Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admission_application",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        errors = {}
        if self.date_of_birth and self.date_of_birth > timezone.localdate():
            errors["date_of_birth"] = "Date of birth cannot be in the future."
        if self.class_obj_id and self.campus_id:
            if self.class_obj.unit.campus_id != self.campus_id:
                errors["class_obj"] = "The selected class does not belong to the selected campus."
        if self.section_id and self.class_obj_id:
            if self.section.class_obj_id != self.class_obj_id:
                errors["section"] = "The selected section does not belong to the selected class."
        if self.academic_year_id and self.campus_id:
            if self.academic_year.school_id != self.campus.school_id:
                errors["academic_year"] = "The academic year does not belong to the selected school."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def applicant_name(self):
        return " ".join(part for part in [self.first_name, self.middle_name, self.last_name] if part)


class Meta:
        ordering = ["-effective_date", "-created_at"]


class AcademicHistory(SoftDeleteMixin):
    """Track student's academic progression through years, classes, and campuses."""

    objects = SoftDeleteManager()

    student = models.ForeignKey(
        "Student",
        on_delete=models.CASCADE,
        related_name="academic_history",
    )

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="academic_history_records",
    )

    campus = models.ForeignKey(
        Campus,
        on_delete=models.PROTECT,
        related_name="academic_history_records",
    )

    class_obj = models.ForeignKey(
        Class,
        on_delete=models.PROTECT,
        related_name="academic_history_records",
    )

    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="academic_history_records",
    )

    roll_number = models.CharField(max_length=20, blank=True)

    enrollment_date = models.DateField()
    withdrawal_date = models.DateField(null=True, blank=True)

    final_status = models.CharField(
        max_length=20,
        choices=[
            ("completed", "Completed"),
            ("withdrawn", "Withdrawn"),
            ("transferred", "Transferred"),
            ("promoted", "Promoted"),
            ("retained", "Retained"),
        ],
        default="completed",
    )

    promotion_status = models.CharField(
        max_length=20,
        choices=[
            ("promoted", "Promoted"),
            ("retained", "Retained"),
            ("not_applicable", "Not Applicable"),
        ],
        default="not_applicable",
        blank=True,
    )

    final_grade = models.CharField(max_length=10, blank=True)
    final_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    attendance_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-academic_year__start_date", "student__admission_number"]
        indexes = [
            models.Index(
                fields=["student", "academic_year"],
                name="academic_hist_stu_year_idx",
            ),
            models.Index(
                fields=["campus", "academic_year", "final_status"],
                name="academic_hist_cmp_yr_sts_idx",
            ),
        ]

    def __str__(self):
        return f"{self.student.full_name} - {self.academic_year.name} ({self.final_status})"

    def clean(self):
        errors = {}
        if self.campus_id and self.class_obj_id:
            if self.class_obj.unit.campus_id != self.campus_id:
                errors["class_obj"] = "The selected class does not belong to the selected campus."
        if self.section_id and self.class_obj_id:
            if self.section.class_obj_id != self.class_obj_id:
                errors["section"] = "The selected section does not belong to the selected class."
        if self.academic_year_id and self.campus_id:
            if self.academic_year.school_id != self.campus.school_id:
                errors["academic_year"] = "The academic year does not belong to the selected campus's school."
        if self.withdrawal_date and self.enrollment_date and self.withdrawal_date < self.enrollment_date:
            errors["withdrawal_date"] = "Withdrawal date must be on or after enrollment date."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class StudentLifecycleEvent(models.Model):
    institution = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="student_lifecycle_events",
        null=True,
        blank=True,
    )

    EVENT_CHOICES = [
        ("activated", "Activated"),
        ("inactive", "Marked inactive"),
        ("withdrawn", "Withdrawn"),
        ("transferred", "Transferred"),
        ("graduated", "Graduated"),
    ]

    student = models.ForeignKey(
        "Student",
        on_delete=models.CASCADE,
        related_name="lifecycle_events",
    )
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    effective_date = models.DateField()
    reason = models.TextField(blank=True)
    from_campus = models.ForeignKey(
        Campus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lifecycle_events_from",
    )
    to_campus = models.ForeignKey(
        Campus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lifecycle_events_to",
    )
    from_enrollment = models.ForeignKey(
        "Enrollment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lifecycle_events_from",
    )
    to_enrollment = models.ForeignKey(
        "Enrollment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lifecycle_events_to",
    )
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_student_lifecycle_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date", "-created_at"]


class Student(SoftDeleteMixin):
    objects = SoftDeleteManager()
    institution = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="students",
        null=True,
        blank=True,
    )

    admission_number = models.CharField(
        max_length=50,
        help_text="School-scoped admission number. Must be unique within the same institution.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "admission_number"],
                name="unique_admission_number_per_institution",
            ),
        ]

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_profile",
    )

    membership = models.OneToOneField("accounts.InstitutionMembership", on_delete=models.SET_NULL, null=True, blank=True, related_name="student_profile")
    primary_campus = models.ForeignKey(Campus, on_delete=models.SET_NULL, null=True, blank=True, related_name="primary_students")

    photo = models.ImageField(
        upload_to="profiles/students/",
        blank=True,
        null=True,
    )

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)

    date_of_birth = models.DateField(
        null=True,
        blank=True,
    )

    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
    ]

    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
    )

    guardian = models.ForeignKey(
        Guardian,
        on_delete=models.PROTECT,
        related_name="students",
    )

    phone = models.CharField(
        max_length=30,
        blank=True,
    )

    address = models.TextField(blank=True)

    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("graduated", "Graduated"),
        ("withdrawn", "Withdrawn"),
    ]

    # Valid status transitions: from_status -> list of allowed to_status
    STATUS_TRANSITIONS = {
        "active": ["inactive", "withdrawn", "graduated"],
        "inactive": ["active", "withdrawn"],
        "graduated": [],  # Terminal state
        "withdrawn": ["active"],  # Re-admission
    }

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    admission_date = models.DateField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "admission_number"],
                name="unique_admission_number_per_institution",
            )
        ]
        indexes = [
            models.Index(
                fields=["institution", "status"],
                name="student_inst_status_idx",
            ),
            models.Index(
                fields=["primary_campus", "status"],
                name="student_campus_status_idx",
            ),
            models.Index(
                fields=["last_name", "first_name"],
                name="student_name_idx",
            ),
        ]

    def __str__(self):
        return f"{self.admission_number} - {self.full_name}"

    def clean(self):
        if self.membership_id and self.user_id and self.membership.user_id != self.user_id:
            raise ValidationError({"membership": "Membership must belong to this user."})
        if self.membership_id and self.primary_campus_id and self.primary_campus.school_id != self.membership.institution_id:
            raise ValidationError({"primary_campus": "Campus must belong to the membership institution."})

    def can_transition_to(self, new_status):
        """Check if transition from current status to new_status is allowed."""
        if self.status == new_status:
            return True
        return new_status in self.STATUS_TRANSITIONS.get(self.status, [])

    def transition_status(self, new_status, user, reason="", effective_date=None):
        """
        Transition student status with validation and audit trail.
        
        Args:
            new_status: Target status
            user: User performing the transition
            reason: Reason for transition
            effective_date: Date when transition takes effect (defaults to today)
        
        Returns:
            StudentLifecycleEvent instance
        
        Raises:
            ValidationError: If transition is not allowed
        """
        from django.utils import timezone
        
        if not self.can_transition_to(new_status):
            raise ValidationError(
                f"Cannot transition from '{self.status}' to '{new_status}'. "
                f"Allowed transitions: {self.STATUS_TRANSITIONS.get(self.status, [])}"
            )

        if effective_date is None:
            effective_date = timezone.now().date()

        old_status = self.status
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])

        # Create lifecycle event
        event = StudentLifecycleEvent.objects.create(
            institution=self.institution,
            student=self,
            event_type=new_status,
            effective_date=effective_date,
            reason=reason,
            recorded_by=user,
        )

        # Update enrollment status based on student status
        active_enrollment = self.enrollments.filter(status="active").first()
        if active_enrollment:
            if new_status in ["withdrawn", "graduated", "inactive"]:
                active_enrollment.status = "completed" if new_status == "graduated" else "withdrawn"
                active_enrollment.save(update_fields=["status", "updated_at"])

        return event

    def request_campus_transfer(self, user, to_campus, academic_year, reason="", effective_date=None):
        """Request a campus transfer."""
        from django.utils import timezone
        
        if effective_date is None:
            effective_date = timezone.now().date()
        
        if not self.can_transition_to("active"):
            raise ValidationError("Student must be active to request a campus transfer.")
        
        active_enrollment = self.enrollments.filter(status="active").first()
        if not active_enrollment:
            raise ValidationError("Student must have an active enrollment to request a transfer.")
        
        if active_enrollment.campus_id == to_campus.id:
            raise ValidationError("Student is already enrolled at the target campus.")
        
        if active_enrollment.campus.school_id != to_campus.school_id:
            raise ValidationError("Cannot transfer to a campus in a different school.")
        
        if academic_year.school_id != to_campus.school_id:
            raise ValidationError("Academic year must belong to the target campus's school.")
        
        transfer = CampusTransfer.objects.create(
            student=self,
            from_campus=active_enrollment.campus,
            to_campus=to_campus,
            academic_year=academic_year,
            effective_date=effective_date,
            reason=reason,
            requested_by=user,
            status="requested",
        )
        
        StudentLifecycleEvent.objects.create(
            institution=self.institution,
            student=self,
            event_type="transferred",
            effective_date=effective_date,
            reason=f"Campus transfer requested: {reason}",
            from_campus=active_enrollment.campus,
            to_campus=to_campus,
            from_enrollment=active_enrollment,
            recorded_by=user,
        )
        
        return transfer

    def request_section_transfer(self, user, to_section, academic_year, transfer_type="section", reason="", effective_date=None):
        """Request a section or class transfer within the same campus."""
        from django.utils import timezone
        
        if effective_date is None:
            effective_date = timezone.now().date()
        
        active_enrollment = self.enrollments.filter(status="active").first()
        if not active_enrollment:
            raise ValidationError("Student must have an active enrollment to request a transfer.")
        
        if active_enrollment.section_id == to_section.id:
            raise ValidationError("Student is already in the target section/class.")
        
        if active_enrollment.section.class_obj.unit.campus_id != to_section.class_obj.unit.campus_id:
            raise ValidationError("Cannot transfer to a section in a different campus.")
        
        if academic_year.school_id != to_section.class_obj.unit.campus.school_id:
            raise ValidationError("Academic year must belong to the target section's school.")
        
        if transfer_type == "class" and to_section.class_obj.level is not None:
            current_level = active_enrollment.class_obj.level
            target_level = to_section.class_obj.level
            if target_level < current_level:
                raise ValidationError("Cannot transfer to a lower class level.")
        
        transfer = SectionTransfer.objects.create(
            student=self,
            transfer_type=transfer_type,
            from_section=active_enrollment.section,
            to_section=to_section,
            academic_year=academic_year,
            effective_date=effective_date,
            reason=reason,
            requested_by=user,
            status="requested",
        )
        
        StudentLifecycleEvent.objects.create(
            institution=self.institution,
            student=self,
            event_type="transferred",
            effective_date=effective_date,
            reason=f"Section/Class transfer requested: {reason}",
            from_campus=active_enrollment.campus,
            to_campus=active_enrollment.campus,
            from_enrollment=active_enrollment,
            recorded_by=user,
        )
        
        return transfer

    def withdraw(self, user, reason="", effective_date=None):
        """Withdraw the student."""
        return self.transition_status("withdrawn", user, reason, effective_date)

    def graduate(self, user, graduation_date=None, reason="", **alumni_kwargs):
        """Graduate the student and create alumni record."""
        if not self.can_transition_to("graduated"):
            raise ValidationError("Student cannot be graduated from current status.")
        
        if graduation_date is None:
            from django.utils import timezone
            graduation_date = timezone.now().date()
        
        # Create alumni record
        from .models import StudentAlumni
        alumni = StudentAlumni.create_from_graduation(
            student=self,
            user=user,
            graduation_date=graduation_date,
            reason=reason,
            **alumni_kwargs,
        )
        
        return alumni

    def withdraw(self, user, reason="", effective_date=None):
        """Withdraw the student."""
        if not self.can_transition_to("withdrawn"):
            raise ValidationError("Student cannot be withdrawn from current status.")
        
        return self.transition_status("withdrawn", user, reason, effective_date)

    def activate(self, user, reason="", effective_date=None):
        """Reactivate a withdrawn/inactive student."""
        if not self.can_transition_to("active"):
            raise ValidationError("Student cannot be activated from current status.")
        
        return self.transition_status("active", user, reason, effective_date)
        return f"{self.admission_number} - {self.full_name}"

    def clean(self):
        if self.membership_id and self.user_id and self.membership.user_id != self.user_id:
            raise ValidationError({"membership": "Membership must belong to this user."})
        if self.membership_id and self.primary_campus_id and self.primary_campus.school_id != self.membership.institution_id:
            raise ValidationError({"primary_campus": "Campus must belong to the membership institution."})

    @property
    def full_name(self):
        return " ".join(
            part
            for part in [
                self.first_name,
                self.middle_name,
                self.last_name,
            ]
            if part
        )

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = timezone.now().date()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )


class Enrollment(models.Model):
    
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="student_enrollments",
    )

    campus = models.ForeignKey(
        Campus,
        on_delete=models.PROTECT,
        related_name="student_enrollments",
    )

    class_obj = models.ForeignKey(
        Class,
        on_delete=models.PROTECT,
        related_name="student_enrollments",
    )

    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="student_enrollments",
    )

    roll_number = models.CharField(max_length=20, blank=True)

    STATUS_CHOICES = [
        ("active", "Active"),
        ("completed", "Completed"),
        ("withdrawn", "Withdrawn"),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    enrollment_date = models.DateField(
        auto_now_add=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["student__first_name", "student__last_name"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "student",
                    "academic_year",
                ],
                name="unique_student_per_academic_year",
            )
        ]
        indexes = [
            models.Index(
                fields=["campus", "status"],
                name="enrollment_campus_status_idx",
            ),
            models.Index(
                fields=["class_obj", "section", "status"],
                name="enrollment_class_section_idx",
            ),
            models.Index(
                fields=["academic_year", "status"],
                name="enrollment_year_status_idx",
            ),
        ]

    def clean(self):
        errors = {}

        # ---------------------------------------------------------
        # 1. Make sure the selected class belongs to the campus
        # ---------------------------------------------------------
        if self.campus_id and self.class_obj_id:
            if self.class_obj.unit.campus_id != self.campus_id:
                errors["class_obj"] = (
                    "The selected class does not belong to the selected campus."
                )

        # ---------------------------------------------------------
        # 2. Make sure the selected section belongs to the class
        # ---------------------------------------------------------
        if self.class_obj_id and self.section_id:
            if self.section.class_obj_id != self.class_obj_id:
                errors["section"] = (
                    "The selected section does not belong to the selected class."
                )

        # ---------------------------------------------------------
        # 3. Make sure Academic Year belongs to the same school
        #    as the selected campus
        # ---------------------------------------------------------
        if self.academic_year_id and self.campus_id:
            if self.academic_year.school_id != self.campus.school_id:
                errors["academic_year"] = (
                    "The selected academic year does not belong "
                    "to the selected campus's school."
                )

        if errors:
            raise ValidationError(errors)
        
        # Run campus assignment validation
        # super().clean()  # Removed CampusAssignmentValidationMixin

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.student.full_name} - "
            f"{self.academic_year.name} - "
            f"{self.class_obj.name} - "
            f"{self.section.name}"
        )


class StudentDocument(SoftDeleteMixin):
    institution = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="student_documents",
        null=True,
        blank=True,
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    DOCUMENT_TYPE_CHOICES = [
        ("birth_certificate", "Birth Certificate"),
        ("b_form", "B-Form / CNIC"),
        ("report_card", "Report Card"),
        ("transfer_certificate", "Transfer Certificate"),
        ("fee_challan", "Fee Challan"),
        ("medical", "Medical Record"),
        ("other", "Other"),
    ]

    document_type = models.CharField(
        max_length=30,
        choices=DOCUMENT_TYPE_CHOICES,
    )

    title = models.CharField(max_length=200)
    file = models.FileField(
        upload_to="students/documents/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    "pdf",
                    "doc",
                    "docx",
                    "jpg",
                    "jpeg",
                    "png",
                    "gif",
                ],
            ),
        ],
    )
    notes = models.TextField(blank=True)

    uploaded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_student_documents",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student.admission_number} - {self.title}"


class CampusTransfer(SoftDeleteMixin):
    """Track campus transfers for students with full history."""

    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    objects = SoftDeleteManager()

    student = models.ForeignKey(
        "Student",
        on_delete=models.CASCADE,
        related_name="campus_transfers",
    )

    from_campus = models.ForeignKey(
        Campus,
        on_delete=models.PROTECT,
        related_name="transfers_from",
    )

    to_campus = models.ForeignKey(
        Campus,
        on_delete=models.PROTECT,
        related_name="transfers_to",
    )

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="campus_transfers",
    )

    effective_date = models.DateField()

    reason = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="requested")

    # Approval workflow
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_campus_transfers",
    )

    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_campus_transfers",
    )

    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    # Completion
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_campus_transfers",
    )

    # Reversal
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversed_campus_transfers",
    )
    reversal_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["student", "status"],
                name="ct_student_status_idx",
            ),
            models.Index(
                fields=["from_campus", "to_campus", "status"],
                name="ct_campus_status_idx",
            ),
            models.Index(
                fields=["academic_year", "status"],
                name="ct_year_status_idx",
            ),
        ]

    def __str__(self):
        return f"{self.student.full_name}: {self.from_campus.name} -> {self.to_campus.name} ({self.status})"

    def clean(self):
        errors = {}
        if self.from_campus_id and self.to_campus_id:
            if self.from_campus_id == self.to_campus_id:
                errors["to_campus"] = "Cannot transfer to the same campus."
            if self.from_campus.school_id != self.to_campus.school_id:
                errors["to_campus"] = "Cannot transfer to a campus in a different school."
        if errors:
            raise ValidationError(errors)

    def approve(self, user, notes=""):
        """Approve the transfer request."""
        from django.utils import timezone
        self.status = "approved"
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"])
        return self

    def reject(self, user, notes=""):
        """Reject the transfer request."""
        from django.utils import timezone
        self.status = "rejected"
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"])
        return self

    def complete(self, user):
        """Mark the transfer as completed and update student's primary campus."""
        from django.utils import timezone
        if self.status != "approved":
            raise ValidationError("Only approved transfers can be completed.")
        
        with transaction.atomic():
            # Update student's primary campus
            self.student.primary_campus = self.to_campus
            self.student.save(update_fields=["primary_campus", "updated_at"])

            # Update active enrollment campus
            active_enrollment = self.student.enrollments.filter(status="active").first()
            if active_enrollment:
                active_enrollment.campus = self.to_campus
                active_enrollment.save(update_fields=["campus", "updated_at"])

            self.status = "completed"
            self.completed_at = timezone.now()
            self.completed_by = user
            self.save(update_fields=["status", "completed_at", "completed_by", "updated_at"])
        return self

    def cancel(self, user):
        """Cancel the transfer request."""
        if self.status in ["completed", "cancelled"]:
            raise ValidationError(f"Cannot cancel a {self.status} transfer.")
        self.status = "cancelled"
        self.save(update_fields=["status", "updated_at"])
        return self

    def reverse(self, user, reason=""):
        """Reverse a completed transfer."""
        if self.status != "completed":
            raise ValidationError("Only completed transfers can be reversed.")
        
        with transaction.atomic():
            # Revert student's primary campus
            self.student.primary_campus = self.from_campus
            self.student.save(update_fields=["primary_campus", "updated_at"])

            # Revert active enrollment campus
            active_enrollment = self.student.enrollments.filter(status="active").first()
            if active_enrollment:
                active_enrollment.campus = self.from_campus
                active_enrollment.save(update_fields=["campus", "updated_at"])

            self.status = "reversed"
            self.reversed_at = timezone.now()
            self.reversed_by = user
            self.reversal_reason = reason
            self.save(update_fields=["status", "reversed_at", "reversed_by", "reversal_reason", "updated_at"])
        return self


class SectionTransfer(SoftDeleteMixin):
    """Track section/class transfers within the same campus."""

    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    TRANSFER_TYPE_CHOICES = [
        ("section", "Section Transfer"),
        ("class", "Class Transfer"),
    ]

    objects = SoftDeleteManager()

    student = models.ForeignKey(
        "Student",
        on_delete=models.CASCADE,
        related_name="section_transfers",
    )

    transfer_type = models.CharField(max_length=10, choices=TRANSFER_TYPE_CHOICES)

    from_section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="transfers_from",
    )

    to_section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="transfers_to",
    )

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="section_transfers",
    )

    effective_date = models.DateField()

    reason = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="requested")

    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_section_transfers",
    )

    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_section_transfers",
    )

    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_section_transfers",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["student", "status"],
                name="st_student_status_idx",
            ),
            models.Index(
                fields=["from_section", "to_section", "status"],
                name="st_section_status_idx",
            ),
        ]

    def __str__(self):
        if self.transfer_type == "section":
            return f"{self.student.full_name}: {self.from_section.name} -> {self.to_section.name} ({self.status})"
        return f"{self.student.full_name}: {self.from_section.class_obj.name} -> {self.to_section.class_obj.name} ({self.status})"

    def clean(self):
        errors = {}
        if self.from_section_id and self.to_section_id:
            if self.from_section_id == self.to_section_id:
                errors["to_section"] = "Cannot transfer to the same section/class."
            
            # Ensure same campus for section transfers
            if self.from_section.class_obj.unit.campus_id != self.to_section.class_obj.unit.campus_id:
                errors["to_section"] = "Cannot transfer to a section in a different campus."
            
            # For class transfers, ensure same academic unit or valid progression
            if self.transfer_type == "class":
                if self.from_section.class_obj.level is not None and self.to_section.class_obj.level is not None:
                    if self.to_section.class_obj.level < self.from_section.class_obj.level:
                        errors["to_section"] = "Cannot transfer to a lower class level."

        if errors:
            raise ValidationError(errors)

    def approve(self, user, notes=""):
        """Approve the section/class transfer."""
        from django.utils import timezone
        self.status = "approved"
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"])
        return self

    def reject(self, user, notes=""):
        """Reject the transfer request."""
        from django.utils import timezone
        self.status = "rejected"
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"])
        return self

    def complete(self, user):
        """Complete the section/class transfer."""
        from django.utils import timezone
        if self.status != "approved":
            raise ValidationError("Only approved transfers can be completed.")
        
        with transaction.atomic():
            # Update enrollment
            active_enrollment = self.student.enrollments.filter(
                academic_year=self.academic_year,
                status="active"
            ).first()
            
            if active_enrollment:
                active_enrollment.section = self.to_section
                active_enrollment.class_obj = self.to_section.class_obj
                active_enrollment.save(update_fields=["section", "class_obj", "updated_at"])
                
                # Update student's primary campus if needed
                if self.student.primary_campus_id != self.to_section.class_obj.unit.campus_id:
                    self.student.primary_campus = self.to_section.class_obj.unit.campus
                    self.student.save(update_fields=["primary_campus", "updated_at"])

            self.status = "completed"
            self.completed_at = timezone.now()
            self.completed_by = user
            self.save(update_fields=["status", "completed_at", "completed_by", "updated_at"])
        return self

    def cancel(self, user):
        """Cancel the transfer request."""
        if self.status in ["completed", "cancelled"]:
            raise ValidationError(f"Cannot cancel a {self.status} transfer.")
        self.status = "cancelled"
        self.save(update_fields=["status", "updated_at"])
        return self


class TransferCertificate(SoftDeleteMixin):
    """Transfer Certificate issued when a student transfers out or graduates."""

    objects = SoftDeleteManager()

    institution = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="transfer_certificates",
        null=True,
        blank=True,
    )

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("issued", "Issued"),
        ("cancelled", "Cancelled"),
    ]

    student = models.ForeignKey(
        "Student",
        on_delete=models.CASCADE,
        related_name="transfer_certificates",
    )

    certificate_number = models.CharField(max_length=50, unique=True)

    issue_date = models.DateField(default=timezone.now)

    # Student info at time of issue
    admission_number = models.CharField(max_length=50)
    full_name = models.CharField(max_length=300)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10)

    guardian_name = models.CharField(max_length=200)
    guardian_relationship = models.CharField(max_length=50)
    guardian_phone = models.CharField(max_length=30)

    # Academic info
    campus = models.ForeignKey(
        Campus,
        on_delete=models.PROTECT,
        related_name="transfer_certificates",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="transfer_certificates",
    )
    class_obj = models.ForeignKey(
        Class,
        on_delete=models.PROTECT,
        related_name="transfer_certificates",
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="transfer_certificates",
    )
    roll_number = models.CharField(max_length=20, blank=True)

    admission_date = models.DateField()
    leaving_date = models.DateField()

    reason = models.CharField(
        max_length=50,
        choices=[
            ("transfer", "Transfer to Another School"),
            ("graduation", "Graduation"),
            ("withdrawal", "Withdrawal"),
            ("expulsion", "Expulsion"),
            ("other", "Other"),
        ],
        default="transfer",
    )

    reason_details = models.TextField(blank=True)

    # Academic performance
    final_grade = models.CharField(max_length=10, blank=True)
    final_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    attendance_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # Conduct and character
    conduct = models.CharField(
        max_length=20,
        choices=[
            ("excellent", "Excellent"),
            ("good", "Good"),
            ("satisfactory", "Satisfactory"),
            ("needs_improvement", "Needs Improvement"),
        ],
        default="good",
    )

    # Issuance
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    issued_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issued_transfer_certificates",
    )
    issued_at = models.DateTimeField(null=True, blank=True)

    # Verification
    verification_code = models.CharField(max_length=50, unique=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issue_date", "-created_at"]
        indexes = [
            models.Index(
                fields=["student", "status"],
                name="tc_student_status_idx",
            ),
            models.Index(
                fields=["campus", "academic_year", "status"],
                name="tc_campus_year_status_idx",
            ),
            models.Index(
                fields=["verification_code"],
                name="tc_verification_code_idx",
            ),
        ]

    def __str__(self):
        return f"{self.certificate_number} - {self.full_name}"

    def clean(self):
        errors = {}
        if self.campus_id and self.class_obj_id:
            if self.class_obj.unit.campus_id != self.campus_id:
                errors["class_obj"] = "The selected class does not belong to the selected campus."
        if self.section_id and self.class_obj_id:
            if self.section.class_obj_id != self.class_obj_id:
                errors["section"] = "The selected section does not belong to the selected class."
        if self.academic_year_id and self.campus_id:
            if self.academic_year.school_id != self.campus.school_id:
                errors["academic_year"] = "The academic year does not belong to the selected campus's school."
        if self.leaving_date and self.admission_date and self.leaving_date < self.admission_date:
            errors["leaving_date"] = "Leaving date must be on or after admission date."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        # Generate verification code if not set
        if not self.verification_code:
            import uuid
            self.verification_code = str(uuid.uuid4())[:8].upper()
        return super().save(*args, **kwargs)

    def issue(self, user):
        """Issue the transfer certificate."""
        from django.utils import timezone
        self.status = "issued"
        self.issued_by = user
        self.issued_at = timezone.now()
        self.save(update_fields=["status", "issued_by", "issued_at", "updated_at"])
        return self

    def cancel(self, user):
        """Cancel the transfer certificate."""
        self.status = "cancelled"
        self.save(update_fields=["status", "updated_at"])
        return self


class StudentLeaveRequest(models.Model):
    institution = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="student_leave_requests",
        null=True,
        blank=True,
    )

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="leave_requests",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="requested_student_leave",
    )
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_student_leave",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        errors = {}
        if self.end_date < self.start_date:
            errors["end_date"] = "End date must be on or after the start date."
        if not self.reason.strip():
            errors["reason"] = "A reason is required."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class StudentAlumni(SoftDeleteMixin):
    """Alumni record for graduated/withdrawn students."""

    objects = SoftDeleteManager()

    GRADUATION_STATUS_CHOICES = [
        ("graduated", "Graduated"),
        ("withdrawn", "Withdrawn"),
        ("expelled", "Expelled"),
        ("transferred_out", "Transferred Out"),
    ]

    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name="student_alumni_profile",
    )

    institution = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="student_alumni_records",
    )

    graduation_status = models.CharField(
        max_length=20,
        choices=GRADUATION_STATUS_CHOICES,
    )

    graduation_date = models.DateField()

    # Academic info at graduation
    final_campus = models.ForeignKey(
        Campus,
        on_delete=models.PROTECT,
        related_name="graduated_students",
    )
    final_class = models.ForeignKey(
        Class,
        on_delete=models.PROTECT,
        related_name="graduated_students",
        null=True,
        blank=True,
    )
    final_section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="graduated_students",
        null=True,
        blank=True,
    )
    final_academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="graduated_students",
    )
    final_grade = models.CharField(max_length=10, blank=True)
    final_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    attendance_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    final_grade_letter = models.CharField(max_length=5, blank=True)

    # Conduct
    conduct = models.CharField(
        max_length=20,
        choices=[
            ("excellent", "Excellent"),
            ("good", "Good"),
            ("satisfactory", "Satisfactory"),
            ("needs_improvement", "Needs Improvement"),
        ],
        default="good",
    )

    # Contact info (for alumni relations)
    personal_email = models.EmailField(blank=True)
    personal_phone = models.CharField(max_length=30, blank=True)
    current_address = models.TextField(blank=True)
    linkedin_profile = models.URLField(blank=True)

    # Further education / career
    current_institution = models.CharField(max_length=200, blank=True)
    current_program = models.CharField(max_length=200, blank=True)
    current_occupation = models.CharField(max_length=200, blank=True)
    current_employer = models.CharField(max_length=200, blank=True)

    # Alumni engagement
    is_active = models.BooleanField(default=True)
    last_contact_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-graduation_date"]
        indexes = [
            models.Index(
                fields=["institution", "graduation_status"],
                name="alumni_inst_status_idx",
            ),
            models.Index(
                fields=["graduation_date"],
                name="alumni_grad_date_idx",
            ),
            models.Index(
                fields=["is_active"],
                name="alumni_active_idx",
            ),
        ]

    def __str__(self):
        return f"{self.student.full_name} - {self.get_graduation_status_display()} ({self.graduation_date})"

    def clean(self):
        errors = {}
        if self.graduation_date and self.student.admission_date:
            if self.graduation_date < self.student.admission_date:
                errors["graduation_date"] = "Graduation date must be on or after admission date."
        if errors:
            raise ValidationError(errors)

    @classmethod
    def create_from_graduation(cls, student, user, graduation_date=None, **kwargs):
        """Create alumni record when a student graduates."""
        from django.utils import timezone

        if graduation_date is None:
            graduation_date = timezone.now().date()
        elif isinstance(graduation_date, str):
            try:
                graduation_date = (
                    timezone.datetime.strptime(
                        graduation_date, "%Y-%m-%d"
                    ).date()
                )
            except ValueError:
                raise ValidationError(
                    "graduation date must be in YYYY-MM-DD format."
                )

        # Get current enrollment info
        active_enrollment = student.enrollments.filter(status="active").first()

        # Pop reason for lifecycle event — StudentAlumni has no reason field
        reason = kwargs.pop("reason", "Graduated")

        alumni = cls.objects.create(
            student=student,
            institution=student.institution,
            graduation_status="graduated",
            graduation_date=graduation_date,
            final_campus=student.primary_campus or (active_enrollment.campus if active_enrollment else None),
            final_class=active_enrollment.class_obj if active_enrollment else None,
            final_section=active_enrollment.section if active_enrollment else None,
            final_academic_year=active_enrollment.academic_year if active_enrollment else None,
            **kwargs
        )

        # Create lifecycle event
        StudentLifecycleEvent.objects.create(
            institution=student.institution,
            student=student,
            event_type="graduated",
            effective_date=graduation_date,
            reason=reason,
            recorded_by=user,
        )

        # Bridge into the alumni directory so graduated students
        # automatically appear in the school's alumni network.
        try:
            from apps.alumni.models import AlumniProfile

            AlumniProfile.objects.get_or_create(
                student=student,
                defaults={
                    "institution": student.institution,
                    "campus": active_enrollment.campus if active_enrollment else student.primary_campus,
                    "full_name": student.full_name,
                    "batch_year": alumni.graduation_date.year,
                    "phone": student.phone or "",
                },
            )
        except Exception:
            # Never let an alumni-directory failure block graduation.
            pass

        # Update student status
        student.status = "graduated"
        student.save(update_fields=["status", "updated_at"])

        return alumni


class ProgressionRecord(SoftDeleteMixin):
    """
    Immutable audit/history record for any academic progression: promotion,
    demotion, class transfer, section transfer, or campus transfer.

    Preserves the full 'previous -> new' transition so that historical data
    is never lost when an enrollment changes.
    """

    ACTION_CHOICES = [
        ("promotion", "Promotion"),
        ("demotion", "Demotion"),
        ("class_transfer", "Class Transfer"),
        ("section_transfer", "Section Transfer"),
        ("campus_transfer", "Campus Transfer"),
    ]

    objects = SoftDeleteManager()

    student = models.ForeignKey(
        "Student",
        on_delete=models.CASCADE,
        related_name="progression_records",
    )

    action = models.CharField(max_length=20, choices=ACTION_CHOICES)

    # Previous state
    from_academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="progression_from",
        null=True,
        blank=True,
    )
    from_class = models.ForeignKey(
        Class,
        on_delete=models.PROTECT,
        related_name="progression_from",
        null=True,
        blank=True,
    )
    from_section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="progression_from",
        null=True,
        blank=True,
    )
    from_campus = models.ForeignKey(
        Campus,
        on_delete=models.PROTECT,
        related_name="progression_from",
        null=True,
        blank=True,
    )

    # New state
    to_academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="progression_to",
        null=True,
        blank=True,
    )
    to_class = models.ForeignKey(
        Class,
        on_delete=models.PROTECT,
        related_name="progression_to",
        null=True,
        blank=True,
    )
    to_section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="progression_to",
        null=True,
        blank=True,
    )
    to_campus = models.ForeignKey(
        Campus,
        on_delete=models.PROTECT,
        related_name="progression_to",
        null=True,
        blank=True,
    )

    effective_date = models.DateField(default=timezone.now)

    performed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performed_progressions",
    )

    reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-effective_date", "-created_at"]
        indexes = [
            models.Index(
                fields=["student", "action"],
                name="prog_student_action_idx",
            ),
            models.Index(
                fields=["from_academic_year", "to_academic_year"],
                name="prog_years_idx",
            ),
            models.Index(
                fields=["from_campus", "to_campus"],
                name="prog_campuses_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.student.full_name} - {self.get_action_display()} "
            f"({self.effective_date})"
        )

    def clean(self):
        errors = {}
        if self.effective_date and self.from_academic_year_id:
            if (
                self.from_academic_year.start_date
                and self.effective_date < self.from_academic_year.start_date
            ):
                errors["effective_date"] = (
                    "Effective date cannot be earlier than the previous "
                    "academic year's start date."
                )
        if errors:
            raise ValidationError(errors)

