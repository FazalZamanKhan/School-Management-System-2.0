import { useState, useCallback, useEffect } from "react";
import { Search, GraduationCap, UserCheck, Building2 } from "lucide-react";
import { PageHeader } from "./ui";
import ProfileModal from "./ProfileModal";
import CredentialDisplay from "../components/CredentialDisplay";
import { buildErrorMessage } from "../api";

const TEACHERS_API_URL = "/api/teachers/";
const CAMPUSES_API_URL = "/api/schools/campuses/";

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

function TeachersPage() {
  const [teachers, setTeachers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [campus, setCampus] = useState("");
  const [gender, setGender] = useState("");
  const [status, setStatus] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [editingTeacher, setEditingTeacher] = useState(null);

  const [profileView, setProfileView] = useState(null);

  const emptyForm = {
    employee_number: "",
    first_name: "",
    last_name: "",
    gender: "",
    date_of_birth: "",
    phone: "",
    email: "",
    primary_campus: "",
    joining_date: "",
    designation: "Teacher",
    status: "active",
    create_account: true,
    username: "",
    password: "",
  };

  const [form, setForm] = useState(emptyForm);
  const [photoFile, setPhotoFile] = useState(null);
  const [accountCreated, setAccountCreated] = useState(null);
  const [campuses, setCampuses] = useState([]);

  /* =========================
     LOAD TEACHERS
  ========================= */

  const loadTeachersData = useCallback(() => {
    const collect = async (startUrl) => {
      const all = [];
      let url = startUrl;

      while (url) {
        const response = await fetch(url, { credentials: "include" });

        if (!response.ok) {
          throw new Error("Failed to load teachers.");
        }

        const data = await response.json();
        const pageData = Array.isArray(data) ? data : data.results || [];

        all.push(...pageData);

        if (data && data.next) {
          const nextUrl = new URL(data.next, window.location.origin);
          url = nextUrl.pathname + nextUrl.search;
        } else {
          url = null;
        }
      }

      return all;
    };

    return collect(TEACHERS_API_URL)
      .then((teacherData) => {
        setTeachers(teacherData);
      })
      .catch((err) => {
        setError(err.message);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const loadTeachers = () => {
    setLoading(true);
    setError("");

    return loadTeachersData();
  };

  useEffect(() => {
    loadTeachersData();
  }, [loadTeachersData]);

  const loadCampuses = useCallback(() => {
    return fetch(CAMPUSES_API_URL, {
      credentials: "include",
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load campuses.");
        }
        return response.json();
      })
      .then((data) => {
        const campusData = Array.isArray(data) ? data : data.results || [];
        setCampuses(campusData);
      })
      .catch((err) => {
        console.error("Failed to load campuses:", err);
      });
  }, []);

  useEffect(() => {
    loadCampuses();
  }, [loadCampuses]);

  // Cleanup modal on unmount to prevent stuck overlays
  useEffect(() => {
    return () => {
      setShowForm(false);
      setEditingTeacher(null);
    };
  }, []);

  /* =========================
     FORM HANDLING
  ========================= */

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

  const openAddTeacher = () => {
    setEditingTeacher(null);
    setPhotoFile(null);
    setForm(emptyForm);
    setShowForm(true);
  };

  const openEditTeacher = (teacher) => {
    setEditingTeacher(teacher);
    setPhotoFile(null);

    setForm({
      employee_number: teacher.employee_number || "",
      first_name:
        teacher.first_name ||
        teacher.user?.first_name ||
        "",
      last_name:
        teacher.last_name ||
        teacher.user?.last_name ||
        "",
      gender: teacher.gender || "",
      date_of_birth: teacher.date_of_birth || "",
      phone: teacher.phone || "",
      email: teacher.email || "",
      primary_campus:
        teacher.primary_campus ||
        teacher.primary_campus_id ||
        teacher.campus?.id ||
        "",
      joining_date: teacher.joining_date || "",
      designation: teacher.designation || "Teacher",
      status: teacher.status || "active",
      create_account: false,
      username: teacher.linked_username || "",
      password: "",
    });

    setShowForm(true);
  };

  const closeForm = () => {
    if (saving) return;

    setShowForm(false);
    setEditingTeacher(null);
    setPhotoFile(null);
    setForm(emptyForm);
  };

  /* =========================
     SAVE TEACHER
  ========================= */

  const handleSubmit = async (event) => {
  event.preventDefault();

  setSaving(true);
  setError("");

  try {
    const isEditing = Boolean(editingTeacher);

    const url = isEditing
      ? `${TEACHERS_API_URL}${editingTeacher.id}/`
      : TEACHERS_API_URL;

    const csrfToken = getCookie("csrftoken");

    const headers = {};

    if (csrfToken) {
      headers["X-CSRFToken"] = csrfToken;
    }

    const body = new FormData();

    body.append("employee_number", form.employee_number);
    body.append("first_name", form.first_name);
    body.append("last_name", form.last_name);
    body.append("gender", form.gender);
    body.append(
      "date_of_birth",
      form.date_of_birth || ""
    );
    body.append("phone", form.phone || "");
    body.append("email", form.email || "");
    body.append("primary_campus", form.primary_campus || "");
    body.append(
      "joining_date",
      form.joining_date || ""
    );
    body.append("designation", form.designation || "");
    body.append("status", form.status);

    body.append(
      "create_account",
      String(Boolean(form.create_account))
    );

    if (form.create_account) {
      body.append("username", form.username || "");
      body.append("password", form.password || "");
    }

    if (photoFile) {
      body.append("photo", photoFile);
    }

    const response = await fetch(url, {
      method: isEditing ? "PUT" : "POST",
      credentials: "include",
      headers,
      body,
    });

    // Read response body ONLY ONCE
    const responseText = await response.text();

    let data = {};

    try {
      data = responseText
        ? JSON.parse(responseText)
        : {};
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
          fallback: "Unable to save teacher.",
        })
      );
    }

    closeForm();
    await loadTeachers();

    if (data.linked_username && data.generated_password) {
      setAccountCreated({
        username: data.linked_username,
        password: data.generated_password,
        name: getTeacherName({
          first_name: data.first_name,
          last_name: data.last_name,
        }),
      });
    }

  } catch (err) {
    setError(err.message);

  } finally {
    setSaving(false);
  }
};

  const handleDeleteTeacher = async (teacher) => {
    const confirmed = window.confirm(
      `Delete teacher "${getTeacherName(teacher)}"? ` +
        "This cannot be undone."
    );

    if (!confirmed) return;

    setSaving(true);
    setError("");

    try {
      const response = await fetch(
        `${TEACHERS_API_URL}${teacher.id}/`,
        {
          method: "DELETE",
          credentials: "include",
          headers: authHeaders(),
        }
      );

      if (!response.ok) {
        throw new Error("Unable to delete teacher.");
      }

      await loadTeachers();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  /* =========================
     FILTERS
  ========================= */

  const filteredTeachers = teachers.filter((teacher) => {
    const fullName =
      `${teacher.first_name || teacher.user?.first_name || ""} ${
        teacher.last_name || teacher.user?.last_name || ""
      }`.trim();

    const employeeNumber =
      teacher.employee_number || "";

    const phone = teacher.phone || "";

    const campusName =
      teacher.primary_campus_name ||
      (typeof teacher.campus === "object"
        ? teacher.campus?.name || ""
        : teacher.campus_name || "");

    const teacherGender =
      teacher.gender || "";

    const teacherStatus =
      teacher.status || "";

    const searchValue = search.toLowerCase();

    const matchesSearch =
      !search ||
      fullName.toLowerCase().includes(searchValue) ||
      employeeNumber.toLowerCase().includes(searchValue) ||
      phone.toLowerCase().includes(searchValue);

    const campusId =
      teacher.primary_campus != null
        ? String(teacher.primary_campus)
        : typeof teacher.campus === "object" && teacher.campus?.id != null
          ? String(teacher.campus.id)
          : String(teacher.campus ?? "");

    const matchesCampus =
      !campus ||
      campusId === String(campus) ||
      campusName.toLowerCase() === campus.toLowerCase();

    const matchesGender =
      !gender ||
      teacherGender.toLowerCase() === gender.toLowerCase();

    const matchesStatus =
      !status ||
      teacherStatus.toLowerCase() === status.toLowerCase();

    return (
      matchesSearch &&
      matchesCampus &&
      matchesGender &&
      matchesStatus
    );
  });

  /* =========================
     CAMPUS OPTIONS
  ========================= */

  const campusOptions = [
    ...campuses.filter((c) => c.name).map((c) => ({ id: c.id, name: c.name })),
  ];

  /* =========================
     HELPERS
  ========================= */

  const getTeacherName = (teacher) => {
    const firstName =
      teacher.first_name ||
      teacher.user?.first_name ||
      "";

    const lastName =
      teacher.last_name ||
      teacher.user?.last_name ||
      "";

    return `${firstName} ${lastName}`.trim() || "Unnamed Teacher";
  };

  const getCampusName = (teacher) => {
    if (teacher.primary_campus_name) {
      return teacher.primary_campus_name;
    }

    if (typeof teacher.campus === "object") {
      return teacher.campus?.name || "—";
    }

    return teacher.campus_name || teacher.campus || "—";
  };

  const getStatus = (teacher) => {
    return teacher.status || "active";
  };

  const getStatusLabel = (value) => {
    if (!value) return "Active";

    return value.charAt(0).toUpperCase() + value.slice(1);
  };

  const activeTeachers = teachers.filter(
    (teacher) => getStatus(teacher) === "active"
  ).length;
  const teacherCampuses = new Set(
    teachers.map((teacher) => getCampusName(teacher))
  ).size;

  return (
    <section className="content">
      {/* PAGE HEADER */}

      <PageHeader
        hero
        crumb="Home / Teachers"
        title="Teachers"
        subtitle="Manage teachers and teaching staff at Perfect Foundation School."
        stats={[
          {
            label: "Teachers",
            value: teachers.length,
            icon: <GraduationCap size={18} />,
            sub: "on the teaching staff",
          },
          {
            label: "Active",
            value: activeTeachers,
            icon: <UserCheck size={18} />,
            sub: "currently active",
          },
          {
            label: "Campuses",
            value: teacherCampuses,
            icon: <Building2 size={18} />,
            sub: "campuses served",
          },
        ]}
      />

      {/* SUCCESS (ACCOUNT CREATED) */}

      {accountCreated && (
        <CredentialDisplay
          username={accountCreated.username}
          password={accountCreated.password}
          name={accountCreated.name}
          note="Share these credentials with the teacher and remind them to change their password after first login."
          onDismiss={() => setAccountCreated(null)}
        />
      )}

      {/* ERROR */}

      {error && (
        <div className="state-card error">
          <strong>Unable to complete request.</strong>

          <span>{error}</span>

          <button
            className="secondary-button"
            onClick={loadTeachers}
          >
            Try Again
          </button>
        </div>
      )}

      {/* SEARCH PANEL */}

      <div className="teacher-filter-panel">
        <div className="teacher-search">
          <Search size={18} />

          <input
            type="text"
            placeholder="Search by name, employee number or phone..."
            value={search}
            onChange={(event) =>
              setSearch(event.target.value)
            }
          />
        </div>

        <select
          value={campus}
          onChange={(event) =>
            setCampus(event.target.value)
          }
        >
          <option value="">All campuses</option>

          {campusOptions.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>

        <select
          value={gender}
          onChange={(event) =>
            setGender(event.target.value)
          }
        >
          <option value="">All genders</option>
          <option value="male">Male</option>
          <option value="female">Female</option>
          <option value="other">Other</option>
        </select>

        <select
          value={status}
          onChange={(event) =>
            setStatus(event.target.value)
          }
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>

        <button
          className="primary-button"
          onClick={loadTeachers}
        >
          Search
        </button>

        <button
          className="secondary-button"
          onClick={() => {
            setSearch("");
            setCampus("");
            setGender("");
            setStatus("");
          }}
        >
          Clear
        </button>
      </div>

      {/* TEACHER LIST */}

      <div className="panel teacher-list-panel">
        <div className="teacher-list-header">
          <div>
            <h3>Teacher List</h3>

            <p>
              {loading
                ? "Loading teachers..."
                : `${filteredTeachers.length} teachers found`}
            </p>
          </div>

          <button
            className="primary-button add-teacher-button"
            onClick={openAddTeacher}
          >
            + Add Teacher
          </button>
        </div>

        {loading ? (
          <div className="state-card">
            Loading teacher data...
          </div>
        ) : filteredTeachers.length === 0 ? (
          <div className="empty-state">
            <GraduationCap size={42} />

            <h3>No teachers found</h3>

            <p>
              No teachers match the current search or filters.
            </p>

            <button
              className="primary-button"
              onClick={openAddTeacher}
            >
              + Add Teacher
            </button>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>EMPLOYEE NO.</th>
                  <th>TEACHER</th>
                  <th>DESIGNATION</th>
                  <th>CAMPUS</th>
                  <th>PHONE</th>
                  <th>GENDER</th>
                  <th>STATUS</th>
                  <th></th>
                </tr>
              </thead>

              <tbody>
                {filteredTeachers.map((teacher) => (
                  <tr key={teacher.id}>
                    <td>
                      <strong>
                        {teacher.employee_number || "—"}
                      </strong>
                    </td>

                    <td>
                      <div className="teacher-name-cell">
                        {teacher.photo_url ? (
                          <img
                            className="table-photo"
                            src={teacher.photo_url}
                            alt={getTeacherName(teacher)}
                          />
                        ) : (
                          <div className="teacher-avatar">
                            {getTeacherName(teacher)
                              .charAt(0)
                              .toUpperCase()}
                          </div>
                        )}

                        <div>
                          <strong>
                            {getTeacherName(teacher)}
                          </strong>

                          <span>
                            {teacher.email || "—"}
                          </span>
                        </div>
                      </div>
                    </td>

                    <td>
                      {teacher.designation || "Teacher"}
                    </td>

                    <td>
                      {getCampusName(teacher)}
                    </td>

                    <td>
                      {teacher.phone || "—"}
                    </td>

                    <td>
                      {teacher.gender
                        ? teacher.gender
                            .charAt(0)
                            .toUpperCase() +
                          teacher.gender.slice(1)
                        : "—"}
                    </td>

                    <td>
                      <span
                        className={`status-badge ${getStatus(
                          teacher
                        )}`}
                      >
                        {getStatusLabel(
                          getStatus(teacher)
                        )}
                      </span>
                    </td>

                    <td>
                      <button
                        className="table-action"
                        onClick={() =>
                          setProfileView({
                            type: "teacher",
                            id: teacher.id,
                          })
                        }
                      >
                        View Profile
                      </button>

                      <button
                        className="table-action"
                        onClick={() =>
                          openEditTeacher(teacher)
                        }
                      >
                        Edit
                      </button>

                      <button
                        className="table-action danger"
                        onClick={() =>
                          handleDeleteTeacher(teacher)
                        }
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ADD / EDIT MODAL */}

      {showForm && (
        <div
          className="modal-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeForm();
            }
          }}
        >
          <div className="teacher-modal">
            <div className="modal-header">
              <div>
                <h3>
                  {editingTeacher
                    ? "Edit Teacher"
                    : "Add Teacher"}
                </h3>

                <p>
                  {editingTeacher
                    ? "Update teacher information."
                    : "Create a new teacher profile."}
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
              <div className="form-section">
                <h4>Personal Information</h4>

                <div className="form-grid">
                  <label>
                    Employee Number
                    <input
                      name="employee_number"
                      value={form.employee_number}
                      onChange={handleChange}
                      placeholder="PF-EMP-0001 (auto)"
                    />
                    <small className="form-hint">Leave blank to auto-generate from the school name.</small>
                  </label>

                  <label>
                    Designation
                    <input
                      name="designation"
                      value={form.designation}
                      onChange={handleChange}
                      placeholder="Teacher"
                    />
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
                    Last Name
                    <input
                      name="last_name"
                      value={form.last_name}
                      onChange={handleChange}
                      placeholder="Last name"
                      required
                    />
                  </label>

                  <label>
                    Gender
                    <select
                      name="gender"
                      value={form.gender}
                      onChange={handleChange}
                      required
                    >
                      <option value="">
                        Select gender
                      </option>
                      <option value="male">Male</option>
                      <option value="female">Female</option>
                      <option value="other">Other</option>
                    </select>
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
                    Email
                    <input
                      type="email"
                      name="email"
                      value={form.email}
                      onChange={handleChange}
                      placeholder="teacher@example.com"
                    />
                  </label>
                </div>
              </div>

              <div className="form-section">
                <h4>Employment</h4>

                <div className="form-grid">
                  <label>
                    Campus
                    <select
                      name="primary_campus"
                      value={form.primary_campus}
                      onChange={handleChange}
                    >
                      <option value="">
                        Select campus
                      </option>

                      {campusOptions.map((opt) => (
                        <option key={opt.id} value={opt.id}>
                          {opt.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Joining Date
                    <input
                      type="date"
                      name="joining_date"
                      value={form.joining_date}
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
                      <option value="active">
                        Active
                      </option>

                      <option value="inactive">
                        Inactive
                      </option>
                    </select>
                  </label>
                </div>
              </div>

              <div className="form-section">
                <h4>Login Account</h4>

                {editingTeacher &&
                  editingTeacher.linked_username && (
                    <p className="field-hint">
                      This teacher is linked to username{" "}
                      <strong>
                        {editingTeacher.linked_username}
                      </strong>
                      .
                    </p>
                  )}

                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={Boolean(form.create_account)}
                    onChange={(event) =>
                      setForm((previous) => ({
                        ...previous,
                        create_account:
                          event.target.checked,
                      }))
                    }
                  />

                  <span>
                    {editingTeacher &&
                    editingTeacher.linked_username
                      ? "Reset this teacher's password"
                      : "Create a login account for this teacher"}
                  </span>
                </label>

                {form.create_account && (
                  <div className="form-grid">
                    {!(editingTeacher &&
                      editingTeacher.linked_username) && (
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
                    : editingTeacher
                    ? "Save Changes"
                    : "Add Teacher"}
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

export default TeachersPage;
