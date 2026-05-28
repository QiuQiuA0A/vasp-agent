"""Shared VASP template rendering — INCAR, KPOINTS, SLURM.

Used by both molecule generation (vasp_input) and surface slab generation (surface).

SLURM defaults come from environment variables:
  VASP_SLURM_PARTITION, VASP_SLURM_NODES, VASP_SLURM_NTASKS,
  VASP_SLURM_WALLTIME, VASP_SLURM_MODULE
"""

from app.core.config import (
    SLURM_PARTITION, SLURM_NODES, SLURM_NTASKS_PER_NODE,
    SLURM_WALLTIME, SLURM_VASP_MODULE,
)


def render_incar(params: dict, label: str = "") -> str:
    """Render a dict of VASP INCAR parameters to string."""
    lines = [f"# INCAR{f' - {label}' if label else ''}"]
    for key, val in params.items():
        if isinstance(val, bool):
            lines.append(f"{key} = .{'TRUE.' if val else 'FALSE.'}")
        elif isinstance(val, float):
            lines.append(f"{key} = {val:.6g}")
        else:
            lines.append(f"{key} = {val}")
    lines.append("")
    return "\n".join(lines)


def render_kpoints(mesh: tuple[int, int, int] = (1, 1, 1),
                   style: str = "Gamma",
                   comment: str = "Automatic mesh") -> str:
    """Render Monkhorst-Pack KPOINTS file."""
    return (
        f"{comment}\n"
        "0\n"
        f"{style}\n"
        f"{mesh[0]}  {mesh[1]}  {mesh[2]}\n"
        "0  0  0\n"
    )


def render_kpoints_kspacing(kspacing: float = 0.5, comment: str = "KSPACING") -> str:
    """Render KPOINTS using KSPACING mode (modern VASP recommended approach)."""
    return f"{comment}\n0\nAuto\n{kspacing:.4f}\n"


def render_kpoints_band(kpoints: list[tuple[float, float, float, str]],
                         n_per_seg: int = 20,
                         comment: str = "Band structure") -> str:
    """Render line-mode KPOINTS for band structure calculations.

    Args:
        kpoints: list of (kx, ky, kz, label) high-symmetry points.
                 e.g. [(0,0,0,"Γ"), (0.5,0,0,"X"), (0.5,0.5,0,"M"), (0,0,0,"Γ")]
        n_per_seg: number of k-points per segment (ignored if 0).
    """
    labels = " ".join(p[3] for p in kpoints)
    n_segs = len(kpoints) - 1
    lines = [
        comment,
        f"{n_segs * n_per_seg + 1}",
        "Reciprocal",
    ]
    for i, (kx, ky, kz, label) in enumerate(kpoints):
        if i < n_segs:
            lines.append(f"  {kx:10.6f}  {ky:10.6f}  {kz:10.6f}  {n_per_seg}")
        else:
            lines.append(f"  {kx:10.6f}  {ky:10.6f}  {kz:10.6f}  0")
    lines.append(f"  {labels}")
    lines.append("")
    return "\n".join(lines)


# Predefined high-symmetry paths for common lattices
BAND_PATHS: dict[str, list[tuple[float, float, float, str]]] = {
    "fcc": [
        (0.000, 0.000, 0.000, "Γ"),
        (0.000, 0.500, 0.500, "X"),
        (0.250, 0.625, 0.625, "U"),
        (0.375, 0.750, 0.375, "K"),
        (0.000, 0.000, 0.000, "Γ"),
        (0.500, 0.500, 0.500, "L"),
        (0.500, 0.625, 0.375, "W"),
        (0.375, 0.750, 0.375, "K"),
    ],
    "bcc": [
        (0.000, 0.000, 0.000, "Γ"),
        (0.000, 0.000, 0.500, "H"),
        (0.250, 0.250, 0.750, "P"),
        (0.000, 0.000, 0.000, "Γ"),
        (0.500, 0.500, 0.500, "N"),
        (0.000, 0.500, 0.500, "X"),
        (0.500, 0.500, 0.500, "N"),
        (0.250, 0.250, 0.750, "P"),
    ],
    "hcp": [
        (0.000, 0.000, 0.000, "Γ"),
        (0.000, 0.000, 0.500, "A"),
        (0.333, 0.333, 0.500, "H"),
        (0.333, 0.333, 0.000, "K"),
        (0.000, 0.000, 0.000, "Γ"),
        (0.500, 0.000, 0.000, "M"),
        (0.333, 0.333, 0.500, "H"),
    ],
    "tetragonal": [
        (0.000, 0.000, 0.000, "Γ"),
        (0.500, 0.000, 0.000, "X"),
        (0.500, 0.500, 0.000, "M"),
        (0.000, 0.000, 0.000, "Γ"),
        (0.000, 0.000, 0.500, "Z"),
        (0.500, 0.000, 0.500, "R"),
        (0.500, 0.500, 0.500, "A"),
        (0.000, 0.000, 0.500, "Z"),
    ],
    "orthorhombic": [
        (0.000, 0.000, 0.000, "Γ"),
        (0.500, 0.000, 0.000, "X"),
        (0.500, 0.500, 0.000, "S"),
        (0.000, 0.500, 0.000, "Y"),
        (0.000, 0.000, 0.000, "Γ"),
        (0.000, 0.000, 0.500, "Z"),
        (0.500, 0.000, 0.500, "U"),
        (0.500, 0.500, 0.500, "R"),
        (0.000, 0.500, 0.500, "T"),
        (0.000, 0.000, 0.500, "Z"),
    ],
    "generic": [
        (0.000, 0.000, 0.000, "Γ"),
        (0.500, 0.000, 0.000, "X"),
        (0.500, 0.500, 0.000, "M"),
        (0.000, 0.500, 0.000, "Y"),
        (0.000, 0.000, 0.000, "Γ"),
        (0.000, 0.000, 0.500, "Z"),
    ],
}


def render_slurm(jobname: str, *,
                 nodes: int | None = None,
                 ntasks: int | None = None,
                 time: str | None = None,
                 partition: str | None = None,
                 vasp_module: str | None = None) -> str:
    """Render a SLURM submission script.

    All parameters optional — defaults from VASP_SLURM_* env vars.
    """
    n = nodes or SLURM_NODES
    nt = ntasks or SLURM_NTASKS_PER_NODE
    t = time or SLURM_WALLTIME
    p = partition or SLURM_PARTITION
    m = vasp_module or SLURM_VASP_MODULE
    return f"""#!/bin/bash
#SBATCH --job-name={jobname}
#SBATCH --nodes={n}
#SBATCH --ntasks-per-node={nt}
#SBATCH --time={t}
#SBATCH --partition={p}
#SBATCH --output={jobname}_%j.out
#SBATCH --error={jobname}_%j.err

module load {m} 2>/dev/null || echo "Adjust module name for your cluster"

mpirun -np $SLURM_NTASKS vasp_std
"""
