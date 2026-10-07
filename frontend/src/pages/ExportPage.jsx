import { useCallback, useEffect, useState } from "react";
import { Download, FileText, Database } from "lucide-react";
import { apiFetch, apiDownload } from "../api";
import { PageHeader, StateArea, EmptyState } from "./ui";

const EXPORT_LIST_URL = "/api/reports/export/";
const EXPORT_URL = "/api/reports/export";
const BACKUP_URL = "/api/reports/backup/";

const ICONS = {
  students: "🎓",
  teachers: "👨‍🏫",
  invoices: "💰",
  payments: "💳",
  attendance: "📋",
  enrollments: "📝",
};

export default function ExportPage() {
  const [exports, setExports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(null);
  const [downloadError, setDownloadError] = useState("");

  const fetchExports = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch(EXPORT_LIST_URL, {}, "Failed to load export options.");
      setExports(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchExports();
  }, [fetchExports]);

  const handleExport = async (key, filename, format) => {
    setDownloading(key);
    setDownloadError("");
    try {
      await apiDownload(`${EXPORT_URL}/${key}/?format=${format}`, `${filename}.${format}`);
    } catch (err) {
      setDownloadError(err.message || "Failed to download the export.");
    } finally {
      setDownloading(null);
    }
  };

  const handleFullBackup = async () => {
    setDownloading("backup");
    try {
      await apiDownload(BACKUP_URL, "full_backup.json");
    } catch {
      // ignore
    } finally {
      setDownloading(null);
    }
  };

  return (
    <section className="content">
      <PageHeader
        crumb="Home / Reports / Data Export"
        title="Data Export & Backup"
        subtitle="Export your data in CSV or JSON format, or download a full backup."
      />

      {downloadError && <div className="state-card error" role="alert">{downloadError}</div>}

      <StateArea loading={loading} error={error} onRetry={fetchExports}>
        {/* Full Backup */}
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="teacher-list-header">
            <h3><Database size={16} /> Full Data Backup</h3>
          </div>
          <div className="form-section">
            <p style={{ marginBottom: 12, fontSize: 13, color: "var(--text-muted)" }}>
              Download a complete JSON backup of all system data including students, teachers, invoices, payments, attendance, and enrollments.
            </p>
            <button
              className="primary-button"
              onClick={handleFullBackup}
              disabled={downloading === "backup"}
            >
              <Download size={15} />
              {downloading === "backup" ? "Downloading..." : "Download Full Backup (JSON)"}
            </button>
          </div>
        </div>

        {/* Individual Exports */}
        <div className="panel">
          <div className="teacher-list-header">
            <h3><FileText size={16} /> Individual Data Exports</h3>
          </div>

          {exports.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No exports available"
              message="No exportable data sets found."
            />
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16, padding: 16 }}>
              {exports.map((exp) => (
                <div key={exp.key} style={{
                  border: "1px solid #e0e0e0",
                  borderRadius: 8,
                  padding: 16,
                  background: "var(--surface)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <span style={{ fontSize: 24 }}>{ICONS[exp.key] || "📄"}</span>
                    <div>
                      <strong>{exp.label}</strong>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{exp.filename}</div>
                    </div>
                  </div>

                  <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                    <button
                      className="secondary-button"
                      style={{ flex: 1, fontSize: 12 }}
                      onClick={() => handleExport(exp.key, exp.filename, "csv")}
                      disabled={downloading === exp.key}
                    >
                      <Download size={13} />
                      {downloading === exp.key ? "..." : "CSV"}
                    </button>
                    <button
                      className="secondary-button"
                      style={{ flex: 1, fontSize: 12 }}
                      onClick={() => handleExport(exp.key, exp.filename, "json")}
                      disabled={downloading === exp.key}
                    >
                      <Download size={13} />
                      {downloading === exp.key ? "..." : "JSON"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </StateArea>
    </section>
  );
}
