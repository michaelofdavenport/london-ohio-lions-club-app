import { setToken, getToken, clearToken } from "./auth.js";

function $(id) {
  return document.getElementById(id);
}

// If already logged in, bounce to dashboard
const existing = getToken();
if (existing) {
  window.location.href = "/static/dashboard.html";
}

async function login(email, password) {
  const form = new FormData();
  form.append("username", email); // OAuth2PasswordRequestForm expects username/password
  form.append("password", password);

  const res = await fetch("/member/login", {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    // Try to show a useful message if backend provides it
    let msg = "Invalid login credentials";
    try {
      const err = await res.json();
      if (err?.detail) msg = err.detail;
    } catch (_) {}
    throw new Error(msg);
  }

  const data = await res.json();
  if (!data?.access_token) {
    throw new Error("Login succeeded but no access_token returned");
  }

  setToken(data.access_token);
  window.location.href = "/static/dashboard.html";
}

const formEl = $("loginForm");
const btn = $("loginBtn");

formEl.addEventListener("submit", async (e) => {
  e.preventDefault();

  const email = $("email").value.trim();
  const password = $("password").value;

  if (!email || !password) {
    alert("Please enter email and password.");
    return;
  }

  btn.disabled = true;

  try {
    // If you had a bad token stored, kill it before attempting
    clearToken();
    await login(email, password);
  } catch (err) {
    alert(err?.message || "Login failed");
    btn.disabled = false;
  }
});
