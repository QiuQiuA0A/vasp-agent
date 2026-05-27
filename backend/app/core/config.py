import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
POTCAR_LIBRARY = Path(os.environ.get(
    "VASP_POTCAR_LIBRARY",
    str(PROJECT_ROOT / "app" / "services" / "potcar" / "library"),
))
POTCAR_FUNCTIONAL = os.environ.get("VASP_POTCAR_FUNCTIONAL", "PBE")

# SLURM cluster defaults — override via environment variables
SLURM_PARTITION = os.environ.get("VASP_SLURM_PARTITION", "compute")
SLURM_NODES = int(os.environ.get("VASP_SLURM_NODES", "1"))
SLURM_NTASKS_PER_NODE = int(os.environ.get("VASP_SLURM_NTASKS", "32"))
SLURM_WALLTIME = os.environ.get("VASP_SLURM_WALLTIME", "24:00:00")
SLURM_VASP_MODULE = os.environ.get("VASP_SLURM_MODULE", "vasp/6.4.3")

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
    "frequency": {
        "IBRION": 5,
        "NSW": 1,
        "NFREE": 2,
        "POTIM": 0.015,
        "EDIFF": 1e-7,
        "PREC": "Accurate",
    },
    "dos": {
        "IBRION": -1,
        "NSW": 0,
        "EDIFF": 1e-6,
        "LORBIT": 11,
        "NEDOS": 2000,
        "ISMEAR": -5,
    },
    "band": {
        "IBRION": -1,
        "NSW": 0,
        "EDIFF": 1e-6,
        "LORBIT": 11,
        "NEDOS": 2000,
        "ICHARG": 11,
    },
    "work_function": {
        "IBRION": -1,
        "NSW": 0,
        "EDIFF": 1e-6,
        "LVHAR": True,
        "LVTOT": True,
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
