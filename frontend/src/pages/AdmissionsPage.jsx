import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, FilePlus2, Inbox, Search, Trash2, UserPlus, X, Building2, BookOpen } from "lucide-react";
import { apiFetch, jsonHeaders } from "../api";
import { PageHeader, PanelHeader, StateArea, StatusBadge } from "./ui";

const ADMISSIONS_URL = "/api/students/admissions/";
const INQUIRIES_URL = "/api/students/inquiries/";
const CAMPUSES_URL = "/api/schools/campuses/";
const ACADEMIC_YEARS_URL = "/api/schools/academic-years/";
const CLASSES_URL = "/api/schools/classes/";
const SECTIONS_URL = "/api/schools/sections/";
const GUARDIANS_URL = "/api/students/guardians/";

const ADMISSION_STATUSES = [
  ["draft", "Draft"],
  ["submitted", "Submitted"],
  ["under_review", "Under review"],
  ["accepted", "Accepted"],
  ["rejected", "Rejected"],
  ["withdrawn", "Withdrawn"],
];

const INQUIRY_STATUSES = [
  ["new", "New"],
  ["contacted", "Contacted"],
  ["interested", "Interested"],
  ["application_started", "Application Started"],
  ["converted", "Converted"],
  ["lost", "Lost"],
  ["closed", "Closed"],
];

const INQUIRY_SOURCES = [
  ["website", "Website"],
  ["walk_in", "Walk-in"],
  ["phone", "Phone"],
  ["email", "Email"],
  ["referral", "Referral"],
  ["social_media", "Social Media"],
  ["event", "Event / Open House"],
  ["other", "Other"],
];

function toList(data) {
  return Array.isArray(data) ? data : data.results || [];
}

function generateApplicationNumber() {
  const now = new Date();
  const date = now.toISOString().slice(0, 10).replace(/-/g, "");
  return `APP-${date}-${Math.floor(Math.random() * 9000) + 1000}`;
}

function useCatalog(campusId, classId) {
  const [classes, setClasses] = useState([]);
  const [sections, setSections] = useState([]);

  useEffect(() => {
    if (!campusId) {
      setClasses([]);
      setSections([]);
      return;
    }
    let alive = true;
    fetch(`${CLASSES_URL}?campus=${campusId}`, { credentials: "include" })
      .then((response) => (response.ok ? response.json() : []))
      .then((data) => {
        if (alive) setClasses(toList(data));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [campusId]);

  useEffect(() => {
    if (!classId) {
      setSections([]);
      return;
    }
    let alive = true;
    fetch(`${SECTIONS_URL}?class=${classId}`, { credentials: "include" })
      .then((response) => (response.ok ? response.json() : []))
      .then((data) => {
        if (alive) setSections(toList(data));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [classId]);

  return [classes, sections];
}

const EMPTY_APP_FORM = {
  first_name: "",
  middle_name: "",
  last_name: "",
  date_of_birth: "",
  gender: "male",
  phone: "",
  address: "",
  campus: "",
  academic_year: "",
  class_obj: "",
  section: "",
  guardian: "",
};

const EMPTY_INQUIRY_FORM = {
  first_name: "",
  middle_name: "",
  last_name: "",
  date_of_birth: "",
  gender: "male",
  phone: "",
  email: "",
  address: "",
  guardian_name: "",
  guardian_phone: "",
  guardian_email: "",
  guardian_relationship: "",
  campus: "",
  academic_year: "",
  class_obj: "",
  source: "website",
  source_details: "",
  notes: "",
};

export default function AdmissionsPage() {
  const [tab, setTab] = useState("applications");

  const [applications, setApplications] = useState([]);
  const [appStatus, setAppStatus] = useState("");
  const [appSearch, setAppSearch] = useState("");
  const [appLoading, setAppLoading] = useState(true);
  const [appError, setAppError] = useState("");

  const [inquiries, setInquiries] = useState([]);
  const [inqStatus, setInqStatus] = useState("");
  const [inqSearch, setInqSearch] = useState("");
  const [inqLoading, setInqLoading] = useState(true);
  const [inqError, setInqError] = useState("");

  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const [appForm, setAppForm] = useState(EMPTY_APP_FORM);
  const [showAppForm, setShowAppForm] = useState(false);
  const [savingApp, setSavingApp] = useState(false);
  const [editingApp, setEditingApp] = useState(null);

  const [inqForm, setInqForm] = useState(EMPTY_INQUIRY_FORM);
  const [showInqForm, setShowInqForm] = useState(false);
  const [savingInq, setSavingInq] = useState(false);
  const [inquirySubmitError, setInquirySubmitError] = useState("");

  const [followInquiry, setFollowInquiry] = useState(null);
  const [followStatus, setFollowStatus] = useState("new");
  const [followNotes, setFollowNotes] = useState("");
  const [savingFollow, setSavingFollow] = useState(false);

  const [convertInquiry, setConvertInquiry] = useState(null);
  const [convertForm, setConvertForm] = useState({});
  const [savingConvert, setSavingConvert] = useState(false);

  const [busyId, setBusyId] = useState(null);

  const [campuses, setCampuses] = useState([]);
  const [academicYears, setAcademicYears] = useState([]);
  const [guardians, setGuardians] = useState([]);

  const loadApplications = useCallback(() => {
    setAppLoading(true);
    const params = new URLSearchParams({ page_size: "500" });
    fetch(`${ADMISSIONS_URL}?${params.toString()}`, { credentials: "include" })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error("Failed to load admission applications."))))
      .then((data) => {
        setApplications(toList(data));
        setAppError("");
      })
      .catch((requestError) => setAppError(requestError.message))
      .finally(() => setAppLoading(false));
  }, []);

  const loadInquiries = useCallback(() => {
    setInqLoading(true);
    const params = new URLSearchParams({ page_size: "500" });
    fetch(`${INQUIRIES_URL}?${params.toString()}`, { credentials: "include" })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error("Failed to load inquiries."))))
      .then((data) => {
        setInquiries(toList(data));
        setInqError("");
      })
      .catch((requestError) => setInqError(requestError.message))
      .finally(() => setInqLoading(false));
  }, []);

  useEffect(() => {
    loadApplications();
  }, [loadApplications]);

  useEffect(() => {
    loadInquiries();
  }, [loadInquiries]);

  useEffect(() => {
    fetch(CAMPUSES_URL, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setCampuses(toList(d)))
      .catch(() => {});

    fetch(ACADEMIC_YEARS_URL, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setAcademicYears(toList(d)))
      .catch(() => {});

    fetch(GUARDIANS_URL, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setGuardians(toList(d)))
      .catch(() => {});
  }, []);

  const [appClasses, appSections] = useCatalog(appForm.campus, appForm.class_obj);
  const [inqClasses] = useCatalog(inqForm.campus, inqForm.class_obj);
  const [convClasses, convSections] = useCatalog(convertForm.campus, convertForm.class_obj);

  const visibleApplications = useMemo(() => {
    const term = appSearch.trim().toLowerCase();
    return applications.filter((application) => {
      if (appStatus && application.status !== appStatus) return false;
      if (!term) return true;
      return (
        (application.applicant_name || "").toLowerCase().includes(term) ||
        (application.application_number || "").toLowerCase().includes(term)
      );
    });
  }, [applications, appStatus, appSearch]);

  const visibleInquiries = useMemo(() => {
    const term = inqSearch.trim().toLowerCase();
    return inquiries.filter((inquiry) => {
      if (inqStatus && inquiry.status !== inqStatus) return false;
      if (!term) return true;
      return [inquiry.applicant_name, inquiry.inquiry_number, inquiry.phone, inquiry.email]
        .some((value) => value && value.toLowerCase().includes(term));
    });
  }, [inquiries, inqStatus, inqSearch]);

  const pipelineApps = useMemo(() => {
    const counts = {};
    ADMISSION_STATUSES.forEach(([key]) => {
      counts[key] = 0;
    });
    applications.forEach((application) => {
      if (Object.prototype.hasOwnProperty.call(counts, application.status)) {
        counts[application.status] += 1;
      }
    });
    return counts;
  }, [applications]);

  const pipelineInqs = useMemo(() => {
    const counts = {};
    INQUIRY_STATUSES.forEach(([key]) => {
      counts[key] = 0;
    });
    inquiries.forEach((inquiry) => {
      if (Object.prototype.hasOwnProperty.call(counts, inquiry.status)) {
        counts[inquiry.status] += 1;
      }
    });
    return counts;
  }, [inquiries]);

  const guardianName = (id) => {
    if (!id) return "";
    const match = guardians.find((g) => Number(g.id) === Number(id));
    return match ? match.name : "";
  };

  const appField = (name) => (event) => {
    const value = event.target.value;
    setAppForm((prev) => {
      const next = { ...prev, [name]: value };
      if (name === "campus") {
        next.class_obj = "";
        next.section = "";
      }
      if (name === "class_obj") {
        next.section = "";
      }
      return next;
    });
  };

  const inqField = (name) => (event) => {
    const value = event.target.value;
    setInqForm((prev) => {
      const next = { ...prev, [name]: value };
      if (name === "campus") {
        next.class_obj = "";
      }
      return next;
    });
  };

  const setNoticeOrError = (message) => {
    setNotice(message);
    setError("");
  };

  const clearBanners = () => {
    setNotice("");
    setError("");
  };

  const openAppCreate = () => {
    clearBanners();
    setEditingApp(null);
    setAppForm(EMPTY_APP_FORM);
    setShowAppForm(true);
  };

  const openAppEdit = (application) => {
    clearBanners();
    setEditingApp(application);
    setAppForm({
      first_name: application.first_name || "",
      middle_name: application.middle_name || "",
      last_name: application.last_name || "",
      date_of_birth: application.date_of_birth || "",
      gender: application.gender || "male",
      phone: application.phone || "",
      address: application.address || "",
      campus: application.campus ? String(application.campus) : "",
      academic_year: application.academic_year ? String(application.academic_year) : "",
      class_obj: application.class_obj ? String(application.class_obj) : "",
      section: application.section ? String(application.section) : "",
      guardian: application.guardian ? String(application.guardian) : "",
    });
    setShowAppForm(true);
  };

  const handleCreateApplication = async (event) => {
    event.preventDefault();
    setSavingApp(true);
    setError("");
    setNotice("");

    const isEditing = Boolean(editingApp);

    const body = {
      application_number: isEditing
        ? editingApp.application_number
        : generateApplicationNumber(),
      first_name: appForm.first_name,
      middle_name: appForm.middle_name,
      last_name: appForm.last_name,
      date_of_birth: appForm.date_of_birth || null,
      gender: appForm.gender,
      phone: appForm.phone,
      address: appForm.address,
      campus: Number(appForm.campus),
      academic_year: Number(appForm.academic_year),
      class_obj: Number(appForm.class_obj),
      section: appForm.section ? Number(appForm.section) : null,
      guardian: appForm.guardian ? Number(appForm.guardian) : null,
      status: isEditing ? editingApp.status : "submitted",
    };

    try {
      await apiFetch(
        isEditing
          ? `${ADMISSIONS_URL}${editingApp.id}/`
          : ADMISSIONS_URL,
        {
          method: isEditing ? "PATCH" : "POST",
          headers: jsonHeaders(),
          body: JSON.stringify(body),
        }
      );
      setShowAppForm(false);
      setAppForm(EMPTY_APP_FORM);
      setEditingApp(null);
      setNoticeOrError(
        isEditing
          ? "Admission application updated successfully."
          : "Admission application created successfully."
      );
      loadApplications();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSavingApp(false);
    }
  };

  const openInquiryCreate = () => {
    clearBanners();
    setInquirySubmitError("");
    setInqForm(EMPTY_INQUIRY_FORM);
    setShowInqForm(true);
  };

  const handleCreateInquiry = async (event) => {
    event.preventDefault();
    setSavingInq(true);
    setInquirySubmitError("");
    setNotice("");

    const body = {
      first_name: inqForm.first_name,
      middle_name: inqForm.middle_name,
      last_name: inqForm.last_name,
      date_of_birth: inqForm.date_of_birth || null,
      gender: inqForm.gender,
      phone: inqForm.phone,
      email: inqForm.email,
      address: inqForm.address,
      guardian_name: inqForm.guardian_name,
      guardian_phone: inqForm.guardian_phone,
      guardian_email: inqForm.guardian_email,
      guardian_relationship: inqForm.guardian_relationship,
      campus: inqForm.campus ? Number(inqForm.campus) : null,
      academic_year: inqForm.academic_year ? Number(inqForm.academic_year) : null,
      class_obj: inqForm.class_obj ? Number(inqForm.class_obj) : null,
      source: inqForm.source,
      source_details: inqForm.source_details,
      notes: inqForm.notes,
    };

    try {
      await apiFetch(INQUIRIES_URL, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify(body),
      }, "Unable to log inquiry.");
      setShowInqForm(false);
      setInqForm(EMPTY_INQUIRY_FORM);
      setNoticeOrError("Inquiry logged. The applicant has been assigned a fresh status pipeline.");
      loadInquiries();
    } catch (requestError) {
      setInquirySubmitError(requestError.message);
    } finally {
      setSavingInq(false);
    }
  };

  const reviewApplication = (application, action) => {
    setBusyId(application.id);
    clearBanners();
    apiFetch(`${ADMISSIONS_URL}${application.id}/review/`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ action }),
    })
      .then(() => {
        setNoticeOrError("Application status updated.");
        loadApplications();
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setBusyId(null));
  };

  const acceptApplication = (application) => {
    const admissionNumber = window.prompt("Admission number", application.application_number);
    if (!admissionNumber) return;
    setBusyId(application.id);
    clearBanners();
    apiFetch(`${ADMISSIONS_URL}${application.id}/accept/`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ admission_number: admissionNumber }),
    })
      .then((data) => {
        setNoticeOrError(`Application accepted for ${data.student?.full_name || "the student"}.`);
        loadApplications();
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setBusyId(null));
  };

  const withdrawApplication = (application) => {
    if (!window.confirm(`Withdraw application ${application.application_number}?`)) return;
    setBusyId(application.id);
    clearBanners();
    apiFetch(`${ADMISSIONS_URL}${application.id}/`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify({ status: "withdrawn" }),
    })
      .then(() => {
        setNoticeOrError("Application withdrawn.");
        loadApplications();
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setBusyId(null));
  };

  const openFollowUp = (inquiry) => {
    clearBanners();
    setFollowInquiry(inquiry);
    setFollowStatus(inquiry.status);
    setFollowNotes(inquiry.notes || "");
  };

  const handleFollowUp = async (event) => {
    event.preventDefault();
    if (!followInquiry) return;
    setSavingFollow(true);
    setError("");
    setNotice("");
    try {
      await apiFetch(`${INQUIRIES_URL}${followInquiry.id}/`, {
        method: "PATCH",
        headers: jsonHeaders(),
        body: JSON.stringify({ status: followStatus, notes: followNotes }),
      });
      setFollowInquiry(null);
      setNoticeOrError(`Inquiry marked as ${followStatus.replace(/_/g, " ")}.`);
      loadInquiries();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSavingFollow(false);
    }
  };

  const openConvert = (inquiry) => {
    clearBanners();
    setConvertInquiry(inquiry);
    setConvertForm({
      application_number: generateApplicationNumber(),
      campus: inquiry.campus || "",
      academic_year: inquiry.academic_year || "",
      class_obj: inquiry.class_obj || "",
      section: "",
    });
  };

  const convertField = (name) => (event) => {
    const value = event.target.value;
    setConvertForm((prev) => {
      const next = { ...prev, [name]: value };
      if (name === "campus") {
        next.class_obj = "";
        next.section = "";
      }
      if (name === "class_obj") {
        next.section = "";
      }
      return next;
    });
  };

  const handleConvert = async (event) => {
    event.preventDefault();
    if (!convertInquiry) return;
    setSavingConvert(true);
    setError("");
    setNotice("");
    try {
      const data = await apiFetch(`${INQUIRIES_URL}${convertInquiry.id}/convert/`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          application_data: {
            application_number: convertForm.application_number,
            campus: convertForm.campus ? Number(convertForm.campus) : null,
            academic_year: convertForm.academic_year ? Number(convertForm.academic_year) : null,
            class_obj: convertForm.class_obj ? Number(convertForm.class_obj) : null,
            section: convertForm.section ? Number(convertForm.section) : null,
          },
        }),
      });
      setConvertInquiry(null);
      const number = data?.application?.application_number || convertForm.application_number;
      setNoticeOrError(`Inquiry converted to application ${number} (draft). Submit it from the Applications tab.`);
      Promise.all([loadApplications(), loadInquiries()]);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSavingConvert(false);
    }
  };

  const deleteInquiry = (inquiry) => {
    if (!window.confirm(`Delete inquiry ${inquiry.inquiry_number}?`)) return;
    setBusyId(inquiry.id);
    clearBanners();
    apiFetch(`${INQUIRIES_URL}${inquiry.id}/`, { method: "DELETE" })
      .then(() => {
        setNoticeOrError("Inquiry deleted.");
        loadInquiries();
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setBusyId(null));
  };

  const appRowActions = (application) => {
    const busy = busyId === application.id;
    const actions = [];

    if (application.status === "draft" || application.status === "submitted" || application.status === "under_review") {
      actions.push(
        <button key="edit" className="secondary-button" disabled={busy} onClick={() => openAppEdit(application)}>
          Edit
        </button>,
      );
    }
    if (application.status === "draft") {
      actions.push(
        <button key="submit" className="secondary-button" disabled={busy} onClick={() => reviewApplication(application, "submit")}>
          Submit
        </button>,
      );
    }
    if (application.status === "submitted") {
      actions.push(
        <button key="review" className="secondary-button" disabled={busy} onClick={() => reviewApplication(application, "under_review")}>
          Review
        </button>,
      );
    }
    if (application.status === "submitted" || application.status === "under_review") {
      actions.push(
        <button key="accept" className="primary-button" disabled={busy} onClick={() => acceptApplication(application)} title="Requires a guardian and section">
          <Check size={15} /> Accept
        </button>,
        <button key="reject" className="danger-button" disabled={busy} onClick={() => reviewApplication(application, "reject")}>
          <X size={15} /> Reject
        </button>,
      );
    }
    if (application.status === "draft" || application.status === "submitted" || application.status === "under_review") {
      actions.push(
        <button key="withdraw" className="danger-button" disabled={busy} onClick={() => withdrawApplication(application)} title="Withdraw this application">
          Withdraw
        </button>,
      );
    }
    return actions;
  };

  const inqRowActions = (inquiry) => {
    const busy = busyId === inquiry.id;
    if (inquiry.status === "converted") return null;
    return (
      <>
        <button className="secondary-button" disabled={busy} onClick={() => openFollowUp(inquiry)}>
          Follow up
        </button>
        <button className="primary-button" disabled={busy} onClick={() => openConvert(inquiry)}>
          <UserPlus size={15} /> Convert
        </button>
        <button className="danger-button" disabled={busy} onClick={() => deleteInquiry(inquiry)}>
          <Trash2 size={15} /> Delete
        </button>
      </>
    );
  };

  const headerAction = () => {
    if (tab === "applications") {
      return (
        <button className="primary-button" onClick={openAppCreate}>
          <FilePlus2 size={15} /> New Application
        </button>
      );
    }
    return (
      <button className="primary-button" onClick={openInquiryCreate}>
        <Inbox size={15} /> Log Inquiry
      </button>
    );
  };

  return (
    <section className="content">
      <PageHeader
        crumb="Home / People / Admissions"
        title="Admissions"
        subtitle="Track inquiries, review applicants, and convert accepted applications into enrolled students."
        action={headerAction()}
        hero
        stats={[
          {
            label: "Applications",
            value: applications.length,
            icon: <FilePlus2 size={18} />,
            sub: "total applications",
          },
          {
            label: "Inquiries",
            value: inquiries.length,
            icon: <Inbox size={18} />,
            sub: "total inquiries",
          },
          {
            label: "Campuses",
            value: campuses.length,
            icon: <Building2 size={18} />,
            sub: "receiving applications",
          },
          {
            label: "Academic years",
            value: academicYears.length,
            icon: <BookOpen size={18} />,
            sub: "open for placement",
          },
        ]}
      />

      {notice && (
        <div className="state-card success">
          <strong>{notice}</strong>
        </div>
      )}

      {error && (
        <div className="state-card error">
          <strong>{error}</strong>
        </div>
      )}

      <div className="tabs" style={{ marginBottom: 16 }}>
        <button type="button" className={tab === "applications" ? "active" : ""} onClick={() => setTab("applications")}>
          Applications
        </button>
        <button type="button" className={tab === "inquiries" ? "active" : ""} onClick={() => setTab("inquiries")}>
          Inquiries
        </button>
      </div>

      {tab === "applications" ? (
        <>
          <div className="pipeline-row">
            <PipelineButton
              active={!appStatus}
              label="All"
              count={applications.length}
              onClick={() => setAppStatus("")}
            />
            {ADMISSION_STATUSES.map(([key, label]) => (
              <PipelineButton
                key={key}
                active={appStatus === key}
                label={label}
                count={pipelineApps[key]}
                onClick={() => setAppStatus(key === appStatus ? "" : key)}
              />
            ))}
          </div>

          <div className="panel students-filters">
            <div className="filter-row">
              <div className="filter-search">
                <Search size={18} />
                <input
                  placeholder="Search applicants or application number..."
                  value={appSearch}
                  onChange={(event) => setAppSearch(event.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="panel">
            <PanelHeader
              title="Application queue"
              subtitle="applications"
              count={visibleApplications.length}
            />
            <StateArea loading={appLoading} error={appError} onRetry={loadApplications}>
              {visibleApplications.length === 0 ? (
                <div className="state-card">No admission applications found.</div>
              ) : (
                <div className="table-wrapper">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>APPLICANT</th>
                        <th>APPLICATION</th>
                        <th>CONTACT</th>
                        <th>CAMPUS / CLASS</th>
                        <th>GUARDIAN</th>
                        <th>STATUS</th>
                        <th>ACTIONS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleApplications.map((application) => (
                        <tr key={application.id}>
                          <td><strong>{application.applicant_name}</strong></td>
                          <td>{application.application_number}</td>
                          <td>{application.phone || "-"}</td>
                          <td>
                            {application.campus_name || "-"}
                            <span className="table-sub">
                              {application.class_name || ""}{application.section_name ? ` · ${application.section_name}` : ""}
                            </span>
                          </td>
                          <td>{guardianName(application.guardian) || "Not linked"}</td>
                          <td><StatusBadge status={application.status} label={application.status_display} /></td>
                          <td>
                            <div className="table-actions">
                              {appRowActions(application)}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </StateArea>
          </div>
        </>
      ) : (
        <>
          <div className="pipeline-row">
            <PipelineButton
              active={!inqStatus}
              label="All"
              count={inquiries.length}
              onClick={() => setInqStatus("")}
            />
            {INQUIRY_STATUSES.map(([key, label]) => (
              <PipelineButton
                key={key}
                active={inqStatus === key}
                label={label}
                count={pipelineInqs[key]}
                onClick={() => setInqStatus(key === inqStatus ? "" : key)}
              />
            ))}
          </div>

          <div className="panel students-filters">
            <div className="filter-row">
              <div className="filter-search">
                <Search size={18} />
                <input
                  placeholder="Search inquiries by name, number, phone or email..."
                  value={inqSearch}
                  onChange={(event) => setInqSearch(event.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="panel">
            <PanelHeader
              title="Inquiry pipeline"
              subtitle="inquiries"
              count={visibleInquiries.length}
            />
            <StateArea loading={inqLoading} error={inqError} onRetry={loadInquiries}>
              {visibleInquiries.length === 0 ? (
                <div className="state-card">No inquiries found.</div>
              ) : (
                <div className="table-wrapper">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>APPLICANT</th>
                        <th>INQUIRY</th>
                        <th>CONTACT</th>
                        <th>CAMPUS / CLASS</th>
                        <th>SOURCE</th>
                        <th>STATUS</th>
                        <th>ACTIONS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleInquiries.map((inquiry) => (
                        <tr key={inquiry.id}>
                          <td><strong>{inquiry.applicant_name}</strong></td>
                          <td>
                            {inquiry.inquiry_number}
                            {inquiry.admission_application_number && (
                              <span className="table-sub">→ {inquiry.admission_application_number}</span>
                            )}
                          </td>
                          <td>
                            {inquiry.phone || inquiry.email || "-"}
                            <span className="table-sub">
                              {inquiry.guardian_name ? `Guardian: ${inquiry.guardian_name}${inquiry.guardian_phone ? ` (${inquiry.guardian_phone})` : ""}` : ""}
                            </span>
                          </td>
                          <td>
                            {inquiry.campus_name || "-"}
                            <span className="table-sub">{inquiry.class_name || ""}</span>
                          </td>
                          <td>{inquiry.source_display}</td>
                          <td><StatusBadge status={inquiry.status} label={inquiry.status_display} /></td>
                          <td>
                            <div className="table-actions">
                              {inqRowActions(inquiry)}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </StateArea>
          </div>
        </>
      )}

      {showAppForm && (
        <Modal title={editingApp ? "Edit Admission Application" : "New Admission Application"} subtitle={editingApp ? "Update the applicant details below." : "Fill in the applicant details below."} onClose={() => { setShowAppForm(false); setEditingApp(null); }}>
          <form onSubmit={handleCreateApplication}>
            <div className="form-section">
              <h4>Applicant Information</h4>
              <div className="form-grid">
                <Field label="First Name" required>
                  <input name="first_name" value={appForm.first_name} onChange={appField("first_name")} placeholder="First name" required />
                </Field>
                <Field label="Middle Name">
                  <input name="middle_name" value={appForm.middle_name} onChange={appField("middle_name")} placeholder="Middle name" />
                </Field>
                <Field label="Last Name">
                  <input name="last_name" value={appForm.last_name} onChange={appField("last_name")} placeholder="Last name" />
                </Field>
                <Field label="Date of Birth">
                  <input type="date" name="date_of_birth" value={appForm.date_of_birth} onChange={appField("date_of_birth")} />
                </Field>
                <Field label="Gender" required>
                  <select name="gender" value={appForm.gender} onChange={appField("gender")} required>
                    <option value="male">Male</option>
                    <option value="female">Female</option>
                  </select>
                </Field>
                <Field label="Phone">
                  <input name="phone" value={appForm.phone} onChange={appField("phone")} placeholder="03XX-XXXXXXX" />
                </Field>
                <Field label="Address">
                  <textarea name="address" value={appForm.address} onChange={appField("address")} placeholder="Full address" rows="2" />
                </Field>
              </div>
            </div>

            <div className="form-section">
              <h4>Academic Details</h4>
              <div className="form-grid">
                <Field label="Campus" required>
                  <select name="campus" value={appForm.campus} onChange={appField("campus")} required>
                    <option value="">Select campus</option>
                    {campuses.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Academic Year" required>
                  <select name="academic_year" value={appForm.academic_year} onChange={appField("academic_year")} required>
                    <option value="">Select year</option>
                    {academicYears.map((y) => (
                      <option key={y.id} value={y.id}>{y.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Class" required>
                  <select name="class_obj" value={appForm.class_obj} onChange={appField("class_obj")} required disabled={!appForm.campus}>
                    <option value="">Select class</option>
                    {appClasses.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Section">
                  <select name="section" value={appForm.section} onChange={appField("section")} disabled={!appForm.class_obj}>
                    <option value="">Select section</option>
                    {appSections.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Guardian">
                  <select name="guardian" value={appForm.guardian} onChange={appField("guardian")}>
                    <option value="">Select guardian</option>
                    {guardians.map((g) => (
                      <option key={g.id} value={g.id}>{g.name} ({g.relationship})</option>
                    ))}
                  </select>
                </Field>
              </div>
            </div>

            <div className="modal-footer">
<button type="button" className="secondary-button" onClick={() => { setShowAppForm(false); setEditingApp(null); }} disabled={savingApp}>
                  <X size={15} /> Cancel
                </button>
                <button type="submit" className="primary-button" disabled={savingApp}>
                  <Check size={15} /> {savingApp ? "Submitting..." : editingApp ? "Save Changes" : "Submit Application"}
                </button>
            </div>
          </form>
        </Modal>
      )}

      {showInqForm && (
        <Modal title="Log an Inquiry" subtitle="Capture a prospective applicant before they submit a formal application." onClose={() => setShowInqForm(false)}>
          {inquirySubmitError && <div className="state-card error" role="alert">{inquirySubmitError}</div>}
          <form onSubmit={handleCreateInquiry}>
            <div className="form-section">
              <h4>Prospective Applicant</h4>
              <div className="form-grid">
                <Field label="First Name" required>
                  <input name="first_name" value={inqForm.first_name} onChange={inqField("first_name")} placeholder="First name" required />
                </Field>
                <Field label="Middle Name">
                  <input name="middle_name" value={inqForm.middle_name} onChange={inqField("middle_name")} placeholder="Middle name" />
                </Field>
                <Field label="Last Name">
                  <input name="last_name" value={inqForm.last_name} onChange={inqField("last_name")} placeholder="Last name" />
                </Field>
                <Field label="Date of Birth">
                  <input type="date" name="date_of_birth" value={inqForm.date_of_birth} onChange={inqField("date_of_birth")} />
                </Field>
                <Field label="Gender">
                  <select name="gender" value={inqForm.gender} onChange={inqField("gender")}>
                    <option value="male">Male</option>
                    <option value="female">Female</option>
                  </select>
                </Field>
                <Field label="Phone">
                  <input name="phone" value={inqForm.phone} onChange={inqField("phone")} placeholder="03XX-XXXXXXX" />
                </Field>
                <Field label="Email">
                  <input type="email" name="email" value={inqForm.email} onChange={inqField("email")} placeholder="name@example.com" />
                </Field>
                <Field label="Address">
                  <textarea name="address" value={inqForm.address} onChange={inqField("address")} placeholder="Full address" rows="2" />
                </Field>
              </div>
            </div>

            <div className="form-section">
              <h4>Guardian / Contact</h4>
              <div className="form-grid">
                <Field label="Guardian Name">
                  <input name="guardian_name" value={inqForm.guardian_name} onChange={inqField("guardian_name")} placeholder="Guardian name" />
                </Field>
                <Field label="Guardian Relationship">
                  <input name="guardian_relationship" value={inqForm.guardian_relationship} onChange={inqField("guardian_relationship")} placeholder="e.g. Father" />
                </Field>
                <Field label="Guardian Phone">
                  <input name="guardian_phone" value={inqForm.guardian_phone} onChange={inqField("guardian_phone")} placeholder="03XX-XXXXXXX" />
                </Field>
                <Field label="Guardian Email">
                  <input type="email" name="guardian_email" value={inqForm.guardian_email} onChange={inqField("guardian_email")} placeholder="guardian@example.com" />
                </Field>
              </div>
            </div>

            <div className="form-section">
              <h4>Interested Class & Source</h4>
              <div className="form-grid">
                <Field label="Campus">
                  <select name="campus" value={inqForm.campus} onChange={inqField("campus")}>
                    <option value="">Select campus</option>
                    {campuses.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Academic Year">
                  <select name="academic_year" value={inqForm.academic_year} onChange={inqField("academic_year")}>
                    <option value="">Select year</option>
                    {academicYears.map((y) => (
                      <option key={y.id} value={y.id}>{y.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Class">
                  <select name="class_obj" value={inqForm.class_obj} onChange={inqField("class_obj")} disabled={!inqForm.campus}>
                    <option value="">Select class</option>
                    {inqClasses.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Source">
                  <select name="source" value={inqForm.source} onChange={inqField("source")}>
                    {INQUIRY_SOURCES.map(([key, label]) => (
                      <option key={key} value={key}>{label}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Source Details">
                  <input name="source_details" value={inqForm.source_details} onChange={inqField("source_details")} placeholder="Where did they hear about the school?" />
                </Field>
                <Field label="Notes">
                  <textarea name="notes" value={inqForm.notes} onChange={inqField("notes")} placeholder="Internal follow-up notes" rows="2" />
                </Field>
              </div>
            </div>

            <div className="modal-footer">
              <button type="button" className="secondary-button" onClick={() => setShowInqForm(false)} disabled={savingInq}>
                <X size={15} /> Cancel
              </button>
              <button type="submit" className="primary-button" disabled={savingInq}>
                <Check size={15} /> {savingInq ? "Saving..." : "Log Inquiry"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {followInquiry && (
        <Modal title={`Follow up — ${followInquiry.applicant_name}`} subtitle={followInquiry.inquiry_number} onClose={() => setFollowInquiry(null)}>
          <form onSubmit={handleFollowUp}>
            <div className="form-section">
              <div className="form-grid">
                <Field label="Pipeline status">
                  <select value={followStatus} onChange={(event) => setFollowStatus(event.target.value)}>
                    {INQUIRY_STATUSES
                      .filter(([key]) => key !== "converted")
                      .map(([key, label]) => (
                        <option key={key} value={key}>{label}</option>
                      ))}
                  </select>
                </Field>
                <Field label="Notes">
                  <textarea value={followNotes} onChange={(event) => setFollowNotes(event.target.value)} rows="3" placeholder="Record the latest interaction..." />
                </Field>
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" className="secondary-button" onClick={() => setFollowInquiry(null)} disabled={savingFollow}>
                Cancel
              </button>
              <button type="submit" className="primary-button" disabled={savingFollow}>
                <Check size={15} /> {savingFollow ? "Saving..." : "Save Follow-up"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {convertInquiry && (
        <Modal title={`Convert to application — ${convertInquiry.applicant_name}`} subtitle="Creates a draft admission application that you can submit from the Applications tab." onClose={() => setConvertInquiry(null)}>
          <form onSubmit={handleConvert}>
            <div className="form-section">
              <div className="form-grid">
                <Field label="Application number" required>
                  <input name="application_number" value={convertForm.application_number} onChange={convertField("application_number")} required />
                </Field>
                <Field label="Campus" required>
                  <select name="campus" value={convertForm.campus || ""} onChange={convertField("campus")} required>
                    <option value="">Select campus</option>
                    {campuses.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Academic Year" required>
                  <select name="academic_year" value={convertForm.academic_year || ""} onChange={convertField("academic_year")} required>
                    <option value="">Select year</option>
                    {academicYears.map((y) => (
                      <option key={y.id} value={y.id}>{y.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Class" required>
                  <select name="class_obj" value={convertForm.class_obj || ""} onChange={convertField("class_obj")} required disabled={!convertForm.campus}>
                    <option value="">Select class</option>
                    {convClasses.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Section (recommended)">
                  <select name="section" value={convertForm.section || ""} onChange={convertField("section")} disabled={!convertForm.class_obj}>
                    <option value="">Select section</option>
                    {convSections.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </Field>
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" className="secondary-button" onClick={() => setConvertInquiry(null)} disabled={savingConvert}>
                Cancel
              </button>
              <button type="submit" className="primary-button" disabled={savingConvert}>
                <UserPlus size={15} /> {savingConvert ? "Converting..." : "Convert to Application"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </section>
  );
}

function PipelineButton({ active, label, count, onClick }) {
  return (
    <button
      type="button"
      className="secondary-button secondary-button-sm"
      style={active ? { borderColor: "var(--primary)", color: "var(--primary)" } : undefined}
      onClick={onClick}
    >
      {label} <span className="pipeline-count">{count}</span>
    </button>
  );
}

function Field({ label, required, children }) {
  return (
    <label>
      {label}
      {required ? " *" : ""}
      {children}
    </label>
  );
}

function Modal({ title, subtitle, onClose, children }) {
  return (
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="teacher-modal event-modal">
        <div className="modal-header">
          <div>
            <h3>{title}</h3>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button
            className="modal-close"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
