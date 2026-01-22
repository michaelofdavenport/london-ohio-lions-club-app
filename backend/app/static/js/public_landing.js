// app/static/js/public_landing.js

const $ = (id) => document.getElementById(id);

const clubSearch = $("clubSearch");
const clubResults = $("clubResults");
const pill = $("selectedClubPill");
const pillName = $("selectedClubName");
const pillSlug = $("selectedClubSlug");

const form = $("publicRequestForm");
const statusMsg = $("statusMsg");
const resetBtn = $("resetBtn");
const membersBtn = $("membersBtn");
const submitBtn = $("submitBtn");

let clubs = [];           // [{id, slug, name}]
let selectedClub = null;  // {id, slug, name}

// ----------------------------
// Helpers
// ----------------------------
function showMsg(text, ok = false) {
  statusMsg.style.display = "block";
  statusMsg.textContent = text;
  statusMsg.classList.toggle("ok", ok);
}

function hideMsg() {
  statusMsg.style.display = "none";
  statusMsg.textContent = "";
  statusMsg.classList.remove("ok");
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;",
    '"': "&quot;", "'": "&#039;"
  }[c]));
}

function setSelectedClub(club) {
  selectedClub = club;
  pill.style.display = "inline-flex";
  pillName.textContent = club.name;
  pillSlug.textContent = club.slug;

  // also set placeholder/title for clarity
  document.title = `${club.name} – Public Request`;
  clubSearch.value = `${club.name} (${club.slug})`;
  clubResults.style.display = "none";
}

function renderResults(list) {
  if (!list.length) {
    clubResults.innerHTML = `<div class="resultItem">No matches found.</div>`;
    clubResults.style.display = "block";
    return;
  }

  clubResults.innerHTML = list.map((c) => `
    <div class="resultItem" data-slug="${escapeHtml(c.slug)}">
      <b>${escapeHtml(c.name)}</b>
      <small>code: ${escapeHtml(c.slug)}</small>
    </div>
  `).join("");

  clubResults.style.display = "block";
}

function filterClubs(query) {
  const q = (query || "").trim().toLowerCase();
  if (!q) return clubs.slice(0, 20);

  return clubs
    .filter((c) =>
      (c.name || "").toLowerCase().includes(q) ||
      (c.slug || "").toLowerCase().includes(q)
    )
    .slice(0, 20);
}

// ----------------------------
// Load clubs (auto-updating dropdown list)
// ----------------------------
async function loadClubs() {
  try {
    const res = await fetch("/public/clubs", {
      headers: { "Accept": "application/json" }
    });
    if (!res.ok) throw new Error("Failed to load clubs");

    const data = await res.json();
    clubs = Array.isArray(data?.clubs) ? data.clubs : [];

    // If there is only ONE club, auto-select it (nice for early demos)
    if (clubs.length === 1) {
      setSelectedClub(clubs[0]);
    }
  } catch (err) {
    showMsg("Could not load club list. Please refresh the page.", false);
  }
}

// ----------------------------
// Club search behaviors
// ----------------------------
clubSearch.addEventListener("input", () => {
  hideMsg();
  const list = filterClubs(clubSearch.value);
  renderResults(list);
});

clubSearch.addEventListener("focus", () => {
  const list = filterClubs(clubSearch.value);
  renderResults(list);
});

document.addEventListener("click", (e) => {
  // click outside closes results
  if (!clubResults.contains(e.target) && e.target !== clubSearch) {
    clubResults.style.display = "none";
  }
});

clubResults.addEventListener("click", (e) => {
  const item = e.target.closest(".resultItem");
  if (!item) return;
  const slug = item.getAttribute("data-slug");
  const club = clubs.find((c) => c.slug === slug);
  if (club) setSelectedClub(club);
});

// Allow selecting by typing exact slug and pressing Enter
clubSearch.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();

  const q = (clubSearch.value || "").trim();
  if (!q) return;

  const exact =
    clubs.find((c) => (c.slug || "").toLowerCase() === q.toLowerCase()) ||
    clubs.find((c) => (c.name || "").toLowerCase() === q.toLowerCase());

  if (exact) setSelectedClub(exact);
});

// ----------------------------
// Submit request
// ----------------------------
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideMsg();

  if (!selectedClub?.slug) {
    showMsg("Pick a club first (start typing in the club search box).", false);
    clubSearch.focus();
    return;
  }

  const payload = {
    full_name: $("fullName").value.trim(),
    email: $("email").value.trim(),
    phone: $("phone").value.trim(),
    category: $("category").value.trim(),
    message: $("message").value.trim(),
  };

  // basic validation
  if (!payload.full_name || !payload.email || !payload.category || !payload.message) {
    showMsg("Please fill out all required fields.", false);
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "Submitting…";

  try {
    const url = `/public/${encodeURIComponent(selectedClub.slug)}/request`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      let detail = "Request failed.";
      try {
        const data = await res.json();
        if (data?.detail) detail = data.detail;
      } catch {}
      throw new Error(detail);
    }

    showMsg("✅ Request submitted. Thank you!", true);
    form.reset();

    // keep selected club, but clear text field to show they can submit another
    clubSearch.value = `${selectedClub.name} (${selectedClub.slug})`;

  } catch (err) {
    showMsg(`❌ ${err.message || "Something went wrong."}`, false);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Submit Request";
  }
});

// ----------------------------
// Reset + Members
// ----------------------------
resetBtn.addEventListener("click", () => {
  hideMsg();
  form.reset();
  selectedClub = null;
  pill.style.display = "none";
  document.title = "Lions – Public Request";
  clubSearch.value = "";
  clubSearch.focus();
});

membersBtn.addEventListener("click", () => {
  // keep it simple for now: send to member login page
  window.location.href = "/static/index.html";
});

// Init
loadClubs();
