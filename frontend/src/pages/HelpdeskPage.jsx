import { useEffect, useState } from "react";
import { LifeBuoy, Pencil, Plus, X, Send, CheckCircle2, RotateCcw } from "lucide-react";
import { useAuth } from "../auth";
import { PageHeader, PanelHeader, StateArea, EmptyState, StatusBadge } from "./ui";
import { apiFetch, jsonHeaders, authHeaders } from "../api";

const API_URL = "/api/helpdesk/tickets/";

const PRIORITIES = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
];

const STATUSES = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In Progress" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

const STATUS_LABELS = {
  open: "Open",
  in_progress: "In Progress",
  resolved: "Resolved",
  closed: "Closed",
};

function statusToneValue(status) {
  if (status === "resolved" || status === "closed") return "active";
  if (status === "in_progress") return "warn";
  return "info";
}

function priorityToneValue(priority) {
  if (priority === "high" || priority === "urgent") return "warn";
  return "info";
}

const EMPTY_FORM = {
  campus: "",
  category: "",
  subject: "",
  description: "",
  priority: "medium",
  assignee: "",
};



export default function HelpdeskPage() {
  const { hasRole } = useAuth();

  const [tickets, setTickets] = useState([]);
  const [categories, setCategories] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [staffMembers, setStaffMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [query, setQuery] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [editingTicket, setEditingTicket] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState("");

  const [active, setActive] = useState(null);
  const [activeLoading, setActiveLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [showInternal, setShowInternal] = useState(false);

  const canManage = hasRole([
    "super_admin", "admin", "principal", "vice_principal", "campus_admin",
    "academic", "hr", "receptionist", "guard", "teacher", "staff",
  ]);

  const loadTickets = (params = new URLSearchParams()) => {
    setLoading(true);
    setError("");

    return fetch(`${API_URL}?${params.toString()}`, { credentials: "include" })
      .then((response) => {
        if (!response.ok) throw new Error("Failed to load tickets.");
        return response.json();
      })
      .then((data) => setTickets(Array.isArray(data) ? data : []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadTickets();

    fetch("/api/helpdesk/categories/", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setCategories(Array.isArray(data) ? data : []))
      .catch(() => {});

    fetch("/api/schools/campuses/", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setCampuses(Array.isArray(data) ? data : []))
      .catch(() => {});

    fetch("/api/staff/?page_size=500", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setStaffMembers(Array.isArray(data) ? data : data.results || []))
      .catch(() => {});
  }, []);

  const applyFilters = (evt) => {
    evt.preventDefault();
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (priority) params.set("priority", priority);
    if (query) params.set("search", query);
    loadTickets(params);
  };

  const clearFilters = () => {
    setStatus("");
    setPriority("");
    setQuery("");
    loadTickets();
  };

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((previous) => ({ ...previous, [name]: value }));
  };

  const openEditTicket = (ticket) => {
    setEditingTicket(ticket);
    setFormError("");
    setForm({
      campus: ticket.campus ? String(ticket.campus) : "",
      category: ticket.category ? String(ticket.category) : "",
      subject: ticket.subject || "",
      description: ticket.description || "",
      priority: ticket.priority || "medium",
      assignee: ticket.assignee ? String(ticket.assignee) : "",
    });
    setShowForm(true);
  };

  const createTicket = (event) => {
    event.preventDefault();
    if (!form.description || !form.description.trim()) {
      setFormError("Please enter a description for the ticket.");
      return;
    }
    setSaving(true);
    setFormError("");

    const payload = {
      subject: form.subject,
      description: form.description.trim(),
      priority: form.priority,
    };
    if (form.category) payload.category = Number(form.category);
    if (form.campus) payload.campus = Number(form.campus);
    payload.assignee = form.assignee ? Number(form.assignee) : null;

    apiFetch(editingTicket ? `${API_URL}${editingTicket.id}/` : API_URL, {
      method: editingTicket ? "PATCH" : "POST",
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    })
      .then(() => {
        setShowForm(false);
        setEditingTicket(null);
        setForm(EMPTY_FORM);
        loadTickets();
      })
      .catch((err) => setFormError(err.message))
      .finally(() => setSaving(false));
  };

  const openTicket = (ticket) => {
    setActiveLoading(true);
    setActive(null);

    fetch(`${API_URL}${ticket.id}/`, { credentials: "include" })
      .then((response) => {
        if (!response.ok) throw new Error("Failed to load ticket.");
        return response.json();
      })
      .then(setActive)
      .catch(() => {})
      .finally(() => setActiveLoading(false));
  };

  const refreshTicket = () => {
    if (!active) return;
    fetch(`${API_URL}${active.id}/`, { credentials: "include" })
      .then((response) => {
        if (!response.ok) throw new Error("Failed to load ticket.");
        return response.json();
      })
      .then(setActive);
  };

  const sendMessage = (event) => {
    event.preventDefault();
    if (!message.trim() || !active) return;

    apiFetch(`${API_URL}${active.id}/messages/`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        body: message,
        is_internal: showInternal,
      }),
    })
      .then(() => {
        setMessage("");
        refreshTicket();
        loadTickets();
      })
      .catch(() => {});
  };

  const resolveTicket = () => {
    if (!active) return;
    const notes = window.prompt("Resolution notes:", "");
    if (notes === null) return;

    apiFetch(`${API_URL}${active.id}/resolve/`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ resolution_notes: notes }),
    })
      .then(() => {
        refreshTicket();
        loadTickets();
      })
      .catch(() => {});
  };

  const reopenTicket = () => {
    if (!active) return;
    apiFetch(`${API_URL}${active.id}/reopen/`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: "{}",
    })
      .then(() => {
        refreshTicket();
        loadTickets();
      })
      .catch(() => {});
  };

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Helpdesk"
        title="Helpdesk"
        subtitle="Support tickets, complaints and their resolution desk."
        action={
          canManage && (
            <button className="primary-button" onClick={() => { setEditingTicket(null); setShowForm(true); }}>
              <Plus size={15} />
              New Ticket
            </button>
          )
        }
      />

      {error && (
        <div className="state-card error">
          <strong>Unable to load tickets.</strong>
          <span>{error}</span>
          <button className="secondary-button" onClick={() => loadTickets()}>
            Try Again
          </button>
        </div>
      )}

      <div className="panel">
        <form onSubmit={applyFilters}>
          <div className="filter-row">
            <div className="filter-search">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search subject or description..."
              />
            </div>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              {STATUSES.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
            <select value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="">All priorities</option>
              {PRIORITIES.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
            <button type="submit" className="secondary-button">Filter</button>
            <button type="button" className="secondary-button" onClick={clearFilters}>
              Clear
            </button>
          </div>
        </form>

        <PanelHeader title="Ticket Desk" subtitle="tickets" count={tickets.length} />

        <StateArea loading={loading} error={error}>
          {tickets.length === 0 ? (
            <EmptyState
              icon={LifeBuoy}
              title="No tickets found"
              message="No support tickets match the current filters."
            />
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Ticket</th>
                    <th>Category</th>
                    <th>Campus</th>
                    <th>Priority</th>
                    <th>Status</th>
                    <th>Assignee</th>
                    <th>Updated</th>
                    {canManage && <th>Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {tickets.map((ticket) => (
                    <tr key={ticket.id}>
                      <td>
                        <button type="button" className="table-link" onClick={() => openTicket(ticket)}>
                          <strong>{ticket.subject}</strong>
                        </button>
                        <span className="table-sub">{ticket.created_by_name}</span>
                      </td>
                      <td>{ticket.category_name || "—"}</td>
                      <td>{ticket.campus_name || "School-wide"}</td>
                      <td>
                        <StatusBadge status={priorityToneValue(ticket.priority)} label={ticket.priority} />
                      </td>
                      <td>
                        <StatusBadge status={statusToneValue(ticket.status)} label={STATUS_LABELS[ticket.status] || ticket.status} />
                      </td>
                      <td>{ticket.assignee_name || "Unassigned"}</td>
                      <td>{new Date(ticket.updated_at).toLocaleDateString()}</td>
                      {canManage && (
                        <td style={{ whiteSpace: "nowrap" }}>
                          <button type="button" className="table-action" onClick={() => openEditTicket(ticket)}>
                            <Pencil size={13} /> Edit
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </StateArea>
      </div>

      {showForm && (
        <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) { setShowForm(false); setEditingTicket(null); } }}>
          <div className="teacher-modal">
            <div className="modal-header">
              <div>
                <h3>{editingTicket ? "Edit Ticket" : "New Ticket"}</h3>
                <p>{editingTicket ? "Update the details of this ticket." : "Raise a support ticket for the helpdesk."}</p>
              </div>
              <button className="modal-close" onClick={() => { setShowForm(false); setEditingTicket(null); }} disabled={saving}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={createTicket}>
              <div className="form-section">
                <div className="form-grid">
                  <label className="form-span">
                    Subject
                    <input name="subject" value={form.subject} onChange={handleChange} placeholder="Brief summary" required />
                  </label>

                  <label className="form-span">
                    Description *
                    <textarea name="description" value={form.description} onChange={handleChange} rows="4" placeholder="What needs attention?" required />
                  </label>

                  <label>
                    Category
                    <select name="category" value={form.category} onChange={handleChange}>
                      <option value="">General</option>
                      {categories.map((item) => (
                        <option key={item.id} value={item.id}>{item.name}</option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Campus
                    <select name="campus" value={form.campus} onChange={handleChange}>
                      <option value="">My campus</option>
                      {campuses.map((item) => (
                        <option key={item.id} value={item.id}>{item.name}</option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Priority
                    <select name="priority" value={form.priority} onChange={handleChange}>
                      {PRIORITIES.map((item) => (
                        <option key={item.value} value={item.value}>{item.label}</option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Assignee
                    <select name="assignee" value={form.assignee} onChange={handleChange}>
                      <option value="">Unassigned</option>
                      {staffMembers.map((staff) => (
                        <option key={staff.id} value={staff.user || staff.user_id || staff.id}>
                          {staff.full_name || `${staff.first_name} ${staff.last_name}`.trim()} ({staff.designation || "Staff"})
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                {formError && <div className="state-card error"><span>{formError}</span></div>}
              </div>

              <div className="modal-footer">
                <button type="button" className="secondary-button" onClick={() => { setShowForm(false); setEditingTicket(null); }} disabled={saving}>
                  Cancel
                </button>
                <button type="submit" className="primary-button" disabled={saving}>
                  {saving ? "Saving..." : editingTicket ? "Save Changes" : "Create Ticket"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {(active || activeLoading) && (
        <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) setActive(null); }}>
          <div className="teacher-modal ticket-modal">
            <div className="modal-header">
              <div>
                <h3>{active ? active.subject : "Ticket"}</h3>
                <p>
                  {active
                    ? `${STATUS_LABELS[active.status] || active.status} · ${active.category_name || "General"} · ${active.campus_name || "School-wide"}`
                    : "Loading..."}
                </p>
              </div>
              <button className="modal-close" onClick={() => setActive(null)}>
                <X size={18} />
              </button>
            </div>

            {active && (
              <>
                <div className="form-section ticket-meta">
                  <p>{active.description || "No description provided."}</p>
                  <p className="ticket-meta-line">
                    Priority: {active.priority} · Reporter: {active.created_by_name} · Assignee: {active.assignee_name || "Unassigned"}
                  </p>
                  {canManage && (
                    <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8 }}>
                      <label style={{ margin: 0, fontWeight: 600, fontSize: "0.85rem" }}>Assign Staff:</label>
                      <select
                        style={{ maxWidth: 260, fontSize: "0.85rem", padding: "4px 8px" }}
                        value={active.assignee ? String(active.assignee) : ""}
                        onChange={(e) => {
                          const newAssignee = e.target.value ? Number(e.target.value) : null;
                          apiFetch(`${API_URL}${active.id}/`, {
                            method: "PATCH",
                            headers: jsonHeaders(),
                            body: JSON.stringify({ assignee: newAssignee }),
                          }).then(() => {
                            refreshTicket();
                            loadTickets();
                          });
                        }}
                      >
                        <option value="">Unassigned</option>
                        {staffMembers.map((s) => (
                          <option key={s.id} value={s.user || s.user_id || s.id}>
                            {s.full_name || `${s.first_name} ${s.last_name}`.trim()} ({s.designation || "Staff"})
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                  {active.resolution_notes && (
                    <p className="ticket-meta-line"><strong>Resolution:</strong> {active.resolution_notes}</p>
                  )}
                </div>

                <div className="form-section ticket-thread">
                  <h4>Conversation</h4>
                  {(active.messages || []).length === 0 ? (
                    <p className="ticket-meta-line">No messages yet.</p>
                  ) : (
                    active.messages.map((msg) => (
                      <div key={msg.id} className={`ticket-message${msg.is_internal ? " internal" : ""}`}>
                        <div className="ticket-message-head">
                          <strong>{msg.author_name}</strong>
                          <span>{new Date(msg.created_at).toLocaleString()}</span>
                          {msg.is_internal && <StatusBadge status="internal" label="Internal" />}
                        </div>
                        <p>{msg.body}</p>
                      </div>
                    ))
                  )}
                </div>

                <form onSubmit={sendMessage} className="form-section">
                  <textarea
                    rows="3"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder="Write a reply..."
                  />
                  <label className="checkbox-label inline">
                    <input
                      type="checkbox"
                      checked={showInternal}
                      onChange={(e) => setShowInternal(e.target.checked)}
                    />
                    Internal note (staff only)
                  </label>
                  <div className="modal-footer">
                    <button className="secondary-button" type="submit">
                      <Send size={16} />
                      Send
                    </button>
                    {active.status === "resolved" || active.status === "closed" ? (
                      <button type="button" className="secondary-button" onClick={reopenTicket}>
                        <RotateCcw size={16} />
                        Reopen
                      </button>
                    ) : (
                      <button type="button" className="primary-button" onClick={resolveTicket}>
                        <CheckCircle2 size={16} />
                        Resolve
                      </button>
                    )}
                  </div>
                </form>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}