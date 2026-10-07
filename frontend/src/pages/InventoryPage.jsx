import { useState, useEffect, useCallback } from "react";
import {
  Tags,
  Truck,
  Wrench,
  PackageSearch,
  Search,
  Plus,
  Pencil,
  Trash2,
  X,
} from "lucide-react";
import { PageHeader, PanelHeader, StateArea, EmptyState } from "./ui";
import { formatCurrency, formatDate } from "./format";
import { apiFetch, jsonHeaders } from "../api";

const BASE = "/api/inventory/";
const CAMPUSES_URL = "/api/schools/campuses/";

const ENDPOINTS = {
  assets: { url: "assets/", icon: PackageSearch, title: "Assets" },
  categories: { url: "categories/", icon: Tags, title: "Categories" },
  suppliers: { url: "suppliers/", icon: Truck, title: "Suppliers" },
  maintenance: { url: "maintenance/", icon: Wrench, title: "Maintenance" },
};

const ASSET_STATUS_CHOICES = [
  { value: "in_stock", label: "In Stock" },
  { value: "in_use", label: "In Use" },
  { value: "maintenance", label: "Under Maintenance" },
  { value: "expired", label: "Expired" },
  { value: "retired", label: "Retired" },
];

const EMPTY_ASSET_FORM = {
  name: "",
  campus: "",
  code: "",
  category: "",
  supplier: "",
  quantity: 1,
  unit: "pcs",
  unit_cost: "",
  purchase_date: "",
  location: "",
  status: "in_stock",
  notes: "",
};

export default function InventoryPage() {
  const [tab, setTab] = useState("assets");
  const [data, setData] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formValidationErrors, setFormValidationErrors] = useState({});
  const [form, setForm] = useState(EMPTY_ASSET_FORM);

  const [campuses, setCampuses] = useState([]);
  const [categories, setCategories] = useState([]);
  const [suppliers, setSuppliers] = useState([]);

  const loadDropdowns = useCallback(() => {
    fetch(CAMPUSES_URL, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setCampuses(Array.isArray(d) ? d : []))
      .catch(() => {});

    fetch(`${BASE}categories/`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setCategories(d.results || d || []))
      .catch(() => {});

    fetch(`${BASE}suppliers/`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setSuppliers(d.results || d || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadDropdowns();
  }, [loadDropdowns]);

  const load = (key) => {
    const config = ENDPOINTS[key];

    setLoading(true);
    setError("");

    const params = new URLSearchParams();

    if (key === "assets" && search.trim()) {
      params.append("q", search.trim());
    }

    const query = params.toString() ? `?${params.toString()}` : "";

    fetch(`${BASE}${config.url}${query}`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) {
          const detail = await response.json().catch(() => null);
          throw new Error(detail?.detail || detail?.message || `Unable to load ${key} (${response.status}).`);
        }
        return response.json();
      })
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
  };

  const switchTab = (key) => {
    setTab(key);

    if (data[key] === undefined) {
      load(key);
    }
  };

  const rows = data[tab] || [];

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    setFormValidationErrors((prev) => ({ ...prev, [name]: "" }));
  };

  const closeForm = () => {
    setShowForm(false);
    setEditing(null);
    setForm(EMPTY_ASSET_FORM);
  };

  const openAddAsset = () => {
    setEditing(null);
    setForm(EMPTY_ASSET_FORM);
    setShowForm(true);
  };

  const openEditAsset = (asset) => {
    setEditing(asset);
    setForm({
      name: asset.name || "",
      campus: asset.campus ?? "",
      code: asset.code || "",
      category: asset.category ?? "",
      supplier: asset.supplier ?? "",
      quantity: asset.quantity ?? 1,
      unit: asset.unit || "pcs",
      unit_cost: asset.unit_cost ?? "",
      purchase_date: asset.purchase_date || "",
      location: asset.location || "",
      status: asset.status || "in_stock",
      notes: asset.notes || "",
    });
    setShowForm(true);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const quantity = Number(form.quantity);
    const unitCost = Number(form.unit_cost);
    const errors = {};
    if (form.quantity === "" || !Number.isInteger(quantity) || quantity < 0) {
      errors.quantity = "Enter a whole quantity of zero or more.";
    }
    if (form.unit_cost === "" || !Number.isFinite(unitCost) || unitCost < 0) {
      errors.unit_cost = "Enter a unit cost of zero or more.";
    }
    setFormValidationErrors(errors);
    if (Object.keys(errors).length) return;

    setSaving(true);

    const payload = {
      name: form.name,
      campus: form.campus || null,
      code: form.code,
      category: form.category || null,
      supplier: form.supplier || null,
      quantity,
      unit: form.unit,
      unit_cost: form.unit_cost,
      purchase_date: form.purchase_date || null,
      location: form.location,
      status: form.status,
      notes: form.notes,
    };

    try {
      const isEditing = Boolean(editing);
      const url = isEditing ? `${BASE}assets/${editing.id}/` : `${BASE}assets/`;

      await apiFetch(url, {
        method: isEditing ? "PATCH" : "POST",
        headers: jsonHeaders(),
        body: JSON.stringify(payload),
      }, `Unable to ${isEditing ? "update" : "create"} asset.`);

      closeForm();
      setMessage(isEditing ? "Asset updated successfully." : "Asset created successfully.");
      load("assets");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteAsset = async (asset) => {
    if (!window.confirm(`Delete asset "${asset.name}"? This cannot be undone.`)) return;

    setError("");

    try {
      await apiFetch(`${BASE}assets/${asset.id}/`, {
        method: "DELETE",
        headers: jsonHeaders(),
      }, "Unable to delete asset.");

      setMessage("Asset deleted successfully.");
      load("assets");
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Inventory"
        title="Inventory"
        subtitle="Track school assets, suppliers, and maintenance records."
        action={
          <button type="button" className="primary-button" onClick={openAddAsset}>
            <Plus size={15} /> Add Asset
          </button>
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

        {tab === "assets" && (
          <div className="filter-row">
            <div className="filter-search">
              <Search size={18} />

              <input
                type="text"
                placeholder="Search assets by name..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>

            <button type="button" className="primary-button" onClick={() => load("assets")}>
              Search
            </button>
          </div>
        )}

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
                  {tab === "assets" && (
                    <tr>
                      <th>NAME</th>
                      <th>CODE</th>
                      <th>CATEGORY</th>
                      <th>SUPPLIER</th>
                      <th>QUANTITY</th>
                      <th>UNIT COST</th>
                      <th>TOTAL VALUE</th>
                      <th>LOCATION</th>
                      <th>STATUS</th>
                      <th>ACTIONS</th>
                    </tr>
                  )}

                  {tab === "categories" && (
                    <tr>
                      <th>NAME</th>
                      <th>DESCRIPTION</th>
                    </tr>
                  )}

                  {tab === "suppliers" && (
                    <tr>
                      <th>NAME</th>
                      <th>CONTACT PERSON</th>
                      <th>PHONE</th>
                      <th>EMAIL</th>
                      <th>ADDRESS</th>
                    </tr>
                  )}

                  {tab === "maintenance" && (
                    <tr>
                      <th>ASSET</th>
                      <th>DATE</th>
                      <th>COST</th>
                      <th>PERFORMED BY</th>
                      <th>STATUS</th>
                      <th>DESCRIPTION</th>
                    </tr>
                  )}
                </thead>

                <tbody>
                  {tab === "assets" &&
                    rows.map((asset) => (
                      <tr key={asset.id}>
                        <td>
                          <strong>{asset.name}</strong>
                        </td>

                        <td>{asset.code || "\u2014"}</td>

                        <td>{asset.category_name || "\u2014"}</td>

                        <td>{asset.supplier_name || "\u2014"}</td>

                        <td>{asset.quantity ?? 0}</td>

                        <td>{formatCurrency(asset.unit_cost)}</td>

                        <td>
                          <strong>{formatCurrency(asset.total_value)}</strong>
                        </td>

                        <td>{asset.location || "\u2014"}</td>

                        <td>
                          <span className={`status-badge ${asset.status === "in_use" ? "active" : asset.status === "retired" || asset.status === "expired" ? "inactive" : "info"}`}>
                            {asset.status_display}
                          </span>
                        </td>

                        <td>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => openEditAsset(asset)}
                          >
                            <Pencil size={13} />
                            Edit
                          </button>
                          <button
                            type="button"
                            className="table-action danger"
                            onClick={() => handleDeleteAsset(asset)}
                          >
                            <Trash2 size={13} />
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}

                  {tab === "categories" &&
                    rows.map((category) => (
                      <tr key={category.id}>
                        <td>
                          <strong>{category.name}</strong>
                        </td>

                        <td>{category.description || "\u2014"}</td>
                      </tr>
                    ))}

                  {tab === "suppliers" &&
                    rows.map((supplier) => (
                      <tr key={supplier.id}>
                        <td>
                          <strong>{supplier.name}</strong>
                        </td>

                        <td>{supplier.contact_person || "\u2014"}</td>

                        <td>{supplier.phone || "\u2014"}</td>

                        <td>{supplier.email || "\u2014"}</td>

                        <td>{supplier.address || "\u2014"}</td>
                      </tr>
                    ))}

                  {tab === "maintenance" &&
                    rows.map((record) => (
                      <tr key={record.id}>
                        <td>
                          <strong>{record.asset_name || "\u2014"}</strong>
                        </td>

                        <td>{formatDate(record.date)}</td>

                        <td>{formatCurrency(record.cost)}</td>

                        <td>{record.performed_by || "\u2014"}</td>

                        <td>
                          <span className={`status-badge ${record.status === "completed" ? "active" : record.status === "scheduled" ? "info" : "warn"}`}>
                            {record.status ? record.status.replace("_", " ") : "\u2014"}
                          </span>
                        </td>

                        <td>{record.description || "\u2014"}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </StateArea>
      </div>

      {showForm && (
        <div
          className="modal-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeForm();
          }}
        >
          <div className="teacher-modal">
            <div className="modal-header">
              <div>
                <h3>{editing ? "Edit Asset" : "Add Asset"}</h3>
                <p>{editing ? "Update the asset details." : "Add a new asset to inventory."}</p>
              </div>
              <button className="modal-close" onClick={closeForm} disabled={saving}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSubmit} noValidate>
              <div className="form-section">
                <h4>Asset Details</h4>
                <div className="form-grid">
                  <label className="form-span">
                    Name
                    <input name="name" value={form.name} onChange={handleChange} required />
                  </label>

                  <label>
                    Campus
                    <select name="campus" value={form.campus} onChange={handleChange}>
                      <option value="">No campus</option>
                      {campuses.map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Code
                    <input name="code" value={form.code} onChange={handleChange} placeholder="Auto-generated if empty" />
                  </label>

                  <label>
                    Category
                    <select name="category" value={form.category} onChange={handleChange}>
                      <option value="">No category</option>
                      {categories.map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Supplier
                    <select name="supplier" value={form.supplier} onChange={handleChange}>
                      <option value="">No supplier</option>
                      {suppliers.map((s) => (
                        <option key={s.id} value={s.id}>{s.name}</option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Quantity
                    <input type="number" name="quantity" value={form.quantity} onChange={handleChange} min="0" step="1" required aria-invalid={Boolean(formValidationErrors.quantity)} />
                    {formValidationErrors.quantity && <span role="alert" className="field-error">{formValidationErrors.quantity}</span>}
                  </label>

                  <label>
                    Unit
                    <input name="unit" value={form.unit} onChange={handleChange} />
                  </label>

                  <label>
                    Unit Cost
                    <input type="number" name="unit_cost" value={form.unit_cost} onChange={handleChange} min="0" step="0.01" required aria-invalid={Boolean(formValidationErrors.unit_cost)} />
                    {formValidationErrors.unit_cost && <span role="alert" className="field-error">{formValidationErrors.unit_cost}</span>}
                  </label>

                  <label>
                    Purchase Date
                    <input type="date" name="purchase_date" value={form.purchase_date} onChange={handleChange} />
                  </label>

                  <label>
                    Location
                    <input name="location" value={form.location} onChange={handleChange} />
                  </label>

                  <label>
                    Status
                    <select name="status" value={form.status} onChange={handleChange}>
                      {ASSET_STATUS_CHOICES.map((s) => (
                        <option key={s.value} value={s.value}>{s.label}</option>
                      ))}
                    </select>
                  </label>

                  <label className="form-span">
                    Notes
                    <textarea name="notes" value={form.notes} onChange={handleChange} rows="3" />
                  </label>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="secondary-button" onClick={closeForm} disabled={saving}>
                  Cancel
                </button>
                <button type="submit" className="primary-button" disabled={saving}>
                  <Plus size={17} />
                  {saving ? "Saving..." : editing ? "Save Changes" : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
