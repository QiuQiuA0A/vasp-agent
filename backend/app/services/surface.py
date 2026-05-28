"""Metal slab building for VASP surface calculations.

Architecture:
  MetalRegistry -> pymatgen Structure -> SlabGenerator -> ASE Atoms
  -> merge_with_molecule -> to_poscar (with selective dynamics)

Adding a new metal = adding one entry to the registry dict. All lattice types
(BCC/FCC/HCP) are handled uniformly by pymatgen's SlabGenerator.
"""

import io
from dataclasses import dataclass

import numpy as np
from ase import Atoms
from ase.io import read, write

from pymatgen.core.structure import Structure
from pymatgen.core.lattice import Lattice
from pymatgen.core.surface import SlabGenerator
from pymatgen.io.ase import AseAtomsAdaptor

from app.core.config import VASP_DEFAULTS
from app.services.vasp_templates import render_incar, render_kpoints, render_slurm


# ─── Metal registry ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class _MetalInfo:
    symbol: str
    lattice_type: str        # "bcc", "fcc", "hcp"
    lattice_constants: dict  # {"a": 2.8665} for cubic, {"a": 3.2, "c": 5.2} for HCP
    space_group: str         # e.g. "Im-3m", "Fm-3m", "P6_3/mmc"
    wyckoff: list[list[float]]  # fractional coordinates of basis atoms


REGISTRY: dict[str, _MetalInfo] = {
    "Fe": _MetalInfo("Fe", "bcc", {"a": 2.8665}, "Im-3m", [[0, 0, 0]]),
    "Cr": _MetalInfo("Cr", "bcc", {"a": 2.8840}, "Im-3m", [[0, 0, 0]]),
    "Cu": _MetalInfo("Cu", "fcc", {"a": 3.6149}, "Fm-3m", [[0, 0, 0]]),
    "Al": _MetalInfo("Al", "fcc", {"a": 4.0495}, "Fm-3m", [[0, 0, 0]]),
    "Ni": _MetalInfo("Ni", "fcc", {"a": 3.5238}, "Fm-3m", [[0, 0, 0]]),
    "Zn": _MetalInfo("Zn", "hcp", {"a": 2.6648, "c": 4.9467}, "P6_3/mmc",
                     [[1/3, 2/3, 1/4]]),
    "Mg": _MetalInfo("Mg", "hcp", {"a": 3.2094, "c": 5.2107}, "P6_3/mmc",
                     [[1/3, 2/3, 1/4]]),
    "Ti": _MetalInfo("Ti", "hcp", {"a": 2.9506, "c": 4.6788}, "P6_3/mmc",
                     [[1/3, 2/3, 1/4]]),
}

# Standard low-index surfaces per lattice type
_STANDARD_SURFACES: dict[str, list[str]] = {
    "bcc": ["100", "110", "111"],
    "fcc": ["100", "110", "111"],
    "hcp": ["0001", "10-10"],
}


# ─── Public API ──────────────────────────────────────────────────────────

@dataclass
class SlabConfig:
    """Parameters for building a metal slab."""
    metal: str        # e.g. "Fe"
    surface: str      # e.g. "110"
    layers: int = 4
    vacuum: float = 15.0   # total vacuum gap in angstrom
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
    """Build a clean metal slab using pymatgen's SlabGenerator."""
    info = _get_metal(config.metal)
    bulk = _make_bulk(info)
    miller = _parse_miller(config.surface)

    d_hkl = bulk.lattice.d_hkl(miller)
    slab_thickness = config.layers * d_hkl

    sg = SlabGenerator(
        bulk,
        miller,
        min_slab_size=slab_thickness,
        min_vacuum_size=config.vacuum / 2.0,
        in_unit_planes=False,
        center_slab=True,
    )
    slabs = sg.get_slabs()
    if not slabs:
        raise ValueError(
            f"No slabs generated for {config.metal}({config.surface})"
        )

    pmg_slab = slabs[0]
    atoms = AseAtomsAdaptor.get_atoms(pmg_slab)

    # Reposition: place slab at bottom of cell with vacuum on top
    zs = atoms.positions[:, 2]
    z_min = float(zs.min())
    slab_height = float(zs.max() - zs.min())
    cell = atoms.get_cell().array.copy()
    cell[2, 2] = slab_height + config.vacuum
    atoms.set_cell(cell)
    atoms.positions[:, 2] -= z_min

    _label_layers(atoms, config.layers)
    return atoms


def merge_with_molecule(slab: Atoms, xyz_str: str) -> Atoms:
    """Merge a slab with a molecule from XYZ string.

    The molecule must already be positioned at the desired adsorption site
    (x, y, z coordinates) in the XYZ. The XYZ atoms are appended to the slab;
    no re-centering or rotation is performed.
    """
    mol = read(io.StringIO(xyz_str), format="xyz")
    combined = slab.copy()
    for atom_idx in range(len(mol)):
        combined.append(mol[atom_idx])
    combined.set_cell(slab.get_cell())
    combined.set_pbc(slab.get_pbc())
    return combined


def to_poscar(atoms: Atoms, config: SlabConfig, selective: bool = True) -> str:
    """Write an Atoms object to VASP POSCAR format string.

    Sorts atoms by element, then injects selective dynamics:
    bottom config.fix_bottom slab layers -> "F F F", everything else -> "T T T".
    """
    from ase.build import sort as ase_sort
    sorted_atoms = ase_sort(atoms)

    flag_map: list[str] = []
    for atom in sorted_atoms:
        tag = int(atom.tag) if atom.tag is not None else 0
        if 1 <= tag <= config.fix_bottom:
            flag_map.append("F F F")
        else:
            flag_map.append("T T T")

    buf = io.StringIO()
    write(buf, sorted_atoms, format="vasp", direct=False)
    raw = buf.getvalue()

    if selective and config.fix_bottom > 0:
        return _inject_selective_dynamics(raw, flag_map)
    return raw


def get_poscar(
    slab: Atoms, config: SlabConfig, xyz_str: str | None = None
) -> SlabResult:
    """Full workflow: build slab, merge molecule, produce POSCAR + summary."""
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


def list_metals() -> dict[str, dict]:
    """Return all registered metals with their surface options."""
    result: dict[str, dict] = {}
    for symbol, info in REGISTRY.items():
        result[symbol] = {
            "lattice_type": info.lattice_type,
            "lattice": info.lattice_constants,
            "surfaces": _STANDARD_SURFACES.get(info.lattice_type, []),
        }
    return result


# ─── Internals ───────────────────────────────────────────────────────────

def _get_metal(name: str) -> _MetalInfo:
    if name not in REGISTRY:
        raise ValueError(
            f"Unknown metal '{name}'. Registered: {sorted(REGISTRY)}"
        )
    return REGISTRY[name]


def _make_bulk(info: _MetalInfo) -> Structure:
    """Build a pymatgen bulk Structure from registry info."""
    if info.lattice_type in ("bcc", "fcc"):
        a = info.lattice_constants["a"]
        lattice = Lattice.cubic(a)
    elif info.lattice_type == "hcp":
        a = info.lattice_constants["a"]
        c = info.lattice_constants["c"]
        lattice = Lattice.hexagonal(a, c)
    else:
        raise ValueError(f"Unknown lattice type: {info.lattice_type}")

    return Structure.from_spacegroup(
        info.space_group, lattice, [info.symbol], info.wyckoff
    )


def _parse_miller(s: str) -> tuple[int, ...]:
    """Parse miller index string.

    '110' -> (1, 1, 0)
    '0001' -> (0, 0, 0, 1) -> (0, 0, 1)  (HCP 4-to-3 index)
    '10-10' -> (1, 0, -1, 0) -> (1, 0, 0)
    """
    if len(s) <= 3:
        return tuple(int(c) for c in s)

    # HCP 4-index: parse characters handling negative digits
    parts: list[int] = []
    i = 0
    while i < len(s):
        if s[i] == "-":
            parts.append(int(s[i:i + 2]))
            i += 2
        else:
            parts.append(int(s[i]))
            i += 1

    # Drop the third index (i) — 4-index (h,k,i,l) -> 3-index (h,k,l)
    return (parts[0], parts[1], parts[3])


def _label_layers(slab: Atoms, n_layers: int):
    """Tag atoms so bottom layer = 1, top layer = n_layers."""
    zs = slab.positions[:, 2]
    unique_z = sorted(set(round(float(z), 3) for z in zs))
    for i, atom in enumerate(slab):
        z = round(float(atom.z), 3)
        try:
            layer = unique_z.index(z) + 1  # 1-indexed
        except ValueError:
            layer = 1
        slab[i].tag = int(layer)


def _inject_selective_dynamics(poscar: str, flags: list[str]) -> str:
    """Rewrite POSCAR to include selective dynamics flags."""
    lines = poscar.strip().split("\n")

    coord_idx = 0
    for i, line in enumerate(lines):
        if line.strip().upper() in ("CARTESIAN", "DIRECT"):
            coord_idx = i
            break

    if coord_idx == 0:
        return poscar

    result = lines[:coord_idx] + ["Selective dynamics"] + lines[coord_idx:]

    header_count = coord_idx + 2  # lines before atom coordinates
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


# ─── INCAR / KPOINTS / SLURM for slab calculations ────────────────────


def generate_incar_for_slab(
    metal: str, surface: str, overrides: dict | None = None
) -> str:
    """Generate INCAR content optimized for metal surface relaxation."""
    params = dict(VASP_DEFAULTS["surface"])
    if overrides:
        params.update(overrides)
    return render_incar(params, f"{metal}({surface}) surface relaxation")


def generate_surface_files(
    config: SlabConfig, slab: Atoms, xyz_str: str | None = None,
    functional: str = "PBE",
) -> dict[str, str]:
    """Bundle all VASP input files for a surface calculation.

    Returns: {filename: content} for INCAR, POSCAR, POTCAR, KPOINTS, run.slurm.
    """
    from app.services.potcar import generate_potcar

    result = get_poscar(slab, config, xyz_str)
    prefix = f"slab_{config.metal}{config.surface}"

    elements = list(result.elements)
    potcar = generate_potcar(elements, functional)
    incar = generate_incar_for_slab(config.metal, config.surface)
    kpoints = render_kpoints((6, 6, 1), "Monkhorst-Pack", "KSPACING surface mesh")
    jobname = f"{config.metal}{config.surface}_{''.join(f'{el}{c}' if c > 1 else el for el, c in zip(result.elements, result.counts))}"
    slurm = render_slurm(jobname, time="48:00:00")

    return {
        f"{prefix}_INCAR": incar,
        f"{prefix}_POSCAR": result.poscar,
        f"{prefix}_POTCAR": potcar,
        f"{prefix}_KPOINTS": kpoints,
        f"{prefix}_run.slurm": slurm,
    }
