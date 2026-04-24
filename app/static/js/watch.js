import { clearMessage, showMessage } from "./api.js";
import {
  copyToClipboard,
  disposeVideoJsPlayer,
  fetchPlaybackBundle,
  populatePlaybackDetails,
  startPlaybackInElement,
} from "./player.js";

const view = document.querySelector("#watch-view");
const itemId = view.dataset.itemId;
const titleElement = document.querySelector("#watch-title");
const sourceElement = document.querySelector("#watch-source");
const descriptionElement = document.querySelector("#watch-description");
const typeElement = document.querySelector("#watch-type");
const messageBox = document.querySelector("#watch-message");
const videoHost = document.querySelector("#watch-video-host");
const streamUrlInput = document.querySelector("#watch-stream-url");
const copyUrlButton = document.querySelector("#watch-copy-url");

let playback = null;
let currentVideoElement = null;

function mountWatchPlaceholder(disabled = true) {
  videoHost.innerHTML = `
    <button class="player-launch-button" type="button" id="watch-launch" ${disabled ? "disabled" : ""}>
      <span class="player-launch-icon" aria-hidden="true">▶</span>
      <span class="player-launch-label">${disabled ? "Loading stream details..." : "Click play to load this stream"}</span>
    </button>
  `;
  currentVideoElement = null;
}

function mountWatchVideoElement() {
  const nextVideo = document.createElement("video");
  nextVideo.id = "video-player";
  nextVideo.className = "video-js vjs-default-skin vjs-big-play-centered w-100 h-100";
  nextVideo.setAttribute("controls", "");
  nextVideo.setAttribute("playsinline", "");
  videoHost.replaceChildren(nextVideo);
  currentVideoElement = nextVideo;
  return nextVideo;
}

copyUrlButton.addEventListener("click", async () => {
  if (!streamUrlInput.value) {
    return;
  }

  try {
    await copyToClipboard(streamUrlInput.value);
    showMessage(messageBox, "Stream URL copied to the clipboard.", "success");
  } catch (error) {
    showMessage(messageBox, "Could not copy the stream URL.", "danger");
  }
});

videoHost.addEventListener("click", async (event) => {
  const launchButton = event.target.closest("#watch-launch");
  if (!launchButton || !playback) {
    return;
  }

  showMessage(messageBox, "Connecting to the stream source...", "info");
  const videoElement = mountWatchVideoElement();

  try {
    await startPlaybackInElement(videoElement, playback);
    clearMessage(messageBox);
  } catch (error) {
    mountWatchPlaceholder(false);
    showMessage(messageBox, error.message, "danger");
  }
});

window.addEventListener("beforeunload", () => {
  disposeVideoJsPlayer(currentVideoElement);
});

async function bootstrapWatchPage() {
  clearMessage(messageBox);
  copyUrlButton.disabled = true;
  mountWatchPlaceholder(true);

  try {
    const bundle = await fetchPlaybackBundle(itemId);
    playback = bundle.playback;
    populatePlaybackDetails({
      item: bundle.item,
      playback,
      titleElement,
      sourceElement,
      descriptionElement,
      typeElement,
      urlInput: streamUrlInput,
    });
    copyUrlButton.disabled = false;
    mountWatchPlaceholder(false);
  } catch (error) {
    showMessage(messageBox, error.message, "danger");
  }
}

bootstrapWatchPage();
