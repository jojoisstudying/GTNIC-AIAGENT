"""Cost calculations loaded from the editable config/pricing.json file."""
import json
from pathlib import Path
from typing import Any

from src import config


PRICING_PATH = config.ROOT / "config" / "pricing.json"


def load_pricing(path: Path = PRICING_PATH) -> dict[str, Any]:
    """Read pricing rates; missing or malformed data raises a clear configuration error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load pricing configuration from {path}") from exc


def calculate_llm_cost(model: str, tokens_in: int, tokens_out: int,
                       pricing: dict[str, Any] | None = None) -> float:
    """Calculate USD cost from token usage and per-million-token rates."""
    rates = (pricing or load_pricing()).get("models", {}).get(model)
    if rates is None:
        rates = (pricing or load_pricing()).get("default", {})
    input_rate = float(rates.get("input_per_million_usd", 0.0))
    output_rate = float(rates.get("output_per_million_usd", 0.0))
    if tokens_in < 0 or tokens_out < 0 or input_rate < 0 or output_rate < 0:
        raise ValueError("Token counts and pricing rates must be non-negative")
    return (tokens_in * input_rate + tokens_out * output_rate) / 1_000_000


def provider_units(provider: str, operations: int = 1,
                   pricing: dict[str, Any] | None = None) -> float:
    """Estimate provider credits/units from the configured per-operation rate."""
    if operations < 0:
        raise ValueError("operations must be non-negative")
    rates = (pricing or load_pricing()).get("providers", {}).get(provider, {})
    per_operation = float(rates.get("units_per_search", 0.0))
    return operations * per_operation
