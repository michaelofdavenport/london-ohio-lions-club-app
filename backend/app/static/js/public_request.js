// app/static/js/public_request.js
// SaaS-ready Public Request submission (multi-club)
// - reads club slug from ?club=... OR localStorage (fallback to default)
// - optionally loads club branding from /public/{club}/info
// - submits to /public/{club}/request

const $ = (id) => document.getElementById(id);

const CLUB_STORAGE_KEY = "lions_club_slug";
const DEFAULT_CLUB_SLUG = "london-ohio"; // ✅ keeps single-club installs working

function setMsg(text, isError = false) {
  const el = $("msg");
  if (!el) return;
  el.textContent = text || "";
  el.style.color = isError ? "#ff8a8a" : "#b9c7ef";
}

function getClubSlug() {
  const params = new URLSearchParams(window.location.search);
  const fromQS = (params.get("club") || "").trim();
  if (fromQS) {
    localStorage.setItem(CLUB_STORAGE_KEY, fromQS);
    return fromQS;
  }
  const fromLS = (localStorage.getItem(CLUB_STORAGE_KEY) || "").trim();
  return fromLS || DEFAULT_CLUB_SLUG;
}

function withClub(url, clubSlug) {
  const club = (clubSlug || "").trim() || getClubSlug();
  if (!club) return url;
  const join = url.includes("?") ? "&" : "?";
  return url.includes("club=") ? url : `${url}${join}club=${encodeURIComponent(club)}`;
}

async function loadBranding(clubSlug) {
  // Safe: if endpoint doesn't exist yet, it just fails quietly.
  try {
    const res = await fetch(`/public/${encodeURIComponent(clubSlug)}/info`, {
      headers: { "Accept": "application/json" },
    });
    if (!res.ok) return;

    const data = await res.json();

    // Expected shape:
    // { name: "London Ohio Lions Club", logo_url: "/static/images/...", subtitle: "Public Request Form" }
    if (data?.name && $("clubName")) $("clubName").textContent = data.name;
    if (data?.logo_url && $("clubLogo")) $("clubLogo").src = data.logo_url;
    if (data?.subtitle && $("subTitle")) $("subTitle").textContent = data.subtitle;
  } catch {
    // ignore branding failures
  }
}

function wireMembersButton(clubSlug) {
  const btn = $("membersBtn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    // ✅ club-safe redirect to member login
    window.location.href = withClub("/static/index.html", clubSlug);
  });
}

function wireReset() {
  $("resetBtn")?.addEventListener("click", () => {
    $("category").value = "";
    $("name").value = "";
    $("phone").value = "";
    $("email").value = "";
    $("address").value = "";
    $("desc").value = "";
    setMsg("");
  });
}

function validate() {
  const category = $("category")?.value?.trim();
  const name = $("name")?.value?.trim();
  const phone = $("phone")?.value?.trim();
  const address = $("address")?.value?.trim();
  const desc = $("desc")?.value?.trim();

  if (!category) return "Please select a category.";
  if (!name) return "Please enter your name.";
  if (!phone) return "Please enter a phone number.";
  if (!address) return "Please enter an address.";
  if (!desc) return "Please describe your request.";

  return "";
}

async function submitRequest(clubSlug) {
  const err = validate();
  if (err) {
    setMsg(err, true);
    return;
  }

  const payload = {
    request_type: $("category").value.trim(),
    name: $("name").value.trim(),
    phone: $("phone").value.trim(),
    email: ($("email").value || "").trim(),
    address: $("address").value.trim(),
    details: $("desc").value.trim(),
  };

  $("submitBtn").disabled = true;
  setMsg("Submitting request…");

  try {
    const res = await fetch(`/public/${encodeURIComponent(clubSlug)}/request`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      let message = "Submit failed.";
      try {
        const data = await res.json();
        if (data?.detail) message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      } catch {
        const text = await res.text();
        if (text) message = text;
      }
      setMsg(message, true);
      return;
    }

    setMsg("✅ Request submitted. Thank you!");
    $("resetBtn")?.click();
  } catch (e) {
    setMsg("Network error. Please try again.", true);
  } finally {
    $("submitBtn").disabled = false;
  }
}

function init() {
  const clubSlug = getClubSlug();

  // ✅ wire MEMBERS button with club preservation
  wireMembersButton(clubSlug);

  wireReset();

  // Optional branding (won't break anything if endpoint not ready yet)
  loadBranding(clubSlug);

  $("submitBtn")?.addEventListener("click", () => submitRequest(clubSlug));
}

init();
