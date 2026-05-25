import re
from dataclasses import dataclass, field


@dataclass
class ScfStep:
    """Single SCF (electronic) step within one ionic step."""

    step: int
    energy: float  # current total energy (eV)
    dE: float  # energy change from previous step (eV)
    dE_avg: float | None = None  # running average energy change (eV)
    free_energy: float | None = None  # F = E - TS (eV)


@dataclass
class IonicStep:
    """One ionic relaxation step with its SCF history."""

    index: int  # ionic step number (1-based)
    scf_steps: list[ScfStep] = field(default_factory=list)
    converged: bool = False

    @property
    def n_scf(self) -> int:
        return len(self.scf_steps)

    @property
    def final_energy(self) -> float | None:
        if self.scf_steps:
            return self.scf_steps[-1].energy
        return None

    @property
    def final_dE(self) -> float | None:
        if self.scf_steps:
            return self.scf_steps[-1].dE
        return None


@dataclass
class OszicarResult:
    """Parsed OSZICAR with convergence diagnostics."""

    ionic_steps: list[IonicStep] = field(default_factory=list)
    total_ionic_steps: int = 0

    # Diagnostics (in plain Chinese for non-expert users)
    status: str = "ok"  # ok | warning | error
    diagnostics: list[str] = field(default_factory=list)

    @property
    def total_scf_steps(self) -> int:
        return sum(s.n_scf for s in self.ionic_steps)

    @property
    def final_energy(self) -> float | None:
        if self.ionic_steps:
            return self.ionic_steps[-1].final_energy
        return None


# ── Main parser ────────────────────────────────────────────────────────


def parse_oszicar(content: str) -> OszicarResult:
    """Parse an OSZICAR file and run convergence diagnostics."""
    result = OszicarResult()
    lines = content.strip().split("\n")

    current_ionic: IonicStep | None = None
    ionic_idx = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Separator between ionic steps
        if stripped.startswith("-") and len(stripped) >= 10 and set(stripped[:10]) <= {"-"}:
            current_ionic = None
            continue

        # Try matching an SCF step line
        scf = _parse_scf_line(stripped)
        if scf is None:
            continue

        if current_ionic is None:
            ionic_idx += 1
            current_ionic = IonicStep(index=ionic_idx)
            result.ionic_steps.append(current_ionic)

        current_ionic.scf_steps.append(scf)

    result.total_ionic_steps = len(result.ionic_steps)
    _run_diagnostics(result)
    return result


# ── SCF line parsing ───────────────────────────────────────────────────


def _parse_scf_line(line: str) -> ScfStep | None:
    """Parse one line like: 'DAV:   6    -0.144075E+01   -0.698E-09   -0.391E-10   472   0.158E-04'

    Returns None if the line does not look like an SCF step.
    """
    # Must start with a known algorithm tag
    if not re.match(r"^(DAV|RMM|CG|KS|QP)\s*:", line):
        return None

    # Remove the algorithm prefix
    body = re.sub(r"^(DAV|RMM|CG|KS|QP)\s*:", "", line).strip()
    parts = body.split()
    if len(parts) < 3:
        return None

    # Parts: [step] [energy] [dE ...] (some versions have [F] free energy before energy)
    try:
        step = int(parts[0])
    except ValueError:
        return None

    # Detect format:
    # Format A:  N  F  E0  dE  dE(avg)  ncg  dE(chg)   — 7 fields
    # Format B:  N  E0  dE  dE(avg)  ncg  dE(chg)      — 6 fields
    # Format C:  N  E0  dE  dE(avg)                     — 3-4 fields
    # In Format A, parts[1] and parts[2] are both energy-like.
    # Heuristic: if parts[2] looks like an energy number and parts[1] also does,
    # then parts[1] = F (free energy), parts[2] = E0.

    try:
        if len(parts) >= 4:
            # Check if parts[1] and parts[2] are both energy floats
            v1 = float(re.sub(r"[Dd]", "E", parts[1]))
            v2 = float(re.sub(r"[Dd]", "E", parts[2]))
            # If v2 is in a reasonable range for an energy and parts[3] is dE,
            # we likely have format A: N F E0 dE ...
            v3 = float(re.sub(r"[Dd]", "E", parts[3]))
            # In format A, v3 (dE) is much smaller than |v2| (energy).
            # In format B, v3 is dE_avg.
            if abs(v2) > abs(v3) * 100:
                # Format A
                free_energy = v1
                energy = v2
                dE = v3
                dE_avg = None
                if len(parts) >= 5:
                    dE_avg = float(re.sub(r"[Dd]", "E", parts[4]))
                return ScfStep(step=step, energy=energy, dE=dE, dE_avg=dE_avg, free_energy=free_energy)
            else:
                # Format B/C
                energy = v1
                dE = v2
                dE_avg = v3
                return ScfStep(step=step, energy=energy, dE=dE, dE_avg=dE_avg)
        else:
            # Minimal: N E0 dE
            energy = float(re.sub(r"[Dd]", "E", parts[1]))
            dE = float(re.sub(r"[Dd]", "E", parts[2]))
            return ScfStep(step=step, energy=energy, dE=dE)
    except (ValueError, IndexError):
        return None

    return None


# ── Diagnostics engine ─────────────────────────────────────────────────


def _run_diagnostics(result: OszicarResult):
    if not result.ionic_steps:
        result.diagnostics.append("OSZICAR 中没有找到离子步数据")
        result.status = "error"
        return

    # 1. Check SCF convergence for each ionic step
    max_scf_warn = 40
    max_scf_error = 80

    for ionic in result.ionic_steps:
        if ionic.n_scf >= max_scf_error:
            result.diagnostics.append(
                f"第 {ionic.index} 个离子步: SCF 步数 = {ionic.n_scf} (严重偏高，可能未收敛或体系有问题)"
            )
            result.status = "error"
        elif ionic.n_scf >= max_scf_warn:
            result.diagnostics.append(
                f"第 {ionic.index} 个离子步: SCF 步数 = {ionic.n_scf} (偏高，收敛较慢)"
            )
            if result.status == "ok":
                result.status = "warning"

    # 2. Check final dE — is SCF tight enough?
    for ionic in result.ionic_steps:
        if ionic.final_dE is not None and abs(ionic.final_dE) > 1e-3:
            result.diagnostics.append(
                f"第 {ionic.index} 个离子步: 最终 dE = {ionic.final_dE:.2e} eV (> 1e-3，可能未达到预期收敛精度)"
            )
            if result.status == "ok":
                result.status = "warning"

    # 3. Energy drift over ionic steps
    if len(result.ionic_steps) >= 2:
        energies = [s.final_energy for s in result.ionic_steps if s.final_energy is not None]
        if len(energies) >= 2:
            first, last = energies[0], energies[-1]
            drift = last - first
            if drift > 1.0:
                result.diagnostics.append(
                    f"能量显著上升 +{drift:.2f} eV（从 {first:.4f} 到 {last:.4f}），结构可能不稳定"
                )
                result.status = "error"
            elif drift > 0.1:
                result.diagnostics.append(
                    f"能量轻微上升 +{drift:.3f} eV，检查是否接近极小值"
                )
                if result.status == "ok":
                    result.status = "warning"

    # 4. Oscillation detection
    for ionic in result.ionic_steps:
        if ionic.n_scf < 4:
            continue
        energies = [s.energy for s in ionic.scf_steps]
        signs = 0
        for i in range(2, len(energies)):
            d1 = energies[i - 1] - energies[i - 2]
            d2 = energies[i] - energies[i - 1]
            if d1 * d2 < 0:
                signs += 1
        osc_ratio = signs / (len(energies) - 2)
        if osc_ratio > 0.4:
            result.diagnostics.append(
                f"第 {ionic.index} 个离子步: 能量震荡明显 ({signs}/{len(energies)-2} 次符号翻转)，建议降低混合参数或增大 SIGMA"
            )
            if result.status == "ok":
                result.status = "warning"

    # 5. Summary
    if result.status == "ok":
        result.diagnostics.insert(
            0,
            f"共 {result.total_ionic_steps} 个离子步，{result.total_scf_steps} 次 SCF 迭代，计算正常。最终能量 = {result.final_energy:.6f} eV"
            if result.final_energy is not None
            else f"共 {result.total_ionic_steps} 个离子步，{result.total_scf_steps} 次 SCF 迭代，计算正常。",
        )
