import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


@dataclass
class VasprunResult:
    """Parsed results from vasprun.xml."""

    system: str = ""
    incar_params: dict[str, str] = field(default_factory=dict)

    energies: list[dict] = field(default_factory=list)  # per ionic step
    forces: list[list[list[float]]] = field(default_factory=list)  # per ionic step
    stress: list[list[list[float]]] = field(default_factory=list)

    eigenvalues: list[dict] = field(default_factory=list)
    fermi_from_dos: float | None = None
    dos_total: list[dict] = field(default_factory=list)
    dos_partial: list[dict] = field(default_factory=list)

    homo: float | None = None
    lumo: float | None = None
    gap: float | None = None

    final_lattice: list[tuple[float, float, float]] | None = None
    final_positions: list[dict] = field(default_factory=list)

    dielectric_data: dict | None = None

    n_ionic_steps: int = 0
    warnings: list[str] = field(default_factory=list)


def parse_vasprun(content: str) -> VasprunResult:
    """Parse a vasprun.xml file using iterative XML parsing with start+end events."""
    result = VasprunResult()
    stream = io.StringIO(content)
    ctx: dict = {
        "calc_idx": -1,
        "bag": None,  # current data-bag: "energy" | "forces" | "stress" | "eigen" | "dos_total" | "dos_partial" | "lattice" | "positions"
        "dos_partial_ion": 1,
        "dos_partial_spin": 1,
        "kpt_index": 0,
        "dielectric_kind": None,  # "imag" or "real"
    }

    try:
        for event, elem in ET.iterparse(stream, events=("start", "end")):
            tag = _local_tag(elem.tag)
            if event == "start":
                _on_start(tag, elem, ctx, result)
            else:
                _on_end(tag, elem, ctx, result)
                elem.clear()
    except ET.ParseError as e:
        result.warnings.append(f"XML 解析错误: {e}")

    _compute_homo_lumo(result)
    return result


def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


# ── Start events: set the data-collecting mode ─────────────────────────


def _on_start(tag: str, elem: ET.Element, ctx: dict, result: VasprunResult):
    if tag == "calculation":
        ctx["calc_idx"] += 1
        result.n_ionic_steps = ctx["calc_idx"] + 1
        _grow_lists(result, ctx["calc_idx"])

    elif tag == "energy":
        ctx["bag"] = "energy"

    elif tag == "varray":
        name = elem.get("name", "")
        if name == "forces":
            ctx["bag"] = "forces"
        elif name == "stress":
            ctx["bag"] = "stress"
        elif name == "basis":
            ctx["bag"] = "lattice"
        elif name == "positions":
            ctx["bag"] = "positions"

    elif tag == "eigenvalues":
        ctx["bag"] = "eigen"
        ctx["kpt_index"] = 0

    elif tag == "dos":
        ctx["bag"] = "dos"
        ctx["dos_partial_ion"] = 1
        ctx["dos_partial_spin"] = 1

    elif tag == "total":
        if ctx["bag"] == "dos":
            ctx["bag"] = "dos_total"

    elif tag == "partial":
        if ctx["bag"] == "dos":
            ctx["bag"] = "dos_partial"

    elif tag == "dielectricfunction":
        ctx["bag"] = "dielectric"
        ctx["dielectric_kind"] = None

    elif tag == "imag":
        if ctx["bag"] == "dielectric":
            ctx["dielectric_kind"] = "imag"

    elif tag == "real":
        if ctx["bag"] == "dielectric":
            ctx["dielectric_kind"] = "real"

    elif tag == "structure":
        if elem.get("name") == "finalpos":
            ctx["bag"] = "structure"

    elif tag == "crystal":
        if ctx["bag"] == "structure":
            ctx["bag"] = "lattice"

    elif tag == "set":
        _on_set_start(elem, ctx)


def _on_set_start(elem: ET.Element, ctx: dict):
    comment = elem.get("comment", "")

    # Eigenvalues: track k-point / spin nesting
    if ctx["bag"] == "eigen":
        if "spin" in comment:
            pass  # spin index increments within a k-point set
        else:
            ctx["kpt_index"] += 1

    # DOS partial: track ion & spin
    if ctx["bag"] == "dos_partial":
        m_ion = re.search(r"ion\s+(\d+)", comment)
        m_spin = re.search(r"spin\s+(\d+)", comment)
        if m_ion:
            ctx["dos_partial_ion"] = int(m_ion.group(1))
        if m_spin:
            ctx["dos_partial_spin"] = int(m_spin.group(1))


# ── End events: extract leaf data based on current bag ─────────────────


def _on_end(tag: str, elem: ET.Element, ctx: dict, result: VasprunResult):
    # Exit sub-bags — pop back to parent context
    if tag in ("energy", "varray", "eigenvalues", "structure", "crystal"):
        ctx["bag"] = None
    elif tag in ("total", "partial"):
        ctx["bag"] = "dos"  # pop back to parent <dos> context
    elif tag in ("imag", "real"):
        ctx["bag"] = "dielectric"  # pop back to parent <dielectricfunction>
    elif tag == "dos":
        ctx["bag"] = None
    elif tag == "dielectricfunction":
        ctx["bag"] = None
        ctx["dielectric_kind"] = None

    # Dispatch leaf extraction based on tag
    if tag == "i":
        _extract_i(elem, ctx, result)
    elif tag == "v":
        _extract_v(elem, ctx, result)
    elif tag == "r":
        _extract_r(elem, ctx, result)


def _grow_lists(result: VasprunResult, idx: int):
    while len(result.energies) <= idx:
        result.energies.append({})
    while len(result.forces) <= idx:
        result.forces.append([])
    while len(result.stress) <= idx:
        result.stress.append([])


# ── Text extractors ────────────────────────────────────────────────────


def _extract_i(elem: ET.Element, ctx: dict, result: VasprunResult):
    name = elem.get("name", "")
    text = (elem.text or "").strip()

    if ctx["bag"] == "energy" and name:
        ci = ctx["calc_idx"]
        if ci >= 0 and ci < len(result.energies):
            result.energies[ci][name] = text

    elif ctx["bag"] is None and name:
        result.incar_params[name] = text
        if name == "SYSTEM":
            result.system = text

    elif ctx["bag"] in ("dos", "dos_total") and name == "efermi":
        try:
            result.fermi_from_dos = float(text)
        except ValueError:
            pass


def _extract_v(elem: ET.Element, ctx: dict, result: VasprunResult):
    text = (elem.text or "").strip()
    parts = text.split()
    if not parts:
        return
    try:
        vals = [float(p) for p in parts]
    except ValueError:
        return

    ci = ctx["calc_idx"]

    if ctx["bag"] == "forces" and 0 <= ci < len(result.forces):
        result.forces[ci].append(vals)

    elif ctx["bag"] == "stress" and 0 <= ci < len(result.stress):
        result.stress[ci].append(vals)

    elif ctx["bag"] == "lattice":
        if len(vals) == 3:
            if result.final_lattice is None:
                result.final_lattice = []
            result.final_lattice.append((vals[0], vals[1], vals[2]))

    elif ctx["bag"] == "positions" and len(vals) == 3:
        result.final_positions.append({"x": vals[0], "y": vals[1], "z": vals[2]})


def _extract_r(elem: ET.Element, ctx: dict, result: VasprunResult):
    text = (elem.text or "").strip()
    parts = text.split()
    if not parts:
        return
    try:
        vals = [float(p) for p in parts]
    except ValueError:
        return

    if ctx["bag"] == "eigen" and len(vals) >= 2:
        result.eigenvalues.append({
            "kpt": ctx["kpt_index"],
            "energy": vals[0],
            "occupation": vals[1],
        })

    elif ctx["bag"] == "dos_total" and len(vals) >= 2:
        result.dos_total.append({
            "energy": vals[0],
            "dos": vals[1],
            "integrated": vals[2] if len(vals) >= 3 else 0.0,
        })

    elif ctx["bag"] == "dos_partial":
        result.dos_partial.append({
            "ion": ctx["dos_partial_ion"],
            "spin": ctx["dos_partial_spin"],
            "energy": vals[0],
            "s": vals[1] if len(vals) > 1 else 0.0,
            "p": vals[2] if len(vals) > 2 else 0.0,
            "d": vals[3] if len(vals) > 3 else 0.0,
        })

    elif ctx["bag"] == "dielectric" and ctx["dielectric_kind"]:
        kind = ctx["dielectric_kind"]
        if result.dielectric_data is None:
            result.dielectric_data = {}
        if kind not in result.dielectric_data:
            result.dielectric_data[kind] = []
        result.dielectric_data[kind].append(vals)


# ── HOMO/LUMO from eigenvalues ─────────────────────────────────────────


def _compute_homo_lumo(result: VasprunResult):
    if not result.eigenvalues:
        return
    homo_val = None
    lumo_val = None
    for ev in sorted(result.eigenvalues, key=lambda x: x["energy"]):
        if ev["occupation"] > 0.1:
            homo_val = ev["energy"]
        elif lumo_val is None and ev["occupation"] < 0.1:
            lumo_val = ev["energy"]
    result.homo = homo_val
    result.lumo = lumo_val
    if homo_val is not None and lumo_val is not None:
        result.gap = lumo_val - homo_val
