const root = document.documentElement;
const themeToggleButton = document.querySelector("#theme-toggle");
const themeToggleIcon = document.querySelector("#theme-toggle-icon");

let currentTheme = root.dataset.theme || "dark";

function iconMarkup(theme) {
  if (theme === "dark") {
    return `
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="4"></circle>
        <path d="M12 2v2.5"></path>
        <path d="M12 19.5V22"></path>
        <path d="M4.93 4.93l1.77 1.77"></path>
        <path d="M17.3 17.3l1.77 1.77"></path>
        <path d="M2 12h2.5"></path>
        <path d="M19.5 12H22"></path>
        <path d="M4.93 19.07l1.77-1.77"></path>
        <path d="M17.3 6.7l1.77-1.77"></path>
      </svg>
    `;
  }

  return `
    <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
      <path d="M21 12.79A9 9 0 0 1 11.21 3a1 1 0 0 0-1.3-1.14A10 10 0 1 0 22.14 14.1a1 1 0 0 0-1.14-1.31z"></path>
    </svg>
  `;
}

function updateThemeToggle(theme) {
  if (!themeToggleButton || !themeToggleIcon) {
    return;
  }

  const nextTheme = theme === "dark" ? "light" : "dark";
  themeToggleIcon.innerHTML = iconMarkup(theme);
  themeToggleButton.setAttribute("aria-label", `Switch to ${nextTheme} mode`);
  themeToggleButton.setAttribute("title", `Switch to ${nextTheme} mode`);
}

function applyTheme(theme) {
  currentTheme = theme === "light" ? "light" : "dark";
  root.dataset.theme = currentTheme;
  root.dataset.bsTheme = currentTheme;
  window.localStorage.setItem("eziptv-theme", currentTheme);
  updateThemeToggle(currentTheme);
}

async function saveTheme(theme) {
  const response = await fetch("/api/settings", {
    method: "PATCH",
    headers: {
      "Accept": "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ default_theme: theme }),
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    throw new Error(payload?.error || `Request failed with status ${response.status}`);
  }

  return payload;
}

async function loadThemeFromSettings() {
  try {
    const response = await fetch("/api/settings", {
      headers: { "Accept": "application/json" },
    });
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    const payload = await response.json();
    applyTheme(payload.default_theme || "dark");
    document.dispatchEvent(new CustomEvent("app-theme-loaded", { detail: { theme: currentTheme } }));
  } catch (error) {
    updateThemeToggle(currentTheme);
  }
}

document.addEventListener("app-theme-changed", (event) => {
  applyTheme(event.detail?.theme || "dark");
});

if (themeToggleButton) {
  themeToggleButton.addEventListener("click", async () => {
    const nextTheme = currentTheme === "dark" ? "light" : "dark";
    const previousTheme = currentTheme;

    applyTheme(nextTheme);

    try {
      const payload = await saveTheme(nextTheme);
      const savedTheme = payload.default_theme || nextTheme;
      applyTheme(savedTheme);
      document.dispatchEvent(new CustomEvent("app-theme-loaded", { detail: { theme: savedTheme } }));
    } catch (error) {
      applyTheme(previousTheme);
    }
  });
}

updateThemeToggle(currentTheme);
loadThemeFromSettings();
