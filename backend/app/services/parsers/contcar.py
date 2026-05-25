from dataclasses import dataclass, field


@dataclass
class ContcarResult:
    """Parsed CONTCAR — final structure from a VASP run."""

    formula: str = ""
    lattice_constant: float = 1.0
    lattice: list[tuple[float, float, float]] | None = None
    elements: list[str] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)
    n_atoms: int = 0
    selective: bool = False
    coordinate_type: str = "Cartesian"
    atoms: list[dict] = field(default_factory=list)  # [{element, x, y, z, fixed: [T/F]}]


def parse_contcar(content: str) -> ContcarResult:
    """Parse CONTCAR file — same format as POSCAR.

    Extracts: formula, lattice vectors, element list, atom positions.
    """
    result = ContcarResult()
    lines = content.strip().split("\n")
    if len(lines) < 6:
        return result

    result.formula = lines[0].strip()

    try:
        result.lattice_constant = float(lines[1].strip())
    except ValueError:
        pass

    # Lattice vectors
    lattice: list[tuple[float, float, float]] = []
    for i in range(2, 5):
        if i >= len(lines):
            break
        parts = lines[i].strip().split()
        if len(parts) >= 3:
            try:
                lattice.append((float(parts[0]), float(parts[1]), float(parts[2])))
            except ValueError:
                pass
    if len(lattice) == 3:
        result.lattice = lattice

    # Find the coordinate type line
    coord_line = 0
    for i in range(5, min(len(lines), 20)):
        stripped = lines[i].strip().upper()
        if stripped in ("CARTESIAN", "DIRECT"):
            coord_line = i
            result.coordinate_type = stripped.capitalize()
            break
        # Selective dynamics line
        if stripped.startswith("SEL"):
            result.selective = True

    # Element names and counts are at lines 5 and 6 (or 5-7 with selective)
    # But positions start after coordinate type line
    # Let's backtrack: after lattice (lines 2-4), next come elements + counts + optional selective + coord type
    # Elements: line 5 (0-indexed)
    # Counts: line 6
    # [Selective: line 7]
    # Cartesian/Direct: line 7 or 8

    el_line = 5
    count_line = 6  # always at line 6 — Selective dynamics comes after counts, not before

    if el_line < len(lines):
        result.elements = lines[el_line].strip().split()
    if count_line < len(lines):
        try:
            result.counts = [int(c) for c in lines[count_line].strip().split()]
            result.n_atoms = sum(result.counts)
        except ValueError:
            pass

    # Atom positions
    start = coord_line + 1 if coord_line > 0 else max(count_line, el_line) + 2
    for i in range(start, len(lines)):
        parts = lines[i].strip().split()
        if len(parts) < 3:
            continue
        try:
            x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
            fixed = []
            if len(parts) >= 6:
                fixed = [p.upper() == "T" for p in parts[3:6]]
            result.atoms.append({"x": x, "y": y, "z": z, "fixed": fixed})
        except ValueError:
            continue

    # Assign element labels to atoms
    if result.elements and result.counts:
        el_idx = 0
        remaining = result.counts[0] if result.counts else 0
        for atom in result.atoms:
            while remaining == 0 and el_idx + 1 < len(result.counts):
                el_idx += 1
                remaining = result.counts[el_idx]
            if el_idx < len(result.elements):
                atom["element"] = result.elements[el_idx]
            remaining -= 1

    return result


def contcar_to_xyz(result: ContcarResult) -> str:
    """Convert parsed CONTCAR to XYZ format string."""
    lines = [str(result.n_atoms), result.formula]
    for atom in result.atoms:
        el = atom.get("element", "X")
        lines.append(f"{el:2s}  {atom['x']:12.8f}  {atom['y']:12.8f}  {atom['z']:12.8f}")
    return "\n".join(lines)
