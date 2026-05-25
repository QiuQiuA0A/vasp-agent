import re
from pathlib import Path

from app.core.config import POTCAR_LIBRARY
from app.services.potcar import POTCAR_MAP


def _lib_root() -> Path:
    return Path(POTCAR_LIBRARY)


def scan_library() -> dict[str, bool]:
    """Scan the POTCAR library and return availability for every known element."""
    root = _lib_root()
    return {
        el: (root / sub / "POTCAR").exists()
        for el, sub in POTCAR_MAP.items()
    }


def library_stats() -> dict:
    """Summary of the POTCAR library state."""
    avail = scan_library()
    total = len(avail)
    present = sum(1 for v in avail.values() if v)
    return {
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
    # Some POTCARs use the subfolder name (e.g. "Fe_pv") as the element token
    # Normalize to the bare element symbol
    bare = symbol.split("_")[0]
    # Verify it looks like an element (1-2 chars, starts with uppercase)
    if re.match(r"^[A-Z][a-z]?$", bare):
        return bare
    return None


def import_potcar(content: str, folder_name: str | None = None) -> tuple[str, str]:
    """Import a POTCAR file into the library.

    If folder_name is not given, auto-detect from content.
    Returns (element_symbol, folder_used).
    """
    root = _lib_root()
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


def remove_potcar(element: str) -> bool:
    """Remove a POTCAR from the library. Returns True if it existed."""
    subfolder = POTCAR_MAP.get(element, element)
    potcar_file = _lib_root() / subfolder / "POTCAR"
    if potcar_file.exists():
        potcar_file.unlink()
        # Remove parent folder if empty
        parent = potcar_file.parent
        if not any(parent.iterdir()):
            parent.rmdir()
        return True
    return False


def bulk_import(files: list[tuple[str, str]]) -> dict:
    """Import multiple POTCAR files at once.

    Each item is (filename, content).
    Returns {filename: "ok"/"error message"}.
    """
    results = {}
    for fname, content in files:
        try:
            elem, folder = import_potcar(content)
            results[fname] = f"ok: {elem} → {folder}/POTCAR"
        except ValueError as e:
            results[fname] = str(e)
    return results
