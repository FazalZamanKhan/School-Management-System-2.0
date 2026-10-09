import { useCallback, useEffect, useRef, useState } from "react";
import { BedDouble, Plus } from "lucide-react";
import { PageHeader, PanelHeader, StateArea } from "./ui";
import { apiFetch, authHeaders } from "../api";
import { useSchool } from "../schoolContext";

const BASE = "/api/hostel/";
const CAMPUSES_URL = "/api/schools/campuses/";

export default function HostelPage() {
  const { currentSchool, isSwitching } = useSchool();
  const schoolId = currentSchool?.id ?? null;
  const [tab, setTab] = useState("hostels");
  const [rows, setRows] = useState([]);
  const [hostels, setHostels] = useState([]);
  const [students, setStudents] = useState([]);
  const [roomOptions, setRoomOptions] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [scopeBlocked, setScopeBlocked] = useState(false);

  // One AbortController per active school. Every school-scoped request shares
  // its signal, so switching (or losing) the active school aborts all
  // in-flight requests for the previous context and a stale response can
  // never overwrite the new school's data. The page tree also remounts on
  // school change (App.jsx keys <Routes> by the active school id), which
  // discards the previous school's component state entirely.
  const scopeRef = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    scopeRef.current = controller;

    return () => {
      controller.abort();
      if (scopeRef.current === controller) scopeRef.current = null;
    };
  }, [schoolId]);

  const [hostelForm, setHostelForm] = useState({
    name: "",
    campus: "",
    warden: "",
    gender: "mixed",
    address: "",
  });

  const loadCampuses = useCallback(() => {
    fetch(CAMPUSES_URL, { credentials: "include" })
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setCampuses(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadCampuses();
  }, [loadCampuses]);

  // Add Room hostel selector — only fetched once the active school resolves.
  useEffect(() => {
    if (!schoolId) {
      setHostels([]);
      return;
    }

    const { signal } = scopeRef.current;

    fetch(`${BASE}room-hostels/`, { credentials: "include", signal })
      .then((r) => (r.ok ? r.json() : { results: [] }))
      .then((data) => {
        if (!signal.aborted) setHostels(data.results || data);
      })
      .catch(() => {});
  }, [schoolId]);

  const [roomForm, setRoomForm] = useState({
    hostel: "",
    room_number: "",
    capacity: 4,
  });

  const [allocForm, setAllocForm] = useState({
    room: "",
    student: "",
    start_date: new Date().toISOString().slice(0, 10),
  });

  // The Hostel Allocation student selector. Resolve the active school first,
  // then request it — never render a populated (or unscoped) student list
  // when the active school is missing or being resolved.
  useEffect(() => {
    if (!schoolId) {
      setStudents([]);
      return;
    }

    const { signal } = scopeRef.current;

    apiFetch("/api/students/?page_size=1000", { signal })
      .then((json) => {
        if (!signal.aborted) setStudents(Array.isArray(json) ? json : json.results || []);
      })
      .catch(() => {});
  }, [schoolId]);

  useEffect(() => {
    if (!schoolId) {
      setRoomOptions([]);
      return;
    }

    const { signal } = scopeRef.current;

    fetch(`${BASE}rooms/`, { credentials: "include", signal })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        if (!signal.aborted) setRoomOptions(data.results || data);
      })
      .catch(() => {});
  }, [schoolId, rows]);

  const load = useCallback(() => {
    if (!schoolId) {
      setRows([]);
      setLoading(false);
      setScopeBlocked(false);
      return;
    }

    setLoading(true);
    setError("");

    const url =
      tab === "hostels"
        ? `${BASE}hostels/`
        : tab === "rooms"
          ? `${BASE}rooms/`
          : `${BASE}allocations/?status=active`;

    const { signal } = scopeRef.current;

    apiFetch(url, { signal })
      .then((data) => {
        if (!signal.aborted) {
          setRows(data.results || data);
          setScopeBlocked(false);
        }
      })
      .catch((err) => {
        if (!signal.aborted) {
          if (err.status === 403) {
            // Active-school failure policy: a 403 on a school-scoped load
            // means the active school is stale, unauthorized, or inactive.
            // Fail closed to the "select a school" state instead of showing
            // a raw error — never a populated or stale student list.
            setRows([]);
            setScopeBlocked(true);
            setError("");
          } else {
            setError(err.message);
          }
        }
      })
      .finally(() => {
        if (!signal.aborted) setLoading(false);
      });
  }, [tab, schoolId]);

  useEffect(() => {
    load();
  }, [load]);

  const submit = (event) => {
    event.preventDefault();
    setSaving(true);
    setFormError("");

    const url =
      tab === "hostels"
        ? `${BASE}hostels/`
        : tab === "rooms"
          ? `${BASE}rooms/`
          : `${BASE}allocations/`;

    const body =
      tab === "hostels"
        ? hostelForm
        : tab === "rooms"
          ? roomForm
          : allocForm;

    apiFetch(url, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    })
      .then(() => {
        setShowForm(false);
        setNotice("Saved.");
        load();
      })
      .catch((err) => setFormError(err.message))
      .finally(() => setSaving(false));
  };

  const vacate = (id) => {
    apiFetch(`${BASE}allocations/${id}/vacate/`, { method: "POST" })
      .then(() => {
        setNotice("Room vacated.");
        load();
      })
      .catch((err) => setError(err.message));
  };

  // Active-school failure policy: while no valid active school is selected —
  // or the resolved context is stale/inactive (backed by a 403 on a scoped
  // load) — the page fails closed: no populated student/room selectors, no
  // scoped tables, and an explicit message pointing at the school switcher.
  const noActiveSchool = !schoolId && !isSwitching;
  const schoolContextUnavailable = noActiveSchool || scopeBlocked;
  const noSchoolMessage =
    tab === "allocations"
      ? "No active school selected. Please select a school to view hostel allocation students."
      : "No active school selected. Please select a school to manage hostels and rooms.";

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Hostel"
        title="Hostel Management"
        subtitle="Boarding houses, rooms and student allocations."
        action={
          <button
            type="button"
            className="primary-button"
            onClick={() => setShowForm((v) => !v)}
          >
            <Plus size={15} />
            Add
          </button>
        }
      />

      <div className="tabs">
        {[
          ["hostels", "Hostels"],
          ["rooms", "Rooms"],
          ["allocations", "Allocations"],
        ].map(([key, label]) => (
          <button
            key={key}
            className={`tab-button ${tab === key ? "active" : ""}`}
            onClick={() => setTab(key)}
          >
            <BedDouble size={15} />
            {label}
          </button>
        ))}
      </div>

      <div className="panel">
        <PanelHeader
          title={notice || "live data"}
          subtitle={`${rows.length} records`}
        />

        {schoolContextUnavailable ? (
          <div className="state-card error">{noSchoolMessage}</div>
        ) : (
        <StateArea loading={loading} error={error} onRetry={load}>
          {showForm && (
            <form onSubmit={submit} className="filter-row">
              {tab === "hostels" && (
                <>
                  <input
                    required
                    placeholder="Hostel name *"
                    value={hostelForm.name}
                    onChange={(e) =>
                      setHostelForm({ ...hostelForm, name: e.target.value })
                    }
                  />
                  <select
                    required
                    value={hostelForm.campus}
                    onChange={(e) =>
                      setHostelForm({ ...hostelForm, campus: e.target.value })
                    }
                  >
                    <option value="">Campus *</option>
                    {campuses.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                  <input
                    placeholder="Warden"
                    value={hostelForm.warden}
                    onChange={(e) =>
                      setHostelForm({ ...hostelForm, warden: e.target.value })
                    }
                  />
                  <select
                    value={hostelForm.gender}
                    onChange={(e) =>
                      setHostelForm({ ...hostelForm, gender: e.target.value })
                    }
                  >
                    <option value="boys">Boys</option>
                    <option value="girls">Girls</option>
                    <option value="mixed">Mixed</option>
                  </select>
                  <input
                    placeholder="Address"
                    value={hostelForm.address}
                    onChange={(e) =>
                      setHostelForm({ ...hostelForm, address: e.target.value })
                    }
                  />
                </>
              )}

              {tab === "rooms" && (
                <>
                  <select
                    required
                    value={roomForm.hostel}
                    onChange={(e) =>
                      setRoomForm({ ...roomForm, hostel: e.target.value })
                    }
                  >
                    <option value="">Hostel...</option>
                    {hostels.map((h) => (
                      <option key={h.id} value={h.id}>{h.name}</option>
                    ))}
                  </select>
                  <input
                    required
                    placeholder="Room no. *"
                    value={roomForm.room_number}
                    onChange={(e) =>
                      setRoomForm({ ...roomForm, room_number: e.target.value })
                    }
                  />
                  <input
                    type="number"
                    min="1"
                    value={roomForm.capacity}
                    onChange={(e) =>
                      setRoomForm({ ...roomForm, capacity: e.target.value })
                    }
                  />
                </>
              )}

              {tab === "allocations" && (
                <>
                  <select
                    required
                    value={allocForm.room}
                    onChange={(e) =>
                      setAllocForm({ ...allocForm, room: e.target.value })
                    }
                  >
                    <option value="">Room...</option>
                    {roomOptions.map((room) => (
                      <option key={room.id} value={room.id} disabled={room.is_full}>
                        {room.hostel_name || `Hostel #${room.hostel}`} - {room.room_number}{" "}
                        {room.is_full ? "(Full)" : `(${room.occupied || 0}/${room.capacity})`}
                      </option>
                    ))}
                  </select>

                  <select
                    required
                    value={allocForm.student}
                    onChange={(e) =>
                      setAllocForm({ ...allocForm, student: e.target.value })
                    }
                  >
                    <option value="">Student...</option>
                    {students.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.full_name} ({s.admission_number})
                      </option>
                    ))}
                  </select>

                  <input
                    type="date"
                    required
                    value={allocForm.start_date}
                    onChange={(e) =>
                      setAllocForm({ ...allocForm, start_date: e.target.value })
                    }
                  />
                </>
              )}

              <button className="primary-button" disabled={saving}>
                {saving ? "Saving..." : "Save"}
              </button>
            </form>
          )}

          {formError && (
            <div className="state-card error">{formError}</div>
          )}

          {rows.length === 0 ? (
            <div className="empty-state">
              <BedDouble size={42} />
              <h3>Nothing here yet</h3>
              <p>Add records using the button above.</p>
            </div>
          ) : (
            <div className="table-wrapper">
              {tab === "hostels" && (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Name</th><th>Campus</th><th>Warden</th>
                      <th>Gender</th><th>Occupied / Capacity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.id}>
                        <td><strong>{row.name}</strong></td>
                        <td>{row.campus_name}</td>
                        <td>{row.warden || "—"}</td>
                        <td>{row.gender}</td>
                        <td>{row.occupied ?? 0} / {row.total_capacity ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {tab === "rooms" && (
                <table className="data-table">
                  <thead>
                    <tr><th>Hostel</th><th>Room</th><th>Capacity</th><th>Occupied</th><th>Status</th></tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.id}>
                        <td>{row.hostel_name || `#${row.hostel}`}</td>
                        <td><strong>{row.room_number}</strong></td>
                        <td>{row.capacity}</td>
                        <td>{row.occupied}</td>
                        <td>{row.is_full ? "Full" : "Available"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {tab === "allocations" && (
                <table className="data-table">
                  <thead>
                    <tr><th>Student</th><th>Admission No</th><th>Room</th><th>Since</th><th></th></tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.id}>
                        <td><strong>{row.student_name}</strong></td>
                        <td>{row.admission_number}</td>
                        <td>{row.room_label}</td>
                        <td>{row.start_date}</td>
                        <td>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => vacate(row.id)}
                          >
                            Vacate
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </StateArea>
        )}
      </div>
    </section>
  );
}
