import { useRef, useState } from "react";
import { Upload, FileDown, CheckCircle2, AlertTriangle, FileSpreadsheet } from "lucide-react";
import { PageHeader, PanelHeader, StateArea } from "./ui";
import { apiFetch, apiDownload, authHeaders } from "../api";
import { hasImportableRows } from "../importPreview";

const IMPORT_TYPES = [
  {
    key: "students",
    label: "Students",
    description:
      "Creates students, guardians and active enrollments. Campus, class and section are matched by name.",
  },
  {
    key: "teachers",
    label: "Teachers",
    description:
      "Creates teacher records with campus assignment. Login accounts are not created.",
  },
];

export default function DataImportPage() {
  const [typeKey, setTypeKey] = useState("students");
  const [file, setFile] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);

  const type = IMPORT_TYPES.find((item) => item.key === typeKey);

  const downloadTemplate = () => {
    apiDownload(
      `/api/reports/import/templates/${typeKey}/`,
      `${typeKey}_import_template.csv`
    ).catch(() => setError("Could not download the template."));
  };

  const runPreview = () => {
    if (!file) {
      setError("Choose a CSV file first.");
      return;
    }

    setPreviewing(true);
    setError("");
    setPreview(null);
    setResult(null);

    const body = new FormData();
    body.append("file", file);

    apiFetch(`/api/reports/import/preview/?key=${typeKey}`, {
      method: "POST",
      headers: authHeaders(),
      body,
    })
      .then(setPreview)
      .catch((err) => setError(err.message))
      .finally(() => setPreviewing(false));
  };

  const runCommit = () => {
    if (!file || previewing || committing || !hasImportableRows(preview)) return;

    setCommitting(true);
    setError("");
    setResult(null);

    const body = new FormData();
    body.append("file", file);

    apiFetch(`/api/reports/import/commit/?key=${typeKey}`, {
      method: "POST",
      headers: authHeaders(),
      body,
    })
      .then(setResult)
      .catch((err) => setError(err.message))
      .finally(() => setCommitting(false));
  };

  const reset = () => {
    setFile(null);
    setPreview(null);
    setResult(null);
    setError("");

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const summaryCards = preview
    ? [
        { label: "Rows in file", value: preview.total_rows },
        { label: "Valid rows", value: preview.valid_rows },
        { label: "Rows with errors", value: preview.error_rows },
      ]
    : [];

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Data Import"
        title="Data Import"
        subtitle="Bulk-import students and teachers from CSV files."
      />

      <div className="panel">
        <PanelHeader
          title="Import data"
          subtitle="1. Download the template · 2. Fill it · 3. Validate · 4. Import"
        />

        <StateArea loading={previewing || committing} error={error}>
          <div className="filter-row">
            <select
              value={typeKey}
              onChange={(event) => {
                setTypeKey(event.target.value);
                reset();
              }}
            >
              {IMPORT_TYPES.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label}
                </option>
              ))}
            </select>

            <button
              type="button"
              className="primary-button"
              onClick={downloadTemplate}
            >
              <FileDown size={15} />
              Download template
            </button>
          </div>

          <p className="subtitle">{type.description}</p>

          <div className="filter-row">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => {
                setFile(event.target.files[0] || null);
                setPreview(null);
                setResult(null);
              }}
            />

            <button
              type="button"
              className="primary-button"
              onClick={runPreview}
              disabled={!file || previewing}
            >
              <Upload size={15} />
              Validate file
            </button>

            <button
              type="button"
              className="primary-button"
              onClick={runCommit}
              disabled={
                !file ||
                committing ||
                previewing ||
                !hasImportableRows(preview)
              }
            >
              <CheckCircle2 size={15} />
              {committing ? "Importing..." : "Run import"}
            </button>
          </div>

          {preview && (
            <>
              <div className="dashboard-grid">
                {summaryCards.map((card) => (
                  <div key={card.label} className="stat-card">
                    <strong>{card.value}</strong>
                    <span>{card.label}</span>
                  </div>
                ))}

                <div className="stat-card">
                  <strong>
                    {preview.can_commit ? (
                      <CheckCircle2 size={18} color="#16a34a" />
                    ) : (
                      <AlertTriangle size={18} color="#d97706" />
                    )}
                  </strong>
                  <span>{preview.can_commit ? "Ready to import" : hasImportableRows(preview) ? "Only valid rows will be imported" : "Fix errors first"}</span>
                </div>
              </div>

              {preview.errors.length > 0 && (
                <div className="table-wrapper">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>CSV ROW</th>
                        <th>PROBLEMS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.errors.map((item) => (
                        <tr key={item.row}>
                          <td>
                            <strong>Line {item.row}</strong>
                          </td>
                          <td>{item.errors.join(" · ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          {result && (
            <div className="panel" style={{ marginTop: 14 }}>
              <PanelHeader
                title="Import result"
                subtitle={<FileSpreadsheet size={14} />}
              />

              <div className="dashboard-grid">
                {(result.students_created !== undefined
                  ? [
                      { label: "Students created", value: result.students_created },
                      { label: "Skipped (already exist)", value: result.students_skipped_existing },
                      { label: "Enrollments created", value: result.enrollments_created },
                      { label: "Rows with errors", value: result.rows_with_errors },
                      { label: "Academic year", value: result.academic_year },
                    ]
                  : [
                      { label: "Teachers created", value: result.teachers_created },
                      { label: "Duplicates skipped", value: result.teachers_skipped_duplicates },
                      { label: "Rows with errors", value: result.rows_with_errors },
                    ]
                ).map((card) => (
                  <div key={card.label} className="stat-card">
                    <strong>{card.value}</strong>
                    <span>{card.label}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </StateArea>
      </div>
    </section>
  );
}
