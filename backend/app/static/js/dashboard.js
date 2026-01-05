// app/static/js/dashboard.js
import { requireAuth, apiFetch, clearToken } from "./auth.js";

// 🔒 Enforce login immediately (once)
requireAuth();

const $ = (id) => document.getElementById(id);

// ----------------------------
// Navigation
// ----------------------------
$("logoutBtn")?.addEventListener("click", () => {
  clearToken();
  window.location.href = "/static/public_request.html";
});

$("inboxBtn")?.addEventListener("click", () => {
  window.location.href = "/static/inbox.html";
});

$("rosterBtn")?.addEventListener("click", () => {
  window.location.href = "/static/roster.html";
});

$("eventsBtn")?.addEventListener("click", () => {
  window.location.href = "/static/events.html";
});

$("hoursBtn")?.addEventListener("click", () => {
  window.location.href = "/static/service_hours.html";
});

$("viewEventsBtn")?.addEventListener("click", () => {
  window.location.href = "/static/events.html";
});

$("viewHoursBtn")?.addEventListener("click", () => {
  window.location.href = "/static/service_hours.html";
});

// ----------------------------
// Admin Tools button (ADMIN ONLY)
// Requires dashboard.html to include:
// <button class="btn btn-nav" id="adminToolsBtn" style="display:none;">Admin Tools</button>
//
// IMPORTANT:
// - /admin/tools is an API route (JSON) and WILL 401 in the address bar.
// - Admin UI should be a static page that uses apiFetch() to call admin APIs.
// ----------------------------
async function setupAdminToolsButton() {
  const btn = $("adminToolsBtn");
  if (!btn) return;

  try {
    const resp = await apiFetch("/member/me");
    if (!resp.ok) return;

    const me = await resp.json();

    if (me?.is_admin) {
      btn.style.display = "inline-flex";
      btn.addEventListener("click", () => {
        // ✅ go to the HTML page
        window.location.href = "/static/admin_tools.html";
      });
    }
  } catch (err) {
    console.error("Admin check failed:", err);
  }
}

// ----------------------------
// Helpers
// ----------------------------
function setBar(el, part, total) {
  if (!el) return;
  const pct = total ? Math.round((part / total) * 100) : 0;
  el.style.width = pct + "%";
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// Events backend values are "UTC-naive" strings like "2026-01-06T18:30:00"
// Treat them as UTC by appending Z, then display local.
function parseUtcNaiveAsDate(utcNaiveString) {
  return new Date(utcNaiveString + "Z");
}

function formatLocalDateTime(dateObj) {
  const d = new Intl.DateTimeFormat("en-US", {
    month: "2-digit",
    day: "2-digit",
    year: "numeric",
  }).format(dateObj);

  const t = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(dateObj);

  return `${d} ${t}`;
}

// ----------------------------
// Widget 1: Requests Metrics
// ----------------------------
async function loadRequestMetrics() {
  try {
    const resp = await apiFetch("/member/requests/summary");
    const data = await resp.json();

    const total = data.total || 0;
    const by = data.by_status || {};

    const approved = by.APPROVED || 0;
    const pending = by.PENDING || 0;

    $("totalCount").textContent = total;
    $("approvedCount").textContent = approved;
    $("pendingCount").textContent = pending;

    setBar($("approvedBar"), approved, total);
    setBar($("pendingBar"), pending, total);
  } catch (err) {
    console.error("Dashboard metrics load failed:", err);
    $("totalCount").textContent = "ERR";
    $("approvedCount").textContent = "ERR";
    $("pendingCount").textContent = "ERR";
    setBar($("approvedBar"), 0, 1);
    setBar($("pendingBar"), 0, 1);
  }
}

// ----------------------------
// Widget 2: Upcoming Events (Next 2)
// ----------------------------
function renderUpcomingEvents(events) {
  const list = $("upcomingEventsList");
  const hint = $("upcomingEventsHint");

  list.innerHTML = "";

  if (!events || events.length === 0) {
    hint.textContent = "No upcoming events.";
    return;
  }

  hint.textContent = "";

  for (const ev of events.slice(0, 2)) {
    const start = ev.start_at ? parseUtcNaiveAsDate(ev.start_at) : null;
    const end = ev.end_at ? parseUtcNaiveAsDate(ev.end_at) : null;

    const when = start
      ? end
        ? `${formatLocalDateTime(start)} → ${formatLocalDateTime(end)}`
        : formatLocalDateTime(start)
      : "—";

    const item = document.createElement("div");
    item.className = "event-item";
    item.innerHTML = `
      <div class="event-when">${escapeHtml(when)}</div>
      <div class="event-title">${escapeHtml(ev.title || "Untitled")}</div>
      <div class="event-loc">${escapeHtml(ev.location || "—")}</div>
    `;
    list.appendChild(item);
  }
}

async function loadUpcomingEvents() {
  $("upcomingEventsHint").textContent = "Loading…";
  try {
    // Prefer member endpoint (includes private). If it doesn't exist, fallback to public.
    let resp = await apiFetch("/member/events?include_past=false").catch(() => null);

    if (!resp || !resp.ok) {
      resp = await fetch("/public/events?include_past=false");
    }

    if (!resp.ok) throw new Error("Failed to load events");

    const data = await resp.json();
    data.sort((a, b) => (a.start_at || "").localeCompare(b.start_at || ""));
    renderUpcomingEvents(data);
  } catch (err) {
    console.error("Upcoming events load failed:", err);
    $("upcomingEventsHint").textContent = "Failed to load upcoming events.";
    renderUpcomingEvents([]);
  }
}

// ----------------------------
// Widget 3: Service Hours YTD (CLUB-WIDE)
// Uses backend endpoint: GET /member/service-hours/summary
// Fallback: computes from current member entries if summary endpoint unavailable
// ----------------------------
function computeMemberYtdHours(entries) {
  const year = new Date().getFullYear();
  let total = 0;

  for (const e of entries || []) {
    if (!e.service_date) continue; // "YYYY-MM-DD"
    const y = Number(String(e.service_date).slice(0, 4));
    if (y !== year) continue;

    const hrs = Number(e.hours || 0);
    if (!Number.isFinite(hrs)) continue;
    total += hrs;
  }

  return total;
}

async function loadServiceHoursYtdClubWide() {
  $("hoursYtdHint").textContent = "Loading…";
  $("hoursYtdValue").textContent = "—";

  // 1) Preferred: club-wide endpoint
  try {
    const resp = await apiFetch("/member/service-hours/summary");
    if (!resp.ok) throw new Error("Summary endpoint not available");

    const data = await resp.json();
    const year = data.year ?? new Date().getFullYear();
    const clubYtd = Number(data.club_ytd_hours ?? 0);

    $("hoursYtdValue").textContent = Number.isFinite(clubYtd) ? clubYtd.toFixed(1) : "0.0";
    $("hoursYtdHint").textContent = `Club-wide YTD total for ${year}.`;
    return;
  } catch (err) {
    console.warn("Club-wide summary unavailable, falling back:", err);
  }

  // 2) Fallback: compute from current member entries (keeps UI alive)
  try {
    const resp = await apiFetch("/member/service-hours");
    if (!resp.ok) throw new Error("Failed to load service hours");

    const data = await resp.json();
    const ytd = computeMemberYtdHours(data);

    $("hoursYtdValue").textContent = ytd.toFixed(1);
    $("hoursYtdHint").textContent = `YTD total for ${new Date().getFullYear()} (fallback: this member).`;
  } catch (err) {
    console.error("Service hours YTD load failed:", err);
    $("hoursYtdValue").textContent = "ERR";
    $("hoursYtdHint").textContent = "Failed to load service hours.";
  }
}

// ----------------------------
// Initial load
// ----------------------------
setupAdminToolsButton();
loadRequestMetrics();
loadUpcomingEvents();
loadServiceHoursYtdClubWide();
