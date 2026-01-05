// app/static/js/auth.js

const TOKEN_KEY = "access_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

// Redirects to login if missing token
export function requireAuth(redirectTo = "/static/index.html") {
  const token = getToken();
  if (!token) {
    window.location.href = redirectTo;
    return null;
  }
  return token;
}

/**
 * Wrapper for fetch that automatically adds Authorization header.
 *
 * Rules:
 * - 401: Not authenticated (missing/expired/invalid token) => clear token + redirect to login
 * - 403: Authenticated but forbidden => DO NOT clear token (caller decides what to do)
 */
export async function apiFetch(url, options = {}) {
  const token = getToken();
  if (!token) {
    window.location.href = "/static/index.html";
    throw new Error("Not logged in");
  }

  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${token}`);

  if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const resp = await fetch(url, { ...options, headers });

  if (resp.status === 401) {
    clearToken();
    window.location.href = "/static/index.html";
    throw new Error("Session expired");
  }

  // IMPORTANT: do NOT clear token on 403
  return resp;
}
