// app/static/js/admin_guard.js
import { requireAuth, apiFetch } from "./auth.js";

requireAuth();

export async function requireAdminOrRedirect() {
  try {
    const resp = await apiFetch("/admin/ping");

    // If token is valid but user isn't admin, backend should return 403
    if (resp.status === 403) {
      window.location.href = "/static/dashboard.html";
      return false;
    }

    if (!resp.ok) {
      window.location.href = "/static/dashboard.html";
      return false;
    }

    return true;
  } catch (e) {
    // apiFetch already redirects on 401
    return false;
  }
}
