import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Search,
  Wallet,
  Receipt,
  FileDown,
  PlusCircle,
  Plus,
} from "lucide-react";
import { useApiList } from "./useApiList";
import {
  PageHeader,
  PanelHeader,
  StateArea,
  EmptyState,
  Pagination,
  StatusBadge,
  SkeletonBlock,
} from "./ui";
import { formatCurrency, formatDate } from "./format";
import { useLang } from "../i18n";
import { apiFetch, jsonHeaders } from "../api";
import { Modal } from "../components/Modal";

const INVOICES_API_URL = "/api/finance/invoices/";
const PAYMENTS_API_URL = "/api/finance/payments/";
const CATEGORIES_API_URL = "/api/finance/categories/";
const FEE_STRUCTURES_API_URL = "/api/finance/fee-structures/";
const ACADEMIC_YEARS_API_URL = "/api/schools/academic-years/";
const CAMPUSES_API_URL = "/api/schools/campuses/";
const CLASSES_API_URL = "/api/schools/classes/";
const DASHBOARD_FINANCE_URL = "/api/dashboard/finance/";
const DASHBOARD_BREAKDOWN_URL = "/api/dashboard/finance/breakdown/";

const INVOICE_STATUSES = [
  ["draft", "Draft"],
  ["issued", "Issued"],
  ["partial", "Partially Paid"],
  ["paid", "Paid"],
  ["overdue", "Overdue"],
  ["cancelled", "Cancelled"],
];

const PAYMENT_METHODS = [
  ["cash", "Cash"],
  ["bank", "Bank Transfer"],
  ["jazzcash", "JazzCash"],
  ["easypaisa", "EasyPaisa"],
  ["card", "Card"],
  ["other", "Other"],
];

function buildParams(search, status, page) {
  const params = new URLSearchParams();

  params.append("page", page);

  if (search.trim()) {
    params.append("search", search.trim());
  }

  if (status) {
    params.append("status", status);
  }

  return params;
}

function Filters({ search, setSearch, status, setStatus, onSearch, onClear }) {
  return (
    <div className="panel students-filters">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSearch();
        }}
      >
        <div className="filter-row">
          <div className="filter-search">
            <Search size={18} />

            <input
              type="text"
              placeholder="Search by name, admission or number..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>

          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setTimeout(onSearch, 0);
            }}
          >
            <option value="">All statuses</option>

            {INVOICE_STATUSES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>

          <button type="submit" className="primary-button">
            Search
          </button>

          <button type="button" className="secondary-button" onClick={onClear}>
            Clear
          </button>
        </div>
      </form>
    </div>
  );
}

function DashboardCards({ data }) {
  if (!data) {
    return null;
  }

  const cards = [
    {
      label: "Total Billed",
      value: formatCurrency(data.total_billed),
      tone: "blue",
    },
    {
      label: "Payments Collected",
      value: formatCurrency(data.payments_collected),
      tone: "green",
    },
    {
      label: "Outstanding",
      value: formatCurrency(data.outstanding),
      tone: "red",
    },
    {
      label: "Invoices",
      value: data.invoices ?? 0,
      tone: "purple",
    },
  ];

  return (
    <div className="stats-grid">
      {cards.map((card) => (
        <div className="stat-card" key={card.label}>
          <div className="stat-icon">
            <Wallet size={21} />
          </div>

          <div className="stat-info">
            <span>{card.label}</span>
            <strong>{card.value}</strong>
          </div>
        </div>
      ))}
    </div>
  );
}

function BreakdownCharts({ data, error, onRetry }) {
  if (error) {
    return (
      <div className="state-card error">
        <strong>Finance breakdown unavailable</strong>
        <span>{error}</span>
        {onRetry && (
          <button type="button" className="secondary-button" onClick={onRetry}>
            Try Again
          </button>
        )}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="state-card">Loading finance breakdown...</div>
    );
  }

  const maxMonthly = Math.max(
    1,
    ...(data.monthly || []).map((item) => Number(item.total))
  );

  const maxCampus = Math.max(
    1,
    ...(data.by_campus || []).map((item) => Number(item.billed))
  );

  return (
    <div className="dashboard-grid">
      <div className="panel">
        <div className="panel-header">
          <div>
            <h3>Monthly Collections</h3>
            <p>Completed payments by month</p>
          </div>
        </div>

        {(data.monthly || []).length === 0 ? (
          <div className="state-card">No payments recorded yet.</div>
        ) : (
          <div className="bar-chart">
            {data.monthly.map((item) => (
              <div className="bar-column" key={item.month}>
                <span className="bar-value">
                  {formatCurrency(item.total)}
                </span>

                <div
                  className="bar"
                  style={{
                    height: `${Math.max(
                      6,
                      (Number(item.total) / maxMonthly) * 100
                    )}%`,
                  }}
                />

                <span className="bar-label">{item.month}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="panel">
        <div className="panel-header">
          <div>
            <h3>Collection by Campus</h3>
            <p>Billed versus collected</p>
          </div>
        </div>

        {(data.by_campus || []).length === 0 ? (
          <div className="state-card">No campus data available.</div>
        ) : (
          <div className="campus-breakdown">
            {data.by_campus.map((item) => (
              <div className="breakdown-row" key={item.campus}>
                <div className="breakdown-label">
                  <span>{item.campus}</span>

                  <strong>{formatCurrency(item.collected)}</strong>
                </div>

                <div className="progress-track">
                  <div
                    className="progress-fill"
                    style={{
                      width: `${Math.max(
                        2,
                        (Number(item.collected) / maxCampus) * 100
                      )}%`,
                    }}
                  />

                  <span className="progress-sub-fill" />

                  <span className="progress-track-label">
                    Billed {formatCurrency(item.billed)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function PaymentModal({ invoice, onClose, onSaved }) {
  const [amount, setAmount] = useState("");
  const [paymentDate, setPaymentDate] = useState(
    new Date().toISOString().slice(0, 10)
  );
  const [paymentMethod, setPaymentMethod] = useState("cash");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const balance = Number(invoice.balance || 0);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");

    try {
      const response = await fetch("/api/finance/payments/create/", {
        method: "POST",
        credentials: "include",
        headers: jsonHeaders(),
        body: JSON.stringify({
          invoice: invoice.id,
          amount: Number(amount),
          payment_date: paymentDate,
          payment_method: paymentMethod,
          reference: reference,
          notes: notes,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        let message = "Unable to record payment.";

        if (data && typeof data === "object") {
          const parts = Object.entries(data).map(([field, value]) => {
            const text = Array.isArray(value)
              ? value.join(", ")
              : String(value);

            return `${field}: ${text}`;
          });

          if (parts.length) {
            message = parts.join(" | ");
          }
        }

        throw new Error(message);
      }

      onSaved(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !saving) {
          onClose();
        }
      }}
    >
      <div className="teacher-modal">
        <div className="modal-header">
          <div>
            <h3>Record Payment</h3>
            <p>
              {invoice.invoice_number} · {invoice.student_name}
            </p>
          </div>

          <button
            className="modal-close"
            onClick={onClose}
            disabled={saving}
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-section">
            <h4>Payment Details</h4>

            <div className="form-grid">
              <label>
                Balance Due
                <input value={formatCurrency(invoice.balance)} disabled />
              </label>

              <label>
                Amount (Rs.)
                <input
                  type="number"
                  min="1"
                  max={balance}
                  step="0.01"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                  placeholder="0.00"
                  required
                />
              </label>

              <label>
                Payment Date
                <input
                  type="date"
                  value={paymentDate}
                  onChange={(event) => setPaymentDate(event.target.value)}
                  required
                />
              </label>

              <label>
                Payment Method
                <select
                  value={paymentMethod}
                  onChange={(event) => setPaymentMethod(event.target.value)}
                >
                  {PAYMENT_METHODS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Reference / Transaction ID
                <input
                  value={reference}
                  onChange={(event) => setReference(event.target.value)}
                  placeholder="Optional"
                />
              </label>

              <label>
                Notes
                <input
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  placeholder="Optional"
                />
              </label>
            </div>

            <p className="field-hint">
              Payments cannot exceed the remaining invoice balance
              ({formatCurrency(invoice.balance)}).
            </p>
          </div>

          {error && (
            <div className="state-card error">
              <strong>Unable to record payment.</strong>
              <span>{error}</span>
            </div>
          )}

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
              {saving ? "Recording..." : "Record Payment"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function FeeStructureModal({
  categories,
  academicYears,
  campuses,
  classes,
  onClose,
  onSaved,
}) {
  const [academicYear, setAcademicYear] = useState("");
  const [campus, setCampus] = useState("");
  const [classObj, setClassObj] = useState("");
  const [category, setCategory] = useState("");
  const [amount, setAmount] = useState("");
  const [dueDay, setDueDay] = useState("10");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const campusClasses = classes.filter(
    (item) => Number(item.campus) === Number(campus)
  );

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");

    try {
      const response = await fetch(FEE_STRUCTURES_API_URL, {
        method: "POST",
        credentials: "include",
        headers: jsonHeaders(),
        body: JSON.stringify({
          academic_year: academicYear,
          campus: campus,
          class_obj: classObj,
          category: category,
          amount: Number(amount),
          due_day: Number(dueDay),
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        let message = "Unable to add fee structure.";

        if (data && typeof data === "object") {
          const parts = Object.entries(data).map(([field, value]) => {
            const text = Array.isArray(value)
              ? value.join(", ")
              : String(value);

            return `${field}: ${text}`;
          });

          if (parts.length) {
            message = parts.join(" | ");
          }
        }

        throw new Error(message);
      }

      onSaved(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !saving) {
          onClose();
        }
      }}
    >
      <div className="teacher-modal">
        <div className="modal-header">
          <div>
            <h3>Add Fee Structure</h3>
            <p>Set the amount charged per category for a class.</p>
          </div>

          <button
            className="modal-close"
            onClick={onClose}
            disabled={saving}
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-section">
            <h4>Fee Structure Details</h4>

            <div className="form-grid">
              <label>
                Academic Year
                <select
                  value={academicYear}
                  onChange={(event) => setAcademicYear(event.target.value)}
                  required
                >
                  <option value="">Select year</option>

                  {academicYears.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Campus
                <select
                  value={campus}
                  onChange={(event) => {
                    setCampus(event.target.value);
                    setClassObj("");
                  }}
                  required
                >
                  <option value="">Select campus</option>

                  {campuses.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Class
                <select
                  value={classObj}
                  onChange={(event) => setClassObj(event.target.value)}
                  required
                  disabled={!campus}
                >
                  <option value="">Select class</option>

                  {campusClasses.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Fee Category
                <select
                  value={category}
                  onChange={(event) => setCategory(event.target.value)}
                  required
                >
                  <option value="">Select category</option>

                  {categories.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} ({item.frequency_display})
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Amount (Rs.)
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                  placeholder="0.00"
                  required
                />
              </label>

              <label>
                Due Day
                <input
                  type="number"
                  min="1"
                  max="31"
                  value={dueDay}
                  onChange={(event) => setDueDay(event.target.value)}
                  placeholder="10"
                  required
                />
              </label>
            </div>

            <p className="field-hint">
              Due day is the day of the month on which this fee is expected.
            </p>
          </div>

          {error && (
            <div className="state-card error">
              <strong>Unable to add fee structure.</strong>
              <span>{error}</span>
            </div>
          )}

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
              {saving ? "Saving..." : "Add Fee Structure"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function FeeStructureSection({ categories }) {
  const { t } = useLang();
  const structures = useApiList(FEE_STRUCTURES_API_URL);

  const [academicYears, setAcademicYears] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [classes, setClasses] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [notice, setNotice] = useState("");

  const refresh = () => {
    structures.refresh(new URLSearchParams({ page: 1 }));
  };

  useEffect(() => {
    fetch(ACADEMIC_YEARS_API_URL, { credentials: "include" })
      .then((response) => (response.ok ? response.json() : []))
      .then(setAcademicYears)
      .catch(() => {});

    fetch(CAMPUSES_API_URL, { credentials: "include" })
      .then((response) => (response.ok ? response.json() : []))
      .then(setCampuses)
      .catch(() => {});

    fetch(CLASSES_API_URL, { credentials: "include" })
      .then((response) => (response.ok ? response.json() : []))
      .then(setClasses)
      .catch(() => {});
  }, []);

  const handleSaved = () => {
    setShowModal(false);
    refresh();
  };

  const toggleStatus = (structure) => {
    fetch(`${FEE_STRUCTURES_API_URL}${structure.id}/`, {
      method: "PATCH",
      credentials: "include",
      headers: jsonHeaders(),
      body: JSON.stringify({
        status: structure.status === "active" ? "inactive" : "active",
      }),
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Unable to update fee structure status.");
        }

        return response.json();
      })
      .then(refresh)
      .catch((err) => setNotice(err.message));
  };

  const removeStructure = (structure) => {
    if (
      !window.confirm(
        `Delete fee structure for ${structure.class_name} - ${structure.category_name}?`
      )
    ) {
      return;
    }

    fetch(`${FEE_STRUCTURES_API_URL}${structure.id}/`, {
      method: "DELETE",
      credentials: "include",
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Unable to delete fee structure.");
        }
      })
      .then(refresh)
      .catch((err) => setNotice(err.message));
  };

  return (
    <div className="panel">
      <PanelHeader
        title={t("Fee Structures")}
        subtitle={t("structures configured")}
        count={structures.count}
        action={
          <button
            className="primary-button"
            onClick={() => {
              setNotice("");
              setShowModal(true);
            }}
          >
            <Plus size={16} /> Add Fee Structure
          </button>
        }
      />

      {notice && (
        <div className="state-card error">
          <strong>Something went wrong.</strong>
          <span>{notice}</span>
        </div>
      )}

      <StateArea
        loading={structures.loading}
        error={structures.error}
        onRetry={refresh}
      >
        {structures.rows.length === 0 ? (
          <EmptyState
            icon={PlusCircle}
            title={t("No fee structures")}
            message="Configure the amount charged per fee category for each class."
          />
        ) : (
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("ACADEMIC YEAR")}</th>
                  <th>{t("CAMPUS")}</th>
                  <th>{t("CLASS")}</th>
                  <th>{t("CATEGORY")}</th>
                  <th>{t("AMOUNT")}</th>
                  <th>{t("DUE DAY")}</th>
                  <th>{t("STATUS")}</th>
                  <th></th>
                </tr>
              </thead>

              <tbody>
                {structures.rows.map((structure) => (
                  <tr key={structure.id}>
                    <td>{structure.academic_year_name}</td>

                    <td>{structure.campus_name}</td>

                    <td>
                      <strong>{structure.class_name}</strong>
                    </td>

                    <td>
                      {structure.category_name}
                      <span className="cell-sub">
                        {structure.category_frequency_display}
                      </span>
                    </td>

                    <td>
                      <strong>{formatCurrency(structure.amount)}</strong>
                    </td>

                    <td>{structure.due_day}</td>

                    <td>
                      <StatusBadge
                        status={structure.status}
                        label={structure.status_display}
                      />
                    </td>

                    <td>
                      <div className="action-group">
                        <button
                          className="table-action"
                          onClick={() => toggleStatus(structure)}
                        >
                          {structure.status === "active"
                            ? "Deactivate"
                            : "Activate"}
                        </button>

                        <button
                          className="table-action"
                          onClick={() => removeStructure(structure)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </StateArea>

      {showModal && (
        <FeeStructureModal
          categories={categories}
          academicYears={academicYears}
          campuses={campuses}
          classes={classes}
          onClose={() => setShowModal(false)}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}

function AccountingOverview() {
  const { t } = useLang();
  const [accounts, setAccounts] = useState([]);
  const [report, setReport] = useState(null);
  const [receivables, setReceivables] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError("");

    Promise.all([
      fetch("/api/finance/accounts/", { credentials: "include" }),
      fetch("/api/finance/reports/income-expense/", { credentials: "include" }),
      fetch("/api/finance/reports/receivables/", { credentials: "include" }),
    ])
      .then(async ([accountsResponse, reportResponse, receivablesResponse]) => {
        if (!accountsResponse.ok || !reportResponse.ok || !receivablesResponse.ok) {
          throw new Error("Accounting data is unavailable for this account.");
        }
        const [accountData, reportData, receivablesData] = await Promise.all([
          accountsResponse.json(),
          reportResponse.json(),
          receivablesResponse.json(),
        ]);
        setAccounts(Array.isArray(accountData) ? accountData : accountData.results || []);
        setReport(reportData);
        setReceivables(receivablesData);
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return (
      <div className="state-card error">
        <strong>Accounting overview unavailable</strong>
        <span>{error}</span>
        <button type="button" className="secondary-button" onClick={load}>
          Try Again
        </button>
      </div>
    );
  }

  if (loading) {
    return <SkeletonBlock rows={3} text="Loading accounting overview..." />;
  }

  return (
    <div className="panel">
      <PanelHeader title={t("Accounting overview")} subtitle={t("ledger accounts and balances")} count={accounts.length} />
      <div className="stats-grid">
        <div className="stat-card"><div className="stat-icon"><Wallet size={20} /></div><div className="stat-info"><span>Income</span><strong>{formatCurrency(report?.income || 0)}</strong></div></div>
        <div className="stat-card"><div className="stat-icon"><Receipt size={20} /></div><div className="stat-info"><span>Expenses</span><strong>{formatCurrency(report?.expense || 0)}</strong></div></div>
        <div className="stat-card"><div className="stat-icon"><Wallet size={20} /></div><div className="stat-info"><span>Net result</span><strong>{formatCurrency(report?.net || 0)}</strong></div></div>
        <div className="stat-card"><div className="stat-icon"><Receipt size={20} /></div><div className="stat-info"><span>Receivables</span><strong>{formatCurrency(receivables?.total || 0)}</strong></div></div>
      </div>
      {accounts.length > 0 && (
        <div className="overview-list">
          {accounts.slice(0, 8).map((account) => (
            <div key={account.id}><span>{account.code} · {account.name}</span><StatusBadge status={account.is_active ? "active" : "inactive"} label={account.account_type_display} /></div>
          ))}
        </div>
      )}
    </div>
  );
}

function FeeCategoryModal({ onClose, onSaved }) {
  const [form, setForm] = useState({ name: "", description: "", frequency: "monthly", status: "active" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    if (!form.name.trim()) {
      setError("Enter a fee category name.");
      return;
    }
    setSaving(true);
    try {
      await apiFetch(CATEGORIES_API_URL, {
        method: "POST", headers: jsonHeaders(),
        body: JSON.stringify({ ...form, name: form.name.trim() }),
      }, "Unable to create the fee category.");
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal isOpen onClose={() => { if (!saving) onClose(); }} title="Add Fee Category">
      {error && <div className="state-card error" role="alert">{error}</div>}
      <form onSubmit={submit}>
        <div className="form-grid">
          <label>Name
            <input required maxLength={100} value={form.name} disabled={saving}
              onChange={(event) => setForm({ ...form, name: event.target.value })} />
          </label>
          <label>Frequency
            <select value={form.frequency} disabled={saving}
              onChange={(event) => setForm({ ...form, frequency: event.target.value })}>
              <option value="one_time">One Time</option>
              <option value="monthly">Monthly</option>
              <option value="term">Per Term</option>
              <option value="annual">Annual</option>
            </select>
          </label>
          <label>Description
            <textarea value={form.description} disabled={saving}
              onChange={(event) => setForm({ ...form, description: event.target.value })} />
          </label>
          <label>Status
            <select value={form.status} disabled={saving}
              onChange={(event) => setForm({ ...form, status: event.target.value })}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </label>
        </div>
        <div className="modal-footer">
          <button type="button" className="secondary-button" disabled={saving} onClick={onClose}>Cancel</button>
          <button type="submit" className="primary-button" disabled={saving}>
            {saving ? "Saving..." : "Create Fee Category"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export default function FinancePage() {
  const { t } = useLang();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");

  const invoices = useApiList(INVOICES_API_URL);
  const payments = useApiList(PAYMENTS_API_URL);
  const categories = useApiList(CATEGORIES_API_URL);
  const [showCategoryModal, setShowCategoryModal] = useState(false);

  const [dashboard, setDashboard] = useState(null);
  const [breakdown, setBreakdown] = useState(null);
  const [breakdownError, setBreakdownError] = useState("");

  const [paymentInvoice, setPaymentInvoice] = useState(null);

  const loadDashboard = () => {
    fetch(DASHBOARD_FINANCE_URL, { credentials: "include" })
      .then((response) => (response.ok ? response.json() : null))
      .then(setDashboard)
      .catch(() => setDashboard(null));

    fetch(DASHBOARD_BREAKDOWN_URL, { credentials: "include" })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Finance breakdown is unavailable right now.");
        }
        return response.json();
      })
      .then((data) => {
        setBreakdown(data);
        setBreakdownError("");
      })
      .catch((err) => {
        setBreakdown(null);
        setBreakdownError(err.message);
      });
  };

  const applyInvoices = (pageNumber = 1) => {
    invoices.refresh(buildParams(search, status, pageNumber));
  };

  const applyPayments = (pageNumber = 1) => {
    const params = new URLSearchParams();

    params.append("page", pageNumber);

    if (search.trim()) {
      params.append("search", search.trim());
    }

    payments.refresh(params);
  };

  const clearFilters = () => {
    setSearch("");
    setStatus("");
    applyInvoices(1);
    applyPayments(1);
  };

  const handlePaymentSaved = () => {
    setPaymentInvoice(null);
    loadDashboard();
    applyInvoices(invoices.page);
    applyPayments(1);
  };

  return (
    <section className="content">
      <PageHeader
        crumb={t("Home / Finance")}
        title={t("Finance")}
        subtitle={t("Track invoices, payments and fee categories.")}
        action={<Link to="/finance/bulk" className="primary-button">Bulk Operations</Link>}
      />

      <DashboardCards data={dashboard} />

      <BreakdownCharts data={breakdown} error={breakdownError} onRetry={loadDashboard} />

      <AccountingOverview />

      <Filters
        search={search}
        setSearch={setSearch}
        status={status}
        setStatus={setStatus}
        onSearch={() => {
          applyInvoices(1);
          applyPayments(1);
        }}
        onClear={clearFilters}
      />

      <div className="panel">
        <PanelHeader
          title={t("Invoices")}
          subtitle={t("invoices found")}
          count={invoices.count}
        />

        <StateArea
          loading={invoices.loading}
          error={invoices.error}
          onRetry={() => applyInvoices(invoices.page)}
        >
          {invoices.rows.length === 0 ? (
            <EmptyState
              icon={Wallet}
              title={t("No invoices found")}
              message="No invoices match the current filters."
            />
          ) : (
            <>
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t("INVOICE NO.")}</th>
                      <th>STUDENT</th>
                      <th>{t("CLASS")}</th>
                      <th>{t("ISSUE DATE")}</th>
                      <th>{t("DUE DATE")}</th>
                      <th>{t("TOTAL")}</th>
                      <th>{t("PAID")}</th>
                      <th>{t("BALANCE")}</th>
                      <th>{t("STATUS")}</th>
                      <th></th>
                    </tr>
                  </thead>

                  <tbody>
                    {invoices.rows.map((invoice) => (
                      <tr key={invoice.id}>
                        <td>
                          <strong>{invoice.invoice_number || "—"}</strong>
                        </td>

                        <td>
                          <strong>{invoice.student_name || "—"}</strong>
                          <span className="cell-sub">
                            {invoice.admission_number || ""}
                          </span>
                        </td>

                        <td>{invoice.class_name || "—"}</td>

                        <td>{formatDate(invoice.issue_date)}</td>

                        <td>{formatDate(invoice.due_date)}</td>

                        <td>{formatCurrency(invoice.total_amount)}</td>

                        <td>{formatCurrency(invoice.paid_amount)}</td>

                        <td>
                          <strong>{formatCurrency(invoice.balance)}</strong>
                        </td>

                        <td>
                          <StatusBadge
                            status={invoice.status}
                            label={invoice.status_display}
                          />
                        </td>

                        <td>
                          <button
                            className="table-action"
                            onClick={() => setPaymentInvoice(invoice)}
                            disabled={Number(invoice.balance) <= 0}
                          >
                            Record Payment
                          </button>
                          {Number(invoice.balance) > 0 && (
                            <button
                              className="table-action"
                              style={{ marginLeft: 6 }}
                              onClick={async () => {
                                try {
                                  const res = await fetch("/api/finance/stripe/checkout/", {
                                    method: "POST",
                                    credentials: "include",
                                    headers: jsonHeaders(),
                                    body: JSON.stringify({ invoice_id: invoice.id }),
                                  });
                                  const data = await res.json();
                                  if (res.ok && data.session_url) {
                                    window.location.href = data.session_url;
                                  } else {
                                    alert(data.detail || "Could not start payment.");
                                  }
                                } catch {
                                  alert("Payment gateway error.");
                                }
                              }}
                            >
                              Pay Online
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Pagination
                count={invoices.count}
                page={invoices.page}
                next={invoices.next}
                previous={invoices.previous}
                onPage={(pageNumber) => applyInvoices(pageNumber)}
              />
            </>
          )}
        </StateArea>
      </div>

      <div className="panel">
        <PanelHeader
          title="Payments"
          subtitle="payments recorded"
          count={payments.count}
        />

        <StateArea
          loading={payments.loading}
          error={payments.error}
          onRetry={() => applyPayments(payments.page)}
        >
          {payments.rows.length === 0 ? (
            <EmptyState
              icon={Receipt}
              title="No payments found"
              message="No payments match the current filters."
            />
          ) : (
            <>
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t("RECEIPT NO.")}</th>
                      <th>STUDENT</th>
                      <th>{t("INVOICE")}</th>
                      <th>{t("DATE")}</th>
                      <th>{t("METHOD")}</th>
                      <th>{t("AMOUNT")}</th>
                      <th>{t("STATUS")}</th>
                      <th>{t("RECEIPT")}</th>
                    </tr>
                  </thead>

                  <tbody>
                    {payments.rows.map((payment) => (
                      <tr key={payment.id}>
                        <td>
                          <strong>{payment.receipt_number || "—"}</strong>
                        </td>

                        <td>
                          <strong>{payment.student_name || "—"}</strong>
                        </td>

                        <td>{payment.invoice_number || "—"}</td>

                        <td>{formatDate(payment.payment_date)}</td>

                        <td>{payment.payment_method_display || "—"}</td>

                        <td>
                          <strong>{formatCurrency(payment.amount)}</strong>
                        </td>

                        <td>
                          <StatusBadge
                            status={payment.status}
                            label={payment.status_display}
                          />
                        </td>

                        <td>
                          <div className="action-group">
                            <button
                              className="table-action"
                              onClick={() =>
                                window.open(
                                  `/api/finance/payments/${payment.id}/receipt/`,
                                  "_blank"
                                )
                              }
                              title="View HTML receipt"
                            >
                              <Receipt size={15} /> View
                            </button>

                            <button
                              className="table-action"
                              onClick={() =>
                                window.open(
                                  `/api/finance/payments/${payment.id}/receipt.pdf/`,
                                  "_blank"
                                )
                              }
                              title="Download PDF receipt"
                            >
                              <FileDown size={15} /> PDF
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Pagination
                count={payments.count}
                page={payments.page}
                next={payments.next}
                previous={payments.previous}
                onPage={(pageNumber) => applyPayments(pageNumber)}
              />
            </>
          )}
        </StateArea>
      </div>

      <div className="panel">
        <PanelHeader
          title="Fee Categories"
          subtitle="categories configured"
          count={categories.count}
          action={<button type="button" className="primary-button" onClick={() => setShowCategoryModal(true)}>
            <Plus size={15} /> Add Fee Category
          </button>}
        />

        <StateArea loading={categories.loading} error={categories.error}>
          {categories.rows.length === 0 ? (
            <EmptyState
              icon={PlusCircle}
              title="No fee categories"
              message="No fee categories have been configured yet."
            />
          ) : (
            <div className="overview-list">
              {categories.rows.map((category) => (
                <div key={category.id}>
                  <span>
                    {category.name} A� {category.frequency_display}
                  </span>

                  <StatusBadge status={category.status} />
                </div>
              ))}
            </div>
          )}
        </StateArea>
      </div>

      <FeeStructureSection categories={categories.rows} />

      {showCategoryModal && <FeeCategoryModal
        onClose={() => setShowCategoryModal(false)}
        onSaved={() => categories.refresh(new URLSearchParams({ page: "1" }))}
      />}

      {paymentInvoice && (
        <PaymentModal
          invoice={paymentInvoice}
          onClose={() => setPaymentInvoice(null)}
          onSaved={handlePaymentSaved}
        />
      )}
    </section>
  );
}
