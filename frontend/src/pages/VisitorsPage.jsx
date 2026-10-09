import { useEffect, useState } from "react";
import { Plus, X, LogOut, Search, UserCheck, DoorOpen } from "lucide-react";
import { PageHeader, PanelHeader, StateArea, EmptyState, StatusBadge } from "./ui";
import { apiFetch, authHeaders } from "../api";

const API_URL = "/api/visitors/visitors/";

const EMPTY_FORM = {
  campus: "",
  full_name: "",
  phone: "",
  id_number: "",
  company: "",
  vehicle_number: "",
  purpose: "",
  meeting_party: "",
};

const VISITOR_STATUS_LABELS = {
  checked_in: "Checked In",
  checked_out: "Checked Out",
  no_show: "No-show",
};

export default function VisitorsPage() {
  const [visitors, setVisitors] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [stats, setStats] = useState({ checked_in_now: 0, today: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState("");

  const loadVisitors = (params = new URLSearchParams()) => {
    setLoading(true);
    setError("");

    return fetch(`${API_URL}?${params.toString()}`, { credentials: "include" })
      .then((response) => {
        if (!response.ok) throw new Error("Failed to load visitors.");
        return response.json();
      })
      .then((data) => setVisitors(Array.isArray(data) ? data : []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadVisitors();

    fetch(`${API_URL}stats/`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : {}))
      .then(setStats)
      .catch(() => {});

    fetch("/api/schools/campuses/", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setCampuses(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  const applyFilters = (evt) => {
    evt.preventDefault();
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (query) params.set("q", query);
    loadVisitors(params);
  };

  const clearFilters = () => {
    setStatus("");
    setQuery("");
    loadVisitors();
  };

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((previous) => ({ ...previous, [name]: value }));
  };

  const checkIn = (event) => {
    event.preventDefault();
    if (!form.campus) {
      setFormError("Please choose a campus.");
      return;
    }
    if (form.phone) {
      const cleaned = form.phone.replace(/[\s\-\(\)\+]/g, "");
      if (!/\d/.test(form.phone) || cleaned.length < 5 || !/^[+0-9\s\-()]+$/.test(form.phone)) {
        setFormError("Please enter a valid phone number with numbers only.");
        return;
      }
    }
    setSaving(true);
    setFormError("");

    const payload = { ...form, campus: Number(form.campus) };

    apiFetch(API_URL, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    })
      .then(() => {
        setShowForm(false);
        setForm(EMPTY_FORM);
        loadVisitors();
        return fetch(`${API_URL}stats/`, { credentials: "include" })
          .then((r) => (r.ok ? r.json() : {}))
          .then(setStats);
      })
      .catch((err) => setFormError(err.message))
      .finally(() => setSaving(false));
  };

  const checkOut = (visitor) => {
    apiFetch(`${API_URL}${visitor.id}/checkout/`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: "{}",
    })
      .then(() => {
        loadVisitors();
        return fetch(`${API_URL}stats/`, { credentials: "include" })
          .then((r) => (r.ok ? r.json() : {}))
          .then(setStats);
      })
      .catch((err) => setError(err.message));
  };

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Gate / Visitors"
        title="Visitor Gate Log"
        subtitle="Check visitors in and out at the campus gate."
        action={
          <button className="primary-button" onClick={() => setShowForm(true)}>
            <Plus size={15} />
            Check In
          </button>
        }
      />

      {error && (
        <div className="state-card error">
          <strong>Unable to load visitors.</strong>
          <span>{error}</span>
          <button className="secondary-button" onClick={() => loadVisitors()}>
            Try Again
          </button>
        </div>
      )}

      <div className="stats-grid">
        <div className="stat-card">
          <DoorOpen size={20} />
          <strong>{stats.checked_in_now ?? 0}</strong>
          <span>Currently on campus</span>
        </div>
        <div className="stat-card">
          <UserCheck size={20} />
          <strong>{stats.today ?? 0}</strong>
          <span>Visitors today</span>
        </div>
      </div>

      <div className="panel">
        <form onSubmit={applyFilters}>
          <div className="filter-row">
            <div className="filter-search">
              <Search size={16} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search name, phone or meeting party..."
              />
            </div>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              <option value="checked_in">Checked in</option>
              <option value="checked_out">Checked out</option>
              <option value="no_show">No-show</option>
            </select>
            <button type="submit" className="secondary-button">Filter</button>
            <button type="button" className="secondary-button" onClick={clearFilters}>
              Clear
            </button>
          </div>
        </form>

        <PanelHeader title="Visitor Log" subtitle="visitors" count={visitors.length} />

        <StateArea loading={loading} error={error}>
          {visitors.length === 0 ? (
            <EmptyState
              icon={DoorOpen}
              title="No visitors logged"
              message="Check in a visitor at the gate to see them here."
            />
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Visitor</th>
                    <th>Badge</th>
                    <th>Campus</th>
                    <th>Purpose</th>
                    <th>Meeting Party</th>
                    <th>Checked In</th>
                    <th>Checked Out</th>
                    <th>Status</th>
                    <th className="table-action"></th>
                  </tr>
                </thead>
                <tbody>
                  {visitors.map((visitor) => (
                    <tr key={visitor.id}>
                      <td className="student-name-cell">
                        <strong>{visitor.full_name}</strong>
                        {visitor.phone && <span className="table-sub">{visitor.phone}</span>}
                      </td>
                      <td>{visitor.badge_number}</td>
                      <td>{visitor.campus_name}</td>
                      <td>{visitor.purpose || "—"}</td>
                      <td>{visitor.meeting_party || "—"}</td>
                      <td>{visitor.check_in ? new Date(visitor.check_in).toLocaleString() : "—"}</td>
                      <td>{visitor.check_out ? new Date(visitor.check_out).toLocaleString() : "—"}</td>
                      <td>
                        <StatusBadge status={visitor.status} label={VISITOR_STATUS_LABELS[visitor.status] || visitor.status} />
                      </td>
                      <td className="table-action">
                        {visitor.status === "checked_in" && (
                          <button className="secondary-button" onClick={() => checkOut(visitor)}>
                            <LogOut size={14} />
                            Check Out
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </StateArea>
      </div>

      {showForm && (
        <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) setShowForm(false); }}>
          <div className="teacher-modal">
            <div className="modal-header">
              <div>
                <h3>Check In Visitor</h3>
                <p>The gate will print a badge number automatically.</p>
              </div>
              <button className="modal-close" onClick={() => setShowForm(false)} disabled={saving}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={checkIn}>
              <div className="form-section">
                <div className="form-grid">
                  <label className="form-span">
                    Campus
                    <select name="campus" value={form.campus} onChange={handleChange} required>
                      <option value="">Select campus</option>
                      {campuses.map((item) => (
                        <option key={item.id} value={item.id}>{item.name}</option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Full Name
                    <input name="full_name" value={form.full_name} onChange={handleChange} required />
                  </label>
                  <label>
                    Phone
                    <input name="phone" value={form.phone} onChange={handleChange} />
                  </label>

                  <label>
                    ID / CNIC
                    <input name="id_number" value={form.id_number} onChange={handleChange} />
                  </label>
                  <label>
                    Company
                    <input name="company" value={form.company} onChange={handleChange} />
                  </label>

                  <label>
                    Vehicle Number
                    <input name="vehicle_number" value={form.vehicle_number} onChange={handleChange} />
                  </label>
                  <label>
                    Purpose
                    <input name="purpose" value={form.purpose} onChange={handleChange} />
                  </label>

                  <label className="form-span">
                    Meeting Party
                    <input name="meeting_party" value={form.meeting_party} onChange={handleChange} />
                  </label>
                </div>
                {formError && <div className="state-card error"><span>{formError}</span></div>}
              </div>

              <div className="modal-footer">
                <button type="button" className="secondary-button" onClick={() => setShowForm(false)} disabled={saving}>
                  Cancel
                </button>
                <button type="submit" className="primary-button" disabled={saving}>
                  <UserCheck size={16} />
                  {saving ? "Checking in..." : "Check In"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}