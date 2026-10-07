import { Link, useNavigate } from "react-router-dom";

import { getDashboard } from "../api/activityApi";
import { useAuth } from "../auth/AuthContext";
import { ActivityChart, SpeciesBars } from "../components/charts";
import DetectionTable from "../components/DetectionTable";
import {
  Alert,
  EmptyState,
  LiveIndicator,
  LoadingState,
  PageHeader,
  StatCard,
} from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useNewIds, usePolling } from "../hooks/usePolling";
import { formatNumber, formatRelative } from "../utils/format";


const REFRESH_SECONDS = 15;


function DashboardPage() {
  const { user, isAdmin } = useAuth();
  const navigate = useNavigate();

  const { data, error, isLoading, reload } = useApi(
    () => getDashboard({ days: 14, recent: 8 }),
    []
  );

  usePolling(() => reload({ silent: true }), REFRESH_SECONDS * 1000);
  const newDetections = useNewIds(data?.recent_detections);

  const name = user?.display_name || user?.email?.split("@")[0];


  return (
    <main className="page">
      <PageHeader
        eyebrow={
          <span className="row" style={{ gap: 12 }}>
            {isAdmin ? "Overview · all devices" : "Overview"}
            <LiveIndicator seconds={REFRESH_SECONDS} />
          </span>
        }
        //title={`Welcome back, ${name}`}
        description="What your monitoring devices have been hearing."
        actions={
          <>
            <Link to="/detections" className="button button-secondary">
              All detections
            </Link>
            <Link to="/devices" className="button button-primary">
              My devices
            </Link>
          </>
        }
      />

      <Alert>{error}</Alert>

      {isLoading && !data && <LoadingState label="Loading your dashboard…" />}

      {data && data.device_count === 0 && (
        <EmptyState
          title="No devices yet"
          actionTo="/devices?add=1"
          actionLabel="Add a device"
        >
          Add your AvianAcoustics device using the device code and claim code
          that came with it. Its recordings and detections will show up here.
        </EmptyState>
      )}

      {data && data.device_count > 0 && (
        <>
          <div className="stats-grid">
            <StatCard
              label="Devices"
              value={formatNumber(data.device_count)}
              hint={`${data.active_device_count} active`}
            />
            <StatCard
              label="Detections (24 h)"
              value={formatNumber(data.detections_last_24h)}
              hint={`${formatNumber(data.detection_count)} all time`}
              accent
            />
            <StatCard
              label="ROI snippets (24 h)"
              value={formatNumber(data.recordings_last_24h)}
              hint={`${formatNumber(data.recording_count)} all time`}
            />
            <StatCard
              label="Species identified"
              value={formatNumber(data.species_count)}
              hint="all time"
            />
            <StatCard
              label="Last upload"
              value={data.last_recording_at ? formatRelative(data.last_recording_at) : "—"}
              hint={data.last_recording_at ? "most recent ROI" : "nothing yet"}
            />
          </div>

          <div className="grid grid-2">
            <section className="card">
              <div className="card-header">
                <div>
                  <h2>Activity</h2>
                  <p>ROI snippets and detections per day, last 14 days.</p>
                </div>
              </div>
              <ActivityChart days={data.daily_activity} />
            </section>

            <section className="card">
              <div className="card-header">
                <div>
                  <h2>Top species</h2>
                  <p>Most frequently detected, all time.</p>
                </div>
              </div>

              {data.top_species.length === 0 ? (
                <div className="empty-detection">No species detected yet.</div>
              ) : (
                <SpeciesBars
                  species={data.top_species}
                  onSelect={(item) =>
                    navigate(`/detections?species=${encodeURIComponent(item.common_name)}`)
                  }
                />
              )}
            </section>
          </div>

          <section className="card" style={{ marginTop: 16 }}>
            <div className="card-header">
              <div>
                <h2>Latest detections</h2>
                <p>The most recent species identifications from your devices.</p>
              </div>
              <Link to="/detections" className="button button-ghost button-small">
                View full history →
              </Link>
            </div>

            {data.recent_detections.length === 0 ? (
              <div className="empty-detection">
                No detections yet. Once your device uploads a bird call, it
                appears here.
              </div>
            ) : (
              <DetectionTable detections={data.recent_detections} highlightIds={newDetections} />
            )}
          </section>
        </>
      )}
    </main>
  );
}


export default DashboardPage;
