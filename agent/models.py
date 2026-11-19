"""Model configuration: load agent/models.yaml and pick the first available model per role."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

ROLES: tuple[str, ...] = ("guard", "writer", "evaluator", "judge")
PROFILES: tuple[str, ...] = ("free", "paid")
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class ModelConfigError(Exception):
    """models.yaml is missing or invalid."""


class ModelsUnavailableError(Exception):
    """The OpenRouter models endpoint could not be read, or no listed model is available."""


@dataclass(frozen=True)
class Price:
    """USD per token, as reported by the OpenRouter models endpoint."""

    prompt: float = 0.0
    completion: float = 0.0

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return prompt_tokens * self.prompt + completion_tokens * self.completion


@dataclass(frozen=True)
class ModelChoice:
    """The active model for one role, plus the remaining candidates for fallback."""

    role: str
    model_id: str
    price: Price
    theoretical_price: Price
    fallbacks: tuple[str, ...] = field(default_factory=tuple)


def resource_path(relative: str) -> Path:
    """Path to a bundled data file, both from source and inside the PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root / relative


def family(model_id: str) -> str:
    """Model family = the provider prefix of the OpenRouter id (e.g. 'google')."""
    return model_id.split("/", 1)[0]


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load and validate models.yaml."""
    path = path or resource_path("agent/models.yaml")
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelConfigError(f"Model config not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ModelConfigError(f"Model config is not valid YAML: {exc}") from exc
    validate_config(config)
    return config


def _entries(config: dict[str, Any], profile: str, role: str) -> list[dict[str, str]]:
    return config["profiles"][profile][role]


def validate_config(config: Any) -> None:
    """Enforce the rules from docs/SPEC.md section 5."""
    if not isinstance(config, dict) or not isinstance(config.get("profiles"), dict):
        raise ModelConfigError("Model config must have a 'profiles' mapping")
    for profile in PROFILES:
        roles = config["profiles"].get(profile)
        if not isinstance(roles, dict):
            raise ModelConfigError(f"Profile '{profile}' is missing")
        for role in ROLES:
            entries = roles.get(role)
            if not isinstance(entries, list) or not entries:
                raise ModelConfigError(
                    f"Role '{role}' in profile '{profile}' has no models"
                )
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                    raise ModelConfigError(
                        f"Every model in {profile}/{role} needs an 'id'"
                    )
                if (
                    profile == "free"
                    and role != "judge"
                    and not entry["id"].endswith(":free")
                ):
                    raise ModelConfigError(
                        f"Free profile model must end with ':free': {entry['id']}"
                    )
        writers = {family(e["id"]) for e in roles["writer"]}
        evaluators = {family(e["id"]) for e in roles["evaluator"]}
        if writers & evaluators:
            raise ModelConfigError(
                f"Writer and evaluator share a model family in profile '{profile}': "
                f"{', '.join(sorted(writers & evaluators))}"
            )


def _price(pricing: dict[str, Any] | None) -> Price:
    pricing = pricing or {}
    try:
        return Price(
            float(pricing.get("prompt") or 0), float(pricing.get("completion") or 0)
        )
    except (TypeError, ValueError):
        return Price()


def fetch_available_models(
    base_url: str = DEFAULT_BASE_URL, client: httpx.Client | None = None
) -> dict[str, Price]:
    """Call GET /models once and return {model_id: Price}."""
    own_client = client is None
    client = client or httpx.Client(timeout=20)
    try:
        response = client.get(f"{base_url.rstrip('/')}/models")
        response.raise_for_status()
        data = response.json()["data"]
    except httpx.HTTPError as exc:
        raise ModelsUnavailableError(
            "Cannot read the OpenRouter model list - check your network connection"
        ) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelsUnavailableError(
            "OpenRouter returned an unexpected model list - try again later"
        ) from exc
    finally:
        if own_client:
            client.close()
    return {
        m["id"]: _price(m.get("pricing"))
        for m in data
        if isinstance(m, dict) and "id" in m
    }


def select_models(
    config: dict[str, Any],
    profile: str,
    available: dict[str, Price],
    roles: tuple[str, ...] = ROLES,
) -> dict[str, ModelChoice]:
    """For each role, take the first listed model that is available."""
    if profile not in PROFILES:
        raise ModelConfigError(
            f"Unknown profile '{profile}' - use one of: {', '.join(PROFILES)}"
        )
    chosen: dict[str, ModelChoice] = {}
    for role in roles:
        entries = _entries(config, profile, role)
        usable = [e for e in entries if e["id"] in available]
        if not usable:
            listed = ", ".join(e["id"] for e in entries)
            raise ModelsUnavailableError(
                f"No available model for role '{role}' in profile '{profile}' ({listed}) "
                "- update agent/models.yaml"
            )
        first = usable[0]
        model_id = first["id"]
        price = available[model_id]
        twin = first.get("theoretical_price_from")
        theoretical = available.get(twin, price) if twin else price
        chosen[role] = ModelChoice(
            role=role,
            model_id=model_id,
            price=price,
            theoretical_price=theoretical,
            fallbacks=tuple(e["id"] for e in usable[1:]),
        )
    return chosen
