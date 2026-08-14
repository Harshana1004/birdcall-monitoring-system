import axios from "axios";


const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000";


const api = axios.create({
  baseURL: API_BASE_URL,
});


export async function uploadAnalysis(
  audioFile
) {
  const formData = new FormData();

  formData.append(
    "audio_file",
    audioFile
  );

  const response = await api.post(
    "/api/v1/analysis",
    formData,
    {
      headers: {
        "Content-Type":
          "multipart/form-data",
      },
    }
  );

  return response.data;
}


export async function getAnalysis(
  captureSessionId
) {
  const response = await api.get(
    `/api/v1/analysis/${captureSessionId}`
  );

  return response.data;
}


export async function getAnalysisVisualization(
  captureSessionId
) {
  const response = await api.get(
    `/api/v1/analysis/${captureSessionId}/visualization`
  );

  return response.data;
}


export async function getAnalysisHistory(
  page = 1,
  pageSize = 20
) {
  const response = await api.get(
    "/api/v1/analysis",
    {
      params: {
        page,
        page_size: pageSize,
      },
    }
  );

  return response.data;
}

export function getRecordingAudioUrl(
  recordingId
) {
  return `${API_BASE_URL}/api/v1/recordings/${recordingId}/audio`;
}