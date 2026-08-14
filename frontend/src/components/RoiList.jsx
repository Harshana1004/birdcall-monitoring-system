import DetectionCard from "./DetectionCard";
import {
  getRecordingAudioUrl,
} from "../api/analysisApi";


function RoiList({
  rois,
}) {
  return (
    <section className="roi-section">
      <h2>
        Detected Acoustic Regions
      </h2>

      {rois.length === 0 ? (
        <div className="empty-state">
          No acoustic regions were
          detected in this recording.
        </div>
      ) : (
        <div className="roi-list">
          {rois.map(
            (roi) => (
              <article
                key={
                  roi.recording_id
                }
                className="roi-card"
              >
                <header className="roi-header">
                  <div>
                    <h3>
                      Region{" "}
                      {
                        roi
                          .snippet_sequence +
                        1
                      }
                    </h3>

                    <span>
                      {roi
                        .roi_start_seconds
                        .toFixed(
                          2
                        )}
                      {" – "}
                      {roi
                        .roi_end_seconds
                        .toFixed(
                          2
                        )}
                      {" s"}
                    </span>
                  </div>

                  <span className="status-badge">
                    {
                      roi
                        .processing_status
                    }
                  </span>
                </header>

                <div className="roi-details">
                  <span>
                    Detected region:{" "}
                    {roi
                      .original_duration_seconds
                      .toFixed(
                        2
                      )}
                    {" s"}
                  </span>

                  <span>
                    BirdNET input:{" "}
                    {roi
                      .stored_duration_seconds
                      .toFixed(
                        2
                      )}
                    {" s"}
                  </span>
                </div>


                <div className="roi-audio">
                <span className="roi-audio-label">
                    Detected snippet
                </span>

                <audio
                    controls
                    preload="metadata"
                    src={getRecordingAudioUrl(
                    roi.recording_id
                    )}
                >
                    Your browser does not support
                    audio playback.
                </audio>
                </div>

                {roi.detections
                  .length ===
                0 ? (
                  <div className="empty-detection">
                    No species exceeded
                    the configured BirdNET
                    confidence threshold.
                  </div>
                ) : (
                  <div className="detection-list">
                    {roi.detections.map(
                      (
                        detection
                      ) => (
                        <DetectionCard
                          key={
                            detection.id
                          }
                          detection={
                            detection
                          }
                        />
                      )
                    )}
                  </div>
                )}
              </article>
            )
          )}
        </div>
      )}
    </section>
  );
}


export default RoiList;