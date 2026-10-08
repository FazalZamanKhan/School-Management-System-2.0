export function PageHeader({ crumb, title, subtitle, action, hero, stats }) {
  if (hero) {
    return (
      <div className="deco-hero">
        <p className="deco-hero-tag">{crumb}</p>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
        {action && <div className="deco-hero-actions">{action}</div>}
        {Array.isArray(stats) && stats.length > 0 && (
          <div className="deco-strip" style={{ marginTop: "1.4rem" }}>
            {stats.map((stat) => (
              <div key={stat.label} className="deco-stat">
                <div className="deco-stat-top">
                  <div className="deco-stat-chip">{stat.icon}</div>
                </div>
                <div className="deco-stat-value">
                  {typeof stat.value === "number"
                    ? stat.value.toLocaleString()
                    : stat.value}
                </div>
                <div className="deco-stat-label">{stat.label}</div>
                {stat.sub && <div className="deco-stat-sub">{stat.sub}</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="page-header">
      <div>
        <div className="breadcrumb">{crumb}</div>
        <h2>{title}</h2>
        <p className="subtitle">{subtitle}</p>
      </div>
      {action && <div>{action}</div>}
    </div>
  );
}

export function PanelHeader({ title, subtitle, count, action }) {
  return (
    <div className="teacher-list-header">
      <div>
        <h3>{title}</h3>
        <p>
          {count !== null && count !== undefined
            ? [count.toLocaleString(), subtitle].filter(Boolean).join(" ")
            : subtitle}
        </p>
      </div>
      {action}
    </div>
  );
}

export function Skeleton({ className = "", style }) {
  return <div className={`skeleton ${className}`.trim()} style={style} aria-hidden="true" />;
}

export function SkeletonBlock({ rows = 6, text }) {
  return (
    <div className="skeleton-block" role="status" aria-label={text || "Loading"}>
      <div className="skeleton-block-head">
        <Skeleton className="skeleton-chip" style={{ width: 180 }} />
        <Skeleton className="skeleton-chip" style={{ width: 110 }} />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div className="skeleton-row" key={i}>
          <Skeleton style={{ flex: 1.2, height: 14 }} />
          <Skeleton style={{ flex: 0.8, height: 14 }} />
          <Skeleton style={{ width: 64, height: 14 }} />
        </div>
      ))}
      <div className="sr-only">{text || "Loading"}</div>
    </div>
  );
}

export function StateArea({
  loading,
  error,
  loadingText = "Loading data...",
  errorTitle = "Unable to load data.",
  errorText,
  onRetry,
  children,
  skeletonRows,
  skeleton,
}) {
  if (loading) {
    return skeleton !== false ? <SkeletonBlock rows={skeletonRows} text={loadingText} /> : <div className="state-card">{loadingText}</div>;
  }

  if (error) {
    return (
      <div className="state-card error">
        <strong>{errorTitle}</strong>
        <span>{errorText || error}</span>
        {onRetry && (
          <button className="secondary-button" onClick={onRetry}>
            Try Again
          </button>
        )}
      </div>
    );
  }

  return children;
}

export function EmptyState({ icon: Icon, title, message, action }) {
  return (
    <div className="empty-state">
      {Icon && <Icon size={42} strokeWidth={1.5} />}
      <h3>{title}</h3>
      <p>{message}</p>
      {action}
    </div>
  );
}

export function Pagination({
  count,
  page,
  next,
  previous,
  onPage,
  pageSize = 20,
}) {
  if (!count) {
    return null;
  }

  const totalPages = Math.max(1, Math.ceil(count / pageSize));

  return (
    <div className="pagination">
      <button disabled={!previous} onClick={() => onPage(page - 1)}>
        Previous
      </button>
      <span>
        Page {page} of {totalPages}
      </span>
      <button disabled={!next} onClick={() => onPage(page + 1)}>
        Next
      </button>
    </div>
  );
}

export function StatusBadge({ status, label }) {
  const safe = (status || "").toLowerCase();

  const tone = [
    "active", "present", "paid", "completed", "pass", "scheduled", "cancelled",
  ].includes(safe)
    ? safe === "cancelled"
      ? "inactive"
      : "active"
    : ["inactive", "absent", "fail", "overdue"].includes(safe)
    ? "inactive"
    : ["late", "pending", "partial"].includes(safe)
    ? "warn"
    : "info";

  return (
    <span className={`status-badge ${tone}`}>
      {label || (status ? status.charAt(0).toUpperCase() + status.slice(1) : "\u2014")}
    </span>
  );
}

export function Button({ variant = "primary", className = "", children, ...props }) {
  const base = variant === "primary" ? "primary-button" : "secondary-button";
  return (
    <button type="button" className={`${base} ${className}`.trim()} {...props}>
      {children}
    </button>
  );
}

export function StatCard({ label, value, icon: Icon, sub }) {
  return (
    <div className="stat-card">
      {Icon && (
        <div className="stat-icon">
          <Icon size={18} />
        </div>
      )}
      <div className="stat-info">
        <span>{label}</span>
        <strong>{typeof value === "number" ? value.toLocaleString() : value}</strong>
        {sub && <small>{sub}</small>}
      </div>
    </div>
  );
}

export function TabButton({ active, onClick, icon: Icon, children }) {
  return (
    <button
      type="button"
      className={`tab-button ${active ? "active" : ""}`.trim()}
      onClick={onClick}
    >
      {Icon && <Icon size={15} style={{ verticalAlign: "-2px", marginRight: 6 }} />}
      {children}
    </button>
  );
}

export function Badge({ tone = "info", children }) {
  return <span className={`status-badge ${tone}`}>{children}</span>;
}
