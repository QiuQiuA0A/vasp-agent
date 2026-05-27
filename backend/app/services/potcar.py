from pathlib import Path
from app.core.config import POTCAR_LIBRARY, POTCAR_FUNCTIONAL


POTCAR_MAP = {
    # Period 1
    "H": "H", "He": "He",
    # Period 2
    "Li": "Li_sv", "Be": "Be_sv", "B": "B", "C": "C", "N": "N",
    "O": "O", "F": "F", "Ne": "Ne",
    # Period 3
    "Na": "Na_pv", "Mg": "Mg_pv", "Al": "Al", "Si": "Si",
    "P": "P", "S": "S", "Cl": "Cl", "Ar": "Ar",
    # Period 4
    "K": "K_sv", "Ca": "Ca_sv", "Sc": "Sc_sv", "Ti": "Ti_sv",
    "V": "V_sv", "Cr": "Cr_pv", "Mn": "Mn_pv", "Fe": "Fe_pv",
    "Co": "Co", "Ni": "Ni_pv", "Cu": "Cu_pv", "Zn": "Zn",
    "Ga": "Ga_d", "Ge": "Ge_d", "As": "As", "Se": "Se",
    "Br": "Br", "Kr": "Kr",
    # Period 5
    "Rb": "Rb_sv", "Sr": "Sr_sv", "Y": "Y_sv", "Zr": "Zr_sv",
    "Nb": "Nb_sv", "Mo": "Mo_pv", "Tc": "Tc_pv", "Ru": "Ru_pv",
    "Rh": "Rh_pv", "Pd": "Pd", "Ag": "Ag", "Cd": "Cd",
    "In": "In_d", "Sn": "Sn_d", "Sb": "Sb", "Te": "Te",
    "I": "I", "Xe": "Xe",
    # Period 6
    "Cs": "Cs_sv", "Ba": "Ba_sv", "La": "La",
    "Ce": "Ce", "Pr": "Pr_3", "Nd": "Nd_3", "Pm": "Pm_3",
    "Sm": "Sm_3", "Eu": "Eu", "Gd": "Gd", "Tb": "Tb_3",
    "Dy": "Dy_3", "Ho": "Ho_3", "Er": "Er_3", "Tm": "Tm_3",
    "Yb": "Yb_2", "Lu": "Lu_3",
    "Hf": "Hf_pv", "Ta": "Ta_pv", "W": "W_pv", "Re": "Re_pv",
    "Os": "Os_pv", "Ir": "Ir", "Pt": "Pt", "Au": "Au",
    "Hg": "Hg", "Tl": "Tl_d", "Pb": "Pb_d", "Bi": "Bi_d",
    # Period 7
    "Po": "Po", "At": "At", "Rn": "Rn",
    "Fr": "Fr_sv", "Ra": "Ra_sv", "Ac": "Ac",
    "Th": "Th", "Pa": "Pa", "U": "U", "Np": "Np",
    "Pu": "Pu",
}


def potcar_path(element: str, functional: str | None = None) -> Path:
    """Get path to POTCAR for a given element symbol under functional subdir."""
    func = functional or POTCAR_FUNCTIONAL
    subfolder = POTCAR_MAP.get(element, element)
    return POTCAR_LIBRARY / func / subfolder / "POTCAR"


def assess_potcar_availability(elements: list[str],
                               functional: str | None = None) -> dict[str, bool]:
    """Check which elements have POTCAR files available."""
    func = functional or POTCAR_FUNCTIONAL
    return {el: potcar_path(el, func).exists() for el in elements}


def generate_potcar(elements: list[str], functional: str | None = None) -> str:
    """Concatenate POTCAR files for given elements in order."""
    func = functional or POTCAR_FUNCTIONAL
    parts = []
    for el in elements:
        path = potcar_path(el, func)
        if path.exists():
            parts.append(path.read_text())
        else:
            parts.append(
                f"# POTCAR for {el} not found at {path}\n"
                f"# Place the {func} POTCAR for {el} in {path.parent}\n"
            )
    return "\n".join(parts)
