// app/static/js/admin_guard.js
import { apiFetch, clearToken } from "./auth.js";

export async function requireAdminOrRedirect() {
  try {
    const resp = await apiFetch("/admin/ping");

    // Not logged in (token missing/expired/invalid)
    if (resp.status === 401) {
      clearToken();
      window.location.href = "/static/index.html"; // your login page
      return false;
    }

    // Logged in, but not allowed (not admin/owner)
    if (resp.status === 403) {
      window.location.href = "/static/dashboard.html?err=not_admin";
      return false;
    }

    if (!resp.ok) {
      console.error("admin/ping failed:", resp.status);
      window.location.href = "/static/dashboard.html";
      return false;
    }

    const data = await resp.json().catch(() => ({}));
    const role = String(data.role || "").toUpperCase();

    if (role !== "OWNER" && role !== "ADMIN") {
      window.location.href = "/static/dashboard.html?err=not_admin";
      return false;
    }

    return true;
  } catch (err) {
    console.error("requireAdminOrRedirect error:", err);
    window.location.href = "/static/dashboard.html";
    return false;
  }
}
