"""KeyPool implementation for multi-key round-robin, cooldown, and masking."""
import hashlib
import os
import time
from typing import Any

from src.core.events import EventEmitter


class ProviderExhausted(RuntimeError):
    """Raised when all keys for a provider are in cooldown or unavailable."""


class KeyPool:
    """Round-robin API key pool with cooldown and safe key masking."""

    def __init__(self, provider: str, keys: list[str] | None = None, *,
                 cooldown_seconds: float = 60.0, emitter: EventEmitter | None = None) -> None:
        self.provider = provider.lower()
        self.cooldown_seconds = cooldown_seconds
        self.emitter = emitter
        self._index = 0
        self._cooldowns: dict[str, float] = {}

        if keys is not None:
            self.keys = [k.strip() for k in keys if k and k.strip()]
        else:
            self.keys = self._load_keys_from_env(self.provider)

    @staticmethod
    def _load_keys_from_env(provider: str) -> list[str]:
        p = provider.upper()
        # Check plural first e.g. GROQ_API_KEYS, TAVILY_API_KEYS
        plural_val = os.getenv(f"{p}_API_KEYS", "")
        if plural_val:
            keys = [k.strip() for k in plural_val.split(",") if k.strip()]
            if keys:
                return keys
        # Check singular e.g. GROQ_API_KEY, TAVILY_API_KEY
        single_val = os.getenv(f"{p}_API_KEY", "")
        if single_val and single_val.strip():
            return [single_val.strip()]
        return []

    @staticmethod
    def mask_key(key: str) -> str:
        """Return a safe 4-character identifier/hash of the key (never the key itself)."""
        if not key:
            return "none"
        # 4-character short hex digest of sha256
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:4]

    def get_current_key(self) -> str:
        """Get the current available active key without rotating."""
        return self.get_key(advance=False)

    def get_key(self, advance: bool = True) -> str:
        """Return an active key that is not in cooldown.

        Raises ProviderExhausted if no keys are configured or all keys are in cooldown.
        """
        if not self.keys:
            raise ProviderExhausted(f"No API keys configured for provider '{self.provider}'")

        now = time.monotonic()
        total = len(self.keys)

        # Check keys starting from current index
        for i in range(total):
            idx = (self._index + i) % total
            candidate = self.keys[idx]
            cooldown_until = self._cooldowns.get(candidate, 0.0)
            if now >= cooldown_until:
                if advance and total > 1 and i > 0:
                    prev_key = self.keys[self._index]
                    self._index = idx
                    if self.emitter:
                        self.emitter.emit("key", self.provider, step="key_pool", status="rotated",
                                          detail={"from_key": self.mask_key(prev_key),
                                                  "to_key": self.mask_key(candidate)})
                elif advance:
                    self._index = (idx + 1) % total
                return candidate

        raise ProviderExhausted(f"All keys for provider '{self.provider}' are cooling down")

    def cooldown(self, key: str, duration: float | None = None) -> None:
        """Mark a key as cooling down after receiving a rate limit (429)."""
        wait_time = duration if duration is not None else self.cooldown_seconds
        self._cooldowns[key] = time.monotonic() + wait_time
        if self.emitter:
            self.emitter.emit("key", self.provider, step="key_pool", status="cooldown",
                              detail={"key_id": self.mask_key(key), "duration_seconds": wait_time})
