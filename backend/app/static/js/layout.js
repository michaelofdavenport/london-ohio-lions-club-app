// app/static/js/layout.js
import { clearToken } from "./auth.js";

const $ = (id) => document.getElementById(id);

function wire(id, fn) {
  const el = $(id);
  if (el && !el.dataset.wired) {
    el.dataset.wired = "1";
    el.addEventListener("click", fn);
  }
}

// Standard routes
wire("dashBtn", () => (window.location.href = "/static/dashboard.html"));
wire("adminToolsBtn", () => (window.location.href = "/admin/tools"));

wire("logoutBtn", () => {
  clearToken();
  window.location.href = "/static/public_request.html";
});
