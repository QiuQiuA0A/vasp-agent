import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
POTCAR_LIBRARY = os.environ.get(
    "VASP_POTCAR_LIBRARY",
    str(PROJECT_ROOT / "potcar_library"),
)

# VASP defaults for different calculation types
VASP_DEFAULTS = {
    "optimization": {
        "IBRION": 2,
        "ISIF": 3,
        "NSW": 100,
        "EDIFF": 1e-5,
        "EDIFFG": -0.02,
    },
    "static": {
        "IBRION": -1,
        "NSW": 0,
        "EDIFF": 1e-6,
        "LORBIT": 11,
        "NEDOS": 1000,
    },
    "dipole": {
        "IBRION": -1,
        "NSW": 0,
        "EDIFF": 1e-6,
        "LDIPOL": True,
        "IDIPOL": 3,
    },
    "aimd": {
        "IBRION": 0,
        "ISIF": 2,
        "NSW": 5000,
        "POTIM": 1.0,
        "TEBEG": 300,
        "TEEND": 300,
        "SMASS": 0,
        "MDALGO": 2,
    },
}

# Common defaults applied to all calculation types
COMMON_DEFAULTS = {
    "ENCUT": 400,
    "PREC": "Normal",
    "ISMEAR": 0,
    "SIGMA": 0.05,
    "LREAL": "Auto",
    "ALGO": "Fast",
    "NPAR": 4,
    "LCHARG": True,
    "LWAVE": False,
}
