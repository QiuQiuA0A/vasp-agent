def parse_eigenval(content: str) -> dict:
    """Parse EIGENVAL file to extract band energies and HOMO-LUMO gap."""
    lines = content.strip().split("\n")
    if len(lines) < 6:
        return {"error": "EIGENVAL file too short"}

    # Find the header line with (electrons, kpoints, nbands)
    # Skip initial comment lines — look for 3 integers/floats
    header_idx = None
    n_electrons = nkpoints = nbands = 0
    for i in range(min(len(lines), 10)):
        parts = lines[i].strip().split()
        if len(parts) >= 3:
            try:
                n_electrons = int(float(parts[0]))
                nkpoints = int(parts[1])
                nbands = int(parts[2])
                if nkpoints > 0 and nbands > 0:
                    header_idx = i
                    break
            except (ValueError, IndexError):
                continue

    if header_idx is None:
        return {"error": "Cannot find EIGENVAL header line"}

    eigenvalues = []
    idx = header_idx + 1
    kpt_count = 0

    while idx < len(lines) and kpt_count < nkpoints:
        # Skip blank lines and k-point coordinate lines
        line = lines[idx].strip()
        idx += 1

        # Skip empty lines
        if not line:
            continue

        parts = line.split()
        # Check if this is a k-point coordinate line (4 values, with exponents)
        if len(parts) == 4:
            try:
                # K-point weight is typically 0.25, 0.5 etc
                float(parts[0])
                # Skip this and the next (usually a blank or kpt line)
                continue
            except ValueError:
                pass

        # Try parsing as eigenvalue line
        if len(parts) >= 3:
            try:
                band_idx = int(parts[0])
                energy = float(parts[1])
                occupation = float(parts[2])

                eigenvalues.append({
                    "kpt": kpt_count + 1,
                    "band": band_idx,
                    "energy": energy,
                    "occupation": occupation,
                })

                if band_idx == nbands:
                    kpt_count += 1
            except (ValueError, IndexError):
                continue

    occupied = [e for e in eigenvalues if e["occupation"] > 0.1]
    unoccupied = [e for e in eigenvalues if e["occupation"] <= 0.1]

    homo = max(e["energy"] for e in occupied) if occupied else None
    lumo = min(e["energy"] for e in unoccupied) if unoccupied else None
    gap = (lumo - homo) if (homo is not None and lumo is not None) else None

    return {
        "nbands": nbands,
        "nkpoints": nkpoints,
        "n_electrons": n_electrons,
        "homo_energy": homo,
        "lumo_energy": lumo,
        "gap": gap,
        "eigenvalues": eigenvalues[:20],  # First 20 for preview
        "total_eigenvalues": len(eigenvalues),
    }
