"""
Schermate segnaposto per le sezioni non ancora implementate.

Non sono finte come il "In Sviluppo" di Gemini (una label e basta):
spiegano onestamente cosa manca e perché - il motore (dnd_engine per
l'Arena, fm_manager per l'Allenamento) esiste già e funziona, quello
che manca è la UI + le decisioni sulle dinamiche di gioco vere e
proprie (formula danni, bilanciamento allenamento), rimandate di
proposito a dopo la struttura.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame


class _PlaceholderScreen(QWidget):
    """Base comune: titolo + card con spiegazione. Le sottoclassi passano
    solo testo, niente logica duplicata."""

    def __init__(self, title_text: str, explanation: str, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel(title_text)
        title.setObjectName("headerTitle")
        layout.addWidget(title)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)

        text = QLabel(explanation)
        text.setObjectName("hint")
        text.setWordWrap(True)
        card_layout.addWidget(text)

        layout.addWidget(card)
        layout.addStretch()


class ArenaPlaceholderScreen(_PlaceholderScreen):
    def __init__(self, parent=None):
        super().__init__(
            "⚔️ Arena del Santuario",
            "Il motore dei combattimenti (core/dnd_engine.py) è già scritto e testato: "
            "tiri per colpire, Classe Armatura derivata dal livello reale dell'armatura, "
            "dado di attacco che scala con la forza dell'armatura. Manca ancora l'interfaccia "
            "grafica del combattimento vero e proprio, e soprattutto manca la formula finale "
            "del danno (Potenza tecnica × Dado) - segnata di proposito come placeholder in "
            "attesa di decidere insieme il bilanciamento.",
            parent,
        )


class TrainingPlaceholderScreen(_PlaceholderScreen):
    def __init__(self, parent=None):
        super().__init__(
            "🏋️ Centro Allenamento",
            "Il motore di allenamento (core/fm_manager.py) è già scritto e testato: "
            "consumo di stamina, crescita delle statistiche, progressione a XP/livello. "
            "Manca ancora l'interfaccia grafica per scegliere il focus di allenamento "
            "e vedere i risultati, e il bilanciamento fine (costi, curva di progressione) "
            "resta da tarare insieme.",
            parent,
        )
