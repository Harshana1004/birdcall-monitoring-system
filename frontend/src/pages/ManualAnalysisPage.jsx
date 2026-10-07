import {
  useState,
} from "react";

import {
  Link,
  useNavigate,
} from "react-router-dom";

import {
  uploadAnalysis,
} from "../api/analysisApi";

import {
  errorMessage,
} from "../api/client";

import AudioUpload from "../components/AudioUpload";
import ProcessingIndicator from "../components/ProcessingIndicator";
import {
  PageHeader,
} from "../components/ui";


function ManualAnalysisPage() {
  const navigate =
    useNavigate();

  const [
    selectedFile,
    setSelectedFile,
  ] = useState(null);

  const [
    isProcessing,
    setIsProcessing,
  ] = useState(false);

  const [
    error,
    setError,
  ] = useState(null);


  async function handleAnalyze() {
    if (!selectedFile) {
      return;
    }

    setIsProcessing(true);
    setError(null);

    try {
      const result =
        await uploadAnalysis(
          selectedFile
        );

      navigate(
        `/analysis/${result.capture_session_id}`,
        {
          state: {
            analysis: result,
          },
        }
      );

    } catch (requestError) {
      console.error(
        requestError
      );

      const message =
        errorMessage(
          requestError,
          "The recording could not be analysed."
        );

      setError(
        message
      );

    } finally {
      setIsProcessing(
        false
      );
    }
  }


  return (
    <main className="page">
      <PageHeader
        eyebrow="Manual analysis"
        title="Analyse a recording"
        description={
          "Upload a WAV or MP3 recording to detect acoustic " +
          "regions and identify bird species using BirdNET."
        }
        actions={
          <Link
            to="/analysis/history"
            className="button button-secondary"
          >
            My analyses
          </Link>
        }
      />


      <AudioUpload
        selectedFile={
          selectedFile
        }
        onFileChange={
          setSelectedFile
        }
        onAnalyze={
          handleAnalyze
        }
        isProcessing={
          isProcessing
        }
      />


      {isProcessing && (
        <ProcessingIndicator />
      )}


      {error && (
        <div className="error-card">
          {error}
        </div>
      )}
    </main>
  );
}


export default ManualAnalysisPage;