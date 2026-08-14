function AnalysisSummary({
  analysis,
}) {
  const processing =
    analysis.processing;

  return (
    <section className="summary-section">
      <h2>
        Analysis Summary
      </h2>

      <div className="summary-grid">
        <div className="metric-card">
          <span className="metric-label">
            Recording
          </span>

          <strong>
            {
              analysis
                .original_filename
            }
          </strong>
        </div>

        <div className="metric-card">
          <span className="metric-label">
            Duration
          </span>

          <strong>
            {processing
              .duration_seconds
              .toFixed(1)}
            {" s"}
          </strong>
        </div>

        <div className="metric-card">
          <span className="metric-label">
            Regions detected
          </span>

          <strong>
            {
              processing
                .roi_count
            }
          </strong>
        </div>

        <div className="metric-card">
          <span className="metric-label">
            BirdNET detections
          </span>

          <strong>
            {
              processing
                .detection_count
            }
          </strong>
        </div>

        <div className="metric-card">
          <span className="metric-label">
            Sample rate
          </span>

          <strong>
            {
              processing
                .sample_rate
            }{" "}
            Hz
          </strong>
        </div>

        <div className="metric-card">
          <span className="metric-label">
            High-pass filter
          </span>

          <strong>
            {
              processing
                .high_pass_cutoff_hz
            }{" "}
            Hz
          </strong>
        </div>
      </div>
    </section>
  );
}


export default AnalysisSummary;