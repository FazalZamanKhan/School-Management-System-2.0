import { useCallback, useEffect, useState } from "react";
import { GraduationCap, Pencil, Plus, Trash2, X } from "lucide-react";
import { PageHeader, PanelHeader, StateArea } from "./ui";
import { apiFetch, authHeaders } from "../api";
import { useToast } from "../toast";

const BASE = "/api/alumni/";

export default function AlumniPage() {
  const toast = useToast();
  const [rows, setRows] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [batchYear, setBatchYear] = useState("");
  const [campusFilter, setCampusFilter] = useState("");

  const [editing, setEditing] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [viewing, setViewing] = useState(null);
  const [form, setForm] = useState({
    full_name: "",
    batch_year: new Date().getFullYear(),
    campus: "",
    email: "",
    phone: "",
    occupation: "",
    organization: "",
    city: "",
    notes: "",
  });

  useEffect(() => {
    fetch("/api/schools/campuses/", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setCampuses(Array.isArray(data) ? data : data.results || []))
      .catch(() => {});
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError("");

    const params = new URLSearchParams();
    if (search) params.append("search", search);
    if (batchYear) params.append("batch_year", batchYear);
    if (campusFilter) params.append("campus", campusFilter);

    apiFetch(`${BASE}?${params.toString()}`)
      .then((data) => setRows(data.results || data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [search, batchYear, campusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const openEdit = (row) => {
    setEditing(row);
    setShowForm(true);
    setForm({
      full_name: row.full_name ?? "",
      batch_year: row.batch_year ?? new Date().getFullYear(),
      campus: row.campus ?? "",
      email: row.email ?? "",
      phone: row.phone ?? "",
      occupation: row.occupation ?? "",
      organization: row.organization ?? "",
      city: row.city ?? "",
      notes: row.notes ?? "",
    });
  };

  const handleDelete = async (row) => {
    if (!window.confirm(`Delete alumni record for "${row.full_name}"? This cannot be undone.`)) return;

    setSaving(true);
    setFormError("");

    try {
      await apiFetch(
        `${BASE}${row.id}/`,
        { method: "DELETE" },
        "Could not delete the alumni record."
      );
      load();
      toast.success(`Alumni record for "${row.full_name}" deleted.`);
    } catch (err) {
      setFormError(err.message);
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  const submit = (event) => {
    event.preventDefault();
    if (!form.full_name.trim()) {
      setFormError("Enter a full name.");
      return;
    }
    const emailInput = event.currentTarget.querySelector('input[type="email"]');
    if (emailInput && !emailInput.checkValidity()) {
      setFormError("Enter a valid email address.");
      return;
    }
    const year = Number(form.batch_year);
    const currentYear = new Date().getFullYear();
    if (!Number.isInteger(year) || year < 1980 || year > currentYear) {
      setFormError(`Batch year must be between 1980 and ${currentYear}.`);
      return;
    }
    setSaving(true);
    setFormError("");

    const isEditing = Boolean(editing);

    apiFetch(isEditing ? `${BASE}${editing.id}/` : BASE, {
      method: isEditing ? "PATCH" : "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ ...form, batch_year: year }),
    })
      .then(() => {
        setEditing(null);
        setShowForm(false);
        load();
        toast.success(isEditing ? "Alumni record updated." : "Alumni record added.");
      })
      .catch((err) => {
        setFormError(err.message);
        toast.error(err.message);
      })
      .finally(() => setSaving(false));
  };

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Alumni"
        title="Alumni Network"
        subtitle="Stay connected with former students."
        action={
          <button
            type="button"
            className="primary-button"
            onClick={() => {
              setEditing(null);
              setShowForm((v) => !v);
            }}
          >
            <Plus size={15} />
            Add Alumni
          </button>
        }
      />

      {showForm && (
        <div className="panel">
          <PanelHeader title={editing ? "Edit alumni record" : "Add alumni record"} />
          <form onSubmit={submit} className="filter-row" noValidate>
            <input
              required
              aria-label="Full name"
              placeholder="Full name *"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />

            <input
              required
              type="number"
              min="1980"
              max={new Date().getFullYear()}
              step="1"
              aria-label="Batch year"
              placeholder="Batch year *"
              value={form.batch_year}
              onChange={(e) => setForm({ ...form, batch_year: e.target.value })}
            />

            <select
              value={form.campus}
              onChange={(e) => setForm({ ...form, campus: e.target.value })}
            >
              <option value="">Campus (optional)</option>
              {campuses.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>

            <input
              aria-label="Occupation"
              placeholder="Occupation"
              value={form.occupation}
              onChange={(e) => setForm({ ...form, occupation: e.target.value })}
            />

            <input
              aria-label="Email"
              placeholder="Email"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />

            <input
              aria-label="Phone"
              placeholder="Phone"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />

            <input
              aria-label="City"
              placeholder="City"
              value={form.city}
              onChange={(e) => setForm({ ...form, city: e.target.value })}
            />

            <button
              type="button"
              className="secondary-button"
              onClick={() => { setEditing(null); setShowForm(false); }}
            >
              Cancel
            </button>
            <button className="primary-button" disabled={saving}>
              {saving ? "Saving..." : editing ? "Save Changes" : "Save"}
            </button>
          </form>
          {formError && <div className="state-card error">{formError}</div>}
        </div>
      )}

      <div className="panel">
        <PanelHeader title="Alumni" subtitle={`${rows.length} records`} />

        <StateArea loading={loading} error={error} onRetry={load}>
          <div className="filter-row">
            <input
              className="filter-search"
              aria-label="Search alumni"
              placeholder="Search by name, organization or city..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />

            <input
              type="number"
              aria-label="Filter by batch year"
              placeholder="Batch year"
              value={batchYear}
              onChange={(e) => setBatchYear(e.target.value)}
            />

            <select
              value={campusFilter}
              onChange={(e) => setCampusFilter(e.target.value)}
            >
              <option value="">All campuses</option>
              {campuses.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>

          {rows.length === 0 ? (
            <div className="empty-state">
              <GraduationCap size={42} />
              <h3>No alumni records</h3>
              <p>Add former students to build the network.</p>
            </div>
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Batch</th>
                    <th>Campus</th>
                    <th>Occupation</th>
                    <th>Organization</th>
                    <th>City</th>
                    <th>Contact</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td><strong>{row.full_name}</strong></td>
                      <td>{row.batch_year}</td>
                      <td>{row.campus_name || "—"}</td>
                      <td>{row.occupation || "—"}</td>
                      <td>{row.organization || "—"}</td>
                      <td>{row.city || "—"}</td>
                      <td>
                        {row.email && <small style={{ display: "block" }}>{row.email}</small>}
                        {row.phone && <small>{row.phone}</small>}
                        {!row.email && !row.phone && "—"}
                      </td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <button
                          type="button"
                          className="table-action"
                          onClick={() => setViewing(row)}
                        >
                          View
                        </button>
                        <button
                          type="button"
                          className="table-action"
                          onClick={() => openEdit(row)}
                        >
                          <Pencil size={13} /> Edit
                        </button>
                        <button
                          type="button"
                          className="table-action danger"
                          onClick={() => handleDelete(row)}
                        >
                          <Trash2 size={13} /> Delete
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

      {viewing && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={`Alumni record — ${viewing.full_name}`}
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setViewing(null);
          }}
        >
          <div className="teacher-modal">
            <div className="modal-header">
              <div>
                <h3>{viewing.full_name}</h3>
                <p>Alumni record detail</p>
              </div>
              <button className="modal-close" aria-label="Close" onClick={() => setViewing(null)}>
                <X size={18} />
              </button>
            </div>

            <div className="form-section">
              <div className="table-wrapper">
                <table className="data-table">
                  <tbody>
                    <tr><th className="detail-label">Batch Year</th><td>{viewing.batch_year || "—"}</td></tr>
                    <tr><th className="detail-label">Campus</th><td>{viewing.campus_name || "—"}</td></tr>
                    <tr><th className="detail-label">Occupation</th><td>{viewing.occupation || "—"}</td></tr>
                    <tr><th className="detail-label">Organization</th><td>{viewing.organization || "—"}</td></tr>
                    <tr><th className="detail-label">Email</th><td>{viewing.email || "—"}</td></tr>
                    <tr><th className="detail-label">Phone</th><td>{viewing.phone || "—"}</td></tr>
                    <tr><th className="detail-label">City</th><td>{viewing.city || "—"}</td></tr>
                    <tr><th className="detail-label">Notes</th><td>{viewing.notes || "—"}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="primary-button"
                onClick={() => {
                  openEdit(viewing);
                  setViewing(null);
                }}
              >
                <Pencil size={15} /> Edit
              </button>
              <button
                type="button"
                className="secondary-button"
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
