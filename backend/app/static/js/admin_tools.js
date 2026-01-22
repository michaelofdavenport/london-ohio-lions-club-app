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
// ✅ API MEMBER NORMALIZER
// Canonical UI fields: full_name + phone
// -----------------------------------------------------
function normalizeMember(raw) {
  const m = raw || {};

  const nameCandidates = [
    m?.full_name,
    m?.fullName,
    m?.name,
    m?.display_name,
    m?.displayName,
    m?.member_name,
    m?.memberName,
  ];

  const fn = String(m?.first_name ?? m?.firstName ?? "").trim();
  const ln = String(m?.last_name ?? m?.lastName ?? "").trim();
  if (fn || ln) nameCandidates.push(`${fn} ${ln}`.trim());

  let full_name = null;
  for (const v of nameCandidates) {
    const s = String(v ?? "").trim();
    if (s) {
      full_name = s;
      break;
    }
  }

  const phoneCandidates = [
    m?.phone,
    m?.phone_number,
    m?.phoneNumber,
    m?.mobile,
    m?.mobile_phone,
    m?.mobilePhone,
  ];

  let phone = null;
  for (const v of phoneCandidates) {
    const s = String(v ?? "").trim();
    if (s) {
      phone = s;
      break;
    }
  }

  return { ...m, full_name, phone };
}

// -----------------------------------------------------
// ✅ NAME NORMALIZER (Admin Tools "Name" column)
// -----------------------------------------------------
function getMemberName(m) {
  const candidates = [
    m?.full_name,
    m?.fullName,
    m?.name,
    m?.display_name,
    m?.displayName,
    m?.member_name,
    m?.memberName,
  ];

  for (const v of candidates) {
    const s = String(v ?? "").trim();
    if (s) return s;
  }

  const email = String(m?.email ?? "").trim();
  return email || "—";
}

// -----------------------------------------------------
// PHONE FORMATTER (modal)
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

// -----------------------------------------------------
// ✅ Roster refresh flag (roster page can listen later)
// -----------------------------------------------------
function bumpRosterRefreshFlag() {
  try {
    localStorage.setItem("roster_needs_refresh", String(Date.now()));
  } catch {}
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

// =====================================================
// OWNER TOOLS (existing)
// =====================================================
let isOwner = false;
let adminRole = "ADMIN";

async function loadAdminContextAndWireOwnerTools() {
  const ownerSection = $("ownerToolsSection");
  const ownerMsgEl = $("ownerToolsMsg");
  const billingCard = $("billingSection");

  if (ownerSection) ownerSection.style.display = "none";
  if (billingCard) billingCard.style.display = "none";
  if (ownerMsgEl) ownerMsgEl.textContent = "";

  try {
    const resp = await apiFetch("/admin/ping");
    if (!resp.ok) throw new Error("admin/ping failed");

    const ctx = await resp.json();
    adminRole = String(ctx.role || "ADMIN").toUpperCase();
    isOwner = adminRole === "OWNER";

    if (isOwner && ownerSection) {
      ownerSection.style.display = "block";

      const promoteBtn = $("ownerPromoteAdminBtn");
      const transferBtn = $("ownerTransferBtn");
      const settingsBtn = $("ownerClubSettingsBtn");

      if (promoteBtn && promoteBtn.dataset.wired !== "1") {
        promoteBtn.dataset.wired = "1";
        promoteBtn.addEventListener("click", ownerPromoteDemoteAdmin);
      }
      if (transferBtn && transferBtn.dataset.wired !== "1") {
        transferBtn.dataset.wired = "1";
        transferBtn.addEventListener("click", ownerTransferOwnership);
      }
      if (settingsBtn && settingsBtn.dataset.wired !== "1") {
        settingsBtn.dataset.wired = "1";
        settingsBtn.addEventListener("click", ownerUpdateClubSettings);
      }

      if (ownerMsgEl) ownerMsgEl.textContent = "✅ Owner tools enabled.";
    }

    await loadBillingAndWireUI();
  } catch (err) {
    console.error(err);
    isOwner = false;
    adminRole = "ADMIN";
    await loadBillingAndWireUI();
  }
}

async function ownerPromoteDemoteAdmin() {
  const msgEl = $("ownerToolsMsg");
  if (msgEl) msgEl.textContent = "";

  const memberIdStr = prompt("Enter the MEMBER ID to change admin status (example: 12):");
  if (!memberIdStr) return;

  const memberId = Number(memberIdStr);
  if (!Number.isFinite(memberId) || memberId <= 0) return alert("Invalid member id.");

  const makeAdmin = confirm("OK = Promote to ADMIN\nCancel = Demote to MEMBER");
  const ok2 = confirm(`${makeAdmin ? "PROMOTE" : "DEMOTE"} member #${memberId}?`);
  if (!ok2) return;

  try {
    if (msgEl) msgEl.textContent = "Saving…";

    const resp = await apiFetch(`/owner/members/${memberId}/admin`, {
      method: "PATCH",
      body: JSON.stringify({ is_admin: makeAdmin }),
    });

    if (resp.status === 403) {
      if (msgEl) msgEl.textContent = "Forbidden (OWNER only).";
      return;
    }
    if (!resp.ok) {
      const t = await resp.text().catch(() => "");
      console.error(t);
      if (msgEl) msgEl.textContent = "Failed (check member ID / permissions).";
      return;
    }

    if (msgEl) msgEl.textContent = `✅ Updated member #${memberId}.`;
    await loadMembers();
  } catch (err) {
    console.error(err);
    if (msgEl) msgEl.textContent = "Failed (network/server).";
  }
}

async function ownerTransferOwnership() {
  const msgEl = $("ownerToolsMsg");
  if (msgEl) msgEl.textContent = "";

  const newOwnerIdStr = prompt("Enter the MEMBER ID of the NEW OWNER (example: 12):");
  if (!newOwnerIdStr) return;

  const newOwnerId = Number(newOwnerIdStr);
  if (!Number.isFinite(newOwnerId) || newOwnerId <= 0) return alert("Invalid member id.");

  const ok = confirm(`Transfer OWNERSHIP to member #${newOwnerId}?`);
  if (!ok) return;

  try {
    if (msgEl) msgEl.textContent = "Transferring…";

    const resp = await apiFetch(`/owner/transfer`, {
      method: "POST",
      body: JSON.stringify({ new_owner_member_id: newOwnerId }),
    });

    if (resp.status === 403) {
      if (msgEl) msgEl.textContent = "Forbidden (OWNER only).";
      return;
    }
    if (!resp.ok) {
      const t = await resp.text().catch(() => "");
      console.error(t);
      if (msgEl) msgEl.textContent = "Transfer failed (check member ID / permissions).";
      return;
    }

    if (msgEl) msgEl.textContent = "✅ Ownership transferred.";
    await loadMembers();
    await loadAdminContextAndWireOwnerTools();
  } catch (err) {
    console.error(err);
    if (msgEl) msgEl.textContent = "Transfer failed (network/server).";
  }
}

async function ownerUpdateClubSettings() {
  const msgEl = $("ownerToolsMsg");
  if (msgEl) msgEl.textContent = "";

  const name = prompt("Club name (leave blank to keep current):") || "";
  const logo_url = prompt("Logo URL (leave blank to keep current):") || "";

  const activeChoice = prompt("Club active? type: active / inactive / blank to keep");
  let is_active = null;
  if (activeChoice) {
    const v = activeChoice.trim().toLowerCase();
    if (v === "active") is_active = true;
    else if (v === "inactive") is_active = false;
    else return alert("Please type: active, inactive, or leave blank.");
  }

  const payload = {};
  if (name.trim()) payload.name = name.trim();
  if (logo_url.trim()) payload.logo_url = logo_url.trim();
  if (is_active !== null) payload.is_active = is_active;

  if (!Object.keys(payload).length) return;

  const ok = confirm(`Update club settings with:\n\n${JSON.stringify(payload, null, 2)}`);
  if (!ok) return;

  try {
    if (msgEl) msgEl.textContent = "Saving…";

    const resp = await apiFetch(`/owner/club`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });

    if (resp.status === 403) {
      if (msgEl) msgEl.textContent = "Forbidden (OWNER only).";
      return;
    }
    if (!resp.ok) {
      const t = await resp.text().catch(() => "");
      console.error(t);
      if (msgEl) msgEl.textContent = "Update failed.";
      return;
    }

    if (msgEl) msgEl.textContent = "✅ Club settings updated.";
  } catch (err) {
    console.error(err);
    if (msgEl) msgEl.textContent = "Update failed (network/server).";
  }
}

// =====================================================
// STRIPE BILLING (existing)
// =====================================================
function fmtPeriodEnd(iso) {
  if (!iso) return "—";
  const s = String(iso);
  return s.length >= 10 ? s.slice(0, 10) : s;
}

function fmtTrialLine(trial) {
  const st = String(trial?.status || "never").toLowerCase();
  if (st === "active") return `✅ Free Trial: ${trial.days_left} day(s) left (ends ${fmtPeriodEnd(trial.expires_at)})`;
  if (st === "expired") return `⛔ Free Trial expired (ended ${fmtPeriodEnd(trial.expires_at)})`;
  if (st === "blocked") return `⛔ Free Trial already used for this email (one-time only).`;
  return `🆓 Free Trial available (7 days).`;
}

async function loadBillingAndWireUI() {
  const card = $("billingSection");
  const msgEl = $("billingMsg");

  if (!card) return;

  card.style.display = "block";
  if (msgEl) msgEl.textContent = "";

  const planEl = $("billingPlan");
  const statusEl = $("billingStatus");
  const endEl = $("billingPeriodEnd");
  const upgradeBtn = $("billingUpgradeBtn");
  const manageBtn = $("billingManageBtn");

  const trialLineEl = $("trialLine");
  const startTrialBtn = $("startTrialBtn");
  const lockLineEl = $("lockLine");

  if (manageBtn) manageBtn.style.display = isOwner ? "inline-block" : "none";

  if (upgradeBtn && upgradeBtn.dataset.wired !== "1") {
    upgradeBtn.dataset.wired = "1";
    upgradeBtn.addEventListener("click", async () => {
      if (msgEl) msgEl.textContent = "Creating Stripe checkout…";
      try {
        const resp = await apiFetch("/billing/checkout", { method: "POST" });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          if (msgEl) msgEl.textContent = `Checkout failed: ${err.detail || "Unknown error"}`;
          return;
        }
        const data = await resp.json();
        if (data.url) window.location.href = data.url;
      } catch (e) {
        console.error(e);
        if (msgEl) msgEl.textContent = "Checkout failed (network/server).";
      }
    });
  }

  if (manageBtn && manageBtn.dataset.wired !== "1") {
    manageBtn.dataset.wired = "1";
    manageBtn.addEventListener("click", async () => {
      if (msgEl) msgEl.textContent = "Opening Stripe portal…";
      try {
        const resp = await apiFetch("/billing/portal", { method: "POST" });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          if (msgEl) msgEl.textContent = `Portal failed: ${err.detail || "Unknown error"}`;
          return;
        }
        const data = await resp.json();
        if (data.url) window.location.href = data.url;
      } catch (e) {
        console.error(e);
        if (msgEl) msgEl.textContent = "Portal failed (network/server).";
      }
    });
  }

  if (startTrialBtn) startTrialBtn.style.display = isOwner ? "inline-block" : "none";

  if (startTrialBtn && startTrialBtn.dataset.wired !== "1") {
    startTrialBtn.dataset.wired = "1";
    startTrialBtn.addEventListener("click", async () => {
      const ok = confirm("Start your ONE-TIME 7-day Free Trial now?");
      if (!ok) return;

      if (msgEl) msgEl.textContent = "Starting free trial…";
      try {
        const resp = await apiFetch("/billing/start-trial", { method: "POST" });
        const data = await resp.json().catch(() => ({}));

        if (!resp.ok || data.ok === false) {
          const code = data.code || "TRIAL_START_FAILED";
          if (msgEl) msgEl.textContent = `Trial could not start: ${code}`;
          return;
        }

        if (msgEl) msgEl.textContent = "✅ Free Trial started.";
        await loadBillingAndWireUI();
      } catch (e) {
        console.error(e);
        if (msgEl) msgEl.textContent = "Trial start failed (network/server).";
      }
    });
  }

  try {
    const resp = await apiFetch("/billing/me");
    if (!resp.ok) throw new Error("billing/me failed");
    const data = await resp.json();

    const club = data.club || {};
    const plan = String(club.plan || "FREE").toUpperCase();
    const st = String(club.subscription_status || "inactive").toLowerCase();
    const pe = fmtPeriodEnd(club.current_period_end);

    if (planEl) planEl.textContent = plan;
    if (statusEl) statusEl.textContent = st;
    if (endEl) endEl.textContent = pe;

    if (upgradeBtn) {
      upgradeBtn.disabled = st === "active" || st === "trialing";
      upgradeBtn.textContent = upgradeBtn.disabled ? "PRO Active" : "Upgrade to PRO";
    }

    let statusData = null;
    try {
      const sresp = await apiFetch("/billing/status");
      if (sresp.ok) statusData = await sresp.json();
    } catch (e) {
      console.warn("billing/status not available yet", e);
    }

    if (statusData) {
      const trial = statusData.trial || { status: "never" };
      const locked = Boolean(statusData.is_locked);
      const canStart = Boolean(statusData.can_start_trial);

      if (trialLineEl) trialLineEl.textContent = fmtTrialLine(trial);

      if (lockLineEl) {
        lockLineEl.textContent = locked
          ? "⛔ App Locked: Trial ended. Upgrade to PRO to continue using the app."
          : "";
      }

      if (startTrialBtn) {
        startTrialBtn.disabled = !canStart || trial?.status === "active";
        startTrialBtn.textContent =
          trial?.status === "active"
            ? "Trial Active"
            : canStart
            ? "Start Free Trial (7 days)"
            : "Trial Unavailable";
      }

      if (locked && msgEl) msgEl.textContent = "⛔ Trial ended — upgrade to PRO to unlock the app.";
    }

    if (msgEl) {
      const urlParams = new URLSearchParams(window.location.search);
      const billingFlag = urlParams.get("billing");
      if (billingFlag === "success") msgEl.textContent = "✅ Checkout completed.";
      else if (billingFlag === "cancel") msgEl.textContent = "Checkout canceled.";
      else if (billingFlag === "portal_return") msgEl.textContent = "Returned from Stripe portal.";
    }
  } catch (err) {
    console.error(err);
    if (msgEl) msgEl.textContent = "Could not load billing status.";
  }
}

// =================================================
// MEMBER MANAGEMENT
// =================================================
let editingId = null;
let editingIsActive = true;

function openModal({ mode, member }) {
  const isEdit = mode === "edit";
  editingId = isEdit ? member.id : null;

  editingIsActive = Boolean(member?.is_active ?? true);

  $("modalTitle").textContent = isEdit ? "Edit Member" : "Add Member";
  $("modalIdHint").textContent = isEdit ? `#${member.id}` : "";
  $("modalMsg").textContent = "";

  $("m_name").value = member?.full_name ?? "";
  $("m_email").value = member?.email ?? "";
  $("m_phone").value = formatPhone(member?.phone ?? "");
  $("m_address").value = member?.address ?? "";
  $("m_since").value = member?.member_since ?? "";
  $("m_bday").value = member?.birthday ?? "";
  $("m_role").value = member?.is_admin ? "admin" : "member";

  $("passwordBlock").style.display = isEdit ? "none" : "block";
  $("m_password").value = "";

  // Default behavior: lock email on edit
  $("m_email").disabled = isEdit;

  $("modalBackdrop").style.display = "flex";
  wireMemberPhoneFormatter();
}

function closeModal() {
  $("modalBackdrop").style.display = "none";
  editingId = null;
  editingIsActive = true;
}

$("cancelBtn")?.addEventListener("click", (e) => {
  e.preventDefault?.();
  closeModal();
});

$("modalBackdrop")?.addEventListener("click", (e) => {
  if (e.target === $("modalBackdrop")) closeModal();
});

$("addBtn")?.addEventListener("click", (e) => {
  e.preventDefault?.();
  openModal({ mode: "add", member: {} });
});

// ----------------------------
// LOAD + RENDER (members)
// ----------------------------
let allMembers = [];

function applyFilters() {
  const q = ($("q")?.value || "").trim().toLowerCase();
  const f = $("filterActive")?.value || "all";

  let rows = Array.isArray(allMembers) ? allMembers.slice() : [];

  if (f === "active") rows = rows.filter((m) => m.is_active);
  if (f === "inactive") rows = rows.filter((m) => !m.is_active);

  if (q) {
    rows = rows.filter((m) => {
      const s = `${getMemberName(m)} ${m.email ?? ""} ${m.phone ?? ""}`.toLowerCase();
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

    const displayName = getMemberName(m);
    const displayPhone = formatPhone(m.phone || "") || "—";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(displayName)}</td>
      <td>${escapeHtml(m.email || "—")}</td>
      <td>${escapeHtml(displayPhone)}</td>
      <td>${rolePill}</td>
      <td>${statusPill}</td>
      <td>${escapeHtml(fmtDate(m.member_since))}</td>
      <td>${escapeHtml(fmtDate(m.birthday))}</td>
      <td>
        <div class="actions">
          <button class="btn btn-secondary btn-small" type="button" data-act="edit" data-id="${m.id}">
            Edit
          </button>

          <button class="btn btn-secondary btn-small" type="button" data-act="toggle" data-id="${m.id}">
            ${m.is_active ? "Deactivate" : "Activate"}
          </button>

          <button class="btn btn-secondary btn-small" type="button" data-act="reset" data-id="${m.id}">
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

    const data = await resp.json();

    const items = Array.isArray(data)
      ? data
      : Array.isArray(data.members)
      ? data.members
      : Array.isArray(data.items)
      ? data.items
      : [];

    allMembers = items.map(normalizeMember);

    $("msg").textContent = "";
    applyFilters();
  } catch (err) {
    console.error(err);
    $("msg").textContent = "Failed to load members (are you logged in as ADMIN?).";
    allMembers = [];
    render([]);
  }
}

$("refreshBtn")?.addEventListener("click", (e) => {
  e.preventDefault?.();
  loadMembers();
});
$("q")?.addEventListener("input", applyFilters);
$("filterActive")?.addEventListener("change", applyFilters);

// ----------------------------
// ROW ACTIONS (members)
// ----------------------------
async function onRowAction(e) {
  e.preventDefault?.();

  const id = Number(e.currentTarget.dataset.id);
  const act = e.currentTarget.dataset.act;
  const m = (Array.isArray(allMembers) ? allMembers : []).find((x) => x.id === id);
  if (!m) return;

  if (act === "edit") {
    const normalized = normalizeMember(m);
    openModal({ mode: "edit", member: normalized });

    // If you truly want email editable from Admin Tools:
    const emailEl = $("m_email");
    if (emailEl) emailEl.disabled = false;

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
      bumpRosterRefreshFlag();
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
// SAVE (ADD / EDIT)
// ----------------------------
const saveBtn = $("saveBtn");
if (saveBtn) {
  saveBtn.addEventListener("click", async (e) => {
    e.preventDefault();

    $("modalMsg").textContent = "";

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

    // ADD
    if (!isEdit) {
      if (!email) return ($("modalMsg").textContent = "Email is required.");
      const password = $("m_password").value;
      if (!password || password.length < 8)
        return ($("modalMsg").textContent = "Password must be 8+ characters.");

      const payload = {
        email,
        password,
        full_name,
        name: full_name,
        display_name: full_name,
        phone,
        phone_number: phone,
        address,
        member_since,
        birthday,
        is_admin,
      };

      saveBtn.disabled = true;
      try {
        const resp = await apiFetch("/admin/members", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        if (!resp.ok) {
          const txt = await resp.text().catch(() => "");
          console.error("POST /admin/members failed:", resp.status, txt);
          $("modalMsg").textContent = `Create failed (${resp.status}): ${txt || "Invalid fields"}`;
          return;
        }
        closeModal();
        await loadMembers();
        bumpRosterRefreshFlag();
      } catch (err) {
        console.error(err);
        $("modalMsg").textContent = "Create failed (network/server).";
      } finally {
        saveBtn.disabled = false;
      }
      return;
    }

    // EDIT
    const payload = {
      email, // you asked to allow email updates
      full_name,
      name: full_name,
      display_name: full_name,
      phone,
      phone_number: phone,
      address,
      member_since,
      birthday,
      is_admin,
      role: is_admin ? "ADMIN" : "MEMBER",
      is_active: editingIsActive,
    };

    saveBtn.disabled = true;
    try {
      const resp = await apiFetch(`/admin/members/${editingId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        console.error("PATCH /admin/members failed:", resp.status, txt);
        $("modalMsg").textContent = `Update failed (${resp.status}): ${txt || "Invalid fields"}`;
        return;
      }

      closeModal();
      await loadMembers();
      bumpRosterRefreshFlag();
    } catch (err) {
      console.error(err);
      $("modalMsg").textContent = "Update failed (network/server).";
    } finally {
      saveBtn.disabled = false;
    }
  });
}

// =================================================
// ADMIN REQUESTS (unchanged)
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
      (r.description || "").length > 180
        ? escapeHtml(r.description.slice(0, 180)) + "…"
        : escapeHtml(r.description || "—");

    const actions = `
      <div class="actions">
        <button class="btn btn-secondary btn-small" type="button" data-req-act="view" data-id="${r.id}">View</button>
        <button class="btn btn-danger btn-small" type="button" data-req-act="deny" data-id="${r.id}">Deny</button>
        <button class="btn btn-primary btn-small" type="button" data-req-act="approve" data-id="${r.id}">Approve</button>
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
  const q = ($("reqQ")?.value || "").trim().toLowerCase();
  const status = $("reqStatus")?.value || "";

  let rows = Array.isArray(allRequests) ? allRequests.slice() : [];

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

    const data = await resp.json();
    allRequests = Array.isArray(data)
      ? data
      : Array.isArray(data.requests)
      ? data.requests
      : Array.isArray(data.items)
      ? data.items
      : [];

    $("reqMsg").textContent = "";
    applyReqFilters();
  } catch (err) {
    console.error(err);
    allRequests = [];
    renderRequests([]);
    $("reqMsg").textContent = "Failed to load requests (are you logged in as ADMIN?).";
  }
}

$("reqRefreshBtn")?.addEventListener("click", (e) => {
  e.preventDefault?.();
  loadRequests();
});
$("reqQ")?.addEventListener("input", applyReqFilters);
$("reqStatus")?.addEventListener("change", loadRequests);

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

$("reqCancelBtn")?.addEventListener("click", (e) => {
  e.preventDefault?.();
  closeReqModal();
});
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
  e.preventDefault?.();

  const id = Number(e.currentTarget.dataset.id);
  const act = e.currentTarget.dataset.reqAct;

  const req = (Array.isArray(allRequests) ? allRequests : []).find((x) => x.id === id);
  if (!req) return;

  if (act === "view") return openReqModal(req);

  if (act === "approve" || act === "deny") {
    openReqModal(req);
    if (act === "approve") $("reqApproveBtn")?.focus();
    if (act === "deny") $("reqDenyBtn")?.focus();
  }
}

// ----------------------------
// Export CSV
// ----------------------------
$("reqExportBtn")?.addEventListener("click", async (e) => {
  e.preventDefault?.();

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
// Test Email
// ----------------------------
const testEmailBtn = $("sendTestEmailBtn");
const testEmailTo = $("testEmailTo");
const testEmailMsg = $("testEmailMsg");

testEmailBtn?.addEventListener("click", async (e) => {
  e.preventDefault?.();

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
  } catch (e2) {
    console.error(e2);
    if (testEmailMsg) testEmailMsg.textContent = "Failed to send (see console).";
  }
});

// ----------------------------
// initial loads
// ----------------------------
loadMembers();
loadRequests();
await loadAdminContextAndWireOwnerTools();
