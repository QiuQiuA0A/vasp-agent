"""Metal slab building for VASP surface calculations.

Architecture:
  MetalRegistry → lattice info (one dict per metal, keyed by symbol)
  build_slab()  → ASE slab Atoms
  merge_with_molecule() → combined slab+molecule Atoms
  to_poscar()   → VASP POSCAR string

Adding a new metal = adding one entry to the registry dict. No code changes elsewhere.

Currently implemented: Fe (BCC). Framework supports BCC/FCC/HCP extension.
"""

import io
from dataclasses import dataclass

from ase import Atoms
from ase.build import bcc100, bcc110, bcc111
from ase.io import read, write


# ─── Metal registry ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class _MetalInfo:
    symbol: str
    lattice_type: str  # "bcc", "fcc", "hcp"
    # BCC/FCC: single float a.  HCP: {"a": ..., "c": ...}
    lattice: float | dict[str, float]


REGISTRY: dict[str, _MetalInfo] = {
    # BCC
    "Fe": _MetalInfo(symbol="Fe", lattice_type="bcc", lattice=2.8665),
    "Cr": _MetalInfo(symbol="Cr", lattice_type="bcc", lattice=2.8840),
    # FCC — lattice constants included; surfaces not yet wired
    "Cu": _MetalInfo(symbol="Cu", lattice_type="fcc", lattice=3.6149),
    "Al": _MetalInfo(symbol="Al", lattice_type="fcc", lattice=4.0495),
    "Ni": _MetalInfo(symbol="Ni", lattice_type="fcc", lattice=3.5238),
    # HCP
    "Zn": _MetalInfo(symbol="Zn", lattice_type="hcp", lattice={"a": 2.6648, "c": 4.9467}),
    "Mg": _MetalInfo(symbol="Mg", lattice_type="hcp", lattice={"a": 3.2094, "c": 5.2107}),
    "Ti": _MetalInfo(symbol="Ti", lattice_type="hcp", lattice={"a": 2.9506, "c": 4.6788}),
}

# BCC surface builders — one function per Miller index
_BCC_SURFACES = {"100": bcc100, "110": bcc110, "111": bcc111}

SUPPORTED_SURFACES_FOR_METAL: dict[str, dict[str, list[str]]] = {
    "bcc": {"Fe": ["100", "110", "111"], "Cr": ["100", "110", "111"]},
    "fcc": {"Cu": ["100", "110", "111"], "Al": ["100", "110", "111"], "Ni": ["100", "110", "111"]},
    "hcp": {"Zn": ["0001", "10-10"], "Mg": ["0001", "10-10"], "Ti": ["0001", "10-10"]},
}


# ─── Public API ──────────────────────────────────────────────────────────

@dataclass
class SlabConfig:
    """Parameters for building a metal slab."""
    metal: str        # e.g. "Fe"
    surface: str      # e.g. "110"
    layers: int = 4
    vacuum: float = 15.0   # angstrom
    fix_bottom: int = 2    # freeze bottom N layers (0 = none)


@dataclass
class SlabResult:
    """Result of building a slab + merging a molecule."""
    metal: str
    surface: str
    n_slab_atoms: int
    n_molecule_atoms: int
    n_total: int
    poscar: str
    elements: list[str]
    counts: list[int]


def build_slab(config: SlabConfig) -> Atoms:
    """Build a clean metal slab as an ASE Atoms object."""
    info = _get_metal(config.metal)

    if info.lattice_type == "bcc":
        builder = _BCC_SURFACES.get(config.surface)
        if builder is None:
            raise ValueError(
                f"Surface {config.surface} not supported for BCC. "
                f"Choose: {sorted(_BCC_SURFACES)}"
            )
        a = float(info.lattice)
        slab = builder(info.symbol, a=a, size=(1, 1, config.layers), vacuum=config.vacuum)

    elif info.lattice_type == "fcc":
        raise NotImplementedError(
            f"FCC slab building not yet implemented. Metal '{config.metal}' "
            f"is registered but FCC surface builders are pending."
        )

    elif info.lattice_type == "hcp":
        raise NotImplementedError(
            f"HCP slab building not yet implemented. Metal '{config.metal}' "
            f"is registered but HCP surface builders are pending."
        )
    else:
        raise ValueError(f"Unknown lattice type: {info.lattice_type}")

    _label_layers(slab, config.layers)
    return slab


def merge_with_molecule(slab: Atoms, xyz_str: str) -> Atoms:
    """Merge a slab with a molecule from XYZ string.

    The molecule must already be positioned at the desired adsorption site
    (x, y, z coordinates) in the XYZ. The XYZ atoms are appended to the slab;
    no re-centering or rotation is performed by this function.

    Returns a new Atoms object. Original slab is not modified.
    """
    mol = read(io.StringIO(xyz_str), format="xyz")
    combined = slab.copy()
    for atom in mol:
        combined.append(atom)
    combined.set_cell(slab.get_cell())
    combined.set_pbc(slab.get_pbc())
    return combined


def to_poscar(atoms: Atoms, config: SlabConfig, selective: bool = True) -> str:
    """Write an Atoms object to VASP POSCAR format string.

    Sorts atoms by element (standard VASP convention), then injects selective
    dynamics: bottom config.fix_bottom slab layers → "F F F", everything else → "T T T".
    """
    # Sort atoms to match standard VASP POSCAR order
    from ase.build import sort as ase_sort
    sorted_atoms = ase_sort(atoms)

    # Build flag for each atom in sorted order
    flag_map: list[str] = []
    for atom in sorted_atoms:
        tag = int(atom.tag) if atom.tag is not None else 0
        if tag >= 1 and tag <= config.fix_bottom:
            flag_map.append("F F F")
        else:
            flag_map.append("T T T")

    buf = io.StringIO()
    write(buf, sorted_atoms, format="vasp", direct=False)  # no sort — already sorted
    raw = buf.getvalue()

    if selective and config.fix_bottom > 0:
        return _inject_selective_dynamics(raw, flag_map)
    return raw


def get_poscar(slab: Atoms, config: SlabConfig, xyz_str: str | None = None) -> SlabResult:
    """Full workflow: build slab, merge molecule, produce POSCAR + summary.

    If xyz_str is None, returns the clean slab POSCAR (no molecule).
    """
    if xyz_str:
        combined = merge_with_molecule(slab, xyz_str)
        mol = read(io.StringIO(xyz_str), format="xyz")
        n_mol = len(mol)
    else:
        combined = slab
        n_mol = 0

    poscar = to_poscar(combined, config)
    symbols = combined.get_chemical_symbols()
    el_order: list[str] = []
    counts: list[int] = []
    for s in symbols:
        if s not in el_order:
            el_order.append(s)
    for el in el_order:
        counts.append(symbols.count(el))

    return SlabResult(
        metal=config.metal,
        surface=config.surface,
        n_slab_atoms=len(slab),
        n_molecule_atoms=n_mol,
        n_total=len(combined),
        poscar=poscar,
        elements=el_order,
        counts=counts,
    )


def list_metals() -> dict:
    """Return all registered metals with their surface options."""
    result: dict[str, list[str]] = {}
    for lt, metals in SUPPORTED_SURFACES_FOR_METAL.items():
        for metal, surfaces in metals.items():
            result[metal] = {
                "lattice_type": lt,
                "lattice": (
                    float(REGISTRY[metal].lattice)
                    if isinstance(REGISTRY[metal].lattice, float)
                    else REGISTRY[metal].lattice
                ),
                "surfaces": surfaces,
            }
    return result


# ─── Internals ───────────────────────────────────────────────────────────

def _get_metal(name: str) -> _MetalInfo:
    if name not in REGISTRY:
        raise ValueError(
            f"Unknown metal '{name}'. Registered: {sorted(REGISTRY)}"
        )
    return REGISTRY[name]


def _label_layers(slab: Atoms, n_layers: int):
    """Re-tag atoms so bottom layer = 1, top layer = n_layers (sequential)."""
    zs = slab.positions[:, 2]
    # Sort unique z values bottom → top
    unique_z = sorted(set(zs.round(decimals=3)))
    if len(unique_z) != n_layers:
        # Sometimes ASE adds more z-positions; tag by binning
        pass
    for i, atom in enumerate(slab):
        z = round(float(atom.z), 3)
        # Map this atom's z to a layer index
        try:
            layer = unique_z.index(z) + 1  # 1-indexed
        except ValueError:
            layer = 1
        slab[i].tag = int(layer)


def _inject_selective_dynamics(poscar: str, flags: list[str]) -> str:
    """Rewrite POSCAR to include selective dynamics flags.

    flags[i] corresponds to the i-th atom coordinate line in the POSCAR.
    """
    lines = poscar.strip().split("\n")

    # Find the coordinate-type line (Cartesian or Direct)
    coord_idx = 0
    for i, line in enumerate(lines):
        if line.strip().upper() in ("CARTESIAN", "DIRECT"):
            coord_idx = i
            break

    if coord_idx == 0:
        return poscar

    # Inject "Selective dynamics" before the coordinate-type line
    result = (
        lines[:coord_idx]
        + ["Selective dynamics"]
        + lines[coord_idx:]
    )

    # Append flags to coordinate lines (after Cart/Direct)
    header_count = coord_idx + 2  # lines before atom coordinates (after injection)
    atom_lines = result[header_count:]
    atom_lines_with_flags = []
    for j, aline in enumerate(atom_lines):
        parts = aline.strip().split()
        if len(parts) >= 3:
            try:
                float(parts[0])
                flag = flags[j] if j < len(flags) else "T T T"
                atom_lines_with_flags.append(f"{aline.rstrip()}  {flag}")
            except (ValueError, IndexError):
                atom_lines_with_flags.append(aline)
        else:
            atom_lines_with_flags.append(aline)

    result = result[:header_count] + atom_lines_with_flags
    return "\n".join(result) + "\n"
