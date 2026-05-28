"""User-defined INCAR parameter templates — save, list, load, delete.

Templates are stored as individual JSON files under INCAR_TEMPLATES_DIR.
Each file: {"name": "...", "params": {"ENCUT": 520, ...}}
"""

import json
import re
from pathlib import Path

from app.core.config import INCAR_TEMPLATES_DIR


def _slug(name: str) -> str:
    """Convert a display name to a filesystem-safe slug."""
    slug = re.sub(r"[^\w\-]", "_", name).strip("_") or "unnamed"
    return slug


def _path(name: str) -> Path:
    return INCAR_TEMPLATES_DIR / f"{_slug(name)}.json"


def _ensure_dir() -> None:
    INCAR_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def list_templates() -> list[dict]:
    """Return all saved templates with their names and param counts."""
    _ensure_dir()
    result = []
    for fp in sorted(INCAR_TEMPLATES_DIR.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            result.append({
                "slug": fp.stem,
                "name": data.get("name", fp.stem),
                "params": data.get("params", {}),
                "n_params": len(data.get("params", {})),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return result


def save_template(name: str, params: dict) -> dict:
    """Save a template. Overwrites if the slug already exists."""
    if not name or not name.strip():
        raise ValueError("Template name cannot be empty")
    if not params:
        raise ValueError("Template params cannot be empty")
    _ensure_dir()
    slug = _slug(name)
    data = {"name": name.strip(), "params": params}
    _path(name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"slug": slug, "name": data["name"], "n_params": len(params)}


def load_template(name: str) -> dict:
    """Load a template by name or slug."""
    fp = _path(name)
    if not fp.exists():
        raise ValueError(f"Template '{name}' not found")
    return json.loads(fp.read_text(encoding="utf-8"))


def delete_template(name: str) -> bool:
    """Delete a template by name or slug. Returns True if deleted."""
    fp = _path(name)
    if fp.exists():
        fp.unlink()
        return True
    return False
