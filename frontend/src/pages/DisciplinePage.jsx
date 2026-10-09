import { useCallback, useEffect, useState, createElement } from "react";
import { X, Plus, Trash2, Edit, AlertTriangle } from "lucide-react";
import { apiFetch } from "../api";
import { useApiList } from "./useApiList";
import { PanelHeader, StateArea, EmptyState } from "./ui";
import { formatDate } from "./format";

const API_URL = "/api/discipline/incidents/";

const SEVERITIES = [
  { value: "minor", label: "Minor" },
  { value: "moderate", label: "Moderate" },
  { value: "major", label: "Major" },
];

const STATUSES = [
  { value: "open", label: "Open" },
  { value: "action_taken", label: "Action Taken" },
  { value: "resolved", label: "Resolved" },
];

const EMPTY_FORM = {
  title: "",
  description: "",
  location: "",
  incident_date: "",
  status: "open",
  severity: "minor",
  student: "",
  campus: "",
};

export default function DisciplinePage() {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [validationErrors, setValidationErrors] = useState({});
  const [students, setStudents] = useState([]);
  const [campuses, setCampuses] = useState([]);

  const {
    count,
    page,
    refresh,
  } = useApiList(API_URL);

  const applyFilters = (pageNumber = 1) => {
    const params = buildParams(pageNumber);
    refresh(params);
    load(params);
  };

  const buildParams = (pageNumber = 1) => {
    const params = new URLSearchParams();
    params.append("page", pageNumber);
    params.append("page_size", 50);
    return params;
  };

  const loadStudents = useCallback(() => {
    fetch("/api/students/?page_size=1000", {
      credentials: "include",
    })
      .then((response) => (response.ok ? response.json() : []))
      .then((json) => {
        const list = Array.isArray(json)
          ? json
          : Array.isArray(json.results)
            ? json.results
            : [];
        setStudents(list);
      })
      .catch(() => {});
  }, []);

  const loadCampuses = useCallback(() => {
    fetch("/api/schools/campuses/", {
      credentials: "include",
    })
      .then((response) => (response.ok ? response.json() : []))
      .then((data) => setCampuses(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setValidationErrors({});
    setShowForm(true);
  };

  const openEdit = (incident) => {
    setEditing(incident);
    setValidationErrors({});
    setForm({
      title: incident.title || "",
      description: incident.description || "",
      location: incident.location || "",
      incident_date: toDateInput(incident.incident_date),
      status: incident.status || "open",
      severity: incident.severity || "minor",
      student: incident.student ? String(incident.student) : "",
      campus: incident.campus ? String(incident.campus) : "",
    });
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditing(null);
    setForm(EMPTY_FORM);
    setValidationErrors({});
  };

  const severityClass = (sev) => {
    const s = (sev || "").toLowerCase();
    if (s === "major") return "danger";
    if (s === "moderate") return "warning";
    return "success";
  };

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((previous) => ({ ...previous, [name]: value }));
    setValidationErrors((previous) => ({ ...previous, [name]: "" }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const errors = {};
    if (!form.student) errors.student = "Select a student.";
    if (!form.campus) errors.campus = "Select a campus.";
    if (!form.title.trim()) errors.title = "Enter an incident title.";
    else if (form.title.trim().length > 200) errors.title = "Title must be 200 characters or fewer.";
    if (!form.description.trim()) errors.description = "Describe what happened.";
    if (form.location.length > 200) errors.location = "Location must be 200 characters or fewer.";
    if (!form.incident_date || Number.isNaN(Date.parse(form.incident_date))) {
      errors.incident_date = "Enter a valid incident date.";
    } else if (new Date(`${form.incident_date}T00:00:00`) > new Date(new Date().toDateString())) {
      errors.incident_date = "Incident date cannot be in the future.";
    }
    if (!SEVERITIES.some(({ value }) => value === form.severity)) errors.severity = "Select a valid severity.";
    if (!STATUSES.some(({ value }) => value === form.status)) errors.status = "Select a valid status.";
    setValidationErrors(errors);
    if (Object.keys(errors).length) return;

    setSaving(true);
    setError("");

    try {
      if (editing) {
        await apiFetch(
          `${API_URL}${editing.id}/`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(form),
          },
          "Failed to update the incident."
        );
      } else {
        await apiFetch(
          API_URL,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(form),
          },
          "Failed to create the incident."
        );
      }

      closeForm();
      applyFilters(page);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (incident) => {
    if (!window.confirm(`Delete incident "${incident.title}"?`)) {
      return;
    }

    try {
      await apiFetch(
        `${API_URL}${incident.id}/`,
        { method: "DELETE" },
        "Failed to delete the incident."
      );
      applyFilters(page);
    } catch (err) {
      setError(err.message || String(err));
    }
  };

  const load = useCallback((params) => {
    setLoading(true);
    setError("");
    const query = params || new URLSearchParams({ page: "1", page_size: "50" });

    fetch(`${API_URL}?${query.toString()}`, { credentials: "include" })
      .then((response) => {
        if (!response.ok) throw new Error("Failed to load incidents.");
        return response.json();
      })
      .then((json) => {
        const rows = Array.isArray(json)
          ? json
          : Array.isArray(json?.results)
            ? json.results
            : [];
        setIncidents(rows);
        setLoading(false);
      })
      .catch((err) => setError(err.message || "Failed to load incidents."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    loadStudents();
    loadCampuses();
  }, [load, loadStudents, loadCampuses]);

  // Build table rows using createElement to avoid rolldown JSX parsing issues
  const buildTableRows = () => {
    const rows = [];
    for (let i = 0; i < incidents.length; i++) {
      const incident = incidents[i];
      const sev = (incident.severity || "").toLowerCase();
      const sevClass =
        sev === "major"
          ? "row-danger"
          : sev === "moderate"
            ? "row-warning"
            : "";
      const severityStyle = {
        padding: "2px 6px",
        borderRadius: "10px",
        fontSize: "11px",
        fontWeight: 600,
        color:
          severityClass(incident.severity) === "danger"
            ? "var(--danger)"
            : severityClass(incident.severity) === "warning"
              ? "var(--warning)"
              : "var(--success)",
      };

      rows.push(
        createElement(
          "tr",
          { key: incident.id, className: sevClass },
          createElement(
            "td",
            null,
            createElement("strong", null, incident.title || "—")
          ),
          createElement(
            "td",
            null,
            incident.student_name || incident.admission_number || "—"
          ),
          createElement(
            "td",
            null,
            createElement(
              "span",
              { style: severityStyle },
              incident.severity || "—"
            )
          ),
          createElement("td", null, incident.category || incident.status || "—"),
          createElement("td", null, formatDate(incident.created_at)),
          createElement(
            "td",
            { style: { whiteSpace: "nowrap" } },
            createElement(
              "button",
              {
                className: "table-action",
                title: "Edit incident",
                onClick: () => openEdit(incident),
              },
              createElement(Edit, { size: 14 })
            ),
            createElement(
              "button",
              {
                className: "table-action danger",
                title: "Delete incident",
                onClick: () => handleDelete(incident),
              },
              createElement(Trash2, { size: 14 })
            )
          )
        )
      );
    }
    return rows;
  };

  return (
    <section className="content">
      <h1 className="page-heading">
        Discipline Management
        <small>Incident reports and actions</small>
      </h1>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="panel">
        <PanelHeader
          title="Incident List"
          subtitle="incidents"
          count={count}
          action={
            <button
              type="button"
              className="primary-button"
              onClick={openCreate}
            >
              <Plus size={15} />
              Add Incident
            </button>
          }
        />

        <StateArea loading={loading} error={error} onRetry={load}>
          {incidents.length === 0 ? (
            <EmptyState
              icon={AlertTriangle}
              title="No incidents found"
              message="Add an incident to track discipline records."
            />
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>TITLE</th>
                    <th>STUDENT</th>
                    <th>SEVERITY</th>
                    <th>STATUS</th>
                    <th>CREATED</th>
                    <th style={{ width: 140 }}>Actions</th>
                  </tr>
                </thead>
                <tbody>{buildTableRows()}</tbody>
              </table>
            </div>
          )}
        </StateArea>
      </div>

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
                  {editing ? "Edit Incident" : "Add Incident"}
                </h3>
                <p>
                  {editing
                    ? "Update the discipline incident."
                    : "Record a new discipline incident."}
                </p>
              </div>

              <button
                className="modal-close"
                onClick={closeForm}
                disabled={saving}
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSubmit} noValidate>
              <div className="form-section">
                <h4>Incident Details</h4>

                <div className="form-grid">
                  <label>
                    Student
                    <select
                      name="student"
                      value={form.student}
                      onChange={handleChange}
                      required
                    >
                      <option value="">
                        Select student
                      </option>

                      {students.map((student) => (
                        <option
                          key={student.id}
                          value={student.id}
                        >
                          {student.full_name ||
                            student.admission_number}
                        </option>
                      ))}
                    </select>
                    {validationErrors.student && <span role="alert" className="field-error">{validationErrors.student}</span>}
                  </label>

                  <label>
                    Campus
                    <select
                      name="campus"
                      value={form.campus}
                      onChange={handleChange}
                      required
                    >
                      <option value="">
                        Select campus
                      </option>

                      {campuses.map((campus) => (
                        <option
                          key={campus.id}
                          value={campus.id}
                        >
                          {campus.name}
                        </option>
                      ))}
                    </select>
                    {validationErrors.campus && <span role="alert" className="field-error">{validationErrors.campus}</span>}
                  </label>

                  <label className="form-span">
                    Title
                    <input
                      name="title"
                      value={form.title}
                      onChange={handleChange}
                      placeholder="e.g. Classroom disruption"
                      required
                      maxLength={200}
                    />
                    {validationErrors.title && <span role="alert" className="field-error">{validationErrors.title}</span>}
                  </label>

                  <label className="form-span">
                    Description
                    <textarea
                      name="description"
                      value={form.description}
                      onChange={handleChange}
                      placeholder="What happened?"
                      rows="3"
                      required
                    />
                    {validationErrors.description && <span role="alert" className="field-error">{validationErrors.description}</span>}
                  </label>

                  <label>
                    Location
                    <input
                      name="location"
                      value={form.location}
                      onChange={handleChange}
                      placeholder="e.g. Science Lab"
                      maxLength={200}
                    />
                    {validationErrors.location && <span role="alert" className="field-error">{validationErrors.location}</span>}
                  </label>

                  <label>
                    Incident Date
                    <input
                      type="date"
                      name="incident_date"
                      value={form.incident_date}
                      onChange={handleChange}
                      required
                    />
                    {validationErrors.incident_date && <span role="alert" className="field-error">{validationErrors.incident_date}</span>}
                  </label>

                  <label>
                    Severity
                    <select
                      name="severity"
                      value={form.severity}
                      onChange={handleChange}
                    >
                      {SEVERITIES.map((item) => (
                        <option
                          key={item.value}
                          value={item.value}
                        >
                          {item.label}
                        </option>
                      ))}
                    </select>
                    {validationErrors.severity && <span role="alert" className="field-error">{validationErrors.severity}</span>}
                  </label>

                  <label>
                    Status
                    <select
                      name="status"
                      value={form.status}
                      onChange={handleChange}
                    >
                      {STATUSES.map((item) => (
                        <option
                          key={item.value}
                          value={item.value}
                        >
                          {item.label}
                        </option>
                      ))}
                    </select>
                    {validationErrors.status && <span role="alert" className="field-error">{validationErrors.status}</span>}
                  </label>
                </div>
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
                  <Plus size={17} />
                  {saving
                    ? editing
                      ? "Saving..."
                      : "Creating..."
                    : editing
                      ? "Save Changes"
                      : "Create Incident"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}

function toDateInput(value) {
  if (!value) return "";
  return String(value).slice(0, 10);
}
