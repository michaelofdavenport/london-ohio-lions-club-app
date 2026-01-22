// app/static/js/inbox.js
import { apiFetch, clearToken } from "./auth.js";
import { requireAdminOrRedirect } from "./admin_guard.js";

await requireAdminOrRedirect();

// -----------------------
// Helpers (safe DOM)
// -----------------------
const $ = (id) => document.getElementById(id);
const on = (id, evt, fn) => {
  const el = $(id);
  if (el) el.addEventListener(evt, fn);
};

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

// -----------------------
// Nav / header buttons
// -----------------------
on("dashBtn", "click", () => (window.location.href = "/static/dashboard.html"));

// ✅ FIX: your working Admin Tools page is static (per your screenshot)
on("adminToolsBtn", "click", () => (window.location.href = "/static/admin_tools.html"));

on("logoutBtn", "click", () => {
  clearToken();
  window.location.href = "/static/public_request.html";
});
on("printBtn", "click", () => window.print());

// -----------------------
// Modal open/close
// -----------------------
function openModal() {
  const mb = $("modalBackdrop");
  if (mb) mb.style.display = "flex";
}
function closeModal() {
  const mb = $("modalBackdrop");
  if (mb) mb.style.display = "none";
  activeId = null;
}

on("closeBtn", "click", closeModal);

on("modalBackdrop", "click", (e) => {
  const mb = $("modalBackdrop");
  if (mb && e.target === mb) closeModal();
});

// -----------------------
// Data loads
// -----------------------
async function loadRoster() {
  try {
    const resp = await apiFetch("/admin/members");
    if (!resp.ok) return (roster = []);

    const data = await resp.json().catch(() => []);
    roster = Array.isArray(data)
      ? data
      : Array.isArray(data.members)
        ? data.members
        : Array.isArray(data.items)
          ? data.items
          : [];
  } catch {
    roster = [];
  }
}

function render(rows) {
  const tbody = $("rows");
  if (!tbody) return;

  tbody.innerHTML = "";

  const countHint = $("countHint");
  if (countHint) countHint.textContent = `${rows.length} request${rows.length === 1 ? "" : "s"}`;

  for (const r of rows) {
    const assigned = r.assigned_to_name
      ? escapeHtml(r.assigned_to_name)
      : `<span class="muted">Unassigned</span>`;

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

  // ❌ No per-button wiring here anymore.
  // ✅ We use event delegation below so re-renders never break buttons.
}

function applyFilters() {
  const qEl = $("q");
  const statusEl = $("status");
  const assignedEl = $("assigned");

  const q = (qEl?.value || "").trim().toLowerCase();
  const status = statusEl?.value || "";
  const assigned = assignedEl?.value || "";

  let rows = Array.isArray(all) ? all.slice() : [];

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
  const msgEl = $("msg");
  if (msgEl) msgEl.textContent = "Loading…";

  try {
    const params = new URLSearchParams();

    const status = $("status")?.value || "";
    const q = ($("q")?.value || "").trim();
    const assigned = $("assigned")?.value || "";

    if (status) params.set("status", status);
    if (q) params.set("q", q);
    if (assigned) params.set("assigned", assigned);

    params.set("limit", "300");

    const resp = await apiFetch(`/admin/requests?${params.toString()}`);
    if (!resp.ok) throw new Error("Failed to load");

    const data = await resp.json().catch(() => []);
    all = Array.isArray(data)
      ? data
      : Array.isArray(data.requests)
        ? data.requests
        : Array.isArray(data.items)
          ? data.items
          : [];

    if (msgEl) msgEl.textContent = "";
    applyFilters();
  } catch (e) {
    console.error(e);
    all = [];
    render([]);
    if (msgEl) msgEl.textContent = "Failed to load requests.";
  }
}

// Toolbar hooks (safe)
on("refreshBtn", "click", loadRequests);
on("q", "input", applyFilters);
on("status", "change", loadRequests);
on("assigned", "change", loadRequests);

// -----------------------
// NOTES (requires backend endpoints)
// -----------------------
async function loadNotes(requestId) {
  try {
    const resp = await apiFetch(`/admin/requests/${requestId}/notes`);
    if (!resp.ok) return [];
    return await resp.json();
  } catch {
    return [];
  }
}

function renderNotes(notes) {
  const el = $("mNotes");
  if (!el) return;

  const sorted = (notes || []).slice().sort((a, b) => {
    const da = Date.parse(a?.created_at || "") || 0;
    const db = Date.parse(b?.created_at || "") || 0;
    return db - da;
  });

  el.textContent = sorted.length
    ? sorted
        .map((n) => `• ${n.created_at} — ${n.author_name || ("#" + n.author_id)}\n  ${n.note}`)
        .join("\n\n")
    : "—";

  try {
    el.scrollTop = 0;
  } catch {}
}

// -----------------------
// OPEN MODAL
// -----------------------
async function openRequestById(id) {
  const rid = Number(id);
  const r = (Array.isArray(all) ? all : []).find((x) => x.id === rid);
  if (!r) return;

  activeId = rid;

  if ($("modalTitle")) $("modalTitle").textContent = "Request";
  if ($("modalHint")) $("modalHint").textContent = `#${r.id} • ${r.category} • ${r.status}`;

  if ($("mWho")) {
    $("mWho").textContent =
      `${r.requester_name || "—"}`
      + (r.requester_email ? ` • ${r.requester_email}` : "")
      + (r.requester_phone ? ` • ${r.requester_phone}` : "");
  }

  if ($("mAddr")) $("mAddr").textContent = r.requester_address || "—";
  if ($("mDesc")) $("mDesc").textContent = r.description || "—";
  if ($("mNote")) $("mNote").value = "";
  if ($("modalMsg")) $("modalMsg").textContent = "";

  // Assign dropdown
  const sel = $("mAssign");
  if (sel) {
    sel.innerHTML = "";

    const opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = "Unassigned";
    sel.appendChild(opt0);

    (Array.isArray(roster) ? roster : [])
      .filter((m) => m.is_active)
      .forEach((m) => {
        const opt = document.createElement("option");
        opt.value = String(m.id);
        opt.textContent = `${m.full_name || m.email} (${m.email})`;
        sel.appendChild(opt);
      });

    sel.value = r.assigned_to_member_id ? String(r.assigned_to_member_id) : "";
  }

  if ($("mStatus")) $("mStatus").value = String(r.status || "PENDING").toUpperCase();

  const notes = await loadNotes(rid);
  renderNotes(notes);

  openModal();
}

// ✅ BULLETPROOF: event delegation for Open buttons (survives re-renders)
document.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-act='open']");
  if (!btn) return;

  const id = btn.dataset.id;
  if (!id) {
    console.warn("Open clicked but missing data-id", btn);
    return alert("Open failed: missing request id.");
  }

  openRequestById(id);
});

// -----------------------
// SAVE ASSIGN + STATUS
// NOW uses /admin/requests/{id}/assign-status to trigger email
// -----------------------
async function saveAssignAndStatus() {
  if (!activeId) return;
  if ($("modalMsg")) $("modalMsg").textContent = "Saving…";

  try {
    const assignedVal = $("mAssign")?.value || "";
    const statusVal = $("mStatus")?.value || "PENDING";

    const resp = await apiFetch(`/admin/requests/${activeId}/assign-status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: statusVal,
        assigned_to_member_id: assignedVal ? Number(assignedVal) : null,
      }),
    });

    if (!resp.ok) {
      let detail = "Save failed.";
      try {
        const data = await resp.json();
        if (data?.detail) detail = String(data.detail);
      } catch {}
      throw new Error(detail);
    }

    // show email result if provided
    let msg = "Saved.";
    try {
      const data = await resp.json();
      if (data?.email_sent) msg = "Saved + email sent.";
      else if (data?.email_error) msg = `Saved, but email failed: ${data.email_error}`;
    } catch {}

    if ($("modalMsg")) $("modalMsg").textContent = msg;

    await loadRequests();
    const notes = await loadNotes(activeId);
    renderNotes(notes);
  } catch (e) {
    console.error(e);
    if ($("modalMsg")) $("modalMsg").textContent = String(e?.message || "Save failed.");
  }
}

on("saveAssignBtn", "click", saveAssignAndStatus);

// -----------------------
// ADD NOTE (requires /note)
// -----------------------
async function addNote() {
  if (!activeId) return;

  const note = ($("mNote")?.value || "").trim();
  if (!note) {
    if ($("modalMsg")) $("modalMsg").textContent = "Type a note first.";
    return;
  }

  if ($("modalMsg")) $("modalMsg").textContent = "Saving note…";

  try {
    const resp = await apiFetch(`/admin/requests/${activeId}/note`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    });

    if (!resp.ok) {
      let detail = "Note failed.";
      try {
        const data = await resp.json();
        if (data?.detail) detail = String(data.detail);
      } catch {}
      throw new Error(detail);
    }

    if ($("mNote")) $("mNote").value = "";
    if ($("modalMsg")) $("modalMsg").textContent = "Note added.";

    const notes = await loadNotes(activeId);
    renderNotes(notes);

    await loadRequests();
  } catch (e) {
    console.error(e);
    if ($("modalMsg")) $("modalMsg").textContent = String(e?.message || "Note failed.");
  }
}

on("saveNoteBtn", "click", addNote);

// -----------------------
// APPROVE / DENY (uses /decision)
// -----------------------
async function decide(status) {
  if (!activeId) return;

  const decision_note = ($("mNote")?.value || "").trim() || null;
  if ($("modalMsg")) $("modalMsg").textContent = "Saving decision…";

  try {
    const resp = await apiFetch(`/admin/requests/${activeId}/decision`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, decision_note }),
    });

    if (!resp.ok) throw new Error("Decision failed.");

    if ($("modalMsg")) $("modalMsg").textContent = "Decision saved.";
    await loadRequests();
    closeModal();
  } catch (e) {
    console.error(e);
    if ($("modalMsg")) $("modalMsg").textContent = "Decision failed.";
  }
}

on("approveBtn", "click", () => decide("APPROVED"));
on("denyBtn", "click", () => decide("DENIED"));

// -----------------------
// initial
// -----------------------
await loadRoster();
await loadRequests();
