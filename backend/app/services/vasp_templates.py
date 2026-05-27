"""Shared VASP template rendering — INCAR, KPOINTS, SLURM.

Used by both molecule generation (vasp_input) and surface slab generation (surface).
"""


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


def render_slurm(jobname: str, *,
                 nodes: int = 1,
                 ntasks: int = 32,
                 time: str = "24:00:00",
                 partition: str = "compute",
                 vasp_module: str = "vasp/6.4.3") -> str:
    """Render a SLURM submission script."""
    return f"""#!/bin/bash
#SBATCH --job-name={jobname}
#SBATCH --nodes={nodes}
#SBATCH --ntasks-per-node={ntasks}
#SBATCH --time={time}
#SBATCH --partition={partition}
#SBATCH --output={jobname}_%j.out
#SBATCH --error={jobname}_%j.err

module load {vasp_module} 2>/dev/null || echo "Adjust module name for your cluster"

mpirun -np $SLURM_NTASKS vasp_std
"""
