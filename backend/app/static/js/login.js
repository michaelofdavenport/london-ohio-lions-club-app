// app/static/js/login.js
import { getToken, setToken } from "./auth.js";

// If already logged in, skip login page.
if (getToken()) {
  window.location.href = "/static/dashboard.html";
}

const emailEl = document.getElementById("email");
const passEl = document.getElementById("password");
const btn = document.getElementById("loginBtn");

btn.addEventListener("click", login);
passEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") login();
});

async function login() {
  const email = (emailEl.value || "").trim();
  const password = passEl.value || "";

  if (!email || !password) {
    alert("Enter email + password.");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Logging in…";

  try {
    const form = new FormData();
    form.append("username", email);
    form.append("password", password);

    const res = await fetch("/member/login", { method: "POST", body: form });

    if (!res.ok) {
      alert("Invalid login credentials");
      return;
    }

    const data = await res.json();

    if (!data?.access_token) {
      alert("Login succeeded but token missing. Backend must return { access_token }.");
      return;
    }

    setToken(data.access_token);
    window.location.href = "/static/dashboard.html";
  } catch (err) {
    console.error(err);
    alert("Login failed (network or server).");
  } finally {
    btn.disabled = false;
    btn.textContent = "Login";
  }
}
