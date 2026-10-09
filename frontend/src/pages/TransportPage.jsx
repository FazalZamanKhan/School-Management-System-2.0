import { useState, useEffect, useCallback, useRef } from "react";
import {
  Bus,
  Car,
  MapPin,
  UsersRound,
  Plus,
  Pencil,
  Trash2,
  X,
  Satellite,
  RefreshCw,
  Truck,
  Search,
  Filter,
} from "lucide-react";
import { PageHeader, PanelHeader, StateArea, EmptyState, StatusBadge } from "./ui";
import { formatDate } from "./format";
import { apiFetch, jsonHeaders } from "../api";

const BASE = "/api/transport/";
const CAMPUSES_URL = "/api/schools/campuses/";
const STUDENTS_URL = "/api/students/?page_size=500";

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

const ASSIGNMENT_STATUS_CHOICES = [
  { value: "active", label: "Active" },
  { value: "suspended", label: "Suspended" },
  { value: "ended", label: "Ended" },
];

const EMPTY_VEHICLE_FORM = {
  plate_number: "",
  campus: "",
  model: "",
  capacity: 30,
  status: "operational",
  notes: "",
};

const EMPTY_ROUTE_FORM = {
  name: "",
  description: "",
  campus: "",
  vehicle: "",
  driver: "",
  start_point: "",
  end_point: "",
  status: true,
};

const EMPTY_ASSIGNMENT_FORM = {
  student: "",
  route: "",
  stop: "",
  status: "active",
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

  const renderMarkers = () => {
    if (!vehicles.length) return null;

    return vehicles.map((v) => {
      if (v.lat == null || v.lng == null) return null;

      const containerWidth = 800;
      const containerHeight = 500;
      const lngRange = 0.5;
      const latRange = 0.4;
      const centerLng = 74.3;
      const centerLat = 31.5;

      const x = ((v.lng - (centerLng - lngRange / 2)) / lngRange) * containerWidth;
      const y = ((centerLat + latRange / 2 - v.lat) / latRange) * containerHeight;

      const isRecent = v.last_seen && Date.now() - new Date(v.last_seen).getTime() < 60000;

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
          <button className="secondary-button" onClick={onRefresh} disabled={false}>
            <RefreshCw size={14} /> Refresh Now
          </button>
        </div>
        <div className="live-legend">
          <span className="legend-item active">
            <span className="dot"></span> Active (&lt; 1 min)
          </span>
          <span className="legend-item stale">
            <span className="dot"></span> Stale (&gt; 1 min)
          </span>
          <span className="legend-item">
            <span className="dot empty"></span> No GPS
          </span>
        </div>
      </div>

      <div className="live-map-container" ref={mapContainerRef}>
        <div
          className="static-map-bg"
          style={{ backgroundImage: "url('https://tile.openstreetmap.org/13/6432/4096.png')" }}
        >
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
            const isRecent = v.last_seen && now - new Date(v.last_seen).getTime() < 60000;
            const rowClass = `list-row${hasGps ? "" : " no-gps"}${isRecent ? " active" : " stale"}`;
            return (
              <div key={v.vehicle} className={rowClass}>
                <span>
                  <Truck size={14} /> {v.vehicle}
                </span>
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

  // Modals state
  const [modalType, setModalType] = useState(null); // 'vehicle' | 'route' | 'assignment' | null
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);

  // Forms
  const [vehicleForm, setVehicleForm] = useState(EMPTY_VEHICLE_FORM);
  const [routeForm, setRouteForm] = useState(EMPTY_ROUTE_FORM);
  const [assignForm, setAssignForm] = useState(EMPTY_ASSIGNMENT_FORM);

  // Dropdown options
  const [campuses, setCampuses] = useState([]);
  const [allVehicles, setAllVehicles] = useState([]);
  const [allDrivers, setAllDrivers] = useState([]);
  const [allRoutes, setAllRoutes] = useState([]);
  const [allStudents, setAllStudents] = useState([]);
  const [selectedRouteStops, setSelectedRouteStops] = useState([]);

  // Search & Filters
  const [routeSearch, setRouteSearch] = useState("");
  const [routeCampus, setRouteCampus] = useState("");
  const [routeStatus, setRouteStatus] = useState("");

  const [assignSearch, setAssignSearch] = useState("");
  const [assignRoute, setAssignRoute] = useState("");
  const [assignStatus, setAssignStatus] = useState("");

  const loadDropdowns = useCallback(() => {
    fetch(CAMPUSES_URL, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setCampuses(Array.isArray(d) ? d : []))
      .catch(() => {});

    fetch(`${BASE}vehicles/`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : { results: [] }))
      .then((d) => setAllVehicles(d.results || d || []))
      .catch(() => {});

    fetch(`${BASE}drivers/`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : { results: [] }))
      .then((d) => setAllDrivers(d.results || d || []))
      .catch(() => {});

    fetch(`${BASE}routes/`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : { results: [] }))
      .then((d) => setAllRoutes(d.results || d || []))
      .catch(() => {});

    fetch(STUDENTS_URL, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : { results: [] }))
      .then((d) => setAllStudents(d.results || d || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadDropdowns();
  }, [loadDropdowns]);

  const load = useCallback(
    (key) => {
      const config = ENDPOINTS[key];
      if (!config) return;

      setLoading(true);
      setError("");

      const params = new URLSearchParams();
      if (key === "routes") {
        if (routeSearch.trim()) params.append("search", routeSearch.trim());
        if (routeCampus) params.append("campus", routeCampus);
        if (routeStatus !== "") params.append("status", routeStatus);
      } else if (key === "assignments") {
        if (assignSearch.trim()) params.append("search", assignSearch.trim());
        if (assignRoute) params.append("route", assignRoute);
        if (assignStatus) params.append("status", assignStatus);
      }

      const queryString = params.toString() ? `?${params.toString()}` : "";

      fetch(`${BASE}${config.url}${queryString}`, { credentials: "include" })
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
    [routeSearch, routeCampus, routeStatus, assignSearch, assignRoute, assignStatus]
  );

  useEffect(() => {
    if (tab !== "live") {
      load(tab);
    }
  }, [tab, load]);

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
  const [refreshInterval, setRefreshInterval] = useState(10000);

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

  useEffect(() => {
    if (tab !== "live") return;
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      loadLive();
    }, refreshInterval);

    loadLive();
    return () => clearInterval(interval);
  }, [tab, autoRefresh, refreshInterval, loadLive]);

  const rows = data[tab] || [];

  const closeModal = () => {
    setModalType(null);
    setEditing(null);
    setVehicleForm(EMPTY_VEHICLE_FORM);
    setRouteForm(EMPTY_ROUTE_FORM);
    setAssignForm(EMPTY_ASSIGNMENT_FORM);
    setSelectedRouteStops([]);
  };

  // Route Form Openers
  const openAddRoute = () => {
    setEditing(null);
    setRouteForm(EMPTY_ROUTE_FORM);
    setModalType("route");
  };

  const openEditRoute = (route) => {
    setEditing(route);
    setRouteForm({
      name: route.name || "",
      description: route.description || "",
      campus: route.campus ?? "",
      vehicle: route.vehicle ?? "",
      driver: route.driver ?? "",
      start_point: route.start_point || "",
      end_point: route.end_point || "",
      status: route.status !== undefined ? route.status : true,
    });
    setModalType("route");
  };

  // Vehicle Form Openers
  const openAddVehicle = () => {
    setEditing(null);
    setVehicleForm(EMPTY_VEHICLE_FORM);
    setModalType("vehicle");
  };

  const openEditVehicle = (vehicle) => {
    setEditing(vehicle);
    setVehicleForm({
      plate_number: vehicle.plate_number || "",
      campus: vehicle.campus ?? "",
      model: vehicle.model || "",
      capacity: vehicle.capacity ?? 30,
      status: vehicle.status || "operational",
      notes: vehicle.notes || "",
    });
    setModalType("vehicle");
  };

  // Assignment Form Openers
  const openAddAssignment = () => {
    setEditing(null);
    setAssignForm(EMPTY_ASSIGNMENT_FORM);
    setSelectedRouteStops([]);
    setModalType("assignment");
  };

  const openEditAssignment = (assignment) => {
    setEditing(assignment);
    const matchedRoute = allRoutes.find((r) => r.id === assignment.route);
    setSelectedRouteStops(matchedRoute?.stops || []);
    setAssignForm({
      student: assignment.student ?? "",
      route: assignment.route ?? "",
      stop: assignment.stop ?? "",
      status: assignment.status || "active",
    });
    setModalType("assignment");
  };

  const handleRouteChange = (e) => {
    const routeId = Number(e.target.value);
    setAssignForm((prev) => ({ ...prev, route: e.target.value, stop: "" }));
    const matched = allRoutes.find((r) => r.id === routeId);
    setSelectedRouteStops(matched?.stops || []);
  };

  // Submit Handlers
  const handleVehicleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);

    const payload = {
      plate_number: vehicleForm.plate_number,
      campus: vehicleForm.campus || null,
      model: vehicleForm.model,
      capacity: Number(vehicleForm.capacity) || 30,
      status: vehicleForm.status,
      notes: vehicleForm.notes,
    };

    try {
      const isEditing = Boolean(editing);
      const url = isEditing ? `${BASE}vehicles/${editing.id}/` : `${BASE}vehicles/`;

      await apiFetch(
        url,
        {
          method: isEditing ? "PATCH" : "POST",
          headers: jsonHeaders(),
          body: JSON.stringify(payload),
        },
        `Unable to ${isEditing ? "update" : "create"} vehicle.`
      );

      closeModal();
      setMessage(isEditing ? "Vehicle updated successfully." : "Vehicle created successfully.");
      load("vehicles");
      loadDropdowns();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleRouteSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);

    const payload = {
      name: routeForm.name,
      description: routeForm.description,
      campus: routeForm.campus || null,
      vehicle: routeForm.vehicle || null,
      driver: routeForm.driver || null,
      start_point: routeForm.start_point,
      end_point: routeForm.end_point,
      status: routeForm.status === "true" || routeForm.status === true,
    };

    try {
      const isEditing = Boolean(editing);
      const url = isEditing ? `${BASE}routes/${editing.id}/` : `${BASE}routes/`;

      await apiFetch(
        url,
        {
          method: isEditing ? "PATCH" : "POST",
          headers: jsonHeaders(),
          body: JSON.stringify(payload),
        },
        `Unable to ${isEditing ? "update" : "create"} route.`
      );

      closeModal();
      setMessage(isEditing ? "Route updated successfully." : "Route created successfully.");
      load("routes");
      loadDropdowns();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleAssignmentSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);

    const payload = {
      student: Number(assignForm.student),
      route: Number(assignForm.route),
      stop: assignForm.stop ? Number(assignForm.stop) : null,
      status: assignForm.status,
    };

    try {
      const isEditing = Boolean(editing);
      const url = isEditing ? `${BASE}assignments/${editing.id}/` : `${BASE}assignments/`;

      await apiFetch(
        url,
        {
          method: isEditing ? "PATCH" : "POST",
          headers: jsonHeaders(),
          body: JSON.stringify(payload),
        },
        `Unable to ${isEditing ? "update" : "create"} assignment.`
      );

      closeModal();
      setMessage(isEditing ? "Assignment updated successfully." : "Assignment created successfully.");
      load("assignments");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Delete Handlers
  const handleDeleteVehicle = async (vehicle) => {
    if (!window.confirm(`Delete vehicle "${vehicle.plate_number}"? This cannot be undone.`)) return;
    setError("");

    try {
      await apiFetch(
        `${BASE}vehicles/${vehicle.id}/`,
        {
          method: "DELETE",
          headers: jsonHeaders(),
        },
        "Unable to delete vehicle."
      );
      setMessage("Vehicle deleted successfully.");
      load("vehicles");
      loadDropdowns();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeleteRoute = async (route) => {
    if (!window.confirm(`Delete route "${route.name}"? This cannot be undone.`)) return;
    setError("");

    try {
      await apiFetch(
        `${BASE}routes/${route.id}/`,
        {
          method: "DELETE",
          headers: jsonHeaders(),
        },
        "Unable to delete route."
      );
      setMessage("Route deleted successfully.");
      load("routes");
      loadDropdowns();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeleteAssignment = async (assignment) => {
    if (!window.confirm(`Remove transport assignment for "${assignment.student_name}"?`)) return;
    setError("");

    try {
      await apiFetch(
        `${BASE}assignments/${assignment.id}/`,
        {
          method: "DELETE",
          headers: jsonHeaders(),
        },
        "Unable to delete assignment."
      );
      setMessage("Assignment removed successfully.");
      load("assignments");
    } catch (err) {
      setError(err.message);
    }
  };

  const renderPrimaryAction = () => {
    if (tab === "vehicles") {
      return (
        <button type="button" className="primary-button" onClick={openAddVehicle}>
          <Plus size={15} /> Add Vehicle
        </button>
      );
    }
    if (tab === "routes") {
      return (
        <button type="button" className="primary-button" onClick={openAddRoute}>
          <Plus size={15} /> Add Route
        </button>
      );
    }
    if (tab === "assignments") {
      return (
        <button type="button" className="primary-button" onClick={openAddAssignment}>
          <Plus size={15} /> Add Assignment
        </button>
      );
    }
    return null;
  };

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Transport"
        title="Transport"
        subtitle="Manage vehicles, drivers, routes, and student transport assignments."
        action={renderPrimaryAction()}
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
        {/* Filters for Routes */}
        {tab === "routes" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              load("routes");
            }}
            className="filter-row"
            style={{ marginBottom: 16 }}
          >
            <div className="filter-search">
              <Search size={16} />
              <input
                value={routeSearch}
                onChange={(e) => setRouteSearch(e.target.value)}
                placeholder="Search route name or points..."
              />
            </div>
            <select value={routeCampus} onChange={(e) => setRouteCampus(e.target.value)}>
              <option value="">All Campuses</option>
              {campuses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <select value={routeStatus} onChange={(e) => setRouteStatus(e.target.value)}>
              <option value="">All Statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
            <button type="submit" className="secondary-button">
              <Filter size={14} /> Filter
            </button>
            {(routeSearch || routeCampus || routeStatus) && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  setRouteSearch("");
                  setRouteCampus("");
                  setRouteStatus("");
                  fetch(`${BASE}routes/`, { credentials: "include" })
                    .then((r) => r.json())
                    .then((json) => setData((prev) => ({ ...prev, routes: json.results || json })));
                }}
              >
                Clear
              </button>
            )}
          </form>
        )}

        {/* Filters for Assignments */}
        {tab === "assignments" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              load("assignments");
            }}
            className="filter-row"
            style={{ marginBottom: 16 }}
          >
            <div className="filter-search">
              <Search size={16} />
              <input
                value={assignSearch}
                onChange={(e) => setAssignSearch(e.target.value)}
                placeholder="Search student or route..."
              />
            </div>
            <select value={assignRoute} onChange={(e) => setAssignRoute(e.target.value)}>
              <option value="">All Routes</option>
              {allRoutes.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
            <select value={assignStatus} onChange={(e) => setAssignStatus(e.target.value)}>
              <option value="">All Statuses</option>
              {ASSIGNMENT_STATUS_CHOICES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
            <button type="submit" className="secondary-button">
              <Filter size={14} /> Filter
            </button>
            {(assignSearch || assignRoute || assignStatus) && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  setAssignSearch("");
                  setAssignRoute("");
                  setAssignStatus("");
                  fetch(`${BASE}assignments/`, { credentials: "include" })
                    .then((r) => r.json())
                    .then((json) => setData((prev) => ({ ...prev, assignments: json.results || json })));
                }}
              >
                Clear
              </button>
            )}
          </form>
        )}

        <PanelHeader
          title={ENDPOINTS[tab].title}
          subtitle="records found"
          count={rows.length || null}
        />

        <StateArea
          loading={tab === "live" ? liveLoading : loading}
          error={tab === "live" ? liveError : error}
          onRetry={() => (tab === "live" ? loadLive() : load(tab))}
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
                      <th>ACTIONS</th>
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
                      <th>ACTIONS</th>
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
                            status={vehicle.status === "operational" ? "active" : vehicle.status}
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
                            className={`status-badge ${driver.status ? "active" : "inactive"}`}
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
                          {route.description && (
                            <span className="table-sub">{route.description}</span>
                          )}
                        </td>
                        <td>{route.start_point || "\u2014"}</td>
                        <td>{route.end_point || "\u2014"}</td>
                        <td>{route.vehicle_plate || "\u2014"}</td>
                        <td>{route.driver_name || "\u2014"}</td>
                        <td>{route.stops?.length ?? 0}</td>
                        <td>
                          <span
                            className={`status-badge ${route.status ? "active" : "inactive"}`}
                          >
                            {route.status ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => openEditRoute(route)}
                          >
                            <Pencil size={13} />
                            Edit
                          </button>
                          <button
                            type="button"
                            className="table-action danger"
                            onClick={() => handleDeleteRoute(route)}
                          >
                            <Trash2 size={13} />
                            Delete
                          </button>
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
                        <td>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => openEditAssignment(assignment)}
                          >
                            <Pencil size={13} />
                            Edit
                          </button>
                          <button
                            type="button"
                            className="table-action danger"
                            onClick={() => handleDeleteAssignment(assignment)}
                          >
                            <Trash2 size={13} />
                            Delete
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

      {/* Vehicle Modal */}
      {modalType === "vehicle" && (
        <div
          className="modal-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeModal();
          }}
        >
          <div className="teacher-modal">
            <div className="modal-header">
              <div>
                <h3>{editing ? "Edit Vehicle" : "Add Vehicle"}</h3>
                <p>{editing ? "Update the vehicle details." : "Add a new vehicle to the fleet."}</p>
              </div>
              <button className="modal-close" onClick={closeModal} disabled={saving}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleVehicleSubmit}>
              <div className="form-section">
                <h4>Vehicle Details</h4>
                <div className="form-grid">
                  <label>
                    Plate Number *
                    <input
                      name="plate_number"
                      value={vehicleForm.plate_number}
                      onChange={(e) =>
                        setVehicleForm((prev) => ({ ...prev, plate_number: e.target.value }))
                      }
                      required
                    />
                  </label>

                  <label>
                    Campus
                    <select
                      name="campus"
                      value={vehicleForm.campus}
                      onChange={(e) =>
                        setVehicleForm((prev) => ({ ...prev, campus: e.target.value }))
                      }
                    >
                      <option value="">No campus</option>
                      {campuses.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Model *
                    <input
                      name="model"
                      value={vehicleForm.model}
                      onChange={(e) =>
                        setVehicleForm((prev) => ({ ...prev, model: e.target.value }))
                      }
                      required
                    />
                  </label>

                  <label>
                    Capacity *
                    <input
                      type="number"
                      name="capacity"
                      value={vehicleForm.capacity}
                      onChange={(e) =>
                        setVehicleForm((prev) => ({ ...prev, capacity: e.target.value }))
                      }
                      min="1"
                      required
                    />
                  </label>

                  <label>
                    Status
                    <select
                      name="status"
                      value={vehicleForm.status}
                      onChange={(e) =>
                        setVehicleForm((prev) => ({ ...prev, status: e.target.value }))
                      }
                    >
                      {VEHICLE_STATUS_CHOICES.map((s) => (
                        <option key={s.value} value={s.value}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="form-span">
                    Notes
                    <textarea
                      name="notes"
                      value={vehicleForm.notes}
                      onChange={(e) =>
                        setVehicleForm((prev) => ({ ...prev, notes: e.target.value }))
                      }
                      rows="3"
                    />
                  </label>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="secondary-button" onClick={closeModal} disabled={saving}>
                  Cancel
                </button>
                <button type="submit" className="primary-button" disabled={saving}>
                  <Plus size={17} />
                  {saving ? "Saving..." : editing ? "Save Changes" : "Create Vehicle"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Route Modal */}
      {modalType === "route" && (
        <div
          className="modal-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeModal();
          }}
        >
          <div className="teacher-modal">
            <div className="modal-header">
              <div>
                <h3>{editing ? "Edit Route" : "Add Route"}</h3>
                <p>{editing ? "Update transport route." : "Create a new transport route."}</p>
              </div>
              <button className="modal-close" onClick={closeModal} disabled={saving}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleRouteSubmit}>
              <div className="form-section">
                <h4>Route Details</h4>
                <div className="form-grid">
                  <label>
                    Route Name *
                    <input
                      name="name"
                      value={routeForm.name}
                      onChange={(e) =>
                        setRouteForm((prev) => ({ ...prev, name: e.target.value }))
                      }
                      placeholder="e.g. Route A - Main Campus"
                      required
                    />
                  </label>

                  <label>
                    Campus
                    <select
                      name="campus"
                      value={routeForm.campus}
                      onChange={(e) =>
                        setRouteForm((prev) => ({ ...prev, campus: e.target.value }))
                      }
                    >
                      <option value="">No campus (School-wide)</option>
                      {campuses.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Assigned Vehicle
                    <select
                      name="vehicle"
                      value={routeForm.vehicle}
                      onChange={(e) =>
                        setRouteForm((prev) => ({ ...prev, vehicle: e.target.value }))
                      }
                    >
                      <option value="">Select vehicle</option>
                      {allVehicles.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.plate_number} ({v.model})
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Assigned Driver
                    <select
                      name="driver"
                      value={routeForm.driver}
                      onChange={(e) =>
                        setRouteForm((prev) => ({ ...prev, driver: e.target.value }))
                      }
                    >
                      <option value="">Select driver</option>
                      {allDrivers.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.full_name || `${d.first_name} ${d.last_name}`}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Start Point
                    <input
                      name="start_point"
                      value={routeForm.start_point}
                      onChange={(e) =>
                        setRouteForm((prev) => ({ ...prev, start_point: e.target.value }))
                      }
                      placeholder="e.g. Central Station"
                    />
                  </label>

                  <label>
                    End Point
                    <input
                      name="end_point"
                      value={routeForm.end_point}
                      onChange={(e) =>
                        setRouteForm((prev) => ({ ...prev, end_point: e.target.value }))
                      }
                      placeholder="e.g. Campus Gate 1"
                    />
                  </label>

                  <label>
                    Status
                    <select
                      name="status"
                      value={String(routeForm.status)}
                      onChange={(e) =>
                        setRouteForm((prev) => ({ ...prev, status: e.target.value === "true" }))
                      }
                    >
                      <option value="true">Active</option>
                      <option value="false">Inactive</option>
                    </select>
                  </label>

                  <label className="form-span">
                    Description
                    <textarea
                      name="description"
                      value={routeForm.description}
                      onChange={(e) =>
                        setRouteForm((prev) => ({ ...prev, description: e.target.value }))
                      }
                      rows="2"
                      placeholder="Optional route description or notes"
                    />
                  </label>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="secondary-button" onClick={closeModal} disabled={saving}>
                  Cancel
                </button>
                <button type="submit" className="primary-button" disabled={saving}>
                  <Plus size={17} />
                  {saving ? "Saving..." : editing ? "Save Changes" : "Create Route"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Assignment Modal */}
      {modalType === "assignment" && (
        <div
          className="modal-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeModal();
          }}
        >
          <div className="teacher-modal">
            <div className="modal-header">
              <div>
                <h3>{editing ? "Edit Assignment" : "Assign Student to Route"}</h3>
                <p>
                  {editing
                    ? "Update student transport assignment."
                    : "Assign a student to a transport route and stop."}
                </p>
              </div>
              <button className="modal-close" onClick={closeModal} disabled={saving}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleAssignmentSubmit}>
              <div className="form-section">
                <h4>Assignment Details</h4>
                <div className="form-grid">
                  <label className="form-span">
                    Student *
                    <select
                      name="student"
                      value={assignForm.student}
                      onChange={(e) =>
                        setAssignForm((prev) => ({ ...prev, student: e.target.value }))
                      }
                      required
                      disabled={Boolean(editing)}
                    >
                      <option value="">Select student</option>
                      {allStudents.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.full_name || `${s.first_name} ${s.last_name}`} (
                          {s.admission_number || "No Adm #"})
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Route *
                    <select
                      name="route"
                      value={assignForm.route}
                      onChange={handleRouteChange}
                      required
                    >
                      <option value="">Select route</option>
                      {allRoutes.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Pickup / Drop Stop
                    <select
                      name="stop"
                      value={assignForm.stop}
                      onChange={(e) =>
                        setAssignForm((prev) => ({ ...prev, stop: e.target.value }))
                      }
                    >
                      <option value="">No specific stop</option>
                      {selectedRouteStops.map((st) => (
                        <option key={st.id} value={st.id}>
                          {st.name} {st.time ? `(${st.time})` : ""}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Status
                    <select
                      name="status"
                      value={assignForm.status}
                      onChange={(e) =>
                        setAssignForm((prev) => ({ ...prev, status: e.target.value }))
                      }
                    >
                      {ASSIGNMENT_STATUS_CHOICES.map((s) => (
                        <option key={s.value} value={s.value}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="secondary-button" onClick={closeModal} disabled={saving}>
                  Cancel
                </button>
                <button type="submit" className="primary-button" disabled={saving}>
                  <Plus size={17} />
                  {saving ? "Saving..." : editing ? "Save Changes" : "Create Assignment"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
