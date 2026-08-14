import {
  useEffect,
  useState,
} from "react";

import {
  useNavigate,
  useParams,
} from "react-router-dom";

import {
  getAnalysisVisualization,
} from "../api/analysisApi";

import AudioVisualization from "../components/AudioVisualization";


function AnalysisVisualizationPage() {
  const {
    captureSessionId,
  } = useParams();

  const navigate =
    useNavigate();

  const [
    visualization,
    setVisualization,
  ] = useState(null);

  const [
    isLoading,
    setIsLoading,
  ] = useState(true);

  const [
    error,
    setError,
  ] = useState(null);


  useEffect(
    () => {
      async function loadVisualization() {
        try {
          const result =
            await getAnalysisVisualization(
              captureSessionId
            );

          setVisualization(
            result
          );

        } catch (requestError) {
          console.error(
            requestError
          );

          setError(
            "The audio processing graphs could not be loaded."
          );

        } finally {
          setIsLoading(
            false
          );
        }
      }

      loadVisualization();

    },
    [
      captureSessionId,
    ]
  );


  if (isLoading) {
    return (
      <main className="page">
        <div className="processing-card">
          Loading audio processing
          data...
        </div>
      </main>
    );
  }


  if (error) {
    return (
      <main className="page">
        <div className="error-card">
          {error}
        </div>
      </main>
    );
  }


  return (
    <main className="page">
      <header className="page-header">
        <span className="eyebrow">
          Signal Processing
        </span>

        <h1>
          Audio Processing Visualization
        </h1>

        <p>
          Inspect the normalized waveform,
          short-time energy signal and
          regions selected for BirdNET
          analysis.
        </p>
      </header>


      <div className="page-actions">
        <button
          className="secondary-button"
          type="button"
          onClick={() =>
            navigate(
              `/analysis/${captureSessionId}`
            )
          }
        >
          Back to Results
        </button>
      </div>


      {visualization && (
        <AudioVisualization
          visualization={
            visualization
          }
        />
      )}
    </main>
  );
}


export default AnalysisVisualizationPage;