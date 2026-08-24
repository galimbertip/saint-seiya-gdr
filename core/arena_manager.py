"""
Gestore dell'Arena del Santuario.

Decisione di design (discussa in chat): l'avversario non è scritto a
mano né è un altro giocatore (nessuna infrastruttura di rete) - viene
GENERATO dal catalogo armature che abbiamo già: si pesca un'armatura di
livello comparabile al tuo, le si danno le sue tecniche vere, e diventa
un "rivale" per lo scontro. Zero dati nuovi da inventare.

Il Cosmo attuale (cosmo_cur) fa da "punti vita" in combattimento, sia
per il giocatore che per l'avversario - niente nuovo campo HP, e resta
in tema (il Cosmo si affievolisce sotto i colpi).

NOTA come per dnd_engine.py e fm_manager.py: le soglie (tolleranza di
livello per l'avversario, potenza dell'Attacco Base, recupero Cosmo a
fine scontro) sono PLACEHOLDER funzionanti, da tarare insieme.
"""
import random
import sqlite3

from core.dnd_engine import DnDEngine
from database.db_manager import get_techniques_for_armor

OPPONENT_LEVEL_TOLERANCE = 20  # cerca avversari con livello armatura entro +-20 dal tuo
BASE_ATTACK_POWER = 20  # "Attacco Base": nessuna tecnica richiesta, ma debole

# PLACEHOLDER: bonus di "sintonia cosmica" alla Classe Armatura.
# calculate_ac si aspettava un valore piccolo (0-100 circa), ma qui il
# Cosmo attuale fa da HP e vale 100-250+ - usarlo direttamente fa
# esplodere la CA a 40+ (vedi test in chat: nessun colpo va a segno in
# 30 round). Anche un valore fisso "moderato" tipo 50 si è rivelato
# comunque troppo alto: con dex_mod+armor_bonus la CA arrivava a 25,
# irraggiungibile per un tiro d20+1 (max 21) - IMPOSSIBILE colpire
# anche con un 20 naturale. Per ora azzerato del tutto, finché non
# progettiamo "sintonia cosmica" come statistica separata e bilanciata.
COSMO_ATTUNEMENT_FOR_AC = 0


def generate_opponent(conn: sqlite3.Connection, player_armor_level: int,
                       exclude_armor_name: str | None = None) -> dict:
    """Genera un avversario dal catalogo armature, di livello comparabile
    al tuo. Se non trova nessuna armatura nella tolleranza (es. livelli
    estremi), allarga la ricerca a tutto il catalogo piuttosto che
    fallire."""
    rows = conn.execute(
        "SELECT * FROM armors WHERE ABS(level - ?) <= ?",
        (player_armor_level, OPPONENT_LEVEL_TOLERANCE),
    ).fetchall()

    candidates = [r for r in rows if r["name"] != exclude_armor_name]
    if not candidates:
        all_rows = conn.execute("SELECT * FROM armors").fetchall()
        candidates = [r for r in all_rows if r["name"] != exclude_armor_name] or list(all_rows)

    armor = random.choice(candidates)
    techniques = [dict(t) for t in get_techniques_for_armor(armor["name"], conn)]
    cosmo = 100 + armor["level"]

    return {
        "name": f"Rivale in {armor['name']}",
        "armor_name": armor["name"],
        "divinity": armor["divinity"],
        "faction": armor["faction"],
        "armor_level": armor["level"],
        "cosmo_cur": cosmo,
        "cosmo_max": cosmo,
        "str": 10 + armor["level"] // 10,
        "dex": 10 + armor["level"] // 10,
        "techniques": techniques,
    }


def resolve_turn(attacker_name: str, attacker_str: int, attacker_armor_level: int,
                  defender_name: str, defender_dex: int, defender_armor_level: int,
                  technique_name: str, technique_power: int) -> tuple[int, str]:
    """Risolve un turno d'attacco riusando DnDEngine (CA, tiro per
    colpire, danno) - qui si orchestra soltanto, nessuna nuova formula.
    Restituisce (danno_inflitto, messaggio_di_log)."""
    defender_ac = DnDEngine.calculate_ac(
        DnDEngine.get_modifier(defender_dex), defender_armor_level, COSMO_ATTUNEMENT_FOR_AC
    )
    hit, dice_roll, attack_total = DnDEngine.resolve_attack(attacker_str, defender_ac)

    if not hit:
        return 0, f"{attacker_name} lancia {technique_name}, ma {defender_name} schiva! ({attack_total} vs CA {defender_ac})"

    _, damage = DnDEngine.resolve_technique_damage(technique_power, attacker_armor_level)
    return damage, (f"{attacker_name} colpisce con {technique_name}! "
                     f"({attack_total} vs CA {defender_ac}) — Danno: {damage}")


def choose_opponent_technique(opponent: dict) -> tuple[str, int]:
    """Sceglie una tecnica a caso tra quelle dell'avversario, o l'Attacco
    Base se non ne ha nessuna. Restituisce (nome, potenza)."""
    if opponent["techniques"]:
        t = random.choice(opponent["techniques"])
        return t["name"], t["power"]
    return "Attacco Base", BASE_ATTACK_POWER


# --- Sensi del Cosmo ------------------------------------------------------
# Soglie legate al player_level (il livello del PERSONAGGIO, non
# dell'armatura), coerenti col canone di Saint Seiya (verificato in
# chat): il Settimo Senso "brucia il Cosmo al massimo" e nei Bronze
# Saint si risveglia da solo in punto di rottura - qui lo traduco in un
# trigger automatico sotto una soglia critica di Cosmo, non un
# pulsante. L'Ottavo (trascendere la morte) idem: automatico, una
# volta a combattimento. Il Nono (Big Will, ascesa alla divinità) è
# dichiarato ma senza effetto meccanico per ora - fuori portata.
SESTO_SENSO_LEVEL = 3
SETTIMO_SENSO_LEVEL = 10
OTTAVO_SENSO_LEVEL = 20
NONO_SENSO_LEVEL = 50  # placeholder narrativo, nessun effetto meccanico oggi

SEVENTH_SENSE_COSMO_RATIO = 0.2  # sotto il 20% del Cosmo massimo
SEVENTH_SENSE_MULTIPLIER = 2.0

CHARGE_COSMO_COST = 15
CHARGE_DAMAGE_MULTIPLIER = 1.5

DEFAULT_DEFENSE_POWER = 10  # "Parata" generica, per chi non ha una tecnica difensiva


def get_unlocked_senses(player_level: int) -> dict:
    """Quali sensi sono sbloccati al livello personaggio dato."""
    return {
        "sesto": player_level >= SESTO_SENSO_LEVEL,
        "settimo": player_level >= SETTIMO_SENSO_LEVEL,
        "ottavo": player_level >= OTTAVO_SENSO_LEVEL,
        "nono": player_level >= NONO_SENSO_LEVEL,
    }


def find_defensive_technique(techniques: list[dict]) -> dict | None:
    """Cerca una tecnica di tipo 'Difensivo/...' tra quelle date. Solo il
    30% circa delle armature ne ha una (verificato in chat) - se non
    c'è, chi chiama userà la Parata generica (DEFAULT_DEFENSE_POWER)."""
    for t in techniques:
        if "difensiv" in (t.get("tech_type") or "").lower():
            return t
    return None


def resolve_defense(raw_damage: int, defense_technique_power: int | None) -> int:
    """Riduce il danno grezzo in base alla potenza della tecnica
    difensiva (o della Parata generica, se non ne hai una)."""
    defense_power = defense_technique_power if defense_technique_power is not None else DEFAULT_DEFENSE_POWER
    reduction = round(defense_power / 10)
    return max(0, raw_damage - reduction)


def choose_opponent_action(opponent: dict) -> tuple[str, dict | None]:
    """Sceglie l'azione PROATTIVA dell'avversario: Attacca o Carica.
    Difendi non è più una scelta proattiva 'alla cieca' - è reattiva
    (vedi opponent_reacts), decisa solo quando è l'avversario a SUBIRE
    un attacco, non quando lo dichiara lui."""
    action = random.choices(["attacca", "carica"], weights=[0.8, 0.2])[0]

    if action == "attacca":
        name, power = choose_opponent_technique(opponent)
        return "attacca", {"name": name, "power": power}
    return "carica", None


def opponent_reacts(opponent: dict) -> dict | None:
    """Decide SE l'avversario si difende dal colpo appena dichiarato
    contro di lui (reattivo: la scelta avviene dopo aver 'visto' il tuo
    attacco, non prima). Più probabile se il suo Cosmo è già basso -
    un avversario messo male para più spesso. Restituisce la tecnica
    usata per difendersi (vera o Parata generica), o None se incassa."""
    cosmo_ratio = opponent["cosmo_cur"] / max(opponent["cosmo_max"], 1)
    defend_chance = 0.25 + (0.35 if cosmo_ratio < 0.3 else 0.0)
    if random.random() > defend_chance:
        return None

    defensive = find_defensive_technique(opponent["techniques"])
    if defensive:
        return dict(defensive)
    return {"name": "Parata", "power": DEFAULT_DEFENSE_POWER, "tech_type": "Difensivo"}
