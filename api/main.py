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
import json

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
    KNIGHTHOOD_LEVEL, RETRY_STAGE_ON_FAILURE, TRAINING_STAGES, resolve_skill_check,
    build_stage_context, build_opponent_from_armor,
)
from core.missions import (
    MISSION_ID, TOTAL_HOUSES, HOUSE_ORDER, COSMO_MAX_REWARD, DENARO_REWARD,
    get_house_guardian, get_house_content, resolve_persuasion,
    COLONNE_MISSION_ID, COLONNE_START_NODE, COLONNE_NODES,
    get_colonne_node_content, pick_duel_armor_for_node, resolve_colonne_ending,
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

# Stessa cosa per gli sfondi personalizzati dell'Arena (richiesto in
# chat: le decorazioni geometriche non reggevano il confronto).
ARENA_BACKGROUNDS_DIR = Path(__file__).resolve().parent.parent / "arena_backgrounds"
ARENA_BACKGROUNDS_DIR.mkdir(exist_ok=True)
app.mount("/arena_backgrounds", StaticFiles(directory=str(ARENA_BACKGROUNDS_DIR)), name="arena_backgrounds")


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
    elif battle_state.get("is_spar"):
        # Lo scontro leggero della tappa "Fianco a fianco" (richiesto
        # in chat) - si avanza comunque, vinca o perda: qui si fa
        # pratica, non si rischia l'addestramento.
        knight["training_stage"] += 1
    elif battle_state.get("is_mission"):
        # Un duello delle Missioni, quale che sia (richiesto in chat) -
        # sulla vittoria si avanza (Casa successiva per la Scalata, il
        # nodo win_next per le Colonne - completando la missione con la
        # ricompensa se è l'ultimo passo); sulla sconfitta si applica
        # lose_next (per la Scalata coincide sempre con restare sulla
        # stessa Casa) - il giocatore sceglierà se ritentare o
        # abbandonare (gestito lato frontend, nessuna penalità qui).
        if knight["mission_id"] == MISSION_ID:
            if winner == "player":
                knight["mission_stage"] += 1
                _complete_scalata_if_done(conn, knight)
        elif knight["mission_id"] == COLONNE_MISSION_ID:
            node_id = knight["mission_node"] or COLONNE_START_NODE
            node = COLONNE_NODES[node_id]
            knight["mission_node"] = node["win_next"] if winner == "player" else node["lose_next"]
            if winner == "player":
                _complete_colonne_if_done(conn, knight)
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
        # Il dizionario già interpretato (non la stringa JSON grezza),
        # stesso principio di weekly_schedule_list qui sopra.
        "arena_backgrounds": json.loads(knight["arena_backgrounds"] or "{}"),
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


VALID_ARENA_THEMES = {"atene", "siberia", "deserto", "colosseo", "piramidi"}
# Una "sede" per ciascuna delle 13 divinità del catalogo (richiesto in
# chat), oltre ai 5 temi elementali già esistenti - stessa galleria,
# stesso meccanismo di upload, solo più chiavi ammesse. "Black Saint"
# ha uno spazio nel nome: qui uso una chiave "sicura" (black_saint) per
# l'URL/il dizionario, la Divinità vera resta quella nel catalogo.
VALID_DIVINITY_ARENA_KEYS = {
    "athena", "hades", "nettuno", "odino", "ares", "artemide", "zeus",
    "crono", "eris", "saturno", "lucifero", "black_saint", "apollo",
}
VALID_ARENA_KEYS = VALID_ARENA_THEMES | VALID_DIVINITY_ARENA_KEYS


@app.post("/characters/{knight_id}/arena-background/{theme}")
async def api_upload_arena_background(knight_id: int, theme: str, file: UploadFile = File(...), conn=Depends(get_db)):
    """Carica un'immagine di sfondo personalizzata per UNO dei 5 temi
    elementali dell'Arena o per una delle 13 "sedi" di divinità
    (richiesto in chat) - uno sfondo solo, uguale per tutti, aveva poco
    senso: meglio una galleria, un'immagine per ciascuno. Le immagini
    sono un dizionario JSON chiave->percorso salvato in
    arena_backgrounds; caricarne una nuova per una chiave sovrascrive
    solo quella, le altre restano intatte."""
    if theme not in VALID_ARENA_KEYS:
        raise HTTPException(status_code=400, detail=f"Tema/divinità non valido - deve essere uno tra: {', '.join(sorted(VALID_ARENA_KEYS))}.")
    knight = _get_knight_or_404(conn, knight_id)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        raise HTTPException(status_code=400, detail="Formato immagine non supportato (usa PNG, JPG, WEBP o GIF).")

    filename = f"knight_{knight_id}_{theme}{ext}"
    dest = ARENA_BACKGROUNDS_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    backgrounds = json.loads(knight["arena_backgrounds"] or "{}")
    backgrounds[theme] = f"/arena_backgrounds/{filename}"
    knight["arena_backgrounds"] = json.dumps(backgrounds)
    save_knight(conn, knight)
    return {"arena_backgrounds": backgrounds}


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


class TrainingChoiceRequest(BaseModel):
    option_index: int


@app.post("/characters/{knight_id}/training-path/attempt")
def api_training_attempt(knight_id: int, req: TrainingChoiceRequest, conn=Depends(get_db)):
    """Un vero tiro di dado per una tappa 'choice_check' (richiesto in
    chat: prima "scegli l'approccio, poi tira" - una decisione vera
    prima del dado, non solo un pulsante nudo) - la statistica usata
    nel tiro dipende dall'approccio scelto, non è più fissa per tappa.
    NON avanza la tappa da solo: sul successo dà un piccolo premio
    permanente alla statistica scelta, poi il chiamante userà
    .../advance per proseguire; sul fallimento, il chiamante può
    richiamare di nuovo questo stesso endpoint (anche con un approccio
    diverso) o comunque .../advance (accetta il fallimento e va avanti
    senza premio)."""
    knight = _get_knight_or_404(conn, knight_id)
    if knight["is_knight"]:
        raise HTTPException(status_code=400, detail="Hai già completato l'addestramento.")
    if knight["training_stage"] >= FINAL_TRIAL_STAGE - 1:
        raise HTTPException(status_code=400, detail="Non c'è nessuna tappa da tentare in questo momento.")

    stage_def = TRAINING_STAGES[knight["training_stage"]]
    if stage_def["type"] != "choice_check":
        raise HTTPException(status_code=400, detail="Questa tappa non richiede una prova a dado.")
    if not (0 <= req.option_index < len(stage_def["approaches"])):
        raise HTTPException(status_code=400, detail="Approccio non valido.")

    techniques = [dict(t) for t in get_techniques_for_armor(knight["armor_name"], conn)]
    ctx = build_stage_context(
        knight["master_name"], knight["master_armor_name"], knight["companion1_name"],
        knight["companion2_name"], techniques, knight["armor_name"],
    )
    stat = stage_def["approaches"][req.option_index]["stat"]
    success = resolve_skill_check(knight, stat)
    if success:
        knight[stat] += 1  # piccolo premio permanente, PLACEHOLDER come le altre formule
        save_knight(conn, knight)

    text = (stage_def["success_text"] if success else stage_def["failure_text"]).format(**ctx)
    return {"success": success, "text": text, "stat": stat}


@app.post("/characters/{knight_id}/training-path/choose")
def api_training_choose(knight_id: int, req: TrainingChoiceRequest, conn=Depends(get_db)):
    """Risolve una scelta per una tappa 'choice' (richiesto in chat) -
    applica l'eventuale premio permanente alla statistica dell'opzione
    scelta, restituisce l'esito narrativo. Non avanza la tappa da solo
    (il chiamante userà .../advance dopo, come per uno skill_check
    riuscito) - una scelta non si "fallisce", ma restare coerenti con
    lo stesso schema di avanzamento evita due percorsi diversi nel
    frontend."""
    knight = _get_knight_or_404(conn, knight_id)
    if knight["is_knight"]:
        raise HTTPException(status_code=400, detail="Hai già completato l'addestramento.")
    if knight["training_stage"] >= FINAL_TRIAL_STAGE - 1:
        raise HTTPException(status_code=400, detail="Non c'è nessuna tappa da scegliere in questo momento.")

    stage_def = TRAINING_STAGES[knight["training_stage"]]
    if stage_def["type"] != "choice":
        raise HTTPException(status_code=400, detail="Questa tappa non prevede una scelta.")
    if not (0 <= req.option_index < len(stage_def["options"])):
        raise HTTPException(status_code=400, detail="Scelta non valida.")

    option = stage_def["options"][req.option_index]
    if option.get("bonus_stat"):
        knight[option["bonus_stat"]] += 1
        save_knight(conn, knight)

    techniques = [dict(t) for t in get_techniques_for_armor(knight["armor_name"], conn)]
    ctx = build_stage_context(
        knight["master_name"], knight["master_armor_name"], knight["companion1_name"],
        knight["companion2_name"], techniques, knight["armor_name"],
    )
    return {"text": option["outcome_text"].format(**ctx)}


@app.post("/characters/{knight_id}/training-path/spar/start")
def api_start_spar(knight_id: int, conn=Depends(get_db)):
    """Avvia lo scontro leggero della tappa 'Fianco a fianco' (richiesto
    in chat) - stesso motore della Prova Finale, ma contro il secondo
    compagno (il primo resta riservato alla Prova Finale) e marcato
    is_spar invece di is_trial: la conclusione (vedi
    _handle_fight_conclusion) fa avanzare la tappa comunque, vinca o
    perda - qui si fa pratica, non si rischia l'addestramento."""
    knight = _get_knight_or_404(conn, knight_id)
    if knight["is_knight"]:
        raise HTTPException(status_code=400, detail="Hai già completato l'addestramento.")
    if knight["training_stage"] >= FINAL_TRIAL_STAGE - 1:
        raise HTTPException(status_code=400, detail="Non c'è nessuno scontro di prova in questo momento.")

    stage_def = TRAINING_STAGES[knight["training_stage"]]
    if stage_def["type"] != "spar":
        raise HTTPException(status_code=400, detail="Questa tappa non prevede uno scontro.")

    armor = get_armor(knight["armor_name"], conn)
    spar_opponent = generate_trial_opponent(conn, False, knight["companion2_name"], "", armor)
    battle_state = start_battle(conn, knight, armor, opponent=spar_opponent)
    battle_state["is_spar"] = True
    return {"battle_state": battle_state}


# --------------------------- Missioni ---------------------------

def _require_mission_ready(knight: dict) -> None:
    """Controlli comuni agli endpoint delle Missioni - solo i
    Cavalieri (non gli Apprendisti) possono avere una missione."""
    if not knight["is_knight"]:
        raise HTTPException(status_code=403, detail="Devi prima completare l'apprendistato e diventare Cavaliere.")


def _mission_flags_set(knight: dict) -> set[str]:
    return set(f for f in knight["mission_flags"].split(",") if f)


@app.get("/characters/{knight_id}/mission")
def api_get_mission(knight_id: int, conn=Depends(get_db)):
    """Lo stato della missione in corso, quale che sia (richiesto in
    chat: più di una missione, ciascuna con la sua forma) - se non ce
    n'è una attiva, il chiamante mostrerà l'elenco di quelle
    disponibili."""
    knight = _get_knight_or_404(conn, knight_id)
    _require_mission_ready(knight)
    if not knight["mission_id"]:
        return {"active": False}

    if knight["mission_id"] == MISSION_ID:
        house_name = HOUSE_ORDER[knight["mission_stage"] - 1]
        guardian_name = get_house_guardian(conn, house_name)
        house = get_house_content(knight["mission_stage"], guardian_name)
        return {"active": True, "mission_id": knight["mission_id"], "house": house}

    if knight["mission_id"] == COLONNE_MISSION_ID:
        node_id = knight["mission_node"] or COLONNE_START_NODE
        node = get_colonne_node_content(node_id)
        return {"active": True, "mission_id": knight["mission_id"], "node": node}

    return {"active": False}


class StartMissionRequest(BaseModel):
    mission_id: str


@app.post("/characters/{knight_id}/mission/start")
def api_start_mission(knight_id: int, req: StartMissionRequest, conn=Depends(get_db)):
    """Avvia una missione (una alla volta, richiesto in chat: non se ne
    può avere già una in corso)."""
    knight = _get_knight_or_404(conn, knight_id)
    _require_mission_ready(knight)
    if knight["mission_id"]:
        raise HTTPException(status_code=400, detail="Hai già una missione in corso.")
    if req.mission_id not in (MISSION_ID, COLONNE_MISSION_ID):
        raise HTTPException(status_code=400, detail="Missione sconosciuta.")

    knight["mission_id"] = req.mission_id
    if req.mission_id == MISSION_ID:
        knight["mission_stage"] = 1
    else:
        knight["mission_node"] = COLONNE_START_NODE
        knight["mission_flags"] = ""
    save_knight(conn, knight)
    return {"active": True}


def _complete_scalata_if_done(conn, knight: dict) -> bool:
    """Se mission_stage ha superato l'ultima Casa, assegna la
    ricompensa (Cosmo massimo + denaro, richiesto in chat) e chiude la
    missione. Restituisce True se la missione è stata completata in
    questa chiamata. Non salva da sola - il chiamante deve comunque
    fare save_knight dopo."""
    if knight["mission_stage"] <= TOTAL_HOUSES:
        return False
    knight["cosmo_max"] += COSMO_MAX_REWARD
    knight["cosmo_cur"] = knight["cosmo_max"]
    knight["denaro"] += DENARO_REWARD
    knight["mission_id"] = ""
    knight["mission_stage"] = 0
    cal = get_calendar_display(knight["created_at"], knight["game_minutes"])
    add_biography_entry(
        conn, knight["id"], knight["game_minutes"],
        f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} completa "
        f"la Scalata delle Dodici Case, guadagnando {COSMO_MAX_REWARD} Cosmo massimo e {DENARO_REWARD} denaro.",
    )
    return True


def _complete_colonne_if_done(conn, knight: dict) -> tuple[bool, str]:
    """Se il nodo attuale è 'fine', assegna la ricompensa (base + un
    eventuale bonus dai flag accumulati durante il percorso, richiesto
    in chat: una conseguenza vera per la scelta morale centrale) e
    chiude la missione. Restituisce (completata, testo del finale)."""
    if knight["mission_node"] != "fine":
        return False, ""
    ending = resolve_colonne_ending(_mission_flags_set(knight))
    knight["cosmo_max"] += COSMO_MAX_REWARD
    knight["cosmo_cur"] = knight["cosmo_max"]
    knight["denaro"] += DENARO_REWARD + ending["bonus"].get("denaro", 0)
    knight["mission_id"] = ""
    knight["mission_node"] = ""
    knight["mission_flags"] = ""
    cal = get_calendar_display(knight["created_at"], knight["game_minutes"])
    add_biography_entry(
        conn, knight["id"], knight["game_minutes"],
        f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} completa "
        f"Le Colonne dei Sette Mari.",
    )
    return True, ending["text"]


@app.post("/characters/{knight_id}/mission/persuade")
def api_mission_persuade(knight_id: int, conn=Depends(get_db)):
    """Tenta di convincere il Guardiano della Casa attuale a lasciarti
    passare senza combattere (richiesto in chat: bivio vero ad ogni
    Casa, non solo duelli) - un vero tiro di dado, si può fallire.
    Specifico della Scalata delle Dodici Case."""
    knight = _get_knight_or_404(conn, knight_id)
    _require_mission_ready(knight)
    if knight["mission_id"] != MISSION_ID:
        raise HTTPException(status_code=400, detail="Nessuna Scalata delle Dodici Case in corso.")

    house_name = HOUSE_ORDER[knight["mission_stage"] - 1]
    guardian_name = get_house_guardian(conn, house_name)
    content = get_house_content(knight["mission_stage"], guardian_name)

    success = resolve_persuasion(knight)
    mission_completed = False
    if success:
        knight["mission_stage"] += 1
        mission_completed = _complete_scalata_if_done(conn, knight)
        save_knight(conn, knight)

    return {
        "success": success,
        "text": content["persuade_success"] if success else content["persuade_failure"],
        "mission_completed": mission_completed,
    }


class MissionChoiceRequest(BaseModel):
    option_index: int


@app.post("/characters/{knight_id}/mission/choose")
def api_mission_choose(knight_id: int, req: MissionChoiceRequest, conn=Depends(get_db)):
    """Risolve una scelta di un nodo 'choice' delle Colonne dei Sette
    Mari (richiesto in chat: bivi che portano DAVVERO a strade diverse)
    - applica l'eventuale flag dell'opzione scelta (che può cambiare il
    finale più avanti) e passa al nodo successivo."""
    knight = _get_knight_or_404(conn, knight_id)
    _require_mission_ready(knight)
    if knight["mission_id"] != COLONNE_MISSION_ID:
        raise HTTPException(status_code=400, detail="Nessuna missione a bivi in corso.")

    node_id = knight["mission_node"] or COLONNE_START_NODE
    node = COLONNE_NODES[node_id]
    if node["type"] != "choice":
        raise HTTPException(status_code=400, detail="Questo nodo non prevede una scelta.")
    if not (0 <= req.option_index < len(node["options"])):
        raise HTTPException(status_code=400, detail="Scelta non valida.")

    option = node["options"][req.option_index]
    if option.get("flag"):
        flags = _mission_flags_set(knight)
        flags.add(option["flag"])
        knight["mission_flags"] = ",".join(sorted(flags))
    knight["mission_node"] = option["next"]
    save_knight(conn, knight)
    return {"next_node": option["next"]}


@app.post("/characters/{knight_id}/mission/attempt")
def api_mission_attempt(knight_id: int, conn=Depends(get_db)):
    """Un vero tiro di dado per un nodo 'skill_check' delle Colonne dei
    Sette Mari (richiesto in chat) - a seconda dell'esito, porta a nodi
    SUCCESSIVI DIVERSI (non solo testo diverso sulla stessa strada)."""
    knight = _get_knight_or_404(conn, knight_id)
    _require_mission_ready(knight)
    if knight["mission_id"] != COLONNE_MISSION_ID:
        raise HTTPException(status_code=400, detail="Nessuna missione a bivi in corso.")

    node_id = knight["mission_node"] or COLONNE_START_NODE
    node = COLONNE_NODES[node_id]
    if node["type"] != "skill_check":
        raise HTTPException(status_code=400, detail="Questo nodo non prevede una prova a dado.")

    success = resolve_skill_check(knight, node["stat"])
    knight["mission_node"] = node["success_next"] if success else node["failure_next"]
    save_knight(conn, knight)
    return {
        "success": success,
        "text": node["success_text"] if success else node["failure_text"],
        "next_node": knight["mission_node"],
    }


@app.post("/characters/{knight_id}/mission/duel/start")
def api_mission_duel_start(knight_id: int, conn=Depends(get_db)):
    """Avvia il duello vero del punto in cui ti trovi nella missione
    attiva, quale che sia (richiesto in chat) - stesso motore di
    battaglia della Prova Finale, marcato is_mission perché
    .../arena/declare e .../arena/react sappiano gestirne la
    conclusione diversamente."""
    knight = _get_knight_or_404(conn, knight_id)
    _require_mission_ready(knight)
    if not knight["mission_id"]:
        raise HTTPException(status_code=400, detail="Nessuna missione in corso.")

    armor = get_armor(knight["armor_name"], conn)

    if knight["mission_id"] == MISSION_ID:
        house_name = HOUSE_ORDER[knight["mission_stage"] - 1]
        guardian_name = get_house_guardian(conn, house_name)
        opponent = build_opponent_from_armor(conn, house_name, guardian_name)
        battle_state = start_battle(conn, knight, armor, opponent=opponent)
        battle_state["is_mission"] = True
        return {"battle_state": battle_state}

    if knight["mission_id"] == COLONNE_MISSION_ID:
        node_id = knight["mission_node"] or COLONNE_START_NODE
        node = COLONNE_NODES[node_id]
        if node["type"] != "duel":
            raise HTTPException(status_code=400, detail="Questo nodo non prevede uno scontro.")
        duel_armor_name = pick_duel_armor_for_node(node_id)
        guardian_name = get_house_guardian(conn, duel_armor_name)
        opponent = build_opponent_from_armor(conn, duel_armor_name, guardian_name)
        battle_state = start_battle(conn, knight, armor, opponent=opponent)
        battle_state["is_mission"] = True
        return {"battle_state": battle_state, "intro": node["intro"].format(guardian=guardian_name)}

    raise HTTPException(status_code=400, detail="Missione sconosciuta.")


@app.post("/characters/{knight_id}/mission/abandon")
def api_abandon_mission(knight_id: int, conn=Depends(get_db)):
    """Abbandona la missione in corso, quale che sia (richiesto in
    chat: diverso dall'uscire dal gioco, che invece la congela dov'era)
    - si torna liberi, senza nessuna ricompensa."""
    knight = _get_knight_or_404(conn, knight_id)
    if not knight["mission_id"]:
        raise HTTPException(status_code=400, detail="Nessuna missione da abbandonare.")
    knight["mission_id"] = ""
    knight["mission_stage"] = 0
    knight["mission_node"] = ""
    knight["mission_flags"] = ""
    save_knight(conn, knight)
    return {"abandoned": True}


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
    if knight["mission_id"]:
        # Missioni (richiesto in chat): "mentre sono in missione, non
        # posso essere in arena/in taverna" - stesso principio
        # dell'apprendistato, l'Allenamento resta bloccato.
        raise HTTPException(status_code=403, detail="Sei in missione - non puoi allenarti liberamente finché non la completi o l'abbandoni.")
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
    if knight["mission_id"]:
        raise HTTPException(status_code=403, detail="Sei in missione - l'Arena resta chiusa finché non la completi o l'abbandoni.")
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
    if knight["mission_id"]:
        raise HTTPException(status_code=403, detail="Sei in missione - l'Arena resta chiusa finché non la completi o l'abbandoni.")
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
