import { useState } from "react";

import { Link } from "react-router-dom";

import { getAnalysisHistory } from "../api/analysisApi";
import { useAuth } from "../auth/AuthContext";
import {
  Alert,
  EmptyState,
  LoadingState,
  PageHeader,
  Pagination,
} from "../components/ui";
import { useApi } from "../hooks/useApi";
import { formatDateTime, formatRelative } from "../utils/format";


function AnalysisHistoryPage() {
  const { isAdmin } = useAuth();
  const [page, setPage] = useState(1);

  const { data, error, isLoading } = useApi(
    () => getAnalysisHistory(page, 20),
    [page]
  );


  return (
    <main className="page">
      <PageHeader
        eyebrow="Manual analysis"
        title={isAdmin ? "All manual analyses" : "My analyses"}
        description="WAV recordings uploaded for analysis through the website."
        actions={
          <Link to="/analysis" className="button button-primary">
            Analyse a recording
          </Link>
        }
      />

      <Alert>{error}</Alert>

      {isLoading && !data && <LoadingState />}

      {data && data.items.length === 0 && (
        <EmptyState title="No analyses yet" actionTo="/analysis" actionLabel="Upload a recording">
          Upload a WAV file to detect acoustic regions and identify the
          species with BirdNET.
        </EmptyState>
      )}

      {data && data.items.length > 0 && (
        <section className="card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Recording</th>
                  <th>Analysed</th>
                  <th>Regions</th>
                  <th>Detections</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.capture_session_id}>
                    <td className="mono">{item.original_filename}</td>
                    <td>
                      <div>{formatDateTime(item.capture_started_at)}</div>
                      <div className="small faint">{formatRelative(item.capture_started_at)}</div>
                    </td>
                    <td>{item.roi_count}</td>
                    <td>
                      <span className={item.detection_count ? "badge badge-green" : "badge"}>
                        {item.detection_count}
                      </span>
                    </td>
                    <td>
                      <Link to={`/analysis/${item.capture_session_id}`} className="button button-secondary button-small">
                        Open
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination pagination={data.pagination} onPageChange={setPage} />
        </section>
      )}
    </main>
  );
}


export default AnalysisHistoryPage;
