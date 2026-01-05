// app/static/js/service_hours.js
import { requireAuth, apiFetch, clearToken } from "./auth.js";

requireAuth();

const $ = (id) => document.getElementById(id);

function fmtDate(yyyy_mm_dd) {
  if (!yyyy_mm_dd) return "—";
  const [y, m, d] = yyyy_mm_dd.split("-").map(Number);
  if (!y || !m || !d) return yyyy_mm_dd;
  return `${m}/${d}/${y}`;
}

function currentYear() {
  return new Date().getFullYear();
}

function safeNum(n) {
  const x = Number(n);
  return Number.isFinite(x) ? x : 0;
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// -------------------------
// NAV
// -------------------------
$("logoutBtn")?.addEventListener("click", () => {
  clearToken();
  window.location.href = "/static/public_request.html";
});

$("dashBtn")?.addEventListener("click", () => {
  window.location.href = "/static/dashboard.html";
});

// -------------------------
// STATE
// -------------------------
let MEMBERS_BY_ID = new Map();     // id -> label
let MY_MEMBER_ID = null;
let CURRENT_ENTRIES = [];         // current loaded entries (for editing)

// -------------------------
// LOADERS
// -------------------------
async function loadMe() {
  const resp = await apiFetch("/member/me");
  if (!resp.ok) throw new Error("Failed to load /member/me");
  return await resp.json();
}

async function loadRoster() {
  const resp = await apiFetch("/member/roster");
  if (!resp.ok) throw new Error("Failed to load roster");
  return await resp.json();
}

async function loadHours() {
  const resp = await apiFetch("/member/service-hours");
  if (!resp.ok) throw new Error("Failed to load service hours");
  return await resp.json();
}

// -------------------------
// RENDER
// -------------------------
function renderMemberSelect(me, roster) {
  const sel = $("memberSelect");
  sel.innerHTML = "";
  sel.disabled = true; // per backend: logging is for current member

  // build member map
  MEMBERS_BY_ID = new Map();
  for (const m of roster) {
    const label = (m.full_name && m.full_name.trim()) ? m.full_name.trim() : m.email;
    MEMBERS_BY_ID.set(m.id, label);
  }

  MY_MEMBER_ID = me.id;
  const myLabel = MEMBERS_BY_ID.get(me.id) || (me.full_name?.trim() || me.email);

  // show just "me"
  const opt = document.createElement("option");
  opt.value = String(me.id);
  opt.textContent = myLabel;
  sel.appendChild(opt);
}

function renderTable(hoursEntries) {
  const rows = $("rows");
  const empty = $("empty");
  const countHint = $("countHint");

  rows.innerHTML = "";
  CURRENT_ENTRIES = Array.isArray(hoursEntries) ? hoursEntries : [];

  if (!CURRENT_ENTRIES.length) {
    empty.style.display = "block";
    countHint.textContent = "0 entries";
    $("ytdHeadline").textContent = `YTD Club Service Hours: 0.00`;
    return;
  }

  empty.style.display = "none";
  countHint.textContent = `${CURRENT_ENTRIES.length} entr${CURRENT_ENTRIES.length === 1 ? "y" : "ies"}`;

  // YTD club total (current year, all entries returned)
  const y = currentYear();
  let ytdTotal = 0;
  for (const e of CURRENT_ENTRIES) {
    const yr = e.service_date ? Number(String(e.service_date).slice(0, 4)) : null;
    if (yr === y) ytdTotal += safeNum(e.hours);
  }
  $("ytdHeadline").textContent = `YTD Club Service Hours: ${ytdTotal.toFixed(2)}`;

  // sort newest service_date first
  const sorted = [...CURRENT_ENTRIES].sort((a, b) => {
    const ad = a.service_date || "";
    const bd = b.service_date || "";
    if (ad !== bd) return bd.localeCompare(ad);
    return String(b.created_at || "").localeCompare(String(a.created_at || ""));
  });

  for (const e of sorted) {
    const memberLabel = MEMBERS_BY_ID.get(e.member_id) || `Member #${e.member_id}`;
    const serviceDate = fmtDate(e.service_date);
    const hrs = safeNum(e.hours);

    // We store location in activity and type in notes (current backend model)
    const location = e.activity || "—";
    const type = e.notes || "—";

    const canEditDelete = (MY_MEMBER_ID != null && e.member_id === MY_MEMBER_ID);

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(memberLabel)}</strong></td>
      <td>${escapeHtml(serviceDate)}</td>
      <td>${hrs.toFixed(2)}</td>
      <td>${escapeHtml(location)}</td>
      <td>${escapeHtml(type)}</td>
      <td class="ytd">${ytdTotal.toFixed(2)}</td>
      <td>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn btn-sm btn-edit" data-action="edit" data-id="${e.id}" ${canEditDelete ? "" : "disabled"}>Edit</button>
          <button class="btn btn-sm btn-del" data-action="delete" data-id="${e.id}" ${canEditDelete ? "" : "disabled"}>Delete</button>
        </div>
      </td>
    `;
    rows.appendChild(tr);
  }

  // table-level click handling
  rows.querySelectorAll("button[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const action = btn.dataset.action;
      const id = Number(btn.dataset.id);
      if (!id) return;

      if (action === "edit") openEditModal(id);
      if (action === "delete") await deleteEntry(id);
    });
  });
}

// -------------------------
// CREATE ENTRY
// -------------------------
async function addEntry() {
  const service_date = $("serviceDate").value;
  const hoursVal = $("serviceHours").value;
  const serviceLocation = $("serviceLocation").value.trim();
  const serviceType = $("serviceType").value.trim();

  if (!service_date) return ($("msg").textContent = "Pick a service date.");
  if (!hoursVal || Number(hoursVal) <= 0) return ($("msg").textContent = "Enter service hours (> 0).");
  if (!serviceLocation) return ($("msg").textContent = "Enter service location.");
  if (!serviceType) return ($("msg").textContent = "Select service type.");

  $("addBtn").disabled = true;
  $("msg").textContent = "Saving…";

  try {
    const payload = {
      service_date,
      hours: Number(hoursVal),
      activity: serviceLocation, // Service Location
      notes: serviceType,        // Service Type
    };

    const resp = await apiFetch("/member/service-hours", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const txt = await resp.text().catch(() => "");
      console.error("Create failed:", txt);
      $("msg").textContent = "Create failed. Check inputs.";
      return;
    }

    $("msg").textContent = "✅ Entry added.";
    $("serviceHours").value = "";
    $("serviceLocation").value = "";
    $("serviceType").value = "";
    await refreshAll();
  } catch (err) {
    console.error(err);
    $("msg").textContent = "Create failed (network/server).";
  } finally {
    $("addBtn").disabled = false;
  }
}

// -------------------------
// EDIT MODAL
// -------------------------
let EDITING_ID = null;

function showModal(show) {
  const bd = $("modalBackdrop");
  bd.style.display = show ? "flex" : "none";
}

function findEntryById(id) {
  return CURRENT_ENTRIES.find((e) => Number(e.id) === Number(id)) || null;
}

function openEditModal(entryId) {
  const e = findEntryById(entryId);
  if (!e) return;

  EDITING_ID = e.id;

  const memberLabel = MEMBERS_BY_ID.get(e.member_id) || `Member #${e.member_id}`;

  $("modalTitle").textContent = "Edit Service Hours Entry";
  $("modalId").textContent = `#${e.id}`;
  $("modalHint").textContent = "";

  $("editMember").value = memberLabel;
  $("editDate").value = e.service_date || "";
  $("editHours").value = safeNum(e.hours) ? String(safeNum(e.hours)) : "";
  $("editLocation").value = e.activity || "";
  $("editType").value = e.notes || "";

  showModal(true);
}

$("modalCancel")?.addEventListener("click", () => {
  EDITING_ID = null;
  showModal(false);
});

$("modalBackdrop")?.addEventListener("click", (ev) => {
  if (ev.target === $("modalBackdrop")) {
    EDITING_ID = null;
    showModal(false);
  }
});

$("modalSave")?.addEventListener("click", async () => {
  if (!EDITING_ID) return;

  const service_date = $("editDate").value;
  const hoursVal = $("editHours").value;
  const location = $("editLocation").value.trim();
  const type = $("editType").value.trim();

  if (!service_date) return ($("modalHint").textContent = "Service date is required.");
  if (!hoursVal || Number(hoursVal) <= 0) return ($("modalHint").textContent = "Hours must be > 0.");
  if (!location) return ($("modalHint").textContent = "Service location is required.");
  if (!type) return ($("modalHint").textContent = "Service type is required.");

  $("modalSave").disabled = true;
  $("modalHint").textContent = "Saving…";

  try {
    const payload = {
      service_date,
      hours: Number(hoursVal),
      activity: location,
      notes: type,
    };

    const resp = await apiFetch(`/member/service-hours/${EDITING_ID}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const txt = await resp.text().catch(() => "");
      console.error("Update failed:", txt);
      $("modalHint").textContent = "Update failed.";
      return;
    }

    $("modalHint").textContent = "✅ Saved.";
    showModal(false);
    EDITING_ID = null;
    await refreshAll();
  } catch (err) {
    console.error(err);
    $("modalHint").textContent = "Update failed (network/server).";
  } finally {
    $("modalSave").disabled = false;
  }
});

// -------------------------
// DELETE
// -------------------------
async function deleteEntry(entryId) {
  const e = findEntryById(entryId);
  if (!e) return;

  const ok = confirm("Delete this service hours entry? This cannot be undone.");
  if (!ok) return;

  $("msg").textContent = "Deleting…";

  try {
    const resp = await apiFetch(`/member/service-hours/${entryId}`, {
      method: "DELETE",
    });

    if (!resp.ok) {
      const txt = await resp.text().catch(() => "");
      console.error("Delete failed:", txt);
      $("msg").textContent = "Delete failed.";
      return;
    }

    $("msg").textContent = "✅ Deleted.";
    await refreshAll();
  } catch (err) {
    console.error(err);
    $("msg").textContent = "Delete failed (network/server).";
  }
}

// -------------------------
// REFRESH
// -------------------------
async function refreshAll() {
  $("msg").textContent = "Loading…";

  const [me, roster, entries] = await Promise.all([
    loadMe(),
    loadRoster(),
    loadHours(),
  ]);

  renderMemberSelect(me, roster);
  renderTable(entries);

  $("msg").textContent = "";
}

// -------------------------
// INIT
// -------------------------
$("addBtn")?.addEventListener("click", addEntry);
$("refreshBtn")?.addEventListener("click", refreshAll);

// default date today
(function initDate(){
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  $("serviceDate").value = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
})();

(async function init(){
  try {
    await refreshAll();
  } catch (err) {
    console.error(err);
    $("msg").textContent = "Failed to load service hours (check token/server).";
  }
})();
