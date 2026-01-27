// app/static/js/auth.js
// Shared auth helpers for ALL pages.
//
// Backwards-compatible:
// - reads token from access_token OR token (and legacy keys)
// - apiFetch() attaches Authorization: Bearer <token>
// - clears tokens on 401

const PRIMARY_KEY = "access_token";
const FALLBACK_KEYS = ["token", "jwt", "auth_token"];

export function getToken() {
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

  // Only auto-set JSON when it looks like JSON.
  // Leave FormData alone (browser sets multipart boundary).
  if (options.body && !headers.has("Content-Type")) {
    if (options.body instanceof URLSearchParams) {
      headers.set("Content-Type", "application/x-www-form-urlencoded");
    } else if (options.body instanceof FormData) {
      // don't set Content-Type
    } else {
      headers.set("Content-Type", "application/json");
    }
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const resp = await fetch(url, { ...options, headers });

  if (resp.status === 401) {
    clearToken();
  }

  return resp;
}
