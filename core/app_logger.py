"""
Logging centralizzato dell'app.

Ogni avvio crea un file di log a sé (logs/session_AAAA-MM-GG_HH-MM-SS.log)
e, prima di crearlo, ripulisce i log più vecchi della soglia di
retention (default 24 ore) - così durante lo sviluppo ci accumuliamo
tutto quello che serve per capire un bug, senza che la cartella logs/
cresca all'infinito.

Uso in qualsiasi modulo:
    from core.app_logger import get_logger
    log = get_logger(__name__)
    log.info("Catalogo caricato: %d armature", n)
    log.error("Errore durante il refresh", exc_info=True)
"""
import logging
import time
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_RETENTION_HOURS = 24

_configured = False  # evita di riconfigurare gli handler ad ogni chiamata


def cleanup_old_logs(retention_hours: int = LOG_RETENTION_HOURS) -> int:
    """Cancella i file .log più vecchi della soglia. Restituisce quanti ne ha rimossi."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - retention_hours * 3600
    removed = 0
    for log_file in LOGS_DIR.glob("session_*.log"):
        if log_file.stat().st_mtime < cutoff:
            log_file.unlink()
            removed += 1
    return removed


def _configure_root_logger() -> None:
    global _configured
    if _configured:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    removed = cleanup_old_logs()

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = LOGS_DIR / f"session_{timestamp}.log"

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root = logging.getLogger("saint_seiya")
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    _configured = True
    root.info("=== Nuova sessione — log salvato in %s ===", log_file.name)
    if removed:
        root.info("Puliti %d file di log più vecchi di %dh", removed, LOG_RETENTION_HOURS)


def get_logger(module_name: str) -> logging.Logger:
    """Da chiamare come get_logger(__name__) in ogni modulo che vuole loggare."""
    _configure_root_logger()
    return logging.getLogger(f"saint_seiya.{module_name}")
