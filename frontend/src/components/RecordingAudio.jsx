import {
  useEffect,
  useState,
} from "react";

import { fetchRecordingAudioUrl } from "../api/activityApi";
import { errorMessage } from "../api/client";


/**
 * Play button for one ROI snippet. The WAV is only downloaded when
 * asked for (with the user's credentials) and then shown in a normal
 * audio player.
 */
function RecordingAudio({ recordingId, autoPlay = true, compact = false }) {
  const [url, setUrl] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);


  useEffect(() => {
    return () => {
      if (url) {
        URL.revokeObjectURL(url);
      }
    };
  }, [url]);


  async function load() {
    setIsLoading(true);
    setError(null);

    try {
      setUrl(await fetchRecordingAudioUrl(recordingId));
    } catch (requestError) {
      setError(errorMessage(requestError, "Audio unavailable."));
    } finally {
      setIsLoading(false);
    }
  }


  if (url) {
    return (
      <div className="audio-player">
        <audio controls autoPlay={autoPlay} src={url} preload="auto">
          Your browser does not support audio playback.
        </audio>
      </div>
    );
  }


  return (
    <div className="audio-player">
      <button
        type="button"
        className={compact ? "button button-secondary button-small" : "button button-secondary"}
        onClick={load}
        disabled={isLoading}
        title="Play this ROI snippet"
      >
        {isLoading ? (
          <span className="spinner small" />
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M7 4.5v15l13-7.5z" fill="currentColor" />
          </svg>
        )}
        {compact ? "Play" : "Play snippet"}
      </button>

      {error && <span className="small" style={{ color: "var(--danger)" }}>{error}</span>}
    </div>
  );
}


export default RecordingAudio;
