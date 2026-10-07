import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Banknote,
  BadgePoundSterling,
  ReceiptText,
  Plus,
  Edit,
  Trash2,
  Loader2,
} from "lucide-react";
import { PageHeader, PanelHeader, StateArea, EmptyState } from "./ui";
import { formatCurrency, formatDate } from "./format";
import { apiFetch, apiDownload, jsonHeaders, buildErrorMessage } from "../api";
import { Modal } from "../components/Modal";

const BASE = "/api/payroll/";

const ENDPOINTS = {
  structures: { url: "salary-structures/", icon: BadgePoundSterling, title: "Salary Structures" },
  records: { url: "records/", icon: Banknote, title: "Payroll Records" },
  payslips: { url: "payslips/", icon: ReceiptText, title: "Payslips" },
};

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const STRUCTURE_STATUS_CHOICES = [
  { value: "active", label: "Active" },
  { value: "archived", label: "Archived" },
];

const COMPONENT_TYPES = [
  { value: "allowance", label: "Allowance" },
  { value: "deduction", label: "Deduction" },
];

const CALCULATION_TYPES = [
  { value: "fixed", label: "Fixed Amount" },
  { value: "percent_basic", label: "% of Basic" },
  { value: "percent_gross", label: "% of Gross" },
  { value: "percent_net", label: "% of Net" },
  { value: "per_day", label: "Per Day" },
  { value: "per_hour", label: "Per Hour" },
];

const RECORD_STATUS_CHOICES = [
  { value: "draft", label: "Draft" },
  { value: "processed", label: "Processed" },
  { value: "approved", label: "Approved" },
  { value: "paid", label: "Paid" },
  { value: "cancelled", label: "Cancelled" },
];

export default function PayrollPage() {
  const [tab, setTab] = useState("records");
  const [data, setData] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [processing, setProcessing] = useState(null);

  // Reference data for forms
  const [employees, setEmployees] = useState([]);
  const [payrollPeriods, setPayrollPeriods] = useState([]);
  const [salaryStructures, setSalaryStructures] = useState([]);

  // Modals
  const [modal, setModal] = useState(null); // null | { type: 'structure'|'record', mode: 'create'|'edit', item }
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  // Structure form state
  const [structureForm, setStructureForm] = useState({
    employee: "",
    name: "",
    code: "",
    basic_salary: "",
    effective_date: "",
    status: "active",
    components: [],
  });

  // Record form state
  const [recordForm, setRecordForm] = useState({
    employee: "",
    campus: "",
    salary_structure: "",
    payroll_period: "",
    month: new Date().getMonth() + 1,
    year: new Date().getFullYear(),
    working_days: "",
    paid_days: "",
    leave_days: "0",
    overtime_hours: "0",
    overtime_amount: "0",
    status: "draft",
  });

  // Load reference data
  const loadReferenceData = useCallback(async () => {
    try {
      const [empRes, periodRes, structRes] = await Promise.all([
        fetch("/api/hr/employees/", { credentials: "include" }),
        fetch("/api/hr/payroll-periods/", { credentials: "include" }),
        fetch("/api/payroll/salary-structures/", { credentials: "include" }),
      ]);

      if (empRes.ok) {
        const empData = await empRes.json();
        setEmployees(Array.isArray(empData) ? empData : (empData.results || []));
      }
      if (periodRes.ok) {
        const periodData = await periodRes.json();
        setPayrollPeriods(Array.isArray(periodData) ? periodData : (periodData.results || []));
      }
      if (structRes.ok) {
        const structData = await structRes.json();
        setSalaryStructures(Array.isArray(structData) ? structData : (structData.results || []));
      }
    } catch (err) {
      console.warn("Failed to load reference data:", err);
    }
  }, []);

  useEffect(() => {
    loadReferenceData();
  }, [loadReferenceData]);

  const load = useCallback(
    (key) => {
      const config = ENDPOINTS[key];

      setLoading(true);
      setError("");

      fetch(`${BASE}${config.url}`, { credentials: "include" })
        .then((response) => (response.ok ? response.json() : { results: [] }))
        .then((json) => {
          setData((previous) => ({
            ...previous,
            [key]: json.results || json,
          }));
          setLoading(false);
        })
        .catch((err) => {
          setError(err.message);
          setLoading(false);
        });
    },
    [],
  );

  const initialLoadDone = useRef(false);

  useEffect(() => {
    if (initialLoadDone.current) return;
    initialLoadDone.current = true;
    load(tab);
  }, [load, tab]);

  const switchTab = (key) => {
    setTab(key);
    setMessage("");

    if (data[key] === undefined) {
      load(key);
    }
  };

  const handleProcess = useCallback(async (recordId) => {
    setProcessing(recordId);
    setMessage("");
    setError("");

    try {
      await apiFetch(
        `${BASE}records/${recordId}/process/`,
        { method: "POST", headers: jsonHeaders() },
        "Could not process the payroll record."
      );

      setMessage("Payroll record marked as paid.");
      setData((previous) => ({ ...previous, records: undefined }));
      load("records");
    } catch (err) {
      setError(err.message);
    } finally {
      setProcessing(null);
    }
  }, [load]);

  const handleApprove = useCallback(async (recordId) => {
    setProcessing(recordId);
    setMessage("");
    setError("");

    try {
      await apiFetch(
        `${BASE}records/${recordId}/approve/`,
        { method: "POST", headers: jsonHeaders() },
        "Could not approve the payroll record."
      );

      setMessage("Payroll record approved.");
      setData((previous) => ({ ...previous, records: undefined }));
      load("records");
    } catch (err) {
      setError(err.message);
    } finally {
      setProcessing(null);
    }
  }, [load]);

  const handlePay = useCallback(async (recordId) => {
    setProcessing(recordId);
    setMessage("");
    setError("");

    try {
      await apiFetch(
        `${BASE}records/${recordId}/pay/`,
        { method: "POST", headers: jsonHeaders() },
        "Could not mark the payroll record as paid."
      );

      setMessage("Payroll record marked as paid.");
      setData((previous) => ({ ...previous, records: undefined }));
      load("records");
    } catch (err) {
      setError(err.message);
    } finally {
      setProcessing(null);
    }
  }, [load]);

  // Modal handlers
  const openStructureModal = useCallback((mode, item = null) => {
    if (mode === "create") {
      setStructureForm({
        employee: "",
        name: "",
        code: "",
        basic_salary: "",
        effective_date: new Date().toISOString().split("T")[0],
        status: "active",
        components: [],
      });
    } else if (mode === "edit" && item) {
      setStructureForm({
        employee: item.employee?.toString() || "",
        name: item.name || "",
        code: item.code || "",
        basic_salary: item.basic_salary?.toString() || "",
        effective_date: item.effective_date || "",
        status: item.status || "active",
        components: item.components || [],
      });
    }
    setModal({ type: "structure", mode, item });
    setFormError("");
  }, []);

  const closeStructureModal = () => {
    setModal(null);
    setFormError("");
  };

  const addComponent = () => {
    setStructureForm((prev) => ({
      ...prev,
      components: [
        ...prev.components,
        {
          component_type: "allowance",
          name: "",
          code: "",
          description: "",
          calculation_type: "fixed",
          amount: "0",
          percentage: "0",
          is_taxable: true,
          is_active: true,
          sequence: prev.components.length,
        },
      ],
    }));
  };

  const handleStructureSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setFormError("");

    try {
      const isEditing = modal.mode === "edit";
      const url = isEditing
        ? `${BASE}salary-structures/${modal.item.id}/`
        : `${BASE}salary-structures/`;

      const payload = {
        employee: Number(structureForm.employee),
        name: structureForm.name.trim(),
        code: structureForm.code.trim(),
        basic_salary: structureForm.basic_salary,
        effective_date: structureForm.effective_date,
        status: structureForm.status,
        components: structureForm.components
          .filter((c) => c.name && c.code)
          .map((c, i) => ({
            component_type: c.component_type,
            name: c.name.trim(),
            code: c.code.trim(),
            description: c.description || "",
            calculation_type: c.calculation_type,
            amount: c.amount,
            percentage: c.percentage || 0,
            is_taxable: c.is_taxable,
            is_active: c.is_active,
            sequence: c.sequence ?? i,
          })),
      };

      const response = await fetch(url, {
        method: isEditing ? "PUT" : "POST",
        credentials: "include",
        headers: jsonHeaders(),
        body: JSON.stringify(payload),
      });

      const responseText = await response.text();
      let responseData = {};
      try {
        responseData = responseText ? JSON.parse(responseText) : {};
      } catch {
        responseData = {};
      }

      if (!response.ok) {
        throw new Error(
          buildErrorMessage({
            status: response.status,
            detail: responseData.detail,
            fieldErrors: responseData,
            responseText,
            fallback: "Failed to save salary structure.",
          })
        );
      }

      setMessage(isEditing ? "Salary structure updated." : "Salary structure created.");
      setModal(null);
      setData((prev) => ({ ...prev, structures: undefined }));
      load("structures");
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const openRecordModal = useCallback((mode, item = null) => {
    if (mode === "create") {
      setRecordForm({
        employee: "",
        campus: "",
        salary_structure: "",
        payroll_period: "",
        month: new Date().getMonth() + 1,
        year: new Date().getFullYear(),
        working_days: "",
        paid_days: "",
        leave_days: "0",
        overtime_hours: "0",
        overtime_amount: "0",
        status: "draft",
      });
    } else if (mode === "edit" && item) {
      setRecordForm({
        employee: item.employee?.toString() || "",
        campus: item.campus?.toString() || "",
        salary_structure: item.salary_structure?.toString() || "",
        payroll_period: item.payroll_period?.toString() || "",
        month: item.month || new Date().getMonth() + 1,
        year: item.year || new Date().getFullYear(),
        working_days: item.working_days?.toString() || "",
        paid_days: item.paid_days?.toString() || "",
        leave_days: item.leave_days?.toString() || "0",
        overtime_hours: item.overtime_hours?.toString() || "0",
        overtime_amount: item.overtime_amount?.toString() || "0",
        status: item.status || "draft",
      });
    }
    setModal({ type: "record", mode, item });
    setFormError("");
  }, []);

  const closeRecordModal = () => {
    setModal(null);
    setFormError("");
  };

  const handleRecordSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setFormError("");

    try {
      const isEditing = modal.mode === "edit";
      const url = isEditing
        ? `${BASE}records/${modal.item.id}/`
        : `${BASE}records/`;

      const payload = {
        employee: Number(recordForm.employee),
        campus: recordForm.campus ? Number(recordForm.campus) : null,
        salary_structure: Number(recordForm.salary_structure),
        payroll_period: Number(recordForm.payroll_period),
        month: Number(recordForm.month),
        year: Number(recordForm.year),
        working_days: Number(recordForm.working_days) || 0,
        paid_days: Number(recordForm.paid_days) || 0,
        leave_days: recordForm.leave_days || 0,
        overtime_hours: recordForm.overtime_hours || 0,
        overtime_amount: recordForm.overtime_amount || 0,
        status: recordForm.status,
      };

      const response = await fetch(url, {
        method: isEditing ? "PATCH" : "POST",
        credentials: "include",
        headers: jsonHeaders(),
        body: JSON.stringify(payload),
      });

      const responseText = await response.text();
      let responseData = {};
      try {
        responseData = responseText ? JSON.parse(responseText) : {};
      } catch {
        responseData = {};
      }

      if (!response.ok) {
        throw new Error(
          buildErrorMessage({
            status: response.status,
            detail: responseData.detail,
            fieldErrors: responseData,
            responseText,
            fallback: "Failed to save payroll record.",
          })
        );
      }

      setMessage(isEditing ? "Payroll record updated." : "Payroll record created.");
      setModal(null);
      setData((prev) => ({ ...prev, records: undefined }));
      load("records");
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = useCallback(async (type, itemId) => {
    if (!window.confirm(`Delete this ${type === "structure" ? "salary structure" : "payroll record"}?`)) return;

    setSaving(true);
    try {
      await fetch(`${BASE}${type === "structure" ? "salary-structures" : "records"}/${itemId}/`, {
        method: "DELETE",
        credentials: "include",
        headers: jsonHeaders(),
      });
      setMessage(`${type === "structure" ? "Salary structure" : "Payroll record"} deleted.`);
      setData((prev) => ({ ...prev, [type === "structure" ? "structures" : "records"]: undefined }));
      load(type === "structure" ? "structures" : "records");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }, [load]);


  const rows = useMemo(() => data[tab] || [], [data, tab]);

  // Render functions for table bodies
  const renderStructures = useCallback(() => (
    rows.map((structure) => (
      <tr key={structure.id}>
        <td>
          <strong>{structure.teacher_name || "—"}</strong>
        </td>

        <td>{formatCurrency(structure.basic_salary)}</td>

        <td>{formatCurrency(structure.total_allowances)}</td>

        <td>
          <strong>{formatCurrency(structure.gross_salary)}</strong>
        </td>

        <td>{formatDate(structure.effective_date)}</td>

        <td>
          <span className={`status-badge ${structure.status === "active" ? "active" : "inactive"}`}>
            {structure.status ? structure.status.charAt(0).toUpperCase() + structure.status.slice(1) : "—"}
          </span>
        </td>

        <td>
          <button
            type="button"
            className="table-action"
            onClick={() => openStructureModal("edit", structure)}
            title="Edit"
          >
            <Edit size={14} />
          </button>
          <button
            type="button"
            className="table-action danger"
            onClick={() => handleDelete("structure", structure.id)}
            title="Delete"
          >
            <Trash2 size={14} />
          </button>
        </td>
      </tr>
    ))
  ), [rows, openStructureModal, handleDelete]);

  const renderRecords = useCallback(() => (
    rows.map((record) => (
      <tr key={record.id}>
        <td>
          <strong>{record.teacher_name || "—"}</strong>
        </td>

        <td>{record.teacher_number || "—"}</td>

        <td>
          {record.month ? MONTHS[record.month - 1] : "—"} {record.year || ""}
        </td>

        <td>{record.working_days ?? "—"}</td>

        <td>{record.paid_days ?? "—"}</td>

        <td>{formatCurrency(record.gross_salary)}</td>

        <td>{formatCurrency(record.total_deductions)}</td>

        <td>
          <strong>{formatCurrency(record.net_salary)}</strong>
        </td>

        <td>
          <span className={`status-badge ${record.status === "paid" ? "active" : record.status === "approved" ? "warn" : record.status === "processed" ? "info" : "inactive"}`}>
            {record.status ? record.status.charAt(0).toUpperCase() + record.status.slice(1) : "—"}
          </span>
        </td>

        <td>
          {record.status !== "paid" && (
            <>
              <button
                type="button"
                className="table-action"
                onClick={() => openRecordModal("edit", record)}
                title="Edit"
              >
                <Edit size={14} />
              </button>
              {record.status === "draft" && (
                <button
                  type="button"
                  className="table-action"
                  disabled={processing === record.id}
                  onClick={() => handleProcess(record.id)}
                  title="Process"
                >
                  {processing === record.id ? <Loader2 size={14} className="spin" /> : "Process"}
                </button>
              )}
              {record.status === "processed" && (
                <button
                  type="button"
                  className="table-action"
                  disabled={processing === record.id}
                  onClick={() => handleApprove(record.id)}
                  title="Approve"
                >
                  {processing === record.id ? <Loader2 size={14} className="spin" /> : "Approve"}
                </button>
              )}
              {record.status === "approved" && (
                <button
                  type="button"
                  className="table-action"
                  disabled={processing === record.id}
                  onClick={() => handlePay(record.id)}
                  title="Mark Paid"
                >
                  {processing === record.id ? <Loader2 size={14} className="spin" /> : "Pay"}
                </button>
              )}
            </>
          )}
          {record.status === "paid" && (
            <button
              type="button"
              className="table-action"
              title="Download Payslip"
              onClick={() =>
                apiDownload(
                  `${BASE}records/${record.id}/payslip.pdf`,
                  `payslip_${record.teacher_number || record.id}_${record.year}_${String(record.month).padStart(2, "0")}.pdf`
                ).catch(() => alert("Could not download payslip."))
              }
              title="Download Payslip"
            >
              Payslip PDF
            </button>
          )}
          {(record.status === "draft" || record.status === "processed") && (
            <button
              type="button"
              className="table-action danger"
              onClick={() => handleDelete("record", record.id)}
              title="Delete"
            >
              <Trash2 size={14} />
            </button>
          )}
        </td>
      </tr>
    ))
  ), [rows, processing, handleProcess, handleApprove, handlePay, openRecordModal, handleDelete]);

  const renderPayslips = useCallback(() => (
    rows.map((payslip) => (
      <tr key={payslip.id}>
        <td>
          <strong>{payslip.teacher_name || "—"}</strong>
        </td>

        <td>{payslip.period || "—"}</td>

        <td>{formatDate(payslip.issued_at)}</td>
      </tr>
    ))
  ), [rows]);

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Payroll"
        title="Payroll"
        subtitle="Manage teacher salary structures, payroll records, and payslips."
        action={
          tab === "structures" ? (
            <button
              type="button"
              className="primary-button"
              onClick={() => openStructureModal("create")}
            >
              <Plus size={15} /> Add Salary Structure
            </button>
          ) : tab === "records" ? (
            <button
              type="button"
              className="primary-button"
              onClick={() => openRecordModal("create")}
            >
              <Plus size={15} /> Add Payroll Record
            </button>
          ) : null
        }
      />

      {message && (
        <div className="state-card success">
          <strong>{message}</strong>
        </div>
      )}

      <div className="tabs">
        {Object.entries(ENDPOINTS).map(([key, config]) => {
          const Icon = config.icon;

          return (
            <button
              key={key}
              className={`tab-button ${tab === key ? "active" : ""}`}
              onClick={() => switchTab(key)}
            >
              <Icon size={15} />
              {config.title}
            </button>
          );
        })}
      </div>

      <div className="panel">
        <PanelHeader
          title={ENDPOINTS[tab].title}
          subtitle="records found"
          count={rows.length || null}
        />

        <StateArea
          loading={loading}
          error={error}
          onRetry={() => load(tab)}
        >
          {rows.length === 0 ? (
            <EmptyState
              icon={ENDPOINTS[tab].icon}
              title={`No ${ENDPOINTS[tab].title.toLowerCase()} found`}
              message="Records will appear here once added."
            />
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  {tab === "structures" && (
                    <tr>
                      <th>TEACHER</th>
                      <th>BASIC SALARY</th>
                      <th>ALLOWANCES</th>
                      <th>GROSS SALARY</th>
                      <th>EFFECTIVE DATE</th>
                      <th>STATUS</th>
                    </tr>
                  )}

                  {tab === "records" && (
                    <tr>
                      <th>TEACHER</th>
                      <th>EMP NO.</th>
                      <th>PERIOD</th>
                      <th>WORKING</th>
                      <th>PAID</th>
                      <th>GROSS</th>
                      <th>DEDUCTIONS</th>
                      <th>NET SALARY</th>
                      <th>STATUS</th>
                      <th>ACTION</th>
                    </tr>
                  )}

                  {tab === "payslips" && (
                    <tr>
                      <th>TEACHER</th>
                      <th>PERIOD</th>
                      <th>ISSUED AT</th>
                    </tr>
                  )}
                </thead>

                <tbody>
                  {tab === "structures" && renderStructures()}
                  {tab === "records" && renderRecords()}
                  {tab === "payslips" && renderPayslips()}
                </tbody>
              </table>
            </div>
          )}
        </StateArea>
      </div>

      {/* Structure Modal */}
      <Modal
        isOpen={modal?.type === "structure"}
        onClose={closeStructureModal}
        title={modal?.mode === "create" ? "Add Salary Structure" : "Edit Salary Structure"}
        size="lg"
        closeOnOverlayClick
        closeOnEscape
      >
        <form onSubmit={handleStructureSubmit}>
          <div className="form-section">
            <h4>Basic Information</h4>
            <div className="form-grid">
              <label>
                Employee *
                <select name="employee" value={structureForm.employee} onChange={(e) => setStructureForm({ ...structureForm, employee: e.target.value })} required>
                  <option value="">Select employee</option>
                  {employees.map((emp) => (
                    <option key={emp.id} value={emp.id}>{emp.full_name || emp.employee_number} ({emp.employee_number})</option>
                  ))}
                </select>
              </label>

              <label>
                Name *
                <input name="name" value={structureForm.name} onChange={(e) => setStructureForm({ ...structureForm, name: e.target.value })} required placeholder="e.g. Primary Teacher Structure" />
              </label>

              <label>
                Code *
                <input name="code" value={structureForm.code} onChange={(e) => setStructureForm({ ...structureForm, code: e.target.value.toUpperCase() })} required placeholder="e.g. TS-PRIMARY" maxLength={20} />
              </label>

              <label>
                Basic Salary *
                <input type="number" name="basic_salary" step="0.01" min="0" value={structureForm.basic_salary} onChange={(e) => setStructureForm({ ...structureForm, basic_salary: e.target.value })} required placeholder="0.00" />
              </label>

              <label>
                Effective Date *
                <input type="date" name="effective_date" value={structureForm.effective_date} onChange={(e) => setStructureForm({ ...structureForm, effective_date: e.target.value })} required />
              </label>

              <label>
                Status *
                <select name="status" value={structureForm.status} onChange={(e) => setStructureForm({ ...structureForm, status: e.target.value })}>
                  {STRUCTURE_STATUS_CHOICES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </label>
            </div>
          </div>

          <div className="form-section">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <h4>Components (Allowances & Deductions)</h4>
              <button type="button" className="secondary-button" onClick={addComponent} disabled={saving}>
                <Plus size={14} /> Add Component
              </button>
            </div>

            {structureForm.components.length === 0 ? (
              <p className="muted" style={{ textAlign: "center", padding: 20 }}>No components added yet. Click "Add Component" to add allowances or deductions.</p>
            ) : (
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>TYPE</th>
                      <th>NAME</th>
                      <th>CODE</th>
                      <th>CALC. TYPE</th>
                      <th>AMOUNT</th>
                      <th>%</th>
                      <th>TAXABLE</th>
                      <th>ACTIVE</th>
                      <th>SEQ</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {structureForm.components.map((comp, i) => (
                      <tr key={i}>
                        <td>
                          <select value={comp.component_type} onChange={(e) => setStructureForm({ ...structureForm, components: structureForm.components.map((c, j) => j === i ? { ...c, component_type: e.target.value } : c) })} disabled={saving}>
                            {COMPONENT_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                          </select>
                        </td>
                        <td><input value={comp.name} onChange={(e) => setStructureForm({ ...structureForm, components: structureForm.components.map((c, j) => j === i ? { ...c, name: e.target.value } : c) })} placeholder="Name" disabled={saving} /></td>
                        <td><input value={comp.code} onChange={(e) => setStructureForm({ ...structureForm, components: structureForm.components.map((c, j) => j === i ? { ...c, code: e.target.value.toUpperCase() } : c) })} placeholder="Code" maxLength={20} disabled={saving} /></td>
                        <td>
                          <select value={comp.calculation_type} onChange={(e) => setStructureForm({ ...structureForm, components: structureForm.components.map((c, j) => j === i ? { ...c, calculation_type: e.target.value } : c) })} disabled={saving}>
                            {CALCULATION_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                          </select>
                        </td>
                        <td><input type="number" step="0.01" min="0" value={comp.amount} onChange={(e) => setStructureForm({ ...structureForm, components: structureForm.components.map((c, j) => j === i ? { ...c, amount: e.target.value } : c) })} disabled={saving} /></td>
                        <td><input type="number" step="0.01" min="0" max="100" value={comp.percentage} onChange={(e) => setStructureForm({ ...structureForm, components: structureForm.components.map((c, j) => j === i ? { ...c, percentage: e.target.value } : c) })} disabled={saving} /></td>
                        <td>
                          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <input type="checkbox" checked={comp.is_taxable} onChange={(e) => setStructureForm({ ...structureForm, components: structureForm.components.map((c, j) => j === i ? { ...c, is_taxable: e.target.checked } : c) })} disabled={saving} />
                          </label>
                        </td>
                        <td>
                          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <input type="checkbox" checked={comp.is_active} onChange={(e) => setStructureForm({ ...structureForm, components: structureForm.components.map((c, j) => j === i ? { ...c, is_active: e.target.checked } : c) })} disabled={saving} />
                          </label>
                        </td>
                        <td><input type="number" min="0" value={comp.sequence} onChange={(e) => setStructureForm({ ...structureForm, components: structureForm.components.map((c, j) => j === i ? { ...c, sequence: Number(e.target.value) } : c) })} style={{ width: 60 }} disabled={saving} /></td>
                        <td>
                          <button type="button" className="table-action danger" onClick={() => setStructureForm({ ...structureForm, components: structureForm.components.filter((_, j) => j !== i) })} disabled={saving} title="Remove">
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="modal-footer">
            <button type="button" className="secondary-button" onClick={closeStructureModal} disabled={saving}>Cancel</button>
            <button type="button" className="primary-button" onClick={handleStructureSubmit} disabled={saving}>
              {saving ? <Loader2 size={14} className="spin" /> : modal?.mode === "create" ? "Create" : "Save"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Record Modal */}
      <Modal
        isOpen={modal?.type === "record"}
        onClose={closeRecordModal}
        title={modal?.mode === "create" ? "Add Payroll Record" : "Edit Payroll Record"}
        size="lg"
        closeOnOverlayClick
        closeOnEscape
      >
        {formError && <div className="state-card error"><strong>Error:</strong> {formError}</div>}
        <form onSubmit={handleRecordSubmit}>
          <div className="form-section">
            <h4>Basic Information</h4>
            <div className="form-grid">
              <label>
                Employee *
                <select name="employee" value={recordForm.employee} onChange={(e) => setRecordForm({ ...recordForm, employee: e.target.value })} required>
                  <option value="">Select employee</option>
                  {employees.map((emp) => (
                    <option key={emp.id} value={emp.id}>{emp.full_name || emp.employee_number} ({emp.employee_number})</option>
                  ))}
                </select>
              </label>

              <label>
                Campus
                <select name="campus" value={recordForm.campus} onChange={(e) => setRecordForm({ ...recordForm, campus: e.target.value })}>
                  <option value="">Select campus (optional)</option>
                </select>
              </label>

              <label>
                Salary Structure *
                <select name="salary_structure" value={recordForm.salary_structure} onChange={(e) => setRecordForm({ ...recordForm, salary_structure: e.target.value })} required>
                  <option value="">Select structure</option>
                  {salaryStructures.map((s) => (
                    <option key={s.id} value={s.id}>{s.name} ({s.code}) - {s.employee?.full_name || s.employee}</option>
                  ))}
                </select>
              </label>

              <label>
                Payroll Period *
                <select name="payroll_period" value={recordForm.payroll_period} onChange={(e) => setRecordForm({ ...recordForm, payroll_period: e.target.value })} required>
                  <option value="">Select period</option>
                  {payrollPeriods.map((p) => (
                    <option key={p.id} value={p.id}>{p.name} ({formatDate(p.start_date)} to {formatDate(p.end_date)})</option>
                  ))}
                </select>
              </label>

              <label>
                Month *
                <select name="month" value={recordForm.month} onChange={(e) => setRecordForm({ ...recordForm, month: e.target.value })} required>
                  {MONTHS.map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
                </select>
              </label>

              <label>
                Year *
                <input type="number" name="year" min="2020" max="2030" value={recordForm.year} onChange={(e) => setRecordForm({ ...recordForm, year: e.target.value })} required />
              </label>

              <label>
                Working Days
                <input type="number" name="working_days" min="0" max="31" value={recordForm.working_days} onChange={(e) => setRecordForm({ ...recordForm, working_days: e.target.value })} placeholder="0" />
              </label>

              <label>
                Paid Days
                <input type="number" name="paid_days" min="0" max="31" value={recordForm.paid_days} onChange={(e) => setRecordForm({ ...recordForm, paid_days: e.target.value })} placeholder="0" />
              </label>

              <label>
                Leave Days
                <input type="number" name="leave_days" step="0.5" min="0" value={recordForm.leave_days} onChange={(e) => setRecordForm({ ...recordForm, leave_days: e.target.value })} placeholder="0" />
              </label>

              <label>
                Overtime Hours
                <input type="number" name="overtime_hours" step="0.5" min="0" value={recordForm.overtime_hours} onChange={(e) => setRecordForm({ ...recordForm, overtime_hours: e.target.value })} placeholder="0" />
              </label>

              <label>
                Overtime Amount
                <input type="number" step="0.01" min="0" name="overtime_amount" value={recordForm.overtime_amount} onChange={(e) => setRecordForm({ ...recordForm, overtime_amount: e.target.value })} placeholder="0.00" />
              </label>

              <label>
                Status *
                <select name="status" value={recordForm.status} onChange={(e) => setRecordForm({ ...recordForm, status: e.target.value })}>
                  {RECORD_STATUS_CHOICES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </label>
</div>
          </div>

          <div className="modal-footer">
            <button type="button" className="secondary-button" onClick={closeRecordModal} disabled={saving}>Cancel</button>
            <button type="button" className="primary-button" onClick={(e) => { e.preventDefault(); handleRecordSubmit(e); }} disabled={saving}>
              {saving ? <Loader2 size={14} className="spin" /> : modal?.mode === "create" ? "Create" : "Save"}
            </button>
          </div>
        </form>
      </Modal>
    </section>
  );
}
