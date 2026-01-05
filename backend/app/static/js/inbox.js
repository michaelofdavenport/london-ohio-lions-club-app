import { apiFetch, clearToken } from "./auth.js";
import { requireAdminOrRedirect } from "./admin_guard.js";

await requireAdminOrRedirect();

const $ = (id) => document.getElementById(id);

$("dashBtn").addEventListener("click", () => (window.location.href = "/static/dashboard.html"));
$("adminToolsBtn").addEventListener("click", () => (window.location.href = "/admin/tools"));
$("logoutBtn").addEventListener("click", () => {
  clearToken();
  window.location.href = "/static/public_request.html";
});
$("printBtn").addEventListener("click", () => window.print());

let all = [];
let roster = [];
let activeId = null;

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function pill(status) {
  const s = String(status || "").toUpperCase();
  if (s === "PENDING") return `<span class="pill pending">PENDING</span>`;
  if (s === "APPROVED") return `<span class="pill approved">APPROVED</span>`;
  if (s === "DENIED") return `<span class="pill denied">DENIED</span>`;
  return `<span class="pill">${escapeHtml(s || "—")}</span>`;
}

function shortDesc(d) {
  const s = String(d || "");
  return s.length > 180 ? escapeHtml(s.slice(0, 180)) + "…" : escapeHtml(s || "—");
}

async function loadRoster() {
  // Use /admin/members so we can assign to anyone active
  const resp = await apiFetch("/admin/members");
  roster = resp.ok ? await resp.json() : [];
}

function render(rows) {
  const tbody = $("rows");
  tbody.innerHTML = "";
  $("countHint").textContent = `${rows.length} request${rows.length === 1 ? "" : "s"}`;

  for (const r of rows) {
    const assigned = r.assigned_to_name ? escapeHtml(r.assigned_to_name) : `<span class="muted">Unassigned</span>`;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="mono">#${r.id}</td>
      <td>${escapeHtml(r.category || "—")}</td>
      <td>${pill(r.status)}</td>
      <td>${escapeHtml(r.requester_name || "—")}</td>
      <td>${assigned}</td>
      <td>${shortDesc(r.description)}</td>
      <td>
        <div class="actions">
          <button class="btn btn-secondary btn-small" data-act="open" data-id="${r.id}">Open</button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  }

  tbody.querySelectorAll("button[data-act='open']").forEach((b) => b.addEventListener("click", onOpen));
}

function applyFilters() {
  const q = $("q").value.trim().toLowerCase();
  const status = $("status").value;
  const assigned = $("assigned").value;

  let rows = all.slice();

  if (status) rows = rows.filter((r) => String(r.status || "").toUpperCase() === status);
  if (assigned === "assigned") rows = rows.filter((r) => r.assigned_to_member_id != null);
  if (assigned === "unassigned") rows = rows.filter((r) => r.assigned_to_member_id == null);

  if (q) {
    rows = rows.filter((r) => {
      const s = `${r.requester_name ?? ""} ${r.requester_email ?? ""} ${r.description ?? ""}`.toLowerCase();
      return s.includes(q);
    });
  }

  render(rows);
}

async function loadRequests() {
  $("msg").textContent = "Loading…";
  try {
    const params = new URLSearchParams();
    const status = $("status").value;
    const q = $("q").value.trim();
    const assigned = $("assigned").value;

    if (status) params.set("status", status);
    if (q) params.set("q", q);
    if (assigned) params.set("assigned", assigned);
    params.set("limit", "300");

    const resp = await apiFetch(`/admin/requests?${params.toString()}`);
    if (!resp.ok) throw new Error("Failed to load");

    all = await resp.json();
    $("msg").textContent = "";
    applyFilters();
  } catch (e) {
    console.error(e);
    all = [];
    render([]);
    $("msg").textContent = "Failed to load requests.";
  }
}

$("refreshBtn").addEventListener("click", loadRequests);
$("q").addEventListener("input", applyFilters);
$("status").addEventListener("change", loadRequests);
$("assigned").addEventListener("change", loadRequests);

function openModal() { $("modalBackdrop").style.display = "flex"; }
function closeModal() { $("modalBackdrop").style.display = "none"; activeId = null; }

$("closeBtn").addEventListener("click", closeModal);
$("modalBackdrop").addEventListener("click", (e) => {
  if (e.target === $("modalBackdrop")) closeModal();
});

async function loadNotes(requestId) {
  try {
    const resp = await apiFetch(`/admin/requests/${requestId}/notes`);
    if (!resp.ok) return [];
    return await resp.json();
  } catch {
    return [];
  }
}

async function onOpen(e) {
  const id = Number(e.currentTarget.dataset.id);
  const r = all.find((x) => x.id === id);
  if (!r) return;

  activeId = id;
  $("modalTitle").textContent = "Request";
  $("modalHint").textContent = `#${r.id} • ${r.category} • ${r.status}`;

  $("mWho").textContent =
    `${r.requester_name || "—"}`
    + (r.requester_email ? ` • ${r.requester_email}` : "")
    + (r.requester_phone ? ` • ${r.requester_phone}` : "");

  $("mAddr").textContent = r.requester_address || "—";
  $("mDesc").textContent = r.description || "—";
  $("mNote").value = "";
  $("modalMsg").textContent = "";

  // Assign dropdown
  const sel = $("mAssign");
  sel.innerHTML = "";
  const opt0 = document.createElement("option");
  opt0.value = "";
  opt0.textContent = "Unassigned";
  sel.appendChild(opt0);

  roster
    .filter((m) => m.is_active)
    .forEach((m) => {
      const opt = document.createElement("option");
      opt.value = String(m.id);
      opt.textContent = `${m.full_name || m.email} (${m.email})`;
      sel.appendChild(opt);
    });

  sel.value = r.assigned_to_member_id ? String(r.assigned_to_member_id) : "";

  $("mStatus").value = String(r.status || "PENDING").toUpperCase();

  // Notes
  const notes = await loadNotes(id);
  $("mNotes").textContent = notes.length
    ? notes.map((n) => `• ${n.created_at} — ${n.author_name || ("#" + n.author_id)}\n  ${n.note}`).join("\n\n")
    : "—";

  openModal();
}

async function saveAssignAndStatus() {
  if (!activeId) return;
  $("modalMsg").textContent = "Saving…";

  try {
    const assignedVal = $("mAssign").value;
    const statusVal = $("mStatus").value;

    // Assign
    await apiFetch(`/admin/requests/${activeId}/assign`, {
      method: "PATCH",
      body: JSON.stringify({ assigned_to_member_id: assignedVal ? Number(assignedVal) : null }),
    });

    // Status
    await apiFetch(`/admin/requests/${activeId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: statusVal }),
    });

    $("modalMsg").textContent = "Saved.";
    await loadRequests();
  } catch (e) {
    console.error(e);
    $("modalMsg").textContent = "Save failed.";
  }
}

$("saveAssignBtn").addEventListener("click", saveAssignAndStatus);

async function addNote() {
  if (!activeId) return;
  const note = $("mNote").value.trim();
  if (!note) return;

  $("modalMsg").textContent = "Saving note…";
  try {
    const resp = await apiFetch(`/admin/requests/${activeId}/note`, {
      method: "POST",
      body: JSON.stringify({ note }),
    });
    if (!resp.ok) throw new Error("note failed");
    $("mNote").value = "";
    $("modalMsg").textContent = "Note added.";
    const notes = await loadNotes(activeId);
    $("mNotes").textContent = notes.length
      ? notes.map((n) => `• ${n.created_at} — ${n.author_name || ("#" + n.author_id)}\n  ${n.note}`).join("\n\n")
      : "—";
    await loadRequests();
  } catch (e) {
    console.error(e);
    $("modalMsg").textContent = "Note failed.";
  }
}

$("saveNoteBtn").addEventListener("click", addNote);

async function decide(status) {
  if (!activeId) return;
  const decision_note = $("mNote").value.trim() || null;

  $("modalMsg").textContent = "Saving decision…";
  try {
    const resp = await apiFetch(`/admin/requests/${activeId}/decision`, {
      method: "PATCH",
      body: JSON.stringify({ status, decision_note }),
    });
    if (!resp.ok) throw new Error("decision failed");
    $("modalMsg").textContent = "Decision saved.";
    await loadRequests();
    closeModal();
  } catch (e) {
    console.error(e);
    $("modalMsg").textContent = "Decision failed.";
  }
}

$("approveBtn").addEventListener("click", () => decide("APPROVED"));
$("denyBtn").addEventListener("click", () => decide("DENIED"));

// initial
await loadRoster();
await loadRequests();
