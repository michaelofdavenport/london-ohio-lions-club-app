// app/static/js/admin.js
import { requireAuth, apiFetch, clearToken, withClub } from "./auth.js";

requireAuth();

const $ = (id) => document.getElementById(id);

function showMsg(text, ok=false) {
  const el = $("statusMsg");
  if (!el) return;
  el.style.display = "block";
  el.classList.toggle("ok", ok);
  el.textContent = text;
}
function clearMsg() {
  const el = $("statusMsg");
  if (!el) return;
  el.style.display = "none";
  el.classList.remove("ok");
  el.textContent = "";
}

function escapeHtml(s) {
  return (s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadMe() {
  const res = await apiFetch("/admin/me");
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || "Failed to load admin profile.");
  return data;
}

async function loadEmailStatus() {
  const res = await apiFetch("/admin/email-status");
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || "Failed to load email status.");
  return data;
}

async function loadMembers() {
  const res = await apiFetch("/admin/members");
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || "Failed to load members.");
  return data;
}

async function inviteMember(payload) {
  const res = await apiFetch("/admin/members/invite", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || "Invite failed.");
  return data;
}

async function setActive(memberId, isActive) {
  const res = await apiFetch(`/admin/members/${memberId}`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || "Update failed.");
  return data;
}

function renderMembers(members=[]) {
  const wrap = $("membersWrap");
  if (!wrap) return;

  if (!members.length) {
    wrap.innerHTML = `<div style="color:#b9c7ef;font-weight:800;">No members found.</div>`;
    return;
  }

  const rows = members.map(m => {
    const status = m.is_active ? "Active" : "Disabled";
    const role = m.is_admin ? "Admin" : "Member";
    return `
      <tr>
        <td>${escapeHtml(m.name || "")}</td>
        <td>${escapeHtml(m.email || "")}</td>
        <td>${role}</td>
        <td>${status}</td>
        <td style="text-align:right;">
          <button class="secondary" data-toggle="${m.id}" data-active="${m.is_active ? "1" : "0"}">
            ${m.is_active ? "Disable" : "Enable"}
          </button>
        </td>
      </tr>
    `;
  }).join("");

  wrap.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Name</th><th>Email</th><th>Role</th><th>Status</th><th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  wrap.querySelectorAll("button[data-toggle]").forEach(btn => {
    btn.addEventListener("click", async () => {
      try {
        clearMsg();
        const id = Number(btn.getAttribute("data-toggle"));
        const active = btn.getAttribute("data-active") === "1";
        await setActive(id, !active);
        showMsg("✅ Member updated.", true);
        await bootMembers();
      } catch (e) {
        showMsg(`❌ ${e.message || "Update failed."}`);
      }
    });
  });
}

async function bootMembers() {
  const data = await loadMembers();
  renderMembers(data.members || []);
}

async function boot() {
  try {
    clearMsg();

    // Nav
    $("goDashboard")?.addEventListener("click", () => {
      window.location.href = withClub("/static/dashboard.html");
    });
    $("logoutBtn")?.addEventListener("click", () => {
      clearToken();
      window.location.href = withClub("/static/index.html");
    });

    // Invite
    $("inviteBtn")?.addEventListener("click", async () => {
      try {
        clearMsg();
        const name = ($("inviteName")?.value || "").trim();
        const email = ($("inviteEmail")?.value || "").trim();
        const is_admin = ($("inviteAdmin")?.value || "false") === "true";
        if (!email) return showMsg("Email is required.");

        await inviteMember({ name, email, is_admin });
        showMsg("✅ Invite created. Email will send if SMTP is configured.", true);

        $("inviteName").value = "";
        $("inviteEmail").value = "";
        $("inviteAdmin").value = "false";

        await bootMembers();
      } catch (e) {
        showMsg(`❌ ${e.message || "Invite failed."}`);
      }
    });

    // Load profile + club pill
    const me = await loadMe();
    const club = me.club;
    $("clubPill").textContent = club ? `${club.name} (${club.slug})` : "No club";

    // Email status
    const es = await loadEmailStatus();
    $("emailStatus").textContent = es.configured ? "Configured ✅" : "Not configured ⚠️";

    // Members
    await bootMembers();

  } catch (e) {
    showMsg(`❌ ${e.message || "Failed to load admin tools."}`);
    console.error(e);
  }
}

boot();
