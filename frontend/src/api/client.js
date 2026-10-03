import axios from "axios";


// Same-origin ("") in production builds served next to the API;
// the local backend during development.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000";

const TOKEN_KEY = "avianacoustics.token";

// Fired when the server rejects our token, so the app can sign out.
export const AUTH_EXPIRED_EVENT = "avianacoustics:auth-expired";


export function getStoredToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}


export function setStoredToken(token) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Private mode etc.: the session lasts until the tab closes.
  }
}


export function clearStoredToken() {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}


export const api = axios.create({
  baseURL: API_BASE_URL,
});


api.interceptors.request.use((config) => {
  const token = getStoredToken();

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});


api.interceptors.response.use(
  (response) => response,
  (error) => {
    const sentToken = Boolean(
      error.config?.headers?.Authorization
    );

    if (error.response?.status === 401 && sentToken) {
      clearStoredToken();
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }

    return Promise.reject(error);
  }
);


/**
 * A readable message from an API error: our {error, message}
 * format, FastAPI validation errors, or a network failure.
 */
export function errorMessage(error, fallback = "Something went wrong.") {
  const data = error?.response?.data;

  if (typeof data?.message === "string") {
    return data.message;
  }

  if (Array.isArray(data?.detail) && data.detail.length > 0) {
    const first = data.detail[0];
    const field = Array.isArray(first.loc)
      ? first.loc[first.loc.length - 1]
      : null;
    const message = String(first.msg ?? "").replace(/^Value error, /, "");

    return field && !message.toLowerCase().includes(String(field))
      ? `${field}: ${message}`
      : message || fallback;
  }

  if (typeof data?.detail === "string") {
    return data.detail;
  }

  if (error?.request && !error?.response) {
    return "Could not reach the server. Check your connection.";
  }

  return fallback;
}
