import {
  useEffect,
  useState,
} from "react";

import {
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";

import {
  getAnalysis,
} from "../api/analysisApi";

import AnalysisSummary from "../components/AnalysisSummary";
import RoiList from "../components/RoiList";


function AnalysisResultsPage() {
  const {
    captureSessionId,
  } = useParams();

  const location =
    useLocation();

  const navigate =
    useNavigate();

  const [
    analysis,
    setAnalysis,
  ] = useState(
    location.state?.analysis ??
      null
  );

  const [
    isLoading,
    setIsLoading,
  ] = useState(
    !location.state?.analysis
  );

  const [
    error,
    setError,
  ] = useState(null);


  useEffect(
    () => {
      if (analysis) {
        return;
      }

      async function loadAnalysis() {
        try {
          const result =
            await getAnalysis(
              captureSessionId
            );

          setAnalysis(
            result
          );

        } catch (requestError) {
          console.error(
            requestError
          );

          setError(
            "The analysis could not be loaded."
          );

        } finally {
          setIsLoading(
            false
          );
        }
      }

      loadAnalysis();

    },
    [
      captureSessionId,
      analysis,
    ]
  );


  if (isLoading) {
    return (
      <main className="page">
        <div className="processing-card">
          Loading analysis...
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


  if (!analysis) {
    return null;
  }


  return (
    <main className="page">
      <header className="page-header">
        <span className="eyebrow">
          Manual Audio Analysis
        </span>

        <h1>
          Analysis Results
        </h1>

        <p>
          {
            analysis
              .original_filename
          }
        </p>
      </header>


      <div className="page-actions">
        <button
          className="secondary-button"
          type="button"
          onClick={() =>
            navigate(
              "/analysis"
            )
          }
        >
          Analyse Another Recording
        </button>

        <button
          className="primary-button"
          type="button"
          onClick={() =>
            navigate(
              `/analysis/${captureSessionId}/visualization`
            )
          }
        >
          View Processing Graphs
        </button>
      </div>


      <AnalysisSummary
        analysis={
          analysis
        }
      />


      <RoiList
        rois={
          analysis.rois
        }
      />
    </main>
  );
}


export default AnalysisResultsPage;