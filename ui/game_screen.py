"""
Schermata di gioco: sidebar di navigazione + area di contenuto che
cambia in base alla voce selezionata.

  ┌─────────────┬─────────────────────────┐
  │ Scheda       │                         │
  │ Arena        │   contenuto della       │
  │ Allenamento  │   pagina selezionata    │
  │             │                         │
  │ Santuario   │                         │
  └─────────────┴─────────────────────────┘

Le icone della sidebar usano qtawesome (icone vettoriali vere) invece
delle emoji di sistema, che su Linux Mint rendevano male (visto negli
screenshot). Richiede: pip install qtawesome nel venv.
"""
import sqlite3
from typing import Callable

import qtawesome as qta
from PySide6.QtCore import Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QStackedWidget, QFrame, QLabel,
)

from ui.theme import COLORS
from ui.character_sheet import CharacterSheetScreen
from ui.training_screen import TrainingScreen
from ui.arena_screen import ArenaScreen
from core.character_factory import get_knight
from core.fm_manager import get_calendar_display


class GameScreen(QWidget):
    back_to_menu_requested = Signal()
    exit_requested = Signal()

    def __init__(self, conn: sqlite3.Connection, knight_id: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.knight_id = knight_id

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Barra calendario, sempre visibile sopra a tutte le pagine ---
        calendar_bar = QFrame()
        calendar_bar.setObjectName("card")
        calendar_layout = QHBoxLayout(calendar_bar)
        calendar_layout.setContentsMargins(18, 8, 18, 8)

        calendar_icon = QLabel()
        calendar_icon.setPixmap(qta.icon("fa5s.calendar-alt", color=COLORS["cosmo_blue"]).pixmap(QSize(16, 16)))
        calendar_layout.addWidget(calendar_icon)

        self.calendar_label = QLabel("—")
        self.calendar_label.setStyleSheet(f"color: {COLORS['cosmo_blue']}; font-weight: 600;")
        calendar_layout.addWidget(self.calendar_label)
        calendar_layout.addStretch()

        outer.addWidget(calendar_bar)

        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        outer.addLayout(root)

        # --- Sidebar ---
        sidebar = QFrame()
        sidebar.setObjectName("card")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 20, 12, 20)
        sidebar_layout.setSpacing(4)

        self.nav_buttons: dict[int, QPushButton] = {}

        self.content = QStackedWidget()

        self.sheet_screen = CharacterSheetScreen(self.conn, self.knight_id)
        self.arena_screen = ArenaScreen(self.conn, self.knight_id, on_change=self._refresh_calendar)
        self.training_screen = TrainingScreen(self.conn, self.knight_id, on_change=self._refresh_calendar)

        icon_color = COLORS["text_secondary"]
        icon_color_active = COLORS["gold"]

        nav_items = (
            ("Scheda Cavaliere", "fa5s.scroll", self.sheet_screen),
            ("Arena del Santuario", "fa5s.khanda", self.arena_screen),
            ("Centro Allenamento", "fa5s.dumbbell", self.training_screen),
        )

        self.nav_icon_names: dict[int, str] = {}

        for label, icon_name, screen in nav_items:
            index = self.content.addWidget(screen)
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setIcon(qta.icon(icon_name, color=icon_color))
            btn.setIconSize(QSize(16, 16))
            btn.clicked.connect(lambda checked=False, i=index: self._select_page(i))
            sidebar_layout.addWidget(btn)
            self.nav_buttons[index] = btn
            self.nav_icon_names[index] = icon_name

        sidebar_layout.addStretch()

        back_button = QPushButton("Torna al Santuario")
        back_button.setObjectName("navButton")
        back_button.setIcon(qta.icon("fa5s.door-open", color=icon_color))
        back_button.setIconSize(QSize(16, 16))
        back_button.clicked.connect(self.back_to_menu_requested.emit)
        sidebar_layout.addWidget(back_button)

        exit_button = QPushButton("Salva ed Esci")
        exit_button.setObjectName("navButton")
        exit_button.setIcon(qta.icon("fa5s.save", color=icon_color))
        exit_button.setIconSize(QSize(16, 16))
        exit_button.clicked.connect(self.exit_requested.emit)
        sidebar_layout.addWidget(exit_button)

        root.addWidget(sidebar)
        root.addWidget(self.content, stretch=1)

        self._icon_color = icon_color
        self._icon_color_active = icon_color_active

        self._refresh_calendar()
        self._select_page(0)

    def _refresh_calendar(self) -> None:
        knight = get_knight(self.conn, self.knight_id)
        if knight is None:
            return
        calendar = get_calendar_display(knight["game_day"])
        self.calendar_label.setText(calendar["label"])

    def _select_page(self, index: int) -> None:
        self.content.setCurrentIndex(index)
        for i, btn in self.nav_buttons.items():
            is_active = i == index
            btn.setObjectName("navButtonActive" if is_active else "navButton")
            color = self._icon_color_active if is_active else self._icon_color
            btn.setIcon(qta.icon(self.nav_icon_names[i], color=color))
            # Riapplica lo stile: cambiare setObjectName da solo non basta,
            # Qt ha bisogno di un refresh esplicito del foglio di stile.
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if index == 0:
            self.sheet_screen.refresh()
        elif index == 1:
            self.arena_screen.refresh()
        elif index == 2:
            self.training_screen.refresh()

        self._refresh_calendar()
