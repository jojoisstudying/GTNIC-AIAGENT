"""Shared test-only configuration; production authentication remains fail-closed."""
import os

# Existing integration tests exercise endpoint workflows without credentials. Make this
# deliberate, test-only development opt-in explicit rather than weakening app defaults.
os.environ.setdefault("ALLOW_UNAUTHENTICATED_DEV", "true")
