"""Kebijakan autonomi per perusahaan dan per kategori konten.

Konfigurasi disimpan di ``EnterpriseProfile.approval_workflow_json``::

    {"autonomy_mode": "assisted|supervised|autonomous_routine|restricted",
     "routine_categories": ["Tips Praktis"],          # boleh auto-publish (mode autonomous_routine)
     "restricted_categories": ["Pengumuman Resmi"],   # selalu butuh persetujuan manusia
     "required_for": ["Informasi harga & penawaran"]}  # juga diperlakukan sebagai restricted

Mode:
- assisted: sistem membuat konten, manusia menyetujui sebelum dijadwalkan DAN dipublikasikan.
- supervised: sistem menjadwalkan sendiri item yang sudah disetujui; publikasi tetap butuh persetujuan manusia.
- autonomous_routine: kategori rutin eksplisit boleh disetujui, dijadwalkan, dan dipublikasikan otomatis.
- restricted: semua konten butuh persetujuan manusia (tanpa jadwal otomatis).
Kategori restricted selalu butuh manusia, apa pun modenya.
"""
from __future__ import annotations

import json

MODES = {"assisted", "supervised", "autonomous_routine", "restricted"}
_LEGACY = {"manual_review": "assisted", "manual": "assisted", "": "assisted"}


def load_policy(workflow_json: str | dict | None) -> dict:
    try:
        wf = json.loads(workflow_json) if isinstance(workflow_json, str) else dict(workflow_json or {})
    except (TypeError, ValueError):
        wf = {}
    mode = str(wf.get("autonomy_mode") or wf.get("default_mode") or "").strip().lower()
    mode = _LEGACY.get(mode, mode)
    if mode not in MODES:
        mode = "assisted"  # fail-safe: jangan pernah lebih longgar dari yang dikonfigurasi
    norm = lambda xs: {str(x).strip().lower() for x in (xs or [])}
    return {
        "mode": mode,
        "routine": norm(wf.get("routine_categories")),
        "restricted": norm(wf.get("restricted_categories")) | norm(wf.get("required_for")),
    }


def _cats(item) -> set[str]:
    return {str(v).strip().lower() for v in (item.content_pillar, item.objective) if v}


def is_restricted(policy: dict, item) -> bool:
    return policy["mode"] == "restricted" or bool(_cats(item) & policy["restricted"])


def is_routine(policy: dict, item) -> bool:
    return policy["mode"] == "autonomous_routine" and not is_restricted(policy, item) \
        and bool(_cats(item) & policy["routine"])


def may_auto_approve(policy: dict, item) -> bool:
    return is_routine(policy, item)


def may_auto_schedule(policy: dict, item) -> bool:
    return policy["mode"] in {"supervised", "autonomous_routine"} and not is_restricted(policy, item)


def may_publish(policy: dict, item) -> bool:
    """Boleh dipublikasikan scheduler? Manusia sudah menyetujui, atau kategori rutin otonom."""
    if item.approved_by == "api_user":
        return True
    return is_routine(policy, item)
