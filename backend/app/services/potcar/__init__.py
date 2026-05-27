"""POTCAR package — generation, library management, and data files."""

from app.services.potcar.potcar import (
    POTCAR_MAP,
    potcar_path,
    generate_potcar,
    assess_potcar_availability,
)

from app.services.potcar.manager import (
    library_stats,
    list_functionals,
    detect_element,
    import_potcar,
    remove_potcar,
    bulk_import,
)
