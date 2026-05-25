import re
from dataclasses import dataclass, field


@dataclass
class VASPResult:
    """Parsed results from a VASP calculation."""

    # Convergence
    converged: bool = False
    n_scf_steps: int = 0
    n_ionic_steps: int = 0

    # Energies (eV)
    total_energy: float | None = None
    energy_without_entropy: float | None = None
    fermi_energy: float | None = None

    # Forces (eV/Ang)
    max_force: float | None = None
    forces: list[tuple[str, float, float, float]] = field(default_factory=list)

    # Stress (kB)
    stress: list[float] | None = None

    # Dipole moment (e*Ang)
    dipole_moment: tuple[float, float, float] | None = None
    dipole_total: float | None = None

    # HOMO/LUMO from eigenvalues
    homo: float | None = None
    lumo: float | None = None
    gap: float | None = None

    # Lattice (final)
    lattice: list[tuple[float, float, float]] | None = None

    # Warnings
    warnings: list[str] = field(default_factory=list)


def parse_outcar(content: str) -> VASPResult:
    """Parse an OUTCAR file and extract key results."""
    result = VASPResult()

    _parse_energies(content, result)
    _parse_convergence(content, result)
    _parse_forces(content, result)
    _parse_dipole(content, result)
    _parse_eigenvalues(content, result)
    _parse_lattice(content, result)
    _parse_steps(content, result)
    _parse_warnings(content, result)

    return result


def _parse_energies(content: str, result: VASPResult):
    # Total energy: "FREE ENERGIE OF THE ION-ELECTRON SYSTEM"
    # or the newer "free  energy   TOTEN  ="
    for pattern in [
        r"FREE ENERGIE OF THE ION-ELECTRON SYSTEM\s*\n\s*[-=]+\s*\n.*?\n\s*free\s+energy\s+TOTEN\s*=\s*([-\d.]+)",
        r"free\s+energy\s+TOTEN\s*=\s*([-\d.]+)",
        r"energy\s+without\s+entropy\s*=\s*([-\d.]+)",
        r"energy\(sigma->0\)\s*=\s*([-\d.]+)",
    ]:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            result.total_energy = float(matches[-1])
            break

    # Energy without entropy
    m = re.search(r"energy\s+without\s+entropy\s*=\s*([-\d.]+)", content, re.IGNORECASE)
    if m:
        result.energy_without_entropy = float(m.group(1))

    # Fermi energy
    m = re.search(r"E-fermi\s*:\s*([-\d.]+)", content)
    if m:
        result.fermi_energy = float(m.group(1))


def _parse_convergence(content: str, result: VASPResult):
    if "reached required accuracy" in content:
        result.converged = True


def _parse_forces(content: str, result: VASPResult):
    """Parse final forces from TOTAL-FORCE section (last occurrence)."""
    blocks = list(re.finditer(
        r"POSITION\s+TOTAL-FORCE\s*\(eV/Angst\)\s*\n\s*-+\s*\n((?:[^\n]*\n)*?)(?=\s*\n|\Z)",
        content
    ))
    if not blocks:
        return

    last = blocks[-1].group(1)
    forces = []
    max_f = 0.0

    for line in last.strip().split("\n"):
        parts = line.strip().split()
        if len(parts) == 6:
            try:
                float(parts[0]); float(parts[1]); float(parts[2])
                fx, fy, fz = float(parts[3]), float(parts[4]), float(parts[5])
                mag = (fx * fx + fy * fy + fz * fz) ** 0.5
                max_f = max(max_f, mag)
                forces.append((parts[0], fx, fy, fz))
            except ValueError:
                continue

    if forces:
        result.forces = forces
        result.max_force = max_f


def _parse_dipole(content: str, result: VASPResult):
    # Try multiple patterns for different VASP versions
    patterns = [
        # "Dipole moment [e*Ang]: x y z" — single-line format (VASP 6.x)
        r"[Dd]ipole\s+moment\s*\[e\*Ang\]\s*:\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)",
        # "Dipole moment [e*Ang] x y z" (older VASP)
        r"[Dd]ipole\s+moment\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)",
        # "Dipolmoment [e*Ang]" — German locale, multi-line
        r"[Dd]ipolmoment\s*\[e\*Ang\].*?\n.*?\n\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)",
    ]
    for pat in patterns:
        m = re.search(pat, content, re.DOTALL)
        if m:
            dx, dy, dz = float(m.group(1)), float(m.group(2)), float(m.group(3))
            result.dipole_moment = (dx, dy, dz)
            result.dipole_total = (dx * dx + dy * dy + dz * dz) ** 0.5
            break


def _parse_eigenvalues(content: str, result: VASPResult):
    """Extract HOMO/LUMO from the eigenvalues section in OUTCAR."""
    blocks = list(re.finditer(
        r"band No\.\s+band energies\s+occupation\s*\n((?:[^\n]*\n)*?)(?=\s*\n|\Z)",
        content
    ))
    if not blocks:
        return

    eigenvalues = []
    occupations = []
    target_block = blocks[-1] if blocks else None

    if target_block:
        for line in target_block.group(1).strip().split("\n"):
            parts = line.strip().split()
            if len(parts) == 3:
                try:
                    int(parts[0])
                    eig = float(parts[1])
                    occ = float(parts[2])
                    eigenvalues.append(eig)
                    occupations.append(occ)
                except ValueError:
                    continue

    if not eigenvalues:
        return

    homo_val = None
    lumo_val = None
    for eig, occ in zip(eigenvalues, occupations):
        if occ > 0.1:
            homo_val = eig
        elif lumo_val is None and occ < 0.1:
            lumo_val = eig

    if homo_val is not None:
        result.homo = homo_val
    if lumo_val is not None:
        result.lumo = lumo_val
    if result.homo is not None and result.lumo is not None:
        result.gap = result.lumo - result.homo


def _parse_lattice(content: str, result: VASPResult):
    """Extract final lattice vectors."""
    # Find the last occurrence of direct lattice vectors
    matches = list(re.finditer(
        r"direct lattice vectors\s+reciprocal lattice vectors\s*\n"
        r"\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+.*?\n"
        r"\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+.*?\n"
        r"\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)",
        content
    ))
    if matches:
        m = matches[-1]
        result.lattice = [
            (float(m.group(1)), float(m.group(2)), float(m.group(3))),
            (float(m.group(4)), float(m.group(5)), float(m.group(6))),
            (float(m.group(7)), float(m.group(8)), float(m.group(9))),
        ]


def _parse_steps(content: str, result: VASPResult):
    """Count SCF and ionic steps."""
    result.n_scf_steps = len(re.findall(r"DAV:\s+\d+", content))
    result.n_ionic_steps = len(re.findall(r"FREE ENERGIE OF THE ION-ELECTRON SYSTEM", content))
    if result.n_ionic_steps == 0:
        result.n_ionic_steps = len(re.findall(r"free\s+energy\s+TOTEN", content))


def _parse_warnings(content: str, result: VASPResult):
    """Collect warnings from OUTCAR."""
    for pattern, msg in [
        (r"WARNING.*?not enough vacuum", "真空层可能不足"),
        (r"WARNING.*?DIMER", "Dimer 计算相关警告"),
        (r"The distance between some ions is very small", "原子间距离过小"),
        (r"aliasing error", "FFT 混叠误差"),
    ]:
        if re.search(pattern, content, re.IGNORECASE):
            result.warnings.append(msg)
    if not result.converged:
        result.warnings.append("计算未收敛 — 请检查 NSW/EDIFF 设置或初始结构")
