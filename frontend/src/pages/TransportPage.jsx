import { useState, useEffect, useCallback, useRef } from "react";
import { Bus, Car, MapPin, UsersRound, Plus, Pencil, Trash2, X, Satellite, RefreshCw, Truck } from "lucide-react";
import { PageHeader, PanelHeader, StateArea, EmptyState, StatusBadge } from "./ui";
import { formatDate } from "./format";
import { apiFetch, jsonHeaders } from "../api";

const BASE = "/api/transport/";
const CAMPUSES_URL = "/api/schools/campuses/";

const ENDPOINTS = {
  vehicles: { url: "vehicles/", icon: Car, title: "Vehicles" },
  drivers: { url: "drivers/", icon: UsersRound, title: "Drivers" },
  routes: { url: "routes/", icon: MapPin, title: "Routes" },
  assignments: { url: "assignments/", icon: Bus, title: "Assignments" },
  live: { url: "gps/live/", icon: Satellite, title: "Live Tracking" },
};

const VEHICLE_STATUS_CHOICES = [
  { value: "operational", label: "Operational" },
  { value: "maintenance", label: "In Maintenance" },
  { value: "out_of_service", label: "Out of Service" },
];

const EMPTY_VEHICLE_FORM = {
  plate_number: "",
  campus: "",
  model: "",
  capacity: 30,
  status: "operational",
  notes: "",
};

const LiveTrackingMap = ({
  vehicles,
  autoRefresh,
  setAutoRefresh,
  refreshInterval,
  setRefreshInterval,
  onRefresh,
}) => {
  const mapContainerRef = useRef(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => setNow(Date.now()), refreshInterval);
    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval]);

  // Simple map using a static image with overlay markers (no Leaflet dependency)
  // In production, you would use Leaflet or Mapbox GL JS
  const renderMarkers = () => {
    if (!vehicles.length) return null;

    return vehicles.map((v) => {
      if (v.lat == null || v.lng == null) return null;

      // Simple coordinate to pixel conversion for a static map container
      // In production, use Leaflet with proper coordinate projection
      const containerWidth = 800;
      const containerHeight = 500;
      // Approximate conversion - in production use proper projection
      const lngRange = 0.5; // degrees
      const latRange = 0.4;
      const centerLng = 74.3; // Example: Lahore center
      const centerLat = 31.5;

      const x = ((v.lng - (centerLng - lngRange / 2)) / lngRange) * containerWidth;
      const y = ((centerLat + latRange / 2 - v.lat) / latRange) * containerHeight;

      const isRecent = v.last_seen && (Date.now() - new Date(v.last_seen).getTime()) < 60000;

      return (
        <div
          key={v.vehicle}
          className="vehicle-marker"
          style={{
            left: `${Math.max(0, Math.min(100, (x / containerWidth) * 100))}%`,
            top: `${Math.max(0, Math.min(100, (y / containerHeight) * 100))}%`,
          }}
        >
          <div
            className={`marker-pin ${isRecent ? "active" : "stale"}`}
            title={
              `${v.vehicle} (${v.route}) - ${v.speed_kmh || 0} km/h\n` +
              `Last seen: ${v.last_seen ? new Date(v.last_seen).toLocaleTimeString() : "Unknown"}`
            }
          >
            <Truck size={16} />
            {isRecent && <span className="pulse-ring" />}
          </div>
          <div className="marker-label">
            <strong>{v.vehicle}</strong>
            <span>{v.route}</span>
            <span>{v.campus}</span>
            {v.speed_kmh && <span>{v.speed_kmh} km/h</span>}
          </div>
        </div>
      );
    });
  };

  return (
    <div className="live-tracking-map">
      <div className="live-map-header">
        <div className="live-controls">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            <span>Auto-refresh ({refreshInterval / 1000}s)</span>
          </label>
          <select
            value={refreshInterval}
            onChange={(e) => setRefreshInterval(Number(e.target.value))}
            style={{ marginLeft: 16 }}
          >
            <option value={5000}>5s</option>
            <option value={10000}>10s</option>
            <option value={30000}>30s</option>
            <option value={60000}>60s</option>
          </select>
          <button
            className="secondary-button"
            onClick={onRefresh}
            disabled={false}
          >
            <RefreshCw size={14} /> Refresh Now
          </button>
        </div>
        <div className="live-legend">
          <span className="legend-item active"><span className="dot"></span> Active (&lt; 1 min)</span>
          <span className="legend-item stale"><span className="dot"></span> Stale (&gt; 1 min)</span>
          <span className="legend-item"><span className="dot empty"></span> No GPS</span>
        </div>
      </div>

      <div className="live-map-container" ref={mapContainerRef}>
        {/* Static map background - in production use Leaflet/Mapbox */}
        <div className="static-map-bg" style={{ backgroundImage: "url('https://tile.openstreetmap.org/13/6432/4096.png')" }}>
          {renderMarkers()}
        </div>

        {vehicles.length === 0 && (
          <div className="no-vehicles">
            <MapPin size={48} />
            <p>No vehicles with GPS data</p>
            <small>Ensure GPS devices are configured and sending pings to /api/transport/gps/ping/</small>
          </div>
        )}
      </div>

      <div className="vehicle-list">
        <h4>Live Vehicle List ({vehicles.length})</h4>
        <div className="vehicle-list-table">
          <div className="list-header">
            <span>Vehicle</span>
            <span>Route</span>
            <span>Campus</span>
            <span>Speed</span>
            <span>Last Seen</span>
            <span>Status</span>
          </div>
{vehicles.map((v) => {
            const hasGps = v.lat != null && v.lng != null;
const isRecent = v.last_seen && (now - new Date(v.last_seen).getTime()) < 60000;
            const rowClass = `list-row${hasGps ? "" : " no-gps"}${isRecent ? " active" : " stale"}`;
            return (
              <div key={v.vehicle} className={rowClass}>
                <span><Truck size={14} /> {v.vehicle}</span>
                <span>{v.route}</span>
                <span>{v.campus}</span>
                <span>{v.speed_kmh ? `${v.speed_kmh} km/h` : "—"}</span>
                <span>{v.last_seen ? new Date(v.last_seen).toLocaleTimeString() : "—"}</span>
                <span>
                  {hasGps && isRecent ? (
                    <span className="status-dot active" title="Active" />
                  ) : (
                    <span className="status-dot stale" title="Stale / No GPS" />
                  )}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default function TransportPage() {
  const [tab, setTab] = useState("vehicles");
  const [data, setData] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(EMPTY_VEHICLE_FORM);

  const [campuses, setCampuses] = useState([]);

  const loadCampuses = useCallback(() => {
    fetch(CAMPUSES_URL, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setCampuses(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadCampuses();
  }, [loadCampuses]);

  const load = (key) => {
    const config = ENDPOINTS[key];

    setLoading(true);
    setError("");

    fetch(`${BASE}${config.url}`, { credentials: "include" })
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

  // Live tracking state
  const [liveVehicles, setLiveVehicles] = useState([]);
  const [liveLoading, setLiveLoading] = useState(false);
  const [liveError, setLiveError] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(10000); // 10 seconds

  // Load live vehicle data from GPS
  const loadLive = useCallback(() => {
    setLiveLoading(true);
    setLiveError("");

    fetch(`${BASE}gps/live/`, { credentials: "include" })
      .then((response) => (response.ok ? response.json() : []))
      .then((json) => {
        setLiveVehicles(Array.isArray(json) ? json : []);
        setLiveLoading(false);
      })
      .catch((err) => {
        setLiveError(err.message);
        setLiveLoading(false);
      });
  }, []);

  // Auto-refresh live data
  useEffect(() => {
    if (tab !== "live") return;
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      loadLive();
    }, refreshInterval);

    loadLive(); // Initial load
    return () => clearInterval(interval);
  }, [tab, autoRefresh, refreshInterval, loadLive]);

  const rows = data[tab] || [];

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const closeForm = () => {
    setShowForm(false);
    setEditing(null);
    setForm(EMPTY_VEHICLE_FORM);
  };

  const openAddVehicle = () => {
    setEditing(null);
    setForm(EMPTY_VEHICLE_FORM);
    setShowForm(true);
  };

  const openEditVehicle = (vehicle) => {
    setEditing(vehicle);
    setForm({
      plate_number: vehicle.plate_number || "",
      campus: vehicle.campus ?? "",
      model: vehicle.model || "",
      capacity: vehicle.capacity ?? 30,
      status: vehicle.status || "operational",
      notes: vehicle.notes || "",
    });
    setShowForm(true);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);

    const payload = {
      plate_number: form.plate_number,
      campus: form.campus || null,
      model: form.model,
      capacity: Number(form.capacity) || 30,
      status: form.status,
      notes: form.notes,
    };

    try {
      const isEditing = Boolean(editing);
      const url = isEditing ? `${BASE}vehicles/${editing.id}/` : `${BASE}vehicles/`;

      await apiFetch(url, {
        method: isEditing ? "PATCH" : "POST",
        headers: jsonHeaders(),
        body: JSON.stringify(payload),
      }, `Unable to ${isEditing ? "update" : "create"} vehicle.`);

      closeForm();
      setMessage(isEditing ? "Vehicle updated successfully." : "Vehicle created successfully.");
      load("vehicles");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteVehicle = async (vehicle) => {
    if (!window.confirm(`Delete vehicle "${vehicle.plate_number}"? This cannot be undone.`)) return;

    setError("");

    try {
      await apiFetch(`${BASE}vehicles/${vehicle.id}/`, {
        method: "DELETE",
        headers: jsonHeaders(),
      }, "Unable to delete vehicle.");

      setMessage("Vehicle deleted successfully.");
      load("vehicles");
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Transport"
        title="Transport"
        subtitle="Manage vehicles, drivers, routes, and student transport assignments."
        action={
          <button type="button" className="primary-button" onClick={openAddVehicle}>
            <Plus size={15} /> Add Vehicle
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

        <StateArea
          loading={tab === "live" ? liveLoading : loading}
          error={tab === "live" ? liveError : error}
          onRetry={() => tab === "live" ? loadLive() : load(tab)}
        >
          {tab === "live" ? (
            <LiveTrackingMap
              vehicles={liveVehicles}
              autoRefresh={autoRefresh}
              setAutoRefresh={setAutoRefresh}
              refreshInterval={refreshInterval}
              setRefreshInterval={setRefreshInterval}
              onRefresh={loadLive}
            />
          ) : rows.length === 0 ? (
            <EmptyState
              icon={ENDPOINTS[tab].icon}
              title={`No ${ENDPOINTS[tab].title.toLowerCase()} found`}
              message="Records will appear here once added."
            />
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  {tab === "vehicles" && (
                    <tr>
                      <th>PLATE NUMBER</th>
                      <th>MODEL</th>
                      <th>CAPACITY</th>
                      <th>STATUS</th>
                      <th>NOTES</th>
                      <th>ACTIONS</th>
                    </tr>
                  )}

                  {tab === "drivers" && (
                    <tr>
                      <th>NAME</th>
                      <th>LICENSE NUMBER</th>
                      <th>PHONE</th>
                      <th>STATUS</th>
                    </tr>
                  )}

                  {tab === "routes" && (
                    <tr>
                      <th>NAME</th>
                      <th>START</th>
                      <th>END</th>
                      <th>VEHICLE</th>
                      <th>DRIVER</th>
                      <th>STOPS</th>
                      <th>STATUS</th>
                    </tr>
                  )}

                  {tab === "assignments" && (
                    <tr>
                      <th>STUDENT</th>
                      <th>ADMISSION NO.</th>
                      <th>ROUTE</th>
                      <th>STOP</th>
                      <th>STATUS</th>
                      <th>ASSIGNED</th>
                    </tr>
                  )}
                </thead>

                <tbody>
                  {tab === "vehicles" &&
                    rows.map((vehicle) => (
                      <tr key={vehicle.id}>
                        <td>
                          <strong>{vehicle.plate_number}</strong>
                        </td>

                        <td>{vehicle.model || "\u2014"}</td>

                        <td>{vehicle.capacity ?? 0}</td>

                        <td>
                          <StatusBadge
                            status={
                              vehicle.status === "operational"
                                ? "active"
                                : vehicle.status
                            }
                            label={vehicle.status_display}
                          />
                        </td>

                        <td>{vehicle.notes || "\u2014"}</td>

                        <td>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => openEditVehicle(vehicle)}
                          >
                            <Pencil size={13} />
                            Edit
                          </button>
                          <button
                            type="button"
                            className="table-action danger"
                            onClick={() => handleDeleteVehicle(vehicle)}
                          >
                            <Trash2 size={13} />
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}

                  {tab === "drivers" &&
                    rows.map((driver) => (
                      <tr key={driver.id}>
                        <td>
                          <strong>{driver.full_name || "\u2014"}</strong>
                        </td>

                        <td>{driver.license_number || "\u2014"}</td>

                        <td>{driver.phone || "\u2014"}</td>

                        <td>
                          <span
                            className={`status-badge ${
                              driver.status ? "active" : "inactive"
                            }`}
                          >
                            {driver.status ? "Active" : "Inactive"}
                          </span>
                        </td>
                      </tr>
                    ))}

                  {tab === "routes" &&
                    rows.map((route) => (
                      <tr key={route.id}>
                        <td>
                          <strong>{route.name}</strong>
                        </td>

                        <td>{route.start_point || "\u2014"}</td>

                        <td>{route.end_point || "\u2014"}</td>

                        <td>{route.vehicle_plate || "\u2014"}</td>

                        <td>{route.driver_name || "\u2014"}</td>

                        <td>{route.stops?.length ?? 0}</td>

                        <td>
                          <span
                            className={`status-badge ${
                              route.status ? "active" : "inactive"
                            }`}
                          >
                            {route.status ? "Active" : "Inactive"}
                          </span>
                        </td>
                      </tr>
                    ))}

                  {tab === "assignments" &&
                    rows.map((assignment) => (
                      <tr key={assignment.id}>
                        <td>
                          <strong>{assignment.student_name}</strong>
                        </td>

                        <td>{assignment.admission_number || "\u2014"}</td>

                        <td>{assignment.route_name || "\u2014"}</td>

                        <td>{assignment.stop_name || "\u2014"}</td>

                        <td>
                          <StatusBadge
                            status={assignment.status}
                            label={
                              assignment.status
                                ? assignment.status.charAt(0).toUpperCase() +
                                  assignment.status.slice(1)
                                : "\u2014"
                            }
                          />
                        </td>

                        <td>{formatDate(assignment.created_at)}</td>
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
                <h3>{editing ? "Edit Vehicle" : "Add Vehicle"}</h3>
                <p>{editing ? "Update the vehicle details." : "Add a new vehicle to the fleet."}</p>
              </div>
              <button className="modal-close" onClick={closeForm} disabled={saving}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSubmit}>
              <div className="form-section">
                <h4>Vehicle Details</h4>
                <div className="form-grid">
                  <label>
                    Plate Number
                    <input name="plate_number" value={form.plate_number} onChange={handleChange} required />
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
                    Model
                    <input name="model" value={form.model} onChange={handleChange} required />
                  </label>

                  <label>
                    Capacity
                    <input type="number" name="capacity" value={form.capacity} onChange={handleChange} min="1" required />
                  </label>

                  <label>
                    Status
                    <select name="status" value={form.status} onChange={handleChange}>
                      {VEHICLE_STATUS_CHOICES.map((s) => (
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
