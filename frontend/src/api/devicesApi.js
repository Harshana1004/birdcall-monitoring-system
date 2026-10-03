import { api } from "./client";


export async function listDevices(params = {}) {
  const response = await api.get("/api/v1/devices", {
    params: { page_size: 100, ...params },
  });

  return response.data;
}


export async function getDevice(deviceId) {
  const response = await api.get(`/api/v1/devices/${deviceId}`);

  return response.data;
}


export async function getDeviceSummary(deviceId, days = 30) {
  const response = await api.get(`/api/v1/devices/${deviceId}/summary`, {
    params: { days },
  });

  return response.data;
}


export async function getDeviceRecordings(deviceId, params = {}) {
  const response = await api.get(`/api/v1/devices/${deviceId}/recordings`, {
    params,
  });

  return response.data;
}


export async function claimDevice({ deviceCode, claimCode }) {
  const response = await api.post("/api/v1/devices/claim", {
    device_code: deviceCode,
    claim_code: claimCode,
  });

  return response.data;
}


export async function updateDevice(deviceId, changes) {
  const response = await api.patch(`/api/v1/devices/${deviceId}`, changes);

  return response.data;
}


export async function releaseDevice(deviceId) {
  const response = await api.delete(`/api/v1/devices/${deviceId}/owner`);

  return response.data;
}


// ---- Admin ---------------------------------------------------------


export async function createDevice({ deviceCode, name, description }) {
  const response = await api.post("/api/v1/devices", {
    device_code: deviceCode,
    name,
    description: description || null,
  });

  return response.data;
}


export async function regenerateClaimCode(deviceId) {
  const response = await api.post(`/api/v1/devices/${deviceId}/claim-code`);

  return response.data;
}


export async function assignDeviceOwner(deviceId, ownerEmail) {
  const response = await api.put(`/api/v1/devices/${deviceId}/owner`, {
    owner_email: ownerEmail || null,
  });

  return response.data;
}


export async function deleteDevice(deviceId) {
  await api.delete(`/api/v1/devices/${deviceId}`);
}
