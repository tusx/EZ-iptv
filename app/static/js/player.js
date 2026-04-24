import { api, clearMessage, showMessage } from "./api.js";

export function truncateText(value, maxLength = 100) {
  const text = String(value ?? "").trim();
  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, Math.max(maxLength - 3, 0)).trimEnd()}...`;
}

export function formatItemTypeLabel(itemType) {
  const labels = {
    live: "Live TV",
    movie: "Movie",
    series: "Series",
    episode: "Episode",
  };

  return labels[itemType] || itemType || "Item";
}

export async function fetchPlaybackBundle(itemId) {
  const [{ item }, { item: playback }] = await Promise.all([
    api.get(`/items/${itemId}`),
    api.get(`/items/${itemId}/playback`),
  ]);

  return { item, playback };
}

export function createVideoJsPlayer(videoElement, playback = null) {
  if (!window.videojs) {
    throw new Error("Video.js is not available on this page.");
  }

  disposeVideoJsPlayer(videoElement);

  const player = window.videojs(videoElement, {
    autoplay: false,
    controls: true,
    preload: "auto",
    responsive: true,
    fluid: false,
    liveui: true,
    controlBar: {
      pictureInPictureToggle: false,
    },
    html5: {
      vhs: {
        overrideNative: !(window.videojs.browser && window.videojs.browser.IS_SAFARI),
      },
      nativeAudioTracks: false,
      nativeVideoTracks: false,
    },
  });

  if (playback) {
    attachPlaybackToPlayer(player, playback);
  }

  return player;
}

export function attachPlaybackToPlayer(player, playback) {
  player.src({
    src: playback.stream_url,
    type: playback.mime_type,
  });
}

export async function startPlaybackInElement(videoElement, playback) {
  const player = createVideoJsPlayer(videoElement, playback);

  try {
    await player.play();
  } catch (error) {
    // Some browsers require a user gesture timing window. The control bar remains ready.
  }

  return player;
}

export function disposeVideoJsPlayer(videoElement) {
  if (!window.videojs || !videoElement) {
    return;
  }

  const player = window.videojs.getPlayer(videoElement.id || videoElement);
  if (player) {
    player.dispose();
  }
}

export async function copyToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "absolute";
  textarea.style.left = "-9999px";
  document.body.append(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

export function populatePlaybackDetails({
  item,
  playback,
  titleElement,
  sourceElement,
  descriptionElement,
  typeElement,
  urlInput,
  openButton,
  titleMaxLength,
}) {
  if (titleElement) {
    const fullTitle = item.title || "Untitled item";
    titleElement.textContent = titleMaxLength ? truncateText(fullTitle, titleMaxLength) : fullTitle;
    titleElement.setAttribute("title", fullTitle);
    titleElement.setAttribute("aria-label", fullTitle);
  }
  if (sourceElement) {
    const sourceLabel = `${item.source_name || "Unknown source"} • ${item.category_name || "Uncategorized"}`;
    sourceElement.textContent = sourceLabel;
    sourceElement.setAttribute("title", sourceLabel);
  }
  if (descriptionElement) {
    descriptionElement.textContent = item.description || "No description is available for this item.";
  }
  if (typeElement) {
    typeElement.textContent = formatItemTypeLabel(item.item_type);
  }
  if (urlInput) {
    urlInput.value = playback.stream_url;
  }
  if (openButton) {
    openButton.href = playback.stream_url;
  }
}

export async function loadPlaybackIntoView({
  itemId,
  videoElement,
  messageElement,
  titleElement,
  sourceElement,
  descriptionElement,
  typeElement,
  urlInput,
  openButton,
  titleMaxLength,
}) {
  clearMessage(messageElement);

  try {
    const { item, playback } = await fetchPlaybackBundle(itemId);
    populatePlaybackDetails({
      item,
      playback,
      titleElement,
      sourceElement,
      descriptionElement,
      typeElement,
      urlInput,
      openButton,
      titleMaxLength,
    });

    return {
      item,
      playback,
      player: createVideoJsPlayer(videoElement, playback),
    };
  } catch (error) {
    showMessage(messageElement, error.message, "danger");
    throw error;
  }
}
