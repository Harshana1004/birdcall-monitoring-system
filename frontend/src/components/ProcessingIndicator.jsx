function ProcessingIndicator() {
  return (
    <section className="processing-card">
      <div className="spinner" />

      <div>
        <h3>
          Processing recording
        </h3>

        <p>
          Detecting acoustic regions
          and running batched BirdNET
          inference...
        </p>
      </div>
    </section>
  );
}


export default ProcessingIndicator;