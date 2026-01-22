// app/static/js/auth.js
// Shared auth helpers for ALL pages.
//
// This version is backwards-compatible:
// - reads token from access_token OR token (and a couple legacy keys)
// - always attaches Authorization: Bearer <token> in apiFetch()
// - clears tokens on 401

const PRIMARY_KEY = "access_token";
const FALLBACK_KEYS = ["token", "jwt", "auth_token"];

function getToken() {
  // Primary key first
  let t = localStorage.getItem(PRIMARY_KEY) || sessionStorage.getItem(PRIMARY_KEY);
  if (t) return t;

  // Fallback keys
  for (const k of FALLBACK_KEYS) {
    t = localStorage.getItem(k) || sessionStorage.getItem(k);
    if (t) return t;
  }
  return null;
}

export function setToken(token) {
  const t = String(token || "").trim();
  if (!t) return;

  // Store to primary + keep "token" for old code
  localStorage.setItem(PRIMARY_KEY, t);
  localStorage.setItem("token", t);
  sessionStorage.setItem(PRIMARY_KEY, t);
  sessionStorage.setItem("token", t);
}

export function clearToken() {
  localStorage.removeItem(PRIMARY_KEY);
  sessionStorage.removeItem(PRIMARY_KEY);

  for (const k of FALLBACK_KEYS) {
    localStorage.removeItem(k);
    sessionStorage.removeItem(k);
  }

  // also remove plain "token" (some code uses it directly)
  localStorage.removeItem("token");
  sessionStorage.removeItem("token");
}

export function requireAuth() {
  const t = getToken();
  if (!t) {
    window.location.href = "/static/index.html";
    return false;
  }
  return true;
}

export async function apiFetch(url, options = {}) {
  const token = getToken();

  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");

  // Set JSON content-type automatically when sending a body (unless already set)
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const resp = await fetch(url, { ...options, headers });

  // If token is invalid/expired, clear it so UI can redirect cleanly
  if (resp.status === 401) {
    clearToken();
  }

  return resp;
}
