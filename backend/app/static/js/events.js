// app/static/js/events.js
import { requireAuth, apiFetch, clearToken } from "./auth.js";

// 🔒 must be logged in
requireAuth();

const $ = (id) => document.getElementById(id);

// -----------------------------------------------------
// TIMEZONE HELPERS (FORCE EASTERN TIME / LONDON, OH)
// -----------------------------------------------------
// Backend stores datetimes as naive UTC strings "YYYY-MM-DDTHH:MM:SS" (UTC-naive)
//
// ✅ DISPLAY as Eastern Time (America/New_York)
// ✅ SEND as UTC-naive by interpreting datetime-local input as Eastern Time,
//    converting to UTC, then ISO slice(0,19)
//
// If Intl timezone support is missing, we gracefully fall back to local behavior
// instead of breaking the page.
// -----------------------------------------------------

const EVENT_TZ = "America/New_York";

function hasTimeZoneSupport() {
  try {
    // If this throws, timezone support isn't there.
    new Intl.DateTimeFormat("en-US", { timeZone: EVENT_TZ }).format(new Date());
    return true;
  } catch {
    return false;
  }
}

const TZ_OK = hasTimeZoneSupport();

function parseUtcNaiveAsDate(utcNaiveString) {
  // Treat backend string as UTC by appending Z
  return new Date(utcNaiveString + "Z");
}

// Get timezone offset (minutes) for a given instant in a target IANA zone.
// Uses Intl.DateTimeFormat, no external libraries needed.
function tzOffsetMinutesForInstant(dateObj, timeZone) {
  const dtf = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

  const parts = dtf.formatToParts(dateObj);
  const get = (type) => parts.find((p) => p.type === type)?.value;

  const asUTC = Date.UTC(
    Number(get("year")),
    Number(get("month")) - 1,
    Number(get("day")),
    Number(get("hour")),
    Number(get("minute")),
    Number(get("second"))
  );

  // dateObj.getTime() is UTC ms of the instant. Difference tells the zone offset.
  return (asUTC - dateObj.getTime()) / 60000;
}

// Local datetime-local -> UTC-naive string (old behavior fallback)
function toUtcNaiveStringFromLocalInput(datetimeLocalValue) {
  const d = new Date(datetimeLocalValue); // local time
  return d.toISOString().slice(0, 19); // UTC-naive string
}

// Convert datetime-local value -> UTC-naive string,
// interpreting the input as Eastern Time (America/New_York).
function toUtcNaiveStringFromEasternInput(datetimeLocalValue) {
  if (!TZ_OK) return toUtcNaiveStringFromLocalInput(datetimeLocalValue);

  // "YYYY-MM-DDTHH:MM"
  const [datePart, timePart] = datetimeLocalValue.split("T");
  const [y, m, d] = datePart.split("-").map(Number);
  const [hh, mi] = timePart.split(":").map(Number);

  // Start with a UTC guess for those wall-clock numbers
  const guess1 = new Date(Date.UTC(y, m - 1, d, hh, mi, 0));
  const off1 = tzOffsetMinutesForInstant(guess1, EVENT_TZ);
  const utcMs1 = guess1.getTime() - off1 * 60000;

  // Second pass (helps DST transition edges)
  const guess2 = new Date(utcMs1);
  const off2 = tzOffsetMinutesForInstant(guess2, EVENT_TZ);
  const utcMs2 = guess1.getTime() - off2 * 60000;

  return new Date(utcMs2).toISOString().slice(0, 19);
}

// Convert backend UTC-naive -> datetime-local value in Eastern
function toEasternDatetimeLocalValueFromUtcNaive(utcNaiveString) {
  const d = parseUtcNaiveAsDate(utcNaiveString);

  if (!TZ_OK) {
    // fallback: show local
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  const dtf = new Intl.DateTimeFormat("en-US", {
    timeZone: EVENT_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  const parts = dtf.formatToParts(d);
  const get = (type) => parts.find((p) => p.type === type)?.value;

  const yyyy = get("year");
  const mm = get("month");
  const dd = get("day");
  const hh = get("hour");
  const mi = get("minute");

  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`;
}

// Format a Date instant as Eastern display string
function formatEasternDateTime(dateObj) {
  if (!TZ_OK) {
    // fallback: local
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

    return `${d} at ${t}`;
  }

  const d = new Intl.DateTimeFormat("en-US", {
    timeZone: EVENT_TZ,
    month: "2-digit",
    day: "2-digit",
    year: "numeric",
  }).format(dateObj);

  const t = new Intl.DateTimeFormat("en-US", {
    timeZone: EVENT_TZ,
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(dateObj);

  return `${d} at ${t} (ET)`;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// -----------------------------------------------------
// NAV
// -----------------------------------------------------
$("logoutBtn")?.addEventListener("click", () => {
  clearToken();
  window.location.href = "/static/public_request.html";
});

$("dashBtn")?.addEventListener("click", () => {
  window.location.href = "/static/dashboard.html";
});

$("rosterBtn")?.addEventListener("click", () => {
  window.location.href = "/static/roster.html";
});

$("hoursBtn")?.addEventListener("click", () => {
  window.location.href = "/static/service_hours.html";
});

// -----------------------------------------------------
// STATE
// -----------------------------------------------------
let editModeId = null;
let eventsCache = [];

function setEditMode(id) {
  editModeId = id;
  const btn = $("createBtn");
  if (btn) btn.textContent = "Save Changes";
  $("msg").textContent = `Editing event #${id}. Make changes above, then click “Save Changes”.`;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function clearEditMode() {
  editModeId = null;
  const btn = $("createBtn");
  if (btn) btn.textContent = "Add Event";
}

// -----------------------------------------------------
// RENDER LIST (DISPLAY IN EASTERN)
// -----------------------------------------------------
function renderEvents(events) {
  const list = $("eventsList");
  const empty = $("empty");
  const countHint = $("countHint");

  list.innerHTML = "";

  if (!events || events.length === 0) {
    empty.style.display = "block";
    countHint.textContent = "0 events";
    return;
  }

  empty.style.display = "none";
  countHint.textContent = `${events.length} event${events.length === 1 ? "" : "s"}`;

  for (const ev of events) {
    const start = ev.start_at ? parseUtcNaiveAsDate(ev.start_at) : null;
    const end = ev.end_at ? parseUtcNaiveAsDate(ev.end_at) : null;

    const when = start
      ? end
        ? `${formatEasternDateTime(start)} → ${formatEasternDateTime(end)}`
        : formatEasternDateTime(start)
      : "—";

    const visibility = ev.is_public ? "Public" : "Private";
    const pillClass = ev.is_public ? "public" : "private";

    const row = document.createElement("div");
    row.className = "event";

    row.innerHTML = `
      <div class="when">
        ${when}
        <span class="pill ${pillClass}">${visibility}</span>
      </div>

      <div class="main">
        <div class="name">${escapeHtml(ev.title || "Untitled")}</div>
        <div class="loc">${escapeHtml(ev.location || "—")}</div>
        <p class="desc">${escapeHtml(ev.description || "")}</p>
      </div>

      <div class="meta">
        <div>Created: ${ev.created_at ? formatEasternDateTime(parseUtcNaiveAsDate(ev.created_at)) : "—"}</div>

        <div style="margin-top:10px; display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
          <button type="button"
            data-action="edit"
            data-id="${ev.id}"
            style="border:0;border-radius:10px;padding:9px 12px;font-weight:900;cursor:pointer;background:#2563eb;color:#fff;">
            Edit
          </button>

          <button type="button"
            data-action="delete"
            data-id="${ev.id}"
            style="border:0;border-radius:10px;padding:9px 12px;font-weight:900;cursor:pointer;background:#dc2626;color:#fff;">
            Delete
          </button>

          <button type="button"
            data-action="invite"
            data-id="${ev.id}"
            style="border:0;border-radius:10px;padding:9px 12px;font-weight:900;cursor:pointer;background:#111827;color:#fff;">
            Invite
          </button>
        </div>
      </div>
    `;

    list.appendChild(row);
  }
}

// -----------------------------------------------------
// LOAD EVENTS
// -----------------------------------------------------
async function loadEvents() {
  $("msg").textContent = "Loading events…";
  try {
    const resp = await apiFetch("/member/events?include_past=true");
    if (!resp.ok) throw new Error("Failed to load events");
    const data = await resp.json();
    eventsCache = Array.isArray(data) ? data : [];
    renderEvents(eventsCache);
    $("msg").textContent = "";
  } catch (err) {
    console.error(err);
    $("msg").textContent = "Failed to load events.";
    eventsCache = [];
    renderEvents([]);
  }
}

$("refreshBtn")?.addEventListener("click", loadEvents);

// -----------------------------------------------------
// CREATE / UPDATE EVENT (same button)
// -----------------------------------------------------
$("createBtn")?.addEventListener("click", async () => {
  const title = $("title").value.trim();
  const location = $("location").value.trim();
  const description = $("description").value.trim();
  const visibility = $("visibility").value;

  const startLocal = $("startAt").value;
  const endLocal = $("endAt").value;

  if (!title) return ($("msg").textContent = "Title is required.");
  if (!location) return ($("msg").textContent = "Location is required.");
  if (!startLocal) return ($("msg").textContent = "Start date/time is required.");

  const start_at = toUtcNaiveStringFromEasternInput(startLocal);
  const end_at = endLocal ? toUtcNaiveStringFromEasternInput(endLocal) : null;

  if (end_at && end_at <= start_at) {
    $("msg").textContent = "End must be after Start.";
    return;
  }

  const payload = {
    title,
    description: description || null,
    location,
    start_at,
    end_at,
    is_public: visibility === "public",
  };

  $("createBtn").disabled = true;
  $("msg").textContent = editModeId ? "Saving changes…" : "Saving…";

  try {
    const url = editModeId ? `/member/events/${editModeId}` : "/member/events";
    const method = editModeId ? "PUT" : "POST";

    const resp = await apiFetch(url, {
      method,
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      $("msg").textContent = editModeId ? "Update failed. Check inputs." : "Create failed. Check inputs.";
      return;
    }

    $("title").value = "";
    $("location").value = "";
    $("description").value = "";
    $("startAt").value = "";
    $("endAt").value = "";
    $("visibility").value = "public";

    if (editModeId) {
      $("msg").textContent = "✅ Event updated.";
      clearEditMode();
    } else {
      $("msg").textContent = "✅ Event added.";
    }

    await loadEvents();
  } catch (err) {
    console.error(err);
    $("msg").textContent = editModeId ? "Update failed (network/server)." : "Create failed (network/server).";
  } finally {
    $("createBtn").disabled = false;
  }
});

// -----------------------------------------------------
// EDIT + DELETE + INVITE (event delegation)
// -----------------------------------------------------
$("eventsList")?.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;

  const action = btn.dataset.action;
  const id = Number(btn.dataset.id);
  if (!id) return;

  if (action === "delete") {
    const ok = confirm("Delete this event? This cannot be undone.");
    if (!ok) return;

    $("msg").textContent = "Deleting…";
    try {
      const resp = await apiFetch(`/member/events/${id}`, { method: "DELETE" });
      if (!resp.ok) {
        $("msg").textContent = "Delete failed.";
        return;
      }
      $("msg").textContent = "✅ Event deleted.";
      if (editModeId === id) clearEditMode();
      await loadEvents();
    } catch (err) {
      console.error(err);
      $("msg").textContent = "Delete failed (network/server).";
    }
    return;
  }

  if (action === "invite") {
    const ok = confirm("Send this event invite email to ALL active roster members with an email?");
    if (!ok) return;

    btn.disabled = true;
    const oldText = btn.textContent;
    btn.textContent = "Sending…";
    $("msg").textContent = "Sending invites…";

    try {
      const resp = await apiFetch(`/admin/events/${id}/invite`, { method: "POST" });

      if (!resp.ok) {
        const t = await resp.text().catch(() => "");
        $("msg").textContent = `Invite failed. ${t || ""}`.trim();
        return;
      }

      const data = await resp.json().catch(() => ({}));
      const sent = Number(data.sent ?? 0);
      const failed = Number(data.failed ?? 0);
      const skipped = Number(data.skipped ?? 0);

      $("msg").textContent = `✅ Invites sent: ${sent}. Failed: ${failed}. Skipped (no email): ${skipped}.`;
    } catch (err) {
      console.error(err);
      $("msg").textContent = "Invite failed (network/server).";
    } finally {
      btn.disabled = false;
      btn.textContent = oldText || "Invite";
    }
    return;
  }

  if (action === "edit") {
    const ev = eventsCache.find((x) => Number(x.id) === id);
    if (!ev) {
      $("msg").textContent = "Could not load event for editing. Refresh list.";
      return;
    }

    $("title").value = ev.title || "";
    $("location").value = ev.location || "";
    $("description").value = ev.description || "";
    $("visibility").value = ev.is_public ? "public" : "private";

    $("startAt").value = ev.start_at ? toEasternDatetimeLocalValueFromUtcNaive(ev.start_at) : "";
    $("endAt").value = ev.end_at ? toEasternDatetimeLocalValueFromUtcNaive(ev.end_at) : "";

    setEditMode(id);
  }
});

// Initial
loadEvents();
