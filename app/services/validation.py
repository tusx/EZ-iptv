from __future__ import annotations


class ValidationError(ValueError):
    pass


ALLOWED_SOURCE_TYPES = {"m3u", "xtream"}
ALLOWED_THEMES = {"dark", "light"}


def normalize_source_payload(payload: dict, partial: bool = False) -> dict:
    source_type = (payload.get("source_type") or "").strip().lower()

    if not partial or source_type:
        if source_type not in ALLOWED_SOURCE_TYPES:
            raise ValidationError("source_type must be either 'm3u' or 'xtream'.")

    name = (payload.get("name") or "").strip()
    if not partial or "name" in payload:
        if not name:
            raise ValidationError("name is required.")

    normalized = {
        "name": name,
        "source_type": source_type,
        "enabled": bool(payload.get("enabled", True)),
        "m3u_url": clean_nullable(payload.get("m3u_url")),
        "xtream_base_url": clean_nullable(payload.get("xtream_base_url")),
        "username": clean_nullable(payload.get("username")),
        "password": clean_nullable(payload.get("password")),
        "user_agent": clean_nullable(payload.get("user_agent")),
    }

    if source_type == "m3u":
        if not normalized["m3u_url"]:
            raise ValidationError("m3u_url is required for M3U sources.")
        normalized["xtream_base_url"] = None
        normalized["username"] = None
        normalized["password"] = None
    elif source_type == "xtream":
        if not normalized["xtream_base_url"]:
            raise ValidationError("xtream_base_url is required for Xtream sources.")
        if not normalized["username"]:
            raise ValidationError("username is required for Xtream sources.")
        if not normalized["password"]:
            raise ValidationError("password is required for Xtream sources.")
        normalized["m3u_url"] = None

    return normalized


def normalize_settings_payload(
    payload: dict,
    *,
    min_minutes: int,
    max_minutes: int,
    min_results_per_page: int,
    max_results_per_page: int,
) -> dict:
    normalized: dict[str, int] = {}

    if "sync_timeout_minutes" in payload:
        value = payload.get("sync_timeout_minutes")

        try:
            minutes = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError("sync_timeout_minutes must be an integer.") from exc

        if minutes < min_minutes or minutes > max_minutes:
            raise ValidationError(
                f"sync_timeout_minutes must be between {min_minutes} and {max_minutes}."
            )

        normalized["sync_timeout_minutes"] = minutes

    if "library_results_per_page" in payload:
        value = payload.get("library_results_per_page")

        try:
            results_per_page = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError("library_results_per_page must be an integer.") from exc

        if results_per_page < min_results_per_page or results_per_page > max_results_per_page:
            raise ValidationError(
                "library_results_per_page must be between "
                f"{min_results_per_page} and {max_results_per_page}."
            )

        normalized["library_results_per_page"] = results_per_page

    if "default_theme" in payload:
        theme = str(payload.get("default_theme") or "").strip().lower()
        if theme not in ALLOWED_THEMES:
            raise ValidationError("default_theme must be either 'dark' or 'light'.")
        normalized["default_theme"] = theme

    if not normalized:
        raise ValidationError("At least one supported setting is required.")

    return normalized


def clean_nullable(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None
