import { useCallback, useEffect, useState } from "react";
import {
  GraduationCap,
  UserPlus,
  Trash2,
  BookOpen,
} from "lucide-react";
import { PageHeader } from "./ui";

const TEACHERS_URL = "/api/teachers/";
const STUDENTS_URL = "/api/students/";
const ASSIGNMENTS_URL = "/api/teachers/assignments/";
const ENROLLMENTS_URL = "/api/students/enrollments/";
const CAMPUSES_URL = "/api/schools/campuses/";
const UNITS_URL = "/api/schools/units/";
const CLASSES_URL = "/api/schools/classes/";
const SECTIONS_URL = "/api/schools/sections/";
const SUBJECTS_URL = "/api/schools/subjects/";
const YEARS_URL = "/api/schools/academic-years/";

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);

  if (parts.length === 2) {
    return parts.pop().split(";").shift();
  }

  return null;
}

async function fetchAllPages(url) {
  const all = [];
  let next = url;

  while (next) {
    const response = await fetch(next, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(`Failed to load ${url}`);
    }

    const data = await response.json();

    all.push(
      ...(Array.isArray(data) ? data : data.results || [])
    );

    if (data.next) {
      // DRF returns absolute pagination URLs that point straight
      // at the API host, bypassing the frontend proxy. Rebuild as
      // a same-origin path so pagination stays on the app origin.
      const nextUrl = new URL(data.next, window.location.origin);
      next = nextUrl.pathname + nextUrl.search;
    } else {
      next = null;
    }
  }

  return all;
}

function toFormPayload(form) {
  const body = new FormData();

  for (const [key, value] of Object.entries(form)) {
    body.append(key, value === "" || value == null ? "" : value);
  }

  return body;
}

function formatError(data) {
  if (data && typeof data === "object") {
    return Object.entries(data)
      .map(([field, value]) => {
        const text = Array.isArray(value)
          ? value.join(", ")
          : String(value);

        return `${field}: ${text}`;
      })
      .join(" | ");
  }

  return String(data || "Request failed.");
}

export default function AssignmentsPage() {
  const [tab, setTab] = useState("assignments");

  const [options, setOptions] = useState({
    teachers: [],
    students: [],
    campuses: [],
    units: [],
    classes: [],
    sections: [],
    subjects: [],
    years: [],
  });

  const [optionsLoading, setOptionsLoading] = useState(true);
  const [optionsError, setOptionsError] = useState("");

  const [assignments, setAssignments] = useState([]);
  const [enrollments, setEnrollments] = useState([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");

  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState("");
  const [success, setSuccess] = useState("");

  const emptyAssignment = {
    teacher: "",
    academic_year: "",
    class_obj: "",
    section: "",
    subject: "",
    role: "class_teacher",
    status: "active",
  };

  const emptyEnrollment = {
    student: "",
    academic_year: "",
    class_obj: "",
    section: "",
    roll_number: "",
    status: "active",
  };

  const [assignmentForm, setAssignmentForm] = useState(
    emptyAssignment
  );
  const [enrollmentForm, setEnrollmentForm] = useState(
    emptyEnrollment
  );

  /* =========================
     LOAD REFERENCE DATA
  ========================= */

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      fetchAllPages(TEACHERS_URL),
      fetchAllPages(STUDENTS_URL),
      fetchAllPages(CAMPUSES_URL),
      fetchAllPages(UNITS_URL),
      fetchAllPages(CLASSES_URL),
      fetchAllPages(SECTIONS_URL),
      fetchAllPages(SUBJECTS_URL),
      fetchAllPages(YEARS_URL),
    ])
      .then(
        ([
          teachers,
          students,
          campuses,
          units,
          classes,
          sections,
          subjects,
          years,
        ]) => {
          if (cancelled) return;

          setOptions({
            teachers,
            students,
            campuses,
            units,
            classes,
            sections,
            subjects,
            years,
          });
        }
      )
      .catch((err) => {
        if (!cancelled) setOptionsError(err.message);
      })
      .finally(() => {
        if (!cancelled) setOptionsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  /* =========================
     LOAD LISTS
  ========================= */

  const loadAssignments = useCallback(() => {
    return fetch(ASSIGNMENTS_URL)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load teacher assignments.");
        }

        return response.json();
      })
      .then((data) => {
        setAssignments(
          Array.isArray(data) ? data : data.results || []
        );
        setListError("");
      })
      .catch((err) => {
        setListError(err.message);
      })
      .finally(() => setListLoading(false));
  }, []);

  const loadEnrollments = useCallback(() => {
    return fetch(ENROLLMENTS_URL)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load student enrollments.");
        }

        return response.json();
      })
      .then((data) => {
        setEnrollments(
          Array.isArray(data) ? data : data.results || []
        );
        setListError("");
      })
      .catch((err) => {
        setListError(err.message);
      })
      .finally(() => setListLoading(false));
  }, []);

  useEffect(() => {
    loadAssignments();
    loadEnrollments();
  }, [loadAssignments, loadEnrollments]);

  /* =========================
     HELPERS
  ========================= */

  const sectionsForClass = (classId) =>
    options.sections.filter(
      (section) => !classId || Number(section.class_obj) === Number(classId)
    );

  const classById = (classId) =>
    options.classes.find(
      (cls) => cls.id === Number(classId)
    );

  const handleAssignmentChange = (event) => {
    const { name, value } = event.target;

    setAssignmentForm((previous) => {
      const next = { ...previous, [name]: value };

      if (name === "class_obj") {
        const cls = classById(value);

        next.section = "";

        const campus = options.campuses.find(
          (c) => c.id === (cls?.campus || -1)
        );

        if (campus) next.campus = campus.id;
      }

      return next;
    });
  };

  const handleEnrollmentChange = (event) => {
    const { name, value } = event.target;

    setEnrollmentForm((previous) => {
      const next = { ...previous, [name]: value };

      if (name === "class_obj") {
        const cls = classById(value);

        next.section = "";

        const campus = options.campuses.find(
          (c) => c.id === (cls?.campus || -1)
        );

        if (campus) next.campus = campus.id;
      }

      return next;
    });
  };

  const resetMessage = () => {
    setActionError("");
    setSuccess("");
  };

  /* =========================
     CREATE
  ========================= */

  const submitAssignment = async (event) => {
    event.preventDefault();

    setSaving(true);
    resetMessage();

    try {
      const response = await fetch(ASSIGNMENTS_URL, {
        method: "POST",
        credentials: "include",
        headers: {
          "X-CSRFToken": getCookie("csrftoken") || "",
        },
        body: toFormPayload({
          teacher: assignmentForm.teacher,
          academic_year: assignmentForm.academic_year,
          campus: assignmentForm.campus,
          class_obj: assignmentForm.class_obj,
          section: assignmentForm.section,
          subject: assignmentForm.subject,
          role: assignmentForm.role,
          status: assignmentForm.status,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(formatError(data));
      }

      setAssignmentForm(emptyAssignment);
      setSuccess("Teacher assigned to the grade successfully.");
      await loadAssignments();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const submitEnrollment = async (event) => {
    event.preventDefault();

    setSaving(true);
    resetMessage();

    try {
      const response = await fetch(ENROLLMENTS_URL, {
        method: "POST",
        credentials: "include",
        headers: {
          "X-CSRFToken": getCookie("csrftoken") || "",
        },
        body: toFormPayload({
          student: enrollmentForm.student,
          academic_year: enrollmentForm.academic_year,
          campus: enrollmentForm.campus,
          class_obj: enrollmentForm.class_obj,
          section: enrollmentForm.section,
          roll_number: enrollmentForm.roll_number,
          status: enrollmentForm.status,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(formatError(data));
      }

      setEnrollmentForm(emptyEnrollment);
      setSuccess("Student enrolled in the grade successfully.");
      await loadEnrollments();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setSaving(false);
    }
  };

  /* =========================
     DELETE
  ========================= */

  const removeAssignment = async (assignment) => {
    const confirmed = window.confirm(
      `Remove the assignment of ${
        assignment.teacher_name || "this teacher"
      } to ${assignment.class_name || ""} ${
        assignment.section_name || ""
      }?`
    );

    if (!confirmed) return;

    setSaving(true);
    resetMessage();

    try {
      const response = await fetch(
        `${ASSIGNMENTS_URL}${assignment.id}/`,
        {
          method: "DELETE",
          credentials: "include",
          headers: {
            "X-CSRFToken": getCookie("csrftoken") || "",
          },
        }
      );

      if (!response.ok) {
        throw new Error("Unable to remove assignment.");
      }

      setSuccess("Assignment removed.");
      await loadAssignments();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const removeEnrollment = async (enrollment) => {
    const confirmed = window.confirm(
      `Remove ${
        enrollment.student_name || "this student"
      } from ${enrollment.class_name || ""} ${
        enrollment.section_name || ""
      }?`
    );

    if (!confirmed) return;

    setSaving(true);
    resetMessage();

    try {
      const response = await fetch(
        `${ENROLLMENTS_URL}${enrollment.id}/`,
        {
          method: "DELETE",
          credentials: "include",
          headers: {
            "X-CSRFToken": getCookie("csrftoken") || "",
          },
        }
      );

      if (!response.ok) {
        throw new Error("Unable to remove enrollment.");
      }

      setSuccess("Enrollment removed.");
      await loadEnrollments();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setSaving(false);
    }
  };

  /* =========================
     RENDER
  ========================= */

  if (optionsLoading) {
    return (
      <section className="content">
        <PageHeader
          crumb="Home / Assignments"
          title="Grade Assignments"
          subtitle="Assign teachers to grades and students to grades."
        />

        <div className="state-card">Loading assignment data...</div>
      </section>
    );
  }

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Assignments"
        title="Grade Assignments"
        subtitle="Assign teachers to grades and students to grades."
      />

      {optionsError && (
        <div className="state-card error">
          <strong>Unable to load reference data.</strong>
          <span>{optionsError}</span>
        </div>
      )}

      {actionError && (
        <div className="state-card error">
          <strong>Unable to save.</strong>
          <span>{actionError}</span>
        </div>
      )}

      {success && (
        <div className="state-card success">
          <strong>{success}</strong>
        </div>
      )}

      <div className="tabs">
        <button
          className={`tab ${tab === "assignments" ? "active" : ""}`}
          onClick={() => setTab("assignments")}
        >
          <BookOpen size={18} />
          Teacher Assignments
        </button>

        <button
          className={`tab ${tab === "enrollments" ? "active" : ""}`}
          onClick={() => setTab("enrollments")}
        >
          <UserPlus size={18} />
          Student Enrollments
        </button>
      </div>

      {tab === "assignments" ? (
        <div className="assignment-grid">
          <div className="panel">
            <div className="teacher-list-header">
              <div>
                <h3>Assign Teacher to Grade</h3>

                <p>Pick a teacher and a grade (class/section).</p>
              </div>
            </div>

            <form onSubmit={submitAssignment} className="assign-form">
              <label>
                Teacher
                <select
                  name="teacher"
                  value={assignmentForm.teacher}
                  onChange={handleAssignmentChange}
                  required
                >
                  <option value="">Select teacher</option>

                  {options.teachers.map((teacher) => (
                    <option key={teacher.id} value={teacher.id}>
                      {teacher.full_name || teacher.employee_number}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Academic Year
                <select
                  name="academic_year"
                  value={assignmentForm.academic_year}
                  onChange={handleAssignmentChange}
                  required
                >
                  <option value="">Select year</option>

                  {options.years.map((year) => (
                    <option key={year.id} value={year.id}>
                      {year.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Grade (Class)
                <select
                  name="class_obj"
                  value={assignmentForm.class_obj}
                  onChange={handleAssignmentChange}
                  required
                >
                  <option value="">Select grade</option>

                  {options.classes.map((cls) => (
                    <option key={cls.id} value={cls.id}>
                      {cls.name} — {cls.campus_name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Section
                <select
                  name="section"
                  value={assignmentForm.section}
                  onChange={handleAssignmentChange}
                  required
                >
                  <option value="">Select section</option>

                  {sectionsForClass(
                    assignmentForm.class_obj
                  ).map((section) => (
                    <option key={section.id} value={section.id}>
                      {section.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Subject
                <select
                  name="subject"
                  value={assignmentForm.subject}
                  onChange={handleAssignmentChange}
                  required
                >
                  <option value="">Select subject</option>

                  {options.subjects.map((subject) => (
                    <option key={subject.id} value={subject.id}>
                      {subject.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Role
                <select
                  name="role"
                  value={assignmentForm.role}
                  onChange={handleAssignmentChange}
                >
                  <option value="class_teacher">
                    Class Teacher
                  </option>

                  <option value="subject_teacher">
                    Subject Teacher
                  </option>

                  <option value="coordinator">
                    Coordinator
                  </option>
                </select>
              </label>

              <label>
                Status
                <select
                  name="status"
                  value={assignmentForm.status}
                  onChange={handleAssignmentChange}
                >
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </label>

              <div className="assign-form-actions">
                <button
                  type="submit"
                  className="primary-button"
                  disabled={saving}
                >
                  {saving ? "Saving..." : "Assign Teacher"}
                </button>
              </div>
            </form>
          </div>

          <div className="panel">
            <div className="teacher-list-header">
              <div>
                <h3>Current Teacher Assignments</h3>

                <p>{assignments.length} assignments</p>
              </div>
            </div>

            {listLoading ? (
              <div className="state-card">Loading assignments...</div>
            ) : listError ? (
              <div className="state-card error">
                <strong>{listError}</strong>
              </div>
            ) : assignments.length === 0 ? (
              <div className="empty-state">
                <GraduationCap size={42} />
                <h3>No assignments yet</h3>
                <p>Assign a teacher to a grade to get started.</p>
              </div>
            ) : (
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>TEACHER</th>
                      <th>GRADE</th>
                      <th>SECTION</th>
                      <th>SUBJECT</th>
                      <th>ROLE</th>
                      <th>YEAR</th>
                      <th>STATUS</th>
                      <th></th>
                    </tr>
                  </thead>

                  <tbody>
                    {assignments.map((assignment) => (
                      <tr key={assignment.id}>
                        <td>
                          <strong>
                            {assignment.teacher_name}
                          </strong>
                        </td>

                        <td>{assignment.class_name}</td>

                        <td>{assignment.section_name}</td>

                        <td>{assignment.subject_name}</td>

                        <td>{assignment.role_label}</td>

                        <td>{assignment.academic_year_name}</td>

                        <td>
                          <span
                            className={`status-badge ${
                              assignment.status === "active"
                                ? "active"
                                : "inactive"
                            }`}
                          >
                            {assignment.status}
                          </span>
                        </td>

                        <td>
                          <button
                            className="table-action danger"
                            onClick={() =>
                              removeAssignment(assignment)
                            }
                            disabled={saving}
                          >
                            <Trash2 size={15} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="assignment-grid">
          <div className="panel">
            <div className="teacher-list-header">
              <div>
                <h3>Enroll Student in Grade</h3>

                <p>Pick a student and a grade (class/section).</p>
              </div>
            </div>

            <form onSubmit={submitEnrollment} className="assign-form">
              <label>
                Student
                <select
                  name="student"
                  value={enrollmentForm.student}
                  onChange={handleEnrollmentChange}
                  required
                >
                  <option value="">Select student</option>

                  {options.students.map((student) => (
                    <option key={student.id} value={student.id}>
                      {student.full_name} —{" "}
                      {student.admission_number}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Academic Year
                <select
                  name="academic_year"
                  value={enrollmentForm.academic_year}
                  onChange={handleEnrollmentChange}
                  required
                >
                  <option value="">Select year</option>

                  {options.years.map((year) => (
                    <option key={year.id} value={year.id}>
                      {year.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Grade (Class)
                <select
                  name="class_obj"
                  value={enrollmentForm.class_obj}
                  onChange={handleEnrollmentChange}
                  required
                >
                  <option value="">Select grade</option>

                  {options.classes.map((cls) => (
                    <option key={cls.id} value={cls.id}>
                      {cls.name} — {cls.campus_name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Section
                <select
                  name="section"
                  value={enrollmentForm.section}
                  onChange={handleEnrollmentChange}
                  required
                >
                  <option value="">Select section</option>

                  {sectionsForClass(
                    enrollmentForm.class_obj
                  ).map((section) => (
                    <option key={section.id} value={section.id}>
                      {section.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Roll Number
                <input
                  name="roll_number"
                  value={enrollmentForm.roll_number}
                  onChange={handleEnrollmentChange}
                  maxLength={20}
                  placeholder="Optional"
                />
              </label>

              <label>
                Status
                <select
                  name="status"
                  value={enrollmentForm.status}
                  onChange={handleEnrollmentChange}
                >
                  <option value="active">Active</option>
                  <option value="completed">Completed</option>
                  <option value="withdrawn">Withdrawn</option>
                </select>
              </label>

              <div className="assign-form-actions">
                <button
                  type="submit"
                  className="primary-button"
                  disabled={saving}
                >
                  {saving ? "Saving..." : "Enroll Student"}
                </button>
              </div>
            </form>
          </div>

          <div className="panel">
            <div className="teacher-list-header">
              <div>
                <h3>Current Enrollments</h3>

                <p>{enrollments.length} enrollments</p>
              </div>
            </div>

            {listLoading ? (
              <div className="state-card">Loading enrollments...</div>
            ) : listError ? (
              <div className="state-card error">
                <strong>{listError}</strong>
              </div>
            ) : enrollments.length === 0 ? (
              <div className="empty-state">
                <GraduationCap size={42} />
                <h3>No enrollments yet</h3>
                <p>Enroll a student in a grade to get started.</p>
              </div>
            ) : (
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>STUDENT</th>
                      <th>GRADE</th>
                      <th>SECTION</th>
                      <th>ROLL NO.</th>
                      <th>YEAR</th>
                      <th>STATUS</th>
                      <th>DATE</th>
                      <th></th>
                    </tr>
                  </thead>

                  <tbody>
                    {enrollments.map((enrollment) => (
                      <tr key={enrollment.id}>
                        <td>
                          <strong>
                            {enrollment.student_name}
                          </strong>
                        </td>

                        <td>{enrollment.class_name}</td>

                        <td>{enrollment.section_name}</td>

                        <td>{enrollment.roll_number || "-"}</td>

                        <td>{enrollment.academic_year_name}</td>

                        <td>
                          <span
                            className={`status-badge ${
                              enrollment.status === "active"
                                ? "active"
                                : "inactive"
                            }`}
                          >
                            {enrollment.status}
                          </span>
                        </td>

                        <td>{enrollment.enrollment_date}</td>

                        <td>
                          <button
                            className="table-action danger"
                            onClick={() =>
                              removeEnrollment(enrollment)
                            }
                            disabled={saving}
                          >
                            <Trash2 size={15} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
