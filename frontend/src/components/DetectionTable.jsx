import { Link } from "react-router-dom";

import { formatDateTime, formatRelative } from "../utils/format";
import RecordingAudio from "./RecordingAudio";
import { ConfidenceBadge, SpeciesName } from "./ui";


/** Detection feed rows (DetectionFeedItem from the API). */
function DetectionTable({ detections, showDevice = true }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Heard at</th>
            <th>Species</th>
            <th>Confidence</th>
            {showDevice && <th>Device</th>}
            <th>Snippet</th>
          </tr>
        </thead>

        <tbody>
          {detections.map((detection) => (
            <tr key={detection.id}>
              <td style={{ whiteSpace: "nowrap" }}>
                <div>{formatDateTime(detection.detected_at)}</div>
                <div className="small faint">{formatRelative(detection.detected_at)}</div>
              </td>

              <td>
                <SpeciesName
                  common={detection.common_name}
                  scientific={detection.scientific_name}
                />
              </td>

              <td>
                <ConfidenceBadge confidence={detection.confidence} />
              </td>

              {showDevice && (
                <td>
                  <Link to={`/devices/${detection.device_id}`}>{detection.device_name}</Link>
                  <div className="small faint mono">{detection.device_code}</div>
                </td>
              )}

              <td>
                <RecordingAudio recordingId={detection.recording_id} compact />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


export default DetectionTable;
