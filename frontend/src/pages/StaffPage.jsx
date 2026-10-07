import {
  useCallback,
  useEffect,
  useState,
} from "react";
import {
  Search,
  Users,
  UserPlus,
  Building2,
  Briefcase,
  Phone,
  Mail,
  ShieldCheck,
  LayoutGrid,
  Eye,
  Pencil,
  Trash2,
} from "lucide-react";

import ProfileModal from "./ProfileModal";
import CredentialDisplay from "../components/CredentialDisplay";
import { buildErrorMessage } from "../api";
import { matchesStaffCampus } from "../staffCampusFilter";

const STAFF_API_URL = "/api/staff/";

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

const DESIGNATION_OPTIONS = [
  "Janitor",
  "Security Guard",
  "Nurse",
  "Librarian",
  "Clerk",
  "Accountant",
  "Driver",
  "Cook",
  "Gardener",
  "Counsellor",
  "Lab Assistant",
  "Administrative Officer",
  "Cleaner",
  "Technician",
  "Other",
];

const DEPARTMENT_OPTIONS = [
  "Administration",
  "Maintenance",
  "Security",
  "Health",
  "Library",
  "Accounts",
  "Transport",
  "Kitchen",
  "Grounds",
  "Student Services",
  "Other",
];

export default function StaffPage() {
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [campus, setCampus] = useState("");
  const [designation, setDesignation] = useState("");
  const [department, setDepartment] = useState("");
  const [status, setStatus] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [editingStaff, setEditingStaff] = useState(null);
  const [photoFile, setPhotoFile] = useState(null);
  const [accountCreated, setAccountCreated] = useState(null);
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
    designation: "Other",
    department: "",
    joining_date: "",
    status: "active",
    create_account: true,
    username: "",
    password: "",
  };

  const [form, setForm] = useState(emptyForm);
  const [campuses, setCampuses] = useState([]);

  /* =========================
     LOAD STAFF & CAMPUSES
  ========================= */

  const loadCampuses = useCallback(() => {
    return fetch("/api/schools/campuses/", {
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

  const loadStaffData = useCallback(() => {
    return fetch(STAFF_API_URL, {
      credentials: "include",
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load staff.");
        }

        return response.json();
      })
      .then((data) => {
        const staffData = Array.isArray(data)
          ? data
          : data.results || data.staff || [];

        setStaff(staffData);
      })
      .catch((err) => {
        setError(err.message);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const loadStaff = () => {
    setLoading(true);
    setError("");

    return loadStaffData();
  };

  useEffect(() => {
    loadStaffData();
    loadCampuses();
  }, [loadStaffData, loadCampuses]);

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

  const openAddStaff = () => {
    setEditingStaff(null);
    setPhotoFile(null);
    setForm(emptyForm);
    setShowForm(true);
  };

  const openEditStaff = (member) => {
    setEditingStaff(member);
    setPhotoFile(null);

    setForm({
      employee_number: member.employee_number || "",
      first_name: member.first_name || "",
      last_name: member.last_name || "",
      gender: member.gender || "",
      date_of_birth: member.date_of_birth || "",
      phone: member.phone || "",
      email: member.email || "",
      primary_campus: member.primary_campus || "",
      designation: member.designation || "Other",
      department: member.department || "",
      joining_date: member.joining_date || "",
      status: member.status || "active",
      create_account: false,
      username: member.linked_username || "",
      password: "",
    });

    setShowForm(true);
  };

  const closeForm = () => {
    if (saving) return;

    setShowForm(false);
    setEditingStaff(null);
    setPhotoFile(null);
    setForm(emptyForm);
  };

  /* =========================
     SAVE STAFF
  ========================= */

  const handleSubmit = async (event) => {
    event.preventDefault();

    setSaving(true);
    setError("");

    try {
      const isEditing = Boolean(editingStaff);

      const url = isEditing
        ? `${STAFF_API_URL}${editingStaff.id}/`
        : STAFF_API_URL;

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
      body.append("date_of_birth", form.date_of_birth || "");
      body.append("phone", form.phone || "");
      body.append("email", form.email || "");
      body.append("primary_campus", form.primary_campus || "");
      body.append("designation", form.designation || "");
      body.append("department", form.department || "");
      body.append("joining_date", form.joining_date || "");
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
            fallback: "Unable to save staff member.",
          })
        );
      }

      closeForm();
      await loadStaff();

      if (data.linked_username && data.generated_password) {
        setAccountCreated({
          username: data.linked_username,
          password: data.generated_password,
          name: data.full_name,
        });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  /* =========================
     DELETE
  ========================= */

  const handleDeleteStaff = async (member) => {
    const confirmed = window.confirm(
      `Delete staff member "${getStaffName(member)}"? ` +
        "This cannot be undone."
    );

    if (!confirmed) return;

    setSaving(true);
    setError("");

    try {
      const response = await fetch(
        `${STAFF_API_URL}${member.id}/`,
        {
          method: "DELETE",
          credentials: "include",
          headers: authHeaders(),
        }
      );

      if (!response.ok) {
        throw new Error("Unable to delete staff member.");
      }

      await loadStaff();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  /* =========================
     FILTERS
  ========================= */

  const getStaffName = (member) => {
    const firstName = member.first_name || "";
    const lastName = member.last_name || "";

    return `${firstName} ${lastName}`.trim() || "Unnamed Staff";
  };

  const getStatus = (member) => {
    return member.status || "active";
  };

  const getStatusLabel = (value) => {
    if (!value) return "Active";

    return value.charAt(0).toUpperCase() + value.slice(1);
  };

  const filteredStaff = staff.filter((member) => {
    const fullName = getStaffName(member);
    const employeeNumber = member.employee_number || "";
    const phone = member.phone || "";

    const searchValue = search.toLowerCase();

    const matchesSearch =
      !search ||
      fullName.toLowerCase().includes(searchValue) ||
      employeeNumber.toLowerCase().includes(searchValue) ||
      phone.toLowerCase().includes(searchValue) ||
      (member.designation || "")
        .toLowerCase()
        .includes(searchValue) ||
      (member.department || "")
        .toLowerCase()
        .includes(searchValue);

    const matchesCampus = matchesStaffCampus(member, campus);

    const matchesDesignation =
      !designation ||
      (member.designation || "").toLowerCase() ===
        designation.toLowerCase();

    const matchesDepartment =
      !department ||
      (member.department || "").toLowerCase() ===
        department.toLowerCase();

    const matchesStatus =
      !status ||
      (member.status || "").toLowerCase() === status.toLowerCase();

    return (
      matchesSearch &&
      matchesCampus &&
      matchesDesignation &&
      matchesDepartment &&
      matchesStatus
    );
  });

  const campusOptions = [
    ...campuses.filter((c) => c.name).map((c) => ({ id: c.id, name: c.name })),
  ];

  const departmentOptions = [
    ...new Set(
      staff
        .map((member) => member.department)
        .filter(Boolean)
        .concat(DEPARTMENT_OPTIONS)
    ),
  ];

  const designationOptions = [
    ...new Set(
      staff
        .map((member) => member.designation)
        .filter(Boolean)
        .concat(DESIGNATION_OPTIONS)
    ),
  ];

  const totalStaff = staff.length;

  const activeStaff = staff.filter(
    (member) =>
      (member.status || "active").toLowerCase() === "active"
  ).length;

  return (
    <section className="content">
      {/* IMMERSIVE HERO */}

      <div className="staff-hero">
        <div className="staff-hero-glow staff-hero-glow-a" />
        <div className="staff-hero-glow staff-hero-glow-b" />

        <div className="staff-hero-top">
          <div>
            <div className="breadcrumb">Home / Staff</div>

            <h2>Staff Roster</h2>

            <p className="subtitle">
              Meet the people keeping every campus running —
              janitors, security guards, nurses and support
              personnel.
            </p>
          </div>

          <button
            className="primary-button staff-add-button"
            onClick={openAddStaff}
          >
            <UserPlus size={17} />
            Add Staff Member
          </button>
        </div>

        <div className="staff-hero-stats">
          <div className="staff-hero-stat">
            <div className="staff-hero-stat-icon">
              <Users size={20} />
            </div>

            <div>
              <strong>{totalStaff}</strong>
              <span>Total Staff</span>
            </div>
          </div>

          <div className="staff-hero-stat">
            <div className="staff-hero-stat-icon">
              <ShieldCheck size={20} />
            </div>

            <div>
              <strong>{activeStaff}</strong>
              <span>Active Members</span>
            </div>
          </div>

          <div className="staff-hero-stat">
            <div className="staff-hero-stat-icon">
              <Briefcase size={20} />
            </div>

            <div>
              <strong>{departmentOptions.length}</strong>
              <span>Departments</span>
            </div>
          </div>

          <div className="staff-hero-stat">
            <div className="staff-hero-stat-icon">
              <Building2 size={20} />
            </div>

            <div>
              <strong>{campusOptions.length}</strong>
              <span>Campuses</span>
            </div>
          </div>
        </div>
      </div>

      {/* SUCCESS (ACCOUNT CREATED) */}

      {accountCreated && (
        <CredentialDisplay
          username={accountCreated.username}
          password={accountCreated.password}
          name={accountCreated.name}
          note="Share these credentials with the staff member and remind them to change their password after first login."
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
            onClick={loadStaff}
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
            placeholder="Search by name, employee number, designation or phone..."
            value={search}
            onChange={(event) =>
              setSearch(event.target.value)
            }
          />
        </div>

        <select
          value={campus}
          onChange={(event) => setCampus(event.target.value)}
        >
          <option value="">All campuses</option>

          {campusOptions.map((opt) => (
            <option key={opt.id} value={opt.id}>
              {opt.name}
            </option>
          ))}
        </select>

        <select
          value={designation}
          onChange={(event) =>
            setDesignation(event.target.value)
          }
        >
          <option value="">All designations</option>

          {designationOptions.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>

        <select
          value={department}
          onChange={(event) =>
            setDepartment(event.target.value)
          }
        >
          <option value="">All departments</option>

          {departmentOptions.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>

        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>

        <button className="primary-button" onClick={loadStaff}>
          Search
        </button>

        <button
          className="secondary-button"
          onClick={() => {
            setSearch("");
            setCampus("");
            setDesignation("");
            setDepartment("");
            setStatus("");
          }}
        >
          Clear
        </button>
      </div>

      {/* DEPARTMENT CHIPS */}

      <div className="staff-chips">
        <span className="staff-chips-label">
          Departments:
        </span>

        <button
          className={`staff-chip ${
            department === "" ? "active" : ""
          }`}
          onClick={() => setDepartment("")}
        >
          All
        </button>

        {departmentOptions.map((item) => (
          <button
            key={item}
            className={`staff-chip ${
              department === item ? "active" : ""
            }`}
            onClick={() =>
              setDepartment(
                department === item ? "" : item
              )
            }
          >
            {item}
          </button>
        ))}
      </div>

      {/* RESULTS HEADER */}

      <div className="staff-results">
        <span>
          <LayoutGrid size={16} />
          Showing {filteredStaff.length} of {totalStaff} staff
          members
        </span>
      </div>

      {/* STAFF LIST */}

      <div className="panel teacher-list-panel">
        {loading ? (
          <div className="state-card">Loading staff data...</div>
        ) : filteredStaff.length === 0 ? (
          <div className="empty-state">
            <Users size={42} />

            <h3>No staff found</h3>

            <p>
              No staff members match the current search or
              filters.
            </p>

            <button
              className="primary-button"
              onClick={openAddStaff}
            >
              + Add Staff Member
            </button>
          </div>
        ) : (
          <div className="staff-grid">
            {filteredStaff.map((member) => {
              const fullName = getStaffName(member);
              const statusKey = getStatus(member);

              return (
                <article
                  className="staff-card"
                  key={member.id}
                >
                  <div className="staff-card-head">
                    {member.photo_url ? (
                      <img
                        className="staff-card-photo"
                        src={member.photo_url}
                        alt={fullName}
                      />
                    ) : (
                      <div className="staff-card-avatar">
                        {fullName
                          .charAt(0)
                          .toUpperCase()}
                      </div>
                    )}

                    <span
                      className={`status-badge ${statusKey}`}
                    >
                      {getStatusLabel(statusKey)}
                    </span>
                  </div>

                  <div className="staff-card-body">
                    <h3>{fullName}</h3>

                    <p className="staff-card-designation">
                      {member.designation || "—"}
                    </p>

                    <span className="staff-card-empno">
                      {member.employee_number || "—"}
                    </span>

                    <div className="staff-card-meta">
                      <span>
                        <Briefcase size={14} />
                        {member.department || "—"}
                      </span>

                      <span>
                        <Building2 size={14} />
                        {member.primary_campus
                          ? campuses.find((c) => c.id === member.primary_campus)?.name || "—"
                          : "—"}
                      </span>

                      <span>
                        <Phone size={14} />
                        {member.phone || "—"}
                      </span>

                      {member.email && (
                        <span>
                          <Mail size={14} />
                          {member.email}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="staff-card-actions">
                    <button
                      className="staff-card-action"
                      onClick={() =>
                        setProfileView({
                          type: "staff",
                          id: member.id,
                        })
                      }
                    >
                      <Eye size={15} />
                      Profile
                    </button>

                    <button
                      className="staff-card-action"
                      onClick={() =>
                        openEditStaff(member)
                      }
                    >
                      <Pencil size={15} />
                      Edit
                    </button>

                    <button
                      className="staff-card-action danger"
                      onClick={() =>
                        handleDeleteStaff(member)
                      }
                    >
                      <Trash2 size={15} />
                      Delete
                    </button>
                  </div>
                </article>
              );
            })}
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
                  {editingStaff
                    ? "Edit Staff Member"
                    : "Add Staff Member"}
                </h3>

                <p>
                  {editingStaff
                    ? "Update staff information."
                    : "Create a new staff profile."}
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
                      placeholder="staff@example.com"
                    />
                  </label>
                </div>
              </div>

              <div className="form-section">
                <h4>Employment</h4>

                <div className="form-grid">
                  <label>
                    Designation
                    <input
                      name="designation"
                      value={form.designation}
                      onChange={handleChange}
                      placeholder="Janitor, Guard, Nurse..."
                      list="staff-designations"
                    />

                    <datalist id="staff-designations">
                      {DESIGNATION_OPTIONS.map((item) => (
                        <option key={item} value={item} />
                      ))}
                    </datalist>
                  </label>

                  <label>
                    Department
                    <input
                      name="department"
                      value={form.department}
                      onChange={handleChange}
                      placeholder="Maintenance, Security..."
                      list="staff-departments"
                    />

                    <datalist id="staff-departments">
                      {DEPARTMENT_OPTIONS.map((item) => (
                        <option key={item} value={item} />
                      ))}
                    </datalist>
                  </label>

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
                      <option value="active">Active</option>

                      <option value="inactive">
                        Inactive
                      </option>
                    </select>
                  </label>
                </div>
              </div>

              <div className="form-section">
                <h4>Login Account</h4>

                {editingStaff && editingStaff.linked_username && (
                  <p className="field-hint">
                    This staff member is linked to username{" "}
                    <strong>
                      {editingStaff.linked_username}
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
                    {editingStaff &&
                    editingStaff.linked_username
                      ? "Reset this staff member's password"
                      : "Create a login account for this staff member"}
                  </span>
                </label>

                {form.create_account && (
                  <div className="form-grid">
                    {!(editingStaff &&
                      editingStaff.linked_username) && (
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
                    : editingStaff
                    ? "Save Changes"
                    : "Add Staff Member"}
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
