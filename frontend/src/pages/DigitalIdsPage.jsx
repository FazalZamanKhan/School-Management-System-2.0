import { useEffect, useState } from "react";
import { Plus, X, CreditCard, ShieldX } from "lucide-react";
import { PageHeader, PanelHeader, StateArea, EmptyState, StatusBadge } from "./ui";
import { apiFetch, authHeaders } from "../api";

const API_URL = "/api/digital-ids/cards/";

const HOLDER_TYPES = [
  { value: "student", label: "Student", endpoint: "/api/students/" },
  { value: "teacher", label: "Teacher", endpoint: "/api/teachers/" },
  { value: "staff", label: "Staff", endpoint: "/api/staff/" },
];

const CARD_STATUS_LABELS = {
  active: "Active",
  revoked: "Revoked",
  expired: "Expired",
};

function holderLabel(holder, type) {
  if (!holder) return "";
  const parts = [holder.first_name, holder.last_name || ""];
  if (type === "student") parts.push(holder.admission_number || "");
  else parts.push(holder.employee_number || "");
  return parts.filter(Boolean).join(" ");
}

export default function DigitalIdsPage() {
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [holderType, setHolderType] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [pickType, setPickType] = useState("student");
  const [holders, setHolders] = useState([]);
  const [holdersLoading, setHoldersLoading] = useState(false);
  const [holderSearch, setHolderSearch] = useState("");
  const [selectedHolder, setSelectedHolder] = useState("");

  const loadCards = (params = new URLSearchParams()) => {
    setLoading(true);
    setError("");

    return fetch(`${API_URL}?${params.toString()}`, { credentials: "include" })
      .then((response) => {
        if (!response.ok) throw new Error("Failed to load ID cards.");
        return response.json();
      })
      .then((data) => setCards(Array.isArray(data) ? data : []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  const loadHolders = (type) => {
    const slug = HOLDER_TYPES.find((item) => item.value === type);
    if (!slug) return;
    setPickType(type);
    setHoldersLoading(true);
    setHolders([]);
    setHolderSearch("");
    setSelectedHolder("");

    fetch(`${slug.endpoint}?limit=100`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        const list = Array.isArray(data)
          ? data
          : Array.isArray(data?.results)
            ? data.results
            : [];
        setHolders(list);
      })
      .catch(() => setHolders([]))
      .finally(() => setHoldersLoading(false));
  };

  useEffect(() => {
    loadCards();
    loadHolders("student");
  }, []);

  const applyFilters = (evt) => {
    evt.preventDefault();
    const params = new URLSearchParams();
    if (holderType) params.set("holder_type", holderType);
    if (status) params.set("status", status);
    if (query) params.set("q", query);
    loadCards(params);
  };

  const clearFilters = () => {
    setHolderType("");
    setStatus("");
    setQuery("");
    loadCards();
  };

  const filteredHolders = holders.filter((holder) => {
    if (!holderSearch) return true;
    return holderLabel(holder, pickType).toLowerCase().includes(holderSearch.toLowerCase());
  });

  const issueCard = (event) => {
    event.preventDefault();
    if (!selectedHolder) {
      setFormError("Please choose a card holder.");
      return;
    }
    setSaving(true);
    setFormError("");

    const payload = { holder_type: pickType };
    payload[pickType] = Number(selectedHolder);

    apiFetch(API_URL, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    })
      .then(() => {
        setShowForm(false);
        setSelectedHolder("");
        loadCards();
      })
      .catch((err) => {
        setFormError(err.detail || err.message || "Failed to issue card.");
      })
      .finally(() => setSaving(false));
  };

  const revokeCard = (card) => {
    apiFetch(`${API_URL}${card.id}/revoke/`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: "{}",
    })
      .then(() => loadCards())
      .catch((err) => setError(err.message));
  };

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Security / Digital IDs"
        title="Digital ID Cards"
        subtitle="Issue and revoke digital ID cards for students, teachers and staff."
        action={
          <button className="primary-button" onClick={() => { setShowForm(true); loadHolders("student"); }}>
            <Plus size={15} />
            Issue Card
          </button>
        }
      />

      {error && (
        <div className="state-card error">
          <strong>Unable to load ID cards.</strong>
          <span>{error}</span>
          <button className="secondary-button" onClick={() => loadCards()}>
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
                placeholder="Search card number, barcode or holder..."
              />
            </div>
            <select value={holderType} onChange={(e) => setHolderType(e.target.value)}>
              <option value="">All holder types</option>
              {HOLDER_TYPES.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="revoked">Revoked</option>
            </select>
            <button type="submit" className="secondary-button">Filter</button>
            <button type="button" className="secondary-button" onClick={clearFilters}>
              Clear
            </button>
          </div>
        </form>

        <PanelHeader title="Issued Cards" subtitle="cards" count={cards.length} />

        <StateArea loading={loading} error={error}>
          {cards.length === 0 ? (
            <EmptyState
              icon={CreditCard}
              title="No ID cards issued"
              message="Issue a digital ID card to a student, teacher or staff member."
            />
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Card Number</th>
                    <th>Holder</th>
                    <th>Type</th>
                    <th>Campus</th>
                    <th>Issued</th>
                    <th>Expiry</th>
                    <th>Status</th>
                    <th className="table-action"></th>
                  </tr>
                </thead>
                <tbody>
                  {cards.map((card) => {
                    const holder = card.student_name || card.teacher_name || card.staff_name || "—";
                    return (
                      <tr key={card.id}>
                        <td className="student-name-cell">
                          <strong>{card.card_number}</strong>
                          <span className="table-sub">{card.barcode_data}</span>
                        </td>
                        <td>{holder}</td>
                        <td>{card.holder_type}</td>
                        <td>{card.campus_name || "—"}</td>
                        <td>{card.issue_date ? new Date(card.issue_date).toLocaleDateString() : "—"}</td>
                        <td>{card.expiry_date ? new Date(card.expiry_date).toLocaleDateString() : "—"}</td>
                        <td>
                          <StatusBadge
                            status={card.status === "active" ? "active" : "inactive"}
                            label={CARD_STATUS_LABELS[card.status] || card.status}
                          />
                        </td>
                        <td className="table-action">
                          {card.status === "active" && (
                            <button className="secondary-button" onClick={() => revokeCard(card)}>
                              <ShieldX size={14} />
                              Revoke
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
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
                <h3>Issue Digital ID</h3>
                <p>A new card number and barcode are generated automatically.</p>
              </div>
              <button className="modal-close" onClick={() => setShowForm(false)} disabled={saving}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={issueCard}>
              <div className="form-section">
                <div className="form-grid">
                  <label className="form-span">
                    Card Holder Type
                    <select
                      value={pickType}
                      onChange={(e) => loadHolders(e.target.value)}
                      disabled={saving}
                    >
                      {HOLDER_TYPES.map((item) => (
                        <option key={item.value} value={item.value}>{item.label}</option>
                      ))}
                    </select>
                  </label>

                  <label className="form-span">
                    Search {pickType === "student" ? "student" : pickType === "teacher" ? "teacher" : "staff member"}
                    <input
                      value={holderSearch}
                      onChange={(e) => setHolderSearch(e.target.value)}
                      placeholder={`Type to filter by name or ${pickType === "student" ? "admission" : "employee"} number...`}
                    />
                  </label>

                  <label className="form-span">
                    Person
                    <select
                      value={selectedHolder}
                      onChange={(e) => setSelectedHolder(e.target.value)}
                      disabled={saving || holdersLoading}
                    >
                      <option value="">
                        {holdersLoading ? "Loading people..." : "Select a person"}
                      </option>
                      {filteredHolders.map((holder) => (
                        <option key={holder.id} value={holder.id}>
                          {holderLabel(holder, pickType)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                {formError && <div className="state-card error"><span>{formError}</span></div>}
              </div>

              <div className="modal-footer">
                <button type="button" className="secondary-button" onClick={() => setShowForm(false)} disabled={saving}>
                  Cancel
                </button>
                <button type="submit" className="primary-button" disabled={saving || !selectedHolder}>
                  <CreditCard size={16} />
                  {saving ? "Issuing..." : "Issue Card"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
