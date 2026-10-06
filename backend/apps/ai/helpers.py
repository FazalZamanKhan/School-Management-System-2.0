"""Shared fixture builders for the AI app's P5 tests."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.accounts.models import (
    InstitutionMembership,
    Role,
    RoleAssignment,
    StaffProfile,
)
from apps.attendance.models import Attendance
from apps.exams.models import Exam, ExamSubject, StudentResult
from apps.finance.models import FeeCategory, Invoice, InvoiceItem
from apps.schools.models import (
    AcademicUnit,
    AcademicYear,
    Campus,
    Class,
    School,
    Section,
    Subject,
)
from apps.students.models import Enrollment, Guardian, Student
from apps.teachers.models import Teacher, TeacherAssignment


def make_school(name, code):
    return School.objects.create(name=name, code=code)


def make_member_user(school, username, role, password="TestPass123!", campus=None):
    user = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@test.edu",
        password=password,
    )
    membership = InstitutionMembership.objects.create(
        user=user,
        institution=school,
    )
    RoleAssignment.objects.create(membership=membership, role=role, campus=campus)
    return user


def make_superuser(username, password="TestPass123!"):
    return get_user_model().objects.create_user(
        username=username,
        email=f"{username}@test.edu",
        password=password,
        is_superuser=True,
    )


def make_student(school, structure, name="Student One", admission=None, campus=None):
    guardian = Guardian.objects.create(
        institution=school,
        name="Guardian",
        phone="0700000000",
        relationship="Parent",
    )
    first, last = name.split(" ", 1) if " " in name else (name, "Surname")
    student = Student.objects.create(
        institution=school,
        admission_number=admission or f"ADM-{Student.objects.count() + 1}",
        first_name=first,
        last_name=last,
        gender="male",
        guardian=guardian,
        phone="0700000001",
        status="active",
    )
    Enrollment.objects.create(
        student=student,
        academic_year=structure["year"],
        campus=campus or structure["campus"],
        class_obj=structure["class_obj"],
        section=structure["section"],
        status="active",
    )
    return student


def make_teacher(user, membership, school, structure, first="Tea", last="Cher"):
    teacher = Teacher.objects.create(
        user=user,
        membership=membership,
        institution=school,
        primary_campus=structure["campus"],
        employee_number=f"TCH-{first.upper()}",
        first_name=first,
        last_name=last,
        gender="male",
    )
    TeacherAssignment.objects.create(
        teacher=teacher,
        campus=structure["campus"],
        class_obj=structure["class_obj"],
        section=structure["section"],
        subject=structure["subject"],
        academic_year=structure["year"],
        role="class_teacher",
        status="active",
    )
    return teacher


def make_staff_profile(user, membership, school, campus):
    return StaffProfile.objects.create(
        user=user,
        membership=membership,
        institution=school,
        primary_campus=campus,
        employee_number=f"STF-{user.username.upper()}",
        first_name=user.username,
        last_name="Staff",
        gender="male",
    )


def make_attendance(student, structure, day, status="present"):
    enrollment = Enrollment.objects.get(student=student, status="active")
    return Attendance.objects.create(
        student=student,
        enrollment=enrollment,
        academic_year=structure["year"],
        campus=structure["campus"],
        class_obj=structure["class_obj"],
        section=structure["section"],
        date=day,
        status=status,
    )


def make_exam(school, structure, name="Mid-Term", start_offset=10, end_offset=5):
    return Exam.objects.create(
        name=name,
        exam_type="midterm",
        academic_year=structure["year"],
        campus=structure["campus"],
        class_obj=structure["class_obj"],
        start_date=date.today() - timedelta(days=start_offset),
        end_date=date.today() - timedelta(days=end_offset),
        status="completed",
    )


def ensure_subject_offering(school, structure):
    from apps.schools.models import SubjectOffering

    SubjectOffering.objects.get_or_create(
        subject=structure["subject"],
        class_obj=structure["class_obj"],
        academic_year=structure["year"],
        defaults={"status": "active"},
    )


def make_structure(school, campus_name="Main", year_name="2025-2026"):
    campus = Campus.objects.create(school=school, name=campus_name)
    unit = AcademicUnit.objects.create(campus=campus, name="Primary")
    class_obj = Class.objects.create(unit=unit, name="Grade 6")
    section = Section.objects.create(class_obj=class_obj, name="A")
    code = "MATH" if campus_name == "Main" else f"MATH-{campus_name.upper()}"
    subject = Subject.objects.create(institution=school, name="Mathematics", code=code)
    year = AcademicYear.objects.create(
        school=school,
        name=year_name,
        start_date=date(2025, 8, 1),
        end_date=date(2026, 7, 31),
    )
    return {
        "campus": campus,
        "class_obj": class_obj,
        "section": section,
        "subject": subject,
        "year": year,
    }


def make_exam_result(exam, student, structure, marks, passing_marks=50, maximum=100):
    ensure_subject_offering(school=exam.academic_year.school, structure=structure)
    exam_subject = ExamSubject.objects.create(
        exam=exam,
        subject=structure["subject"],
        maximum_marks=maximum,
        passing_marks=passing_marks,
    )
    return StudentResult.objects.create(
        exam=exam,
        student=student,
        exam_subject=exam_subject,
        obtained_marks=Decimal(str(marks)),
        is_absent=False,
        grade="A" if marks >= passing_marks else "F",
        is_pass=marks >= passing_marks,
    )


def make_fee_category(name="Tuition"):
    return FeeCategory.objects.create(name=name, frequency="monthly")


def make_invoice(school, student, structure, number, amount, due_days_ago, status="issued"):
    enrollment = Enrollment.objects.get(student=student, status="active")
    invoice = Invoice.objects.create(
        invoice_number=number,
        institution=school,
        student=student,
        enrollment=enrollment,
        academic_year=structure["year"],
        campus=structure["campus"],
        issue_date=date.today() - timedelta(days=due_days_ago + 10),
        due_date=date.today() - timedelta(days=due_days_ago),
        status=status,
    )
    InvoiceItem.objects.create(
        invoice=invoice,
        category=make_fee_category(),
        description="Tuition",
        amount=Decimal(str(amount)),
    )
    return invoice
