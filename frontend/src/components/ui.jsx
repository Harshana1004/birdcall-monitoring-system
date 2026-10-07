// Small presentational building blocks shared by the pages.

import { Link } from "react-router-dom";

import { formatPercent } from "../utils/format";


export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>

      {actions && <div className="header-actions">{actions}</div>}
    </header>
  );
}


export function StatCard({ label, value, hint, accent = false }) {
  return (
    <div className={accent ? "stat-card accent" : "stat-card"}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  );
}


export function LoadingState({ label = "Loading…" }) {
  return (
    <div className="loading-state" role="status">
      <div className="spinner" />
      <span>{label}</span>
    </div>
  );
}


export function EmptyState({ title, children, actionTo, actionLabel, onAction }) {
  return (
    <div className="empty-state">
      {title && <h3>{title}</h3>}
      {children && <div>{children}</div>}

      {actionTo && (
        <Link to={actionTo} className="button button-primary">
          {actionLabel}
        </Link>
      )}

      {onAction && (
        <button type="button" className="button button-primary" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}


export function Alert({ kind = "error", children }) {
  if (!children) {
    return null;
  }

  return (
    <div className={`alert alert-${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}


export function ConfidenceBadge({ confidence }) {
  const kind =
    confidence >= 0.7 ? "badge-green" : confidence >= 0.4 ? "badge-lime" : "badge-warning";

  return (
    <span className={`badge ${kind}`} title="BirdNET confidence">
      {formatPercent(confidence)}
    </span>
  );
}


/** Pulsing "Live" marker for pages that refresh themselves. */
export function LiveIndicator({ seconds }) {
  return (
    <span className="live-indicator" title={`Refreshes every ${seconds} s`}>
      <span className="live-dot" />
      Live
    </span>
  );
}


export function SpeciesName({ common, scientific }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div className="species-name">{common}</div>
      <div className="species-sci">{scientific}</div>
    </div>
  );
}


export function Pagination({ pagination, onPageChange }) {
  if (!pagination || pagination.total_pages <= 1) {
    return null;
  }

  const { page, total_pages: totalPages, total_items: totalItems } = pagination;

  return (
    <div className="pagination">
      <span>
        Page {page} of {totalPages} · {totalItems} total
      </span>

      <div className="row">
        <button
          type="button"
          className="button button-secondary button-small"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          ← Newer
        </button>
        <button
          type="button"
          className="button button-secondary button-small"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Older →
        </button>
      </div>
    </div>
  );
}
