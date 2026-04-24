const API_BASE = "/api";

export async function apiRequest(path, options = {}) {
  const requestOptions = { ...options };
  requestOptions.headers = {
    "Accept": "application/json",
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
  };

  const response = await fetch(`${API_BASE}${path}`, requestOptions);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    throw new Error(payload?.error || `Request failed with status ${response.status}`);
  }

  return payload;
}

export const api = {
  get: (path) => apiRequest(path),
  post: (path, body) => apiRequest(path, { method: "POST", body: JSON.stringify(body) }),
  patch: (path, body) => apiRequest(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: (path) => apiRequest(path, { method: "DELETE" }),
};

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function formatDate(value) {
  if (!value) {
    return "Never";
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function statusBadge(status) {
  const styles = {
    success: "text-bg-success",
    failed: "text-bg-danger",
    syncing: "text-bg-warning text-dark",
    running: "text-bg-warning text-dark",
    queued: "text-bg-info text-dark",
    superseded: "text-bg-secondary",
    never: "text-bg-secondary",
  };

  return `<span class="badge ${styles[status] || "text-bg-secondary"}">${escapeHtml(status)}</span>`;
}

export function showMessage(element, message, kind = "info") {
  element.className = `alert alert-${kind}`;
  element.textContent = message;
  element.classList.remove("d-none");
}

export function clearMessage(element) {
  element.textContent = "";
  element.classList.add("d-none");
}
