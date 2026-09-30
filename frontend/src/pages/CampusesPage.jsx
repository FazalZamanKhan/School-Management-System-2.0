import { useEffect, useState } from "react";
import {
  Building2,
  BookOpen,
  Users,
  LayoutGrid,
  Plus,
  Eye,
  Pencil,
  Trash2,
  X,
  Copy,
  Check,
} from "lucide-react";
import { useApiList } from "./useApiList";
import {
  PageHeader,
  PanelHeader,
  StateArea,
  EmptyState,
  StatusBadge,
} from "./ui";
import { apiFetch, authHeaders } from "../api";
import { useSchool } from "../schoolContext";
import { formatDate } from "./format";

const API_URL = "/api/schools/campuses/";
const TENANTS_URL = "/api/schools/tenants/";
const SCHOOLS_URL = "/api/schools/";

const emptyForm = {
  name: "",
  city: "",
  address: "",
  school: "",
  // Admin provisioning fields
  admin_first_name: "",
  admin_last_name: "",
  admin_username: "",
  admin_email: "",
  admin_password: "",
  admin_confirm_password: "",
  admin_phone: "",
  admin_position: "",
};

export default function CampusesPage() {
  const { rows, count, loading, error, refresh } = useApiList(API_URL);
  const { currentSchool, modules } = useSchool();

  const [schools, setSchools] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [form, setForm] = useState(emptyForm);

  const [viewing, setViewing] = useState(null);
  const [showPassword, setShowPassword] = useState(false);
  const [createdAdmin, setCreatedAdmin] = useState(null);

  // Campus admin management state
  const [campusAdmin, setCampusAdmin] = useState(null);
  const [campusAdminLoading, setCampusAdminLoading] = useState(false);
  const [campusAdminError, setCampusAdminError] = useState("");
  const [assignAdminForm, setAssignAdminForm] = useState({
    user_id: "",
    role: "campus_admin",
  });
  const [assignAdminSaving, setAssignAdminSaving] = useState(false);

  // Fetch campus admin when editing
  const fetchCampusAdmin = async (campusId) => {
    setCampusAdminLoading(true);
    setCampusAdminError("");
    try {
      const data = await apiFetch(`${API_URL}${campusId}/admin/`);
      setCampusAdmin(data.admins || []);
    } catch (err) {
      setCampusAdminError(err.message);
    } finally {
      setCampusAdminLoading(false);
    }
  };

  const currentParams = () =>
    new URLSearchParams(
      selectedSchool ? { school: selectedSchool } : {}
    );

  const buildForm = (firstSchoolId) => ({
    ...emptyForm,
    school: firstSchoolId ? String(firstSchoolId) : "",
  });

  // School dropdown for the campus form.
  //
  // Platform admins (superuser OR super_admin role — the same rule as the
  // backend's IsPlatformAdmin) may create campuses in ANY school, so they load
  // the full tenant list. Every other role is scoped to a single active school
  // and the Campus API ignores the `school` field for them anyway, so we seed
  // the dropdown from the current school instead. This avoids firing a
  // guaranteed 403 against the platform-only /api/schools/tenants/ endpoint
  // (which the backend correctly denies for non-platform users) during normal
  // page use.
  useEffect(() => {
    if (modules.isPlatformAdmin) {
      let cancelled = false;

      apiFetch(TENANTS_URL)
        .then((data) => {
          if (cancelled) return;
          const list = (data.tenants || []).map((t) => ({
            id: t.id,
            name: t.name,
          }));
          setSchools(list);
          if (list.length === 1) {
            setForm((f) => (f.school ? f : { ...f, school: String(list[0].id) }));
          }
        })
        .catch(() => {
          if (cancelled) return;
          apiFetch(SCHOOLS_URL)
            .then((rowsData) => {
              if (Array.isArray(rowsData) && rowsData.length) {
                const list = rowsData.map((s) => ({ id: s.id, name: s.name }));
                setSchools(list);
                setForm((f) => (f.school ? f : { ...f, school: String(list[0].id) }));
              }
            })
            .catch(() => {});
        });

      return () => {
        cancelled = true;
      };
    }

    if (currentSchool?.id) {
      const list = [{ id: currentSchool.id, name: currentSchool.name }];
      setSchools(list);
      setForm((f) => (f.school ? f : { ...f, school: String(list[0].id) }));
    }
  }, [currentSchool, modules.isPlatformAdmin]);

  const toggleForm = () => {
    const opening = !showForm;
    setShowForm(opening);

    if (opening) {
      setEditing(null);
      setFormError("");
      setCreatedAdmin(null);
      setForm(buildForm(schools.length === 1 ? schools[0].id : ""));
    } else {
      setEditing(null);
      setFormError("");
      setCreatedAdmin(null);
      setForm(emptyForm);
    }
  };

  const startEdit = (campus) => {
    setEditing(campus);
    setFormError("");
    setCreatedAdmin(null);
    setCampusAdmin(null);
    setCampusAdminError("");
    setAssignAdminForm({ user_id: "", role: "campus_admin" });
    setForm({
      name: campus.name,
      city: campus.city || "",
      address: campus.address || "",
      school: campus.school ? String(campus.school) : buildForm(schools.length === 1 ? schools[0].id : "").school,
    });
    setShowForm(true);
    // Fetch existing campus admin
    fetchCampusAdmin(campus.id);
  };

  const handlePasswordToggle = () => setShowPassword((v) => !v);

  const handleCopy = (text, label) => {
    navigator.clipboard.writeText(text);
    setFormError(`${label} copied to clipboard!`);
    setTimeout(() => setFormError(""), 2000);
  };

  // Campus admin assignment/removal handlers
  const handleAssignAdmin = async () => {
    if (!assignAdminForm.user_id) return;
    setAssignAdminSaving(true);
    setFormError("");
    try {
      await apiFetch(`${API_URL}${editing.id}/assign_admin/`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          user_id: parseInt(assignAdminForm.user_id, 10),
          role: assignAdminForm.role,
        }),
      });
      setAssignAdminForm({ user_id: "", role: "campus_admin" });
      await fetchCampusAdmin(editing.id);
    } catch (err) {
      setFormError(err.message);
    } finally {
      setAssignAdminSaving(false);
    }
  };

  const handleRemoveAdmin = async (userId, role) => {
    const confirmed = window.confirm(
      `Remove this ${role.replace("_", " ")} from campus "${editing.name}"?`
    );
    if (!confirmed) return;
    setAssignAdminSaving(true);
    setFormError("");
    try {
      await apiFetch(`${API_URL}${editing.id}/remove_admin/`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ user_id: userId, role }),
      });
      await fetchCampusAdmin(editing.id);
    } catch (err) {
      setFormError(err.message);
    } finally {
      setAssignAdminSaving(false);
    }
  };

  const submit = (event) => {
    event.preventDefault();
    setSaving(true);
    setFormError("");

    const isEdit = Boolean(editing);

    // Validate admin fields if provided
    const hasAdminData = form.admin_email || form.admin_position || form.admin_first_name || form.admin_last_name;
    if (hasAdminData) {
      if (!form.admin_email || !form.admin_position) {
        setFormError("Admin email and position are required when creating an admin.");
        setSaving(false);
        return;
      }
      if (!["principal", "vice_principal", "campus_admin"].includes(form.admin_position)) {
        setFormError("Position must be Principal, Vice Principal, or Campus Admin.");
        setSaving(false);
        return;
      }
      // If password is provided, validate it
      if (form.admin_password) {
        if (form.admin_password !== form.admin_confirm_password) {
          setFormError("Passwords do not match.");
          setSaving(false);
          return;
        }
        if (form.admin_password.length < 8) {
          setFormError("Password must be at least 8 characters.");
          setSaving(false);
          return;
        }
      }
      // If username is provided, validate it's not empty
      if (form.admin_username && !form.admin_username.trim()) {
        setFormError("Username cannot be empty if provided.");
        setSaving(false);
        return;
      }
    }

    const payload = {
      name: form.name,
      city: form.city,
      address: form.address,
    };

    if (form.school) {
      payload.school = form.school;
    }

    if (hasAdminData) {
      payload.admin = {
        username: form.admin_username || "",
        email: form.admin_email,
        password: form.admin_password || "",
        first_name: form.admin_first_name || "",
        last_name: form.admin_last_name || "",
        position: form.admin_position,
      };
    }

    apiFetch(isEdit ? `${API_URL}${editing.id}/` : API_URL, {
      method: isEdit ? "PATCH" : "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    })
      .then((data) => {
        setShowForm(false);
        setEditing(null);
        setForm(emptyForm);
        if (!isEdit && data.admin_username) {
          setCreatedAdmin({
            campusName: form.name,
            name: `${form.admin_first_name} ${form.admin_last_name}`,
            position: form.admin_position,
            username: data.admin_username,
            email: data.admin_email,
            password: data.admin_password,
          });
        }
        refresh(currentParams());
      })
      .catch((err) => setFormError(err.message))
      .finally(() => setSaving(false));
  };

  const removeCampus = (campus) => {
    const confirmed = window.confirm(
      `Delete campus "${campus.name}"?\n\n` +
        "This permanently removes the campus and all linked academic units, classes, sections and enrollments."
    );

    if (!confirmed) return;

    apiFetch(`${API_URL}${campus.id}/`, {
      method: "DELETE",
      headers: authHeaders(),
    })
      .then(() => refresh(currentParams()))
      .catch((err) => setFormError(err.message));
  };

  const onSchoolFilter = (event) => {
    const id = event.target.value;
    setSelectedSchool(id);
    refresh(new URLSearchParams(id ? { school: id } : {}));
  };

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Campuses"
        title="Campuses"
        subtitle="Manage campuses across schools and their statistics."
        action={
          <button type="button" className="primary-button" onClick={toggleForm}>
            <Plus size={15} />
            Add Campus
          </button>
        }
      />

      {showForm && (
        <div className="panel">
          <PanelHeader
            title={editing ? `Edit ${editing.name}` : "Add a new campus"}
            subtitle={
              editing
                ? "Update this campus' details."
                : "Choose which school this campus belongs to."
            }
          />
          <form onSubmit={submit} className="filter-row">
            <select
              required
              value={form.school}
              onChange={(e) => setForm({ ...form, school: e.target.value })}
              disabled={schools.length === 1}
            >
              <option value="">
                {schools.length ? "Select school *" : "Loading schools..."}
              </option>
              {schools.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <input
              required
              placeholder="Campus name *"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <input
              placeholder="City"
              value={form.city}
              onChange={(e) => setForm({ ...form, city: e.target.value })}
            />
<input
              placeholder="Address"
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
            />
            {!editing ? (
              <fieldset style={{ border: 0, padding: 0, marginTop: 16, borderTop: "1px solid var(--border)" }}>
                <legend style={{ fontSize: 13, fontWeight: 600, color: "var(--text-muted)", marginBottom: 12 }}>Campus Administrator (optional)</legend>
                <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                  Create the first admin user for this campus. Choose their role: Campus Admin (campus operations), Principal (campus leadership), or Vice Principal (deputy leadership). Username and password will be auto-generated if left blank.
                </p>
                <label>
                  Position *
                  <select
                    value={form.admin_position}
                    onChange={(e) => setForm({ ...form, admin_position: e.target.value })}
                  >
                    <option value="">Select position</option>
                    <option value="principal">Principal</option>
                    <option value="vice_principal">Vice Principal</option>
                    <option value="campus_admin">Campus Admin</option>
                  </select>
                </label>
                <label>
                  Email *
                  <input
                    type="email"
                    placeholder="e.g. admin@campus.edu"
                    value={form.admin_email}
                    onChange={(e) => setForm({ ...form, admin_email: e.target.value })}
                  />
                </label>
                <label>
                  Username (optional - auto-generated if blank)
                  <input
                    placeholder="e.g. principal_campus1"
                    value={form.admin_username}
                    onChange={(e) => setForm({ ...form, admin_username: e.target.value })}
                  />
                </label>
                <label>
                  Password (optional - auto-generated if blank)
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <input
                      type={showPassword ? "text" : "password"}
                      placeholder="Minimum 8 characters (auto-generated if blank)"
                      value={form.admin_password}
                      onChange={(e) => setForm({ ...form, admin_password: e.target.value })}
                      style={{ flex: 1 }}
                    />
                    <button type="button" className="secondary-button" onClick={handlePasswordToggle} style={{ padding: "8px 12px" }}>
                      {showPassword ? <Eye size={16} /> : <Eye size={16} style={{ opacity: 0.5 }} />}
                    </button>
                  </div>
                </label>
                <label>
                  Confirm Password (required only if password provided)
                  <input
                    type={showPassword ? "text" : "password"}
                    placeholder="Confirm password"
                    value={form.admin_confirm_password}
                    onChange={(e) => setForm({ ...form, admin_confirm_password: e.target.value })}
                  />
                </label>
                <label>
                  First name (optional)
                  <input
                    placeholder="e.g. John"
                    value={form.admin_first_name}
                    onChange={(e) => setForm({ ...form, admin_first_name: e.target.value })}
                  />
                </label>
                <label>
                  Last name (optional)
                  <input
                    placeholder="e.g. Doe"
                    value={form.admin_last_name}
                    onChange={(e) => setForm({ ...form, admin_last_name: e.target.value })}
                  />
                </label>
                <label>
                  Phone (optional)
                  <input
                    placeholder="e.g. +1234567890"
                    value={form.admin_phone || ""}
                    onChange={(e) => setForm({ ...form, admin_phone: e.target.value })}
                  />
                </label>
              </fieldset>
            ) : (
              // Campus Admin Management (Edit Mode)
              <fieldset style={{ border: 0, padding: 0, marginTop: 16, borderTop: "1px solid var(--border)" }}>
                <legend style={{ fontSize: 13, fontWeight: 600, color: "var(--text-muted)", marginBottom: 12 }}>
                  Campus Administrator
                </legend>
                {campusAdminLoading && (
                  <p style={{ fontSize: 12, color: "var(--text-muted)" }}>Loading campus administrator...</p>
                )}
                {campusAdminError && (
                  <div className="state-card error" style={{ marginBottom: 12 }}>
                    {campusAdminError}
                  </div>
                )}
                {campusAdmin && campusAdmin.length > 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {campusAdmin.map((admin) => (
                      <div key={admin.user_id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px", background: "var(--bg-secondary)", borderRadius: 8 }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 600 }}>{admin.first_name} {admin.last_name}</div>
                          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                            {admin.username} &middot; {admin.email}
                          </div>
                          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                            Role: {admin.role_display} &middot; Assigned: {new Date(admin.assigned_at).toLocaleDateString()}
                          </div>
                        </div>
                        <button
                          type="button"
                          className="table-action danger"
                          onClick={() => handleRemoveAdmin(admin.user_id, admin.role)}
                          disabled={assignAdminSaving}
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                    No campus administrator assigned. Assign an existing user below.
                  </p>
                )}
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
                  <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
                    Assign Existing User as Campus Administrator
                  </p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
                    <label style={{ flex: 1, minWidth: 200 }}>
                      User ID *
                      <input
                        type="number"
                        placeholder="e.g. 42"
                        value={assignAdminForm.user_id}
                        onChange={(e) => setAssignAdminForm({ ...assignAdminForm, user_id: e.target.value })}
                      />
                    </label>
                    <label style={{ flex: 1, minWidth: 180 }}>
                      Role
                      <select
                        value={assignAdminForm.role}
                        onChange={(e) => setAssignAdminForm({ ...assignAdminForm, role: e.target.value })}
                      >
                        <option value="campus_admin">Campus Admin</option>
                        <option value="principal">Principal</option>
                        <option value="vice_principal">Vice Principal</option>
                      </select>
                    </label>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={handleAssignAdmin}
                      disabled={assignAdminSaving || !assignAdminForm.user_id}
                    >
                      {assignAdminSaving ? "Assigning..." : "Assign"}
                    </button>
                  </div>
                </div>
              </fieldset>
            )}
            <button className="primary-button" disabled={saving}>
              {saving ? "Saving..." : editing ? "Update Campus" : "Save Campus"}
            </button>
          </form>
          {formError && (
            <div className="state-card error" style={{ marginTop: 10 }}>
              {formError}
            </div>
          )}
        </div>
      )}

      {createdAdmin && (
        <div className="panel">
          <PanelHeader
            title="Campus Created Successfully"
            subtitle="Administrator credentials generated. Save these securely — the password will not be shown again."
          />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16, marginTop: 16 }}>
            <div className="detail-grid">
              <div className="detail-label">Campus</div>
              <div className="detail-value" style={{ fontWeight: 600 }}>{createdAdmin.campusName}</div>
            </div>
            <div className="detail-grid">
              <div className="detail-label">Administrator</div>
              <div className="detail-value" style={{ fontWeight: 600 }}>{createdAdmin.name}</div>
            </div>
            <div className="detail-grid">
              <div className="detail-label">Position</div>
              <div className="detail-value" style={{ fontWeight: 600, textTransform: "capitalize" }}>{createdAdmin.position.replace("_", " ")}</div>
            </div>
            <div className="detail-grid">
              <div className="detail-label">Username</div>
              <div className="detail-value" style={{ fontFamily: "monospace", fontSize: 14 }}>
                <span>{createdAdmin.username}</span>
                <button className="secondary-button" onClick={() => handleCopy(createdAdmin.username, "Username")} style={{ marginLeft: 8, padding: "4px 8px", fontSize: 11 }}>
                  <Copy size={12} /> Copy
                </button>
              </div>
            </div>
            <div className="detail-grid">
              <div className="detail-label">Email</div>
              <div className="detail-value" style={{ fontFamily: "monospace", fontSize: 14 }}>
                <span>{createdAdmin.email}</span>
                <button className="secondary-button" onClick={() => handleCopy(createdAdmin.email, "Email")} style={{ marginLeft: 8, padding: "4px 8px", fontSize: 11 }}>
                  <Copy size={12} /> Copy
                </button>
              </div>
            </div>
            <div className="detail-grid">
              <div className="detail-label">Password</div>
              <div className="detail-value" style={{ fontFamily: "monospace", fontSize: 14 }}>
                <span>{createdAdmin.password}</span>
                <button className="secondary-button" onClick={() => handleCopy(createdAdmin.password, "Password")} style={{ marginLeft: 8, padding: "4px 8px", fontSize: 11 }}>
                  <Copy size={12} /> Copy
                </button>
              </div>
            </div>
          </div>
          <div style={{ marginTop: 16, display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button className="primary-button" onClick={() => setCreatedAdmin(null)}>
              <Check size={14} /> Done
            </button>
          </div>
        </div>
      )}

      <div className="panel">
        <PanelHeader
          title="Campus List"
          subtitle="campuses found"
          count={count}
          action={
            schools.length > 1 ? (
              <select
                value={selectedSchool}
                onChange={onSchoolFilter}
                style={{ maxWidth: 260 }}
              >
                <option value="">
                  All schools (current scope)
                </option>
                {schools.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            ) : null
          }
        />

        <StateArea
          loading={loading}
          error={error}
          onRetry={() => refresh(currentParams())}
        >
          {rows.length === 0 ? (
            <EmptyState
              icon={Building2}
              title="No campuses found"
              message="Click 'Add Campus' to create your first campus."
            />
          ) : (
            <div className="campuses-grid">
              {rows.map((campus) => (
                <div className="campus-card" key={campus.id}>
                  <div className="campus-card-head">
                    <div className="campus-card-icon">
                      <Building2 size={22} />
                    </div>

                    <div>
                      <strong>{campus.name}</strong>

                      <span>
                        {[
                          campus.school_name,
                          campus.city,
                          campus.address,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "—"}
                      </span>
                    </div>

                    <StatusBadge status={campus.status} />
                  </div>

                  <div className="campus-stats">
                    <div>
                      <Users size={17} />
                      <strong>
                        {campus.student_count ?? 0}
                      </strong>
                      <span>Students</span>
                    </div>

                    <div>
                      <BookOpen size={17} />
                      <strong>
                        {campus.class_count ?? 0}
                      </strong>
                      <span>Classes</span>
                    </div>

                    <div>
                      <LayoutGrid size={17} />
                      <strong>
                        {campus.section_count ?? 0}
                      </strong>
                      <span>Sections</span>
                    </div>
                  </div>

                  <div className="campus-card-actions">
                    <button
                      type="button"
                      className="table-action"
                      onClick={() => setViewing(campus)}
                    >
                      <Eye size={13} />
                      View
                    </button>
                    <button
                      type="button"
                      className="table-action"
                      onClick={() => startEdit(campus)}
                    >
                      <Pencil size={13} />
                      Edit
                    </button>
                    <button
                      type="button"
                      className="table-action danger"
                      onClick={() => removeCampus(campus)}
                    >
                      <Trash2 size={13} />
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </StateArea>
      </div>

      {viewing && (
        <div
          className="modal-overlay"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setViewing(null);
          }}
        >
          <div className="modal">
            <div className="modal-header">
              <h3>Campus details</h3>
              <button
                className="modal-close"
                onClick={() => setViewing(null)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="modal-body">
              <div className="campus-view-row">
                <span>Name</span>
                <strong>{viewing.name}</strong>
              </div>
              <div className="campus-view-row">
                <span>School</span>
                <strong>{viewing.school_name || "—"}</strong>
              </div>
              <div className="campus-view-row">
                <span>Status</span>
                <StatusBadge status={viewing.status} />
              </div>
              <div className="campus-view-row">
                <span>City</span>
                <strong>{viewing.city || "—"}</strong>
              </div>
              <div className="campus-view-row">
                <span>Address</span>
                <strong>{viewing.address || "—"}</strong>
              </div>
              <div className="campus-view-row">
                <span>Students</span>
                <strong>{viewing.student_count ?? 0}</strong>
              </div>
              <div className="campus-view-row">
                <span>Classes</span>
                <strong>{viewing.class_count ?? 0}</strong>
              </div>
              <div className="campus-view-row">
                <span>Sections</span>
                <strong>{viewing.section_count ?? 0}</strong>
              </div>
              <div className="campus-view-row">
                <span>Created</span>
                <strong>{formatDate(viewing.created_at)}</strong>
              </div>
              <div className="campus-view-row">
                <span>Updated</span>
                <strong>{formatDate(viewing.updated_at)}</strong>
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="table-action"
                onClick={() => {
                  const campus = viewing;
                  setViewing(null);
                  startEdit(campus);
                }}
              >
                <Pencil size={13} />
                Edit
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={() => setViewing(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}