import {
  useState,
} from "react";

import {
  useNavigate,
} from "react-router-dom";

import {
  uploadAnalysis,
} from "../api/analysisApi";

import AudioUpload from "../components/AudioUpload";
import ProcessingIndicator from "../components/ProcessingIndicator";


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
        requestError
          ?.response
          ?.data
          ?.message ??
        "The recording could not be analysed.";

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
      <header className="page-header">
        <span className="eyebrow">
          BirdCall Monitoring System
        </span>

        <h1>
          Bird Audio Analysis
        </h1>

        <p>
          Upload a WAV recording to
          detect acoustic regions and
          identify bird species using
          BirdNET.
        </p>
      </header>


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