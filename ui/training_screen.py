"""
Centro Allenamento — programma settimanale stile Football Manager.

Si IMPOSTA un programma per i 7 giorni della settimana (un focus per
giorno, tramite tendine), poi si avanza di una settimana o di un mese
intero (stesso programma ripetuto 4 volte, niente bisogno di 30
tendine). Ogni avanzamento applica un programma bilanciato su più
statistiche, non un singolo focus ripetuto a piacere.

Il programma scelto viene salvato (weekly_schedule) e riproposto la
prossima volta - così puoi affinarlo nel tempo invece di reimpostarlo
sempre da capo.
"""
import sqlite3
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QProgressBar, QComboBox, QScrollArea,
)

from core.character_factory import get_knight, save_knight
from core.fm_manager import (
    RosterManager, TRAINING_FOCUS_OPTIONS, WEEKDAY_NAMES,
    parse_weekly_schedule, serialize_weekly_schedule, get_calendar_display,
)
from core.app_logger import get_logger

log = get_logger(__name__)


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


class TrainingScreen(QWidget):
    def __init__(self, conn: sqlite3.Connection, knight_id: int,
                 on_change: Optional[Callable[[], None]] = None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.knight_id = knight_id
        self.knight: dict | None = None
        self.on_change = on_change

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Centro Allenamento")
        title.setObjectName("headerTitle")
        root.addWidget(title)

        self.day_label = QLabel("—")
        self.day_label.setObjectName("hint")
        root.addWidget(self.day_label)

        # --- Card: stato attuale ---
        status_card, status_layout = _card("Stato attuale")

        stamina_label = QLabel("Stamina")
        stamina_label.setObjectName("hint")
        status_layout.addWidget(stamina_label)
        self.stamina_bar = QProgressBar()
        self.stamina_bar.setRange(0, 100)
        status_layout.addWidget(self.stamina_bar)

        xp_label = QLabel("Esperienza")
        xp_label.setObjectName("hint")
        status_layout.addWidget(xp_label)
        self.xp_bar = QProgressBar()
        status_layout.addWidget(self.xp_bar)

        root.addWidget(status_card)

        # --- Card: programma settimanale ---
        schedule_card, schedule_layout = _card("Programma settimanale")

        grid = QGridLayout()
        grid.setSpacing(6)
        self.day_combos: list[QComboBox] = []
        for col, day_name in enumerate(WEEKDAY_NAMES):
            day_label = QLabel(day_name[:3])  # Lun, Mar, Mer... per stare stretti
            day_label.setObjectName("hint")
            day_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(day_label, 0, col)

            combo = QComboBox()
            combo.addItems(TRAINING_FOCUS_OPTIONS)
            grid.addWidget(combo, 1, col)
            self.day_combos.append(combo)

        schedule_layout.addLayout(grid)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)

        self.advance_week_button = QPushButton("▶  Avanza Settimana (7 giorni)")
        self.advance_week_button.clicked.connect(lambda: self._on_advance_clicked(is_month=False))
        buttons_row.addWidget(self.advance_week_button)

        self.advance_month_button = QPushButton("▶▶  Avanza Mese (stesso programma x4)")
        self.advance_month_button.setObjectName("secondary")
        self.advance_month_button.clicked.connect(lambda: self._on_advance_clicked(is_month=True))
        buttons_row.addWidget(self.advance_month_button)

        schedule_layout.addLayout(buttons_row)
        root.addWidget(schedule_card)

        # --- Card: log risultati, con scroll vero (un mese fa fino a 30 righe) ---
        log_card, log_card_layout = _card("Ultimo avanzamento")

        self.log_scroll = QScrollArea()
        self.log_scroll.setWidgetResizable(True)
        self.log_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.log_content = QWidget()
        self.log_layout = QVBoxLayout(self.log_content)
        self.log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_layout.setSpacing(6)
        self.log_layout.addStretch()  # tiene le righe in cima man mano che se ne aggiungono

        self.log_hint = QLabel("I risultati del prossimo avanzamento appariranno qui.")
        self.log_hint.setObjectName("hint")
        self.log_hint.setWordWrap(True)
        self.log_layout.insertWidget(0, self.log_hint)

        self.log_scroll.setWidget(self.log_content)
        log_card_layout.addWidget(self.log_scroll)
        root.addWidget(log_card, stretch=1)

        self.refresh()

    def refresh(self) -> None:
        """Ricarica il personaggio dal DB, aggiorna le barre e ripopola
        le tendine col programma salvato. Da richiamare ogni volta che
        si torna su questa schermata."""
        self.knight = get_knight(self.conn, self.knight_id)
        if self.knight is None:
            log.error("TrainingScreen: nessun cavaliere con id=%s", self.knight_id)
            return
        self._update_bars()
        self._load_schedule_into_combos()

    def _load_schedule_into_combos(self) -> None:
        schedule = parse_weekly_schedule(self.knight["weekly_schedule"])
        for combo, focus in zip(self.day_combos, schedule):
            index = combo.findText(focus)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _update_bars(self) -> None:
        k = self.knight
        self.stamina_bar.setValue(k["stamina"])
        self.stamina_bar.setFormat(f"{k['stamina']} / 100")

        xp_needed = RosterManager.xp_to_next_level(k["player_level"])
        self.xp_bar.setRange(0, max(xp_needed, 1))
        self.xp_bar.setValue(min(k["xp"], xp_needed))
        self.xp_bar.setFormat(f"Livello {k['player_level']} — {k['xp']} / {xp_needed} XP")

        calendar = get_calendar_display(k["created_at"], k["game_minutes"])
        self.day_label.setText(f"{calendar['label']}  ·  Età {k['age']} anni")

    def _on_advance_clicked(self, is_month: bool) -> None:
        if self.knight is None:
            return

        schedule = [combo.currentText() for combo in self.day_combos]
        self.knight["weekly_schedule"] = serialize_weekly_schedule(schedule)

        if is_month:
            results = RosterManager.advance_month(self.knight, schedule)
        else:
            results = RosterManager.advance_week(self.knight, schedule)

        save_knight(self.conn, self.knight)

        self._clear_log()
        for day_label, focus, msg in results:
            log.info("Allenamento: %s (%s) -> %s", day_label, focus, msg)
            self._append_log_line(f"{day_label} ({focus}): {msg}")

        self._update_bars()

        if self.on_change:
            self.on_change()

    def _clear_log(self) -> None:
        """Pulisce il log del giro precedente prima di mostrare quello nuovo."""
        while self.log_layout.count() > 1:  # tiene lo stretch finale
            child = self.log_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _append_log_line(self, text: str) -> None:
        line = QLabel(f"• {text}")
        line.setWordWrap(True)
        self.log_layout.insertWidget(self.log_layout.count() - 1, line)
