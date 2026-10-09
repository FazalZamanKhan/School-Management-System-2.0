import { useCallback, useEffect, useState } from "react";
import { FileText, Upload, Download, Search, Filter, X } from "lucide-react";
import { useAuth } from "../auth";
import { apiFetch } from "../api";
import { PageHeader, PanelHeader, StateArea, StatusBadge, EmptyState } from "./ui";
import { formatDate } from "./format";

const DOCUMENTS_URL = "/api/documents/";
const DOCUMENTS_UPLOAD_URL = "/api/documents/upload/";
const STUDENTS_API = "/api/students/";
const EMPLOYEES_API = "/api/hr/employees/";
const CAMPUSES_URL = "/api/schools/campuses/";

const STUDENT_DOC_TYPES = [
  ["birth_certificate", "Birth Certificate"],
  ["b_form", "B-Form / CNIC"],
  ["report_card", "Report Card"],
  ["transfer_certificate", "Transfer Certificate"],
  ["fee_challan", "Fee Challan"],
  ["medical", "Medical Record"],
  ["other", "Other"],
];

const EMPLOYEE_DOC_TYPES = [
  ["CNIC", "CNIC"],
  ["degree", "Degree"],
  ["experience_letter", "Experience Letter"],
  ["offer_letter", "Offer Letter"],
  ["contract", "Contract"],
  ["other", "Other"],
];

function UploadDocumentModal({ onClose, onDone }) {
  const [entityType, setEntityType] = useState("student");
  const [entityId, setEntityId] = useState("");
  const [entitySearch, setEntitySearch] = useState("");
  const [entities, setEntities] = useState([]);
  const [loadingEntities, setLoadingEntities] = useState(false);
  const [documentType, setDocumentType] = useState("other");
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [file, setFile] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const fetchEntities = useCallback(async () => {
    setLoadingEntities(true);
    try {
      const url = entityType === "student" ? STUDENTS_API : EMPLOYEES_API;
      const params = entitySearch ? `?search=${encodeURIComponent(entitySearch)}` : "";
      const data = await apiFetch(`${url}${params}`, {}, "Failed to load.");
      const rows = Array.isArray(data) ? data : data.results || [];
      setEntities(rows);
    } catch {
      setEntities([]);
    } finally {
      setLoadingEntities(false);
    }
  }, [entityType, entitySearch]);

  useEffect(() => {
    const timer = setTimeout(fetchEntities, 300);
    return () => clearTimeout(timer);
  }, [fetchEntities]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!file) { setError("Please select a file."); return; }
    if (!entityId) { setError("Please select a student or employee."); return; }

    setSaving(true);
    setError("");

    const formData = new FormData();
    formData.append("entity_type", entityType);
    formData.append("entity_id", entityId);
    formData.append("document_type", documentType);
    formData.append("title", title || file.name);
    formData.append("notes", notes);
    formData.append("file", file);
    if (entityType === "employee" && expiryDate) {
      formData.append("expiry_date", expiryDate);
    }

    try {
      const csrfToken = document.cookie.split("; ")
        .find((c) => c.startsWith("csrftoken="))
        ?.split("=")[1] || "";

      const response = await fetch(DOCUMENTS_UPLOAD_URL, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        credentials: "include",
        body: formData,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        const msg = errData.detail || errData.file || (typeof errData === "object" && Object.values(errData)[0]) || "Upload failed.";
        throw new Error(Array.isArray(msg) ? msg[0] : String(msg));
      }

      onDone();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const docTypes = entityType === "student" ? STUDENT_DOC_TYPES : EMPLOYEE_DOC_TYPES;

  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="teacher-modal">
        <div className="modal-header">
          <div>
            <h3>Upload Document</h3>
            <p>Attach a document to a student or employee record.</p>
          </div>
          <button className="modal-close" onClick={onClose} disabled={saving}><X size={18} /></button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-section">
            <div className="form-grid">
              <label>
                Entity Type *
                <select value={entityType} onChange={(e) => { setEntityType(e.target.value); setEntityId(""); setEntities([]); }}>
                  <option value="student">Student</option>
                  <option value="employee">Employee</option>
                </select>
              </label>

              <label>
                Search {entityType === "student" ? "Student" : "Employee"} *
                <input
                  value={entitySearch}
                  onChange={(e) => setEntitySearch(e.target.value)}
                  placeholder="Search by name or ID..."
                />
              </label>

              <label>
                Select {entityType === "student" ? "Student" : "Employee"} *
                <select value={entityId} onChange={(e) => setEntityId(e.target.value)} required>
                  <option value="">
                    {loadingEntities ? "Loading..." : `Select ${entityType}`}
                  </option>
                  {entities.map((ent) => {
                    const label = entityType === "student"
                      ? `${ent.first_name} ${ent.last_name} (${ent.admission_number})`
                      : `${ent.first_name} ${ent.last_name} (${ent.employee_number})`;
                    return <option key={ent.id} value={ent.id}>{label}</option>;
                  })}
                </select>
              </label>

              <label>
                Document Type *
                <select value={documentType} onChange={(e) => setDocumentType(e.target.value)}>
                  {docTypes.map(([val, label]) => (
                    <option key={val} value={val}>{label}</option>
                  ))}
                </select>
              </label>

              <label>
                Title
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Document title (defaults to filename)"
                />
              </label>

              {entityType === "employee" && (
                <label>
                  Expiry Date
                  <input type="date" value={expiryDate} onChange={(e) => setExpiryDate(e.target.value)} />
                </label>
              )}

              <label>
                Notes
                <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional notes" />
              </label>

              <label>
                File *
                <input
                  type="file"
                  onChange={(e) => setFile(e.target.files[0])}
                  accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.gif"
                  required
                />
              </label>
            </div>
          </div>

          {error && <div className="state-card error"><strong>{error}</strong></div>}

          <div className="modal-footer">
            <button type="button" className="secondary-button" onClick={onClose} disabled={saving}>Cancel</button>
            <button type="submit" className="primary-button" disabled={saving || !file}>
              <Upload size={15} />
              {saving ? "Uploading..." : "Upload Document"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function DocumentsPage() {
  const { hasRole } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [entityType, setEntityType] = useState("");
  const [documentType, setDocumentType] = useState("");
  const [campus, setCampus] = useState("");
  const [campuses, setCampuses] = useState([]);

  const [showUpload, setShowUpload] = useState(false);

  const canManage = hasRole(["super_admin", "admin", "accountant"]);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (entityType) params.set("entity_type", entityType);
      if (documentType) params.set("document_type", documentType);
      if (campus) params.set("campus", campus);

      const data = await apiFetch(`${DOCUMENTS_URL}?${params}`, {}, "Failed to load documents.");
      setDocuments(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [search, entityType, documentType, campus]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  useEffect(() => {
    fetch(CAMPUSES_URL, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setCampuses(Array.isArray(d) ? d : d.results || []))
      .catch(() => {});
  }, []);

  const studentDocs = documents.filter((d) => d.entity_type === "student");
  const employeeDocs = documents.filter((d) => d.entity_type === "employee");
  const expiringSoon = documents.filter((d) => {
    if (!d.expiry_date) return false;
    const diff = (new Date(d.expiry_date) - new Date()) / (1000 * 60 * 60 * 24);
    return diff <= 30 && diff >= 0;
  });

  const clearFilters = () => {
    setSearch("");
    setEntityType("");
    setDocumentType("");
    setCampus("");
  };

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Documents"
        title="Document Management"
        subtitle="Upload, view and manage all documents in one place."
        action={
          canManage && (
            <button className="primary-button" onClick={() => setShowUpload(true)}>
              <Upload size={15} /> Upload Document
            </button>
          )
        }
      />

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon"><FileText size={21} /></div>
          <div>
            <h3>{documents.length}</h3>
            <p>Total Documents</p>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon"><FileText size={21} /></div>
          <div>
            <h3>{studentDocs.length}</h3>
            <p>Student Documents</p>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon"><FileText size={21} /></div>
          <div>
            <h3>{employeeDocs.length}</h3>
            <p>Employee Documents</p>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon" style={{ color: expiringSoon.length > 0 ? "var(--danger)" : undefined }}>
            <FileText size={21} />
          </div>
          <div>
            <h3 style={{ color: expiringSoon.length > 0 ? "var(--danger)" : undefined }}>{expiringSoon.length}</h3>
            <p>Expiring Soon</p>
          </div>
        </div>
      </div>

      <div className="panel">
        <PanelHeader
          title="All Documents"
          subtitle="documents found"
          count={documents.length}
        />

        <div className="filters">
          <div className="filter-group">
            <div className="filter-item" style={{ position: "relative", flex: 2 }}>
              <Search size={15} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", opacity: 0.5 }} />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by title, name or ID..."
                style={{ paddingLeft: 32 }}
              />
            </div>
            <div className="filter-item">
              <select value={entityType} onChange={(e) => setEntityType(e.target.value)}>
                <option value="">All Types</option>
                <option value="student">Students</option>
                <option value="employee">Employees</option>
              </select>
            </div>
            <div className="filter-item">
              <select value={documentType} onChange={(e) => setDocumentType(e.target.value)}>
                <option value="">All Document Types</option>
                <optgroup label="Student">
                  {STUDENT_DOC_TYPES.map(([val, label]) => (
                    <option key={val} value={val}>{label}</option>
                  ))}
                </optgroup>
                <optgroup label="Employee">
                  {EMPLOYEE_DOC_TYPES.map(([val, label]) => (
                    <option key={val} value={val}>{label}</option>
                  ))}
                </optgroup>
              </select>
            </div>
            <div className="filter-item">
              <select value={campus} onChange={(e) => setCampus(e.target.value)}>
                <option value="">All Campuses</option>
                {campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <button className="secondary-button" onClick={clearFilters}>
              <Filter size={14} /> Clear
            </button>
          </div>
        </div>

        <StateArea loading={loading} error={error} onRetry={fetchDocuments}>
          {documents.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No documents found"
              message="No documents match your current filters."
            />
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>TITLE</th>
                    <th>TYPE</th>
                    <th>ENTITY</th>
                    <th>ENTITY TYPE</th>
                    <th>UPLOADED BY</th>
                    <th>DATE</th>
                    <th>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr key={`${doc.entity_type}-${doc.id}`}>
                      <td><strong>{doc.title}</strong></td>
                      <td><StatusBadge status={doc.document_type} /></td>
                      <td>{doc.entity_label}</td>
                      <td>
                        <StatusBadge status={doc.entity_type} />
                      </td>
                      <td>{doc.uploaded_by_name || "-"}</td>
                      <td>{formatDate(doc.created_at)}</td>
                      <td>
                        {doc.file_url && (
                          <a
                            className="table-action"
                            href={doc.file_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <Download size={15} /> View
                          </a>
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

      {showUpload && (
        <UploadDocumentModal
          onClose={() => setShowUpload(false)}
          onDone={fetchDocuments}
        />
      )}
    </section>
  );
}
