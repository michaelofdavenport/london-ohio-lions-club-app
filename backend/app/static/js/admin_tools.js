// app/static/js/admin_tools.js
import { apiFetch, clearToken } from "./auth.js";
import { requireAdminOrRedirect } from "./admin_guard.js";

await requireAdminOrRedirect();

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmtDate(d) {
  if (!d) return "—";
  const s = String(d);
  return s.length >= 10 ? s.slice(0, 10) : s;
}

function pillStatus(status) {
  const s = String(status || "").toUpperCase();
  if (s === "PENDING") return `<span class="pill pending">PENDING</span>`;
  if (s === "APPROVED") return `<span class="pill approved">APPROVED</span>`;
  if (s === "DENIED") return `<span class="pill denied">DENIED</span>`;
  return `<span class="pill member">${escapeHtml(s || "—")}</span>`;
}

// -----------------------------------------------------
// PHONE FORMATTER (Admin Tools Member Modal)
// Forces: (xxx)xxx-xxxx, no matter how user types/pastes
// -----------------------------------------------------
function formatPhone(value) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 10);
  if (digits.length === 0) return "";
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `(${digits.slice(0, 3)})${digits.slice(3)}`;
  return `(${digits.slice(0, 3)})${digits.slice(3, 6)}-${digits.slice(6)}`;
}

function applyFormatKeepingCaret(input) {
  const prev = input.value;
  const prevPos = input.selectionStart ?? prev.length;

  const digitsBeforeCaret = prev.slice(0, prevPos).replace(/\D/g, "").length;

  const next = formatPhone(prev);
  input.value = next;

  let seenDigits = 0;
  let newPos = next.length;
  for (let i = 0; i < next.length; i++) {
    if (/\d/.test(next[i])) seenDigits++;
    if (seenDigits >= digitsBeforeCaret) {
      newPos = i + 1;
      break;
    }
  }

  try {
    input.setSelectionRange(newPos, newPos);
  } catch {}
}

function wireMemberPhoneFormatter() {
  const phoneEl = $("m_phone");
  if (!phoneEl) return;
  if (phoneEl.dataset.phoneWired === "1") return;

  phoneEl.dataset.phoneWired = "1";

  phoneEl.addEventListener("input", () => applyFormatKeepingCaret(phoneEl));
  phoneEl.addEventListener("blur", () => {
    phoneEl.value = formatPhone(phoneEl.value);
  });
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

// =================================================
// MEMBER MANAGEMENT (existing working code)
// =================================================

// ----------------------------
// MODAL STATE (members)
// ----------------------------
let editingId = null;

function openModal({ mode, member }) {
  const isEdit = mode === "edit";
  editingId = isEdit ? member.id : null;

  $("modalTitle").textContent = isEdit ? "Edit Member" : "Add Member";
  $("modalIdHint").textContent = isEdit ? `#${member.id}` : "";
  $("modalMsg").textContent = "";

  $("m_name").value = member?.full_name ?? "";
  $("m_email").value = member?.email ?? "";
  $("m_phone").value = formatPhone(member?.phone ?? ""); // ✅ normalize on open
  $("m_address").value = member?.address ?? "";
  $("m_since").value = member?.member_since ?? "";
  $("m_bday").value = member?.birthday ?? "";
  $("m_role").value = member?.is_admin ? "admin" : "member";

  $("passwordBlock").style.display = isEdit ? "none" : "block";
  $("m_password").value = "";

  $("m_email").disabled = isEdit;

  $("modalBackdrop").style.display = "flex";

  // ✅ wire formatter once modal is in use
  wireMemberPhoneFormatter();
}

function closeModal() {
  $("modalBackdrop").style.display = "none";
  editingId = null;
}

$("cancelBtn")?.addEventListener("click", closeModal);
$("modalBackdrop")?.addEventListener("click", (e) => {
  if (e.target === $("modalBackdrop")) closeModal();
});

$("addBtn")?.addEventListener("click", () => {
  openModal({ mode: "add", member: {} });
});

// ----------------------------
// LOAD + RENDER (members)
// ----------------------------
let allMembers = [];

function applyFilters() {
  const q = $("q").value.trim().toLowerCase();
  const f = $("filterActive").value;

  let rows = allMembers.slice();

  if (f === "active") rows = rows.filter((m) => m.is_active);
  if (f === "inactive") rows = rows.filter((m) => !m.is_active);

  if (q) {
    rows = rows.filter((m) => {
      const s = `${m.full_name ?? ""} ${m.email ?? ""} ${m.phone ?? ""}`.toLowerCase();
      return s.includes(q);
    });
  }

  render(rows);
}

function render(members) {
  const tbody = $("rows");
  tbody.innerHTML = "";

  $("countHint").textContent = `${members.length} member${members.length === 1 ? "" : "s"} shown`;

  for (const m of members) {
    const rolePill = m.is_admin
      ? `<span class="pill admin">Admin</span>`
      : `<span class="pill member">Member</span>`;

    const statusPill = m.is_active
      ? `<span class="pill active">Active</span>`
      : `<span class="pill inactive">Inactive</span>`;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(m.full_name || "—")}</td>
      <td>${escapeHtml(m.email || "—")}</td>
      <td>${escapeHtml(formatPhone(m.phone || "") || "—")}</td>
      <td>${rolePill}</td>
      <td>${statusPill}</td>
      <td>${escapeHtml(fmtDate(m.member_since))}</td>
      <td>${escapeHtml(fmtDate(m.birthday))}</td>
      <td>
        <div class="actions">
          <button class="btn btn-secondary btn-small" data-act="edit" data-id="${m.id}">Edit</button>
          <button class="btn btn-secondary btn-small" data-act="toggle" data-id="${m.id}">
            ${m.is_active ? "Deactivate" : "Activate"}
          </button>
          <button class="btn btn-secondary btn-small" data-act="reset" data-id="${m.id}">
            Reset Password
          </button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  }

  tbody.querySelectorAll("button[data-act]").forEach((btn) => {
    btn.addEventListener("click", onRowAction);
  });
}

async function loadMembers() {
  $("msg").textContent = "Loading…";
  try {
    const resp = await apiFetch("/admin/members");
    if (!resp.ok) throw new Error("Failed to load members (admin only).");

    allMembers = await resp.json();
    $("msg").textContent = "";
    applyFilters();
  } catch (err) {
    console.error(err);
    $("msg").textContent = "Failed to load members (are you logged in as ADMIN?).";
    allMembers = [];
    render([]);
  }
}

$("refreshBtn")?.addEventListener("click", loadMembers);
$("q")?.addEventListener("input", applyFilters);
$("filterActive")?.addEventListener("change", applyFilters);

// ----------------------------
// ROW ACTIONS (members)
// ----------------------------
async function onRowAction(e) {
  const id = Number(e.currentTarget.dataset.id);
  const act = e.currentTarget.dataset.act;
  const m = allMembers.find((x) => x.id === id);
  if (!m) return;

  if (act === "edit") {
    openModal({ mode: "edit", member: m });
    return;
  }

  if (act === "toggle") {
    const ok = confirm(`${m.is_active ? "Deactivate" : "Activate"} ${m.email}?`);
    if (!ok) return;

    try {
      const resp = await apiFetch(`/admin/members/${id}/active`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !m.is_active }),
      });

      if (!resp.ok) throw new Error("Toggle failed");
      await loadMembers();
    } catch (err) {
      console.error(err);
      alert("Update failed.");
    }
    return;
  }

  if (act === "reset") {
    const newPwd = prompt("Enter a NEW password (min 8 chars):");
    if (!newPwd) return;
    if (newPwd.length < 8) return alert("Password must be at least 8 characters.");

    const ok = confirm(`Reset password for ${m.email}?`);
    if (!ok) return;

    try {
      const resp = await apiFetch(`/admin/members/${id}/password`, {
        method: "PATCH",
        body: JSON.stringify({ password: newPwd }),
      });
      if (!resp.ok) throw new Error("Reset failed");
      alert("✅ Password updated.");
    } catch (err) {
      console.error(err);
      alert("Password reset failed.");
    }
    return;
  }
}

// ----------------------------
// SAVE (ADD / EDIT) (members)
// ----------------------------
$("saveBtn")?.addEventListener("click", async () => {
  $("modalMsg").textContent = "";

  // ✅ force normalization right before saving
  const phoneEl = $("m_phone");
  if (phoneEl) phoneEl.value = formatPhone(phoneEl.value);

  const full_name = $("m_name").value.trim() || null;
  const email = $("m_email").value.trim();
  const phone = (phoneEl?.value || "").trim() || null;
  const address = $("m_address").value.trim() || null;
  const member_since = $("m_since").value || null;
  const birthday = $("m_bday").value || null;
  const is_admin = $("m_role").value === "admin";

  const isEdit = Boolean(editingId);

  if (!isEdit) {
    if (!email) return ($("modalMsg").textContent = "Email is required.");
    const password = $("m_password").value;
    if (!password || password.length < 8) return ($("modalMsg").textContent = "Password must be 8+ characters.");

    const payload = { email, password, full_name, phone, address, member_since, birthday, is_admin };

    $("saveBtn").disabled = true;
    try {
      const resp = await apiFetch("/admin/members", { method: "POST", body: JSON.stringify(payload) });
      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        console.error(txt);
        $("modalMsg").textContent = "Create failed (email exists or invalid fields).";
        return;
      }
      closeModal();
      await loadMembers();
    } catch (err) {
      console.error(err);
      $("modalMsg").textContent = "Create failed (network/server).";
    } finally {
      $("saveBtn").disabled = false;
    }

    return;
  }

  const payload = { full_name, phone, address, member_since, birthday, is_admin };

  $("saveBtn").disabled = true;
  try {
    const resp = await apiFetch(`/admin/members/${editingId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const txt = await resp.text().catch(() => "");
      console.error(txt);
      $("modalMsg").textContent = "Update failed (invalid fields).";
      return;
    }

    closeModal();
    await loadMembers();
  } catch (err) {
    console.error(err);
    $("modalMsg").textContent = "Update failed (network/server).";
  } finally {
    $("saveBtn").disabled = false;
  }
});

// =================================================
// ADMIN REQUESTS (inside Admin Tools)
// =================================================

let allRequests = [];
let activeReqId = null;

function renderRequests(rows) {
  const tbody = $("reqRows");
  tbody.innerHTML = "";

  $("reqCountHint").textContent = `${rows.length} request${rows.length === 1 ? "" : "s"} shown`;

  for (const r of rows) {
    const tr = document.createElement("tr");

    const who = escapeHtml(r.requester_name || "—");
    const contactParts = [];
    if (r.requester_email) contactParts.push(escapeHtml(r.requester_email));
    if (r.requester_phone) contactParts.push(escapeHtml(r.requester_phone));
    const contact = contactParts.length ? contactParts.join("<br/>") : "—";

    const reviewed = r.reviewed_at
      ? `${escapeHtml(r.reviewed_by_name || ("#" + r.reviewed_by_member_id))}<br/><span class="mono">${escapeHtml(
          String(r.reviewed_at).replace("T", " ").slice(0, 19)
        )}</span>`
      : "—";

    const descShort =
      (r.description || "").length > 180 ? escapeHtml(r.description.slice(0, 180)) + "…" : escapeHtml(r.description || "—");

    const actions = `
      <div class="actions">
        <button class="btn btn-secondary btn-small" data-req-act="view" data-id="${r.id}">View</button>
        <button class="btn btn-danger btn-small" data-req-act="deny" data-id="${r.id}">Deny</button>
        <button class="btn btn-primary btn-small" data-req-act="approve" data-id="${r.id}">Approve</button>
      </div>
    `;

    tr.innerHTML = `
      <td class="mono">#${r.id}</td>
      <td>${escapeHtml(r.category || "—")}</td>
      <td>${pillStatus(r.status)}</td>
      <td>${who}</td>
      <td>${contact}</td>
      <td>${descShort}</td>
      <td>${reviewed}</td>
      <td>${actions}</td>
    `;

    tbody.appendChild(tr);
  }

  tbody.querySelectorAll("button[data-req-act]").forEach((b) => b.addEventListener("click", onReqAction));
}

function applyReqFilters() {
  const q = $("reqQ").value.trim().toLowerCase();
  const status = $("reqStatus").value;

  let rows = allRequests.slice();

  if (status) rows = rows.filter((r) => String(r.status || "").toUpperCase() === status);

  if (q) {
    rows = rows.filter((r) => {
      const s = `${r.requester_name ?? ""} ${r.requester_email ?? ""} ${r.description ?? ""}`.toLowerCase();
      return s.includes(q);
    });
  }

  renderRequests(rows);
}

async function loadRequests() {
  $("reqMsg").textContent = "Loading…";
  try {
    const params = new URLSearchParams();
    const status = $("reqStatus").value;
    const q = $("reqQ").value.trim();
    if (status) params.set("status", status);
    if (q) params.set("q", q);
    params.set("limit", "200");

    const resp = await apiFetch(`/admin/requests?${params.toString()}`);
    if (!resp.ok) throw new Error("Failed to load requests");

    allRequests = await resp.json();
    $("reqMsg").textContent = "";
    applyReqFilters();
  } catch (err) {
    console.error(err);
    allRequests = [];
    renderRequests([]);
    $("reqMsg").textContent = "Failed to load requests (are you logged in as ADMIN?).";
  }
}

$("reqRefreshBtn")?.addEventListener("click", loadRequests);
$("reqQ")?.addEventListener("input", applyReqFilters);
$("reqStatus")?.addEventListener("change", loadRequests);

// ---- Request modal ----
function openReqModal(req) {
  activeReqId = req.id;

  $("reqModalTitle").textContent = "Review Request";
  $("reqModalIdHint").textContent = `#${req.id} • ${req.category || "—"} • ${req.status || "—"}`;

  $("reqModalRequester").textContent = `${req.requester_name || "—"}${req.requester_email ? " • " + req.requester_email : ""}${
    req.requester_phone ? " • " + req.requester_phone : ""
  }`;
  $("reqModalAddress").textContent = req.requester_address || "—";
  $("reqModalDesc").textContent = req.description || "—";

  $("reqDecisionNote").value = "";
  $("reqModalMsg").textContent = "";

  $("reqModalBackdrop").style.display = "flex";
}

function closeReqModal() {
  $("reqModalBackdrop").style.display = "none";
  activeReqId = null;
}

$("reqCancelBtn")?.addEventListener("click", closeReqModal);
$("reqModalBackdrop")?.addEventListener("click", (e) => {
  if (e.target === $("reqModalBackdrop")) closeReqModal();
});

async function decideReq(status) {
  if (!activeReqId) return;

  const note = $("reqDecisionNote").value.trim() || null;

  $("reqApproveBtn").disabled = true;
  $("reqDenyBtn").disabled = true;

  try {
    const resp = await apiFetch(`/admin/requests/${activeReqId}/decision`, {
      method: "PATCH",
      body: JSON.stringify({ status, decision_note: note }),
    });

    if (!resp.ok) {
      const txt = await resp.text().catch(() => "");
      console.error(txt);
      $("reqModalMsg").textContent = "Decision failed.";
      return;
    }

    closeReqModal();
    await loadRequests();
  } catch (err) {
    console.error(err);
    $("reqModalMsg").textContent = "Decision failed (network/server).";
  } finally {
    $("reqApproveBtn").disabled = false;
    $("reqDenyBtn").disabled = false;
  }
}

$("reqApproveBtn")?.addEventListener("click", () => decideReq("APPROVED"));
$("reqDenyBtn")?.addEventListener("click", () => decideReq("DENIED"));

async function onReqAction(e) {
  const id = Number(e.currentTarget.dataset.id);
  const act = e.currentTarget.dataset.reqAct;

  const req = allRequests.find((x) => x.id === id);
  if (!req) return;

  if (act === "view") return openReqModal(req);

  if (act === "approve" || act === "deny") {
    openReqModal(req);
    if (act === "approve") $("reqApproveBtn")?.focus();
    if (act === "deny") $("reqDenyBtn")?.focus();
  }
}

// ----------------------------
// Export CSV (Admin Requests)
// ----------------------------
$("reqExportBtn")?.addEventListener("click", async () => {
  try {
    const q = $("reqQ")?.value?.trim() || "";
    const status = $("reqStatus")?.value || "";

    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (q) params.set("q", q);
    params.set("limit", "10000");

    const resp = await apiFetch(`/admin/requests/export.csv?${params.toString()}`);
    if (!resp.ok) throw new Error("Export failed");

    const blob = await resp.blob();

    const cd = resp.headers.get("Content-Disposition") || "";
    const match = cd.match(/filename="([^"]+)"/);
    const filename = match?.[1] || "requests_export.csv";

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (err) {
    console.error(err);
    alert("Export CSV failed.");
  }
});

// ----------------------------
// Test Email (button in Admin Tools)
// ----------------------------
const testEmailBtn = $("sendTestEmailBtn");
const testEmailTo = $("testEmailTo");
const testEmailMsg = $("testEmailMsg");

testEmailBtn?.addEventListener("click", async () => {
  if (testEmailMsg) testEmailMsg.textContent = "Sending…";

  const to = (testEmailTo?.value || "").trim();

  try {
    const url = to ? `/admin/email/test?to_email=${encodeURIComponent(to)}` : "/admin/email/test";
    const resp = await apiFetch(url, { method: "POST" });

    if (resp.status === 403) {
      if (testEmailMsg) testEmailMsg.textContent = "Forbidden (admin only).";
      return;
    }
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      if (testEmailMsg) testEmailMsg.textContent = `Failed: ${err.detail || "Unknown error"}`;
      return;
    }

    const data = await resp.json();
    if (data.ok) {
      if (testEmailMsg) testEmailMsg.textContent = `✅ Sent to ${data.to}`;
    } else {
      if (testEmailMsg) testEmailMsg.textContent = `⚠️ Not sent. Check server console + .env SMTP values.`;
    }
  } catch (e) {
    console.error(e);
    if (testEmailMsg) testEmailMsg.textContent = "Failed to send (see console).";
  }
});

// ----------------------------
// initial loads
// ----------------------------
loadMembers();
loadRequests();
