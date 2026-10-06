import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Building2,
  Plus,
  Power,
  Pencil,
  Eye,
  X,
  LogIn,
  Check,
  Pause,
  Play,
} from "lucide-react";
import { PageHeader, PanelHeader, StateArea } from "./ui";
import { apiFetch, authHeaders } from "../api";
import { useSchool } from "../schoolContext";

const BASE = "/api/schools/tenants/";

const STATUS_CHOICES = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "archived", label: "Archived" },
];

const EMPTY_FORM = {
  name: "",
  code: "",
  city: "",
  first_campus: "",
  admin_username: "",
  admin_email: "",
  admin_password: "",
  admin_first_name: "",
  admin_last_name: "",
  admin_phone: "",
};

function labelFor(status) {
  const found = STATUS_CHOICES.find((s) => s.value === status);
  return found ? found.label : status;
}

function SchoolModal({
  title,
  subtitle,
  saving,
  error,
  onClose,
  onSubmit,
  children,
}) {
  // Lock body scroll when modal is open
  useEffect(() => {
    document.body.classList.add("modal-open");
    return () => document.body.classList.remove("modal-open");
  }, []);

  return (
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !saving) onClose();
      }}
    >
      <div className="teacher-modal">
        <div className="modal-header">
          <div>
            <h3>{title}</h3>
            {subtitle && (
              <p className="hint" style={{ margin: "2px 0 0" }}>
                {subtitle}
              </p>
            )}
          </div>
          <button
            className="modal-close"
            onClick={onClose}
            disabled={saving}
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
        <form onSubmit={onSubmit}>
          <div className="modal-body">
            {error && (
              <div className="state-card error" style={{ marginBottom: 12 }}>
                <strong>Unable to save school.</strong>
                <span>{error}</span>
              </div>
            )}
            <div className="form-grid" style={{ gridTemplateColumns: "1fr" }}>
              {children}
            </div>
          </div>
          <div className="modal-footer">
            <button
              type="button"
              className="secondary-button"
              onClick={onClose}
              disabled={saving}
            >
              Cancel
            </button>
            <button type="submit" className="primary-button" disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function SchoolDetail({
    tenant,
    onClose,
    onEdit,
    onModules,
    onAccess,
    canAccess,
    schoolAdmins,
    schoolAdminsLoading,
    schoolAdminsError,
    assignSchoolAdminForm,
    setAssignSchoolAdminForm,
    assignSchoolAdminSaving,
    handleAssignSchoolAdmin,
    handleRemoveSchoolAdmin,
  }) {
  useEffect(() => {
    document.body.classList.add("modal-open");
    return () => document.body.classList.remove("modal-open");
  }, []);

  return (
    <div className="modal-overlay" onMouseDown={(e) => {
      if (e.target === e.currentTarget) onClose();
    }}>
      <div className="teacher-modal large">
        <div className="modal-header">
          <div>
            <h3>{tenant.name}</h3>
            {tenant.city && (
              <p className="hint" style={{ margin: "2px 0 0" }}>
                {tenant.city}
              </p>
            )}
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="modal-body">
          <div className="detail-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 16 }}>
            <div className="form-group">
              <div className="detail-label" style={{ fontSize: 12, color: "var(--text-muted)" }}>School code</div>
              <div className="detail-value" style={{ fontWeight: 600 }}>{tenant.code || "—"}</div>
            </div>
            <div className="form-group">
              <div className="detail-label" style={{ fontSize: 12, color: "var(--text-muted)" }}>Status</div>
              <div className="detail-value" style={{ fontWeight: 600 }}>{labelFor(tenant.status)}</div>
            </div>
            <div className="form-group">
              <div className="detail-label" style={{ fontSize: 12, color: "var(--text-muted)" }}>Campuses</div>
              <div className="detail-value" style={{ fontWeight: 600 }}>{tenant.stats?.campuses ?? 0}</div>
            </div>
            <div className="form-group">
              <div className="detail-label" style={{ fontSize: 12, color: "var(--text-muted)" }}>Students</div>
              <div className="detail-value" style={{ fontWeight: 600 }}>{tenant.stats?.students ?? 0}</div>
            </div>
            <div className="form-group">
              <div className="detail-label" style={{ fontSize: 12, color: "var(--text-muted)" }}>Created</div>
              <div className="detail-value" style={{ fontWeight: 600 }}>
                {tenant.created_at ? new Date(tenant.created_at).toLocaleDateString() : "—"}
              </div>
            </div>
            <div className="form-group">
              <div className="detail-label" style={{ fontSize: 12, color: "var(--text-muted)" }}>School ID</div>
              <div className="detail-value" style={{ fontWeight: 600 }}>{tenant.id}</div>
            </div>
          </div>

          <div className="form-section">
            <h4>Modules</h4>
            {tenant.enabled_modules?.length ? (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {tenant.enabled_modules.map((mod) => (
                  <span key={mod} className="status-badge info">{mod}</span>
                ))}
              </div>
            ) : (
              <p className="hint">All modules enabled.</p>
            )}
          </div>

          {/* School Administrators Section */}
          <div className="form-section" style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
            <h4>School Administrators</h4>
            {schoolAdminsLoading && (
              <p style={{ fontSize: 12, color: "var(--text-muted)" }}>Loading school administrators...</p>
            )}
            {schoolAdminsError && (
              <div className="state-card error" style={{ marginBottom: 12 }}>
                {schoolAdminsError}
              </div>
            )}
            {schoolAdmins && schoolAdmins.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {schoolAdmins.map((admin) => (
                  <div key={admin.user_id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px", background: "var(--bg-secondary)", borderRadius: 8 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600 }}>{admin.first_name} {admin.last_name}</div>
                      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                        {admin.username} &middot; {admin.email}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                        Role: School Admin &middot; Assigned: {new Date(admin.assigned_at).toLocaleDateString()}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="table-action danger"
                      onClick={() => handleRemoveSchoolAdmin(admin.user_id)}
                      disabled={assignSchoolAdminSaving}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
                No school administrators assigned. Assign an existing user below.
              </p>
            )}
            <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
                Assign Existing User as School Administrator
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
                <label style={{ flex: 1, minWidth: 200 }}>
                  User ID *
                  <input
                    type="number"
                    placeholder="e.g. 42"
                    value={assignSchoolAdminForm.user_id}
                    onChange={(e) => setAssignSchoolAdminForm({ user_id: e.target.value })}
                  />
                </label>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => handleAssignSchoolAdmin(tenant.id)}
                  disabled={assignSchoolAdminSaving || !assignSchoolAdminForm.user_id}
                >
                  {assignSchoolAdminSaving ? "Assigning..." : "Assign"}
                </button>
              </div>
            </div>
          </div>

        </div>
        <div className="modal-footer">
          <button type="button" className="secondary-button" onClick={() => onModules(tenant)}>
            Modules
          </button>
          <button type="button" className="secondary-button" onClick={() => onEdit(tenant)}>
            <Pencil size={13} /> Edit
          </button>
          {canAccess && (
            <button type="button" className="primary-button" onClick={() => onAccess(tenant)}>
              <LogIn size={13} /> Access dashboard
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function TenantsPage() {
  const [tenants, setTenants] = useState([]);
  const [allModules, setAllModules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState(EMPTY_FORM);
  const [createSaving, setCreateSaving] = useState(false);
  const [createError, setCreateError] = useState("");
  const [created, setCreated] = useState(null);

  const [editForm, setEditForm] = useState(null);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState("");

  const [detail, setDetail] = useState(null);

  const [editingModules, setEditingModules] = useState(null);
  const [draftModules, setDraftModules] = useState([]);

  // School admin management state
  const [schoolAdmins, setSchoolAdmins] = useState(null);
  const [schoolAdminsLoading, setSchoolAdminsLoading] = useState(false);
  const [schoolAdminsError, setSchoolAdminsError] = useState("");
  const [assignSchoolAdminForm, setAssignSchoolAdminForm] = useState({
    user_id: "",
  });
  const [assignSchoolAdminSaving, setAssignSchoolAdminSaving] = useState(false);

  // Fetch school admins when viewing detail
  const fetchSchoolAdmins = async (schoolId) => {
    setSchoolAdminsLoading(true);
    setSchoolAdminsError("");
    try {
      const data = await apiFetch(`/api/schools/tenants/${schoolId}/admins/`);
      setSchoolAdmins(data.admins || []);
    } catch (err) {
      setSchoolAdminsError(err.message);
    } finally {
      setSchoolAdminsLoading(false);
    }
  };

  // School admin assignment/removal handlers
  const handleAssignSchoolAdmin = async (schoolId) => {
    if (!assignSchoolAdminForm.user_id) return;
    setAssignSchoolAdminSaving(true);
    setError("");
    try {
      await apiFetch(`/api/schools/tenants/${schoolId}/assign_admin/`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          user_id: parseInt(assignSchoolAdminForm.user_id, 10),
        }),
      });
      setAssignSchoolAdminForm({ user_id: "" });
      await fetchSchoolAdmins(schoolId);
    } catch (err) {
      setError(err.message);
    } finally {
      setAssignSchoolAdminSaving(false);
    }
  };

  const handleRemoveSchoolAdmin = async (userId) => {
    const confirmed = window.confirm(
      `Remove this School Admin from the school?`
    );
    if (!confirmed) return;
    setAssignSchoolAdminSaving(true);
    setError("");
    try {
      // We need to know the school ID - get it from detail
      const schoolId = detail?.id;
      if (!schoolId) throw new Error("School context lost");
      await apiFetch(`/api/schools/tenants/${schoolId}/remove_admin/`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ user_id: userId }),
      });
      await fetchSchoolAdmins(schoolId);
    } catch (err) {
      setError(err.message);
    } finally {
      setAssignSchoolAdminSaving(false);
    }
  };

  const { switchSchool } = useSchool();
  const navigate = useNavigate();

  const load = useCallback(() => {
    setLoading(true);
    setError("");

    apiFetch(BASE)
      .then((data) => {
        setTenants(data.tenants || []);
        setAllModules(data.all_modules || []);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const extractError = (err) => {
    if (err && err.message && err.message !== "Request failed.") {
      return err.message;
    }
    return "Something went wrong. Please try again.";
  };

  const createTenant = (event) => {
    event.preventDefault();
    setCreateSaving(true);
    setCreateError("");

    const hasAdminData = createForm.admin_username || createForm.admin_email || createForm.admin_password;

    apiFetch(BASE, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        name: createForm.name,
        code: createForm.code,
        city: createForm.city,
        first_campus: createForm.first_campus,
        admin: hasAdminData ? {
          username: createForm.admin_username,
          email: createForm.admin_email,
          password: createForm.admin_password,
          first_name: createForm.admin_first_name,
          last_name: createForm.admin_last_name,
          phone: createForm.admin_phone,
        } : undefined,
      }),
    })
      .then((data) => {
        setShowCreate(false);
        setCreateForm(EMPTY_FORM);
        setCreated(data);
        setNotice(`School "${data.name}" created.`);
        load();
      })
      .catch((err) => setCreateError(extractError(err)))
      .finally(() => setCreateSaving(false));
  };

  const updateSchool = (event) => {
    event.preventDefault();
    if (!editForm) return;
    setEditSaving(true);
    setEditError("");

    const hasAdminData = editForm.admin_username || editForm.admin_email || editForm.admin_password;

    const payload = {
      name: editForm.name,
      code: editForm.code,
      city: editForm.city,
      status: editForm.status,
      admin: hasAdminData ? {
        username: editForm.admin_username,
        email: editForm.admin_email,
        password: editForm.admin_password,
        first_name: editForm.admin_first_name,
        last_name: editForm.admin_last_name,
        phone: editForm.admin_phone,
      } : undefined,
    };

    apiFetch(`${BASE}${editForm.id}/`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    })
      .then((data) => {
        setEditForm(null);
        setEditError("");
        setDetail(null);
        setNotice(`"${payload.name}" updated.`);
        if (data.admin) {
          setNotice(`"${payload.name}" updated. Admin user created: ${data.admin.username}`);
        }
        load();
      })
      .catch((err) => setEditError(extractError(err)))
      .finally(() => setEditSaving(false));
  };

  const toggleStatus = (tenant) => {
    const next = tenant.status === "active" ? "inactive" : "active";

    apiFetch(`${BASE}${tenant.id}/`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ status: next }),
    })
      .then(() => {
        setNotice(`${tenant.name} is now ${next}.`);
        load();
      })
      .catch((err) => setError(err.message));
  };

  const togglePause = (tenant) => {
    const next = !tenant.is_paused;

    apiFetch(`${BASE}${tenant.id}/`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ is_paused: next }),
    })
      .then(() => {
        setNotice(`${tenant.name} ${next ? "paused." : "resumed."}`);
        load();
      })
      .catch((err) => setError(err.message));
  };

  const saveModules = (tenant) => {
    apiFetch(`${BASE}${tenant.id}/`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ enabled_modules: draftModules }),
    })
      .then(() => {
        setEditingModules(null);
        setDetail(null);
        setNotice(`Modules updated for ${tenant.name}.`);
        load();
      })
      .catch((err) => setError(err.message));
  };

  const openModules = (tenant) => {
    setDetail(null);
    setEditingModules(tenant.id);
    setDraftModules(tenant.enabled_modules?.length ? [...tenant.enabled_modules] : [...allModules]);
  };

  const openEdit = (tenant) => {
    setDetail(null);
    setEditingModules(null);
    setEditForm({
      id: tenant.id,
      name: tenant.name,
      code: tenant.code || "",
      city: tenant.city || "",
      status: tenant.status,
      admin_username: "",
      admin_email: "",
      admin_password: "",
      admin_first_name: "",
      admin_last_name: "",
      admin_phone: "",
    });
    setEditError("");
  };

  // Open detail view and fetch school admins
  const openDetail = (tenant) => {
    setEditingModules(null);
    setEditForm(null);
    setDetail(tenant);
    fetchSchoolAdmins(tenant.id);
  };

  const accessSchool = (tenant) => {
    switchSchool(tenant.id)
      .then(() => {
        setDetail(null);
        setNotice(`Switched context to "${tenant.name}".`);
        navigate("/");
      })
      .catch((err) => setError(extractError(err)));
  };

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Schools"
        title="Platform · Schools"
        subtitle="Create schools, activate or deactivate tenants, and control which modules each school gets."
        action={
          <button
            type="button"
            className="primary-button"
            onClick={() => {
              setShowCreate((v) => !v);
              setCreated(null);
              setCreateError("");
            }}
          >
            <Plus size={15} />
            New School
          </button>
        }
      />

      {showCreate && (
        <SchoolModal
          title="Onboard a new school"
          subtitle="Creates an isolated tenant. Modules can be adjusted after creation."
          saving={createSaving}
          error={createError}
          onClose={() => setShowCreate(false)}
          onSubmit={createTenant}
        >
          <label>
            School name *
            <input
              required
              placeholder="e.g. Springfield Academy"
              value={createForm.name}
              onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
            />
          </label>
          <label>
            Short code
            <input
              placeholder="Optional (auto-generated if blank)"
              value={createForm.code}
              onChange={(e) => setCreateForm({ ...createForm, code: e.target.value })}
            />
          </label>
          <label>
            City
            <input
              placeholder="e.g. Lahore"
              value={createForm.city}
              onChange={(e) => setCreateForm({ ...createForm, city: e.target.value })}
            />
          </label>
          <label>
            First campus name
            <input
              placeholder="Optional — creates an initial campus"
              value={createForm.first_campus}
              onChange={(e) => setCreateForm({ ...createForm, first_campus: e.target.value })}
            />
          </label>
          <fieldset style={{ border: 0, padding: 0, marginTop: 16, borderTop: "1px solid var(--border)" }}>
            <legend style={{ fontSize: 13, fontWeight: 600, color: "var(--text-muted)", marginBottom: 12 }}>School Administrator (optional)</legend>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
              Create the first admin user for this school. They will have full admin access.
            </p>
            <label>
              Username *
              <input
                placeholder="e.g. admin_springfield"
                value={createForm.admin_username}
                onChange={(e) => setCreateForm({ ...createForm, admin_username: e.target.value })}
              />
            </label>
            <label>
              Email *
              <input
                type="email"
                placeholder="e.g. admin@springfield.edu"
                value={createForm.admin_email}
                onChange={(e) => setCreateForm({ ...createForm, admin_email: e.target.value })}
              />
            </label>
            <label>
              Password *
              <input
                type="password"
                placeholder="Minimum 8 characters"
                value={createForm.admin_password}
                onChange={(e) => setCreateForm({ ...createForm, admin_password: e.target.value })}
              />
            </label>
            <label>
              First name
              <input
                placeholder="e.g. John"
                value={createForm.admin_first_name}
                onChange={(e) => setCreateForm({ ...createForm, admin_first_name: e.target.value })}
              />
            </label>
            <label>
              Last name
              <input
                placeholder="e.g. Doe"
                value={createForm.admin_last_name}
                onChange={(e) => setCreateForm({ ...createForm, admin_last_name: e.target.value })}
              />
            </label>
            <label>
              Phone
              <input
                placeholder="e.g. +92 300 1234567"
                value={createForm.admin_phone}
                onChange={(e) => setCreateForm({ ...createForm, admin_phone: e.target.value })}
              />
            </label>
          </fieldset>
        </SchoolModal>
      )}

      {editForm && (
        <SchoolModal
          title={`Edit school — ${editForm.name}`}
          subtitle="Update school details. Changes apply to this tenant only."
          saving={editSaving}
          error={editError}
          onClose={() => setEditForm(null)}
          onSubmit={updateSchool}
        >
          <label>
            School name *
            <input
              required
              value={editForm.name}
              onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
            />
          </label>
          <label>
            Short code
            <input
              value={editForm.code}
              onChange={(e) => setEditForm({ ...editForm, code: e.target.value })}
            />
          </label>
          <label>
            City
            <input
              value={editForm.city}
              onChange={(e) => setEditForm({ ...editForm, city: e.target.value })}
            />
          </label>
          <label>
            Status
            <select
              value={editForm.status}
              onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
            >
              {STATUS_CHOICES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <fieldset style={{ border: 0, padding: 0, marginTop: 16, borderTop: "1px solid var(--border)" }}>
            <legend style={{ fontSize: 13, fontWeight: 600, color: "var(--text-muted)", marginBottom: 12 }}>Add School Administrator (optional)</legend>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
              Create an additional admin user for this school. They will have full admin access.
            </p>
            <label>
              Username *
              <input
                placeholder="e.g. admin_springfield"
                value={editForm.admin_username || ""}
                onChange={(e) => setEditForm({ ...editForm, admin_username: e.target.value })}
              />
            </label>
            <label>
              Email *
              <input
                type="email"
                placeholder="e.g. admin@springfield.edu"
                value={editForm.admin_email || ""}
                onChange={(e) => setEditForm({ ...editForm, admin_email: e.target.value })}
              />
            </label>
            <label>
              Password *
              <input
                type="password"
                placeholder="Minimum 8 characters"
                value={editForm.admin_password || ""}
                onChange={(e) => setEditForm({ ...editForm, admin_password: e.target.value })}
              />
            </label>
            <label>
              First name
              <input
                placeholder="e.g. John"
                value={editForm.admin_first_name || ""}
                onChange={(e) => setEditForm({ ...editForm, admin_first_name: e.target.value })}
              />
            </label>
            <label>
              Last name
              <input
                placeholder="e.g. Doe"
                value={editForm.admin_last_name || ""}
                onChange={(e) => setEditForm({ ...editForm, admin_last_name: e.target.value })}
              />
            </label>
            <label>
              Phone
              <input
                placeholder="e.g. +92 300 1234567"
                value={editForm.admin_phone || ""}
                onChange={(e) => setEditForm({ ...editForm, admin_phone: e.target.value })}
              />
            </label>
          </fieldset>
        </SchoolModal>
      )}

      {detail && !editForm && (
        <SchoolDetail
          tenant={detail}
          onClose={() => setDetail(null)}
          onEdit={openEdit}
          onModules={openModules}
          onAccess={accessSchool}
          canAccess
          schoolAdmins={schoolAdmins}
          schoolAdminsLoading={schoolAdminsLoading}
          schoolAdminsError={schoolAdminsError}
          assignSchoolAdminForm={assignSchoolAdminForm}
          setAssignSchoolAdminForm={setAssignSchoolAdminForm}
          assignSchoolAdminSaving={assignSchoolAdminSaving}
          handleAssignSchoolAdmin={(schoolId) => handleAssignSchoolAdmin(schoolId)}
          handleRemoveSchoolAdmin={handleRemoveSchoolAdmin}
        />
      )}

      <div className="panel">
        <PanelHeader
          title="Tenants"
          subtitle={notice || `${tenants.length} schools on this platform`}
        />

        {created && (
          <div className="state-card success" style={{ marginBottom: 12 }}>
            <strong>School created successfully.</strong>
            <span>
              {created.name} (code: {created.code || "auto-generated"}) is ready.
              Credentials are not auto-generated — create the school administrator
              from the school's staff area.
            </span>
            <button type="button" className="secondary-button" onClick={() => setCreated(null)}>
              Dismiss
            </button>
          </div>
        )}

        <StateArea loading={loading} error={error} onRetry={load}>
          {tenants.length === 0 ? (
            <div className="empty-state">
              <Building2 size={42} />
              <h3>No schools yet</h3>
              <p>Create your first tenant using the "New School" button.</p>
            </div>
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>School</th>
                    <th>Code</th>
                    <th>Status</th>
                    <th>Campuses</th>
                    <th>Students</th>
                    <th>Modules</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {tenants.map((tenant) => (
                    <tr key={tenant.id}>
                      <td>
                        <strong>{tenant.name}</strong>
                        <small style={{ display: "block" }}>
                          {tenant.city || "—"}
                        </small>
                      </td>
                      <td>{tenant.code || "—"}</td>
                      <td>
                        <span className={`status-badge ${tenant.status === "active" ? "active" : tenant.status === "inactive" ? "inactive" : "warn"}`}>
                          {labelFor(tenant.status)}
                        </span>
                        {tenant.is_paused && (
                          <span className="status-badge warn">
                            Paused
                          </span>
                        )}
                      </td>
                      <td>{tenant.stats?.campuses ?? 0}</td>
                      <td>{tenant.stats?.students ?? 0}</td>
                      <td>
                        {(tenant.enabled_modules?.length
                          ? tenant.enabled_modules.length + " enabled"
                          : "All")}
                        {editingModules === tenant.id && (
                          <div
                            style={{
                              marginTop: 8,
                              maxWidth: 320,
                              display: "grid",
                              gridTemplateColumns: "1fr 1fr",
                              gap: 4,
                            }}
                          >
                            {allModules.map((mod) => (
                              <label key={mod} style={{ fontSize: 12 }}>
                                <input
                                  type="checkbox"
                                  checked={draftModules.includes(mod)}
                                  onChange={(e) =>
                                    setDraftModules(
                                      e.target.checked
                                        ? [...draftModules, mod]
                                        : draftModules.filter((m) => m !== mod)
                                    )
                                  }
                                />{" "}
                                {mod}
                              </label>
                            ))}
                            <button
                              type="button"
                              className="primary-button"
                              onClick={() => saveModules(tenant)}
                            >
                              Save
                            </button>
                          </div>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="table-action"
                          title="View details"
                          onClick={() => {
                            setEditingModules(null);
                            setEditForm(null);
                            openDetail(editingModules === tenant.id ? null : tenant);
                          }}
                        >
                          <Eye size={13} />
                          View
                        </button>{" "}
                        <button
                          type="button"
                          className="table-action"
                          title="Edit school"
                          onClick={() => openEdit(tenant)}
                        >
                          <Pencil size={13} />
                          Edit
                        </button>{" "}
                        <button
                          type="button"
                          className="table-action"
                          title="Toggle modules"
                          onClick={() => {
                            setDetail(null);
                            if (editingModules !== tenant.id) {
                              setEditingModules(tenant.id);
                              setDraftModules(
                                tenant.enabled_modules?.length
                                  ? [...tenant.enabled_modules]
                                  : [...allModules]
                              );
                            } else {
                              setEditingModules(null);
                            }
                          }}
                        >
                          {editingModules === tenant.id ? (
                            <Check size={13} />
                          ) : (
                            <span>Modules</span>
                          )}
                        </button>{" "}
                        <button
                          type="button"
                          className="table-action"
                          title={
                            tenant.is_paused
                              ? "Resume school operations"
                              : tenant.status === "active"
                              ? "Pause school operations"
                              : "Only active schools can be paused"
                          }
                          onClick={() => togglePause(tenant)}
                          disabled={
                            !tenant.is_paused &&
                            tenant.status !== "active"
                          }
                        >
                          {tenant.is_paused ? (
                            <Play size={13} />
                          ) : (
                            <Pause size={13} />
                          )}
                          {tenant.is_paused ? "Resume" : "Pause"}
                        </button>{" "}
                        <button
                          type="button"
                          className="table-action"
                          onClick={() => toggleStatus(tenant)}
                        >
                          <Power size={13} />
                          {tenant.status === "active" ? "Deactivate" : "Activate"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </StateArea>
      </div>
    </section>
  );
}
