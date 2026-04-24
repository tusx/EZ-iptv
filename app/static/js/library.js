import { api, clearMessage, escapeHtml, showMessage } from "./api.js";
import {
  copyToClipboard,
  disposeVideoJsPlayer,
  fetchPlaybackBundle,
  formatItemTypeLabel,
  populatePlaybackDetails,
  startPlaybackInElement,
  truncateText,
} from "./player.js";

const PLAY_ICON = `
  <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true" focusable="false">
    <path fill="currentColor" d="M8 6.25v11.5c0 .62.68 1 1.2.67l9-5.75a.8.8 0 0 0 0-1.34l-9-5.75A.8.8 0 0 0 8 6.25Z"></path>
  </svg>
`;

const sourceFilter = document.querySelector("#source-filter");
const categoryFilter = document.querySelector("#category-filter");
const searchFilter = document.querySelector("#search-filter");
const itemGrid = document.querySelector("#item-grid");
const loadingBox = document.querySelector("#library-loading");
const messageBox = document.querySelector("#library-message");
const topPagination = document.querySelector("#library-pagination-top");
const bottomPagination = document.querySelector("#library-pagination-bottom");
const countSources = document.querySelector("#count-sources");
const countCategories = document.querySelector("#count-categories");
const countItems = document.querySelector("#count-items");

const seriesModalElement = document.querySelector("#series-modal");
const seriesModalTitle = document.querySelector("#series-modal-title");
const seriesModalSubtitle = document.querySelector("#series-modal-subtitle");
const seriesModalMessage = document.querySelector("#series-modal-message");
const seriesEpisodes = document.querySelector("#series-episodes");

const playerModalElement = document.querySelector("#player-modal");
const playerModalType = document.querySelector("#player-modal-type");
const playerModalTitle = document.querySelector("#player-modal-title");
const playerModalSubtitle = document.querySelector("#player-modal-subtitle");
const playerModalDescription = document.querySelector("#player-modal-description");
const playerModalVideoHost = document.querySelector("#player-modal-video-host");
const playerModalStreamUrl = document.querySelector("#player-modal-stream-url");
const playerModalCopyUrl = document.querySelector("#player-modal-copy-url");
const playerModalMessage = document.querySelector("#player-modal-message");

const seriesModal = new bootstrap.Modal(seriesModalElement);
const playerModal = new bootstrap.Modal(playerModalElement);
const TITLE_MAX_LENGTH = 100;

const state = {
  sourceId: "",
  categoryId: "",
  search: "",
  page: 1,
  perPage: 20,
  totalPages: 1,
  totalItems: 0,
};

let searchDebounceTimer = null;
let itemsRequestToken = 0;
let categoriesRequestToken = 0;
let seriesRequestToken = 0;
let playerRequestToken = 0;
let pendingEpisodeId = null;
let activePlayerItemId = null;
let activePlayback = null;
let playerModalVideo = null;

function setLoading(isLoading) {
  loadingBox.classList.toggle("d-none", !isLoading);
}

function updateCounters({ sourceCount, categoryCount, visibleCount }) {
  countSources.textContent = String(sourceCount);
  countCategories.textContent = String(categoryCount);
  countItems.textContent = String(visibleCount);
}

function sourceCount() {
  return Math.max(sourceFilter.options.length - 1, 0);
}

function categoryCount() {
  return Math.max(categoryFilter.options.length - 1, 0);
}

function buildQuery(params) {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) {
      searchParams.set(key, String(value));
    }
  });

  return searchParams.toString();
}

function imageMarkup(item) {
  return `
    <div class="item-poster-frame">
      ${item.artwork_url ? `
        <img
          class="item-poster item-poster-image"
          src="${escapeHtml(item.artwork_url)}"
          alt="${escapeHtml(item.title)} artwork"
          loading="lazy"
        >
      ` : ""}
      <div class="item-poster item-poster-fallback d-flex align-items-center justify-content-center px-3 text-center text-secondary ${item.artwork_url ? "d-none" : ""}">
        No artwork available
      </div>
    </div>
  `;
}

function renderItemCard(item) {
  const truncatedTitle = truncateText(item.title, TITLE_MAX_LENGTH);
  const playableOverlay = item.is_playable
    ? `
        <button
          class="item-play-overlay border-0"
          type="button"
          data-play-id="${item.id}"
          aria-label="Play ${escapeHtml(item.title)}"
          title="Play ${escapeHtml(item.title)}"
        >
          <span class="item-play-overlay-icon">
            ${PLAY_ICON}
          </span>
        </button>
      `
    : "";

  const actionMarkup = item.item_type === "series"
    ? `
        <button class="btn btn-outline-primary btn-sm mt-3" type="button" data-series-id="${item.id}">
          Browse episodes${item.children_count ? ` (${item.children_count})` : ""}
        </button>
      `
    : "";

  return `
    <article class="col-sm-6 col-xl-3">
      <div class="card h-100 item-card">
        <div class="item-poster-wrap">
          ${imageMarkup(item)}
          ${playableOverlay}
        </div>
        <div class="card-body d-flex flex-column">
          <div class="d-flex align-items-start justify-content-between gap-2 mb-2">
            <span class="badge text-bg-primary">${escapeHtml(formatItemTypeLabel(item.item_type))}</span>
            <span class="small text-secondary text-end">${escapeHtml(item.category_name || "Uncategorized")}</span>
          </div>
          <h2 class="h5 mb-2" title="${escapeHtml(item.title)}" aria-label="${escapeHtml(item.title)}">${escapeHtml(truncatedTitle)}</h2>
          <p class="small text-secondary mb-2">${escapeHtml(item.source_name || "Unknown source")}</p>
          <p class="text-secondary small mb-0 flex-grow-1">
            ${escapeHtml(item.description || "No description available for this item.")}
          </p>
          ${actionMarkup}
        </div>
      </div>
    </article>
  `;
}

function renderEmptyState(message) {
  itemGrid.innerHTML = `
    <div class="col-12">
      <section class="empty-state rounded-4 p-5 text-center">
        <h2 class="h4 mb-2">Nothing matched those filters.</h2>
        <p class="text-secondary mb-0">${escapeHtml(message)}</p>
      </section>
    </div>
  `;
}

function showPosterFallback(image) {
  const fallback = image.parentElement?.querySelector(".item-poster-fallback");
  image.classList.add("d-none");
  fallback?.classList.remove("d-none");
}

function bindPosterFallbacks() {
  itemGrid.querySelectorAll(".item-poster-image").forEach((image) => {
    if (image.dataset.posterBound === "true") {
      return;
    }

    image.dataset.posterBound = "true";
    image.addEventListener("error", () => showPosterFallback(image), { once: true });
    image.addEventListener("load", () => {
      if (!image.naturalWidth) {
        showPosterFallback(image);
      }
    }, { once: true });

    if (image.complete && !image.naturalWidth) {
      showPosterFallback(image);
    }
  });
}

function paginationPages(currentPage, totalPages) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const pages = new Set([1, totalPages, currentPage - 1, currentPage, currentPage + 1]);
  if (currentPage <= 3) {
    pages.add(2);
    pages.add(3);
    pages.add(4);
  }
  if (currentPage >= totalPages - 2) {
    pages.add(totalPages - 1);
    pages.add(totalPages - 2);
    pages.add(totalPages - 3);
  }

  const sortedPages = Array.from(pages).filter((page) => page >= 1 && page <= totalPages).sort((a, b) => a - b);
  const result = [];

  sortedPages.forEach((page) => {
    const previous = result[result.length - 1];
    if (previous && page - previous > 1) {
      result.push("ellipsis");
    }
    result.push(page);
  });

  return result;
}

function renderPagination(target, payload) {
  if (payload.total_pages <= 1) {
    target.innerHTML = "";
    target.classList.add("d-none");
    return;
  }

  const pageItems = paginationPages(payload.page, payload.total_pages).map((page) => {
    if (page === "ellipsis") {
      return `
        <li class="page-item disabled" aria-hidden="true">
          <span class="page-link">…</span>
        </li>
      `;
    }

    return `
      <li class="page-item ${page === payload.page ? "active" : ""}">
        <button class="page-link" type="button" data-page="${page}" ${page === payload.page ? 'aria-current="page"' : ""}>
          ${page}
        </button>
      </li>
    `;
  }).join("");

  target.innerHTML = `
    <ul class="pagination pagination-sm mb-0">
      <li class="page-item ${payload.has_prev ? "" : "disabled"}">
        <button class="page-link" type="button" data-page="${payload.page - 1}" ${payload.has_prev ? "" : "disabled"}>
          Previous
        </button>
      </li>
      ${pageItems}
      <li class="page-item ${payload.has_next ? "" : "disabled"}">
        <button class="page-link" type="button" data-page="${payload.page + 1}" ${payload.has_next ? "" : "disabled"}>
          Next
        </button>
      </li>
    </ul>
  `;
  target.classList.remove("d-none");
}

function resetPlayerModalContent() {
  playerModalType.textContent = "Loading";
  playerModalTitle.textContent = "Preparing stream...";
  playerModalTitle.removeAttribute("title");
  playerModalTitle.removeAttribute("aria-label");
  playerModalSubtitle.textContent = "";
  playerModalSubtitle.removeAttribute("title");
  playerModalDescription.textContent = "The app loads stream details first and only requests the provider stream after you press play.";
  playerModalStreamUrl.value = "";
  playerModalCopyUrl.disabled = true;
  activePlayback = null;
  clearMessage(playerModalMessage);
}

function mountPlayerPlaceholder(disabled = true) {
  playerModalVideoHost.innerHTML = `
    <button class="player-launch-button" type="button" id="player-modal-launch" ${disabled ? "disabled" : ""}>
      <span class="player-launch-icon" aria-hidden="true">▶</span>
      <span class="player-launch-label">${disabled ? "Loading stream details..." : "Click play to load this stream"}</span>
    </button>
  `;
  playerModalVideo = null;
}

function mountFreshPlayerElement() {
  const nextVideo = document.createElement("video");
  nextVideo.id = "player-modal-video";
  nextVideo.className = "video-js vjs-default-skin vjs-big-play-centered w-100 h-100";
  nextVideo.setAttribute("controls", "");
  nextVideo.setAttribute("playsinline", "");

  playerModalVideoHost.replaceChildren(nextVideo);
  playerModalVideo = nextVideo;
  return nextVideo;
}

async function loadPlayerModalItem(itemId) {
  const requestToken = ++playerRequestToken;
  activePlayerItemId = itemId;

  disposeVideoJsPlayer(playerModalVideo);
  mountPlayerPlaceholder(true);
  resetPlayerModalContent();
  showMessage(playerModalMessage, "Loading stream details from the app...", "info");

  try {
    const { item, playback } = await fetchPlaybackBundle(itemId);
    if (
      requestToken !== playerRequestToken
      || itemId !== activePlayerItemId
    ) {
      return null;
    }

    populatePlaybackDetails({
      item,
      playback,
      titleElement: playerModalTitle,
      sourceElement: playerModalSubtitle,
      descriptionElement: playerModalDescription,
      typeElement: playerModalType,
      urlInput: playerModalStreamUrl,
      titleMaxLength: TITLE_MAX_LENGTH,
    });
    activePlayback = playback;
    playerModalCopyUrl.disabled = false;
    mountPlayerPlaceholder(false);
    clearMessage(playerModalMessage);
    return { item, playback };
  } catch (error) {
    if (requestToken !== playerRequestToken) {
      return null;
    }
    showMessage(playerModalMessage, error.message, "danger");
    return null;
  }
}

async function openPlayerModal(itemId) {
  activePlayerItemId = itemId;

  if (!playerModalElement.classList.contains("show")) {
    playerModal.show();
  }

  await loadPlayerModalItem(itemId);
}

async function startModalPlayback() {
  if (!activePlayback || !activePlayerItemId) {
    return;
  }

  const requestToken = playerRequestToken;
  showMessage(playerModalMessage, "Connecting to the stream source...", "info");
  const freshVideoElement = mountFreshPlayerElement();

  try {
    const player = await startPlaybackInElement(freshVideoElement, activePlayback);
    if (requestToken !== playerRequestToken || !activePlayback) {
      player.dispose();
      return;
    }
    clearMessage(playerModalMessage);
    return player;
  } catch (error) {
    if (requestToken !== playerRequestToken) {
      return null;
    }
    mountPlayerPlaceholder(false);
    showMessage(playerModalMessage, error.message, "danger");
    return null;
  }
}

function resetSeriesModal() {
  seriesModalTitle.textContent = "Series details";
  seriesModalSubtitle.textContent = "";
  seriesEpisodes.innerHTML = "";
  clearMessage(seriesModalMessage);
}

function renderEpisodeList(seriesItem) {
  if (!seriesItem.children || seriesItem.children.length === 0) {
    showMessage(seriesModalMessage, "No episodes are available for this series yet.", "info");
    return;
  }

  seriesEpisodes.innerHTML = seriesItem.children.map((episode) => {
    const seasonLabel = episode.season_number ? `S${String(episode.season_number).padStart(2, "0")}` : "Season ?";
    const episodeLabel = episode.episode_number ? `E${String(episode.episode_number).padStart(2, "0")}` : "Episode";
    const meta = `${seasonLabel} • ${episodeLabel}`;

    return `
      <button
        class="list-group-item list-group-item-action py-3 episode-link"
        type="button"
        data-play-id="${episode.id}"
      >
        <div class="d-flex justify-content-between align-items-start gap-3">
          <div>
            <div class="fw-semibold">${escapeHtml(episode.title)}</div>
            <div class="small text-secondary">${escapeHtml(meta)}</div>
          </div>
          <span class="badge text-bg-primary align-self-center">Play</span>
        </div>
      </button>
    `;
  }).join("");
}

async function openSeriesModal(itemId) {
  const requestToken = ++seriesRequestToken;

  resetSeriesModal();
  seriesModal.show();
  showMessage(seriesModalMessage, "Loading episodes...", "info");

  try {
    const { item } = await api.get(`/items/${itemId}`);
    if (requestToken !== seriesRequestToken) {
      return;
    }

    clearMessage(seriesModalMessage);
    seriesModalTitle.textContent = item.title;
    seriesModalSubtitle.textContent = `${item.source_name || "Unknown source"} • ${item.category_name || "Uncategorized"}`;
    renderEpisodeList(item);
  } catch (error) {
    if (requestToken !== seriesRequestToken) {
      return;
    }
    showMessage(seriesModalMessage, error.message, "danger");
  }
}

async function loadSources() {
  const { items } = await api.get("/sources");
  const selectedValue = sourceFilter.value;

  sourceFilter.innerHTML = `
    <option value="">All sources</option>
    ${items.map((source) => `<option value="${source.id}">${escapeHtml(source.name)}</option>`).join("")}
  `;

  if (selectedValue && Array.from(sourceFilter.options).some((option) => option.value === selectedValue)) {
    sourceFilter.value = selectedValue;
  }

  updateCounters({
    sourceCount: sourceCount(),
    categoryCount: categoryCount(),
    visibleCount: Number(countItems.textContent || 0),
  });
}

async function loadCategories() {
  const requestToken = ++categoriesRequestToken;
  const query = buildQuery({ source_id: state.sourceId || null });

  try {
    const { items } = await api.get(`/categories${query ? `?${query}` : ""}`);
    if (requestToken !== categoriesRequestToken) {
      return;
    }

    const selectedValue = state.categoryId;
    categoryFilter.innerHTML = `
      <option value="">All categories</option>
      ${items.map((category) => `<option value="${category.id}">${escapeHtml(category.name)}</option>`).join("")}
    `;

    if (selectedValue && Array.from(categoryFilter.options).some((option) => option.value === selectedValue)) {
      categoryFilter.value = selectedValue;
    } else {
      categoryFilter.value = "";
      state.categoryId = "";
    }

    updateCounters({
      sourceCount: sourceCount(),
      categoryCount: categoryCount(),
      visibleCount: Number(countItems.textContent || 0),
    });
  } catch (error) {
    if (requestToken !== categoriesRequestToken) {
      return;
    }

    categoryFilter.innerHTML = '<option value="">All categories</option>';
    state.categoryId = "";
    updateCounters({
      sourceCount: sourceCount(),
      categoryCount: categoryCount(),
      visibleCount: Number(countItems.textContent || 0),
    });
    showMessage(messageBox, error.message, "danger");
  }
}

async function loadItems() {
  const requestToken = ++itemsRequestToken;
  setLoading(true);
  clearMessage(messageBox);

  const query = buildQuery({
    source_id: state.sourceId || null,
    category_id: state.categoryId || null,
    q: state.search || null,
    page: state.page,
    per_page: state.perPage,
  });

  try {
    const payload = await api.get(`/items?${query}`);
    if (requestToken !== itemsRequestToken) {
      return;
    }

    state.page = payload.page;
    state.perPage = payload.per_page;
    state.totalPages = payload.total_pages;
    state.totalItems = payload.total_items;

    if (payload.items.length === 0) {
      renderEmptyState("Try a different source, category, or title search.");
    } else {
      itemGrid.innerHTML = payload.items.map(renderItemCard).join("");
      bindPosterFallbacks();
    }

    renderPagination(topPagination, payload);
    renderPagination(bottomPagination, payload);
    updateCounters({
      sourceCount: sourceCount(),
      categoryCount: categoryCount(),
      visibleCount: payload.items.length,
    });
  } catch (error) {
    if (requestToken !== itemsRequestToken) {
      return;
    }

    itemGrid.innerHTML = "";
    renderPagination(topPagination, { total_pages: 0 });
    renderPagination(bottomPagination, { total_pages: 0 });
    updateCounters({
      sourceCount: sourceCount(),
      categoryCount: categoryCount(),
      visibleCount: 0,
    });
    showMessage(messageBox, error.message, "danger");
  } finally {
    if (requestToken === itemsRequestToken) {
      setLoading(false);
    }
  }
}

async function refreshLibrary({ reloadCategories = false } = {}) {
  if (reloadCategories) {
    await loadCategories();
  }
  await loadItems();
}

function queueSearchRefresh() {
  window.clearTimeout(searchDebounceTimer);
  searchDebounceTimer = window.setTimeout(() => {
    refreshLibrary();
  }, 250);
}

sourceFilter.addEventListener("change", async () => {
  state.sourceId = sourceFilter.value;
  state.categoryId = "";
  state.page = 1;
  await refreshLibrary({ reloadCategories: true });
});

categoryFilter.addEventListener("change", async () => {
  state.categoryId = categoryFilter.value;
  state.page = 1;
  await refreshLibrary();
});

searchFilter.addEventListener("input", () => {
  state.search = searchFilter.value.trim();
  state.page = 1;
  queueSearchRefresh();
});

[topPagination, bottomPagination].forEach((element) => {
  element.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-page]");
    if (!button || button.disabled) {
      return;
    }

    const nextPage = Number(button.dataset.page);
    if (!Number.isFinite(nextPage) || nextPage < 1 || nextPage === state.page) {
      return;
    }

    state.page = nextPage;
    await refreshLibrary();
    topPagination.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
});

itemGrid.addEventListener("click", async (event) => {
  const playTrigger = event.target.closest("[data-play-id]");
  if (playTrigger) {
    event.preventDefault();
    await openPlayerModal(playTrigger.dataset.playId);
    return;
  }

  const seriesTrigger = event.target.closest("[data-series-id]");
  if (seriesTrigger) {
    event.preventDefault();
    await openSeriesModal(seriesTrigger.dataset.seriesId);
  }
});

seriesEpisodes.addEventListener("click", (event) => {
  const playTrigger = event.target.closest("[data-play-id]");
  if (!playTrigger) {
    return;
  }

  pendingEpisodeId = playTrigger.dataset.playId;
  seriesModal.hide();
});

seriesModalElement.addEventListener("hidden.bs.modal", async () => {
  resetSeriesModal();

  if (!pendingEpisodeId) {
    return;
  }

  const itemId = pendingEpisodeId;
  pendingEpisodeId = null;
  await openPlayerModal(itemId);
});

playerModalVideoHost.addEventListener("click", async (event) => {
  const launchButton = event.target.closest("#player-modal-launch");
  if (!launchButton) {
    return;
  }

  event.preventDefault();
  await startModalPlayback();
});

playerModalCopyUrl.addEventListener("click", async () => {
  if (!playerModalStreamUrl.value) {
    return;
  }

  try {
    await copyToClipboard(playerModalStreamUrl.value);
    showMessage(playerModalMessage, "Stream URL copied to the clipboard.", "success");
  } catch (error) {
    showMessage(playerModalMessage, "Could not copy the stream URL.", "danger");
  }
});

playerModalElement.addEventListener("hidden.bs.modal", () => {
  playerRequestToken += 1;
  activePlayerItemId = null;
  activePlayback = null;
  disposeVideoJsPlayer(playerModalVideo);
  mountPlayerPlaceholder(true);
  resetPlayerModalContent();
});

async function bootstrapLibrary() {
  try {
    const [{ library_results_per_page: perPage }, _sources] = await Promise.all([
      api.get("/settings"),
      loadSources(),
    ]);

    state.perPage = perPage;
    await refreshLibrary({ reloadCategories: true });
  } catch (error) {
    setLoading(false);
    showMessage(messageBox, error.message, "danger");
  }
}

bootstrapLibrary();
