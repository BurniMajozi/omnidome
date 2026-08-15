/**
 * OmniDome customer self-service portal (static shell).
 *
 * Theme: loaded at runtime from ../brand_guidelines/default_theme.json
 * (served by the scoped nginx mount in docker-compose.yaml).
 *
 * API: set window.PORTAL_API_BASE before this script loads (e.g. via an
 * injected config.js) to point at the gateway. No backend calls are made
 * until that is configured - cards render in the "Not connected" state.
 */
const API_BASE = window.PORTAL_API_BASE || null;
const THEME_URL = "../brand_guidelines/default_theme.json";

async function applyTheme() {
  try {
    const res = await fetch(THEME_URL);
    if (!res.ok) throw new Error(`theme fetch failed: ${res.status}`);
    const t = await res.json();
    const root = document.documentElement.style;
    if (t.primary_color) root.setProperty("--primary", t.primary_color);
    if (t.secondary_color) root.setProperty("--secondary", t.secondary_color);
    if (t.accent_color) root.setProperty("--accent", t.accent_color);
    if (t.font_family) root.setProperty("--font", t.font_family);
    if (t.hero && t.hero.bg_gradient) root.setProperty("--hero-bg", t.hero.bg_gradient);

    if (t.brand_name) {
      document.getElementById("brand-name").textContent = t.brand_name;
      document.getElementById("footer-brand").textContent =
        `${t.brand_name} © ${new Date().getFullYear()}`;
      document.title = t.brand_name;
    }
    if (t.hero && t.hero.title) {
      document.getElementById("hero-title").textContent = t.hero.title;
    }
    if (t.hero && t.hero.subtitle) {
      document.getElementById("hero-subtitle").textContent = t.hero.subtitle;
    }
    if (t.logo_url) {
      const logo = document.getElementById("brand-logo");
      logo.src = t.logo_url;
      logo.hidden = false;
      logo.onerror = () => { logo.hidden = true; };
    }
  } catch (err) {
    // Theme is cosmetic - fall back to defaults in styles.css, never block render.
    console.warn("Portal theme unavailable, using defaults:", err.message);
  }
}

async function initCards() {
  const cards = document.querySelectorAll(".card");
  for (const card of cards) {
    const state = card.querySelector(".card-state");
    if (!API_BASE) {
      state.dataset.state = "unconnected";
      state.textContent = "Not connected";
      continue;
    }
    const endpoint = card.querySelector(".card-body").dataset.endpoint;
    try {
      const res = await fetch(`${API_BASE}${endpoint}`, { credentials: "include" });
      state.dataset.state = res.ok ? "connected" : "error";
      state.textContent = res.ok ? "Connected" : `Service error (${res.status})`;
    } catch {
      state.dataset.state = "error";
      state.textContent = "Service unreachable";
    }
  }
}

applyTheme();
initCards();
