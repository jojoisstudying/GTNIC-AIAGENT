"""Model layout (dataclass murni) + validasi. Tidak bergantung pada pydantic."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .primitives.icons import ICON_NAMES

ROLES = ("cover", "konteks", "penjelasan", "langkah", "daftar", "data",
         "perbandingan", "bukti", "rangkuman", "cta")
STATUSES = ("draft", "approved", "retired")
DENSITIES = ("low", "medium", "high")
NEEDS_PHOTO = ("none", "optional", "required")
SLOT_TYPES = ("text", "list", "number", "image", "icon")


class LayoutError(ValueError):
    """Layout tidak valid (meta/schema/sample)."""


@dataclass(frozen=True)
class SlotSpec:
    name: str
    type: str = "text"
    required: bool = False
    min_chars: int = 0
    max_chars: int = 200
    min_items: int = 0
    max_items: int = 0
    item_max_chars: int = 0
    min_font_px: int = 0
    emphasis: bool = False


@dataclass(frozen=True)
class ParamSpec:
    name: str
    enum: tuple[str, ...]
    default: str


@dataclass(frozen=True)
class LayoutMeta:
    id: str
    role: str
    status: str
    density: str
    needs_photo: str
    pose_tags: tuple[str, ...] = ()
    photo_crop: str = ""
    tags: tuple[str, ...] = ()
    reference_notes: str = ""
    batch: int = 0


@dataclass(frozen=True)
class LayoutSpec:
    meta: LayoutMeta
    slots: dict[str, SlotSpec]
    params: dict[str, ParamSpec]
    path: Path
    samples: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.meta.id


def parse_meta(raw: dict, folder: str) -> LayoutMeta:
    for key in ("id", "role", "status", "density", "needs_photo"):
        if key not in raw:
            raise LayoutError(f"{folder}: meta.json tidak punya field '{key}'")
    if raw["id"] != folder:
        raise LayoutError(f"{folder}: id '{raw['id']}' harus sama dengan nama folder")
    checks = (("role", ROLES), ("status", STATUSES), ("density", DENSITIES), ("needs_photo", NEEDS_PHOTO))
    for key, allowed in checks:
        if raw[key] not in allowed:
            raise LayoutError(f"{folder}: {key}='{raw[key]}' tidak valid, harus salah satu dari {allowed}")
    return LayoutMeta(
        id=raw["id"], role=raw["role"], status=raw["status"], density=raw["density"],
        needs_photo=raw["needs_photo"], pose_tags=tuple(raw.get("pose_tags", ())),
        photo_crop=raw.get("photo_crop", ""), tags=tuple(raw.get("tags", ())),
        reference_notes=raw.get("reference_notes", ""), batch=int(raw.get("batch", 0)),
    )


def parse_schema(raw: dict, folder: str) -> tuple[dict[str, SlotSpec], dict[str, ParamSpec]]:
    slots: dict[str, SlotSpec] = {}
    for name, spec in (raw.get("slots") or {}).items():
        stype = spec.get("type", "text")
        if stype not in SLOT_TYPES:
            raise LayoutError(f"{folder}: slot '{name}' bertipe tidak dikenal '{stype}'")
        unknown = set(spec) - {"type", "required", "min_chars", "max_chars", "min_items", "max_items",
                               "item_max_chars", "min_font_px", "emphasis"}
        if unknown:
            raise LayoutError(f"{folder}: slot '{name}' punya field tidak dikenal {sorted(unknown)}")
        slots[name] = SlotSpec(name=name, **spec)
    if not slots:
        raise LayoutError(f"{folder}: schema.json harus punya minimal satu slot")
    params: dict[str, ParamSpec] = {}
    for name, spec in (raw.get("params") or {}).items():
        enum = tuple(str(x) for x in spec.get("enum", ()))
        default = str(spec.get("default", ""))
        if not enum or default not in enum:
            raise LayoutError(f"{folder}: param '{name}' butuh enum dan default yang ada di enum")
        params[name] = ParamSpec(name=name, enum=enum, default=default)
    return slots, params


def validate_content(spec: LayoutSpec, slots: dict, params: dict | None = None,
                     emphasis: list[str] | None = None) -> list[str]:
    """Kembalikan daftar pelanggaran (kosong = valid). Dipakai validator rencana nanti."""
    errors: list[str] = []
    params = params or {}
    for name in slots:
        if name not in spec.slots:
            errors.append(f"slot '{name}' tidak dikenal oleh layout {spec.id}")
    for name, s in spec.slots.items():
        val = slots.get(name)
        empty = val in (None, "", [])
        if empty:
            if s.required:
                errors.append(f"slot wajib '{name}' kosong")
            continue
        if s.type == "list":
            if not isinstance(val, list):
                errors.append(f"slot '{name}' harus list")
                continue
            if s.min_items and len(val) < s.min_items:
                errors.append(f"slot '{name}' butuh minimal {s.min_items} item ({len(val)})")
            if s.max_items and len(val) > s.max_items:
                errors.append(f"slot '{name}' melebihi {s.max_items} item ({len(val)})")
            for item in val:
                if s.item_max_chars and len(str(item)) > s.item_max_chars:
                    errors.append(f"item '{name}' melebihi {s.item_max_chars} karakter")
        elif s.type == "icon":
            if val not in ICON_NAMES:
                errors.append(f"ikon '{val}' tidak dikenal; pilihan: {list(ICON_NAMES)}")
        else:
            text = str(val)
            if len(text) > s.max_chars:
                errors.append(f"slot '{name}' {len(text)} karakter, maksimal {s.max_chars}")
            if len(text) < s.min_chars:
                errors.append(f"slot '{name}' {len(text)} karakter, minimal {s.min_chars}")
    for name, value in params.items():
        p = spec.params.get(name)
        if p is None:
            errors.append(f"param '{name}' tidak dikenal oleh layout {spec.id}")
        elif str(value) not in p.enum:
            errors.append(f"param '{name}'='{value}' di luar enum {list(p.enum)}")
    for e in emphasis or []:
        hay = " ".join(str(v) if not isinstance(v, list) else " ".join(map(str, v))
                       for v in slots.values() if v)
        if e.lower() not in hay.lower():
            errors.append(f"emphasis '{e}' tidak ditemukan di slot mana pun")
    return errors
