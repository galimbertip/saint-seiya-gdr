"""
Scheda del Cavaliere: mostra un personaggio già creato.

A differenza della versione di Gemini, le tecniche mostrate sono
SEMPRE quelle vere del catalogo (get_techniques_for_armor), mai il
fallback finto "Colpo del Cosmo / Barriera Cosmica" che scattava
quando l'armatura non veniva trovata nel JSON statico - qui l'armatura
esiste sempre, perché character_factory la valida in creazione.
"""
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
    QProgressBar, QScrollArea,
)

from database.db_manager import get_armor, get_techniques_for_armor
from core.character_factory import get_knight
from core.fm_manager import RosterManager
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


def _stat_chip(label_text: str) -> tuple[QFrame, QLabel]:
    """Un piccolo riquadro con etichetta (STR/DEX/...) e valore grande,
    usato per la riga delle 5 statistiche. Restituisce (frame, label_valore)."""
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(2)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    name_lbl = QLabel(label_text)
    name_lbl.setObjectName("hint")
    name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

    value_lbl = QLabel("0")
    value_lbl.setStyleSheet("font-size: 20px; font-weight: 700;")
    value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

    layout.addWidget(value_lbl)
    layout.addWidget(name_lbl)
    return frame, value_lbl


class CharacterSheetScreen(QWidget):
    def __init__(self, conn: sqlite3.Connection, knight_id: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.knight_id = knight_id
        self.knight: dict | None = None

        # Contenitore esterno: solo lo scroll, niente margini/spaziature
        # (quelli stanno nel contenuto interno) - così se la scheda
        # cresce (tante tecniche, finestra piccola) compare una barra di
        # scorrimento invece di forzare la finestra oltre lo schermo.
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

        self.title_label = QLabel("—")
        self.title_label.setObjectName("headerTitle")
        root.addWidget(self.title_label)

        self.subtitle_label = QLabel("—")
        self.subtitle_label.setObjectName("hint")
        root.addWidget(self.subtitle_label)

        # --- Card: Cosmo ---
        cosmo_card, cosmo_layout = _card("Cosmo")
        self.cosmo_bar = QProgressBar()
        self.cosmo_bar.setTextVisible(True)
        cosmo_layout.addWidget(self.cosmo_bar)
        root.addWidget(cosmo_card)

        # --- Card: Statistiche ---
        stats_card, stats_layout = _card("Statistiche")
        stats_grid = QHBoxLayout()
        stats_grid.setSpacing(10)
        self.stat_value_labels: dict[str, QLabel] = {}
        for key, label_text in (("str", "FORZA"), ("dex", "DESTREZZA"), ("con", "COSTITUZIONE"),
                                 ("tec", "TECNICA"), ("vol", "VOLONTÀ")):
            chip, value_label = _stat_chip(label_text)
            self.stat_value_labels[key] = value_label
            stats_grid.addWidget(chip)
        stats_layout.addLayout(stats_grid)
        root.addWidget(stats_card)

        # --- Card: Progressione (livello, xp, stamina, età) ---
        prog_card, prog_layout = _card("Progressione")

        level_row = QHBoxLayout()
        self.level_label = QLabel("Livello —")
        self.age_label = QLabel("Età —")
        self.age_label.setObjectName("hint")
        level_row.addWidget(self.level_label)
        level_row.addStretch()
        level_row.addWidget(self.age_label)
        prog_layout.addLayout(level_row)

        self.xp_bar = QProgressBar()
        self.xp_bar.setTextVisible(True)
        prog_layout.addWidget(self.xp_bar)

        stamina_label = QLabel("Stamina")
        stamina_label.setObjectName("hint")
        prog_layout.addWidget(stamina_label)
        self.stamina_bar = QProgressBar()
        self.stamina_bar.setRange(0, 100)
        self.stamina_bar.setTextVisible(True)
        prog_layout.addWidget(self.stamina_bar)

        root.addWidget(prog_card)

        # --- Card: Tecniche ---
        self.tech_card, self.tech_layout = _card("Tecniche dell'armatura")
        root.addWidget(self.tech_card, stretch=1)

        self.refresh()

    def refresh(self) -> None:
        """Ricarica i dati del personaggio dal DB e aggiorna tutta la UI.
        Da richiamare dopo ogni azione che modifica il knight (allenamento,
        combattimento...)."""
        self.knight = get_knight(self.conn, self.knight_id)
        if self.knight is None:
            log.error("CharacterSheetScreen: nessun cavaliere con id=%s", self.knight_id)
            self.title_label.setText("Personaggio non trovato")
            return

        k = self.knight
        armor = get_armor(k["armor_name"], self.conn)

        self.title_label.setText(k["formal_name"])
        if armor:
            self.subtitle_label.setText(
                f"{armor['divinity']} · {armor['faction']} · Livello armatura {armor['level']}"
            )
        else:
            self.subtitle_label.setText(k["armor_name"])

        self.cosmo_bar.setRange(0, max(k["cosmo_max"], 1))
        self.cosmo_bar.setValue(k["cosmo_cur"])
        self.cosmo_bar.setFormat(f"{k['cosmo_cur']} / {k['cosmo_max']}")

        for key, value_label in self.stat_value_labels.items():
            value_label.setText(str(k[key]))

        self.level_label.setText(f"Livello personaggio {k['player_level']}")
        self.age_label.setText(f"Età {k['age']}")

        xp_needed = RosterManager.xp_to_next_level(k["player_level"])
        self.xp_bar.setRange(0, max(xp_needed, 1))
        self.xp_bar.setValue(min(k["xp"], xp_needed))
        self.xp_bar.setFormat(f"{k['xp']} / {xp_needed} XP")

        self.stamina_bar.setValue(k["stamina"])
        self.stamina_bar.setFormat(f"{k['stamina']} / 100")

        self._refresh_techniques(k["armor_name"])

    def _refresh_techniques(self, armor_name: str) -> None:
        while self.tech_layout.count() > 1:
            child = self.tech_layout.takeAt(1)
            if child.widget():
                child.widget().deleteLater()

        techniques = get_techniques_for_armor(armor_name, self.conn)
        if not techniques:
            hint = QLabel("Nessuna tecnica registrata per questa armatura nel catalogo.")
            hint.setObjectName("hint")
            self.tech_layout.addWidget(hint)
            return

        for t in techniques:
            line = QLabel(f"⚡ {t['name']}  —  {t['tech_type']}  (potenza {t['power']})")
            line.setWordWrap(True)
            self.tech_layout.addWidget(line)
            if t["launch_desc"]:
                desc = QLabel(t["launch_desc"])
                desc.setObjectName("hint")
                desc.setWordWrap(True)
                self.tech_layout.addWidget(desc)
