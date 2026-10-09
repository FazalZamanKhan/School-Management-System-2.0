from datetime import date

from rest_framework.test import APITestCase
from apps.accounts.models import Role
from apps.accounts.test_access import make_user
from apps.ai.helpers import make_school, make_structure, make_student
from apps.schools.models import AcademicYear
from apps.students.models import Enrollment, Student


class StudentCountReconciliationTests(APITestCase):
    def setUp(self):
        self.school = make_school("Student counts A", "COUNT-A")
        self.tree = make_structure(self.school)
        self.owned = make_student(self.school, self.tree, name="Owned Student")
        self.legacy = make_student(self.school, self.tree, name="Legacy Student")
        Student.objects.filter(pk=self.legacy.pk).update(institution=None)
        other = make_school("Student counts B", "COUNT-B")
        self.foreign = make_student(other, make_structure(other), name="Foreign Student")
        # Untagged, entirely unowned legacy records must not inflate school totals.
        self.unowned = Student.objects.create(admission_number="UNOWNED", first_name="Unowned", last_name="Student", gender="male", guardian=self.owned.guardian)
        self.admin = make_user("count-admin", Role.ADMIN, self.school)
        self.client.force_login(self.admin)

    def assert_counts(self, expected):
        students = self.client.get("/api/students/")
        overview = self.client.get("/api/dashboard/overview/")
        executive = self.client.get("/api/dashboard/executive/")
        for response in (students, overview, executive):
            self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertEqual(students.json()["count"], expected)
        self.assertEqual(overview.json()["students"]["total"], expected)
        self.assertEqual(executive.json()["summary"]["students"]["total"], expected)

    def test_list_overview_and_executive_include_owned_legacy_students_once(self):
        extra_year = AcademicYear.objects.create(school=self.school, name="Another year", start_date=date(2027, 8, 1), end_date=date(2028, 7, 31))
        Enrollment.objects.create(student=self.legacy, academic_year=extra_year, campus=self.tree["campus"], class_obj=self.tree["class_obj"], section=self.tree["section"])
        self.assert_counts(2)

    def test_empty_school_does_not_count_unowned_or_foreign_legacy_students(self):
        empty = make_school("Empty counts", "EMPTY-COUNT")
        self.client.force_login(make_user("empty-count-admin", Role.ADMIN, empty))
        self.assert_counts(0)

    def test_explicit_foreign_owner_is_not_overridden_by_an_enrollment(self):
        Enrollment.objects.create(student=self.foreign, academic_year=self.tree["year"], campus=self.tree["campus"], class_obj=self.tree["class_obj"], section=self.tree["section"])
        self.assert_counts(2)

    def test_campus_counts_follow_enrollment_when_primary_campus_is_missing(self):
        north = make_structure(self.school, campus_name="North", year_name="North year")
        make_student(self.school, north, name="North Student")
        campus_admin = make_user("campus-count-admin", Role.CAMPUS_ADMIN, self.school, campus=self.tree["campus"])
        self.client.force_login(campus_admin)
        self.assert_counts(2)
