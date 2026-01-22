// app/static/js/login.js
// Login page logic (club loader + member login). Not used by dashboard pages.

const $ = (id) => document.getElementById(id);

function setMessage(msg, isError = true) {
  const el = $("message");
  if (!el) return;
  el.style.color = isError ? "#b00020" : "#0a7a0a";
  el.textContent = msg || "";
}

function getQueryParam(name) {
  const url = new URL(window.location.href);
  return url.searchParams.get(name);
}

function setQueryParam(name, value) {
  const url = new URL(window.location.href);
  if (!value) url.searchParams.delete(name);
  else url.searchParams.set(name, value);
  window.history.replaceState({}, "", url.toString());
}

async function fetchClub(slug) {
  const s = (slug || "").trim();
  if (!s) throw new Error("Enter a Club Code.");
  const res = await fetch(`/public/club/${encodeURIComponent(s)}`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || "Club not found.");
  return data.club;
}

function applyClubBranding(club) {
  const name = club?.name || "Sign In";
  const slug = club?.slug || "";

  const heading = $("clubNameHeading");
  const title = $("pageTitle");
  const hint = $("clubHint");

  if (heading) heading.textContent = name;
  if (title) title.textContent = `${name} — Sign In`;
  if (hint) hint.textContent = `Club Code: ${slug}`;

  // store for login + other pages
  localStorage.setItem("club_slug", slug);
}

async function loadClubFromInput() {
  try {
    setMessage("");
    const slug = $("clubSlug")?.value || "";
    const club = await fetchClub(slug);
    applyClubBranding(club);
    setQueryParam("club", club.slug);
    setMessage("Club loaded. Now sign in.", false);
  } catch (e) {
    setMessage(e.message || "Could not load club.");
  }
}

async function loadClubFromUrlOrStorage() {
  const urlSlug = getQueryParam("club");
  const savedSlug = localStorage.getItem("club_slug");
  const slug = (urlSlug || savedSlug || "").trim();

  if (!slug) return;

  if ($("clubSlug")) $("clubSlug").value = slug;

  try {
    const club = await fetchClub(slug);
    applyClubBranding(club);
    setQueryParam("club", club.slug);
  } catch (e) {
    setMessage(e.message || "Could not load club.");
  }
}

async function login(email, password, clubSlug) {
  const payload = new URLSearchParams();
  payload.append("username", email);
  payload.append("password", password);
  payload.append("club_slug", clubSlug);

  const res = await fetch("/member/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: payload.toString(),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || "Login failed.");
  return data;
}

function saveTokenFromLoginResponse(data) {
  const token = data?.access_token || data?.token || data?.jwt;
  if (!token) return null;
  localStorage.setItem("token", token); // ✅ shared auth.js will accept this key
  return token;
}

// Wire up UI
$("loadClubBtn")?.addEventListener("click", loadClubFromInput);

$("loginForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  setMessage("");

  const clubSlug = (localStorage.getItem("club_slug") || $("clubSlug")?.value || "").trim();
  const email = ($("email")?.value || "").trim();
  const password = ($("password")?.value || "").trim();

  if (!clubSlug) return setMessage("Enter and load your Club Code first.");
  if (!email || !password) return setMessage("Enter email and password.");

  try {
    const data = await login(email, password, clubSlug);
    const token = saveTokenFromLoginResponse(data);
    if (!token) throw new Error("Login succeeded but no token returned.");
    setMessage("Signed in!", false);
    window.location.href = "/static/dashboard.html";
  } catch (err) {
    setMessage(err.message || "Login failed.");
  }
});

loadClubFromUrlOrStorage();
