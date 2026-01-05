// app/static/app.js
const API_BASE = "http://127.0.0.1:8000";

function setToken(token) {
  localStorage.setItem("token", token);
}

function getToken() {
  return localStorage.getItem("token");
}

function clearToken() {
  localStorage.removeItem("token");
}

function authHeader() {
  const t = getToken();
  return t ? { "Authorization": `Bearer ${t}` } : {};
}

async function api(path, opts = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(opts.headers || {}),
    ...authHeader(),
  };

  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });

  // Try to parse JSON, but don't explode if it isn't JSON
  let data = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }

  if (!res.ok) {
    const msg =
      (data && data.detail) ? data.detail :
      (typeof data === "string" && data) ? data :
      `Request failed (${res.status})`;
    throw new Error(msg);
  }

  return data;
}

function requireLoginOrRedirect() {
  if (!getToken()) window.location.href = "/static/index.html";
}

function fmtDate(d) {
  try {
    return new Date(d).toLocaleString();
  } catch {
    return d || "";
  }
}
