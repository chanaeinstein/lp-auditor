"""Tests for agent/models.py (models.yaml + startup availability check)."""

from __future__ import annotations

import copy

import httpx
import pytest

from agent.models import (
    ModelConfigError,
    ModelsUnavailableError,
    Price,
    family,
    fetch_available_models,
    load_config,
    select_models,
    validate_config,
)


def _all_ids(config: dict) -> set[str]:
    return {
        entry["id"]
        for roles in config["profiles"].values()
        for entries in roles.values()
        for entry in entries
    }


def test_real_models_yaml_is_valid() -> None:
    config = load_config()
    assert set(config["profiles"]) == {"free", "paid"}


def test_free_writer_and_evaluator_families_differ() -> None:
    roles = load_config()["profiles"]["free"]
    writers = {family(e["id"]) for e in roles["writer"]}
    evaluators = {family(e["id"]) for e in roles["evaluator"]}
    assert not writers & evaluators


def test_validate_rejects_non_free_id_in_free_profile() -> None:
    config = copy.deepcopy(load_config())
    config["profiles"]["free"]["guard"][0]["id"] = "google/gemma-4-31b-it"
    with pytest.raises(ModelConfigError, match=":free"):
        validate_config(config)


def test_validate_rejects_shared_family() -> None:
    config = copy.deepcopy(load_config())
    config["profiles"]["paid"]["evaluator"] = [{"id": "google/gemini-2.5-flash-lite"}]
    with pytest.raises(ModelConfigError, match="family"):
        validate_config(config)


def test_select_takes_first_available_and_theoretical_price() -> None:
    config = load_config()
    available = {i: Price() for i in _all_ids(config)}
    first_guard = config["profiles"]["free"]["guard"][0]
    del available[first_guard["id"]]
    second_guard = config["profiles"]["free"]["guard"][1]
    available[second_guard["theoretical_price_from"]] = Price(0.000001, 0.000003)

    choices = select_models(config, "free", available)

    assert choices["guard"].model_id == second_guard["id"]
    assert choices["guard"].theoretical_price == Price(0.000001, 0.000003)
    assert first_guard["id"] not in choices["guard"].fallbacks


def test_select_raises_clear_error_when_none_available() -> None:
    with pytest.raises(
        ModelsUnavailableError, match="No available model for role 'guard'"
    ):
        select_models(load_config(), "free", {}, roles=("guard",))


def test_select_rejects_unknown_profile() -> None:
    with pytest.raises(ModelConfigError, match="Unknown profile"):
        select_models(load_config(), "premium", {})


def test_fetch_available_models_parses_pricing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "a/model:free",
                        "pricing": {"prompt": "0", "completion": "0"},
                    },
                    {
                        "id": "a/model",
                        "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                    },
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    models = fetch_available_models("https://openrouter.test/api/v1", client=client)
    assert models["a/model"] == Price(0.000001, 0.000002)
    assert models["a/model:free"] == Price()


def test_fetch_available_models_network_error_is_clear() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(ModelsUnavailableError, match="network"):
        fetch_available_models(client=client)
