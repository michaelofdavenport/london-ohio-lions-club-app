// app/static/js/roster.js
import { requireAuth, apiFetch, clearToken } from "./auth.js";

// 🔒 Enforce login
requireAuth();

const $ = (id) => document.getElementById(id);

const rowsEl = $("rows");
const emptyEl = $("empty");
const hintEl = $("hint");
const qEl = $("q");

const modalBackdrop = $("modalBackdrop");
const modalClose = $("modalClose");
const modalCancel = $("modalCancel");
const modalSave = $("modalSave");
const modalMsg = $("modalMsg");

// -----------------------------------------------------
// PHONE FORMATTER (Roster "Add Member" modal)
// Forces: (xxx)xxx-xxxx, no matter how user types/pastes
// -----------------------------------------------------
function formatPhone(value) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 10);
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

function wireRosterPhoneInput() {
  const phoneInput = $("m_phone");
  if (!phoneInput) return;

  if (phoneInput.dataset.phoneWired === "1") return;
  phoneInput.dataset.phoneWired = "1";

  phoneInput.addEventListener("input", () => applyFormatKeepingCaret(phoneInput));
  phoneInput.addEventListener("blur", () => {
    phoneInput.value = formatPhone(phoneInput.value);
  });
}

// -----------------------------------------------------
// NAV
// -----------------------------------------------------
$("dashBtn")?.addEventListener("click", () => {
  window.location.href = "/static/dashboard.html";
});

$("logoutBtn")?.addEventListener("click", () => {
  clearToken();
  window.location.href = "/static/public_request.html";
});

// Helpers
function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fmtDate(d) {
  if (!d) return "—";
  const dt = new Date(d);
  if (Number.isNaN(dt.getTime())) return "—";
  return dt.toLocaleDateString();
}

function normalizeMember(m) {
  return {
    full_name: m.full_name ?? "—",
    address: m.address ?? "—",
    email: m.email ?? "—",
    phone: m.phone ?? "—",
    member_since: m.member_since ?? null,
    birthday: m.birthday ?? null,
  };
}

function renderRows(list) {
  rowsEl.innerHTML = "";
  emptyEl.style.display = list.length ? "none" : "block";

  for (const raw of list) {
    const m = normalizeMember(raw);

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${esc(m.full_name)}</strong></td>
      <td>${esc(m.address)}</td>
      <td>${esc(m.email)}</td>
      <td>${esc(m.phone)}</td>
      <td>${esc(fmtDate(m.member_since))}</td>
      <td>${esc(fmtDate(m.birthday))}</td>
    `;
    rowsEl.appendChild(tr);
  }
}

function applySearch(list, q) {
  const needle = q.trim().toLowerCase();
  if (!needle) return list;

  return list.filter((m) => {
    const mm = normalizeMember(m);
    return (
      String(mm.full_name).toLowerCase().includes(needle) ||
      String(mm.email).toLowerCase().includes(needle) ||
      String(mm.phone).toLowerCase().includes(needle) ||
      String(mm.address).toLowerCase().includes(needle)
    );
  });
}

// Load roster
let rosterCache = [];

async function loadRoster() {
  hintEl.textContent = "Loading…";
  try {
    const resp = await apiFetch("/member/roster");
    const data = await resp.json();
    rosterCache = Array.isArray(data) ? data : [];
    const filtered = applySearch(rosterCache, qEl.value);
    renderRows(filtered);
    hintEl.textContent = `${filtered.length} member(s) shown`;
  } catch (err) {
    console.error("Roster load failed:", err);
    renderRows([]);
    hintEl.textContent = "Failed to load roster (check server / login).";
  }
}

$("refreshBtn")?.addEventListener("click", loadRoster);

qEl?.addEventListener("input", () => {
  const filtered = applySearch(rosterCache, qEl.value);
  renderRows(filtered);
  hintEl.textContent = `${filtered.length} member(s) shown`;
});

// Modal open/close
function openModal() {
  modalMsg.textContent = "";
  $("m_full_name").value = "";
  $("m_email").value = "";
  $("m_phone").value = "";
  $("m_address").value = "";
  $("m_member_since").value = "";
  $("m_birthday").value = "";
  $("m_password").value = "";
  $("m_is_admin").value = "false";

  modalBackdrop.style.display = "flex";

  // ✅ Wire formatting when modal opens (guaranteed the input exists)
  wireRosterPhoneInput();
}

function closeModal() {
  modalBackdrop.style.display = "none";
}

$("addBtn")?.addEventListener("click", openModal);
modalClose?.addEventListener("click", closeModal);
modalCancel?.addEventListener("click", closeModal);
modalBackdrop?.addEventListener("click", (e) => {
  if (e.target === modalBackdrop) closeModal();
});

// ✅ Save new member (now includes member_since + birthday)
modalSave?.addEventListener("click", async () => {
  modalMsg.textContent = "";

  // ✅ Normalize phone RIGHT before saving (so DB always receives formatted)
  const phoneEl = $("m_phone");
  if (phoneEl) phoneEl.value = formatPhone(phoneEl.value);

  const memberSinceVal = $("m_member_since").value || null; // "YYYY-MM-DD"
  const birthdayVal = $("m_birthday").value || null; // "YYYY-MM-DD"

  const payload = {
    email: $("m_email").value.trim(),
    password: $("m_password").value,
    full_name: $("m_full_name").value.trim() || null,
    phone: $("m_phone").value.trim() || null,
    address: $("m_address").value.trim() || null,
    is_admin: $("m_is_admin").value === "true",
    member_since: memberSinceVal,
    birthday: birthdayVal,
  };

  if (!payload.email || !payload.password) {
    modalMsg.textContent = "Email + Temporary Password are required.";
    return;
  }

  modalSave.disabled = true;
  modalMsg.textContent = "Saving…";

  try {
    const resp = await apiFetch("/admin/members", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const txt = await resp.text().catch(() => "");
      if (resp.status === 403) {
        modalMsg.textContent = "Not allowed. Only admins can add members.";
      } else if (resp.status === 400) {
        modalMsg.textContent = "Email already exists (or bad input).";
      } else if (resp.status === 422) {
        modalMsg.textContent = "Server rejected fields (schema mismatch). Apply backend update.";
      } else {
        modalMsg.textContent = `Save failed (${resp.status}). ${txt ? "Check server logs." : ""}`;
      }
      return;
    }

    modalMsg.textContent = "✅ Member created.";
    closeModal();
    await loadRoster();
  } catch (err) {
    console.error(err);
    modalMsg.textContent = "Save failed (network/server).";
  } finally {
    modalSave.disabled = false;
  }
});

// Initial load
loadRoster();
