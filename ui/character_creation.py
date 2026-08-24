"""
Schermata di creazione personaggio.

A differenza della versione di Gemini (nome + armatura scritti a mano
libera, nessuna validazione), qui:
  - l'armatura si SCEGLIE da una tabella con le sole armature davvero
    disponibili al livello del giocatore (character_factory.list_available_armors)
  - selezionando una riga si vedono subito le tecniche di
    quell'armatura, per decidere con cognizione di causa
  - "Crea personaggio" passa da character_factory.create_knight, che
    valida armatura esistente + livello minimo prima di salvare
"""
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QMessageBox,
    QAbstractItemView, QComboBox,
)

FILTER_ALL = "Tutte"

from core.character_factory import (
    list_available_armors, create_knight, ArmorNotFoundError, ArmorLevelTooHighError,
)
from database.db_manager import get_techniques_for_armor

STARTING_PLAYER_LEVEL = 1  # un personaggio nuovo parte sempre a livello 1


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    """Crea un pannello 'card' con titolo, in stile coerente col tema."""
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


class CharacterCreationScreen(QWidget):
    """Emette character_created(knight_id) quando la creazione va a buon fine,
    così la finestra principale può passare alla scheda del personaggio."""
    character_created = Signal(int)

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._all_armors: list[sqlite3.Row] = []
        self._armors_by_row: dict[int, sqlite3.Row] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        header = QLabel("Crea il tuo Cavaliere")
        header.setObjectName("headerTitle")
        root.addWidget(header)

        # --- Card: nome ---
        name_card, name_layout = _card("Nome del personaggio")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("es. Seiya")
        name_layout.addWidget(self.name_input)
        root.addWidget(name_card)

        # --- Card: scelta armatura ---
        armor_card, armor_layout = _card(
            f"Scegli l'armatura (disponibili al livello {STARTING_PLAYER_LEVEL})"
        )

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        divinity_col = QVBoxLayout()
        divinity_col.setSpacing(4)
        divinity_label = QLabel("Divinità")
        divinity_label.setObjectName("hint")
        self.divinity_filter = QComboBox()
        self.divinity_filter.currentIndexChanged.connect(self._on_divinity_filter_changed)
        divinity_col.addWidget(divinity_label)
        divinity_col.addWidget(self.divinity_filter)
        filter_row.addLayout(divinity_col, stretch=1)

        faction_col = QVBoxLayout()
        faction_col.setSpacing(4)
        faction_label = QLabel("Fazione / Grado")
        faction_label.setObjectName("hint")
        self.faction_filter = QComboBox()
        self.faction_filter.currentIndexChanged.connect(self._apply_filters)
        faction_col.addWidget(faction_label)
        faction_col.addWidget(self.faction_filter)
        filter_row.addLayout(faction_col, stretch=1)

        armor_layout.addLayout(filter_row)

        self.armor_table = QTableWidget(0, 4)
        self.armor_table.setHorizontalHeaderLabels(["Armatura", "Divinità", "Fazione", "Livello"])
        self.armor_table.setAlternatingRowColors(True)
        self.armor_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.armor_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.armor_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.armor_table.verticalHeader().setVisible(False)
        self.armor_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.armor_table.setMinimumHeight(260)
        self.armor_table.itemSelectionChanged.connect(self._on_armor_selected)
        armor_layout.addWidget(self.armor_table)

        root.addWidget(armor_card, stretch=1)

        # --- Card: anteprima tecniche ---
        self.preview_card, self.preview_layout = _card("Tecniche dell'armatura selezionata")
        self.preview_hint = QLabel("Seleziona un'armatura per vedere le sue tecniche.")
        self.preview_hint.setObjectName("hint")
        self.preview_hint.setWordWrap(True)
        self.preview_layout.addWidget(self.preview_hint)
        root.addWidget(self.preview_card)

        # --- Pulsante crea ---
        button_row = QHBoxLayout()
        button_row.addStretch()
        self.create_button = QPushButton("Crea e Seleziona")
        self.create_button.clicked.connect(self._on_create_clicked)
        button_row.addWidget(self.create_button)
        root.addLayout(button_row)

        self._load_armors()

    def _load_armors(self) -> None:
        """Carica UNA VOLTA tutte le armature disponibili al livello del
        giocatore, poi popola i filtri e mostra la tabella. I filtri
        successivi lavorano sulla lista già in memoria, senza rileggere
        il database ad ogni cambio (più reattivo)."""
        self._all_armors = list_available_armors(self.conn, STARTING_PLAYER_LEVEL)

        divinities = sorted({a["divinity"] for a in self._all_armors})
        self.divinity_filter.blockSignals(True)
        self.divinity_filter.clear()
        self.divinity_filter.addItem(FILTER_ALL)
        self.divinity_filter.addItems(divinities)
        self.divinity_filter.blockSignals(False)

        self._refresh_faction_filter()
        self._apply_filters()

    def _refresh_faction_filter(self) -> None:
        """Ricostruisce le opzioni di Fazione in base alla Divinità
        selezionata (o tutte, se 'Tutte le divinità')."""
        selected_divinity = self.divinity_filter.currentText()
        if selected_divinity and selected_divinity != FILTER_ALL:
            candidates = [a for a in self._all_armors if a["divinity"] == selected_divinity]
        else:
            candidates = self._all_armors

        factions = sorted({a["faction"] for a in candidates})

        self.faction_filter.blockSignals(True)
        self.faction_filter.clear()
        self.faction_filter.addItem(FILTER_ALL)
        self.faction_filter.addItems(factions)
        self.faction_filter.blockSignals(False)

    def _on_divinity_filter_changed(self) -> None:
        self._refresh_faction_filter()
        self._apply_filters()

    def _apply_filters(self) -> None:
        selected_divinity = self.divinity_filter.currentText()
        selected_faction = self.faction_filter.currentText()

        filtered = self._all_armors
        if selected_divinity and selected_divinity != FILTER_ALL:
            filtered = [a for a in filtered if a["divinity"] == selected_divinity]
        if selected_faction and selected_faction != FILTER_ALL:
            filtered = [a for a in filtered if a["faction"] == selected_faction]

        self._populate_table(filtered)

    def _populate_table(self, armors: list[sqlite3.Row]) -> None:
        self.armor_table.setRowCount(len(armors))
        self._armors_by_row.clear()

        for row_idx, armor in enumerate(armors):
            self._armors_by_row[row_idx] = armor
            values = [armor["name"], armor["divinity"], armor["faction"], str(armor["level"])]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.armor_table.setItem(row_idx, col_idx, item)

    def _on_armor_selected(self) -> None:
        # Ripulisce l'anteprima precedente (tutto tranne il titolo, primo elemento)
        while self.preview_layout.count() > 1:
            child = self.preview_layout.takeAt(1)
            if child.widget():
                child.widget().deleteLater()

        selected_rows = self.armor_table.selectionModel().selectedRows()
        if not selected_rows:
            hint = QLabel("Seleziona un'armatura per vedere le sue tecniche.")
            hint.setObjectName("hint")
            self.preview_layout.addWidget(hint)
            return

        armor = self._armors_by_row[selected_rows[0].row()]
        techniques = get_techniques_for_armor(armor["name"], self.conn)

        if not techniques:
            hint = QLabel("Questa armatura non ha ancora tecniche registrate nel catalogo.")
            hint.setObjectName("hint")
            self.preview_layout.addWidget(hint)
            return

        for t in techniques:
            line = QLabel(f"⚡ {t['name']}  —  {t['tech_type']}  (potenza {t['power']})")
            line.setWordWrap(True)
            self.preview_layout.addWidget(line)

    def _on_create_clicked(self) -> None:
        raw_name = self.name_input.text().strip()
        if not raw_name:
            QMessageBox.warning(self, "Nome mancante", "Inserisci un nome per il personaggio.")
            return

        selected_rows = self.armor_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Armatura mancante", "Seleziona un'armatura dalla tabella.")
            return

        armor = self._armors_by_row[selected_rows[0].row()]

        try:
            knight = create_knight(self.conn, raw_name, armor["name"], STARTING_PLAYER_LEVEL)
        except (ArmorNotFoundError, ArmorLevelTooHighError) as e:
            QMessageBox.critical(self, "Impossibile creare il personaggio", str(e))
            return

        self.character_created.emit(knight["id"])
