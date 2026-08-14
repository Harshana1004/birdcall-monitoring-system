import { useRef } from "react";


function AudioUpload({
  selectedFile,
  onFileChange,
  onAnalyze,
  isProcessing,
}) {
  const inputRef = useRef(null);


  function handleFileSelection(
    event
  ) {
    const file =
      event.target.files?.[0];

    if (!file) {
      return;
    }

    onFileChange(file);
  }


  function handleDrop(
    event
  ) {
    event.preventDefault();

    const file =
      event.dataTransfer
        .files?.[0];

    if (!file) {
      return;
    }

    onFileChange(file);
  }


  function handleDragOver(
    event
  ) {
    event.preventDefault();
  }


  return (
    <section className="upload-card">
      <h2>
        Manual Audio Analysis
      </h2>

      <p className="section-description">
        Upload a WAV recording to run
        the complete bird-call
        processing and identification
        pipeline.
      </p>

      <div
        className="drop-zone"
        onClick={() =>
          inputRef.current?.click()
        }
        onDrop={handleDrop}
        onDragOver={
          handleDragOver
        }
      >
        <input
          ref={inputRef}
          type="file"
          accept=".wav,audio/wav"
          hidden
          onChange={
            handleFileSelection
          }
        />

        {selectedFile ? (
          <>
            <strong>
              {selectedFile.name}
            </strong>

            <span>
              {(
                selectedFile.size /
                1024 /
                1024
              ).toFixed(2)}{" "}
              MB
            </span>
          </>
        ) : (
          <>
            <strong>
              Select or drop a WAV
              recording
            </strong>

            <span>
              Click here or drag a
              file into this area.
            </span>
          </>
        )}
      </div>

      <button
        className="primary-button"
        type="button"
        disabled={
          !selectedFile ||
          isProcessing
        }
        onClick={onAnalyze}
      >
        {isProcessing
          ? "Analysing..."
          : "Analyse Recording"}
      </button>
    </section>
  );
}


export default AudioUpload;