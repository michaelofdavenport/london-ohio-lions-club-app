// app/static/js/events.js
import { requireAuth, apiFetch, clearToken } from "./auth.js";

// 🔒 must be logged in
requireAuth();

const $ = (id) => document.getElementById(id);

// -----------------------------------------------------
// TIMEZONE HELPERS (FORCE EASTERN TIME / LONDON, OH)
// -----------------------------------------------------
const EVENT_TZ = "America/New_York";

function hasTimeZoneSupport() {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: EVENT_TZ }).format(new Date());
    return true;
  } catch {
    return false;
  }
}
const TZ_OK = hasTimeZoneSupport();

function parseUtcNaiveAsDate(utcNaiveString) {
  return new Date(String(utcNaiveString || "") + "Z"); // treat backend as UTC naive
}

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

  return (asUTC - dateObj.getTime()) / 60000;
}

function toUtcNaiveStringFromLocalInput(datetimeLocalValue) {
  const d = new Date(datetimeLocalValue);
  return d.toISOString().slice(0, 19);
}

function toUtcNaiveStringFromEasternInput(datetimeLocalValue) {
  if (!TZ_OK) return toUtcNaiveStringFromLocalInput(datetimeLocalValue);

  const [datePart, timePart] = datetimeLocalValue.split("T");
  const [y, m, d] = datePart.split("-").map(Number);
  const [hh, mi] = timePart.split(":").map(Number);

  const guess1 = new Date(Date.UTC(y, m - 1, d, hh, mi, 0));
  const off1 = tzOffsetMinutesForInstant(guess1, EVENT_TZ);
  const utcMs1 = guess1.getTime() - off1 * 60000;

  const guess2 = new Date(utcMs1);
  const off2 = tzOffsetMinutesForInstant(guess2, EVENT_TZ);
  const utcMs2 = guess1.getTime() - off2 * 60000;

  return new Date(utcMs2).toISOString().slice(0, 19);
}

function toEasternDatetimeLocalValueFromUtcNaive(utcNaiveString) {
  const d = parseUtcNaiveAsDate(utcNaiveString);

  if (!TZ_OK) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
      d.getHours()
    )}:${pad(d.getMinutes())}`;
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

  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

function formatEasternDateTime(dateObj) {
  if (!TZ_OK) {
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
  return String(s ?? "")
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
$("dashBtn")?.addEventListener("click", () => (window.location.href = "/static/dashboard.html"));
$("rosterBtn")?.addEventListener("click", () => (window.location.href = "/static/roster.html"));
$("hoursBtn")?.addEventListener("click", () => (window.location.href = "/static/service_hours.html"));

// -----------------------------------------------------
// CONTRACT-FIRST ENDPOINT DISCOVERY via /__routes
// -----------------------------------------------------
let API = {
  list: null,         // GET
  create: null,       // POST
  updateTmpl: null,   // PUT/PATCH with {id}
  deleteTmpl: null,   // DELETE with {id}
  inviteTmpl: null,   // POST with {id}
  listSupportsIncludePast: true, // optimistic; harmless if ignored
};

function hasMethod(route, method) {
  const methods = route?.methods || [];
  return methods.includes(method);
}

function normalizePath(p) {
  return String(p || "");
}

function isEventsCorePath(p) {
  const s = normalizePath(p);
  // exclude public list endpoint and invite helper while searching “core”
  if (s.startsWith("/public/")) return false;
  if (!s.includes("/events")) return false;
  if (s.includes("/invite")) return false;
  return true;
}

function templateWithId(p) {
  const s = normalizePath(p);
  // FastAPI uses "{id}" or "{event_id}" in the path string
  if (s.includes("{id}")) return s;
  if (s.includes("{event_id}")) return s;
  // allow ":id" style just in case (not typical FastAPI, but safe)
  if (s.includes(":id")) return s;
  return null;
}

function fillId(template, id) {
  if (!template) return null;
  return template
    .replace("{id}", String(id))
    .replace("{event_id}", String(id))
    .replace(":id", String(id));
}

async function discoverEventEndpoints() {
  try {
    const resp = await apiFetch("/__routes");
    if (!resp.ok) throw new Error("routes fetch failed");
    const routes = await resp.json();

    // 1) LIST: prefer GET on "/member/events" then "/admin/events" then any GET containing "/events"
    const listCand = routes
      .filter((r) => hasMethod(r, "GET") && isEventsCorePath(r.path))
      .sort((a, b) => {
        const ap = a.path || "";
        const bp = b.path || "";
        const score = (p) =>
          (p.startsWith("/member/events") ? 0 :
           p.startsWith("/admin/events") ? 1 :
           p.includes("/events") ? 2 : 9);
        return score(ap) - score(bp);
      })[0];

    API.list = listCand ? listCand.path : null;

    // 2) CREATE: POST on the same collection path (ends with "/events" and not "/{id}")
    const createCand = routes
      .filter((r) => hasMethod(r, "POST") && isEventsCorePath(r.path))
      .filter((r) => !String(r.path).includes("{") && String(r.path).endsWith("/events"))
      .sort((a, b) => {
        const ap = a.path || "";
        const bp = b.path || "";
        const score = (p) =>
          (p.startsWith("/member/events") ? 0 :
           p.startsWith("/admin/events") ? 1 : 9);
        return score(ap) - score(bp);
      })[0];

    API.create = createCand ? createCand.path : null;

    // 3) UPDATE: PUT preferred, else PATCH, path contains "{id}"
    const updateCand = routes
      .filter((r) => isEventsCorePath(r.path))
      .filter((r) => templateWithId(r.path))
      .filter((r) => hasMethod(r, "PUT") || hasMethod(r, "PATCH"))
      .sort((a, b) => {
        // prefer PUT over PATCH, and /member over /admin
        const aPut = hasMethod(a, "PUT") ? 0 : 1;
        const bPut = hasMethod(b, "PUT") ? 0 : 1;
        if (aPut !== bPut) return aPut - bPut;

        const ap = a.path || "";
        const bp = b.path || "";
        const score = (p) =>
          (p.startsWith("/member/events") ? 0 :
           p.startsWith("/admin/events") ? 1 : 9);
        return score(ap) - score(bp);
      })[0];

    API.updateTmpl = updateCand ? updateCand.path : null;

    // 4) DELETE: DELETE + "{id}"
    const delCand = routes
      .filter((r) => isEventsCorePath(r.path))
      .filter((r) => templateWithId(r.path))
      .filter((r) => hasMethod(r, "DELETE"))
      .sort((a, b) => {
        const ap = a.path || "";
        const bp = b.path || "";
        const score = (p) =>
          (p.startsWith("/member/events") ? 0 :
           p.startsWith("/admin/events") ? 1 : 9);
        return score(ap) - score(bp);
      })[0];

    API.deleteTmpl = delCand ? delCand.path : null;

    // 5) INVITE: POST + "/invite"
    const inviteCand = routes
      .filter((r) => hasMethod(r, "POST"))
      .filter((r) => String(r.path || "").includes("/events/") && String(r.path || "").includes("/invite"))
      .filter((r) => templateWithId(r.path))
      .sort((a, b) => {
        // prefer /admin/events/.../invite
        const ap = a.path || "";
        const bp = b.path || "";
        const score = (p) => (p.startsWith("/admin/events") ? 0 : 9);
        return score(ap) - score(bp);
      })[0];

    API.inviteTmpl = inviteCand ? inviteCand.path : null;

    return true;
  } catch (e) {
    console.error(e);
    return false;
  }
}

function endpointsStatusText() {
  const bits = [];
  bits.push(`LIST=${API.list || "—"}`);
  bits.push(`CREATE=${API.create || "—"}`);
  bits.push(`UPDATE=${API.updateTmpl || "—"}`);
  bits.push(`DELETE=${API.deleteTmpl || "—"}`);
  bits.push(`INVITE=${API.inviteTmpl || "—"}`);
  return bits.join(" • ");
}

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
// RENDER LIST
// -----------------------------------------------------
function renderEvents(events) {
  const list = $("eventsList");
  const empty = $("empty");
  const countHint = $("countHint");
  if (!list || !empty || !countHint) return;

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
        <div>Created: ${
          ev.created_at ? formatEasternDateTime(parseUtcNaiveAsDate(ev.created_at)) : "—"
        }</div>

        <div style="margin-top:10px; display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
          <button type="button" data-action="edit" data-id="${ev.id}"
            style="border:0;border-radius:10px;padding:9px 12px;font-weight:900;cursor:pointer;background:#2563eb;color:#fff;">
            Edit
          </button>

          <button type="button" data-action="delete" data-id="${ev.id}"
            style="border:0;border-radius:10px;padding:9px 12px;font-weight:900;cursor:pointer;background:#dc2626;color:#fff;">
            Delete
          </button>

          <button type="button" data-action="invite" data-id="${ev.id}"
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
  const msg = $("msg");
  if (!API.list) {
    if (msg) msg.textContent = `Events not wired: no LIST endpoint found. (${endpointsStatusText()})`;
    eventsCache = [];
    renderEvents([]);
    return;
  }

  if (msg) msg.textContent = "Loading events…";
  try {
    // harmless query; backend may ignore include_past if not supported
    const url = API.list.includes("?") ? `${API.list}&include_past=true` : `${API.list}?include_past=true`;
    const resp = await apiFetch(url);
    if (!resp.ok) throw new Error("Failed to load events");
    const data = await resp.json();
    eventsCache = Array.isArray(data) ? data : [];
    renderEvents(eventsCache);
    if (msg) msg.textContent = "";
  } catch (err) {
    console.error(err);
    if (msg) msg.textContent = "Failed to load events.";
    eventsCache = [];
    renderEvents([]);
  }
}

$("refreshBtn")?.addEventListener("click", loadEvents);

// -----------------------------------------------------
// CREATE / UPDATE EVENT
// -----------------------------------------------------
$("createBtn")?.addEventListener("click", async () => {
  const msg = $("msg");

  const title = ($("title")?.value || "").trim();
  const location = ($("location")?.value || "").trim();
  const description = ($("description")?.value || "").trim();
  const visibility = $("visibility")?.value || "public";

  const startLocal = $("startAt")?.value || "";
  const endLocal = $("endAt")?.value || "";

  if (!title) return (msg.textContent = "Title is required.");
  if (!location) return (msg.textContent = "Location is required.");
  if (!startLocal) return (msg.textContent = "Start date/time is required.");

  const start_at = toUtcNaiveStringFromEasternInput(startLocal);
  const end_at = endLocal ? toUtcNaiveStringFromEasternInput(endLocal) : null;

  if (end_at && end_at <= start_at) {
    msg.textContent = "End must be after Start.";
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

  // Decide endpoint
  const isEdit = !!editModeId;

  if (!isEdit && !API.create) {
    msg.textContent = `Events not wired: no CREATE endpoint found. (${endpointsStatusText()})`;
    return;
  }
  if (isEdit && !API.updateTmpl) {
    msg.textContent = `Events not wired: no UPDATE endpoint found. (${endpointsStatusText()})`;
    return;
  }

  const btn = $("createBtn");
  btn.disabled = true;
  msg.textContent = isEdit ? "Saving changes…" : "Saving…";

  try {
    let url = null;
    let method = null;

    if (!isEdit) {
      url = API.create;
      method = "POST";
    } else {
      url = fillId(API.updateTmpl, editModeId);
      method = hasMethod({ methods: ["PUT"] }, "PUT") ? "PUT" : "PUT"; // keep PUT; apiFetch handles if backend allows PATCH too via updateTmpl discovery
      // If your update route only allows PATCH, the discovered template is still correct,
      // but the method matters. So we detect it by asking /__routes again quickly:
      const routesResp = await apiFetch("/__routes");
      if (routesResp.ok) {
        const routes = await routesResp.json();
        const match = routes.find((r) => r.path === API.updateTmpl);
        if (match?.methods?.includes("PATCH") && !match?.methods?.includes("PUT")) method = "PATCH";
        else method = match?.methods?.includes("PUT") ? "PUT" : "PATCH";
      } else {
        method = "PUT";
      }
    }

    const resp = await apiFetch(url, {
      method,
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const t = await resp.text().catch(() => "");
      msg.textContent = (isEdit ? "Update failed. " : "Create failed. ") + (t || "Check inputs.");
      return;
    }

    // clear form
    $("title").value = "";
    $("location").value = "";
    $("description").value = "";
    $("startAt").value = "";
    $("endAt").value = "";
    $("visibility").value = "public";

    if (isEdit) {
      msg.textContent = "✅ Event updated.";
      clearEditMode();
    } else {
      msg.textContent = "✅ Event added.";
    }

    await loadEvents();
  } catch (err) {
    console.error(err);
    msg.textContent = isEdit ? "Update failed (network/server)." : "Create failed (network/server).";
  } finally {
    btn.disabled = false;
  }
});

// -----------------------------------------------------
// EDIT + DELETE + INVITE
// -----------------------------------------------------
$("eventsList")?.addEventListener("click", async (e) => {
  const msg = $("msg");
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;

  const action = btn.dataset.action;
  const id = Number(btn.dataset.id);
  if (!id) return;

  if (action === "delete") {
    if (!API.deleteTmpl) {
      msg.textContent = `Events not wired: no DELETE endpoint found. (${endpointsStatusText()})`;
      return;
    }

    const ok = confirm("Delete this event? This cannot be undone.");
    if (!ok) return;

    msg.textContent = "Deleting…";
    try {
      const url = fillId(API.deleteTmpl, id);
      const resp = await apiFetch(url, { method: "DELETE" });
      if (!resp.ok) {
        const t = await resp.text().catch(() => "");
        msg.textContent = `Delete failed. ${t || ""}`.trim();
        return;
      }
      msg.textContent = "✅ Event deleted.";
      if (editModeId === id) clearEditMode();
      await loadEvents();
    } catch (err) {
      console.error(err);
      msg.textContent = "Delete failed (network/server).";
    }
    return;
  }

  if (action === "invite") {
    if (!API.inviteTmpl) {
      msg.textContent = `Events not wired: no INVITE endpoint found. (${endpointsStatusText()})`;
      return;
    }

    const ok = confirm("Send this event invite email to ALL active roster members with an email?");
    if (!ok) return;

    btn.disabled = true;
    const oldText = btn.textContent;
    btn.textContent = "Sending…";
    msg.textContent = "Sending invites…";

    try {
      const url = fillId(API.inviteTmpl, id);
      const resp = await apiFetch(url, { method: "POST" });
      if (!resp.ok) {
        const t = await resp.text().catch(() => "");
        msg.textContent = `Invite failed. ${t || ""}`.trim();
        return;
      }

      const data = await resp.json().catch(() => ({}));
      const sent = Number(data.sent ?? 0);
      const failed = Number(data.failed ?? 0);
      const skipped = Number(data.skipped ?? 0);

      msg.textContent = `✅ Invites sent: ${sent}. Failed: ${failed}. Skipped (no email): ${skipped}.`;
    } catch (err) {
      console.error(err);
      msg.textContent = "Invite failed (network/server).";
    } finally {
      btn.disabled = false;
      btn.textContent = oldText || "Invite";
    }
    return;
  }

  if (action === "edit") {
    const ev = eventsCache.find((x) => Number(x.id) === id);
    if (!ev) {
      msg.textContent = "Could not load event for editing. Refresh list.";
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

// -----------------------------------------------------
// INITIAL BOOT
// -----------------------------------------------------
(async function boot() {
  const ok = await discoverEventEndpoints();

  // If discovery fails, still show something useful
  if (!ok) {
    const msg = $("msg");
    if (msg) msg.textContent = "Could not load /__routes. (Are you logged in?)";
    return;
  }

  // If create/list not found, show exact contract status
  const msg = $("msg");
  if (msg && (!API.list || !API.create)) {
    msg.textContent = `Events contract: ${endpointsStatusText()}`;
  }

  await loadEvents();
})();
