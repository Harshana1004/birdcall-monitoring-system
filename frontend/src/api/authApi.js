import { api } from "./client";


export async function register({ email, password, displayName }) {
  const response = await api.post("/api/v1/auth/register", {
    email,
    password,
    display_name: displayName || null,
  });

  return response.data;
}


export async function login({ email, password }) {
  const response = await api.post("/api/v1/auth/login", {
    email,
    password,
  });

  return response.data;
}


export async function getMe() {
  const response = await api.get("/api/v1/auth/me");

  return response.data;
}


export async function updateMe({ displayName }) {
  const response = await api.patch("/api/v1/auth/me", {
    display_name: displayName,
  });

  return response.data;
}


export async function changePassword({ currentPassword, newPassword }) {
  await api.post("/api/v1/auth/me/password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
}
