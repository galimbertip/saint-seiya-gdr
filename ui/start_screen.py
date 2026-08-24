"""
Schermata iniziale (menu). Sostituisce l'avvio "automatico" che avevo
messo in main.py: invece di caricare in silenzio l'ultimo personaggio,
chiede esplicitamente cosa fare - e, se ci sono più partite salvate
(previsto per il futuro, oggi in pratica ce n'è quasi sempre una),
le elenca tutte invece di scegliere per te.
"""
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QListWidget, QListWidgetItem, QAbstractItemView, QMessageBox,
)

from core.character_factory import list_knights, delete_knight
from core.version import APP_VERSION


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 16)
    layout.setSpacing(10)
    if title:
        lbl = QLabel(title)
        lbl.setObjectName("sectionTitle")
        layout.addWidget(lbl)
    return frame, layout


class StartScreen(QWidget):
    """Emette continue_requested(knight_id) se l'utente sceglie una
    partita salvata, oppure new_game_requested() se vuole iniziarne una nuova."""
    continue_requested = Signal(int)
    new_game_requested = Signal()
    exit_requested = Signal()

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 40, 24, 24)
        root.setSpacing(18)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("SAINT SEIYA")
        title.setObjectName("headerTitle")
        title.setStyleSheet("font-size: 30px; font-weight: 700;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        subtitle = QLabel(f"Sacro Imperio  ·  {APP_VERSION}")
        subtitle.setObjectName("hint")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(subtitle)

        root.addSpacing(10)

        # --- Card: partite salvate ---
        self.saves_card, self.saves_layout = _card("Partite salvate")
        self.saves_list = QListWidget()
        self.saves_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.saves_list.setMinimumHeight(180)
        self.saves_list.itemDoubleClicked.connect(self._on_save_double_clicked)
        self.saves_layout.addWidget(self.saves_list)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.continue_button = QPushButton("Continua")
        self.continue_button.clicked.connect(self._on_continue_clicked)
        action_row.addWidget(self.continue_button, stretch=1)

        self.delete_button = QPushButton("Elimina")
        self.delete_button.setObjectName("secondary")
        self.delete_button.clicked.connect(self._on_delete_clicked)
        action_row.addWidget(self.delete_button)

        self.saves_layout.addLayout(action_row)

        root.addWidget(self.saves_card)

        # --- Nuova partita ---
        self.new_game_button = QPushButton("+ Nuova Partita")
        self.new_game_button.setObjectName("secondary")
        self.new_game_button.clicked.connect(self.new_game_requested.emit)
        root.addWidget(self.new_game_button)

        root.addStretch()

        self.exit_button = QPushButton("Esci")
        self.exit_button.setObjectName("secondary")
        self.exit_button.clicked.connect(self.exit_requested.emit)
        root.addWidget(self.exit_button)

        self.refresh()

    def refresh(self) -> None:
        """Ricarica l'elenco delle partite salvate. Da richiamare ogni
        volta che si torna a questa schermata (es. dopo una creazione,
        o tornando indietro dalla scheda)."""
        self.saves_list.clear()
        knights = list_knights(self.conn)

        if not knights:
            self.saves_card.setVisible(False)
            return

        self.saves_card.setVisible(True)
        for k in knights:
            item = QListWidgetItem(
                f"{k['formal_name']}  —  Livello {k['player_level']}  —  {k['armor_name']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, k["id"])
            self.saves_list.addItem(item)

        self.saves_list.setCurrentRow(0)  # la più recente (list_knights ordina per id DESC)

    def _on_continue_clicked(self) -> None:
        item = self.saves_list.currentItem()
        if item is None:
            return
        self.continue_requested.emit(item.data(Qt.ItemDataRole.UserRole))

    def _on_save_double_clicked(self, item: QListWidgetItem) -> None:
        self.continue_requested.emit(item.data(Qt.ItemDataRole.UserRole))

    def _on_delete_clicked(self) -> None:
        item = self.saves_list.currentItem()
        if item is None:
            return

        answer = QMessageBox.question(
            self,
            "Eliminare il personaggio?",
            f"Vuoi eliminare definitivamente '{item.text()}'?\n"
            f"L'azione non si può annullare.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        delete_knight(self.conn, item.data(Qt.ItemDataRole.UserRole))
        self.refresh()
