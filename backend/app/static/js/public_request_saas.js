// app/static/js/public_request_saas.js
// Unified Public Landing Page logic (club search + submit request to correct club)
// ✅ Auto-maps payload to your backend schema by reading /openapi.json
// ✅ Robust: finds the POST /public/*/request schema even if path param name differs
// ✅ Never "silent fails": shows backend error text in UI + logs to console

const $ = (id) => document.getElementById(id);

const clubSearch = $("clubSearch");
const clubResults = $("clubResults");
const selectedClubPill = $("selectedClubPill");
const selectedClubName = $("selectedClubName");
const selectedClubSlug = $("selectedClubSlug");

const form = $("publicRequestForm");
const statusMsg = $("statusMsg");

const fullName = $("fullName");
const email = $("email");
const phone = $("phone");
const category = $("category");
const address = $("address"); // ✅ NEW
const message = $("message");

const resetBtn = $("resetBtn");
const membersBtn = $("membersBtn");

let clubs = [];
let selectedClub = null;

// OpenAPI cache
let openapi = null;
let saasRequestSchema = null; // resolved JSON-schema for POST /public/{X}/request body
let detectedRequestPath = null;

// -----------------------------
// Phone formatting (NEW)
// -----------------------------
function digitsOnly(v) {
  return (v || "").toString().replace(/\D/g, "");
}

// Formats 10 digits -> "(xxx)xxx-xxxx"
// If fewer than 10, it formats progressively while typing.
function formatPhoneUS(raw) {
  const d = digitsOnly(raw).slice(0, 10);
  if (!d) return "";

  const a = d.slice(0, 3);
  const b = d.slice(3, 6);
  const c = d.slice(6, 10);

  if (d.length <= 3) return `(${a}`;
  if (d.length <= 6) return `(${a})${b}`;
  return `(${a})${b}-${c}`;
}

function getNormalizedPhone() {
  const d = digitsOnly(phone?.value || "").slice(0, 10);
  if (!d) return null;
  if (d.length < 10) return null; // optional field: if they didn't finish it, treat as blank
  return formatPhoneUS(d);
}

function wirePhoneFormatting() {
  if (!phone) return;

  // format as they type/paste
  phone.addEventListener("input", () => {
    const before = phone.value;
    const formatted = formatPhoneUS(before);
    phone.value = formatted;
  });

  // enforce final format on blur
  phone.addEventListener("blur", () => {
    const normalized = getNormalizedPhone();
    phone.value = normalized || "";
  });
}

// -----------------------------
// UI helpers
// -----------------------------
function showMsg(text, ok = false) {
  if (!statusMsg) return;
  statusMsg.style.display = "block";
  statusMsg.classList.toggle("ok", ok);
  statusMsg.textContent = text;
}

function clearMsg() {
  if (!statusMsg) return;
  statusMsg.style.display = "none";
  statusMsg.classList.remove("ok");
  statusMsg.textContent = "";
}

function normalize(str) {
  return (str || "").toString().trim().toLowerCase();
}

function escapeHtml(s) {
  return (s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderResults(list) {
  if (!clubResults) return;
  clubResults.innerHTML = "";

  if (!list.length) {
    clubResults.style.display = "none";
    return;
  }

  clubResults.style.display = "block";

  for (const c of list) {
    const div = document.createElement("div");
    div.className = "resultItem";
    div.innerHTML = `
      <div><b>${escapeHtml(c.name)}</b></div>
      <small>code: ${escapeHtml(c.slug)}</small>
    `;
    div.addEventListener("click", () => selectClub(c));
    clubResults.appendChild(div);
  }
}

function selectClub(c) {
  selectedClub = c;

  if (selectedClubPill) selectedClubPill.style.display = "inline-flex";
  if (selectedClubName) selectedClubName.textContent = c.name;
  if (selectedClubSlug) selectedClubSlug.textContent = c.slug;

  if (clubSearch) clubSearch.value = `${c.name} (${c.slug})`;
  if (clubResults) clubResults.style.display = "none";

  clearMsg();
}

function clearSelectedClub() {
  selectedClub = null;
  if (selectedClubPill) selectedClubPill.style.display = "none";
  if (selectedClubName) selectedClubName.textContent = "—";
  if (selectedClubSlug) selectedClubSlug.textContent = "—";
}

// -----------------------------
// Query param helpers
// -----------------------------
function getQueryParam(name) {
  try {
    const url = new URL(window.location.href);
    return url.searchParams.get(name);
  } catch {
    return null;
  }
}

function preselectClubFromQuery() {
  const slug = getQueryParam("club");
  if (!slug) return;

  const found = clubs.find((c) => normalize(c.slug) === normalize(slug));
  if (found) selectClub(found);
}

// -----------------------------
// Error parsing
// -----------------------------
function extractFastAPIErrorText(errJson, fallback = "Request failed.") {
  if (!errJson) return fallback;
  if (typeof errJson === "string") return errJson;

  // FastAPI 422 typically: { detail: [ {loc, msg, type}, ... ] }
  if (Array.isArray(errJson.detail)) {
    const lines = errJson.detail.map((d) => {
      const loc = Array.isArray(d.loc) ? d.loc.join(".") : "";
      const msg = d.msg || "Invalid value";
      return loc ? `${loc}: ${msg}` : msg;
    });
    return lines.join(" | ");
  }

  if (typeof errJson.detail === "string") return errJson.detail;

  try {
    return JSON.stringify(errJson);
  } catch {
    return fallback;
  }
}

// -----------------------------
// Load clubs (for dropdown/search)
// -----------------------------
async function loadClubs() {
  try {
    const res = await fetch("/public/clubs", {
      headers: { Accept: "application/json" },
    });

    if (!res.ok) {
      showMsg(`Could not load clubs (HTTP ${res.status}).`);
      return;
    }

    const data = await res.json();
    clubs = Array.isArray(data.clubs) ? data.clubs : [];

    // If ?club=slug in URL, preselect it
    preselectClubFromQuery();

    // Optional: if only one club exists, auto-select it
    if (!selectedClub && clubs.length === 1) selectClub(clubs[0]);
  } catch (e) {
    console.error("[PublicRequest] loadClubs error:", e);
    showMsg("Could not load clubs (network error).");
  }
}

// -----------------------------
// OpenAPI schema auto-detect for SaaS request endpoint
// -----------------------------
async function loadOpenApi() {
  try {
    const res = await fetch("/openapi.json", { headers: { Accept: "application/json" } });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function resolveRef(obj, ref) {
  // ref format: "#/components/schemas/SomeSchema"
  if (!ref || typeof ref !== "string" || !ref.startsWith("#/")) return null;
  const path = ref.slice(2).split("/");
  let cur = obj;
  for (const part of path) {
    if (!cur || typeof cur !== "object") return null;
    cur = cur[part];
  }
  return cur || null;
}

function findSaasRequestPostOperation(openapiDoc) {
  // Try exact known variants first
  const candidates = [
    "/public/{club_slug}/request",
    "/public/{slug}/request",
    "/public/{club}/request",
  ];

  for (const p of candidates) {
    const postOp = openapiDoc?.paths?.[p]?.post;
    if (postOp) return { path: p, postOp };
  }

  // Fallback: find any POST path that starts with /public/ and ends with /request
  const paths = openapiDoc?.paths || {};
  for (const [pathKey, pathItem] of Object.entries(paths)) {
    if (!pathKey.startsWith("/public/")) continue;
    if (!pathKey.endsWith("/request")) continue;
    if (pathItem?.post) return { path: pathKey, postOp: pathItem.post };
  }

  return { path: null, postOp: null };
}

function getRequestBodySchemaForSaas(openapiDoc) {
  const { path, postOp } = findSaasRequestPostOperation(openapiDoc);
  detectedRequestPath = path;

  const schema =
    postOp?.requestBody?.content?.["application/json"]?.schema ||
    postOp?.requestBody?.content?.["application/json; charset=utf-8"]?.schema;

  if (!schema) return null;

  // If it’s a $ref, resolve it
  if (schema.$ref) return resolveRef(openapiDoc, schema.$ref);

  // If it’s an allOf, try the first ref
  if (Array.isArray(schema.allOf)) {
    for (const s of schema.allOf) {
      if (s?.$ref) {
        const resolved = resolveRef(openapiDoc, s.$ref);
        if (resolved) return resolved;
      }
    }
  }

  return schema;
}

function pickFirstMatch(candidateNames, schemaProps) {
  const keys = Object.keys(schemaProps || {});
  for (const want of candidateNames) {
    const found = keys.find((k) => normalize(k) === normalize(want));
    if (found) return found;
  }
  return null;
}

function buildPayloadFromSchema(schema) {
  const props = schema?.properties || {};
  const required = new Set(schema?.required || []);

  const kName = pickFirstMatch(
    ["name", "full_name", "requester_name", "contact_name"],
    props
  );

  const kEmail = pickFirstMatch(
    ["email", "requester_email", "contact_email"],
    props
  );

  const kPhone = pickFirstMatch(
    ["phone", "requester_phone", "contact_phone"],
    props
  );

  const kCategory = pickFirstMatch(
    ["category", "request_category", "type", "request_type"],
    props
  );

  const kMessage = pickFirstMatch(
    ["message", "details", "description", "request_details", "body", "notes"],
    props
  );

  // ✅ NEW: address mapping
  const kAddress = pickFirstMatch(
    ["address", "street_address", "location", "service_address"],
    props
  );

  const missingMap = [];
  if (!kName) missingMap.push("name");
  if (!kEmail) missingMap.push("email");
  if (!kCategory) missingMap.push("category/request_type");
  if (!kMessage) missingMap.push("message/details");
  if (!kAddress) missingMap.push("address");

  if (missingMap.length) {
    return {
      ok: false,
      error:
        `Frontend can't map fields to backend schema. Missing schema keys for: ${missingMap.join(", ")}. ` +
        `OpenAPI schema properties are: ${Object.keys(props).join(", ")}`,
    };
  }

  const payload = {};
  payload[kName] = fullName?.value?.trim() || "";
  payload[kEmail] = email?.value?.trim() || "";
  payload[kCategory] = category?.value?.trim() || "";
  payload[kMessage] = message?.value?.trim() || "";
  payload[kAddress] = address?.value?.trim() || "";

  // ✅ Phone: always submit normalized "(xxx)xxx-xxxx" or null
  const normalizedPhone = getNormalizedPhone();
  if (kPhone && (normalizedPhone || required.has(kPhone))) {
    payload[kPhone] = normalizedPhone || null;
  }

  return { ok: true, payload };
}

async function initSchema() {
  openapi = await loadOpenApi();
  if (!openapi) {
    showMsg("Warning: could not load /openapi.json (schema auto-mapping disabled).");
    console.warn("[PublicRequest] /openapi.json not available; using fallback payload keys.");
    return;
  }

  saasRequestSchema = getRequestBodySchemaForSaas(openapi);

  if (!saasRequestSchema) {
    showMsg("Warning: could not detect schema for POST /public/*/request.");
    console.warn("[PublicRequest] Could not resolve request schema from OpenAPI.");
    return;
  }

  const props = Object.keys(saasRequestSchema.properties || {});
  console.log("[PublicRequest] Detected request path:", detectedRequestPath);
  console.log("[PublicRequest] Request schema properties:", props);
}

// -----------------------------
// Search behavior
// -----------------------------
clubSearch?.addEventListener("input", () => {
  clearMsg();
  const q = normalize(clubSearch.value);

  if (
    selectedClub &&
    q &&
    !normalize(`${selectedClub.name} (${selectedClub.slug})`).includes(q)
  ) {
    clearSelectedClub();
  }

  if (!q) {
    renderResults([]);
    return;
  }

  const filtered = clubs
    .filter((c) => {
      const name = normalize(c.name);
      const slug = normalize(c.slug);
      return name.includes(q) || slug.includes(q);
    })
    .slice(0, 12);

  renderResults(filtered);
});

document.addEventListener("click", (e) => {
  if (!clubResults || !clubSearch) return;
  const inside = clubResults.contains(e.target) || clubSearch.contains(e.target);
  if (!inside) clubResults.style.display = "none";
});

// -----------------------------
// Buttons
// -----------------------------
resetBtn?.addEventListener("click", () => {
  form?.reset();
  if (clubSearch) clubSearch.value = "";
  renderResults([]);
  clearSelectedClub();
  clearMsg();

  // clear phone formatting state too
  if (phone) phone.value = "";

  try {
    const u = new URL(window.location.href);
    u.searchParams.delete("club");
    window.history.replaceState({}, "", u.toString());
  } catch {}
});

membersBtn?.addEventListener("click", () => {
  const slug = selectedClub?.slug || getQueryParam("club");
  if (slug) window.location.href = `/static/index.html?club=${encodeURIComponent(slug)}`;
  else window.location.href = "/static/index.html";
});

// -----------------------------
// Submit request
// -----------------------------
form?.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearMsg();

  if (!selectedClub?.slug) {
    showMsg("Please select a club first.");
    return;
  }

  const n = fullName?.value?.trim() || "";
  const em = email?.value?.trim() || "";
  const cat = category?.value?.trim() || "";
  const addr = address?.value?.trim() || "";
  const msg = message?.value?.trim() || "";

  if (!n || !em || !cat || !addr || !msg) {
    showMsg("Please fill out Name, Email, Category, Address, and Request Details.");
    return;
  }

  // ✅ normalize phone right before submit so payload is correct
  if (phone) phone.value = getNormalizedPhone() || "";

  let payload;
  if (saasRequestSchema) {
    const built = buildPayloadFromSchema(saasRequestSchema);
    if (!built.ok) {
      showMsg(built.error);
      console.error("[PublicRequest] Payload mapping error:", built.error);
      return;
    }
    payload = built.payload;
  } else {
    // fallback
    payload = {
      request_type: cat,
      name: n,
      phone: getNormalizedPhone() || null,
      email: em,
      address: addr,
      details: msg,
    };
  }

  const url = `/public/${encodeURIComponent(selectedClub.slug)}/request`;
  console.log("[PublicRequest] POST", url, payload);

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });

    const raw = await res.text();
    console.log("[PublicRequest] Response", res.status, raw);

    let data = null;
    try {
      data = raw ? JSON.parse(raw) : null;
    } catch {
      data = { detail: raw };
    }

    if (!res.ok) {
      const msgText = extractFastAPIErrorText(data, raw || `Request failed (HTTP ${res.status}).`);
      showMsg(msgText);
      console.error("[PublicRequest] ERROR", res.status, data);
      return;
    }

    showMsg("✅ Request submitted! Thank you — a club member will follow up.", true);

    form.reset();
    if (phone) phone.value = "";
    if (fullName) fullName.focus();
  } catch (err) {
    console.error("[PublicRequest] Network error:", err);
    showMsg("Request failed (network error).");
  }
});

// -----------------------------
// Boot
// -----------------------------
(async function boot() {
  wirePhoneFormatting(); // ✅ NEW
  await initSchema();
  await loadClubs();
})();
