import re
from dataclasses import dataclass, field


@dataclass
class XdatcarFrame:
    """Single MD frame from XDATCAR."""

    index: int  # 1-based frame number
    positions: list[list[float]] = field(default_factory=list)  # (x, y, z) per atom


@dataclass
class XdatcarResult:
    """Parsed XDATCAR trajectory."""

    formula: str = ""
    lattice_constant: float = 1.0
    lattice: list[tuple[float, float, float]] | None = None
    elements: list[str] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)
    n_atoms: int = 0
    frames: list[XdatcarFrame] = field(default_factory=list)
    n_frames: int = 0

    @property
    def atoms_frame(self) -> list[dict]:
        """Return first-frame atoms with element labels for display."""
        if not self.frames or not self.frames[0].positions:
            return []
        atoms = []
        el_idx = 0
        el_remaining = self.counts[0] if self.counts else 0
        for pos in self.frames[0].positions:
            while el_remaining == 0 and el_idx + 1 < len(self.counts):
                el_idx += 1
                el_remaining = self.counts[el_idx]
            element = self.elements[el_idx] if el_idx < len(self.elements) else "?"
            atoms.append({"element": element, "x": pos[0], "y": pos[1], "z": pos[2]})
            el_remaining -= 1
        return atoms


def parse_xdatcar(content: str) -> XdatcarResult:
    """Parse XDATCAR file to extract MD trajectory frames.

    Returns frame count, per-frame atom positions, lattice info.
    """
    result = XdatcarResult()
    lines = content.strip().split("\n")
    if len(lines) < 8:
        return result

    result.formula = lines[0].strip()
    try:
        result.lattice_constant = float(lines[1].strip())
    except ValueError:
        pass

    # Parse lattice vectors (lines 2-4, 1-indexed: 3-5)
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

    # Element names and counts
    # Find the element/count lines — they're before "Direct" or "Cartesian"
    header_end = 0
    for i in range(max(5, len(lattice) + 2), min(len(lines), 30)):
        stripped = lines[i].strip()
        if stripped.startswith("Direct") or stripped.startswith("Cart"):
            header_end = i
            break

    if header_end >= 7:
        # Try lines[5] and lines[6] as element names and counts
        el_parts = lines[5].strip().split()
        count_parts = lines[6].strip().split() if header_end > 6 else []
        if el_parts and count_parts:
            all_alpha = all(not p[0].isdigit() for p in el_parts)
            all_num = all(p[0].isdigit() for p in count_parts)
            if all_alpha and all_num:
                result.elements = el_parts
                try:
                    result.counts = [int(c) for c in count_parts]
                    result.n_atoms = sum(result.counts)
                except ValueError:
                    pass

    # Parse frames
    frame_lines: list[str] = []
    for i in range(header_end, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        if re.match(r"Direct\s+configuration\s*=\s*(\d+)", stripped):
            # Start a new frame; save previous frame lines if any
            if frame_lines:
                _flush_frame(result, frame_lines)
                frame_lines = []
        else:
            frame_lines.append(lines[i])

    # Last frame
    if frame_lines:
        _flush_frame(result, frame_lines)

    result.n_frames = len(result.frames)
    return result


def _flush_frame(result: XdatcarResult, raw_lines: list[str]):
    """Parse accumulated lines into a frame."""
    if not raw_lines:
        return
    frame = XdatcarFrame(index=result.n_frames + 1)
    for line in raw_lines:
        parts = line.strip().split()
        if len(parts) >= 3:
            try:
                frame.positions.append([float(parts[0]), float(parts[1]), float(parts[2])])
            except ValueError:
                continue
    if frame.positions:
        result.frames.append(frame)
