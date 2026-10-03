import { api } from "./client";


export async function getDashboard(params = {}) {
  const response = await api.get("/api/v1/dashboard", { params });

  return response.data;
}


export async function listDetections(params = {}) {
  const response = await api.get("/api/v1/detections", { params });

  return response.data;
}


export async function listUsers(params = {}) {
  const response = await api.get("/api/v1/users", {
    params: { page_size: 100, ...params },
  });

  return response.data;
}


export async function updateUser(userId, changes) {
  const response = await api.patch(`/api/v1/users/${userId}`, changes);

  return response.data;
}


/**
 * Download one ROI snippet with the user's credentials and return a
 * blob: URL for an <audio> element (plain src URLs cannot carry the
 * Authorization header). Revoke it with URL.revokeObjectURL.
 */
export async function fetchRecordingAudioUrl(recordingId) {
  const response = await api.get(
    `/api/v1/recordings/${recordingId}/audio`,
    { responseType: "blob" }
  );

  return URL.createObjectURL(response.data);
}
