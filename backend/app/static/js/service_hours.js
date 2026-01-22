// app/static/js/service_hours.js
import { apiFetch, clearToken, requireAuth } from "./auth.js";

requireAuth();

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function displayMemberName(m) {
  const name = (m?.full_name || "").trim();
  return name ? name : (m?.email || "—");
}

function toISODateOnly(v) {
  if (!v) return "";
  const s = String(v);
  return s.length >= 10 ? s.slice(0, 10) : s;
}

function toMMDDYYYY(v) {
  // expects YYYY-MM-DD from <input type="date">
  if (!v) return "";
  const [y, m, d] = String(v).split("-");
  if (!y || !m || !d) return String(v);
  return `${m}/${d}/${y}`;
}

function toYYYYMMDD(v) {
  // accepts "MM/DD/YYYY" or "YYYY-MM-DD"
  if (!v) return "";
  const s = String(v).trim();
  if (s.includes("-")) return s.slice(0, 10);
  const parts = s.split("/");
  if (parts.length !== 3) return s;
  const [mm, dd, yyyy] = parts;
  return `${yyyy}-${mm.padStart(2, "0")}-${dd.padStart(2, "0")}`;
}

// ----------------------------
// NAV
// ----------------------------
$("logoutBtn")?.addEventListener("click", () => {
  clearToken();
  window.location.href = "/static/public_request.html";
});
$("dashBtn")?.addEventListener("click", () => (window.location.href = "/static/dashboard.html"));
$("rosterBtn")?.addEventListener("click", () => (window.location.href = "/static/roster.html"));
$("eventsBtn")?.addEventListener("click", () => (window.location.href = "/static/events.html"));
$("hoursBtn")?.addEventListener("click", () => (window.location.href = "/static/service_hours.html"));

// ----------------------------
// STATE
// ----------------------------
let me = null;
let entries = [];

// ----------------------------
// LOAD ME (fix: show full_name, not email)
// ----------------------------
async function loadMe() {
  const msgEl = $("msg");
  try {
    const resp = await apiFetch("/member/me");
    if (!resp.ok) throw new Error("member/me failed");
    me = await resp.json();

    const sel = $("memberSelect");
    // If your HTML uses a <select> for MEMBER NAME, we populate it.
    // If it’s actually an <input>, we set value/text safely.
    if (sel) {
      if (sel.tagName === "SELECT") {
        sel.innerHTML = "";
        const opt = document.createElement("option");
        opt.value = String(me?.id ?? "");
        opt.textContent = displayMemberName(me);
        sel.appendChild(opt);
      } else {
        sel.value = displayMemberName(me);
      }
    }

    // If there’s a plain label somewhere:
    const nameLabel = $("memberNameLabel");
    if (nameLabel) nameLabel.textContent = displayMemberName(me);

    if (msgEl) msgEl.textContent = "";
  } catch (e) {
    console.error(e);
    if (msgEl) msgEl.textContent = "Could not load member profile.";
  }
}

// ----------------------------
// RENDER TABLE (fix: show full_name when available)
// ----------------------------
function render(entriesToRender) {
  const tbody = $("rows");
  if (!tbody) return;

  tbody.innerHTML = "";

  const countHint = $("countHint");
  if (countHint) countHint.textContent = `${entriesToRender.length} entr${entriesToRender.length === 1 ? "y" : "ies"}`;

  for (const r of entriesToRender) {
    // Try every likely field name so we don’t care what the backend returns.
    const memberName =
      (r.member_name || r.member_full_name || r.full_name || r.member?.full_name || "").trim() ||
      (r.member_email || r.email || r.member?.email || "").trim() ||
      displayMemberName(me);

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(memberName || "—")}</td>
      <td>${escapeHtml(toISODateOnly(r.service_date) || "—")}</td>
      <td>${escapeHtml(String(r.hours ?? "—"))}</td>
      <td>${escapeHtml(r.activity || r.service_location || r.location || "—")}</td>
      <td>${escapeHtml(r.notes || r.service_type || r.type || "—")}</td>
      <td>${escapeHtml(String(r.club_ytd_hours ?? r.ytd_club_hours ?? r.ytd ?? "—"))}</td>
      <td>
        <button class="btn btn-secondary btn-small" data-act="edit" data-id="${r.id}">Edit</button>
        <button class="btn btn-danger btn-small" data-act="delete" data-id="${r.id}">Delete</button>
      </td>
    `;
    tbody.appendChild(tr);
  }

  tbody.querySelectorAll("button[data-act]").forEach((btn) => btn.addEventListener("click", onRowAction));
}

// ----------------------------
// LOAD ENTRIES
// ----------------------------
async function loadEntries() {
  const msgEl = $("msg");
  if (msgEl) msgEl.textContent = "Loading…";

  try {
    const resp = await apiFetch("/member/service-hours");
    if (!resp.ok) throw new Error("service-hours failed");
    const data = await resp.json();

    entries = Array.isArray(data)
      ? data
      : Array.isArray(data.items)
        ? data.items
        : Array.isArray(data.entries)
          ? data.entries
          : [];

    if (msgEl) msgEl.textContent = "";
    render(entries);
  } catch (e) {
    console.error(e);
    entries = [];
    render([]);
    if (msgEl) msgEl.textContent = "Failed to load service hours.";
  }
}

$("refreshBtn")?.addEventListener("click", loadEntries);

// ----------------------------
// ADD ENTRY
// ----------------------------
$("addBtn")?.addEventListener("click", async () => {
  const msgEl = $("msg");
  if (msgEl) msgEl.textContent = "";

  const serviceDateEl = $("serviceDate");
  const hoursEl = $("hours");
  const locationEl = $("location");
  const typeEl = $("type");

  const service_date = toYYYYMMDD(serviceDateEl?.value || "") || null;
  const hours = Number(hoursEl?.value || 0);
  const activity = (typeEl?.value || "").trim() || null;
  const notes = (locationEl?.value || "").trim() || null;

  if (!service_date) return (msgEl.textContent = "Service date is required.");
  if (!Number.isFinite(hours) || hours <= 0) return (msgEl.textContent = "Hours must be greater than 0.");

  const payload = { service_date, hours, activity, notes };

  try {
    if (msgEl) msgEl.textContent = "Saving…";
    const resp = await apiFetch("/member/service-hours", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const t = await resp.text().catch(() => "");
      console.error(t);
      if (msgEl) msgEl.textContent = "Create failed.";
      return;
    }

    if (msgEl) msgEl.textContent = "";
    await loadEntries();
  } catch (e) {
    console.error(e);
    if (msgEl) msgEl.textContent = "Create failed (network/server).";
  }
});

// ----------------------------
// EDIT / DELETE
// ----------------------------
async function onRowAction(e) {
  const id = Number(e.currentTarget.dataset.id);
  const act = e.currentTarget.dataset.act;
  const row = (entries || []).find((x) => Number(x.id) === id);
  if (!row) return;

  if (act === "delete") {
    const ok = confirm("Delete this service hour entry?");
    if (!ok) return;

    try {
      const resp = await apiFetch(`/member/service-hours/${id}`, { method: "DELETE" });
      if (!resp.ok) throw new Error("delete failed");
      await loadEntries();
    } catch (err) {
      console.error(err);
      alert("Delete failed.");
    }
    return;
  }

  if (act === "edit") {
    // Simple prompt edit (keeps this file independent from any modal HTML changes)
    const newDate = prompt("Service date (YYYY-MM-DD):", toISODateOnly(row.service_date) || "");
    if (!newDate) return;

    const newHoursStr = prompt("Hours:", String(row.hours ?? ""));
    if (!newHoursStr) return;

    const newHours = Number(newHoursStr);
    if (!Number.isFinite(newHours) || newHours <= 0) return alert("Hours must be > 0.");

    const newActivity = prompt("Service type/activity:", String(row.activity ?? row.service_type ?? "")) ?? "";
    const newNotes = prompt("Notes/location:", String(row.notes ?? row.service_location ?? "")) ?? "";

    const payload = {
      service_date: toYYYYMMDD(newDate),
      hours: newHours,
      activity: newActivity.trim() || null,
      notes: newNotes.trim() || null,
    };

    try {
      const resp = await apiFetch(`/member/service-hours/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const t = await resp.text().catch(() => "");
        console.error(t);
        alert("Update failed.");
        return;
      }
      await loadEntries();
    } catch (err) {
      console.error(err);
      alert("Update failed (network/server).");
    }
  }
}

// ----------------------------
// BOOT
// ----------------------------
await loadMe();
await loadEntries();
