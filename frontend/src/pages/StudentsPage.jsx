import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { Search, Building2, Users, ClipboardCheck } from "lucide-react";
import { useSchool } from "../schoolContext";
import { useLang } from "../i18n";
import { StatusBadge, PageHeader } from "./ui";
import ProfileModal from "./ProfileModal";
import CredentialDisplay from "../components/CredentialDisplay";
import { buildErrorMessage } from "../api";

/* Basic theming & component styles */

const STUDENTS_API_URL = "/api/students/";

const emptyCampusData = {
  students: [],
  count: 0,
  page: 1,
  next: null,
  previous: null,
  loading: true,
  error: "",
};

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);

  if (parts.length === 2) {
    return parts.pop().split(";").shift();
  }

  return null;
}

function authHeaders(extra = {}) {
  const csrfToken = getCookie("csrftoken");

  return {
    ...extra,
    ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
  };
}

function jsonHeaders(extra = {}) {
  return authHeaders({
    "Content-Type": "application/json",
    ...extra,
  });
}

function getCampusIdFromUrl() {
  const path = window.location.pathname;
  const match = path.match(/\/students\/([^/]+)/);
  if (match) return match[1];
  const params = new URLSearchParams(window.location.search);
  return params.get("campus") || "";
}

function StudentsPage() {
  const { t } = useLang();
  const { scopedHasRole } = useSchool();
  const campusSectionRefs = useRef({});

  const isStudentSelf =
    scopedHasRole(["student"]) &&
    !scopedHasRole([
      "super_admin",
      "admin",
      "principal",
      "academic",
      "accountant",
      "teacher",
      "staff",
    ]);

  const canManage = scopedHasRole([
    "super_admin",
    "admin",
    "principal",
    "academic",
  ]);

  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [gender, setGender] = useState("");
  const [status, setStatus] = useState("");

  const [section, setSection] = useState("");
  const [campusOptions, setCampusOptions] = useState([]);
  const [sectionOptions, setSectionOptions] = useState([]);

  const [campusData, setCampusData] = useState({});

  const [showForm, setShowForm] = useState(false);
  const [editingStudent, setEditingStudent] = useState(null);
  const [saving, setSaving] = useState(false);

  const [profileView, setProfileView] = useState(null);

  const handleStudentDelete = async (studentId) => {
    if (!window.confirm("Are you sure you want to delete this student? This will soft-delete the record.")) {
      return;
    }
    try {
      const res = await fetch(`/api/students/${studentId}/`, {
        method: "DELETE",
        credentials: "include",
        headers: jsonHeaders(),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to delete student.");
      }
      setError(data.detail || "Student soft-deleted successfully.");
      // Refresh the student list
      const campusId = getCampusIdFromUrl();
      if (campusId) {
        fetchCampusStudents(campusId);
      } else {
        fetchAllCampuses();
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const emptyForm = {
    admission_number: "",
    first_name: "",
    middle_name: "",
    last_name: "",
    gender: "",
    date_of_birth: "",
    phone: "",
    address: "",
    status: "active",
    admission_date: "",
    campus: "",
    class_obj: "",
    section: "",
    academic_year: "",
    guardian_name: "",
    guardian_relationship: "",
    guardian_phone: "",
    guardian_alternate_phone: "",
    guardian_email: "",
    guardian_address: "",
    create_account: true,
    username: "",
    password: "",
  };

  const [form, setForm] = useState(emptyForm);
  const [photoFile, setPhotoFile] = useState(null);
  const [accountCreated, setAccountCreated] = useState(null);

  const [classOptions, setClassOptions] = useState([]);
  const [yearOptions, setYearOptions] = useState([]);

  const [myProfile, setMyProfile] = useState(null);
  const [myProfileLoading, setMyProfileLoading] = useState(
    isStudentSelf
  );

  const buildStudentParams = (campusId, pageNumber) => {
    const params = new URLSearchParams();

    params.append("campus", campusId);
    params.append("page", pageNumber);

    if (search.trim()) {
      params.append("search", search.trim());
    }

    if (gender) {
      params.append("gender", gender);
    }

    if (status) {
      params.append("status", status);
    }

    if (section) {
      params.append("section", section);
    }

    return params;
  };

  const fetchCampusStudents = (campusId, pageNumber = 1) => {
    const params = buildStudentParams(campusId, pageNumber);

    setCampusData((prev) => ({
      ...prev,
      [campusId]: { ...(prev[campusId] || {}), loading: true },
    }));

    return fetch(`${STUDENTS_API_URL}?${params.toString()}`, {
      credentials: "include",
    })
      .then(async (response) => {
        if (response.ok) {
          return response.json();
        }

        if (response.status === 403) {
          const body = await response.json().catch(() => null);
          throw new Error(
            body?.detail || "You don't have permission to view these students."
          );
        }

        throw new Error("Failed to load students.");
      })
      .then((data) => {
        setCampusData((prev) => ({
          ...prev,
          [campusId]: {
            students: data.results || [],
            count: data.count || 0,
            page: pageNumber,
            next: data.next,
            previous: data.previous,
            loaded: true,
            loading: false,
            error: "",
          },
        }));
      })
      .catch((err) => {
        setCampusData((prev) => ({
          ...prev,
          [campusId]: {
            ...emptyCampusData,
            ...(prev[campusId] || {}),
            loaded: true,
            loading: false,
            error: err.message,
          },
        }));
      });
  };

  const fetchAllCampuses = (pageNumber = 1) => {
    campusOptions.forEach((campus) => {
      fetchCampusStudents(campus.id, pageNumber);
    });
  };

  const loadSectionOptions = () =>
    fetch("/api/schools/sections/", { credentials: "include" })
      .then((response) => (response.ok ? response.json() : []))
      .then((data) => setSectionOptions(Array.isArray(data) ? data : []))
      .catch(() => {});

  const loadClassOptions = () =>
    fetch("/api/schools/classes/", { credentials: "include" })
      .then((response) => (response.ok ? response.json() : []))
      .then((data) => setClassOptions(Array.isArray(data) ? data : []))
      .catch(() => {});

  const loadYearOptions = () =>
    fetch("/api/schools/academic-years/", { credentials: "include" })
      .then((response) => (response.ok ? response.json() : []))
      .then((data) => setYearOptions(Array.isArray(data) ? data : []))
      .catch(() => {});

  const loadUnitOptions = () =>
    fetch("/api/schools/units/", { credentials: "include" })
      .then((response) => (response.ok ? response.json() : []))
      .then((data) => setUnitOptions(Array.isArray(data) ? data : []))
      .catch(() => {});

  const [unitOptions, setUnitOptions] = useState([]);
  const [quickAdd, setQuickAdd] = useState("");
  const [quickForm, setQuickForm] = useState({ name: "", start_date: "", end_date: "", unit: "", class_obj: "", capacity: 30 });
  const [quickSaving, setQuickSaving] = useState(false);
  const [quickError, setQuickError] = useState("");

  const setQuickField = (name) => (event) => {
    setQuickForm((prev) => ({ ...prev, [name]: event.target.value }));
  };

  const openQuick = (kind) => {
    setQuickError("");
    setQuickForm({ name: "", start_date: "", end_date: "", unit: "", class_obj: "", capacity: 30 });
    setQuickAdd(kind);
  };

  const submitQuickAdd = async (event) => {
    event.preventDefault();
    setQuickError("");
    setQuickSaving(true);
    try {
      const postJson = async (url, payload) => {
        const res = await fetch(url, {
          method: "POST",
          credentials: "include",
          headers: jsonHeaders(),
          body: JSON.stringify(payload),
        });
        const text = await res.text();
        let data;
        try { data = text ? JSON.parse(text) : {}; } catch { data = {}; }
        if (!res.ok) {
          throw new Error(
            buildErrorMessage({
              status: res.status,
              detail: data.detail,
              fieldErrors: data,
              responseText: text,
              fallback: "Request failed.",
            })
          );
        }
        return data;
      };

      if (quickAdd === "year") {
        if (!quickForm.name.trim() || !quickForm.start_date || !quickForm.end_date) {
          setQuickError("Name, start and end dates are required.");
          return;
        }
        await postJson("/api/schools/academic-years/", {
          name: quickForm.name.trim(),
          start_date: quickForm.start_date,
          end_date: quickForm.end_date,
          status: "active",
        });
        await loadYearOptions();
        setQuickAdd("");
        return;
      }

      if (quickAdd === "class") {
        if (!quickForm.unit || !quickForm.name.trim()) {
          setQuickError("Select a unit and enter a class name.");
          return;
        }
        await postJson("/api/schools/classes/", {
          unit: Number(quickForm.unit),
          name: quickForm.name.trim(),
        });
        await loadUnitOptions();
        await loadClassOptions();
        setQuickAdd("");
        setForm((prev) => ({ ...prev, class_obj: "", section: "" }));
        return;
      }

      if (quickAdd === "section") {
        if (!quickForm.class_obj || !quickForm.name.trim()) {
          setQuickError("Select a class and enter a section name.");
          return;
        }
        await postJson("/api/schools/sections/", {
          class_obj: Number(quickForm.class_obj),
          name: quickForm.name.trim(),
          capacity: Number(quickForm.capacity) || 30,
        });
        await loadSectionOptions();
        setQuickAdd("");
        return;
      }
    } catch (err) {
      setQuickError(err.message);
    } finally {
      setQuickSaving(false);
    }
  };

  useEffect(() => {
    if (isStudentSelf) {
      fetch("/api/students/me/", { credentials: "include" })
        .then((response) => {
          if (!response.ok) {
            throw new Error("No student profile linked.");
          }

          return response.json();
        })
        .then((data) => {
          setMyProfile(data);
          setError("");
        })
        .catch((err) => {
          setError(err.message);
        })
        .finally(() => {
          setMyProfileLoading(false);
        });

      return;
    }

    const loadCampusStudents = (campus, pageNumber) => {
      const params = new URLSearchParams();

      params.append("campus", campus.id);
      params.append("page", pageNumber);

      fetch(`${STUDENTS_API_URL}?${params.toString()}`, {
        credentials: "include",
      })
        .then(async (response) => {
          if (response.ok) {
            return response.json();
          }

          if (response.status === 403) {
            const body = await response.json().catch(() => null);
            throw new Error(
              body?.detail || "You don't have permission to view these students."
            );
          }

          throw new Error("Failed to load students.");
        })
        .then((data) => {
          setCampusData((prev) => ({
            ...prev,
            [campus.id]: {
              students: data.results || [],
              count: data.count || 0,
              page: pageNumber,
              next: data.next,
              previous: data.previous,
              loaded: true,
              loading: false,
              error: "",
            },
          }));
        })
        .catch((err) => {
          setCampusData((prev) => ({
            ...prev,
            [campus.id]: {
              ...emptyCampusData,
              ...(prev[campus.id] || {}),
              loaded: true,
              loading: false,
              error: err.message,
            },
          }));
        });
    };

    fetch("/api/schools/campuses/", {
      credentials: "include",
    })
      .then((response) =>
        response.ok ? response.json() : []
      )
      .then((data) => {
        const campuses = Array.isArray(data) ? data : [];

        setCampusOptions(campuses);

        campuses.forEach((campus) => {
          loadCampusStudents(campus, 1);
        });
      })
      .catch(() => {});

    fetch("/api/schools/sections/", {
      credentials: "include",
    })
      .then((response) =>
        response.ok ? response.json() : []
      )
      .then((data) =>
        setSectionOptions(
          Array.isArray(data) ? data : []
        )
      )
      .catch(() => {});

    fetch("/api/schools/classes/", {
      credentials: "include",
    })
      .then((response) =>
        response.ok ? response.json() : []
      )
      .then((data) =>
        setClassOptions(Array.isArray(data) ? data : [])
      )
      .catch(() => {});

    fetch("/api/schools/academic-years/", {
      credentials: "include",
    })
      .then((response) =>
        response.ok ? response.json() : []
      )
      .then((data) =>
        setYearOptions(Array.isArray(data) ? data : [])
      )
      .catch(() => {});
  }, [isStudentSelf]);

  const viewCampusStudents = (campusId) => {
    campusSectionRefs.current[campusId]?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  const handleSectionChange = (value) => {
    setSection(value);

    const timeoutID = setTimeout(() => {
      fetchAllCampuses(1);
    }, 0);
    return () => clearTimeout(timeoutID);
  };

  const handleSearch = (event) => {
    event.preventDefault();
    fetchAllCampuses(1);
  };

  const clearFilters = () => {
    setSearch("");
    setGender("");
    setStatus("");
    setSection("");

    const timeoutID = setTimeout(() => {
      fetchAllCampuses(1);
    }, 0);
    return () => clearTimeout(timeoutID);
  };

  /* --------------------------
     FORM HANDLING
  -------------------------- */

  const handleChange = (event) => {
    const { name, value } = event.target;

    setForm((previous) => ({
      ...previous,
      [name]: value,
    }));
  };

  const handlePhoto = (event) => {
    setPhotoFile(event.target.files[0] || null);
  };

  const openAddStudent = () => {
    setEditingStudent(null);
    setPhotoFile(null);
    setForm(emptyForm);
    setShowForm(true);
  };

  const openEditStudent = (student) => {
    setEditingStudent(student);
    setPhotoFile(null);

    const current = student.current_enrollment || {};

    setForm({
      admission_number: student.admission_number || "",
      first_name: student.first_name || "",
      middle_name: student.middle_name || "",
      last_name: student.last_name || "",
      gender: student.gender || "",
      date_of_birth: student.date_of_birth || "",
      phone: student.phone || "",
      address: student.address || "",
      status: student.status || "active",
      admission_date: student.admission_date || "",
      campus: current.campus_id
        ? String(current.campus_id)
        : student.primary_campus
        ? String(student.primary_campus)
        : "",
      class_obj: current.class_id
        ? String(current.class_id)
        : "",
      section: current.section_id
        ? String(current.section_id)
        : "",
      academic_year: current.academic_year_id
        ? String(current.academic_year_id)
        : "",
      guardian_name:
        student.guardian_details?.name || "",
      guardian_relationship:
        student.guardian_details?.relationship || "",
      guardian_phone:
        student.guardian_details?.phone || "",
      guardian_alternate_phone:
        student.guardian_details?.alternate_phone || "",
      guardian_email:
        student.guardian_details?.email || "",
      guardian_address:
        student.guardian_details?.address || "",
      create_account: false,
      username: student.linked_username || "",
      password: "",
    });

    setShowForm(true);
  };

  const closeForm = () => {
    if (saving) return;

    setShowForm(false);
    setEditingStudent(null);
    setPhotoFile(null);
    setForm(emptyForm);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    setSaving(true);
    setError("");

    try {
      if ((form.middle_name || "").length > 100) {
        throw new Error("Middle Name must be 100 characters or fewer.");
      }

      const isEditing = Boolean(editingStudent);

      const url = isEditing
        ? `${STUDENTS_API_URL}${editingStudent.id}/`
        : STUDENTS_API_URL;

      const body = new FormData();

      const studentFields = [
        "admission_number",
        "first_name",
        "middle_name",
        "last_name",
        "gender",
        "date_of_birth",
        "phone",
        "address",
        "status",
        "admission_date",
        "guardian_name",
        "guardian_relationship",
        "guardian_phone",
        "guardian_alternate_phone",
        "guardian_email",
        "guardian_address",
      ];

      for (const key of studentFields) {
        if (!(key in form)) continue;
        const value = form[key];
        body.append(key, value === "" || value == null ? "" : value);
      }

      if (form.campus) {
        body.append("primary_campus", String(form.campus));
      }

      if (photoFile) {
        body.append("photo", photoFile);
      }

      if (form.create_account) {
        body.append("create_account", "true");
        body.append("username", form.username || "");
        body.append("password", form.password || "");
      } else {
        body.append("create_account", "false");
      }

      const response = await fetch(url, {
        method: isEditing ? "PUT" : "POST",
        credentials: "include",
        headers: authHeaders(),
        body,
      });

      const responseText = await response.text();

      let data = {};

      try {
        data = responseText ? JSON.parse(responseText) : {};
      } catch {
        data = {};
      }

      if (!response.ok) {
        throw new Error(
          buildErrorMessage({
            status: response.status,
            detail: data.detail,
            fieldErrors: data,
            responseText,
            fallback: "Unable to save student.",
          })
        );
      }

      // A student only appears in the list when they have an active
      // Enrollment, so on create we also enrol them into the chosen
      // campus/class/section/year. On edit we keep the enrollment in
      // sync with any changes to campus/class/section/year.
      if (data.id && form.campus && form.academic_year) {
        const enrolBody = {
          student: data.id,
          campus: Number(form.campus),
          class_obj: Number(form.class_obj),
          section: Number(form.section),
          academic_year: Number(form.academic_year),
          status: "active",
        };

        const existingEnrollment =
          editingStudent?.current_enrollment;

        const enrollmentFields = [
          ["campus_id", enrolBody.campus],
          ["class_id", enrolBody.class_obj],
          ["section_id", enrolBody.section],
          ["academic_year_id", enrolBody.academic_year],
        ];
        const enrollmentChanged =
          !existingEnrollment ||
          enrollmentFields.some(
            ([field, value]) => Number(existingEnrollment[field]) !== value
          );

        const enrolUrl = existingEnrollment
          ? `/api/students/enrollments/${existingEnrollment.enrollment_id}/`
          : "/api/students/enrollments/";

        if (enrollmentChanged) {
          const enrolRes = await fetch(enrolUrl, {
            method: existingEnrollment ? "PATCH" : "POST",
            credentials: "include",
            headers: jsonHeaders(),
            body: JSON.stringify(enrolBody),
          });

          if (!enrolRes.ok) {
            const enrolText = await enrolRes.text();
            let enrolData = {};

            try {
              enrolData = enrolText ? JSON.parse(enrolText) : {};
            } catch {
              enrolData = {};
            }

            throw new Error(
              (isEditing
                ? "Student saved but updating enrollment failed: "
                : "Student was created but enrolling failed: ") +
                (enrolData.detail ||
                  Object.entries(enrolData)
                    .map(([f, v]) => `${f}: ${v}`)
                    .join(" | ") ||
                  enrolText ||
                  `HTTP ${enrolRes.status}`)
            );
          }
        }
      }

      closeForm();
      await fetchAllCampuses(1);

      if (data.linked_username && data.generated_password) {
        setAccountCreated({
          username: data.linked_username,
          password: data.generated_password,
          name: data.full_name || data.first_name
            ? [data.first_name, data.middle_name, data.last_name].filter(Boolean).join(" ")
            : "",
        });
      }

      if (isStudentSelf) {
        fetch("/api/students/me/", {
          credentials: "include",
        })
          .then((response) => response.json())
          .then((profile) => setMyProfile(profile))
          .catch(() => {});
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (student) => {
    const confirmed = window.confirm(
      `Delete student "${student.full_name || student.admission_number}"? ` +
        "This cannot be undone."
    );

    if (!confirmed) return;

    setSaving(true);
    setError("");

    try {
      const response = await fetch(
        `${STUDENTS_API_URL}${student.id}/`,
        {
          method: "DELETE",
          credentials: "include",
          headers: authHeaders(),
        }
      );

      if (!response.ok) {
        throw new Error("Unable to delete student.");
      }

      const campusId = student.current_enrollment?.campus_id;

      if (campusId) {
        const entry = campusData[campusId] || {};
        await fetchCampusStudents(campusId, entry.page || 1);
      } else {
        await fetchAllCampuses(1);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  /* --------------------------
     STUDENT SELF PROFILE
  -------------------------- */

  if (isStudentSelf) {
    return (
      <section className="content">
        <PageHeader
          hero
          crumb="Home / My Profile"
          title="My Profile"
          subtitle="Your student information at your school."
          stats={[
            {
              label: "Enrollments",
              value: (myProfile && myProfile.enrollments
                ? myProfile.enrollments.length
                : 0),
              icon: <ClipboardCheck size={18} />,
              sub: "academic years",
            },
            {
              label: "Active",
              value: (myProfile && myProfile.enrollments
                ? myProfile.enrollments.filter(
                    (e) => e.status === "active"
                  ).length
                : 0),
              icon: <Users size={18} />,
              sub: "active enrollments",
            },
          ]}
        />

        {myProfileLoading && (
          <div className="state-card">
            Loading your profile...
          </div>
        )}

        {!myProfileLoading && error && (
          <div className="state-card error">
            <strong>Unable to load your profile.</strong>
            <span>{error}</span>
          </div>
        )}

        {!myProfileLoading && !error && myProfile && (
          <div className="profile-grid">
            <div className="panel profile-card">
              {myProfile.photo_url ? (
                <img
                  className="profile-photo"
                  src={myProfile.photo_url}
                  alt={myProfile.full_name}
                />
              ) : (
                <div className="profile-photo placeholder">
                  {(myProfile.full_name || "S")
                    .charAt(0)
                    .toUpperCase()}
                </div>
              )}

              <h3>{myProfile.full_name}</h3>
              <span className="status-badge active">
                {myProfile.status}
              </span>

              <p className="muted">
                {myProfile.admission_number}
              </p>

              <div className="profile-detail">
                <strong>Date of Birth</strong>
                <span>{myProfile.date_of_birth || "—"}</span>
              </div>

              <div className="profile-detail">
                <strong>Gender</strong>
                <span>
                  {myProfile.gender
                    ? myProfile.gender.charAt(0).toUpperCase() +
                      myProfile.gender.slice(1)
                    : "—"}
                </span>
              </div>

              <div className="profile-detail">
                <strong>Phone</strong>
                <span>{myProfile.phone || "—"}</span>
              </div>

              <div className="profile-detail">
                <strong>Address</strong>
                <span>{myProfile.address || "—"}</span>
              </div>
            </div>

            <div className="profile-grid-main">
              <div className="panel">
                <div className="panel-header">
                  <div>
                    <h3>Guardian</h3>
                    <p>Contact information of your guardian</p>
                  </div>
                </div>

                <div className="overview-list">
                  <div>
                    <span>Name</span>
                    <strong>
                      {myProfile.guardian_details?.name || "—"}
                    </strong>
                  </div>
                  <div>
                    <span>Relationship</span>
                    <strong>
                      {myProfile.guardian_details?.relationship ||
                        "—"}
                    </strong>
                  </div>
                  <div>
                    <span>Phone</span>
                    <strong>
                      {myProfile.guardian_details?.phone || "—"}
                    </strong>
                  </div>
                  <div>
                    <span>Email</span>
                    <strong>
                      {myProfile.guardian_details?.email || "—"}
                    </strong>
                  </div>
                </div>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <div>
                    <h3>Enrollments</h3>
                    <p>Classes you are enrolled in</p>
                  </div>
                </div>

                {(myProfile.enrollments || []).length === 0 ? (
                  <div className="state-card">
                    No enrollments found.
                  </div>
                ) : (
                  <div className="table-wrapper">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>ACADEMIC YEAR</th>
                          <th>CLASS</th>
                          <th>SECTION</th>
                          <th>STATUS</th>
                        </tr>
                      </thead>

                      <tbody>
                        {myProfile.enrollments.map(
                          (enrollment) => (
                            <tr key={enrollment.id}>
                              <td>
                                {enrollment.academic_year_name}
                              </td>
                              <td>
                                <strong>
                                  {enrollment.class_name}
                                </strong>
                              </td>
                              <td>{enrollment.section_name}</td>
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
                            </tr>
                          )
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </section>
    );
  }

  /* --------------------------
     ADMIN / TEACHER LIST VIEW
  -------------------------- */

  const totalStudentsAcrossCampuses = Object.values(campusData).reduce(
    (sum, data) => sum + (data && data.count ? data.count : 0),
    0
  );

  return (
    <section className="page">
      <PageHeader
        hero
        crumb={t("Home / Students")}
        title={t("Students")}
        subtitle={t("Manage students enrolled at your school.")}
        action={
          canManage ? (
            <button className="primary-button" onClick={openAddStudent}>
              {t("+ Add Student")}
            </button>
          ) : undefined
        }
        stats={[
          {
            label: t("Students"),
            value: totalStudentsAcrossCampuses,
            icon: <Users size={18} />,
            sub: t("across all campuses"),
          },
          {
            label: t("Campuses"),
            value: campusOptions.length,
            icon: <Building2 size={18} />,
            sub: t("currently visible"),
          },
          {
            label: t("Sections"),
            value: sectionOptions.length,
            icon: <ClipboardCheck size={18} />,
            sub: t("academic groups"),
          },
        ]}
      />

      {accountCreated && (
        <CredentialDisplay
          username={accountCreated.username}
          password={accountCreated.password}
          name={accountCreated.name}
          note="Share these credentials with the student and remind them to change their password after first login."
          onDismiss={() => setAccountCreated(null)}
        />
      )}

      {/* Drag & drop upload zone */}
      <div
        className="drop-zone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          const file = e.dataTransfer.files[0];
          if (file && file.type.startsWith("image/")) {
            setPhotoFile(file);
          }
        }}
      >
        <p>Drag & drop an image here to upload</p>
      </div>

      {/* Campus overview */}
      {campusOptions.length > 0 && (
        <div className="campus-cards">
          {campusOptions.map((item) => (
            <div key={item.id} className="campus-card">
              <div className="campus-card-header">
                <Building2 size={20} />
                <strong>{item.name}</strong>
              </div>

              <p className="campus-card-sub">
                {[item.city, item.address]
                  .filter(Boolean)
                  .join(", ") || "Your School"}
              </p>

              <div className="campus-card-stats">
                <div>
                  <span>{item.student_count || 0}</span>
                  <small>Students</small>
                </div>

                <div>
                  <span>{item.class_count || 0}</span>
                  <small>Classes</small>
                </div>

                <div>
                  <span>{item.section_count || 0}</span>
                  <small>Sections</small>
                </div>
              </div>

              <button
                className="primary-button campus-card-button"
                onClick={() => viewCampusStudents(item.id)}
              >
                View All Students
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="panel students-filters">
        <form onSubmit={handleSearch}>
          <div className="filter-row">
            <div className="filter-search">
              <Search size={18} />

              <input
                type="text"
                placeholder={t("Search by name, admission number or phone...")}
                value={search}
                onChange={(event) =>
                  setSearch(event.target.value)
                }
              />
            </div>

            <select
              value={gender}
              onChange={(event) => {
                setGender(event.target.value);
                const genderTimeout = setTimeout(() => {
                  fetchAllCampuses(1);
                }, 0);
                return () => clearTimeout(genderTimeout);
              }}
            >
              <option value="">All genders</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
            </select>

            <select
              value={section}
              onChange={(event) =>
                handleSectionChange(event.target.value)
              }
            >
              <option value="">All sections</option>

              {sectionOptions.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.class_name} - {item.name}
                </option>
              ))}
            </select>

            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                const statusTimeout = setTimeout(() => {
                  fetchAllCampuses(1);
                }, 0);
                return () => clearTimeout(statusTimeout);
              }}
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>

            <button type="submit" className="primary-button">
              Search
            </button>

            <button
              type="button"
              className="secondary-button"
              onClick={clearFilters}
            >
              Clear
            </button>
          </div>
        </form>
      </div>

      {/* Student lists by campus */}
      {campusOptions.length === 0 ? (
        <div className="state-card">
          No campuses found.
        </div>
      ) : (
        <div className="campus-student-lists">
          {campusOptions.map((campus) => {
            const data = {
              ...emptyCampusData,
              ...(campusData[campus.id] || {}),
            };

            const campusTotalPages = Math.max(
              1,
              Math.ceil(data.count / 20)
            );

            return (
              <div
                key={campus.id}
                className="panel campus-student-list"
                ref={(el) => {
                  campusSectionRefs.current[campus.id] = el;
                }}
              >
                <div className="panel-header">
                  <div>
                    <h3>{campus.name}</h3>

                    <p>
                      {data.count.toLocaleString()} students
                      found
                    </p>
                  </div>
                </div>

                {/* Student cards grid (first 5 per campus) */}
                {data.students.length > 0 && (
                  <div className="student-cards-grid">
                    {data.students.slice(0, 5).map((student) => (
                      <div
                        key={student.id}
                        className="student-card"
                        onClick={() => console.log("student clicked", student.id)}
                      >
                        {student.photo_url ? (
                          <img
                            className="student-card-photo"
                            src={student.photo_url}
                            alt={student.full_name}
                          />
                        ) : (
                          <div className="student-card-placeholder">
                            {(student.full_name || "S").charAt(0).toUpperCase()}
                          </div>
                        )}
                        <div className="student-card-info">
                          <strong>{student.full_name || student.admission_number}</strong>
                          <span className="student-card-status">
                            <StatusBadge status={student.status === "active" ? "active" : "inactive"} label={student.status} />
                          </span>
                        </div>
                        <div className="student-card-actions">
                          {canManage && (
                            <>
                              <button className="btn-edit">Edit</button>
                              <button className="btn-delete">Delete</button>
                            </>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {data.loading && (
                  <div className="state-card">
                    Loading students...
                  </div>
                )}

                {!data.loading && data.error && (
                  <div className="state-card error">
                    <strong>
                      Unable to load students.
                    </strong>

                    <span>{data.error}</span>
                  </div>
                )}

                {!data.loading && !data.error && (
                  <>
                    {data.students.length === 0 ? (
                      <div className="state-card">
                        No students found.
                      </div>
                    ) : (
                      <div className="students-table-wrapper">
                        <table className="data-table">
                          <thead>
                            <tr>
                  <th>{t("Student")}</th>
                  <th>{t("Admission No.")}</th>
                  <th>{t("Class")}</th>
                  <th>{t("Section")}</th>
                  <th>{t("Date of Birth")}</th>
                  <th>{t("Gender")}</th>
                  <th>{t("Guardian")}</th>
                  <th>{t("Phone")}</th>
                  <th>{t("Status")}</th>
                              <th></th>
                            </tr>
                          </thead>

                          <tbody>
                            {data.students.map((student) => (
                              <tr key={student.id}>
                                <td>
                                  <div className="student-name-cell">
                                    {student.photo_url ? (
                                      <img
                                        className="table-photo"
                                        src={student.photo_url}
                                        alt={student.full_name}
                                      />
                                    ) : (
                                      <div className="table-avatar">
                                        {(
                                          student.full_name ||
                                          "S"
                                        )
                                          .charAt(0)
                                          .toUpperCase()}
                                      </div>
                                    )}

                                    <strong>
                                      {student.full_name ||
                                        `${student.first_name ||
                                          ""} ${
                                          student.middle_name ||
                                          ""
                                        } ${
                                          student.last_name ||
                                          ""
                                        }`.trim()}
                                    </strong>
                                  </div>
                                </td>

                                <td>
                                  <strong>
                                    {student.admission_number}
                                  </strong>
                                </td>

                                <td>
                                  {student.current_enrollment
                                    ?.class_name || "—"}
                                </td>

                                <td>
                                  {student.current_enrollment
                                    ?.section_name || "—"}
                                </td>

                                <td>
                                  {student.date_of_birth ||
                                    "—"}
                                </td>

                                <td>
                                  {student.gender
                                    ? student.gender
                                        .charAt(0)
                                        .toUpperCase() +
                                      student.gender.slice(1)
                                    : "—"}
                                </td>

                                <td>
                                  {student.guardian_details
                                    ?.name || "—"}
                                </td>

                                <td>{student.phone || "—"}</td>

                                <td>
                                  <span
                                    className={`status-badge ${
                                      student.status ===
                                      "active"
                                        ? "active"
                                        : "inactive"
                                    }`}
                                  >
                                    {student.status || "—"}
                                  </span>
                                </td>
                                <td>
                                  {canManage && (
                                    <button
                                      className="btn-delete"
                                      onClick={() => handleStudentDelete(student.id)}
                                      title="Delete student"
                                    >
                                      Delete
                                    </button>
                                  )}
                                </td>

                                <td>
                                  <Link
                                    className="table-action"
                                    to={`/students/${student.id}`}
                                  >
                                    360°
                                  </Link>

                                  <button
                                    className="table-action"
                                    onClick={() =>
                                      setProfileView({
                                        type: "student",
                                        id: student.id,
                                      })
                                    }
                                  >
                                    View Profile
                                  </button>

                                  {canManage && (
                                    <>
                                      <button
                                        className="table-action"
                                        onClick={() =>
                                          openEditStudent(
                                            student
                                          )
                                        }
                                      >
                                        Edit
                                      </button>

                                      <button
                                        className="table-action danger"
                                        onClick={() =>
                                          handleDelete(student)
                                        }
                                      >
                                        Delete
                                      </button>
                                    </>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {data.count > 0 && (
                      <div className="pagination">
                        <button
                          disabled={!data.previous}
                          onClick={() =>
                            fetchCampusStudents(
                              campus.id,
                              data.page - 1
                            )
                          }
                        >
                          Previous
                        </button>

                        <span>
                          Page {data.page} of{" "}
                          {campusTotalPages}
                        </span>

                        <button
                          disabled={!data.next}
                          onClick={() =>
                            fetchCampusStudents(
                              campus.id,
                              data.page + 1
                            )
                          }
                        >
                          Next
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Add / Edit Student Modal */}
      {showForm && (
        <div
          className="modal-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeForm();
            }
          }}
        >
          <div className="teacher-modal student-modal">
            <div className="modal-header">
              <div>
                <h3>
                  {editingStudent
                    ? "Edit Student"
                    : "Add Student"}
                </h3>

                <p>
                  {editingStudent
                    ? "Update student information."
                    : "Create a new student profile."}
                </p>
              </div>

              <button
                className="modal-close"
                onClick={closeForm}
                disabled={saving}
              >
                ×
              </button>
            </div>

            <form onSubmit={handleSubmit}>
              {error && (
                <div className="state-card error" style={{ marginBottom: 16 }}>
                  <strong>{error}</strong>
                </div>
              )}

              <div className="form-section">
                <h4>Personal Information</h4>

                <div className="form-grid">
                  <label>
                    Admission Number
                    <input
                      name="admission_number"
                      value={form.admission_number}
                      onChange={handleChange}
                      placeholder="PF-ST-0001 (auto)"
                    />
                    <small className="form-hint">Leave blank to auto-generate from the school name.</small>
                  </label>

                  <label>
                    Gender
                    <select
                      name="gender"
                      value={form.gender}
                      onChange={handleChange}
                      required
                    >
                      <option value="">Select gender</option>
                      <option value="male">Male</option>
                      <option value="female">Female</option>
                    </select>
                  </label>

                  <label>
                    First Name
                    <input
                      name="first_name"
                      value={form.first_name}
                      onChange={handleChange}
                      placeholder="First name"
                      required
                    />
                  </label>

                  <label>
                    Middle Name
                    <input
                      name="middle_name"
                      value={form.middle_name}
                      onChange={handleChange}
                      maxLength={100}
                      placeholder="Middle name"
                    />
                  </label>

                  <label>
                    Last Name
                    <input
                      name="last_name"
                      value={form.last_name}
                      onChange={handleChange}
                      placeholder="Last name"
                    />
                  </label>

                  <label>
                    Date of Birth
                    <input
                      type="date"
                      name="date_of_birth"
                      value={form.date_of_birth}
                      onChange={handleChange}
                    />
                  </label>

                  <label>
                    Admission Date
                    <input
                      type="date"
                      name="admission_date"
                      value={form.admission_date}
                      onChange={handleChange}
                    />
                  </label>

                  <label>
                    Status
                    <select
                      name="status"
                      value={form.status}
                      onChange={handleChange}
                    >
                      <option value="active">Active</option>
                      <option value="inactive">Inactive</option>
                      <option value="graduated">
                        Graduated
                      </option>
                      <option value="withdrawn">
                        Withdrawn
                      </option>
                    </select>
                  </label>

                  <label>
                    Photo
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handlePhoto}
                    />
                  </label>

                  {photoFile && (
                    <div className="photo-preview">
                      <img
                        src={URL.createObjectURL(photoFile)}
                        alt="preview"
                      />
                    </div>
                  )}
                </div>
              </div>

              <div className="form-section">
                <h4>Campus & Enrollment</h4>
                <span className="field-hint">
                  Choose the campus and grade so the student shows up
                  in the right list. Required for new students.
                </span>

                <div className="form-grid">
                  <label>
                    Campus
                    <select
                      name="campus"
                      value={form.campus}
                      onChange={handleChange}
                      required={!editingStudent}
                    >
                      <option value="">
                        Select campus
                      </option>

                      {campusOptions.map((item) => (
                        <option
                          key={item.id}
                          value={item.id}
                        >
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    <span className="field-label-row">
                      <span>Academic Year</span>
                      <button type="button" className="quick-add-link" onClick={() => openQuick("year")}>+ Add</button>
                    </span>
                    <select
                      name="academic_year"
                      value={form.academic_year}
                      onChange={handleChange}
                      required
                    >
                      <option value="">
                        Select year
                      </option>

                      {yearOptions.map((item) => (
                        <option
                          key={item.id}
                          value={item.id}
                        >
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    <span className="field-label-row">
                      <span>Class</span>
                      <button type="button" className="quick-add-link" onClick={() => { loadUnitOptions(); openQuick("class"); }}>+ Add</button>
                    </span>
                    <select
                      name="class_obj"
                      value={form.class_obj}
                      onChange={handleChange}
                      required
                    >
                      <option value="">
                        Select class
                      </option>

                      {classOptions
                        .filter(
                          (item) =>
                            !form.campus ||
                            String(item.campus) ===
                              String(form.campus)
                        )
                        .map((item) => (
                          <option
                            key={item.id}
                            value={item.id}
                          >
                            {item.name}
                          </option>
                        ))}
                    </select>
                  </label>

                  <label>
                    <span className="field-label-row">
                      <span>Section</span>
                      <button type="button" className="quick-add-link" onClick={() => openQuick("section")}>+ Add</button>
                    </span>
                    <select
                      name="section"
                      value={form.section}
                      onChange={handleChange}
                      required
                    >
                      <option value="">
                        Select section
                      </option>

                      {sectionOptions
                        .filter(
                          (item) =>
                            !form.class_obj ||
                            String(item.class_obj) ===
                              String(form.class_obj)
                        )
                        .map((item) => (
                          <option
                            key={item.id}
                            value={item.id}
                          >
                            {item.name}
                          </option>
                        ))}
                    </select>
                  </label>
                </div>
              </div>

              {quickAdd && (
                <div className="form-section" style={{ marginTop: 16, borderTop: "1px solid var(--border)", paddingTop: 16 }}>
                  <h4 style={{ marginBottom: 12 }}>Quick Add: {quickAdd === "year" ? "Academic Year" : quickAdd === "class" ? "Class" : "Section"}</h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {quickAdd === "year" && (
                      <>
                        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Year name *</span>
                          <input name="name" value={quickForm.name} onChange={setQuickField("name")} placeholder="e.g. 2026-2027" />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Start date *</span>
                          <input type="date" name="start_date" value={quickForm.start_date} onChange={setQuickField("start_date")} />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>End date *</span>
                          <input type="date" name="end_date" value={quickForm.end_date} onChange={setQuickField("end_date")} />
                        </label>
                      </>
                    )}
                    {quickAdd === "class" && (
                      <>
                        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Academic unit *</span>
                          <select name="unit" value={quickForm.unit} onChange={setQuickField("unit")}>
                            <option value="">Select unit</option>
                            {unitOptions.map((u) => (
                              <option key={u.id} value={u.id}>
                                {u.campus_name ? `${u.campus_name} — ` : ""}{u.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Class name *</span>
                          <input name="name" value={quickForm.name} onChange={setQuickField("name")} placeholder="e.g. Grade 7" />
                        </label>
                      </>
                    )}
                    {quickAdd === "section" && (
                      <>
                        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Class *</span>
                          <select name="class_obj" value={quickForm.class_obj} onChange={setQuickField("class_obj")}>
                            <option value="">Select class</option>
                            {classOptions.map((c) => (
                              <option key={c.id} value={c.id}>{c.name}</option>
                            ))}
                          </select>
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Section name *</span>
                          <input name="name" value={quickForm.name} onChange={setQuickField("name")} placeholder="e.g. A" />
                        </label>
                        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Capacity</span>
                          <input type="number" name="capacity" value={quickForm.capacity} onChange={setQuickField("capacity")} />
                        </label>
                      </>
                    )}
                    {quickError && <div style={{ color: "var(--danger)", fontSize: 13 }}>{quickError}</div>}
                    <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 8 }}>
                      <button type="button" className="secondary-button" onClick={() => setQuickAdd("")} disabled={quickSaving}>Cancel</button>
                      <button type="button" className="primary-button" onClick={submitQuickAdd} disabled={quickSaving}>{quickSaving ? "Saving..." : "Save"}</button>
                    </div>
                  </div>
                </div>
              )}

              <div className="form-section">
                <h4>Contact Information</h4>

                <div className="form-grid">
                  <label>
                    Phone
                    <input
                      name="phone"
                      value={form.phone}
                      onChange={handleChange}
                      placeholder="03XX-XXXXXXX"
                    />
                  </label>

                  <label>
                    Address
                    <input
                      name="address"
                      value={form.address}
                      onChange={handleChange}
                      placeholder="Home address"
                    />
                  </label>
                </div>
              </div>

              <div className="form-section">
                <h4>Guardian Information</h4>

                <div className="form-grid">
                  <label>
                    Guardian Name
                    <input
                      name="guardian_name"
                      value={form.guardian_name}
                      onChange={handleChange}
                      placeholder="Full name"
                      required={!editingStudent}
                    />
                  </label>

                  <label>
                    Relationship
                    <input
                      name="guardian_relationship"
                      value={form.guardian_relationship}
                      onChange={handleChange}
                      placeholder="e.g. Father, Mother"
                      required={!editingStudent}
                    />
                  </label>

                  <label>
                    Guardian Phone
                    <input
                      name="guardian_phone"
                      value={form.guardian_phone}
                      onChange={handleChange}
                      placeholder="03XX-XXXXXXX"
                      required={!editingStudent}
                    />
                  </label>

                  <label>
                    Alternate Phone
                    <input
                      name="guardian_alternate_phone"
                      value={form.guardian_alternate_phone}
                      onChange={handleChange}
                      placeholder="Alternate phone"
                    />
                  </label>

                  <label>
                    Guardian Email
                    <input
                      type="email"
                      name="guardian_email"
                      value={form.guardian_email}
                      onChange={handleChange}
                      placeholder="guardian@example.com"
                    />
                  </label>

                  <label>
                    Guardian Address
                    <input
                      name="guardian_address"
                      value={form.guardian_address}
                      onChange={handleChange}
                      placeholder="Guardian address"
                    />
                  </label>
                </div>
              </div>

              <div className="form-section">
                <h4>Login Account</h4>

                {editingStudent &&
                  editingStudent.linked_username && (
                    <p className="field-hint">
                      This student is linked to username{" "}
                      <strong>
                        {editingStudent.linked_username}
                      </strong>.
                    </p>
                  )}

                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={Boolean(form.create_account)}
                    onChange={(event) =>
                      setForm((previous) => ({
                        ...previous,
                        create_account: event.target.checked,
                      }))
                    }
                  />

                  <span>
                    {editingStudent &&
                    editingStudent.linked_username
                      ? "Reset this student's password"
                      : "Create a login account for this student"}
                  </span>
                </label>

                {form.create_account && (
                  <div className="form-grid">
                    {!(editingStudent &&
                      editingStudent.linked_username) && (
                      <label>
                        Username
                        <input
                          name="username"
                          value={form.username}
                          onChange={handleChange}
                          placeholder="Leave blank to auto-generate"
                        />
                      </label>
                    )}

                    <label>
                      Password
                      <input
                        type="text"
                        name="password"
                        value={form.password}
                        onChange={handleChange}
                        placeholder="Leave blank to auto-generate"
                        autoComplete="new-password"
                      />
                    </label>
                  </div>
                )}
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={closeForm}
                  disabled={saving}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  className="primary-button"
                  disabled={saving}
                >
                  {saving
                    ? "Saving..."
                    : editingStudent
                    ? "Save Changes"
                    : "Add Student"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {profileView && (
        <ProfileModal
          type={profileView.type}
          id={profileView.id}
          onClose={() => setProfileView(null)}
        />
      )}
    </section>
  );
}

export default StudentsPage;
