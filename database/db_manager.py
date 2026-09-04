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
from datetime import datetime

from core.data_loader import load_armors_database
from core.app_logger import get_logger

log = get_logger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "saint_seiya.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS world_clock (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    minutes INTEGER NOT NULL DEFAULT 0,
    last_npc_tick_minutes INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO world_clock (id, minutes) VALUES (1, 0);

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
    vita_cur INTEGER NOT NULL DEFAULT 100,
    vita_max INTEGER NOT NULL DEFAULT 100,
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
    avatar_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    is_knight INTEGER NOT NULL DEFAULT 1,
    training_stage INTEGER NOT NULL DEFAULT 0,
    master_name TEXT NOT NULL DEFAULT '',
    master_armor_name TEXT NOT NULL DEFAULT '',
    companion1_name TEXT NOT NULL DEFAULT '',
    companion2_name TEXT NOT NULL DEFAULT '',
    arena_background_path TEXT NOT NULL DEFAULT '',
    arena_backgrounds TEXT NOT NULL DEFAULT '{}',
    denaro INTEGER NOT NULL DEFAULT 0,
    renown INTEGER NOT NULL DEFAULT 0,
    mission_id TEXT NOT NULL DEFAULT '',
    mission_stage INTEGER NOT NULL DEFAULT 0,
    mission_node TEXT NOT NULL DEFAULT '',
    mission_flags TEXT NOT NULL DEFAULT '',
    tournament_bracket TEXT NOT NULL DEFAULT '',
    mission_counter INTEGER NOT NULL DEFAULT 0,
    apprentice_status TEXT NOT NULL DEFAULT ''
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

-- Tecniche personalizzate (richiesta in chat): create dal giocatore,
-- legate a UN cavaliere specifico (non al catalogo armature come le
-- tecniche vere) - nome/elemento/descrizioni a scelta del giocatore,
-- potenza calcolata dal gioco in base al livello (mai scelta a mano,
-- per evitare abusi). ON DELETE CASCADE: se il personaggio viene
-- eliminato, le sue tecniche personalizzate vanno via con lui.
CREATE TABLE IF NOT EXISTS custom_techniques (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knight_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    tech_type TEXT NOT NULL,
    launch_desc TEXT NOT NULL DEFAULT '',
    effect_desc TEXT NOT NULL DEFAULT '',
    power INTEGER NOT NULL,
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
    npc_alive INTEGER NOT NULL DEFAULT 1,
    npc_generation INTEGER NOT NULL DEFAULT 1,
    npc_fate TEXT NOT NULL DEFAULT '',
    last_world_event_minutes INTEGER NOT NULL DEFAULT 0,
    npc_status TEXT NOT NULL DEFAULT 'occupied',
    npc_training_candidate TEXT NOT NULL DEFAULT '',
    npc_training_ready_minutes INTEGER NOT NULL DEFAULT 0,
    npc_injured INTEGER NOT NULL DEFAULT 0,
    npc_injury_cause TEXT NOT NULL DEFAULT '',
    npc_alignment TEXT NOT NULL DEFAULT '',
    npc_vita_cur INTEGER NOT NULL DEFAULT 0,
    npc_vita_max INTEGER NOT NULL DEFAULT 0,
    npc_cosmo_cur INTEGER NOT NULL DEFAULT 0,
    npc_cosmo_max INTEGER NOT NULL DEFAULT 0,
    npc_stamina_cur INTEGER NOT NULL DEFAULT 0,
    npc_stamina_max INTEGER NOT NULL DEFAULT 0,
    npc_last_regen_minutes INTEGER NOT NULL DEFAULT 0,
    npc_trait TEXT NOT NULL DEFAULT '',
    npc_ideal TEXT NOT NULL DEFAULT '',
    npc_bond TEXT NOT NULL DEFAULT '',
    npc_flaw TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (armor_name) REFERENCES armors(name),
    FOREIGN KEY (claimed_by_knight_id) REFERENCES knights(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS world_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    world_minutes INTEGER NOT NULL,
    armor_name TEXT NOT NULL,
    entry TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tavern_relationships (
    knight_id INTEGER NOT NULL,
    armor_name TEXT NOT NULL,
    affinity INTEGER NOT NULL DEFAULT 0,
    last_message_minutes INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (knight_id, armor_name),
    FOREIGN KEY (knight_id) REFERENCES knights(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tavern_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knight_id INTEGER NOT NULL,
    armor_name TEXT NOT NULL,
    world_minutes INTEGER NOT NULL,
    speaker TEXT NOT NULL,
    text TEXT NOT NULL,
    FOREIGN KEY (knight_id) REFERENCES knights(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tavern_bartenders (
    divinity TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    alignment TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS institutional_alignments (
    npc_id TEXT PRIMARY KEY,
    alignment TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tavern_seating (
    divinity TEXT NOT NULL,
    armor_name TEXT NOT NULL,
    table_number INTEGER NOT NULL,
    seat_index INTEGER NOT NULL,
    PRIMARY KEY (divinity, armor_name)
);

CREATE TABLE IF NOT EXISTS tavern_seating_meta (
    divinity TEXT PRIMARY KEY,
    last_reshuffle_minutes INTEGER NOT NULL DEFAULT 0
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
        # Avatar del cavaliere (richiesto in chat): il percorso di
        # un'eventuale immagine caricata dal giocatore (vuoto = nessuna
        # immagine, mostra solo un segnaposto). skin_tone/hair_color
        # restano nello schema per compatibilità ma non sono più usati
        # da quando le sagome geometriche sono state tolte (non
        # reggevano il confronto, segnalato in chat).
        conn.execute("ALTER TABLE knights ADD COLUMN skin_tone TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE knights ADD COLUMN hair_color TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE knights ADD COLUMN avatar_path TEXT NOT NULL DEFAULT ''")
        conn.commit()
        log.info("Migrazione: aggiunte colonne skin_tone/hair_color/avatar_path a knights.")
    if "created_at" not in existing_columns:
        # Calendario reale (richiesto in chat, stile Football Manager):
        # il personaggio "nasce" nel momento vero in cui viene creato,
        # non più in un "Anno 1" fittizio - da qui in poi il calendario
        # somma i minuti di gioco a questo timestamp reale. Per i
        # salvataggi già esistenti non abbiamo un vero momento di
        # creazione registrato: usiamo "adesso" come miglior
        # approssimazione disponibile.
        now_iso = datetime.now().isoformat()
        conn.execute("ALTER TABLE knights ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE knights SET created_at = ? WHERE created_at = ''", (now_iso,))
        conn.commit()
        log.info("Migrazione: aggiunta colonna created_at a knights (approssimata a 'adesso' per i salvataggi esistenti).")
    if "is_knight" not in existing_columns:
        # Apprendistato (richiesto in chat): i personaggi già esistenti
        # nascono già "Cavalieri" (is_knight=1) - nessuno resta bloccato
        # retroattivamente da un percorso che non esisteva quando sono
        # stati creati.
        conn.execute("ALTER TABLE knights ADD COLUMN is_knight INTEGER NOT NULL DEFAULT 1")
        conn.execute("ALTER TABLE knights ADD COLUMN training_stage INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE knights ADD COLUMN master_name TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE knights ADD COLUMN master_armor_name TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE knights ADD COLUMN companion1_name TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE knights ADD COLUMN companion2_name TEXT NOT NULL DEFAULT ''")
        conn.commit()
        log.info("Migrazione: aggiunte colonne dell'apprendistato a knights (salvataggi esistenti già 'Cavalieri').")
    if "arena_background_path" not in existing_columns:
        # Sfondo personalizzato dell'Arena (richiesto in chat: le
        # decorazioni geometriche non reggevano il confronto) - vuoto
        # per tutti finché non se ne carica uno, usa il colore del tema.
        conn.execute("ALTER TABLE knights ADD COLUMN arena_background_path TEXT NOT NULL DEFAULT ''")
        conn.commit()
        log.info("Migrazione: aggiunta colonna arena_background_path a knights.")
    if "arena_backgrounds" not in existing_columns:
        # Sostituisce arena_background_path (richiesto in chat: uno
        # sfondo SOLO ha poco senso, meglio uno per ciascuno dei 5 temi
        # - un dizionario JSON tema->percorso invece di un unico
        # campo). Il vecchio campo resta nello schema per compatibilità
        # ma non è più usato da qui in avanti.
        conn.execute("ALTER TABLE knights ADD COLUMN arena_backgrounds TEXT NOT NULL DEFAULT '{}'")
        conn.commit()
        log.info("Migrazione: aggiunta colonna arena_backgrounds a knights (dizionario JSON per tema).")
    if "denaro" not in existing_columns:
        # Missioni (richiesto in chat): una ricompensa in Cosmo/denaro a
        # missione completata - nessun negozio dove spenderlo ancora
        # (le taverne restano un capitolo futuro), ma il numero cresce
        # già da ora. mission_id/mission_stage tracciano una missione
        # in corso - vuoti/zero quando nessuna è attiva.
        conn.execute("ALTER TABLE knights ADD COLUMN denaro INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE knights ADD COLUMN mission_id TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE knights ADD COLUMN mission_stage INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        log.info("Migrazione: aggiunte colonne delle Missioni a knights (denaro, mission_id, mission_stage).")
    if "renown" not in existing_columns:
        # La Renown di fazione (richiesto in chat, dalla roadmap) - un
        # punteggio persistente di reputazione col PERSONAGGIO
        # GIOCATORE presso la propria fazione, separato dall'affinità
        # individuale della Taverna (quella è con UN singolo PNG,
        # questa è con la fazione intera) - cresce completando
        # missioni, sblocca un titolo onorifico a soglie crescenti.
        conn.execute("ALTER TABLE knights ADD COLUMN renown INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        log.info("Migrazione: aggiunta colonna renown a knights.")
    if "mission_node" not in existing_columns:
        # Seconda missione a grafo (richiesto in chat: bivi che portano
        # DAVVERO a strade diverse) - mission_node tiene il nodo
        # attuale (per missioni a grafo come "Le Colonne dei Sette
        # Mari"), mission_flags i flag accumulati durante il percorso
        # (es. "helped_prisoner", separati da virgola) che influenzano
        # il finale. La Scalata delle Dodici Case continua a usare solo
        # mission_stage, essendo il suo ordine fisso per fedeltà al
        # canone.
        conn.execute("ALTER TABLE knights ADD COLUMN mission_node TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE knights ADD COLUMN mission_flags TEXT NOT NULL DEFAULT ''")
        conn.commit()
        log.info("Migrazione: aggiunte colonne mission_node/mission_flags a knights (per missioni a grafo).")
    if "tournament_bracket" not in existing_columns:
        # Il tabellone dei tornei (richiesto in chat: "non si conosce i
        # partecipanti, il tabellone" - generato tutto in una volta
        # all'iscrizione, non più avversari pescati alla cieca round
        # per round) - un JSON con tutti i partecipanti e l'esito
        # dell'intero tabellone (il percorso "fantasma" degli altri
        # partecipanti è già simulato al momento dell'iscrizione, così
        # si può mostrare il tabellone completo fin dall'inizio).
        conn.execute("ALTER TABLE knights ADD COLUMN tournament_bracket TEXT NOT NULL DEFAULT ''")
        conn.commit()
        log.info("Migrazione: aggiunta colonna tournament_bracket a knights.")
    if "mission_counter" not in existing_columns:
        # Un contatore numerico generico riusabile da varie missioni per
        # il proprio stato (richiesto in chat: "Ade a prove" - il
        # livello di allerta che sale sui fallimenti) - non serve una
        # colonna dedicata per ogni singola missione futura che avrà
        # bisogno di un contatore proprio.
        conn.execute("ALTER TABLE knights ADD COLUMN mission_counter INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        log.info("Migrazione: aggiunta colonna mission_counter a knights.")
    if "apprentice_status" not in existing_columns:
        # Alternative al fallimento della Prova Finale (richiesto in
        # chat) - vuoto vuol dire "addestramento normale in corso",
        # "soldier" vuol dire "diventato soldato semplice" (uno stato
        # vero, con attività dedicate proprie - vedi core/soldier.py).
        # Il riaddestramento per un'altra armatura e la morte del
        # personaggio non hanno bisogno di un campo a parte: il primo
        # resetta semplicemente i campi già esistenti dell'apprendistato
        # (stessa forma di una nuova creazione), la seconda cancella
        # la riga stessa.
        conn.execute("ALTER TABLE knights ADD COLUMN apprentice_status TEXT NOT NULL DEFAULT ''")
        conn.commit()
        log.info("Migrazione: aggiunta colonna apprentice_status a knights.")
    if "vita_cur" not in existing_columns:
        # Le tre barre (richiesto in chat): il Cosmo smette di fare
        # doppio lavoro (risorsa E vita) - ora la Vita è il vero
        # indicatore di salute in combattimento, il Cosmo diventa
        # puramente una risorsa che le tecniche consumano. I salvataggi
        # esistenti partono a Vita piena (100/100) - un valore
        # ragionevole finché non si allena/combatte, dopodiché la
        # formula vera (legata a Costituzione) prende il sopravvento
        # al prossimo save_knight.
        conn.execute("ALTER TABLE knights ADD COLUMN vita_cur INTEGER NOT NULL DEFAULT 100")
        conn.execute("ALTER TABLE knights ADD COLUMN vita_max INTEGER NOT NULL DEFAULT 100")
        conn.commit()
        log.info("Migrazione: aggiunte colonne vita_cur/vita_max a knights (le tre barre).")

    # Stessa logica di migrazione, ma per il roster (richiesto in chat:
    # il mondo che vive per conto suo) - i PNG ora possono morire ed
    # essere sostituiti, non sono più nomi statici.
    roster_columns = {row["name"] for row in conn.execute("PRAGMA table_info(roster)")}
    if "npc_alive" not in roster_columns:
        conn.execute("ALTER TABLE roster ADD COLUMN npc_alive INTEGER NOT NULL DEFAULT 1")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_generation INTEGER NOT NULL DEFAULT 1")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_fate TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE roster ADD COLUMN last_world_event_minutes INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        log.info("Migrazione: aggiunte colonne npc_alive/npc_generation/npc_fate/last_world_event_minutes a roster.")
    if "npc_status" not in roster_columns:
        # Un successore non prende il posto ISTANTANEAMENTE (richiesto
        # in chat: "sarebbe meglio dire che comincia l'addestramento",
        # non che diventa Cavaliere di colpo) - vacante, poi in
        # addestramento, poi occupato di nuovo.
        conn.execute("ALTER TABLE roster ADD COLUMN npc_status TEXT NOT NULL DEFAULT 'occupied'")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_training_candidate TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_training_ready_minutes INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        log.info("Migrazione: aggiunte colonne npc_status/npc_training_candidate/npc_training_ready_minutes a roster.")
    if "npc_injured" not in roster_columns:
        # Le ferite come stato intermedio (richiesto in chat): un PNG
        # può uscire ferito da uno scontro/missione/incidente
        # d'allenamento simulato, restando al proprio posto ma con un
        # rischio vero - nei giorni seguenti - di guarire o di
        # peggiorare fino a morirne.
        conn.execute("ALTER TABLE roster ADD COLUMN npc_injured INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_injury_cause TEXT NOT NULL DEFAULT ''")
        conn.commit()
        log.info("Migrazione: aggiunte colonne npc_injured/npc_injury_cause a roster.")
    if "npc_alignment" not in roster_columns:
        # L'allineamento vero (richiesto in chat, stile D&D a 9
        # caselle) - MAI mostrato al giocatore, si scopre solo
        # giocando/fallendo. Assegnato in Python (vedi
        # core/alignment.py), non con un default SQL fisso, per questo
        # la colonna nasce vuota e viene riempita subito dopo dalla
        # migrazione applicativa in ensure_roster_populated.
        conn.execute("ALTER TABLE roster ADD COLUMN npc_alignment TEXT NOT NULL DEFAULT ''")
        conn.commit()
        log.info("Migrazione: aggiunta colonna npc_alignment a roster.")
    if "npc_vita_max" not in roster_columns:
        # Le tre barre vere anche per i PNG (richiesto in chat) - non
        # più generate al volo ad ogni combattimento, ma persistite: un
        # PNG che perde un duello resta debole finché non recupera nel
        # tempo, esattamente come il giocatore. Valori a 0 qui di
        # proposito (sentinella "non ancora inizializzato") - il
        # catalogo delle armature potrebbe non essere ancora caricato
        # in questo punto della migrazione; i valori VERI (in base al
        # livello dell'armatura) vengono calcolati subito dopo da
        # ensure_roster_populated, che gira solo a catalogo pronto.
        conn.execute("ALTER TABLE roster ADD COLUMN npc_vita_cur INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_vita_max INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_cosmo_cur INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_cosmo_max INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_stamina_cur INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_stamina_max INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_last_regen_minutes INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        log.info("Migrazione: aggiunte colonne delle tre barre (vita/cosmo/stamina) a roster.")
    if "npc_trait" not in roster_columns:
        # Il sistema Tratto/Ideale/Legame/Difetto (richiesto in chat,
        # dalla roadmap: "caratterizzazione più profonda dei PNG") -
        # stesso principio già seguito per npc_alignment: colonne
        # vuote qui, riempite dalla migrazione applicativa in
        # ensure_roster_populated una volta che il catalogo è pronto.
        conn.execute("ALTER TABLE roster ADD COLUMN npc_trait TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_ideal TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_bond TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE roster ADD COLUMN npc_flaw TEXT NOT NULL DEFAULT ''")
        conn.commit()
        log.info("Migrazione: aggiunte colonne Tratto/Ideale/Legame/Difetto a roster.")

    world_clock_columns = {row["name"] for row in conn.execute("PRAGMA table_info(world_clock)")}
    if "last_npc_tick_minutes" not in world_clock_columns:
        conn.execute("ALTER TABLE world_clock ADD COLUMN last_npc_tick_minutes INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        log.info("Migrazione: aggiunta colonna last_npc_tick_minutes a world_clock.")

    # Il taverniere (richiesto in chat) usa una chiave speciale al
    # posto di un vero nome di armatura per parlare con lui nella
    # stessa infrastruttura di conversazione - il vincolo di chiave
    # esterna su armor_name, corretto qui, lo avrebbe impedito (bug
    # scoperto in chat). SQLite non supporta togliere un vincolo con
    # ALTER TABLE: si ricrea la tabella da capo, copiando i dati.
    fk_list = conn.execute("PRAGMA foreign_key_list(tavern_relationships)").fetchall()
    has_armor_fk = any(fk["table"] == "armors" for fk in fk_list)
    if has_armor_fk:
        conn.execute("ALTER TABLE tavern_relationships RENAME TO tavern_relationships_old")
        conn.execute(
            """CREATE TABLE tavern_relationships (
                knight_id INTEGER NOT NULL,
                armor_name TEXT NOT NULL,
                affinity INTEGER NOT NULL DEFAULT 0,
                last_message_minutes INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (knight_id, armor_name),
                FOREIGN KEY (knight_id) REFERENCES knights(id) ON DELETE CASCADE
            )"""
        )
        conn.execute(
            "INSERT INTO tavern_relationships SELECT knight_id, armor_name, affinity, last_message_minutes FROM tavern_relationships_old"
        )
        conn.execute("DROP TABLE tavern_relationships_old")
        conn.commit()
        log.info("Migrazione: rimosso il vincolo di chiave esterna su tavern_relationships.armor_name.")


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


def get_world_minutes(conn: sqlite3.Connection) -> int:
    """L'orologio del mondo (richiesto in chat) - un unico calendario
    condiviso da tutti i personaggi e i PNG, non più uno personale a
    testa. Avanza SOLO quando qualcuno fa passare del tempo (allenarsi,
    combattere, ecc. - vedi RosterManager.spend_time), esattamente come
    in Football Manager: giocando la propria partita, avanza il tempo
    per tutti."""
    row = conn.execute("SELECT minutes FROM world_clock WHERE id = 1").fetchone()
    return row["minutes"] if row else 0


def advance_world_minutes(conn: sqlite3.Connection, minutes: int) -> int:
    """Fa avanzare l'orologio del mondo di `minutes` minuti - restituisce
    il nuovo totale. Chiamata da RosterManager.spend_time ogni volta che
    un personaggio fa passare del tempo, cosa che ora avanza il
    calendario CONDIVISO invece che uno personale."""
    conn.execute("UPDATE world_clock SET minutes = minutes + ? WHERE id = 1", (minutes,))
    conn.commit()
    return get_world_minutes(conn)


def get_last_npc_tick_minutes(conn: sqlite3.Connection) -> int:
    """Il mondo che vive per conto suo (richiesto in chat) - l'ultimo
    punto dell'orologio del mondo fino a cui i PNG sono già stati
    simulati, per non doverli ricalcolare tutti ad ogni minuscolo
    avanzamento (sarebbe sprecato farlo ad ogni round di
    combattimento)."""
    row = conn.execute("SELECT last_npc_tick_minutes FROM world_clock WHERE id = 1").fetchone()
    return row["last_npc_tick_minutes"] if row else 0


def set_last_npc_tick_minutes(conn: sqlite3.Connection, minutes: int) -> None:
    conn.execute("UPDATE world_clock SET last_npc_tick_minutes = ? WHERE id = 1", (minutes,))
    conn.commit()


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
        SELECT r.armor_name, r.npc_name, r.claimed_by_knight_id, r.npc_generation, r.npc_fate,
               r.npc_status, r.npc_training_candidate,
               r.npc_trait, r.npc_ideal, r.npc_bond, r.npc_flaw,
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


def insert_roster_entry(conn: sqlite3.Connection, armor_name: str, npc_name: str, alignment: str = "",
                         vita_max: int = 0, cosmo_max: int = 0, stamina_max: int = 0,
                         last_regen_minutes: int = 0, trait: str = "", ideal: str = "",
                         bond: str = "", flaw: str = "") -> None:
    """Crea lo slot per un'armatura con il suo PNG fisso - ignorata (non
    sovrascrive) se esiste già, perché il nome del PNG non deve mai
    cambiare una volta assegnato (richiesto in chat). `alignment`
    (richiesto in chat, stile D&D): il vero allineamento del PNG, mai
    mostrato al giocatore. `vita_max`/`cosmo_max`/`stamina_max`
    (richiesto in chat, tre barre vere anche per i PNG): le statistiche
    massime del PNG, con le correnti che partono già al massimo (un
    PNG appena creato è sano). `trait`/`ideal`/`bond`/`flaw` (richiesto
    in chat, dalla roadmap: caratterizzazione più profonda) - le
    quattro frasi di personalità, generate dal chiamante
    (core.personality) in base all'umore derivato dall'allineamento -
    non qui, per non far dipendere questo modulo di basso livello da
    logica applicativa."""
    conn.execute(
        """INSERT OR IGNORE INTO roster
           (armor_name, npc_name, claimed_by_knight_id, npc_alignment,
            npc_vita_cur, npc_vita_max, npc_cosmo_cur, npc_cosmo_max,
            npc_stamina_cur, npc_stamina_max, npc_last_regen_minutes,
            npc_trait, npc_ideal, npc_bond, npc_flaw)
           VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (armor_name, npc_name, alignment, vita_max, vita_max, cosmo_max, cosmo_max,
         stamina_max, stamina_max, last_regen_minutes, trait, ideal, bond, flaw),
    )


def claim_roster_slot(conn: sqlite3.Connection, armor_name: str, knight_id: int) -> None:
    """Un personaggio giocatore reclama lo slot della sua armatura - il
    PNG 'si fa da parte' (resta nel database ma non compare più come
    occupante finché lo slot è reclamato)."""
    conn.execute("UPDATE roster SET claimed_by_knight_id = ? WHERE armor_name = ?", (knight_id, armor_name))
    conn.commit()


def release_roster_slot(conn: sqlite3.Connection, armor_name: str) -> None:
    """L'opposto di claim_roster_slot (richiesto in chat: riaddestrarsi
    per un'altra armatura, o la morte del personaggio, rilasciano
    quella vecchia) - torna disponibile per un altro personaggio, il
    PNG fisso ricompare come occupante finché nessuno la reclama di
    nuovo."""
    conn.execute("UPDATE roster SET claimed_by_knight_id = NULL WHERE armor_name = ?", (armor_name,))
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


def add_world_event(conn: sqlite3.Connection, world_minutes: int, armor_name: str, entry: str) -> None:
    """La Cronaca del Mondo (richiesto in chat) - una riga per ogni
    evento accaduto ai PNG nel tempo condiviso (morte, ritiro,
    sparizione, sostituzione), leggibile da tutti indipendentemente da
    quale personaggio si stia giocando in quel momento - a differenza
    del diario, che è personale per ciascun personaggio."""
    conn.execute(
        "INSERT INTO world_events (world_minutes, armor_name, entry) VALUES (?, ?, ?)",
        (world_minutes, armor_name, entry),
    )
    conn.commit()


def get_world_chronicle(conn: sqlite3.Connection, limit: int = 100) -> list[sqlite3.Row]:
    """Le voci più recenti della Cronaca del Mondo (richiesto in chat) -
    dalla più recente alla meno recente, limitate a `limit` per non
    restituire un elenco enorme dopo mesi di gioco."""
    return conn.execute(
        "SELECT * FROM world_events ORDER BY world_minutes DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()


def get_tavern_relationship(conn: sqlite3.Connection, knight_id: int, armor_name: str) -> sqlite3.Row | None:
    """Il rapporto (richiesto in chat, la Taverna) tra un personaggio
    giocatore e un PNG - None se non si sono ancora mai parlati."""
    return conn.execute(
        "SELECT * FROM tavern_relationships WHERE knight_id = ? AND armor_name = ?",
        (knight_id, armor_name),
    ).fetchone()


def adjust_tavern_affinity(conn: sqlite3.Connection, knight_id: int, armor_name: str,
                            delta: int, world_minutes: int) -> int:
    """Sposta l'affinità di `delta` (può essere negativo) - crea il
    rapporto se non esiste ancora. Restituisce l'affinità risultante."""
    conn.execute(
        """INSERT INTO tavern_relationships (knight_id, armor_name, affinity, last_message_minutes)
           VALUES (?, ?, ?, ?)
           ON CONFLICT (knight_id, armor_name)
           DO UPDATE SET affinity = affinity + excluded.affinity, last_message_minutes = excluded.last_message_minutes""",
        (knight_id, armor_name, delta, world_minutes),
    )
    conn.commit()
    return get_tavern_relationship(conn, knight_id, armor_name)["affinity"]


def add_tavern_message(conn: sqlite3.Connection, knight_id: int, armor_name: str,
                        world_minutes: int, speaker: str, text: str) -> None:
    """Una riga di conversazione nella Taverna (richiesto in chat) -
    speaker è 'player' o 'npc'."""
    conn.execute(
        "INSERT INTO tavern_messages (knight_id, armor_name, world_minutes, speaker, text) VALUES (?, ?, ?, ?, ?)",
        (knight_id, armor_name, world_minutes, speaker, text),
    )
    conn.commit()


def get_tavern_conversation(conn: sqlite3.Connection, knight_id: int, armor_name: str,
                             limit: int = 50) -> list[sqlite3.Row]:
    """L'ultima parte della conversazione con un PNG specifico, in
    ordine cronologico (dalla più vecchia alla più recente, per essere
    mostrata così com'è in una schermata di chat)."""
    rows = conn.execute(
        "SELECT * FROM tavern_messages WHERE knight_id = ? AND armor_name = ? ORDER BY id DESC LIMIT ?",
        (knight_id, armor_name, limit),
    ).fetchall()
    return list(reversed(rows))


def get_institutional_alignment(conn: sqlite3.Connection, npc_id: str) -> sqlite3.Row | None:
    """Il vero allineamento (richiesto in chat, stile D&D, esteso alle
    Figure Istituzionali) di chi occupa in questo momento un ruolo
    istituzionale - None se non ancora assegnato."""
    return conn.execute("SELECT * FROM institutional_alignments WHERE npc_id = ?", (npc_id,)).fetchone()


def set_institutional_alignment(conn: sqlite3.Connection, npc_id: str, alignment: str, generation: int) -> None:
    """Assegna (o riassegna, ad ogni successione) l'allineamento di chi
    occupa un ruolo istituzionale - nuova persona, nuovo carattere."""
    conn.execute(
        """INSERT INTO institutional_alignments (npc_id, alignment, generation) VALUES (?, ?, ?)
           ON CONFLICT (npc_id) DO UPDATE SET alignment = excluded.alignment, generation = excluded.generation""",
        (npc_id, alignment, generation),
    )
    conn.commit()


def get_tavern_bartender(conn: sqlite3.Connection, divinity: str) -> sqlite3.Row | None:
    """Il taverniere di questo regno (richiesto in chat, la Taverna a
    mappa) - un PNG fisso non legato a nessuna armatura, generato una
    volta sola per regno."""
    return conn.execute("SELECT * FROM tavern_bartenders WHERE divinity = ?", (divinity,)).fetchone()


def insert_tavern_bartender(conn: sqlite3.Connection, divinity: str, name: str, alignment: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO tavern_bartenders (divinity, name, alignment) VALUES (?, ?, ?)",
        (divinity, name, alignment),
    )
    conn.commit()


def get_tavern_seating(conn: sqlite3.Connection, divinity: str) -> list[sqlite3.Row]:
    """Chi siede dove, in questo momento, nella Taverna di questo regno
    (richiesto in chat) - ogni riga è un PNG con il tavolo e il posto
    che occupa."""
    return conn.execute("SELECT * FROM tavern_seating WHERE divinity = ?", (divinity,)).fetchall()


def set_tavern_seating(conn: sqlite3.Connection, divinity: str, armor_name: str,
                        table_number: int, seat_index: int) -> None:
    conn.execute(
        """INSERT INTO tavern_seating (divinity, armor_name, table_number, seat_index) VALUES (?, ?, ?, ?)
           ON CONFLICT (divinity, armor_name) DO UPDATE SET table_number = excluded.table_number, seat_index = excluded.seat_index""",
        (divinity, armor_name, table_number, seat_index),
    )


def remove_tavern_seating(conn: sqlite3.Connection, divinity: str, armor_name: str) -> None:
    conn.execute("DELETE FROM tavern_seating WHERE divinity = ? AND armor_name = ?", (divinity, armor_name))


def get_tavern_last_reshuffle(conn: sqlite3.Connection, divinity: str) -> int:
    row = conn.execute(
        "SELECT last_reshuffle_minutes FROM tavern_seating_meta WHERE divinity = ?", (divinity,)
    ).fetchone()
    return row["last_reshuffle_minutes"] if row else 0


def set_tavern_last_reshuffle(conn: sqlite3.Connection, divinity: str, world_minutes: int) -> None:
    conn.execute(
        """INSERT INTO tavern_seating_meta (divinity, last_reshuffle_minutes) VALUES (?, ?)
           ON CONFLICT (divinity) DO UPDATE SET last_reshuffle_minutes = excluded.last_reshuffle_minutes""",
        (divinity, world_minutes),
    )
    conn.commit()


def get_biography_entries(conn: sqlite3.Connection, knight_id: int) -> list[sqlite3.Row]:
    """Tutte le voci del diario di un personaggio, in ordine cronologico."""
    return conn.execute(
        "SELECT * FROM biography_entries WHERE knight_id = ? ORDER BY id ASC", (knight_id,)
    ).fetchall()


def get_custom_techniques(conn: sqlite3.Connection, knight_id: int) -> list[sqlite3.Row]:
    """Le tecniche personalizzate di un personaggio, in ordine di
    creazione."""
    return conn.execute(
        "SELECT * FROM custom_techniques WHERE knight_id = ? ORDER BY id ASC", (knight_id,)
    ).fetchall()


def add_custom_technique(conn: sqlite3.Connection, knight_id: int, name: str, tech_type: str,
                          launch_desc: str, effect_desc: str, power: int) -> None:
    """Registra una nuova tecnica personalizzata - la potenza arriva già
    calcolata dal chiamante (vedi core.arena_manager.
    calculate_custom_technique_power), mai scelta dal giocatore."""
    conn.execute(
        "INSERT INTO custom_techniques (knight_id, name, tech_type, launch_desc, effect_desc, power) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (knight_id, name, tech_type, launch_desc, effect_desc, power),
    )
    conn.commit()


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
