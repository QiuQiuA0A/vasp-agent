import re
from pathlib import Path

from app.core.config import POTCAR_LIBRARY, POTCAR_FUNCTIONAL
from app.services.potcar.potcar import POTCAR_MAP


def _lib_root(functional: str | None = None) -> Path:
    func = functional or POTCAR_FUNCTIONAL
    return POTCAR_LIBRARY / func


def scan_library(functional: str | None = None) -> dict[str, bool]:
    """Scan the POTCAR library and return availability for every known element."""
    root = _lib_root(functional)
    return {
        el: (root / sub / "POTCAR").exists()
        for el, sub in POTCAR_MAP.items()
    }


def list_functionals() -> list[dict]:
    """List available functionals with element counts."""
    result = []
    for d in sorted(POTCAR_LIBRARY.iterdir()):
        if d.is_dir() and (d / 'H' / 'POTCAR').exists() or (d / 'H' / 'POTCAR').exists():
            pass  # check actual element count
        if d.is_dir():
            n = sum(1 for _ in d.iterdir() if _.is_dir())
            result.append({"name": d.name, "available": n, "total": len(POTCAR_MAP)})
    return result


def library_stats(functional: str | None = None) -> dict:
    """Summary of the POTCAR library state for a functional."""
    avail = scan_library(functional)
    total = len(avail)
    present = sum(1 for v in avail.values() if v)
    func = functional or POTCAR_FUNCTIONAL
    return {
        "functional": func,
        "total_elements": total,
        "available": present,
        "missing": total - present,
        "elements": avail,
    }


def detect_element(content: str) -> str | None:
    """Auto-detect element symbol from POTCAR content (TITEL line).

    Typical VASP POTCAR contains a line like:
      TITEL  = PAW_PBE O 03May2023
    or:
      TITEL  = PAW_PBE Fe_pv 02Aug2007
    """
    m = re.search(r"TITEL\s*=\s*PAW[_\w]*\s+(\w+)", content)
    if not m:
        return None
    symbol = m.group(1)
    bare = symbol.split("_")[0]
    if re.match(r"^[A-Z][a-z]?$", bare):
        return bare
    return None


def import_potcar(content: str, folder_name: str | None = None,
                  functional: str | None = None) -> tuple[str, str]:
    """Import a POTCAR file into the library.

    If folder_name is not given, auto-detect from content.
    Returns (element_symbol, folder_used).
    """
    root = _lib_root(functional)
    if folder_name:
        subfolder = folder_name
        elem = folder_name.split("_")[0]
    else:
        elem = detect_element(content)
        if not elem:
            raise ValueError(
                "Cannot detect element from POTCAR content. "
                "Ensure the file is a valid VASP POTCAR with a TITEL line."
            )
        subfolder = POTCAR_MAP.get(elem, elem)

    folder = root / subfolder
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "POTCAR").write_text(content)
    return elem, subfolder


def remove_potcar(element: str, functional: str | None = None) -> bool:
    """Remove a POTCAR from the library. Returns True if it existed."""
    subfolder = POTCAR_MAP.get(element, element)
    potcar_file = _lib_root(functional) / subfolder / "POTCAR"
    if potcar_file.exists():
        potcar_file.unlink()
        parent = potcar_file.parent
        if not any(parent.iterdir()):
            parent.rmdir()
        return True
    return False


def bulk_import(files: list[tuple[str, str]],
                functional: str | None = None) -> dict:
    """Import multiple POTCAR files at once.

    Each item is (filename, content).
    Returns {filename: "ok"/"error message"}.
    """
    results = {}
    for fname, content in files:
        try:
            elem, folder = import_potcar(content, functional=functional)
            results[fname] = f"ok: {elem} → {folder}/POTCAR"
        except ValueError as e:
            results[fname] = str(e)
    return results
