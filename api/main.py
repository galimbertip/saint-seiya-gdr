"""
Backend web per Saint Seiya: Sacro Imperio.

Espone come richieste HTTP le stesse azioni che finora vivevano nei
pulsanti PySide6 - la logica sotto (core/, api/arena_session.py) è
identica e già testata, qui si aggiunge solo un modo diverso di
chiamarla.

Avvio locale (da Codespaces o dal tuo PC):
    uvicorn api.main:app --reload
Poi apri http://localhost:8000/docs per una pagina di test automatica
(Swagger UI, generata da sola da FastAPI - permette di provare ogni
endpoint dal browser senza scrivere codice).

NOTA: questo file non è stato eseguito in questa sessione (l'ambiente
di sviluppo non ha accesso alla rete per installare FastAPI) - la
sintassi è verificata, ma la prova viva va fatta da Codespaces, dove
la rete c'è.
"""
from typing import Literal, Optional
from pathlib import Path
import random

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.staticfiles import StaticFiles
import shutil
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from database.db_manager import (
    get_connection, init_db, refresh_armors_catalog,
    get_armor, get_techniques_for_armor, list_armors_for_player_level, get_roster,
    add_biography_entry, get_biography_entries, get_custom_techniques, add_custom_technique,
)
from core.character_factory import (
    create_knight, get_knight, list_knights, delete_knight, save_knight,
    ArmorNotFoundError, ArmorLevelTooHighError, ArmorAlreadyClaimedError, ensure_roster_populated,
)
from core.fm_manager import (
    RosterManager, get_calendar_display, parse_weekly_schedule,
    serialize_weekly_schedule, TRAINING_FOCUS_OPTIONS,
)
from core.arena_manager import (
    find_defensive_technique, get_unlocked_senses, calculate_movement_points, GEO_ORIGINS,
    custom_technique_slots, calculate_custom_technique_power, allowed_custom_technique_elements,
)
from core.version import APP_VERSION
from core.institutional_npcs import get_institutional_npcs
from core.training_path import (
    render_stage, generate_trial_opponent, FINAL_TRIAL_STAGE, LEVEL_UP_AFTER_STAGE,
    KNIGHTHOOD_LEVEL, RETRY_STAGE_ON_FAILURE,
)
from api.arena_session import (
    start_battle, list_opponent_candidates, resolve_declare, resolve_react, finalize_fight, move_player,
)

app = FastAPI(title="Saint Seiya: Sacro Imperio API", version=APP_VERSION)

# Sviluppo: aperto a tutte le origini. Quando ci sarà un frontend vero
# con un suo indirizzo fisso, restringiamo a quello soltanto.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cartella per gli avatar caricati dai giocatori (richiesto in chat) -
# servita direttamente come file statici su /avatars/<nome-file>.
AVATARS_DIR = Path(__file__).resolve().parent.parent / "avatars"
AVATARS_DIR.mkdir(exist_ok=True)
app.mount("/avatars", StaticFiles(directory=str(AVATARS_DIR)), name="avatars")


def _init_schema_once() -> None:
    """Crea le tabelle, carica il catalogo armature dai CSV, e popola la
    Gerarchia (un PNG fisso per ogni armatura che non ne ha ancora uno)
    - va fatto UNA SOLA VOLTA all'avvio del processo, non ad ogni
    richiesta (il refresh del catalogo fa oltre 200 upsert, sarebbe uno
    spreco farlo per ogni singola chiamata API)."""
    conn = get_connection()
    init_db(conn)
    refresh_armors_catalog(conn)
    ensure_roster_populated(conn)
    conn.close()


_init_schema_once()


def get_db():
    """Una connessione NUOVA per ogni richiesta, chiusa sempre a fine
    richiesta (anche in caso di errore, grazie al finally). Necessario
    perché una sqlite3.Connection non è condivisibile tra thread
    diversi, e FastAPI può eseguire endpoint sincroni (def, non async
    def, come questi) su thread diversi da una richiesta all'altra -
    una connessione condivisa unica avrebbe potuto rompersi in modo
    intermittente e difficile da riprodurre."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


# --------------------------- Modelli richieste ---------------------------

class CreateCharacterRequest(BaseModel):
    raw_name: str
    armor_name: str
    player_level: int = 1
    surname: Optional[str] = ""
    age: Optional[int] = 15
    gender: Optional[str] = ""
    origin: Optional[str] = ""
    build: Optional[str] = "Media"
    biography: Optional[str] = ""
    skin_tone: Optional[str] = ""
    hair_color: Optional[str] = ""


class CreateCustomTechniqueRequest(BaseModel):
    name: str
    tech_type: str
    is_defensive: bool = False
    launch_desc: Optional[str] = ""
    effect_desc: Optional[str] = ""


class TrainRequest(BaseModel):
    mode: Literal["settimana", "mese"]
    schedule: list[str]  # fino a 7 focus, uno per giorno della griglia


class ArenaStartBattleRequest(BaseModel):
    opponent: dict  # uno dei candidati restituiti da GET /arena/candidates


class ArenaMoveRequest(BaseModel):
    x: float  # coordinata bersaglio sulla griglia (0-10)
    y: float
    battle_state: dict


class ArenaDeclareRequest(BaseModel):
    action: Literal["attacca", "carica"]
    technique_name: Optional[str] = None
    technique_power: Optional[int] = None
    technique_type: Optional[str] = None
    technique_launch_desc: Optional[str] = None
    technique_effect_desc: Optional[str] = None
    battle_state: dict


class ArenaReactRequest(BaseModel):
    action: Literal["difenditi", "contrattacca", "incassa"]
    battle_state: dict
    counter_technique_name: Optional[str] = None
    counter_technique_power: Optional[int] = None
    counter_technique_type: Optional[str] = None
    counter_technique_launch_desc: Optional[str] = None
    counter_technique_effect_desc: Optional[str] = None


# --------------------------- Serializzazione ---------------------------

def _record_fight_outcome(conn, knight: dict, opponent_name: str, winner: str) -> None:
    """Aggiunge una voce al diario per la vittoria/sconfitta appena
    conclusa (richiesto in chat) - chiamata da entrambi i punti in cui
    uno scontro può finire (declare e react), invece di duplicare la
    stessa logica due volte."""
    cal = get_calendar_display(knight["created_at"], knight["game_minutes"])
    if winner == "player":
        entry = f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} sconfigge {opponent_name} nell'Arena."
    else:
        entry = f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} viene sconfitto da {opponent_name} nell'Arena."
    add_biography_entry(conn, knight["id"], knight["game_minutes"], entry)


def _handle_fight_conclusion(conn, knight: dict, battle_state: dict, winner: str) -> None:
    """Gestisce la conclusione di uno scontro - normale (Arena) o la
    Prova Finale (riconosciuta dal flag is_trial nel battle_state,
    impostato da .../training-path/trial/start) in modo diverso
    (richiesto in chat: la Prova Finale ora è un vero combattimento,
    non un tiro di dado narrato - la sua conclusione va gestita qui,
    non più in un endpoint a parte). Chiama finalize_fight e
    save_knight al posto del chiamante, non serve richiamarli anche
    fuori da qui."""
    opponent_name = battle_state["opponent"]["name"]
    finalize_fight(knight)

    if battle_state.get("is_trial"):
        cal = get_calendar_display(knight["created_at"], knight["game_minutes"])
        if winner == "player":
            knight["training_stage"] = FINAL_TRIAL_STAGE
            knight["is_knight"] = 1
            knight["player_level"] = max(knight["player_level"], KNIGHTHOOD_LEVEL)
            add_biography_entry(
                conn, knight["id"], knight["game_minutes"],
                f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} "
                f"supera la Prova Finale contro {opponent_name} e diventa Cavaliere.",
            )
        else:
            knight["training_stage"] = RETRY_STAGE_ON_FAILURE
            add_biography_entry(
                conn, knight["id"], knight["game_minutes"],
                f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} "
                f"non supera la Prova Finale contro {opponent_name} - dovrà prepararsi meglio prima di riprovare.",
            )
    else:
        _record_fight_outcome(conn, knight, opponent_name, winner)

    save_knight(conn, knight)


def _knight_payload(conn, knight: dict) -> dict:
    """Impacchetta un knight con tutto il contesto che il frontend
    normalmente dovrebbe richiedere separatamente (armatura, tecniche,
    calendario, sensi, Punti Movimento) - una sola chiamata invece di
    cinque."""
    armor = get_armor(knight["armor_name"], conn)
    techniques = [dict(t) for t in get_techniques_for_armor(knight["armor_name"], conn)]
    calendar = get_calendar_display(knight["created_at"], knight["game_minutes"])
    senses = get_unlocked_senses(knight["player_level"])
    movement_points = calculate_movement_points(knight["player_level"], knight["age"])
    return {
        **knight,
        "armor": dict(armor) if armor else None,
        "techniques": techniques,
        "calendar": calendar,
        "senses": senses,
        "movement_points": movement_points,
        "weekly_schedule_list": parse_weekly_schedule(knight["weekly_schedule"]),
    }


def _get_knight_or_404(conn, knight_id: int) -> dict:
    knight = get_knight(conn, knight_id)
    if knight is None:
        raise HTTPException(status_code=404, detail="Personaggio non trovato")
    return knight


# --------------------------- Salute del servizio ---------------------------

@app.get("/")
def api_root():
    return {"status": "ok", "app": "Saint Seiya: Sacro Imperio", "version": APP_VERSION}


# --------------------------- Frontend web ---------------------------
# Servita dallo STESSO server dell'API (stessa origine): il JavaScript
# della pagina chiama /characters, /armors, ecc. come indirizzi
# relativi, senza bisogno di conoscere l'indirizzo lungo e mutevole
# generato da Codespaces ad ogni riavvio.
_FRONTEND_PATH = Path(__file__).resolve().parent.parent / "web" / "index.html"


@app.get("/app", response_class=HTMLResponse)
def serve_frontend():
    # Niente cache per questa pagina (diagnosticato in chat: un proxy
    # intermedio - probabile l'inoltro delle porte di Codespaces -
    # continuava a servire una versione vecchia anche dopo refresh
    # forzato e riavvio del Codespace). Intestazioni esplicite per
    # impedire a QUALSIASI livello (browser o proxy) di mettere in
    # cache questa risposta.
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    return HTMLResponse(content=_FRONTEND_PATH.read_text(encoding="utf-8"), headers=headers)


# --------------------------- Personaggi ---------------------------

@app.get("/characters")
def api_list_characters(conn=Depends(get_db)):
    return [dict(k) for k in list_knights(conn)]


@app.post("/characters")
def api_create_character(req: CreateCharacterRequest, conn=Depends(get_db)):
    try:
        knight = create_knight(
            conn, req.raw_name, req.armor_name, req.player_level,
            surname=req.surname or "", age=req.age or 15, gender=req.gender or "", origin=req.origin or "",
            build=req.build or "Media", biography=req.biography or "",
            skin_tone=req.skin_tone or "", hair_color=req.hair_color or "",
        )
    except (ArmorNotFoundError, ArmorLevelTooHighError, ArmorAlreadyClaimedError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _knight_payload(conn, knight)


@app.get("/characters/{knight_id}")
def api_get_character(knight_id: int, conn=Depends(get_db)):
    knight = _get_knight_or_404(conn, knight_id)
    return _knight_payload(conn, knight)


@app.delete("/characters/{knight_id}")
def api_delete_character(knight_id: int, conn=Depends(get_db)):
    _get_knight_or_404(conn, knight_id)
    delete_knight(conn, knight_id)
    return {"deleted": True}


@app.post("/characters/{knight_id}/tutorial-seen")
def api_mark_tutorial_seen(knight_id: int, conn=Depends(get_db)):
    """Segna il tutorial iniziale come già visto per questo personaggio
    (richiesto in chat) - non ricompare più da solo, ma resta
    riapribile a piacere dal pulsante '?' nella schermata di gioco."""
    knight = _get_knight_or_404(conn, knight_id)
    knight["tutorial_seen"] = 1
    save_knight(conn, knight)
    return {"tutorial_seen": True}


class UpdateBackgroundRequest(BaseModel):
    biography: str


@app.post("/characters/{knight_id}/background")
def api_update_background(knight_id: int, req: UpdateBackgroundRequest, conn=Depends(get_db)):
    """Modifica l'abbozzo del background dopo la creazione (richiesto
    in chat: prima si poteva scrivere solo alla creazione, mai più
    dopo). Tocca solo l'abbozzo iniziale, non le voci auto-generate del
    Diario (quelle restano una cronaca, non modificabile)."""
    knight = _get_knight_or_404(conn, knight_id)
    knight["biography"] = req.biography.strip()
    save_knight(conn, knight)
    return {"biography": knight["biography"]}


@app.post("/characters/{knight_id}/avatar")
async def api_upload_avatar(knight_id: int, file: UploadFile = File(...), conn=Depends(get_db)):
    """Carica un'immagine come ritratto del personaggio (richiesto in
    chat). Salvata su disco (cartella avatars/, servita come file
    statico), il percorso va nel database. Un'immagine per cavaliere:
    caricarne una nuova sovrascrive quella precedente."""
    knight = _get_knight_or_404(conn, knight_id)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        raise HTTPException(status_code=400, detail="Formato immagine non supportato (usa PNG, JPG, WEBP o GIF).")

    filename = f"knight_{knight_id}{ext}"
    dest = AVATARS_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    knight["avatar_path"] = f"/avatars/{filename}"
    save_knight(conn, knight)
    return {"avatar_path": knight["avatar_path"]}


@app.get("/characters/{knight_id}/training-path")
def api_get_training_path(knight_id: int, conn=Depends(get_db)):
    """Lo stato del percorso di Apprendistato (richiesto in chat): se è
    già Cavaliere, non c'è nulla da mostrare. Altrimenti, la tappa
    attuale da leggere, o il segnale che è pronto per la Prova Finale
    (l'ultima tappa, risolta a parte con POST .../trial)."""
    knight = _get_knight_or_404(conn, knight_id)
    if knight["is_knight"]:
        return {"is_knight": True}

    if knight["training_stage"] >= FINAL_TRIAL_STAGE - 1:
        return {
            "is_knight": False, "ready_for_trial": True,
            "master_name": knight["master_name"], "master_armor_name": knight["master_armor_name"],
            "companion1_name": knight["companion1_name"], "companion2_name": knight["companion2_name"],
            "your_armor_name": knight["armor_name"],
        }

    techniques = [dict(t) for t in get_techniques_for_armor(knight["armor_name"], conn)]
    stage = render_stage(
        knight["training_stage"] + 1, knight["master_name"], knight["master_armor_name"],
        knight["companion1_name"], knight["companion2_name"], techniques,
        your_armor_name=knight["armor_name"],
    )
    return {"is_knight": False, "ready_for_trial": False, "stage": stage}


@app.post("/characters/{knight_id}/training-path/advance")
def api_advance_training(knight_id: int, conn=Depends(get_db)):
    """Segna completata la tappa attuale e passa alla prossima -
    applica anche l'eventuale salita di livello legata a quella tappa
    (richiesto in chat: livello 2 dopo la lezione sul Cosmo, livello 3
    dopo la prima tecnica, livello 4 dopo la seconda)."""
    knight = _get_knight_or_404(conn, knight_id)
    if knight["is_knight"]:
        raise HTTPException(status_code=400, detail="Hai già completato l'addestramento.")
    if knight["training_stage"] >= FINAL_TRIAL_STAGE - 1:
        raise HTTPException(status_code=400, detail="Sei pronto per la Prova Finale - non c'è altro da avanzare.")

    knight["training_stage"] += 1
    leveled_up_to = LEVEL_UP_AFTER_STAGE.get(knight["training_stage"])
    if leveled_up_to:
        knight["player_level"] = leveled_up_to
        cal = get_calendar_display(knight["created_at"], knight["game_minutes"])
        add_biography_entry(
            conn, knight["id"], knight["game_minutes"],
            f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} "
            f"raggiunge il livello {leveled_up_to} nel proprio addestramento.",
        )

    save_knight(conn, knight)
    return {"training_stage": knight["training_stage"], "leveled_up_to": leveled_up_to}


@app.post("/characters/{knight_id}/training-path/trial/start")
def api_start_trial(knight_id: int, conn=Depends(get_db)):
    """Avvia la Prova Finale come un VERO combattimento (richiesto in
    chat: "fammi combattere davvero", non un tiro di dado narrato) -
    stesso motore di battaglia dell'Arena (POST .../arena/opponent),
    solo con un avversario apposito (il Maestro con la sua armatura
    vera, o un compagno di pari fascia) e un flag is_trial nel
    battle_state, così .../arena/declare e .../arena/react sanno di
    dover gestire la conclusione in modo diverso (vedi
    _handle_fight_conclusion)."""
    knight = _get_knight_or_404(conn, knight_id)
    if knight["is_knight"]:
        raise HTTPException(status_code=400, detail="Hai già completato l'addestramento.")
    if knight["training_stage"] < FINAL_TRIAL_STAGE - 1:
        raise HTTPException(status_code=400, detail="Non sei ancora pronto per la Prova Finale.")

    armor = get_armor(knight["armor_name"], conn)
    opponent_is_master = random.random() < 0.2  # per lo più contro un compagno, a volte contro il Maestro
    opponent_name = knight["master_name"] if opponent_is_master else knight["companion1_name"]
    trial_opponent = generate_trial_opponent(conn, opponent_is_master, opponent_name, knight["master_armor_name"], armor)

    battle_state = start_battle(conn, knight, armor, opponent=trial_opponent)
    battle_state["is_trial"] = True
    return {"battle_state": battle_state}


@app.get("/characters/{knight_id}/custom-techniques")
def api_get_custom_techniques(knight_id: int, conn=Depends(get_db)):
    """Le tecniche personalizzate del personaggio, quanti slot ha
    sbloccato/usato, e quali elementi può scegliere per una nuova
    (richiesto in chat: correlati alla sua armatura o Provenienza)."""
    knight = _get_knight_or_404(conn, knight_id)
    armor_techniques = [dict(t) for t in get_techniques_for_armor(knight["armor_name"], conn)]
    existing = get_custom_techniques(conn, knight_id)
    return {
        "techniques": [dict(t) for t in existing],
        "slots_total": custom_technique_slots(knight["player_level"]),
        "slots_used": len(existing),
        "allowed_elements": allowed_custom_technique_elements(armor_techniques, knight["origin"]),
    }


@app.post("/characters/{knight_id}/custom-techniques")
def api_create_custom_technique(knight_id: int, req: CreateCustomTechniqueRequest, conn=Depends(get_db)):
    """Crea una nuova tecnica personalizzata - la potenza viene
    calcolata dal gioco in base al livello (mai scelta dal giocatore),
    e l'elemento deve essere uno di quelli ammessi (correlato
    all'armatura o alla Provenienza)."""
    knight = _get_knight_or_404(conn, knight_id)

    if not req.name.strip():
        raise HTTPException(status_code=400, detail="La tecnica deve avere un nome.")

    armor_techniques = [dict(t) for t in get_techniques_for_armor(knight["armor_name"], conn)]
    existing = get_custom_techniques(conn, knight_id)

    slots = custom_technique_slots(knight["player_level"])
    if len(existing) >= slots:
        raise HTTPException(
            status_code=400,
            detail=f"Nessuno slot disponibile per una nuova tecnica personalizzata ({len(existing)}/{slots} già usati).",
        )

    allowed = allowed_custom_technique_elements(armor_techniques, knight["origin"])
    if req.tech_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"L'elemento scelto deve essere correlato alla tua armatura o provenienza: {', '.join(allowed) or 'nessuno disponibile'}.",
        )

    power = calculate_custom_technique_power(knight["player_level"])
    # Offensiva o difensiva (richiesto in chat - mancava del tutto):
    # stessa convenzione delle tecniche del catalogo, un suffisso
    # '/Difensivo' nel tech_type, riconosciuto ovunque nel motore
    # cerca "difensiv" per escludere una tecnica dalle opzioni
    # d'attacco o includerla come difesa automatica.
    stored_tech_type = f"{req.tech_type}/Difensivo" if req.is_defensive else req.tech_type
    add_custom_technique(
        conn, knight_id, req.name.strip(), stored_tech_type,
        (req.launch_desc or "").strip(), (req.effect_desc or "").strip(), power,
    )
    return {"created": True, "power": power}


# --------------------------- Catalogo armature ---------------------------

@app.get("/armors")
def api_list_armors(player_level: int = 1, conn=Depends(get_db)):
    return [dict(a) for a in list_armors_for_player_level(player_level, conn)]


@app.get("/characters/{knight_id}/biography")
def api_get_biography(knight_id: int, conn=Depends(get_db)):
    """Il diario del personaggio (richiesto in chat): l'abbozzo scritto
    alla creazione più le voci che il gioco aggiunge da solo (level up,
    Sensi, vittorie/sconfitte in Arena). Servito a parte (non dentro
    _knight_payload) perché può crescere molto in una partita lunga -
    va richiesto solo quando si apre davvero la scheda del diario."""
    knight = _get_knight_or_404(conn, knight_id)
    entries = get_biography_entries(conn, knight_id)
    return {"sketch": knight["biography"], "entries": [dict(e) for e in entries]}


@app.get("/roster")
def api_get_roster(conn=Depends(get_db)):
    """La Gerarchia completa (richiesta in chat): tutte le 224 armature
    con chi le occupa - il PNG fisso se libere, il personaggio
    giocatore se reclamate. Ordinata per divinità/fazione/livello."""
    return [dict(r) for r in get_roster(conn)]


@app.get("/institutional-npcs")
def api_get_institutional_npcs():
    """Le figure istituzionali del mondo di gioco (richiesto in chat):
    non giocabili, statiche, un minimo di ambientazione/gdr - Il
    Grande Sacerdote, Pandora, ecc. Nessun accesso al DB, sono dati
    fissi del gioco, non legati a nessun personaggio."""
    return get_institutional_npcs()


@app.get("/geo-origins")
def api_geo_origins():
    """L'albero Continente -> Macrozona -> Nazione per il menu a tendina
    della Provenienza in creazione personaggio (richiesto in chat) -
    fonte di verità unica, condivisa con l'affinità elementale usata in
    combattimento (vedi core/arena_manager.py)."""
    return GEO_ORIGINS


@app.get("/armors/{armor_name}/techniques")
def api_armor_techniques(armor_name: str, conn=Depends(get_db)):
    return [dict(t) for t in get_techniques_for_armor(armor_name, conn)]


# --------------------------- Allenamento ---------------------------

@app.post("/characters/{knight_id}/train")
def api_train(knight_id: int, req: TrainRequest, conn=Depends(get_db)):
    knight = _get_knight_or_404(conn, knight_id)
    if not knight["is_knight"]:
        # Apprendistato (richiesto in chat): "ti stai già addestrando,
        # è quello il tuo allenamento" - l'Allenamento normale resta
        # bloccato finché non si diventa Cavaliere per davvero.
        raise HTTPException(status_code=403, detail="Sei ancora un Apprendista - segui il tuo percorso di addestramento prima di poterti allenare liberamente.")
    old_level = knight["player_level"]

    schedule = list(req.schedule[:7])
    while len(schedule) < 7:
        schedule.append("Riposo")
    for focus in schedule:
        if focus not in TRAINING_FOCUS_OPTIONS:
            raise HTTPException(status_code=400, detail=f"Focus di allenamento sconosciuto: {focus}")

    knight["weekly_schedule"] = serialize_weekly_schedule(schedule)

    if req.mode == "settimana":
        results = RosterManager.advance_week(knight, schedule)
    else:
        results = RosterManager.advance_month(knight, schedule)

    save_knight(conn, knight)

    log_entries = [{"day": d, "focus": f, "message": m} for d, f, m in results]

    # Annuncio armature sbloccate salendo di livello - richiesto in chat:
    # prima si scopriva solo per caso entrando in creazione di un nuovo
    # personaggio. Confronta il livello PRIMA e DOPO l'allenamento (può
    # essere salito di più di uno, con Avanza Mese), non solo l'ultimo.
    new_level = knight["player_level"]
    if new_level > old_level:
        newly_unlocked = conn.execute(
            "SELECT name FROM armors WHERE min_player_level > ? AND min_player_level <= ? ORDER BY min_player_level",
            (old_level, new_level),
        ).fetchall()
        if newly_unlocked:
            names = ", ".join(row["name"] for row in newly_unlocked)
            log_entries.append({
                "day": "", "focus": "",
                "message": f"🗡️ Livello raggiunto! In una nuova creazione potresti scegliere: {names}",
            })

        # Diario auto-scritto (richiesto in chat): il level up e ogni
        # nuovo Senso risvegliato diventano una voce del diario, non
        # solo un messaggio nel log dell'allenamento che sparisce alla
        # sessione successiva.
        cal = get_calendar_display(knight["created_at"], knight["game_minutes"])
        add_biography_entry(
            conn, knight["id"], knight["game_minutes"],
            f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} raggiunge il livello {new_level}.",
        )
        old_senses = get_unlocked_senses(old_level)
        new_senses = get_unlocked_senses(new_level)
        sense_labels = {"sesto": "Sesto Senso", "settimo": "Settimo Senso", "ottavo": "Ottavo Senso", "nono": "Nono Senso"}
        for key, label in sense_labels.items():
            if new_senses[key] and not old_senses[key]:
                add_biography_entry(
                    conn, knight["id"], knight["game_minutes"],
                    f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} risveglia il {label}.",
                )

    return {
        "log": log_entries,
        "character": _knight_payload(conn, knight),
    }


# --------------------------- Arena ---------------------------

@app.post("/characters/{knight_id}/arena/candidates")
def api_arena_candidates(knight_id: int, difficulty: str = "medio", conn=Depends(get_db)):
    """La 'sala d'attesa': genera 5 avversari candidati tra cui
    scegliere (richiesto in chat), invece di uno solo imposto a caso.
    Non crea ancora nessuno stato di battaglia - è solo la lista da
    mostrare; la battaglia vera parte con POST /arena/opponent passando
    il candidato scelto."""
    knight = _get_knight_or_404(conn, knight_id)
    if not knight["is_knight"]:
        raise HTTPException(status_code=403, detail="Sei ancora un Apprendista - l'Arena resta chiusa finché non superi la Prova Finale.")
    armor = get_armor(knight["armor_name"], conn)
    candidates = list_opponent_candidates(conn, armor, difficulty=difficulty)
    return {"candidates": candidates}


@app.post("/characters/{knight_id}/arena/opponent")
def api_arena_new_opponent(knight_id: int, req: ArenaStartBattleRequest, conn=Depends(get_db)):
    """Avvia la battaglia con l'avversario scelto dalla sala d'attesa
    (uno dei candidati di POST /arena/candidates). Il battle_state
    restituito va conservato dal chiamante (es. nello stato della
    pagina web) e rimandato indietro ad ogni chiamata successiva - il
    server non lo ricorda tra una richiesta e l'altra."""
    knight = _get_knight_or_404(conn, knight_id)
    if not knight["is_knight"]:
        raise HTTPException(status_code=403, detail="Sei ancora un Apprendista - l'Arena resta chiusa finché non superi la Prova Finale.")
    armor = get_armor(knight["armor_name"], conn)

    battle_state = start_battle(conn, knight, armor, opponent=req.opponent)
    return {"battle_state": battle_state}


@app.post("/characters/{knight_id}/arena/move")
def api_arena_move(knight_id: int, req: ArenaMoveRequest, conn=Depends(get_db)):
    """Sposta il giocatore verso (x, y) sulla mappa - Fase 1: solo
    visivo, non blocca né abilita ancora nessuna azione di
    combattimento (vedi api/arena_session.py). Muove anche
    l'avversario di un piccolo passo a caso."""
    knight = _get_knight_or_404(conn, knight_id)

    log = move_player(knight, req.battle_state, req.x, req.y)
    save_knight(conn, knight)

    return {"log": log, "character": _knight_payload(conn, knight), "battle_state": req.battle_state}


@app.post("/characters/{knight_id}/arena/declare")
def api_arena_declare(knight_id: int, req: ArenaDeclareRequest, conn=Depends(get_db)):
    """Metà 1 del round: dichiari Attacca o Carica."""
    knight = _get_knight_or_404(conn, knight_id)
    armor = get_armor(knight["armor_name"], conn)

    if req.action == "attacca" and (not req.technique_name or req.technique_power is None):
        raise HTTPException(status_code=400, detail="Serve una tecnica (nome e potenza) per attaccare")

    log, fight_over, winner = resolve_declare(
        knight, armor, req.action, req.technique_name, req.technique_power, req.battle_state,
        technique_type=req.technique_type,
        technique_launch_desc=req.technique_launch_desc, technique_effect_desc=req.technique_effect_desc,
    )

    if fight_over:
        _handle_fight_conclusion(conn, knight, req.battle_state, winner)
        return {
            "log": log, "fight_over": True, "won": winner == "player",
            "character": _knight_payload(conn, knight), "battle_state": None,
        }

    save_knight(conn, knight)
    return {
        "log": log, "fight_over": False,
        "character": _knight_payload(conn, knight), "battle_state": req.battle_state,
    }


@app.post("/characters/{knight_id}/arena/react")
def api_arena_react(knight_id: int, req: ArenaReactRequest, conn=Depends(get_db)):
    """Metà 2 del round: reagisci (Difenditi, Contrattacca o Incassa) a
    un attacco già dichiarato dall'avversario (visto in anticipo)."""
    knight = _get_knight_or_404(conn, knight_id)
    armor = get_armor(knight["armor_name"], conn)

    if req.battle_state.get("pending_opponent_technique") is None:
        raise HTTPException(status_code=400, detail="Nessun attacco in sospeso a cui reagire")

    my_techniques = [dict(t) for t in get_techniques_for_armor(knight["armor_name"], conn)]
    # Le tecniche difensive personalizzate (richiesto in chat) contano
    # anche loro per la scelta automatica di "Difenditi" - prima
    # venivano ignorate, solo quelle del catalogo erano considerate.
    my_techniques += [dict(t) for t in get_custom_techniques(conn, knight_id)]
    my_defense = find_defensive_technique(my_techniques)

    log, fight_over, winner = resolve_react(
        knight, armor, req.action, my_defense, req.battle_state,
        counter_technique_name=req.counter_technique_name, counter_technique_power=req.counter_technique_power,
        counter_technique_type=req.counter_technique_type, counter_technique_launch_desc=req.counter_technique_launch_desc,
        counter_technique_effect_desc=req.counter_technique_effect_desc,
    )

    if fight_over:
        _handle_fight_conclusion(conn, knight, req.battle_state, winner)
        return {
            "log": log, "fight_over": True, "won": winner == "player",
            "character": _knight_payload(conn, knight), "battle_state": None,
        }

    save_knight(conn, knight)
    return {
        "log": log, "fight_over": False,
        "character": _knight_payload(conn, knight), "battle_state": req.battle_state,
    }


@app.post("/characters/{knight_id}/arena/retreat")
def api_arena_retreat(knight_id: int, conn=Depends(get_db)):
    knight = _get_knight_or_404(conn, knight_id)
    finalize_fight(knight)
    save_knight(conn, knight)
    return {"character": _knight_payload(conn, knight)}
