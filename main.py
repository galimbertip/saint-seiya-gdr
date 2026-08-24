"""
Entry point dell'app.

Flusso di navigazione (QStackedWidget con 3 pagine):
  StartScreen ──continua──────────────► CharacterSheetScreen
      │                                        │
      └──nuova partita──► CharacterCreationScreen ──creato──┘
                                                     (torna a StartScreen col tasto ◄ Menu)

A differenza della prima versione di main.py, l'avvio non sceglie più
in automatico l'ultimo personaggio: mostra sempre il menu iniziale e
lascia scegliere all'utente, con l'elenco di tutte le partite salvate
(oggi in pratica quasi sempre una sola, ma la struttura regge già più
personaggi in futuro).
"""
import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from database.db_manager import get_connection, init_db, refresh_armors_catalog
from core.version import APP_VERSION
from core.app_logger import get_logger
from ui.theme import build_stylesheet
from ui.start_screen import StartScreen
from ui.character_creation import CharacterCreationScreen
from ui.game_screen import GameScreen

log = get_logger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn

        self.setWindowTitle(f"Saint Seiya: Sacro Imperio [{APP_VERSION}]")
        self.resize(760, 820)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.start_screen = StartScreen(self.conn)
        self.start_screen.continue_requested.connect(self._show_sheet)
        self.start_screen.new_game_requested.connect(self._show_creation)
        self.start_screen.exit_requested.connect(self._exit_app)
        self.stack.addWidget(self.start_screen)

        self.creation_screen = CharacterCreationScreen(self.conn)
        self.creation_screen.character_created.connect(self._on_character_created)
        self.stack.addWidget(self.creation_screen)

        self.sheet_screen: GameScreen | None = None

        self.stack.setCurrentWidget(self.start_screen)

    def _show_creation(self) -> None:
        log.info("Utente ha scelto: Nuova Partita")
        self.stack.setCurrentWidget(self.creation_screen)

    def _on_character_created(self, knight_id: int) -> None:
        log.info("Personaggio creato dalla UI: id=%d", knight_id)
        self._show_sheet(knight_id)

    def _show_sheet(self, knight_id: int) -> None:
        log.info("Apro schermata di gioco: id=%d", knight_id)
        if self.sheet_screen is not None:
            self.stack.removeWidget(self.sheet_screen)
            self.sheet_screen.deleteLater()

        self.sheet_screen = GameScreen(self.conn, knight_id)
        self.sheet_screen.back_to_menu_requested.connect(self._show_start)
        self.sheet_screen.exit_requested.connect(self._exit_app)
        self.stack.addWidget(self.sheet_screen)
        self.stack.setCurrentWidget(self.sheet_screen)

    def _exit_app(self) -> None:
        log.info("Uscita richiesta dall'utente (i dati sono già tutti salvati su DB).")
        self.close()

    def _show_start(self) -> None:
        log.info("Ritorno al menu iniziale")
        self.start_screen.refresh()  # rilegge l'elenco, utile se nel frattempo è stata creata una partita
        self.stack.setCurrentWidget(self.start_screen)


def main():
    log.info("Avvio applicazione — versione %s", APP_VERSION)

    conn = get_connection()
    init_db(conn)
    refresh_armors_catalog(conn)

    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet())

    window = MainWindow(conn)
    window.show()

    exit_code = app.exec()
    log.info("Applicazione chiusa (exit code %d)", exit_code)
    conn.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
