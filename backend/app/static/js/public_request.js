// app/static/js/public_request.js
import { getToken } from "./auth.js";

// ✅ Auto-redirect logged-in members away from public page
if (getToken()) {
  window.location.replace("/static/dashboard.html");
}

const $ = (id) => document.getElementById(id);

const membersBtn = $("membersBtn");
const submitBtn = $("submitBtn");
const resetBtn = $("resetBtn");
const msg = $("msg");

// Form fields
const categoryEl = $("category");
const nameEl = $("name");
const phoneEl = $("phone");
const emailEl = $("email");
const addressEl = $("address");
const descEl = $("desc");

// Safety: if page is missing expected elements, fail silently (prevents console explosions)
if (!membersBtn || !submitBtn || !resetBtn || !msg ||
    !categoryEl || !nameEl || !phoneEl || !emailEl || !addressEl || !descEl) {
  console.warn("Public Request page missing expected elements.");
} else {
  membersBtn.addEventListener("click", () => {
    window.location.href = "/static/index.html";
  });

  function setMsg(text) {
    msg.textContent = text || "";
  }

  function resetForm() {
    categoryEl.value = "";
    nameEl.value = "";
    phoneEl.value = "";
    emailEl.value = "";
    addressEl.value = "";
    descEl.value = "";
    setMsg("");
  }

  resetBtn.addEventListener("click", resetForm);

  // Allow Enter to submit (except inside textarea)
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target !== descEl) {
      e.preventDefault();
      submitBtn.click();
    }
  });

  submitBtn.addEventListener("click", async () => {
    const payload = {
      category: categoryEl.value,
      requester_name: nameEl.value.trim(),
      requester_phone: phoneEl.value.trim(),
      requester_email: emailEl.value.trim() || null,
      requester_address: addressEl.value.trim(),
      description: descEl.value.trim(),
    };

    if (
      !payload.category ||
      !payload.requester_name ||
      !payload.requester_phone ||
      !payload.requester_address ||
      !payload.description
    ) {
      setMsg("Please fill out all required fields (email is optional).");
      return;
    }

    submitBtn.disabled = true;
    resetBtn.disabled = true;
    setMsg("Submitting…");

    try {
      const res = await fetch("/public/requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        // Try to surface backend detail if present
        let detail = "";
        try {
          const errJson = await res.json();
          detail = errJson?.detail ? ` (${errJson.detail})` : "";
        } catch {
          // ignore parse errors
        }
        setMsg(`Submission failed. Please try again.${detail}`);
        return;
      }

      setMsg("✅ Request submitted! A Lions member will review it soon.");
      resetForm();
    } catch (err) {
      console.error(err);
      setMsg("Submission failed (network/server). Please try again.");
    } finally {
      submitBtn.disabled = false;
      resetBtn.disabled = false;
    }
  });
}
