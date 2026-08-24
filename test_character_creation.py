"""
Harness di test: lancia SOLO la schermata di creazione personaggio,
per verificare visivamente tema + tabella armature + validazioni
prima di costruire il resto della finestra principale.

Uso:
    python -m test_character_creation
(richiede PySide6 installato nel tuo venv: pip install PySide6)
"""
import sys

from PySide6.QtWidgets import QApplication

from database.db_manager import get_connection, init_db, refresh_armors_catalog
from ui.theme import build_stylesheet
from ui.character_creation import CharacterCreationScreen
from core.version import APP_VERSION
from core.app_logger import get_logger

log = get_logger(__name__)


def main():
    log.info("Avvio test_character_creation — versione %s", APP_VERSION)

    conn = get_connection()
    init_db(conn)
    refresh_armors_catalog(conn)  # ricarica il catalogo dai CSV ad ogni avvio

    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet())

    screen = CharacterCreationScreen(conn)
    screen.setWindowTitle(f"Saint Seiya: Sacro Imperio — Test creazione personaggio [{APP_VERSION}]")
    screen.resize(720, 780)

    def on_created(knight_id: int):
        from core.character_factory import get_knight
        knight = get_knight(conn, knight_id)
        log.info("Personaggio creato: id=%d nome=%s armatura=%s",
                  knight_id, knight["raw_name"], knight["armor_name"])
        print(f"[TEST] Personaggio creato con id={knight_id}")
        print(knight)

    screen.character_created.connect(on_created)
    screen.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
