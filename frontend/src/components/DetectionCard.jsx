function DetectionCard({
  detection,
}) {
  const percentage =
    detection.confidence * 100;

  return (
    <article className="detection-card">
      <div className="detection-heading">
        <div>
          <h4>
            {
              detection
                .common_name
            }
          </h4>

          <p className="scientific-name">
            {
              detection
                .scientific_name
            }
          </p>
        </div>

        <strong className="confidence">
          {percentage.toFixed(1)}%
        </strong>
      </div>

      <div className="confidence-track">
        <div
          className="confidence-fill"
          style={{
            width: `${Math.min(
              percentage,
              100
            )}%`,
          }}
        />
      </div>

      <div className="detection-meta">
        <span>
          Model:{" "}
          {
            detection
              .model_name
          }{" "}
          {
            detection
              .model_version
          }
        </span>
      </div>
    </article>
  );
}


export default DetectionCard;