"""Alternative al fallimento della Prova Finale (richiesto in chat):
oltre a "ritenta" (comportamento esistente), tre strade vere -
riaddestrarsi per un'altra armatura libera, diventare soldato semplice
(uno stato di gioco vero, con attività dedicate proprie, non solo
narrativo), o la morte definitiva del personaggio. La scelta compare
ad OGNI fallimento, non solo dopo un certo numero di tentativi.

I compagni non hanno una loro Prova Finale simulata a parte (richiesto
in chat, per restare allineati - il rischio altrimenti è ritrovarsi
con due Cavalieri per la stessa Cloth). Il loro destino si decide nello
stesso momento in cui la VICENDA DEL GIOCATORE con quell'armatura si
conclude, quale che sia l'esito - vittoria, riaddestramento, soldato o
morte."""

import random
import sqlite3

from database.db_manager import (
    get_armor, get_roster_entry, claim_roster_slot, release_roster_slot,
    list_armors_for_player_level,
)
from core.training_path import select_master, generate_companions

# --- Destino dei compagni -------------------------------------------------
# Per lo più diventano soldati o si riaddestrano altrove; raramente
# qualcosa di più tragico - mai la norma, richiesto in chat solo come
# possibilità realistica, non come esito comune.
COMPANION_FATES = [
    ("diventa soldato semplice, mettendo al servizio della fazione quel che ha imparato in questi mesi.", 0.5),
    ("lascia questo Santuario per tentare l'addestramento altrove, per un'armatura diversa.", 0.4),
    ("non ce l'ha fatta. Il suo nome resterà comunque tra quelli che hanno provato fino in fondo.", 0.1),
]


def resolve_companion_fate(companion_name: str) -> str:
    """Un destino narrativo per UN compagno che non ottiene l'armatura
    (richiesto in chat) - per lo più diventa soldato o si riaddestra
    altrove, raramente qualcosa di più tragico."""
    roll = random.random()
    cumulative = 0.0
    for text, weight in COMPANION_FATES:
        cumulative += weight
        if roll < cumulative:
            return f"{companion_name} {text}"
    return f"{companion_name} {COMPANION_FATES[-1][0]}"


def resolve_companions_fates(companion1_name: str, companion2_name: str) -> list[str]:
    """I destini di ENTRAMBI i compagni (richiesto in chat: si decidono
    insieme, nello stesso momento in cui si conclude la tua vicenda con
    l'armatura, non con una Prova Finale simulata a parte per
    ciascuno)."""
    return [resolve_companion_fate(companion1_name), resolve_companion_fate(companion2_name)]


# --- Soldato Semplice: un vero mini-percorso, non solo uno stato ----------
# (richiesto in chat) - attività ripetibili, ciascuna con una piccola
# ricompensa in denaro e un po' di testo diverso ogni volta.
SOLDIER_ACTIVITIES = {
    "guardia": {
        "label": "Turno di guardia",
        "flavor": [
            "Ore di silenzio sulle mura, interrotte solo dal vento che fischia tra le colonne.",
            "Un allarme falso ti tiene sveglio più del dovuto, ma non succede nulla di grave.",
            "Passi la notte a fissare l'orizzonte, senza che nulla lo turbi davvero.",
            "Il cambio della guardia arriva con calma, un altro turno chiuso senza incidenti.",
        ],
        "denaro_min": 5, "denaro_max": 15,
    },
    "pattuglia": {
        "label": "Pattuglia nei dintorni",
        "flavor": [
            "Un giro di perlustrazione tranquillo: nulla fuori posto lungo il perimetro.",
            "Aiuti un viandante smarrito a ritrovare la strada verso il villaggio più vicino.",
            "Trovi tracce sospette, ma seguirle non porta a nulla di concreto.",
            "La routine della pattuglia ti lascia comunque il tempo di pensare, forse troppo.",
        ],
        "denaro_min": 8, "denaro_max": 20,
    },
    "addestramento_reclute": {
        "label": "Addestramento delle reclute",
        "flavor": [
            "Insegni le basi a un gruppo di nuovi arrivati, più goffi di quanto tu fossi mai stato.",
            "Una recluta particolarmente testarda ti ricorda te stesso, all'inizio di tutto questo.",
            "La giornata passa tra flessioni, corsa, e la solita fatica di sempre - ma dall'altra parte, stavolta.",
            "Qualcuno dei tuoi allievi ha davvero talento - ti chiedi se un giorno arriverà dove tu non sei arrivato.",
        ],
        "denaro_min": 6, "denaro_max": 18,
    },
}


def resolve_soldier_activity(activity_key: str) -> tuple[str, int]:
    """Risolve un'attività da Soldato Semplice (richiesto in chat: un
    vero mini-percorso, non solo uno stato passivo) - restituisce
    (testo, denaro guadagnato)."""
    activity = SOLDIER_ACTIVITIES[activity_key]
    flavor = random.choice(activity["flavor"])
    denaro = random.randint(activity["denaro_min"], activity["denaro_max"])
    return flavor, denaro


# --- Riaddestrarsi per un'altra armatura ----------------------------------

def pick_available_armor(conn: sqlite3.Connection, player_level: int, exclude_armor_name: str) -> sqlite3.Row | None:
    """Un'armatura libera (nessun personaggio giocatore la porta già) e
    adatta al livello attuale, diversa da quella appena abbandonata
    (richiesto in chat: riaddestrarsi per un'altra armatura LIBERA) -
    None se non ce n'è nessuna disponibile (caso limite, con 228
    armature nel catalogo estremamente improbabile)."""
    candidates = [
        a for a in list_armors_for_player_level(player_level, conn)
        if a["name"] != exclude_armor_name
    ]
    random.shuffle(candidates)
    for armor in candidates:
        roster_entry = get_roster_entry(conn, armor["name"])
        if roster_entry is None or roster_entry["claimed_by_knight_id"] is None:
            return armor
    return None


def retrain_for_new_armor(conn: sqlite3.Connection, knight: dict) -> dict:
    """Riaddestra il personaggio per una nuova armatura libera
    (richiesto in chat) - rilascia quella vecchia, ne reclama una
    nuova, genera un nuovo Maestro e nuovi compagni, azzera la tappa
    dell'addestramento. Il livello e le statistiche già guadagnate
    RESTANO (richiesto in chat implicito: non si riparte da zero, solo
    il percorso per QUESTA specifica armatura ricomincia). Muta
    `knight` in place e lo restituisce; il chiamante deve comunque fare
    save_knight dopo."""
    new_armor = pick_available_armor(conn, knight["player_level"], knight["armor_name"])
    if new_armor is None:
        raise RuntimeError("Nessuna armatura libera disponibile per il riaddestramento.")

    release_roster_slot(conn, knight["armor_name"])
    claim_roster_slot(conn, new_armor["name"], knight["id"])

    master_name, master_armor_name = select_master(conn, new_armor["divinity"], new_armor["faction"])
    companion1_name, companion2_name = generate_companions(exclude_name=master_name)

    knight["armor_name"] = new_armor["name"]
    knight["training_stage"] = 1
    knight["master_name"] = master_name
    knight["master_armor_name"] = master_armor_name
    knight["companion1_name"] = companion1_name
    knight["companion2_name"] = companion2_name
    knight["apprentice_status"] = ""
    return knight
