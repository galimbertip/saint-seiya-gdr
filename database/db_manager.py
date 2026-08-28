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
    origin TEXT NOT NULL DEFAULT '',
    build TEXT NOT NULL DEFAULT 'Media',
    tutorial_seen INTEGER NOT NULL DEFAULT 0,
    biography TEXT NOT NULL DEFAULT '',
    skin_tone TEXT NOT NULL DEFAULT '',
    hair_color TEXT NOT NULL DEFAULT '',
    avatar_path TEXT NOT NULL DEFAULT ''
);

-- Diario del cavaliere (richiesto in chat): l'abbozzo scritto dal
-- giocatore alla creazione vive nella colonna biography di knights;
-- qui invece le voci che il gioco stesso aggiunge nel tempo (level up,
-- Sensi sbloccati, vittorie/sconfitte in Arena) - una riga per evento,
-- non un unico blob di testo, così restano ordinabili e non c'è mai
-- il rischio di sovrascrivere quello che è già stato scritto.
CREATE TABLE IF NOT EXISTS biography_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knight_id INTEGER NOT NULL,
    game_minutes INTEGER NOT NULL,
    entry TEXT NOT NULL,
    FOREIGN KEY (knight_id) REFERENCES knights(id) ON DELETE CASCADE
);

-- Gerarchia dei cavalieri (richiesta in chat): ogni armatura del
-- catalogo ha un PNG fisso assegnato una volta sola (npc_name, non
-- cambia mai) - finché nessun giocatore la reclama, è quel PNG a
-- "occupare" lo slot. claimed_by_knight_id punta al personaggio che
-- l'ha presa; ON DELETE SET NULL fa "tornare" automaticamente il PNG
-- quando quel personaggio viene eliminato, senza bisogno di codice
-- applicativo apposta.
CREATE TABLE IF NOT EXISTS roster (
    armor_name TEXT PRIMARY KEY,
    npc_name TEXT NOT NULL,
    claimed_by_knight_id INTEGER,
    FOREIGN KEY (armor_name) REFERENCES armors(name),
    FOREIGN KEY (claimed_by_knight_id) REFERENCES knights(id) ON DELETE SET NULL
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
    if "build" not in existing_columns:
        # Corporatura (richiesta in chat) - sposta la Costituzione di
        # partenza, ma solo alla CREAZIONE: per i personaggi già
        # esistenti non tocchiamo le statistiche già in gioco, solo
        # etichettiamo 'Media' (nessun bonus/malus retroattivo).
        conn.execute("ALTER TABLE knights ADD COLUMN build TEXT NOT NULL DEFAULT 'Media'")
        conn.commit()
        log.info("Migrazione: aggiunta colonna build a knights ('Media' per i salvataggi esistenti, nessun effetto retroattivo sulle statistiche).")
    if "tutorial_seen" not in existing_columns:
        # Tutorial iniziale skippabile (richiesto in chat) - i
        # personaggi già esistenti lo segniamo già visto (1): non ha
        # senso mostrarlo a chi gioca già da prima che esistesse.
        conn.execute("ALTER TABLE knights ADD COLUMN tutorial_seen INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE knights SET tutorial_seen = 1")
        conn.commit()
        log.info("Migrazione: aggiunta colonna tutorial_seen a knights (personaggi esistenti segnati come già visto).")
    if "biography" not in existing_columns:
        # Diario del cavaliere (richiesto in chat) - l'abbozzo iniziale;
        # vuoto per i personaggi già esistenti, nessuno lo aveva scritto.
        conn.execute("ALTER TABLE knights ADD COLUMN biography TEXT NOT NULL DEFAULT ''")
        conn.commit()
        log.info("Migrazione: aggiunta colonna biography a knights (vuota per i salvataggi esistenti).")
    if "avatar_path" not in existing_columns:
        # Avatar del cavaliere (richiesto in chat): tono pelle/colore
        # capelli per la sagoma stilizzata, più il percorso di
        # un'eventuale immagine caricata dal giocatore (vuoto = usa la
        # sagoma). Tutti vuoti per i salvataggi esistenti.
        conn.execute("ALTER TABLE knights ADD COLUMN skin_tone TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE knights ADD COLUMN hair_color TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE knights ADD COLUMN avatar_path TEXT NOT NULL DEFAULT ''")
        conn.commit()
        log.info("Migrazione: aggiunte colonne skin_tone/hair_color/avatar_path a knights.")


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


def get_roster(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """La gerarchia completa: ogni armatura con chi la 'occupa' - il
    PNG fisso se nessuno l'ha reclamata, o il personaggio giocatore che
    l'ha presa (richiesto in chat). Ordinata per divinità/fazione/
    livello, così la pagina può raggrupparle a colpo d'occhio."""
    return conn.execute(
        """
        SELECT r.armor_name, r.npc_name, r.claimed_by_knight_id,
               a.divinity, a.faction, a.level,
               k.raw_name AS claimed_by_raw_name, k.surname AS claimed_by_surname,
               k.player_level AS claimed_by_level
        FROM roster r
        JOIN armors a ON a.name = r.armor_name
        LEFT JOIN knights k ON k.id = r.claimed_by_knight_id
        ORDER BY a.divinity, a.faction, a.level
        """
    ).fetchall()


def get_roster_entry(conn: sqlite3.Connection, armor_name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM roster WHERE armor_name = ?", (armor_name,)).fetchone()


def insert_roster_entry(conn: sqlite3.Connection, armor_name: str, npc_name: str) -> None:
    """Crea lo slot per un'armatura con il suo PNG fisso - ignorata (non
    sovrascrive) se esiste già, perché il nome del PNG non deve mai
    cambiare una volta assegnato (richiesto in chat)."""
    conn.execute(
        "INSERT OR IGNORE INTO roster (armor_name, npc_name, claimed_by_knight_id) VALUES (?, ?, NULL)",
        (armor_name, npc_name),
    )


def claim_roster_slot(conn: sqlite3.Connection, armor_name: str, knight_id: int) -> None:
    """Un personaggio giocatore reclama lo slot della sua armatura - il
    PNG 'si fa da parte' (resta nel database ma non compare più come
    occupante finché lo slot è reclamato)."""
    conn.execute("UPDATE roster SET claimed_by_knight_id = ? WHERE armor_name = ?", (knight_id, armor_name))
    conn.commit()


def add_biography_entry(conn: sqlite3.Connection, knight_id: int, game_minutes: int, entry: str) -> None:
    """Aggiunge una voce al diario auto-scritto del personaggio
    (richiesto in chat) - una riga per evento (level up, Senso
    sbloccato, vittoria/sconfitta in Arena), non un unico testo
    riscritto ogni volta."""
    conn.execute(
        "INSERT INTO biography_entries (knight_id, game_minutes, entry) VALUES (?, ?, ?)",
        (knight_id, game_minutes, entry),
    )
    conn.commit()


def get_biography_entries(conn: sqlite3.Connection, knight_id: int) -> list[sqlite3.Row]:
    """Tutte le voci del diario di un personaggio, in ordine cronologico."""
    return conn.execute(
        "SELECT * FROM biography_entries WHERE knight_id = ? ORDER BY id ASC", (knight_id,)
    ).fetchall()


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
