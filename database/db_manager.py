"""
Gestione del database SQLite.

Tre tabelle (vedi schema discusso in chat):
  armors      -> catalogo di riferimento, popolato dall'import CSV
  techniques  -> catalogo di riferimento, popolato dall'import CSV
  knights     -> l'unica tabella "viva", i personaggi giocanti

armors/techniques vengono ricreate ad ogni avvio a partire dai CSV
(sono dati di sola lettura per il giocatore): così se aggiorni un CSV
e rilanci l'app, il catalogo si aggiorna da solo, senza migrazioni a
mano. knights invece è persistente e non viene mai toccata dall'import.
"""
import sqlite3
from pathlib import Path

from core.data_loader import load_armors_database
from core.app_logger import get_logger

log = get_logger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "saint_seiya.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS armors (
    name TEXT PRIMARY KEY,
    divinity TEXT NOT NULL,
    faction TEXT NOT NULL,
    level INTEGER NOT NULL,
    min_player_level INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS techniques (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    armor_name TEXT NOT NULL REFERENCES armors(name),
    name TEXT NOT NULL,
    tech_type TEXT,
    launch_desc TEXT,
    effect_desc TEXT,
    power INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS knights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    formal_name TEXT NOT NULL,
    raw_name TEXT NOT NULL,
    armor_name TEXT NOT NULL REFERENCES armors(name),
    cosmo_cur INTEGER NOT NULL,
    cosmo_max INTEGER NOT NULL,
    str INTEGER NOT NULL,
    dex INTEGER NOT NULL,
    con INTEGER NOT NULL,
    tec INTEGER NOT NULL,
    vol INTEGER NOT NULL,
    player_level INTEGER NOT NULL DEFAULT 1,
    xp INTEGER NOT NULL DEFAULT 0,
    stamina INTEGER NOT NULL DEFAULT 100,
    age INTEGER NOT NULL DEFAULT 15,
    game_day INTEGER NOT NULL DEFAULT 1,
    game_minutes INTEGER NOT NULL DEFAULT 0,
    weekly_schedule TEXT NOT NULL DEFAULT 'Cosmo,Forza,Destrezza,Costituzione,Tecnica,Volontà,Riposo',
    surname TEXT NOT NULL DEFAULT '',
    gender TEXT NOT NULL DEFAULT '',
    origin TEXT NOT NULL DEFAULT ''
);
"""


def _ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    """Aggiunge colonne nuove alle tabelle già esistenti, senza perdere
    i dati già salvati (es. il tuo 'Garin' creato prima che esistesse
    game_day/weekly_schedule/game_minutes). SQLite non supporta 'ADD
    COLUMN IF NOT EXISTS', quindi controlliamo noi se la colonna manca
    prima di aggiungerla."""
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(knights)")}
    if "game_day" not in existing_columns:
        conn.execute("ALTER TABLE knights ADD COLUMN game_day INTEGER NOT NULL DEFAULT 1")
        conn.commit()
        log.info("Migrazione: aggiunta colonna game_day a knights (salvataggi esistenti impostati a giorno 1).")
    if "game_minutes" not in existing_columns:
        # L'orologio a giorni interi (game_day) diventa un orologio a
        # minuti (game_minutes) - fonte di verità da ora in poi. Per i
        # salvataggi esistenti, convertiamo il giorno già raggiunto in
        # minuti equivalenti (mezzanotte di quel giorno), così non si
        # perde il progresso già fatto.
        conn.execute("ALTER TABLE knights ADD COLUMN game_minutes INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE knights SET game_minutes = (game_day - 1) * 1440")
        conn.commit()
        log.info("Migrazione: aggiunta colonna game_minutes a knights, convertita da game_day esistente.")
    if "weekly_schedule" not in existing_columns:
        conn.execute(
            "ALTER TABLE knights ADD COLUMN weekly_schedule TEXT NOT NULL "
            "DEFAULT 'Cosmo,Forza,Destrezza,Costituzione,Tecnica,Volontà,Riposo'"
        )
        conn.commit()
        log.info("Migrazione: aggiunta colonna weekly_schedule a knights (programma di default per i salvataggi esistenti).")
    if "surname" not in existing_columns:
        # Creazione personaggio più dettagliata (richiesta in chat):
        # Cognome, Sesso, Provenienza - dati puramente narrativi del
        # personaggio, nessun collegamento con dati reali del giocatore.
        conn.execute("ALTER TABLE knights ADD COLUMN surname TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE knights ADD COLUMN gender TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE knights ADD COLUMN origin TEXT NOT NULL DEFAULT ''")
        conn.commit()
        log.info("Migrazione: aggiunte colonne surname/gender/origin a knights (vuote per i salvataggi esistenti).")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """Crea le tabelle se non esistono. Non tocca mai knights se già popolata."""
    own_conn = conn is None
    conn = conn or get_connection()
    conn.executescript(SCHEMA)
    _ensure_schema_migrations(conn)
    conn.commit()
    if own_conn:
        conn.close()


def refresh_armors_catalog(conn: sqlite3.Connection | None = None) -> int:
    """Ricarica armors + techniques dai CSV via data_loader.

    IMPORTANTE (fix PG_V0.1.1): non fa più DELETE + INSERT su tutta la
    tabella armors, perché se un cavaliere già salvato punta a
    un'armatura (knights.armor_name), SQLite blocca la cancellazione di
    quella riga per via del vincolo di foreign key - giustamente, visto
    che altrimenti il personaggio rimarrebbe con un riferimento rotto.

    Ora usa un UPSERT (INSERT ... ON CONFLICT DO UPDATE): le armature
    esistenti vengono aggiornate sul posto, mai cancellate e ricreate.
    Le uniche armature rimosse sono quelle non più presenti nei CSV E
    non referenziate da nessun cavaliere - quindi sicure da eliminare.

    Non tocca mai la tabella knights. Restituisce il numero di armature
    caricate dai CSV in questa passata."""
    own_conn = conn is None
    conn = conn or get_connection()

    armors = load_armors_database()
    log.info("Refresh catalogo: %d armature lette dai CSV", len(armors))

    cur = conn.cursor()

    # Le tecniche non sono mai referenziate da nessun'altra tabella:
    # sicuro cancellarle e ricrearle sempre da zero.
    cur.execute("DELETE FROM techniques")

    # Rimuovi solo le armature "orfane": non più nei CSV E non usate da
    # nessun cavaliere esistente. Quelle usate da un cavaliere restano,
    # anche se sparite dai CSV, per non rompere il riferimento.
    current_names = [a.name for a in armors.values()]
    if current_names:
        placeholders = ",".join("?" for _ in current_names)
        cur.execute(
            f"""
            DELETE FROM armors
            WHERE name NOT IN ({placeholders})
              AND name NOT IN (SELECT DISTINCT armor_name FROM knights)
            """,
            current_names,
        )
        removed = cur.rowcount
        if removed:
            log.info("Rimosse %d armature obsolete (non più nei CSV, nessun cavaliere le usa)", removed)

    for armor in armors.values():
        cur.execute(
            """
            INSERT INTO armors (name, divinity, faction, level, min_player_level)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                divinity = excluded.divinity,
                faction = excluded.faction,
                level = excluded.level,
                min_player_level = excluded.min_player_level
            """,
            (armor.name, armor.divinity, armor.faction, armor.level, armor.min_player_level),
        )
        for t in armor.techniques:
            cur.execute(
                "INSERT INTO techniques (armor_name, name, tech_type, launch_desc, effect_desc, power) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (armor.name, t.name, t.tech_type, t.launch_desc, t.effect_desc, t.power),
            )

    conn.commit()
    log.info("Refresh catalogo completato senza errori.")
    if own_conn:
        conn.close()
    return len(armors)


def get_armor(name: str, conn: sqlite3.Connection | None = None) -> sqlite3.Row | None:
    own_conn = conn is None
    conn = conn or get_connection()
    row = conn.execute("SELECT * FROM armors WHERE name = ?", (name,)).fetchone()
    if own_conn:
        conn.close()
    return row


def get_techniques_for_armor(name: str, conn: sqlite3.Connection | None = None) -> list[sqlite3.Row]:
    own_conn = conn is None
    conn = conn or get_connection()
    rows = conn.execute("SELECT * FROM techniques WHERE armor_name = ?", (name,)).fetchall()
    if own_conn:
        conn.close()
    return rows


def list_armors_for_player_level(player_level: int, conn: sqlite3.Connection | None = None) -> list[sqlite3.Row]:
    """Armature scelte in creazione personaggio: solo quelle che il
    giocatore può già usare al suo livello."""
    own_conn = conn is None
    conn = conn or get_connection()
    rows = conn.execute(
        "SELECT * FROM armors WHERE min_player_level <= ? ORDER BY level DESC", (player_level,)
    ).fetchall()
    if own_conn:
        conn.close()
    return rows


if __name__ == "__main__":
    conn = get_connection()
    init_db(conn)
    n = refresh_armors_catalog(conn)
    print(f"[db_manager] Catalogo caricato: {n} armature.")

    # Verifica rapida
    row = get_armor("Scale di Chrysaor", conn)
    print(dict(row))
    for t in get_techniques_for_armor("Scale di Chrysaor", conn):
        print("  -", t["name"], t["power"])

    lvl1 = list_armors_for_player_level(1, conn)
    print(f"\nArmature disponibili a livello 1: {len(lvl1)}")
    conn.close()
