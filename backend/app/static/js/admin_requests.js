// app/static/js/admin_requests.js
import { apiFetch, clearToken } from "./auth.js";
import { requireAdminOrRedirect } from "./admin_guard.js";

const $ = (id) => document.getElementById(id);

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
  return `<span class="pill other">${escapeHtml(s || "—")}</span>`;
}

function fmtDate(d) {
  if (!d) return "—";
  const s = String(d);
  return s.length >= 19 ? s.slice(0, 19).replace("T", " ") : s;
}

let all = [];
let selected = null;

function openDrawer(req) {
  selected = req;

  const drawer = $("drawer");
  if (!drawer) return;

  drawer.classList.add("open");
  $("drawerMsg").textContent = "";

  $("drawerTitle").textContent = `Request #${req.id}`;
  $("d_id").textContent = req.id;
  $("d_status").textContent = req.status || "—";
  $("d_submitted").textContent = fmtDate(req.created_at);

  const submitter = `${req.submitted_by_name || "—"}${
    req.submitted_by_email ? ` <${req.submitted_by_email}>` : ""
  }`;
  $("d_submitter").textContent = submitter.trim();

  $("d_assigned").textContent =
    req.assigned_to_name || (req.assigned_to_id ? `Member #${req.assigned_to_id}` : "—");

  $("d_assign").value = req.assigned_to_id ?? "";
  $("d_note").value = "";
}

function closeDrawer() {
  $("drawer")?.classList.remove("open");
  selected = null;
}

$("closeDrawerBtn")?.addEventListener("click", closeDrawer);

// NAV
$("logoutBtn")?.addEventListener("click", () => {
  clearToken();
  window.location.href = "/static/public_request.html";
});
$("dashBtn")?.addEventListener("click", () => (window.location.href = "/static/dashboard.html"));
$("toolsBtn")?.addEventListener("click", () => (window.location.href = "/admin/tools")); // ✅ correct protected route

// Filters
$("refreshBtn")?.addEventListener("click", load);
$("q")?.addEventListener("input", renderFiltered);
$("status")?.addEventListener("change", load);
$("assigned")?.addEventListener("change", load);

async function load() {
  $("msg").textContent = "Loading…";

  const status = $("status")?.value || "";
  const assigned = $("assigned")?.value || "";
  const q = $("q")?.value.trim() || "";

  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (assigned) params.set("assigned", assigned);
  if (q) params.set("q", q);
  params.set("limit", "200");

  try {
    const resp = await apiFetch(`/admin/requests?${params.toString()}`);
    if (resp.status === 403) {
      $("msg").textContent = "You are logged in, but not an admin.";
      all = [];
      render([]);
      return;
    }
    if (!resp.ok) throw new Error("Failed to load");

    all = await resp.json();
    $("msg").textContent = "";
    renderFiltered();
  } catch (e) {
    console.error(e);
    $("msg").textContent = "Failed to load requests.";
    all = [];
    render([]);
  }
}

function renderFiltered() {
  const q = ($("q")?.value || "").trim().toLowerCase();
  let rows = all.slice();

  if (q) {
    rows = rows.filter((r) => {
      const s = `${r.title || ""} ${r.description || ""} ${r.submitted_by_email || ""}`.toLowerCase();
      return s.includes(q);
    });
  }
  render(rows);
}

function render(rows) {
  const tbody = $("rows");
  if (!tbody) return;

  tbody.innerHTML = "";
  $("countHint").textContent = `${rows.length} request${rows.length === 1 ? "" : "s"}`;

  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.id}</td>
      <td>${pill(r.status)}</td>
      <td class="row-title">${escapeHtml(r.title || "—")}</td>
      <td class="desc">${escapeHtml((r.description || "").slice(0, 180) || "—")}</td>
      <td>${escapeHtml(fmtDate(r.created_at))}</td>
      <td>${escapeHtml(r.assigned_to_name || (r.assigned_to_id ? `#${r.assigned_to_id}` : "—"))}</td>
      <td>
        <div class="actions">
          <button class="btn btn-secondary btn-small" data-act="open" data-id="${r.id}">Open</button>
          <button class="btn btn-primary btn-small" data-act="approve" data-id="${r.id}">Approve</button>
          <button class="btn btn-secondary btn-small" data-act="deny" data-id="${r.id}">Deny</button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  }

  tbody.querySelectorAll("button[data-act]").forEach((b) => b.addEventListener("click", onRowAction));
}

function getById(id) {
  return all.find((x) => x.id === id);
}

async function onRowAction(e) {
  const act = e.currentTarget.dataset.act;
  const id = Number(e.currentTarget.dataset.id);
  const r = getById(id);
  if (!r) return;

  if (act === "open") return openDrawer(r);
  if (act === "approve") return decide(id, "APPROVED", null); // ✅ no drawer note from table click
  if (act === "deny") return decide(id, "DENIED", null);
}

async function decide(id, status, decision_note) {
  const ok = confirm(`${status === "APPROVED" ? "Approve" : "Deny"} request #${id}?`);
  if (!ok) return;

  try {
    const resp = await apiFetch(`/admin/requests/${id}/decision`, {
      method: "PATCH",
      body: JSON.stringify({ status, decision_note }),
    });
    if (resp.status === 403) return alert("Forbidden (admin only).");
    if (!resp.ok) throw new Error("Decision failed");
    await load();
  } catch (e) {
    console.error(e);
    alert("Update failed.");
  }
}

// Drawer actions
$("approveBtn")?.addEventListener("click", async () => {
  if (!selected) return;
  const note = $("d_note")?.value?.trim() || null;
  await decide(selected.id, "APPROVED", note);
  closeDrawer();
});

$("denyBtn")?.addEventListener("click", async () => {
  if (!selected) return;
  const note = $("d_note")?.value?.trim() || null;
  await decide(selected.id, "DENIED", note);
  closeDrawer();
});

$("assignBtn")?.addEventListener("click", async () => {
  if (!selected) return;
  $("drawerMsg").textContent = "";

  const raw = ($("d_assign")?.value || "").trim();
  const assigned_to_id = raw ? Number(raw) : null;
  if (raw && !Number.isFinite(assigned_to_id)) {
    $("drawerMsg").textContent = "Assignment must be a number (member id) or blank.";
    return;
  }

  try {
    const resp = await apiFetch(`/admin/requests/${selected.id}/assign`, {
      method: "PATCH",
      body: JSON.stringify({ assigned_to_id }),
    });
    if (resp.status === 403) return ($("drawerMsg").textContent = "Forbidden (admin only).");
    if (!resp.ok) throw new Error("Assign failed");

    $("drawerMsg").textContent = "✅ Assignment saved.";
    await load();
  } catch (e) {
    console.error(e);
    $("drawerMsg").textContent = "Assignment failed.";
  }
});

$("noteBtn")?.addEventListener("click", async () => {
  if (!selected) return;
  $("drawerMsg").textContent = "";

  const note = $("d_note")?.value?.trim() || "";
  if (!note) {
    $("drawerMsg").textContent = "Type a note first.";
    return;
  }

  try {
    const resp = await apiFetch(`/admin/requests/${selected.id}/note`, {
      method: "POST",
      body: JSON.stringify({ note }),
    });
    if (resp.status === 403) return ($("drawerMsg").textContent = "Forbidden (admin only).");
    if (!resp.ok) throw new Error("Note failed");

    $("drawerMsg").textContent = "✅ Note saved.";
    $("d_note").value = "";
  } catch (e) {
    console.error(e);
    $("drawerMsg").textContent = "Note failed.";
  }
});

// INIT
(async function init() {
  const ok = await requireAdminOrRedirect();
  if (!ok) return;
  await load();
})();
