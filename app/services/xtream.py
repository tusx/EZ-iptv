from __future__ import annotations

from urllib.parse import urlencode

import requests

from app.models import Source


class XtreamError(RuntimeError):
    pass


class XtreamClient:
    def __init__(self, source: Source):
        self.source = source
        self.base_url = normalize_base_url(source.xtream_base_url or "")
        self.username = source.username or ""
        self.password = source.password or ""
        self.session = requests.Session()
        if source.user_agent:
            self.session.headers["User-Agent"] = source.user_agent

    def get_live_categories(self):
        return self._get_json("get_live_categories")

    def get_vod_categories(self):
        return self._get_json("get_vod_categories")

    def get_series_categories(self):
        return self._get_json("get_series_categories")

    def get_live_streams(self):
        return self._get_json("get_live_streams")

    def get_vod_streams(self):
        return self._get_json("get_vod_streams")

    def get_series(self):
        return self._get_json("get_series")

    def get_series_info(self, series_id: str):
        return self._get_json("get_series_info", series_id=series_id)

    def build_stream_url(self, item_type: str, stream_id: str | int, extension: str | None = None) -> str:
        stream_id = str(stream_id)
        ext = extension or ("ts" if item_type == "live" else "mp4")

        if item_type == "live":
            return f"{self.base_url}/live/{self.username}/{self.password}/{stream_id}.{ext}"
        if item_type == "movie":
            return f"{self.base_url}/movie/{self.username}/{self.password}/{stream_id}.{ext}"
        if item_type == "episode":
            return f"{self.base_url}/series/{self.username}/{self.password}/{stream_id}.{ext}"
        raise XtreamError(f"Unsupported playback type: {item_type}")

    def _get_json(self, action: str, **params):
        query = urlencode(
            {
                "username": self.username,
                "password": self.password,
                "action": action,
                **params,
            }
        )
        response = self.session.get(f"{self.base_url}/player_api.php?{query}", timeout=30)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and data.get("user_info", {}).get("auth") == 0:
            raise XtreamError("Xtream source rejected the supplied credentials.")

        return data


def normalize_base_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if value.endswith("/player_api.php"):
        return value[: -len("/player_api.php")]
    return value
