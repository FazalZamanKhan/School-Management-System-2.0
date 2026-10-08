import { useEffect, useState } from "react";
import { CalendarDays, Sparkles } from "lucide-react";
import { useApiList } from "./useApiList";
import { useAuth } from "../auth";
import { useSchool } from "../schoolContext";
import {
  PageHeader,
  PanelHeader,
  StateArea,
  EmptyState,
  StatusBadge,
} from "./ui";
import { apiFetch, authHeaders } from "../api";
import { useToast } from "../toast";

const PERIODS_API_URL = "/api/timetable/periods/";
const ENTRIES_API_URL = "/api/timetable/entries/";
const GENERATE_URL = "/api/timetable/generate/";
const CLASSES_URL = "/api/schools/classes/";
const SECTIONS_URL = "/api/schools/sections/";

function AutoGeneratePanel() {
  const toast = useToast();
  const { campusList } = useSchool();
  const [campus, setCampus] = useState("");
  const [classes, setClasses] = useState([]);
  const [sections, setSections] = useState([]);
  const [classId, setClassId] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [lessons, setLessons] = useState(5);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const lessonsValid = Number.isInteger(Number(lessons)) && Number(lessons) >= 1 && Number(lessons) <= 20;

  useEffect(() => {
    if (!campus) {
      setClasses([]);
      setClassId("");
      setSections([]);
      setSectionId("");
      return;
    }

    apiFetch(CLASSES_URL)
      .then((data) => setClasses(data.results || data || []))
      .catch(() => setClasses([]));

    setClassId("");
    setSections([]);
    setSectionId("");
  }, [campus]);

  useEffect(() => {
    if (!classId) {
      setSections([]);
      setSectionId("");
      return;
    }

    apiFetch(`${SECTIONS_URL}?class=${classId}`)
      .then((data) => setSections(data.results || data || []))
      .catch(() => setSections([]));

    setSectionId("");
  }, [classId]);

  const run = () => {
    if (!campus || !lessonsValid) return;

    setBusy(true);
    setError("");
    setResult(null);

    apiFetch(GENERATE_URL, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        campus: Number(campus),
        lessons_per_subject: Number(lessons),
        ...(classId ? { class_id: Number(classId) } : {}),
        ...(sectionId ? { section_id: Number(sectionId) } : {}),
        confirm: true,
      }),
    }, "Unable to generate timetable. Check periods and teacher assignments for the selected school.")
    .then((data) => {
      setResult(data);
      const placed = data.sections || 0;
      const total = data.sections_total || placed;
      const summary = `Timetable generated: ${data.created} entries across ${placed}/${total} sections.`;
      toast.success(
        data.unplaced_count > 0
          ? `${summary} ${data.unplaced_count} lessons unplaced (teacher conflicts).`
          : summary
      );
    })
    .catch((err) => {
      setError(err.message);
      toast.error(err.message);
    })
    .finally(() => setBusy(false));
  };

  const scopeLabel = classId
    ? `class ${classes.find((c) => String(c.id) === String(classId))?.name || classId}${sectionId ? `, section ${sections.find((s) => String(s.id) === String(sectionId))?.name || sectionId}` : ""}`
    : `campus ${campusList.find((c) => String(c.id) === String(campus))?.name || campus}`;

  return (
    <div className="panel">
      <PanelHeader
        title="Auto-generate"
        subtitle="Rebuilds the weekly timetable from teacher assignments. Existing entries for the selected campus/class/section are replaced."
      />

      <div className="filter-row">
        <select value={campus} onChange={(e) => setCampus(e.target.value)} required>
          <option value="">Select campus...</option>
          {campusList.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>

        <select
          value={classId}
          onChange={(e) => setClassId(e.target.value)}
          disabled={!campus}
        >
          <option value="">{campus ? "All classes" : "Class (alpha first)"}</option>
          {classes
            .filter((c) => String(c.campus) === String(campus))
            .map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
        </select>

        <select
          value={sectionId}
          onChange={(e) => setSectionId(e.target.value)}
          disabled={!classId}
        >
          <option value="">{classId ? "All sections" : "Section (all)"}</option>
          {sections.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>

        <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
          Lessons/subject/week
          <input
            type="number"
            min="1"
            max="20"
            value={lessons}
            onChange={(e) => setLessons(e.target.value)}
            style={{ width: 64 }}
          />
        </label>
        {!lessonsValid && <span className="field-hint" role="alert">Enter a whole number from 1 to 20.</span>}

        <button
          type="button"
          className="primary-button"
          disabled={busy || !campus || !lessonsValid}
          onClick={() => {
            if (
              window.confirm(
                `Replace the current timetable for "${scopeLabel}"?`
              )
            ) {
              run();
            }
          }}
        >
          <Sparkles size={15} />
          {busy ? "Generating..." : "Generate"}
        </button>
      </div>

      {error && <div className="state-card error">{error}</div>}

      {result && (
        <p>
          Created <strong>{result.created}</strong> entries across{" "}
          <strong>{result.sections}/{result.sections_total}</strong> sections.
          {result.unplaced_count > 0 &&
            ` ${result.unplaced_count} lessons could not be placed (teacher conflicts).`}
        </p>
      )}
    </div>
  );
}

export default function TimetablePage() {
  const periods = useApiList(PERIODS_API_URL);
  const entries = useApiList(ENTRIES_API_URL);
  const { user, hasRole } = useAuth();

  const isTeacher = hasRole(["teacher"]);
  const canGenerate = hasRole(["super_admin", "admin", "org_admin", "head_office", "academic"]);

  const teacherName = user
    ? `${user.first_name || ""} ${user.last_name || ""}`.trim()
    : "";

  const pageTitle = isTeacher ? "My Timetable" : "Timetable";

  const pageSubtitle = isTeacher
    ? `Welcome, ${teacherName || "Teacher"}. This is your personal class schedule.`
    : "View class timetables and period schedules.";

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Timetable"
        title={pageTitle}
        subtitle={pageSubtitle}
      />

      {canGenerate && <AutoGeneratePanel />}

      <div className="panel">
        <PanelHeader
          title="Period Schedule"
          subtitle="periods configured"
          count={periods.count}
        />

        <StateArea loading={periods.loading} error={periods.error}>
          {periods.rows.length === 0 ? (
            <EmptyState
              icon={CalendarDays}
              title="No periods configured"
              message="No teaching periods have been configured yet."
            />
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>PERIOD</th>
                    <th>NUMBER</th>
                    <th>START</th>
                    <th>END</th>
                    <th>TYPE</th>
                    <th>STATUS</th>
                  </tr>
                </thead>

                <tbody>
                  {periods.rows.map((period) => (
                    <tr key={period.id}>
                      <td>
                        <strong>{period.name || "—"}</strong>
                      </td>

                      <td>#{period.number}</td>

                      <td>{period.start_time || "—"}</td>

                      <td>{period.end_time || "—"}</td>

                      <td>
                        {period.is_break ? "Break" : "Teaching"}
                      </td>

                      <td>
                        <StatusBadge
                          status={period.status}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </StateArea>
      </div>

      <div className="panel">
        <PanelHeader
          title="Timetable Entries"
          subtitle="entries found"
          count={entries.count}
        />

        <StateArea loading={entries.loading} error={entries.error}>
          {entries.rows.length === 0 ? (
            <EmptyState
              icon={CalendarDays}
              title="No timetable entries"
              message="No class timetable entries have been created yet."
            />
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>DAY</th>
                    <th>PERIOD</th>
                    <th>TIME</th>
                    <th>GRADE</th>
                    <th>SUBJECT</th>
                    <th>TEACHER</th>
                    <th>SECTION</th>
                    <th>ROOM</th>
                    <th>STATUS</th>
                  </tr>
                </thead>

                <tbody>
                  {entries.rows.map((entry) => (
                    <tr key={entry.id}>
                      <td>
                        <strong>{entry.day_display || "—"}</strong>
                      </td>

                      <td>
                        {entry.period_name || "—"} (
                        {entry.period_number || "—"})
                      </td>

                      <td>
                        {entry.start_time || "—"} –{" "}
                        {entry.end_time || "—"}
                      </td>

                      <td>
                        <span className="grade-badge">
                          {entry.class_name || "—"}
                        </span>
                      </td>

                      <td>
                        <strong>
                          {entry.subject_name || "—"}
                        </strong>

                        {entry.subject_code && (
                          <span className="cell-sub">
                            {entry.subject_code}
                          </span>
                        )}
                      </td>

                      <td>{entry.teacher_name || "—"}</td>

                      <td>{entry.section_name || "—"}</td>

                      <td>{entry.room || "—"}</td>

                      <td>
                        <StatusBadge
                          status={entry.status}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </StateArea>
      </div>
    </section>
  );
}
