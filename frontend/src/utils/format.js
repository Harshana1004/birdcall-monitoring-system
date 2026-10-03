// Display helpers. Times are shown in the viewer's local time zone.


const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

const dateFormat = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const timeFormat = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

const shortDayFormat = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
});

const relativeFormat = new Intl.RelativeTimeFormat(undefined, {
  numeric: "auto",
});


function toDate(value) {
  if (!value) {
    return null;
  }

  const date = value instanceof Date ? value : new Date(value);

  return Number.isNaN(date.getTime()) ? null : date;
}


export function formatDateTime(value) {
  const date = toDate(value);

  return date ? dateTimeFormat.format(date) : "—";
}


export function formatDate(value) {
  const date = toDate(value);

  return date ? dateFormat.format(date) : "—";
}


export function formatTime(value) {
  const date = toDate(value);

  return date ? timeFormat.format(date) : "—";
}


/** A calendar day from the API ("2026-10-01"), e.g. "1 Oct". */
export function formatDay(isoDay) {
  if (!isoDay) {
    return "";
  }

  const [year, month, day] = isoDay.split("-").map(Number);

  return shortDayFormat.format(new Date(year, month - 1, day));
}


const RELATIVE_STEPS = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
  ["second", 1],
];


export function formatRelative(value) {
  const date = toDate(value);

  if (!date) {
    return "never";
  }

  const seconds = (date.getTime() - Date.now()) / 1000;

  for (const [unit, size] of RELATIVE_STEPS) {
    if (Math.abs(seconds) >= size || unit === "second") {
      return relativeFormat.format(Math.round(seconds / size), unit);
    }
  }

  return "just now";
}


export function formatPercent(fraction, digits = 0) {
  if (fraction === null || fraction === undefined) {
    return "—";
  }

  return `${(fraction * 100).toFixed(digits)}%`;
}


export function formatSeconds(seconds, digits = 1) {
  if (seconds === null || seconds === undefined) {
    return "—";
  }

  return `${Number(seconds).toFixed(digits)} s`;
}


export function formatNumber(value) {
  return new Intl.NumberFormat().format(value ?? 0);
}


/** "online" (< 1 h), "idle" (< 24 h) or "offline" from a last-seen time. */
export function activityState(lastSeen) {
  const date = toDate(lastSeen);

  if (!date) {
    return "offline";
  }

  const ageHours = (Date.now() - date.getTime()) / 3_600_000;

  if (ageHours < 1) {
    return "online";
  }

  return ageHours < 24 ? "idle" : "offline";
}


export function initials(user) {
  const source = user?.display_name || user?.email || "?";
  const parts = source.split(/[\s@._-]+/).filter(Boolean);

  return (parts[0]?.[0] ?? "?").toUpperCase() +
    (parts[1]?.[0] ?? "").toUpperCase();
}


/** <input type="datetime-local"> value -> ISO string with offset. */
export function localInputToIso(value) {
  if (!value) {
    return undefined;
  }

  const date = new Date(value);

  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}
