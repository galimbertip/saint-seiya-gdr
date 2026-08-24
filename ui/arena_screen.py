"""
Arena del Santuario — combattimento con turno "dichiara poi reagisci",
non più scelta simultanea alla cieca (vedi discussione in chat: la
scelta alla cieca sembrava "un dado contro un altro dado", niente vera
lettura dell'avversario).

Ogni round ha due metà:
  1. TU dichiari (Attacca o Carica). Se attacchi, l'AVVERSARIO reagisce
     d'istinto (si difende o incassa, più probabile difendersi se è
     già messo male) - reazione automatica, non richiede il tuo input.
  2. L'AVVERSARIO dichiara (Attacca o Carica). Se attacca, TU vedi
     QUALE tecnica sta arrivando e scegli se difenderti o incassare -
     qui la UI si ferma e aspetta la tua scelta, invece di deciderla
     in anticipo alla cieca.

Ispirato a Magic: The Gathering (istantaneo/stregoneria, dichiara poi
rispondi) ma senza la complessità della "pila": qui ogni round ha al
massimo una finestra di reazione per lato, niente contro-risposte a
catena.

Il Cosmo attuale fa da "punti vita" per entrambi. A fine scontro si
ricarica al massimo (placeholder, nessun recupero graduale ancora).
Il tempo passa in minuti, non più a giorni interi: ogni mezzo-round
(la tua dichiarazione, o la reazione dell'avversario dichiarata) costa
ARENA_ROUND_MINUTES - così un combattimento breve costa poco tempo di
gioco, uno lungo costa di più, e puoi incatenare altre azioni (un
allenamento, un altro scontro) nello stesso giorno se te lo puoi
permettere.
"""
import sqlite3
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFrame,
    QProgressBar, QScrollArea,
)

from core.character_factory import get_knight, save_knight
from core.arena_manager import (
    generate_opponent, resolve_turn, choose_opponent_action,
    resolve_defense, opponent_reacts, find_defensive_technique, get_unlocked_senses,
    BASE_ATTACK_POWER, DEFAULT_DEFENSE_POWER, SEVENTH_SENSE_COSMO_RATIO,
    SEVENTH_SENSE_MULTIPLIER, CHARGE_COSMO_COST, CHARGE_DAMAGE_MULTIPLIER,
    SESTO_SENSO_LEVEL, SETTIMO_SENSO_LEVEL, OTTAVO_SENSO_LEVEL,
)
from core.fm_manager import RosterManager, ARENA_ROUND_MINUTES
from database.db_manager import get_armor, get_techniques_for_armor
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


class ArenaScreen(QWidget):
    def __init__(self, conn: sqlite3.Connection, knight_id: int,
                 on_change: Optional[Callable[[], None]] = None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.knight_id = knight_id
        self.knight: dict | None = None
        self.armor: dict | None = None
        self.my_techniques: list[dict] = []
        self.my_defensive_technique: dict | None = None
        self.opponent: dict | None = None
        self.on_change = on_change

        # Stato effimero del combattimento in corso (mai salvato su DB).
        self._player_charge_multiplier = 1.0
        self._opponent_charge_multiplier = 1.0
        self._seventh_sense_used = False
        self._eighth_sense_used = False

        # Fase "reagisci": quando non-None, l'avversario ha dichiarato
        # questa tecnica contro di te e aspetti la TUA scelta.
        self._pending_opponent_technique: dict | None = None

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

        title = QLabel("Arena del Santuario")
        title.setObjectName("headerTitle")
        root.addWidget(title)

        # --- Card: i due combattenti ---
        fighters_card, fighters_layout = _card("Combattenti")

        me_label = QLabel("Tu")
        me_label.setObjectName("hint")
        fighters_layout.addWidget(me_label)
        self.my_cosmo_bar = QProgressBar()
        fighters_layout.addWidget(self.my_cosmo_bar)

        self.opponent_name_label = QLabel("Nessun avversario")
        self.opponent_name_label.setObjectName("hint")
        fighters_layout.addWidget(self.opponent_name_label)
        self.opponent_cosmo_bar = QProgressBar()
        fighters_layout.addWidget(self.opponent_cosmo_bar)

        root.addWidget(fighters_card)

        # --- Card: azioni (fase normale: dichiari tu) ---
        actions_card, self.actions_layout = _card("Le tue azioni")

        self.senses_label = QLabel("—")
        self.senses_label.setObjectName("hint")
        self.senses_label.setWordWrap(True)
        self.actions_layout.addWidget(self.senses_label)

        self.search_button = QPushButton("🗡  Cerca un Avversario")
        self.search_button.clicked.connect(self._on_search_opponent)
        self.actions_layout.addWidget(self.search_button)

        self.attack_buttons: list[QPushButton] = []  # popolati in _rebuild_action_buttons

        self.charge_button = QPushButton("🔥  Carica il Cosmo")
        self.charge_button.setObjectName("secondary")
        self.charge_button.clicked.connect(self._on_charge_clicked)
        self.charge_button.setVisible(False)
        self.actions_layout.addWidget(self.charge_button)

        # --- Card: reazione (fase reattiva: l'avversario ha dichiarato, tocca a te) ---
        self.reaction_label = QLabel("")
        self.reaction_label.setObjectName("sectionTitle")
        self.reaction_label.setWordWrap(True)
        self.reaction_label.setVisible(False)
        self.actions_layout.addWidget(self.reaction_label)

        self.defend_reaction_button = QPushButton("🛡  Difenditi")
        self.defend_reaction_button.clicked.connect(self._on_defend_reaction_clicked)
        self.defend_reaction_button.setVisible(False)
        self.actions_layout.addWidget(self.defend_reaction_button)

        self.take_hit_button = QPushButton("😤  Incassa il colpo")
        self.take_hit_button.setObjectName("secondary")
        self.take_hit_button.clicked.connect(self._on_take_hit_clicked)
        self.take_hit_button.setVisible(False)
        self.actions_layout.addWidget(self.take_hit_button)

        self.retreat_button = QPushButton("Ritirati")
        self.retreat_button.setObjectName("secondary")
        self.retreat_button.clicked.connect(self._on_retreat_clicked)
        self.retreat_button.setVisible(False)
        self.actions_layout.addWidget(self.retreat_button)

        root.addWidget(actions_card)

        # --- Card: log combattimento ---
        log_card, log_card_layout = _card("Cronaca dello scontro")

        self.log_scroll = QScrollArea()
        self.log_scroll.setWidgetResizable(True)
        self.log_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.log_content = QWidget()
        self.log_layout = QVBoxLayout(self.log_content)
        self.log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_layout.setSpacing(6)
        self.log_layout.addStretch()

        self.log_hint = QLabel("Cerca un avversario per iniziare uno scontro.")
        self.log_hint.setObjectName("hint")
        self.log_hint.setWordWrap(True)
        self.log_layout.insertWidget(0, self.log_hint)

        self.log_scroll.setWidget(self.log_content)
        log_card_layout.addWidget(self.log_scroll)
        root.addWidget(log_card, stretch=1)

        self.refresh()

    def refresh(self) -> None:
        self.knight = get_knight(self.conn, self.knight_id)
        if self.knight is None:
            log.error("ArenaScreen: nessun cavaliere con id=%s", self.knight_id)
            return
        self.armor = get_armor(self.knight["armor_name"], self.conn)
        self.my_techniques = [dict(t) for t in get_techniques_for_armor(self.knight["armor_name"], self.conn)]
        self.my_defensive_technique = find_defensive_technique(self.my_techniques)
        self._update_my_bar()
        self._rebuild_action_buttons()

    def _update_my_bar(self) -> None:
        k = self.knight
        self.my_cosmo_bar.setRange(0, max(k["cosmo_max"], 1))
        self.my_cosmo_bar.setValue(max(k["cosmo_cur"], 0))
        self.my_cosmo_bar.setFormat(f"Cosmo: {k['cosmo_cur']} / {k['cosmo_max']}")

    def _update_opponent_bar(self) -> None:
        if self.opponent is None:
            self.opponent_name_label.setText("Nessun avversario")
            self.opponent_cosmo_bar.setRange(0, 1)
            self.opponent_cosmo_bar.setValue(0)
            self.opponent_cosmo_bar.setFormat("—")
            return

        o = self.opponent
        self.opponent_name_label.setText(f"{o['name']} ({o['divinity']} / {o['faction']})")
        self.opponent_cosmo_bar.setRange(0, max(o["cosmo_max"], 1))
        self.opponent_cosmo_bar.setValue(max(o["cosmo_cur"], 0))
        self.opponent_cosmo_bar.setFormat(f"Cosmo: {o['cosmo_cur']} / {o['cosmo_max']}")

    def _rebuild_action_buttons(self) -> None:
        for btn in self.attack_buttons:
            btn.deleteLater()
        self.attack_buttons.clear()

        in_combat = self.opponent is not None
        self.search_button.setVisible(not in_combat)
        self.retreat_button.setVisible(in_combat)

        if not in_combat:
            self.charge_button.setVisible(False)
            self.reaction_label.setVisible(False)
            self.defend_reaction_button.setVisible(False)
            self.take_hit_button.setVisible(False)
            return

        senses = get_unlocked_senses(self.knight["player_level"])
        mark = lambda unlocked: "✓" if unlocked else "✗"
        self.senses_label.setText(
            f"Sensi — Sesto (liv.{SESTO_SENSO_LEVEL}) {mark(senses['sesto'])}  ·  "
            f"Settimo (liv.{SETTIMO_SENSO_LEVEL}) {mark(senses['settimo'])}  ·  "
            f"Ottavo (liv.{OTTAVO_SENSO_LEVEL}) {mark(senses['ottavo'])}"
        )

        awaiting_reaction = self._pending_opponent_technique is not None

        # --- Fase reattiva: l'avversario ha dichiarato, tocca a te decidere ---
        self.reaction_label.setVisible(awaiting_reaction)
        self.defend_reaction_button.setVisible(awaiting_reaction)
        self.take_hit_button.setVisible(awaiting_reaction)
        self.search_button.setVisible(not in_combat)
        self.charge_button.setVisible(not awaiting_reaction)

        if awaiting_reaction:
            t = self._pending_opponent_technique
            self.reaction_label.setText(
                f"⚔ {self.opponent['name']} sta per colpirti con {t['name']} (potenza {t['power']})! Come rispondi?"
            )
            defense = self.my_defensive_technique
            self.defend_reaction_button.setText(
                f"🛡  Difenditi con {defense['name']}" if defense else "🛡  Difenditi (Parata generica)"
            )
            return  # in questa fase non mostro i pulsanti tecnica: prima devi reagire

        # --- Fase normale: dichiari tu ---
        self.charge_button.setEnabled(senses["sesto"])
        self.charge_button.setText(
            "🔥  Carica il Cosmo" if senses["sesto"]
            else f"🔥  Carica il Cosmo (richiede Sesto Senso, livello {SESTO_SENSO_LEVEL})"
        )

        options = [("Attacco Base", BASE_ATTACK_POWER)] + [
            (t["name"], t["power"]) for t in self.my_techniques
            if "difensiv" not in (t.get("tech_type") or "").lower()
        ]
        insert_at = self.actions_layout.indexOf(self.search_button) + 1
        for name, power in options:
            btn = QPushButton(f"⚔  {name} (potenza {power})")
            btn.clicked.connect(lambda checked=False, n=name, p=power: self._on_attack_clicked(n, p))
            self.actions_layout.insertWidget(insert_at, btn)
            self.attack_buttons.append(btn)
            insert_at += 1

    def _on_search_opponent(self) -> None:
        if self.knight is None or self.armor is None:
            return

        self.opponent = generate_opponent(self.conn, self.armor["level"], exclude_armor_name=self.armor["name"])
        self._player_charge_multiplier = 1.0
        self._opponent_charge_multiplier = 1.0
        self._seventh_sense_used = False
        self._eighth_sense_used = False
        self._pending_opponent_technique = None

        self._clear_log()
        self._append_log_line(
            f"Un rivale si fa avanti: {self.opponent['name']} "
            f"({self.opponent['divinity']} / {self.opponent['faction']}, livello armatura {self.opponent['armor_level']})."
        )
        self._update_opponent_bar()
        self._rebuild_action_buttons()

    # --- Metà 1 del round: dichiari tu -------------------------------------

    def _on_attack_clicked(self, technique_name: str, technique_power: int) -> None:
        if self.knight is None or self.opponent is None or self.armor is None:
            return

        o = self.opponent
        dmg, msg = resolve_turn(
            self.knight["raw_name"], self.knight["str"], self.armor["level"],
            o["name"], o["dex"], o["armor_level"], technique_name, technique_power,
        )
        dmg = self._apply_charge_bonus(dmg, is_player_attacking=True)

        defense = opponent_reacts(o)
        if defense:
            reduced = resolve_defense(dmg, defense["power"])
            o["cosmo_cur"] = max(0, o["cosmo_cur"] - reduced)
            self._append_log_line(f"{msg} — {o['name']} para con {defense['name']}, il danno scende a {reduced}.")
        else:
            o["cosmo_cur"] = max(0, o["cosmo_cur"] - dmg)
            self._append_log_line(msg)

        self._update_opponent_bar()
        aging_msg = RosterManager.spend_time(self.knight, ARENA_ROUND_MINUTES)
        if aging_msg:
            self._append_log_line(aging_msg)
        if self.on_change:
            self.on_change()

        if self._check_fight_over():
            return

        self._start_opponent_declaration()

    def _on_charge_clicked(self) -> None:
        if self.knight is None:
            return
        self._player_charges()
        self._append_log_line(f"{self.knight['raw_name']} carica il Cosmo, pronto a colpire più forte.")
        self._update_my_bar()
        aging_msg = RosterManager.spend_time(self.knight, ARENA_ROUND_MINUTES)
        if aging_msg:
            self._append_log_line(aging_msg)
        if self.on_change:
            self.on_change()
        self._start_opponent_declaration()

    # --- Metà 2 del round: dichiara l'avversario, tu reagisci --------------

    def _start_opponent_declaration(self) -> None:
        """L'avversario dichiara la sua mossa. Se attacca, la UI si
        ferma e aspetta la TUA scelta (fase reattiva) - non decide più
        tutto in automatico."""
        o = self.opponent
        action, detail = choose_opponent_action(o)

        if action == "carica":
            self._opponent_charges()
            self._append_log_line(f"{o['name']} carica il proprio Cosmo per il prossimo colpo.")
            self._update_opponent_bar()
            aging_msg = RosterManager.spend_time(self.knight, ARENA_ROUND_MINUTES)
            if aging_msg:
                self._append_log_line(aging_msg)
            if self.on_change:
                self.on_change()
            self._rebuild_action_buttons()
            return

        self._pending_opponent_technique = detail
        self._append_log_line(f"⚔ {o['name']} si prepara a colpire con {detail['name']}!")
        self._rebuild_action_buttons()

    def _on_defend_reaction_clicked(self) -> None:
        self._resolve_opponent_attack(defend=True)

    def _on_take_hit_clicked(self) -> None:
        self._resolve_opponent_attack(defend=False)

    def _resolve_opponent_attack(self, defend: bool) -> None:
        if self.knight is None or self.opponent is None or self.armor is None:
            return
        o = self.opponent
        t = self._pending_opponent_technique
        self._pending_opponent_technique = None

        dmg2, msg2 = resolve_turn(
            o["name"], o["str"], o["armor_level"],
            self.knight["raw_name"], self.knight["dex"], self.armor["level"],
            t["name"], t["power"],
        )
        dmg2 = self._apply_charge_bonus(dmg2, is_player_attacking=False)

        if defend:
            defense_technique = self.my_defensive_technique or {"name": "Parata", "power": DEFAULT_DEFENSE_POWER}
            reduced = resolve_defense(dmg2, defense_technique["power"])
            self.knight["cosmo_cur"] = max(0, self.knight["cosmo_cur"] - reduced)
            self._append_log_line(f"{msg2} — ti difendi con {defense_technique['name']}, il danno scende a {reduced}.")
        else:
            self.knight["cosmo_cur"] = max(0, self.knight["cosmo_cur"] - dmg2)
            self._append_log_line(msg2)

        self._check_eighth_sense()
        self._check_seventh_sense(after_damage_to_player=True)
        self._update_my_bar()

        aging_msg = RosterManager.spend_time(self.knight, ARENA_ROUND_MINUTES)
        if aging_msg:
            self._append_log_line(aging_msg)
        if self.on_change:
            self.on_change()

        if self._check_fight_over():
            return
        self._rebuild_action_buttons()

    # --- Carica (self-buff, nessuna reazione dell'altro necessaria) --------

    def _player_charges(self) -> None:
        self.knight["cosmo_cur"] = max(1, self.knight["cosmo_cur"] - CHARGE_COSMO_COST)
        self._player_charge_multiplier = max(self._player_charge_multiplier, CHARGE_DAMAGE_MULTIPLIER)

    def _opponent_charges(self) -> None:
        o = self.opponent
        o["cosmo_cur"] = max(1, o["cosmo_cur"] - CHARGE_COSMO_COST)
        self._opponent_charge_multiplier = max(self._opponent_charge_multiplier, CHARGE_DAMAGE_MULTIPLIER)

    def _apply_charge_bonus(self, damage: int, is_player_attacking: bool) -> int:
        if is_player_attacking and self._player_charge_multiplier > 1.0:
            multiplier = self._player_charge_multiplier
            self._player_charge_multiplier = 1.0
            return round(damage * multiplier)
        if not is_player_attacking and self._opponent_charge_multiplier > 1.0:
            multiplier = self._opponent_charge_multiplier
            self._opponent_charge_multiplier = 1.0
            return round(damage * multiplier)
        return damage

    # --- Sensi del Cosmo ----------------------------------------------------

    def _check_seventh_sense(self, after_damage_to_player: bool) -> None:
        if not after_damage_to_player or self.knight is None or self._seventh_sense_used:
            return
        senses = get_unlocked_senses(self.knight["player_level"])
        if not senses["settimo"]:
            return
        threshold = self.knight["cosmo_max"] * SEVENTH_SENSE_COSMO_RATIO
        if 0 < self.knight["cosmo_cur"] <= threshold:
            self._player_charge_multiplier = max(self._player_charge_multiplier, SEVENTH_SENSE_MULTIPLIER)
            self._seventh_sense_used = True
            self._append_log_line(
                f"⚡ {self.knight['raw_name']} risveglia il SETTIMO SENSO! "
                f"Il prossimo attacco sarà devastante."
            )

    def _check_eighth_sense(self) -> None:
        if self.knight is None or self.knight["cosmo_cur"] > 0:
            return
        senses = get_unlocked_senses(self.knight["player_level"])
        if senses["ottavo"] and not self._eighth_sense_used:
            self._eighth_sense_used = True
            self.knight["cosmo_cur"] = 1
            self._append_log_line(
                f"✨ {self.knight['raw_name']} trascende la morte con l'OTTAVO SENSO "
                f"e resta in piedi con l'ultimo respiro di Cosmo!"
            )

    # --- Fine scontro ---------------------------------------------------

    def _check_fight_over(self) -> bool:
        if self.opponent is None or self.knight is None:
            return False
        if self.opponent["cosmo_cur"] <= 0:
            self._end_fight(won=True)
            return True
        if self.knight["cosmo_cur"] <= 0:
            self._end_fight(won=False)
            return True
        return False

    def _end_fight(self, won: bool) -> None:
        if won:
            self._append_log_line(f"🏆 Hai sconfitto {self.opponent['name']}!")
        else:
            self._append_log_line(f"💀 Sei stato sconfitto da {self.opponent['name']}...")

        # Il tempo è già stato speso round per round durante lo scontro
        # (vedi ARENA_ROUND_MINUTES) - niente costo fisso extra qui.

        # Placeholder: recupero completo del Cosmo a fine scontro, in
        # attesa di un sistema di recupero graduale fuori combattimento.
        self.knight["cosmo_cur"] = self.knight["cosmo_max"]
        save_knight(self.conn, self.knight)
        log.info("Arena: combattimento concluso (vittoria=%s) contro %s", won, self.opponent["name"])

        self.opponent = None
        self._pending_opponent_technique = None
        self._update_my_bar()
        self._update_opponent_bar()
        self._rebuild_action_buttons()

        if self.on_change:
            self.on_change()

    def _on_retreat_clicked(self) -> None:
        if self.opponent is None:
            return
        self._append_log_line(f"Ti ritiri dallo scontro con {self.opponent['name']}.")

        # Idem: il tempo dei round già combattuti è già stato speso,
        # niente costo fisso aggiuntivo per la ritirata in sé.

        self.knight["cosmo_cur"] = self.knight["cosmo_max"]
        save_knight(self.conn, self.knight)

        self.opponent = None
        self._pending_opponent_technique = None
        self._update_my_bar()
        self._update_opponent_bar()
        self._rebuild_action_buttons()

        if self.on_change:
            self.on_change()

    def _clear_log(self) -> None:
        while self.log_layout.count() > 1:
            child = self.log_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _append_log_line(self, text: str) -> None:
        line = QLabel(f"• {text}")
        line.setWordWrap(True)
        self.log_layout.insertWidget(self.log_layout.count() - 1, line)
