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
from datetime import datetime

from database.db_manager import (
    get_armor, list_armors_for_player_level, get_roster_entry, insert_roster_entry, claim_roster_slot,
    add_biography_entry,
)
from core.arena_manager import OPPONENT_FIRST_NAMES, OPPONENT_SURNAMES
from core.training_path import select_master, generate_companions
from core.fm_manager import get_calendar_display

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
                   gender: str = "", origin: str = "", build: str = "Media",
                   biography: str = "", skin_tone: str = "", hair_color: str = "") -> dict:
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
    solo narrativo.
    biography: l'abbozzo iniziale del diario (richiesto in chat) - da
    qui in poi il gioco stesso aggiunge voci (level up, Sensi,
    vittorie/sconfitte) in biography_entries, vedi
    database.db_manager.add_biography_entry.
    skin_tone/hair_color: personalizzano la sagoma stilizzata
    (richiesto in chat) - l'avatar caricato (vedi avatar_path,
    impostato a parte via l'endpoint di upload) ha sempre la
    precedenza quando presente."""

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
    # Calendario reale (richiesto in chat): il personaggio "nasce" nel
    # momento vero in cui viene creato - il calendario di gioco parte
    # da qui, non da un "Anno 1" fittizio.
    created_at = datetime.now().isoformat()

    # Apprendistato (richiesto in chat): un personaggio che nasce a
    # livello 1 è un vero esordiente - deve completare l'addestramento
    # prima di poter mettere piede in Arena. Chi dichiara già un
    # livello più alto in creazione (un "veterano") salta l'apprendistato
    # per intero, esattamente come oggi - non ha senso rimandarlo a
    # scuola se si dichiara già affermato.
    is_knight = 1 if player_level > 1 else 0
    master_name = master_armor_name = companion1_name = companion2_name = ""
    if not is_knight:
        master_name, master_armor_name = select_master(conn, armor["divinity"], armor["faction"])
        companion1_name, companion2_name = generate_companions(exclude_name=master_name)

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO knights (formal_name, raw_name, armor_name, cosmo_cur, cosmo_max,
                              str, dex, con, tec, vol, player_level, xp, stamina, age,
                              surname, gender, origin, build, biography, skin_tone, hair_color, created_at,
                              is_knight, master_name, master_armor_name, companion1_name, companion2_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 100, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (formal_name, raw_name, armor_name, cosmo, cosmo,
         stats["str"], stats["dex"], stats["con"], stats["tec"], stats["vol"], player_level,
         age, surname, gender, origin, build, biography, skin_tone, hair_color, created_at,
         is_knight, master_name, master_armor_name, companion1_name, companion2_name),
    )
    conn.commit()

    claim_roster_slot(conn, armor_name, cur.lastrowid)

    if not is_knight:
        # Diario auto-scritto (richiesto in chat): il momento in cui
        # inizia l'addestramento merita una voce, con Maestro/armatura e
        # compagni - prima non c'era traccia di questo nel Diario.
        cal = get_calendar_display(created_at, 0)
        add_biography_entry(
            conn, cur.lastrowid, 0,
            f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {raw_name} inizia il proprio "
            f"addestramento sotto la guida di {master_name} ({master_armor_name}), "
            f"insieme a {companion1_name} e {companion2_name}.",
        )

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
                            player_level=?, xp=?, stamina=?, age=?, game_day=?, game_minutes=?, weekly_schedule=?,
                            surname=?, gender=?, origin=?, build=?, tutorial_seen=?, biography=?,
                            skin_tone=?, hair_color=?, avatar_path=?, created_at=?,
                            is_knight=?, training_stage=?, master_name=?, master_armor_name=?,
                            companion1_name=?, companion2_name=?, arena_background_path=?
        WHERE id=?
        """,
        (knight["cosmo_cur"], knight["cosmo_max"], knight["str"], knight["dex"], knight["con"],
         knight["tec"], knight["vol"], knight["player_level"], knight["xp"], knight["stamina"],
         knight["age"], knight["game_day"], knight["game_minutes"], knight["weekly_schedule"],
         knight["surname"], knight["gender"], knight["origin"], knight["build"], knight["tutorial_seen"],
         knight["biography"], knight["skin_tone"], knight["hair_color"], knight["avatar_path"],
         knight["created_at"], knight["is_knight"], knight["training_stage"], knight["master_name"],
         knight["master_armor_name"], knight["companion1_name"], knight["companion2_name"],
         knight["arena_background_path"], knight["id"]),
    )
    conn.commit()
