import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatDay, formatNumber, formatPercent, formatRelative } from "../utils/format";


const COLORS = {
  grid: "#233830",
  axis: "#6c8379",
  recordings: "#2fa86c",
  detections: "#b5e655",
};


function ActivityTooltip({ active, payload, label }) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="chart-tooltip">
      <strong>{formatDay(label)}</strong>
      {payload.map((entry) => (
        <div key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}: {formatNumber(entry.value)}
        </div>
      ))}
    </div>
  );
}


/** Recordings and detections per day (from the API's daily_activity). */
export function ActivityChart({ days, tall = false }) {
  return (
    <div className={tall ? "chart-box tall" : "chart-box"}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={days} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
          <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="day"
            tickFormatter={formatDay}
            stroke={COLORS.axis}
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={{ stroke: COLORS.grid }}
            minTickGap={16}
          />
          <YAxis
            allowDecimals={false}
            stroke={COLORS.axis}
            tick={{ fontSize: 12 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip content={<ActivityTooltip />} cursor={{ fill: "rgba(47,184,114,0.08)" }} />
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 13, color: COLORS.axis }}
          />
          <Bar
            dataKey="recording_count"
            name="ROI snippets"
            fill={COLORS.recordings}
            radius={[4, 4, 0, 0]}
            maxBarSize={22}
          />
          <Bar
            dataKey="detection_count"
            name="Detections"
            fill={COLORS.detections}
            radius={[4, 4, 0, 0]}
            maxBarSize={22}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}


/** Horizontal bars for the most-detected species. */
export function SpeciesBars({ species, onSelect }) {
  const max = Math.max(1, ...species.map((item) => item.detection_count));

  return (
    <div className="bar-list">
      {species.map((item) => (
        <div
          key={item.scientific_name}
          className="bar-row"
          style={onSelect ? { cursor: "pointer" } : undefined}
          onClick={onSelect ? () => onSelect(item) : undefined}
          title={`Best confidence ${formatPercent(item.max_confidence)} · last heard ${formatRelative(item.last_detected_at)}`}
        >
          <div style={{ minWidth: 0 }}>
            <span className="species-name">{item.common_name}</span>{" "}
            <span className="species-sci">{item.scientific_name}</span>
          </div>
          <strong>{formatNumber(item.detection_count)}</strong>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{ width: `${(item.detection_count / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
