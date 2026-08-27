"""
Creazione e recupero personaggi. Mette insieme db_manager (persistenza)
e il catalogo armature, così la creazione di un cavaliere:
  - può scegliere SOLO un'armatura che esiste davvero nel catalogo
  - non può scegliere un'armatura sopra al proprio player_level
    (validazione di min_player_level, prima assente)
  - parte con statistiche derivate dall'armatura scelta, non più
    fisse a 10/10/10/10/10 per chiunque

NOTA come per dnd_engine.py e fm_manager.py: la formula che deriva le
statistiche iniziali dal livello dell'armatura è un PLACEHOLDER
funzionante (bonus lineare semplice), non il bilanciamento definitivo -
la struttura (che ci sia una dipendenza reale statistiche<->armatura)
è quella buona, i numeri si tarano con le dinamiche.
"""
import random
import sqlite3

from database.db_manager import (
    get_armor, list_armors_for_player_level, get_roster_entry, insert_roster_entry, claim_roster_slot,
)
from core.arena_manager import OPPONENT_FIRST_NAMES, OPPONENT_SURNAMES

STARTING_COSMO_BASE = 100
STARTING_STAT_BASE = 10

# Corporatura: richiesta in chat, sposta la Costituzione di partenza -
# un cavaliere robusto incassa meglio, uno minuto un po' meno. Piccoli
# scarti (non uno squilibrio), applicati una volta sola alla creazione.
BUILD_CON_BONUS = {"Minuta": -1, "Media": 0, "Robusta": 2}


class ArmorAlreadyClaimedError(ValueError):
    pass


class ArmorNotFoundError(ValueError):
    pass


class ArmorLevelTooHighError(ValueError):
    pass


def _starting_stats(armor_level: int) -> dict:
    """PLACEHOLDER: statistiche iniziali derivate dal livello armatura.
    Bonus lineare semplice (0-10 punti extra distribuiti equamente su
    tutte e 5 le statistiche), da ritarare con le dinamiche vere."""
    bonus = armor_level // 20  # 0-5
    return {
        "str": STARTING_STAT_BASE + bonus,
        "dex": STARTING_STAT_BASE + bonus,
        "con": STARTING_STAT_BASE + bonus,
        "tec": STARTING_STAT_BASE + bonus,
        "vol": STARTING_STAT_BASE + bonus,
    }


def list_available_armors(conn: sqlite3.Connection, player_level: int) -> list[sqlite3.Row]:
    """Armature selezionabili in creazione personaggio, dato il livello
    del giocatore. Wrapper diretto su db_manager, qui per comodità
    (la GUI parlerà solo con character_factory, non col DB direttamente)."""
    return list_armors_for_player_level(player_level, conn)


def create_knight(conn: sqlite3.Connection, raw_name: str, armor_name: str,
                   player_level: int = 1, surname: str = "", age: int = 15,
                   gender: str = "", origin: str = "", build: str = "Media") -> dict:
    """Crea un nuovo cavaliere, validando armatura e livello. Solleva
    ArmorNotFoundError / ArmorLevelTooHighError se la scelta non è valida,
    invece di salvare comunque come faceva la versione di Gemini.
    ArmorAlreadyClaimedError se l'armatura è già portata da un altro
    personaggio giocatore (richiesto in chat: la gerarchia è 1 a 1, un
    solo occupante per slot - il PNG fisso finché nessuno la reclama).
    surname/gender/origin: dettagli narrativi opzionali del personaggio
    (richiesti in chat per la creazione 'come vuoi tu') - nessun
    collegamento con dati reali del giocatore, sono del personaggio.
    build ('Minuta'/'Media'/'Robusta'): sposta la Costituzione di
    partenza (vedi BUILD_CON_BONUS) - anche questo richiesto in chat,
    per dare un effetto MECCANICO reale alla corporatura scelta, non
    solo narrativo."""

    armor = get_armor(armor_name, conn)
    if armor is None:
        raise ArmorNotFoundError(f"Armatura {armor_name!r} non trovata nel catalogo.")

    if armor["min_player_level"] > player_level:
        raise ArmorLevelTooHighError(
            f"{armor_name!r} richiede livello giocatore {armor['min_player_level']}, "
            f"ma il personaggio è livello {player_level}."
        )

    roster_entry = get_roster_entry(conn, armor_name)
    if roster_entry is not None and roster_entry["claimed_by_knight_id"] is not None:
        raise ArmorAlreadyClaimedError(
            f"{armor_name!r} è già portata da un altro cavaliere - scegline un'altra dalla Gerarchia."
        )

    stats = _starting_stats(armor["level"])
    stats["con"] = max(1, stats["con"] + BUILD_CON_BONUS.get(build, 0))
    cosmo = STARTING_COSMO_BASE + armor["level"]
    full_display_name = f"{raw_name} {surname}".strip()
    formal_name = f"{full_display_name} di {armor_name}"

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO knights (formal_name, raw_name, armor_name, cosmo_cur, cosmo_max,
                              str, dex, con, tec, vol, player_level, xp, stamina, age,
                              surname, gender, origin, build)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 100, ?, ?, ?, ?, ?)
        """,
        (formal_name, raw_name, armor_name, cosmo, cosmo,
         stats["str"], stats["dex"], stats["con"], stats["tec"], stats["vol"], player_level,
         age, surname, gender, origin, build),
    )
    conn.commit()

    claim_roster_slot(conn, armor_name, cur.lastrowid)

    return get_knight(conn, cur.lastrowid)


def ensure_roster_populated(conn: sqlite3.Connection) -> int:
    """Genera un PNG fisso per ogni armatura del catalogo che non ne ha
    ancora uno - va richiamata all'avvio, come refresh_armors_catalog
    (richiesto in chat). Sicura da richiamare più volte: ignora le
    armature che hanno già uno slot (il nome del PNG non deve mai
    cambiare una volta assegnato). Restituisce quanti PNG nuovi sono
    stati generati in questa chiamata."""
    all_armors = conn.execute("SELECT name FROM armors").fetchall()
    creati = 0
    for row in all_armors:
        if get_roster_entry(conn, row["name"]) is None:
            npc_name = f"{random.choice(OPPONENT_FIRST_NAMES)} {random.choice(OPPONENT_SURNAMES)}"
            insert_roster_entry(conn, row["name"], npc_name)
            creati += 1
    conn.commit()
    return creati


def get_knight(conn: sqlite3.Connection, knight_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM knights WHERE id = ?", (knight_id,)).fetchone()
    return dict(row) if row else None


def list_knights(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM knights ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def delete_knight(conn: sqlite3.Connection, knight_id: int) -> None:
    """Elimina definitivamente un personaggio. Nessuna altra tabella
    referenzia knights (è armors/techniques ad essere referenziate DA
    knights, non il contrario), quindi è sempre un'operazione sicura."""
    conn.execute("DELETE FROM knights WHERE id = ?", (knight_id,))
    conn.commit()


def save_knight(conn: sqlite3.Connection, knight: dict) -> None:
    """Salva le modifiche di un knight (es. dopo un allenamento o un
    combattimento) tornando dal dict in memoria al DB."""
    conn.execute(
        """
        UPDATE knights SET cosmo_cur=?, cosmo_max=?, str=?, dex=?, con=?, tec=?, vol=?,
                            player_level=?, xp=?, stamina=?, age=?, game_day=?, game_minutes=?, weekly_schedule=?
        WHERE id=?
        """,
        (knight["cosmo_cur"], knight["cosmo_max"], knight["str"], knight["dex"], knight["con"],
         knight["tec"], knight["vol"], knight["player_level"], knight["xp"], knight["stamina"],
         knight["age"], knight["game_day"], knight["game_minutes"], knight["weekly_schedule"], knight["id"]),
    )
    conn.commit()
