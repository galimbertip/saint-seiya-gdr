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
    get_armor, get_techniques_for_armor, list_armors_for_player_level, get_roster, get_world_chronicle,
    add_biography_entry, get_biography_entries, get_custom_techniques, add_custom_technique,
    release_roster_slot, get_roster_entry, get_world_minutes,
    get_tavern_relationship, adjust_tavern_affinity, add_tavern_message, get_tavern_conversation,
    get_tavern_bartender, get_tavern_seating,
)
from core.tavern import (
    resolve_tavern_response, TAVERN_REALMS, get_faction_relation, RELATION_STARTING_AFFINITY,
    check_mission_offer, MISSION_OFFER_TEXTS,
    ensure_tavern_bartender, ensure_tavern_seating, maybe_reshuffle_tavern, TABLE_LAYOUT,
    TAVERN_TONES,
)
from core.world_sim import apply_npc_damage, ensure_institutional_alignments, ensure_divinity_alignments
from core.renown import (
    RENOWN_SCALATA_COMPLETE, RENOWN_GRAPH_MISSION_COMPLETE, RENOWN_TOURNAMENT_PER_ROUND,
    RENOWN_TOURNAMENT_CHAMPION_BONUS, RENOWN_INFERI_COMPLETE, RENOWN_DEFENSE_PER_WAVE,
    RENOWN_DEFENSE_VICTORY_BONUS, renown_title, has_staff_osservatore, STAFF_OSSERVATORE_AFFINITY_THRESHOLD,
)
from core.meditation import (
    can_meditate, minutes_until_next_meditation, next_sequence_length,
    generate_sequence, resolve_meditation_reward, MEDITATION_TIME_MINUTES,
)
from core.squad_battle import (
    DEFENSE_MISSION_ID, UNITS_PER_SIDE,
    get_defense_team_candidates, start_defense_mission, resolve_squad_action,
    resolve_defense_reward, _current_actor, _skip_dead_and_autoresolve_enemies,
    abandon_defense_mission,
)
from core.character_factory import (
    create_knight, get_knight, list_knights, delete_knight, save_knight,
    ArmorNotFoundError, ArmorLevelTooHighError, ArmorAlreadyClaimedError, ensure_roster_populated,
    ensure_npc_stats_generated,
)
from core.fm_manager import (
    RosterManager, get_calendar_display, parse_weekly_schedule,
    serialize_weekly_schedule, TRAINING_FOCUS_OPTIONS,
)
from core.arena_manager import (
    get_unlocked_senses, calculate_movement_points, GEO_ORIGINS,
    custom_technique_slots, calculate_custom_technique_power, allowed_custom_technique_elements,
)
from core.version import APP_VERSION
from core.institutional_npcs import get_institutional_npcs
from core.divinities import get_divinity_npcs
from core.app_logger import get_logger
log = get_logger(__name__)
from core.training_path import (
    render_stage, generate_trial_opponent, FINAL_TRIAL_STAGE, LEVEL_UP_AFTER_STAGE,
    KNIGHTHOOD_LEVEL, RETRY_STAGE_ON_FAILURE, TRAINING_STAGES, resolve_skill_check,
    build_stage_context, build_opponent_from_armor, get_training_location, DEFAULT_TRAINING_LOCATION,
)
from core.missions import (
    MISSION_ID, TOTAL_HOUSES, HOUSE_ORDER, COSMO_MAX_REWARD, DENARO_REWARD,
    get_house_guardian, get_house_content, resolve_persuasion,
    GRAPH_MISSIONS, get_graph_node_content, pick_graph_duel_armor, resolve_graph_mission_ending,
    TOURNAMENT_MISSIONS, is_eligible_for_tournament,
    generate_tournament_bracket, save_tournament_bracket, load_tournament_bracket, build_tournament_opponent,
    resolve_tournament_reward, tournament_round_label, tournament_round_label_with_preposition,
    INFERI_MISSION_ID, INFERI_STAGES, INFERI_PUZZLES, INFERI_AMBUSH_THRESHOLD, JUDGE_ARMORS, SPECTER_AMBUSH_ARMORS,
    get_inferi_stage, pick_inferi_puzzle, check_inferi_answer, resolve_inferi_reward,
)
from core.alignment import persuasion_flavor_line
from core.apprentice_fates import (
    resolve_companions_fates, resolve_soldier_activity, retrain_for_new_armor, SOLDIER_ACTIVITIES,
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
    ensure_npc_stats_generated(conn)
    ensure_institutional_alignments(conn)
    ensure_divinity_alignments(conn)
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
    defense_technique_name: Optional[str] = None
    defense_technique_power: Optional[int] = None
    defense_technique_type: Optional[str] = None
    defense_technique_launch_desc: Optional[str] = None
    defense_technique_effect_desc: Optional[str] = None
    counter_technique_name: Optional[str] = None
    counter_technique_power: Optional[int] = None
    counter_technique_type: Optional[str] = None
    counter_technique_launch_desc: Optional[str] = None
    counter_technique_effect_desc: Optional[str] = None


class DefenseStartRequest(BaseModel):
    mode: Literal["random", "selected"]
    ally_armor_names: list[str] = []  # usato solo se mode == "selected"


class DefenseActionRequest(BaseModel):
    battle_state: dict
    actor_id: str
    action: Literal["attacca", "difendi", "carica"]
    target_id: Optional[str] = None
    technique_name: Optional[str] = None
    technique_power: Optional[int] = None
    technique_type: Optional[str] = None
    target_mode: Literal["singolo", "area"] = "singolo"
    counter_technique_name: Optional[str] = None
    counter_technique_power: Optional[int] = None
    counter_technique_type: Optional[str] = None
    counter_technique_launch_desc: Optional[str] = None
    counter_technique_effect_desc: Optional[str] = None
    # La tecnica difensiva scelta dal giocatore (richiesto in chat: la
    # difesa dev'essere una scelta, non qualcosa deciso in automatico
    # dal sistema - stessa struttura di Attacco Base + tecniche del
    # Contrattacco, applicata anche qui). None = Difesa Base generica.
    defense_technique_name: Optional[str] = None
    defense_technique_power: Optional[int] = None
    defense_technique_type: Optional[str] = None
    defense_technique_launch_desc: Optional[str] = None
    defense_technique_effect_desc: Optional[str] = None


class DefenseAbandonRequest(BaseModel):
    battle_state: dict


# --------------------------- Serializzazione ---------------------------

def _record_fight_outcome(conn, knight: dict, opponent_name: str, winner: str) -> None:
    """Aggiunge una voce al diario per la vittoria/sconfitta appena
    conclusa (richiesto in chat) - chiamata da entrambi i punti in cui
    uno scontro può finire (declare e react), invece di duplicare la
    stessa logica due volte."""
    cal = get_calendar_display(knight["game_minutes"])
    if winner == "player":
        entry = f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} sconfigge {opponent_name} nell'Arena."
    else:
        entry = f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} viene sconfitto da {opponent_name} nell'Arena."
    add_biography_entry(conn, knight["id"], knight["game_minutes"], entry)


def _handle_fight_conclusion(conn, knight: dict, battle_state: dict, winner: str) -> dict:
    """Gestisce la conclusione di uno scontro - normale (Arena) o la
    Prova Finale (riconosciuta dal flag is_trial nel battle_state,
    impostato da .../training-path/trial/start) in modo diverso
    (richiesto in chat: la Prova Finale ora è un vero combattimento,
    non un tiro di dado narrato - la sua conclusione va gestita qui,
    non più in un endpoint a parte). Chiama finalize_fight e
    save_knight al posto del chiamante, non serve richiamarli anche
    fuori da qui. Restituisce un dict con eventuali informazioni extra
    per il chiamante - per ora solo se una Missione è stata completata
    proprio in questo duello (bug corretto in chat: prima veniva
    scartato, il frontend non aveva modo di saperlo e di mostrare la
    ricompensa/il finale)."""
    opponent_name = battle_state["opponent"]["name"]
    finalize_fight(knight)
    extra: dict = {}

    # Le tre barre vere anche per i PNG (richiesto in chat) - se
    # l'avversario era il PNG canonico del roster (non un nome casuale
    # dell'Arena), persiste quanta Vita/Cosmo gli restano: la prossima
    # volta che lo incontri, arriverà ancora debole se ha perso di
    # recente, non di nuovo al massimo come se nulla fosse successo.
    opponent = battle_state["opponent"]
    if opponent.get("is_roster_linked") and opponent.get("armor_name"):
        apply_npc_damage(conn, opponent["armor_name"], opponent["vita_cur"], opponent["cosmo_cur"], knight["game_minutes"])

    if battle_state.get("is_trial"):
        cal = get_calendar_display(knight["game_minutes"])
        if winner == "player":
            knight["training_stage"] = FINAL_TRIAL_STAGE
            knight["is_knight"] = 1
            knight["player_level"] = max(knight["player_level"], KNIGHTHOOD_LEVEL)
            add_biography_entry(
                conn, knight["id"], knight["game_minutes"],
                f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} "
                f"supera la Prova Finale contro {opponent_name} e diventa Cavaliere.",
            )
            # La tua vicenda con questa armatura si conclude qui
            # (richiesto in chat) - i compagni non ottengono la Cloth,
            # il loro destino si decide adesso, insieme al tuo.
            fates = resolve_companions_fates(knight["companion1_name"], knight["companion2_name"])
            for fate in fates:
                add_biography_entry(conn, knight["id"], knight["game_minutes"], fate)
            extra["companion_fates"] = fates
        else:
            # Non si imposta più da sola la tappa di ripreparazione
            # (richiesto in chat: la scelta - ritenta, riaddestrati
            # altrove, diventa Soldato Semplice, o muori - spetta ora
            # al giocatore, ad ogni singolo fallimento) - il frontend
            # la presenterà, e chiamerà uno degli endpoint dedicati in
            # base alla scelta.
            add_biography_entry(
                conn, knight["id"], knight["game_minutes"],
                f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} "
                f"non supera la Prova Finale contro {opponent_name}.",
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
                if _complete_scalata_if_done(conn, knight):
                    extra["mission_completed"] = True
                    extra["mission_ending_text"] = None
        elif knight["mission_id"] in GRAPH_MISSIONS:
            mission_id = knight["mission_id"]
            node_id = knight["mission_node"] or GRAPH_MISSIONS[mission_id]["start_node"]
            node = GRAPH_MISSIONS[mission_id]["nodes"][node_id]
            knight["mission_node"] = node["win_next"] if winner == "player" else node["lose_next"]
            if winner == "player":
                completed, ending_text = _complete_graph_mission_if_done(conn, knight)
                if completed:
                    extra["mission_completed"] = True
                    extra["mission_ending_text"] = ending_text
        elif knight["mission_id"] in TOURNAMENT_MISSIONS:
            extra.update(_conclude_tournament_round(conn, knight, winner))
        elif knight["mission_id"] == INFERI_MISSION_ID:
            extra.update(_conclude_inferi_duel(conn, knight, winner))
    else:
        _record_fight_outcome(conn, knight, opponent_name, winner)

    save_knight(conn, knight)
    return extra


def _knight_payload(conn, knight: dict) -> dict:
    """Impacchetta un knight con tutto il contesto che il frontend
    normalmente dovrebbe richiedere separatamente (armatura, tecniche,
    calendario, sensi, Punti Movimento) - una sola chiamata invece di
    cinque."""
    armor = get_armor(knight["armor_name"], conn)
    techniques = [dict(t) for t in get_techniques_for_armor(knight["armor_name"], conn)]
    calendar = get_calendar_display(knight["game_minutes"])
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
        # Il titolo onorifico derivato dalla Renown (richiesto in chat,
        # dalla roadmap) - calcolato qui, non salvato: cambia da solo
        # quando la Renown supera una soglia, niente da tenere in sync.
        "renown_title": renown_title(knight["renown"]),
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
    try:
        filename = f"knight_{knight_id}{ext}"
        dest = AVATARS_DIR / filename
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        knight["avatar_path"] = f"/avatars/{filename}"
        save_knight(conn, knight)
    except Exception:
        # Un log dettagliato invece di un 500 muto (richiesto in chat:
        # un errore così com'era non dava nessun indizio su cosa fosse
        # andato storto davvero) - qualunque cosa succeda qui, almeno
        # resta traccia nei log per capire la causa reale.
        log.exception(f"Caricamento avatar fallito per il cavaliere {knight_id}")
        raise HTTPException(status_code=500, detail="Caricamento immagine fallito - controlla i log del server per il dettaglio.")
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
    if knight["apprentice_status"] == "soldier":
        # Diventato Soldato Semplice dopo un fallimento della Prova
        # Finale (richiesto in chat) - non è più "in addestramento" in
        # questo senso, ha un suo percorso a parte (vedi .../soldier/*).
        return {"is_knight": False, "is_soldier": True}
    if knight["training_stage"] >= FINAL_TRIAL_STAGE - 1:
        own_armor = get_armor(knight["armor_name"], conn)
        own_techniques = [dict(t) for t in get_techniques_for_armor(knight["armor_name"], conn)]
        location = get_training_location(dict(own_armor), own_techniques) if own_armor else DEFAULT_TRAINING_LOCATION
        return {
            "is_knight": False, "ready_for_trial": True,
            "master_name": knight["master_name"], "master_armor_name": knight["master_armor_name"],
            "companion1_name": knight["companion1_name"], "companion2_name": knight["companion2_name"],
            "your_armor_name": knight["armor_name"], "location": location,
        }
    techniques = [dict(t) for t in get_techniques_for_armor(knight["armor_name"], conn)]
    own_armor = get_armor(knight["armor_name"], conn)
    stage = render_stage(
        knight["training_stage"] + 1, knight["master_name"], knight["master_armor_name"],
        knight["companion1_name"], knight["companion2_name"], techniques,
        your_armor_name=knight["armor_name"], own_armor=dict(own_armor) if own_armor else None,
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
        cal = get_calendar_display(knight["game_minutes"])
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
    own_armor = get_armor(knight["armor_name"], conn)
    ctx = build_stage_context(
        knight["master_name"], knight["master_armor_name"], knight["companion1_name"],
        knight["companion2_name"], techniques, knight["armor_name"], dict(own_armor) if own_armor else None,
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
    own_armor = get_armor(knight["armor_name"], conn)
    ctx = build_stage_context(
        knight["master_name"], knight["master_armor_name"], knight["companion1_name"],
        knight["companion2_name"], techniques, knight["armor_name"], dict(own_armor) if own_armor else None,
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


def _parse_inferi_flags(mission_flags: str) -> tuple[int | None, int | None]:
    """Le Prove degli Inferi (richiesto in chat, enigmi veri invece del
    tiro di dado) riusano mission_flags per un formato tutto loro,
    "stage:puzzle_index" - a differenza delle missioni a grafo, che lo
    usano come insieme di flag testuali. Restituisce (None, None) se
    il formato non corrisponde (nessun enigma ancora assegnato)."""
    parts = mission_flags.split(":")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]), int(parts[1])
    return None, None


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
    if knight["mission_id"] in GRAPH_MISSIONS:
        mission_id = knight["mission_id"]
        node_id = knight["mission_node"] or GRAPH_MISSIONS[mission_id]["start_node"]
        node = get_graph_node_content(mission_id, node_id)
        return {"active": True, "mission_id": mission_id, "node": node}
    if knight["mission_id"] in TOURNAMENT_MISSIONS:
        tournament_id = knight["mission_id"]
        settings = TOURNAMENT_MISSIONS[tournament_id]
        round_number = knight["mission_stage"]
        return {
            "active": True, "mission_id": tournament_id,
            "tournament": {
                "name": settings["name"], "round_number": round_number, "total_rounds": settings["rounds"],
                "round_label": tournament_round_label(tournament_id, round_number),
                "bracket": load_tournament_bracket(knight),
            },
        }
    if knight["mission_id"] == INFERI_MISSION_ID:
        stage = get_inferi_stage(knight["mission_stage"])
        alert = knight["mission_counter"]
        puzzle_data = None
        if stage is not None and alert < INFERI_AMBUSH_THRESHOLD:
            # Un enigma vero (richiesto in chat), non un tiro di dado -
            # va scelto UNA SOLA volta per prova e persistito
            # (mission_flags), altrimenti ogni ricarica della pagina
            # pescherebbe un enigma diverso e la risposta del giocatore
            # non avrebbe più senso rispetto a quello mostrato.
            stored_stage, stored_puzzle_index = _parse_inferi_flags(knight["mission_flags"])
            if stored_stage == knight["mission_stage"] and stored_puzzle_index is not None:
                question, options, _correct = INFERI_PUZZLES[knight["mission_stage"] - 1][stored_puzzle_index]
            else:
                stored_puzzle_index, picked = pick_inferi_puzzle(knight["mission_stage"])
                question, options = picked["question"], picked["options"]
                knight["mission_flags"] = f"{knight['mission_stage']}:{stored_puzzle_index}"
                save_knight(conn, knight)
            puzzle_data = {"question": question, "options": options}
        return {
            "active": True, "mission_id": INFERI_MISSION_ID,
            "inferi": {
                "stage_index": knight["mission_stage"], "total_stages": len(INFERI_STAGES),
                "stage_name": stage["name"] if stage else "La Sala dei Tre Giudici",
                "stage_text": stage["text"] if stage else "Hai attraversato tutte le prove. Solo un Giudice ti separa dal successo.",
                "alert": alert, "ambush_threshold": INFERI_AMBUSH_THRESHOLD,
                "is_ambush": stage is not None and alert >= INFERI_AMBUSH_THRESHOLD,
                "is_final_boss": stage is None,
                "puzzle": puzzle_data,
            },
        }
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
    known_missions = {MISSION_ID, INFERI_MISSION_ID} | set(GRAPH_MISSIONS) | set(TOURNAMENT_MISSIONS)
    if req.mission_id not in known_missions:
        raise HTTPException(status_code=400, detail="Missione sconosciuta.")
    if req.mission_id in TOURNAMENT_MISSIONS and not is_eligible_for_tournament(conn, knight, req.mission_id):
        raise HTTPException(status_code=400, detail="Non sei idoneo a iscriverti a questo torneo.")
    knight["mission_id"] = req.mission_id
    if req.mission_id == MISSION_ID:
        knight["mission_stage"] = 1
    elif req.mission_id == INFERI_MISSION_ID:
        knight["mission_stage"] = 1
        knight["mission_counter"] = 0
    elif req.mission_id in TOURNAMENT_MISSIONS:
        knight["mission_stage"] = 1
        bracket = generate_tournament_bracket(conn, knight, req.mission_id)
        save_tournament_bracket(knight, bracket)
    else:
        knight["mission_node"] = GRAPH_MISSIONS[req.mission_id]["start_node"]
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
    knight["renown"] += RENOWN_SCALATA_COMPLETE
    knight["mission_id"] = ""
    knight["mission_stage"] = 0
    cal = get_calendar_display(knight["game_minutes"])
    add_biography_entry(
        conn, knight["id"], knight["game_minutes"],
        f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} completa "
        f"la Scalata delle Dodici Case, guadagnando {COSMO_MAX_REWARD} Cosmo massimo e {DENARO_REWARD} Dracme.",
    )
    return True


def _conclude_inferi_duel(conn, knight: dict, winner: str) -> dict:
    """Gestisce l'esito di uno scontro delle Prove degli Inferi
    (richiesto in chat) - sia un'imboscata (che, se vinta, fa scendere
    l'allerta e permette di ritentare la stessa prova, non di avanzare
    gratis) sia il duello finale contro un Giudice (che, se vinto,
    chiude la missione con la ricompensa piena). Perdere QUALUNQUE
    scontro qui - imboscata o Giudice - chiude comunque la missione:
    un'infiltrazione scoperta non si ritenta (stesso principio dei
    tornei, coerente col tema: ti hanno preso)."""
    stage_index = knight["mission_stage"]
    is_final_boss = get_inferi_stage(stage_index) is None
    cal = get_calendar_display(knight["game_minutes"])
    extra: dict = {"tournament_champion": False}
    if winner == "player":
        if is_final_boss:
            reward = resolve_inferi_reward(len(INFERI_STAGES), is_champion=True)
            knight["denaro"] += reward["denaro"]
            knight["renown"] += RENOWN_INFERI_COMPLETE
            if reward["cosmo_max"]:
                knight["cosmo_max"] += reward["cosmo_max"]
                knight["cosmo_cur"] = knight["cosmo_max"]
            knight["mission_id"] = ""
            knight["mission_stage"] = 0
            knight["mission_counter"] = 0
            add_biography_entry(
                conn, knight["id"], knight["game_minutes"],
                f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} "
                f"attraversa le Prove degli Inferi e sconfigge un Giudice nella Sala dei Tre Giudici.",
            )
            extra["mission_completed"] = True
            extra["mission_ending_text"] = "Hai sconfitto un Giudice degli Inferi. L'infiltrazione è un successo completo."
            extra["tournament_champion"] = True
        else:
            knight["mission_counter"] = INFERI_AMBUSH_RESET_ALERT
    else:
        stages_completed = stage_index - 1
        reward = resolve_inferi_reward(stages_completed, is_champion=False)
        knight["denaro"] += reward["denaro"]
        knight["mission_id"] = ""
        knight["mission_stage"] = 0
        knight["mission_counter"] = 0
        outcome_label = "un Giudice degli Inferi" if is_final_boss else "uno Spettro in agguato"
        add_biography_entry(
            conn, knight["id"], knight["game_minutes"],
            f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} viene "
            f"sopraffatto da {outcome_label} durante l'infiltrazione negli Inferi, con {stages_completed} "
            f"prove superate prima di essere scoperto.",
        )
        extra["mission_completed"] = True
        extra["mission_ending_text"] = f"Sei stato sopraffatto. Prove superate prima di essere scoperto: {stages_completed}."
        extra["tournament_champion"] = False
    return extra


def _conclude_tournament_round(conn, knight: dict, winner: str) -> dict:
    """Gestisce l'esito di un round di torneo (richiesto in chat: vero
    a eliminazione diretta, niente ritentativi come nella Scalata o
    nelle missioni a grafo - qui perdere significa essere fuori,
    davvero) - avanza sulla vittoria (campione se era l'ultimo round),
    chiude tutto sull'eliminazione, con una ricompensa proporzionale ai
    round superati in entrambi i casi."""
    tournament_id = knight["mission_id"]
    settings = TOURNAMENT_MISSIONS[tournament_id]
    round_number = knight["mission_stage"]
    cal = get_calendar_display(knight["game_minutes"])
    extra: dict = {"tournament_champion": False}
    if winner == "player" and round_number < settings["rounds"]:
        # Non era l'ultimo round - si avanza, la missione resta attiva.
        knight["mission_stage"] += 1
        return extra
    rounds_completed = round_number if winner == "player" else round_number - 1
    is_champion = winner == "player"
    reward = resolve_tournament_reward(tournament_id, rounds_completed, is_champion)
    knight["denaro"] += reward["denaro"]
    knight["renown"] += RENOWN_TOURNAMENT_PER_ROUND * rounds_completed + (RENOWN_TOURNAMENT_CHAMPION_BONUS if is_champion else 0)
    if reward["cosmo_max"]:
        knight["cosmo_max"] += reward["cosmo_max"]
        knight["cosmo_cur"] = knight["cosmo_max"]
    knight["mission_id"] = ""
    knight["mission_stage"] = 0
    if is_champion:
        add_biography_entry(
            conn, knight["id"], knight["game_minutes"],
            f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} vince "
            f"{settings['name']}, diventandone campione.",
        )
        ending_text = "Vittoria! Sei il campione di questo torneo."
    else:
        label_with_prep = tournament_round_label_with_preposition(tournament_id, round_number)
        add_biography_entry(
            conn, knight["id"], knight["game_minutes"],
            f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} viene "
            f"eliminato {label_with_prep} di un torneo, con {rounds_completed} vittorie racimolate lungo il cammino.",
        )
        ending_text = f"Eliminato {label_with_prep}. Vittorie in totale: {rounds_completed}."
    extra["mission_completed"] = True
    extra["mission_ending_text"] = ending_text
    extra["tournament_champion"] = is_champion
    return extra


def _complete_graph_mission_if_done(conn, knight: dict) -> tuple[bool, str]:
    """Se il nodo attuale è 'fine', assegna la ricompensa (base + un
    eventuale bonus dai flag accumulati durante il percorso, richiesto
    in chat: una conseguenza vera per la scelta morale centrale) e
    chiude la missione. Generica (richiesto in chat, "molte più
    missioni") - funziona per QUALUNQUE missione registrata in
    GRAPH_MISSIONS, non più solo per Le Colonne. Restituisce
    (completata, testo del finale)."""
    if knight["mission_node"] != "fine":
        return False, ""
    mission_id = knight["mission_id"]
    mission_name = GRAPH_MISSIONS[mission_id]["name"]
    ending = resolve_graph_mission_ending(mission_id, _mission_flags_set(knight))
    knight["cosmo_max"] += COSMO_MAX_REWARD
    knight["cosmo_cur"] = knight["cosmo_max"]
    knight["denaro"] += DENARO_REWARD + ending["bonus"].get("denaro", 0)
    knight["renown"] += RENOWN_GRAPH_MISSION_COMPLETE
    knight["mission_id"] = ""
    knight["mission_node"] = ""
    knight["mission_flags"] = ""
    cal = get_calendar_display(knight["game_minutes"])
    add_biography_entry(
        conn, knight["id"], knight["game_minutes"],
        f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} completa "
        f"{mission_name}.",
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
    # L'allineamento vero del Guardiano (richiesto in chat, stile D&D)
    # sposta la soglia di persuasione - MAI mostrato al giocatore, solo
    # una frase di tono aggiunta al testo già scritto per la Casa.
    guardian_entry = get_roster_entry(conn, house_name)
    guardian_alignment = guardian_entry["npc_alignment"] if guardian_entry else ""
    success = resolve_persuasion(knight, guardian_alignment)
    mission_completed = False
    if success:
        knight["mission_stage"] += 1
        mission_completed = _complete_scalata_if_done(conn, knight)
        save_knight(conn, knight)
    base_text = content["persuade_success"] if success else content["persuade_failure"]
    flavor = persuasion_flavor_line(guardian_alignment, success) if guardian_alignment else ""
    full_text = f"{base_text} {flavor}".strip()
    return {
        "success": success,
        "text": full_text,
        "mission_completed": mission_completed,
    }


class MissionChoiceRequest(BaseModel):
    option_index: int


@app.post("/characters/{knight_id}/mission/choose")
def api_mission_choose(knight_id: int, req: MissionChoiceRequest, conn=Depends(get_db)):
    """Risolve una scelta di un nodo 'choice' di una missione a grafo
    (richiesto in chat: bivi che portano DAVVERO a strade diverse) -
    applica l'eventuale flag dell'opzione scelta (che può cambiare il
    finale più avanti) e passa al nodo successivo. Generica (richiesto
    in chat, "molte più missioni") - funziona per qualunque missione
    registrata in GRAPH_MISSIONS."""
    knight = _get_knight_or_404(conn, knight_id)
    _require_mission_ready(knight)
    if knight["mission_id"] not in GRAPH_MISSIONS:
        raise HTTPException(status_code=400, detail="Nessuna missione a bivi in corso.")
    mission_id = knight["mission_id"]
    node_id = knight["mission_node"] or GRAPH_MISSIONS[mission_id]["start_node"]
    node = GRAPH_MISSIONS[mission_id]["nodes"][node_id]
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
    return {"next_node": option["next"], "text": option.get("outcome_text", "")}


class MissionAttemptRequest(BaseModel):
    answer_index: int | None = None


@app.post("/characters/{knight_id}/mission/attempt")
def api_mission_attempt(knight_id: int, req: MissionAttemptRequest = MissionAttemptRequest(), conn=Depends(get_db)):
    """Un vero tiro di dado per un nodo 'skill_check' di una missione a
    grafo, o la risposta a un enigma vero per le Prove degli Inferi
    (richiesto in chat: "non un lanciadadi... mettiamo indovinelli" -
    non più un tiro pesato dalla statistica, una vera prova di logica
    che il giocatore deve risolvere) - nel primo caso porta a nodi
    SUCCESSIVI DIVERSI, nel secondo fa salire l'allerta sui fallimenti
    (fino a scatenare un'imboscata)."""
    knight = _get_knight_or_404(conn, knight_id)
    _require_mission_ready(knight)
    if knight["mission_id"] == INFERI_MISSION_ID:
        if knight["mission_counter"] >= INFERI_AMBUSH_THRESHOLD:
            raise HTTPException(status_code=400, detail="Sei stato scoperto - devi affrontare chi ti ha intercettato.")
        stage = get_inferi_stage(knight["mission_stage"])
        if stage is None:
            raise HTTPException(status_code=400, detail="Questa fase prevede uno scontro, non una prova.")
        if req.answer_index is None:
            raise HTTPException(status_code=400, detail="Manca la risposta all'enigma.")
        stored_stage, stored_puzzle_index = _parse_inferi_flags(knight["mission_flags"])
        if stored_stage != knight["mission_stage"] or stored_puzzle_index is None:
            raise HTTPException(status_code=400, detail="Nessun enigma assegnato - ricarica la missione e riprova.")
        _question, options, correct_index = INFERI_PUZZLES[knight["mission_stage"] - 1][stored_puzzle_index]
        success = check_inferi_answer(knight["mission_stage"], stored_puzzle_index, req.answer_index)
        knight["mission_flags"] = ""  # l'enigma è stato usato - il prossimo GET ne sceglie uno nuovo tra i 10
        if success:
            knight["mission_stage"] += 1
            knight["mission_counter"] = max(0, knight["mission_counter"] - 1)
        else:
            knight["mission_counter"] += 1
        save_knight(conn, knight)
        text = stage["text"] if success else f"Risposta sbagliata - quella giusta era: \"{options[correct_index]}\"."
        return {
            "success": success,
            "text": text,
            "alert": knight["mission_counter"],
            "ambush_triggered": knight["mission_counter"] >= INFERI_AMBUSH_THRESHOLD,
        }
    if knight["mission_id"] not in GRAPH_MISSIONS:
        raise HTTPException(status_code=400, detail="Nessuna missione a bivi in corso.")
    mission_id = knight["mission_id"]
    node_id = knight["mission_node"] or GRAPH_MISSIONS[mission_id]["start_node"]
    node = GRAPH_MISSIONS[mission_id]["nodes"][node_id]
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
    if knight["mission_id"] in GRAPH_MISSIONS:
        mission_id = knight["mission_id"]
        node_id = knight["mission_node"] or GRAPH_MISSIONS[mission_id]["start_node"]
        node = GRAPH_MISSIONS[mission_id]["nodes"][node_id]
        if node["type"] != "duel":
            raise HTTPException(status_code=400, detail="Questo nodo non prevede uno scontro.")
        duel_armor_name = pick_graph_duel_armor(mission_id, node_id)
        guardian_name = get_house_guardian(conn, duel_armor_name)
        opponent = build_opponent_from_armor(conn, duel_armor_name, guardian_name)
        battle_state = start_battle(conn, knight, armor, opponent=opponent)
        battle_state["is_mission"] = True
        return {"battle_state": battle_state, "intro": node["intro"].format(guardian=guardian_name)}
    if knight["mission_id"] in TOURNAMENT_MISSIONS:
        tournament_id = knight["mission_id"]
        round_number = knight["mission_stage"]
        settings = TOURNAMENT_MISSIONS[tournament_id]
        bracket = load_tournament_bracket(knight)
        if bracket is None:
            raise HTTPException(status_code=400, detail="Tabellone del torneo mancante - riprova ad iscriverti.")
        opponent = build_tournament_opponent(conn, bracket, round_number)
        battle_state = start_battle(conn, knight, armor, opponent=opponent)
        battle_state["is_mission"] = True
        round_label = tournament_round_label(tournament_id, round_number)
        intro = (f"{round_label.capitalize()} del {settings['name']} - "
                 f"{round_number}º di {settings['rounds']}: affronti {opponent['name']}.")
        return {"battle_state": battle_state, "intro": intro}
    if knight["mission_id"] == INFERI_MISSION_ID:
        stage = get_inferi_stage(knight["mission_stage"])
        if stage is None:
            # Oltre l'ultima prova: il duello finale contro uno dei Tre
            # Giudici degli Inferi.
            judge_armor_name = random.choice(JUDGE_ARMORS)
            guardian_name = get_house_guardian(conn, judge_armor_name)
            opponent = build_opponent_from_armor(conn, judge_armor_name, guardian_name)
            battle_state = start_battle(conn, knight, armor, opponent=opponent)
            battle_state["is_mission"] = True
            intro = (f"Hai attraversato tutte le prove degli Inferi. Nella Sala dei Tre Giudici, "
                      f"{opponent['name']} ti attende - l'ultima, vera barriera.")
            return {"battle_state": battle_state, "intro": intro}
        if knight["mission_counter"] < INFERI_AMBUSH_THRESHOLD:
            raise HTTPException(status_code=400, detail="Non sei ancora stato scoperto - tenta la prova, non lo scontro.")
        specter_armor_name = random.choice(SPECTER_AMBUSH_ARMORS)
        guardian_name = get_house_guardian(conn, specter_armor_name)
        opponent = build_opponent_from_armor(conn, specter_armor_name, guardian_name)
        battle_state = start_battle(conn, knight, armor, opponent=opponent)
        battle_state["is_mission"] = True
        intro = f"L'allerta è troppo alta - {opponent['name']} ti intercetta prima che tu possa proseguire."
        return {"battle_state": battle_state, "intro": intro}
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


@app.post("/characters/{knight_id}/training-path/trial/retry")
def api_trial_retry(knight_id: int, conn=Depends(get_db)):
    """Una delle alternative al fallimento della Prova Finale (richiesto
    in chat, compare ad OGNI fallimento): ritenta, come si faceva
    prima in automatico - ora è una scelta esplicita, non più imposta."""
    knight = _get_knight_or_404(conn, knight_id)
    if knight["is_knight"]:
        raise HTTPException(status_code=400, detail="Hai già completato l'addestramento.")
    knight["training_stage"] = RETRY_STAGE_ON_FAILURE
    save_knight(conn, knight)
    return {"training_stage": knight["training_stage"]}


@app.post("/characters/{knight_id}/training-path/trial/retrain")
def api_trial_retrain(knight_id: int, conn=Depends(get_db)):
    """Un'altra alternativa al fallimento (richiesto in chat):
    riaddestrarsi per un'armatura diversa, libera - rilascia quella
    vecchia, ne reclama una nuova, nuovo Maestro e nuovi compagni. I
    compagni di PRIMA non ottengono la Cloth abbandonata: il loro
    destino si decide adesso, insieme alla tua scelta."""
    knight = _get_knight_or_404(conn, knight_id)
    if knight["is_knight"]:
        raise HTTPException(status_code=400, detail="Hai già completato l'addestramento.")
    old_companion1, old_companion2 = knight["companion1_name"], knight["companion2_name"]
    old_armor_name = knight["armor_name"]
    fates = resolve_companions_fates(old_companion1, old_companion2)
    cal = get_calendar_display(knight["game_minutes"])
    add_biography_entry(
        conn, knight["id"], knight["game_minutes"],
        f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} rinuncia "
        f"all'armatura {old_armor_name} per riaddestrarsi altrove.",
    )
    for fate in fates:
        add_biography_entry(conn, knight["id"], knight["game_minutes"], fate)
    try:
        knight = retrain_for_new_armor(conn, knight)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    save_knight(conn, knight)
    return {"new_armor_name": knight["armor_name"], "companion_fates": fates}


@app.post("/characters/{knight_id}/training-path/trial/become-soldier")
def api_trial_become_soldier(knight_id: int, conn=Depends(get_db)):
    """Un'altra alternativa al fallimento (richiesto in chat): diventare
    Soldato Semplice - uno stato di gioco vero, con attività dedicate
    proprie (vedi .../soldier/*), non solo narrativo. Rilascia
    l'armatura; i compagni non la ottengono nemmeno loro, il loro
    destino si decide adesso."""
    knight = _get_knight_or_404(conn, knight_id)
    if knight["is_knight"]:
        raise HTTPException(status_code=400, detail="Hai già completato l'addestramento.")
    fates = resolve_companions_fates(knight["companion1_name"], knight["companion2_name"])
    cal = get_calendar_display(knight["game_minutes"])
    add_biography_entry(
        conn, knight["id"], knight["game_minutes"],
        f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} rinuncia "
        f"all'armatura {knight['armor_name']} e diventa Soldato Semplice.",
    )
    for fate in fates:
        add_biography_entry(conn, knight["id"], knight["game_minutes"], fate)
    release_roster_slot(conn, knight["armor_name"])
    knight["apprentice_status"] = "soldier"
    save_knight(conn, knight)
    return {"companion_fates": fates}


@app.post("/characters/{knight_id}/training-path/trial/die")
def api_trial_die(knight_id: int, conn=Depends(get_db)):
    """L'ultima alternativa al fallimento (richiesto in chat): la morte
    definitiva del personaggio - permadeath vero, non uno stato. I
    compagni non ottengono la Cloth nemmeno in questo caso; il loro
    destino, restituito qui PRIMA della cancellazione (dopo non ci
    sarebbe più nessun personaggio a cui associarlo), resta come
    ultimo ricordo per il giocatore."""
    knight = _get_knight_or_404(conn, knight_id)
    if knight["is_knight"]:
        raise HTTPException(status_code=400, detail="Hai già completato l'addestramento.")
    fates = resolve_companions_fates(knight["companion1_name"], knight["companion2_name"])
    raw_name = knight["raw_name"]
    armor_name = knight["armor_name"]
    delete_knight(conn, knight_id)
    return {"raw_name": raw_name, "armor_name": armor_name, "companion_fates": fates}


SOLDIER_ACTIVITY_MINUTES = 480  # un turno di servizio, PLACEHOLDER come le altre durate del gioco


@app.get("/characters/{knight_id}/soldier")
def api_get_soldier_status(knight_id: int, conn=Depends(get_db)):
    """Lo stato da Soldato Semplice (richiesto in chat: un vero
    mini-percorso, non solo uno stato passivo) - l'elenco delle
    attività disponibili, per chi ha scelto questa strada dopo un
    fallimento della Prova Finale."""
    knight = _get_knight_or_404(conn, knight_id)
    if knight["apprentice_status"] != "soldier":
        raise HTTPException(status_code=403, detail="Non sei un Soldato Semplice.")
    activities = [{"key": k, "label": v["label"]} for k, v in SOLDIER_ACTIVITIES.items()]
    return {"activities": activities, "denaro": knight["denaro"]}


class SoldierActivityRequest(BaseModel):
    activity_key: str


@app.post("/characters/{knight_id}/soldier/activity")
def api_do_soldier_activity(knight_id: int, req: SoldierActivityRequest, conn=Depends(get_db)):
    """Risolve un'attività da Soldato Semplice (richiesto in chat) - un
    po' di tempo di gioco, un po' di denaro, un po' di narrazione
    diversa ogni volta."""
    knight = _get_knight_or_404(conn, knight_id)
    if knight["apprentice_status"] != "soldier":
        raise HTTPException(status_code=403, detail="Non sei un Soldato Semplice.")
    if req.activity_key not in SOLDIER_ACTIVITIES:
        raise HTTPException(status_code=400, detail="Attività sconosciuta.")
    text, denaro = resolve_soldier_activity(req.activity_key)
    knight["denaro"] += denaro
    aging_msg = RosterManager.spend_time(conn, knight, SOLDIER_ACTIVITY_MINUTES)
    save_knight(conn, knight)
    return {"text": text, "denaro_earned": denaro, "denaro_total": knight["denaro"], "aging_message": aging_msg}


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


@app.get("/characters/{knight_id}/taverns")
def api_get_taverns(knight_id: int, conn=Depends(get_db)):
    """L'elenco delle 13 Taverne, una per regno/fazione (richiesto in
    chat: separate, non un'unica Taverna con tutti) - con la relazione
    tra la TUA fazione e quella di ciascun regno, così sai già, prima
    di entrare, se ti aspetta un'accoglienza fredda."""
    knight = _get_knight_or_404(conn, knight_id)
    armor = get_armor(knight["armor_name"], conn)
    player_divinity = armor["divinity"] if armor else ""
    result = []
    for divinity, name in TAVERN_REALMS.items():
        result.append({
            "divinity": divinity,
            "name": name,
            "relation": get_faction_relation(player_divinity, divinity),
        })
    return result


@app.get("/characters/{knight_id}/tavern-map/{divinity}")
def api_get_tavern_map(knight_id: int, divinity: str, conn=Depends(get_db)):
    """La mappa vera della Taverna di un regno (richiesto in chat: non
    più un semplice elenco da cui scegliere, una stanza con un bancone
    e dei tavoli) - chi c'è al bancone (il taverniere, fisso) e chi
    siede a ciascun tavolo in QUESTO momento (dinamico: la disposizione
    può essere appena cambiata, controllato ad ogni chiamata - vedi
    core.tavern.maybe_reshuffle_tavern)."""
    knight = _get_knight_or_404(conn, knight_id)
    if divinity not in TAVERN_REALMS:
        raise HTTPException(status_code=404, detail="Regno sconosciuto.")
    world_minutes = get_world_minutes(conn)
    bartender = ensure_tavern_bartender(conn, divinity)
    ensure_tavern_seating(conn, divinity, world_minutes)
    maybe_reshuffle_tavern(conn, divinity, world_minutes)
    seating_rows = get_tavern_seating(conn, divinity)
    npc_names = {}
    if seating_rows:
        placeholders = ",".join("?" for _ in seating_rows)
        armor_names = [row["armor_name"] for row in seating_rows]
        for r in conn.execute(f"SELECT armor_name, npc_name FROM roster WHERE armor_name IN ({placeholders})", armor_names):
            npc_names[r["armor_name"]] = r["npc_name"]
    tables = []
    for table_number, info in TABLE_LAYOUT.items():
        if table_number == 0:
            continue
        occupants = [
            {"seat_index": row["seat_index"], "armor_name": row["armor_name"], "npc_name": npc_names.get(row["armor_name"], "???")}
            for row in seating_rows if row["table_number"] == table_number
        ]
        tables.append({"table_number": table_number, "label": info["label"], "seats": info["seats"], "occupants": occupants})
    player_armor = get_armor(knight["armor_name"], conn)
    relation = get_faction_relation(player_armor["divinity"] if player_armor else "", divinity)
    return {
        "divinity": divinity,
        "name": TAVERN_REALMS[divinity],
        "relation": relation,
        "bartender": {"name": bartender["name"], "armor_name": f"{BARTENDER_KEY_PREFIX}{divinity}"},
        "tables": tables,
    }


BARTENDER_KEY_PREFIX = "__bartender__"


def _resolve_tavern_npc_info(conn, armor_name: str) -> tuple[str, str, str] | None:
    """Restituisce (nome, allineamento, divinità) sia per un vero PNG
    del roster sia per il taverniere (richiesto in chat: anche lui si
    può interpellare, non solo chi siede ai tavoli) - il taverniere
    usa una chiave speciale (__bartender__{divinity}) al posto di un
    vero nome di armatura, per riusare la stessa infrastruttura di
    conversazione invece di duplicarla."""
    if armor_name.startswith(BARTENDER_KEY_PREFIX):
        divinity = armor_name[len(BARTENDER_KEY_PREFIX):]
        bartender = get_tavern_bartender(conn, divinity)
        if bartender is None:
            return None
        return bartender["name"], bartender["alignment"], divinity
    roster_entry = get_roster_entry(conn, armor_name)
    if roster_entry is None:
        return None
    npc_armor = get_armor(armor_name, conn)
    return roster_entry["npc_name"], roster_entry["npc_alignment"], (npc_armor["divinity"] if npc_armor else "")


@app.get("/characters/{knight_id}/tavern")
def api_get_tavern_conversation(knight_id: int, armor_name: str, conn=Depends(get_db)):
    """La conversazione con un PNG specifico nella Taverna (richiesto
    in chat) - la cronologia già scambiata, e l'affinità accumulata
    finora. Testo libero, nessuna vera IA dietro (richiesto in chat,
    costo zero) - solo un riconoscimento a parole chiave, vedi
    core.tavern. Se è la prima volta che parlate, l'affinità parte già
    dal punto giusto in base alla relazione tra le vostre fazioni
    (richiesto in chat: "sicuramente inizialmente c'è diffidenza") -
    non da zero per tutti indistintamente. `armor_name` come parametro
    di query, non nel percorso (bug corretto in chat: molti nomi di
    armature contengono "/", es. "Ursa Minor / Orsa Minore" - anche
    codificato, uno slash nel PERCORSO di un URL può rompere il
    routing prima ancora che arrivi a FastAPI)."""
    knight = _get_knight_or_404(conn, knight_id)
    npc_info = _resolve_tavern_npc_info(conn, armor_name)
    if npc_info is None:
        raise HTTPException(status_code=404, detail="PNG sconosciuto.")
    npc_name, _npc_alignment, npc_divinity = npc_info
    relationship = get_tavern_relationship(conn, knight_id, armor_name)
    if relationship is None:
        player_armor = get_armor(knight["armor_name"], conn)
        relation = get_faction_relation(player_armor["divinity"] if player_armor else "", npc_divinity)
        starting_affinity = RELATION_STARTING_AFFINITY.get(relation, 0)
        affinity = adjust_tavern_affinity(conn, knight_id, armor_name, starting_affinity, get_world_minutes(conn))
    else:
        affinity = relationship["affinity"]
    messages = get_tavern_conversation(conn, knight_id, armor_name)
    return {
        "npc_name": npc_name,
        "affinity": affinity,
        "messages": [{"speaker": m["speaker"], "text": m["text"]} for m in messages],
        # I vecchi pulsanti "argomento" che inserivano una frase fissa
        # sono stati rimossi (richiesto in chat: "vorrei lasciare
        # scrivere al pg la frase") - il testo libero ora passa dal
        # classificatore di intenti (core.intent_classifier), niente
        # più bisogno di garantire la comprensione con una scorciatoia.
        "tones": [{"tone": t, "label": label} for t, label, _mult in TAVERN_TONES],
    }


class TavernMessageRequest(BaseModel):
    armor_name: str
    text: str
    intent: str | None = None
    tone: str = "neutro"


@app.post("/characters/{knight_id}/tavern/message")
def api_send_tavern_message(knight_id: int, req: TavernMessageRequest, conn=Depends(get_db)):
    """Invia un messaggio a un PNG nella Taverna (richiesto in chat) -
    testo libero, risposta a parole chiave filtrata per il vero
    allineamento del PNG (mai mostrato) e per la relazione tra le
    vostre fazioni (fiducia lenta da guadagnare, facile da perdere con
    un rivale) - se non riconosce nessuna parola chiave, chiede di
    ripetere in stile Saint Seiya invece di un freddo errore. Se
    l'affinità supera la soglia di fiducia proprio con questo
    messaggio, il PNG può offrire da solo la missione del proprio
    regno (richiesto in chat). `armor_name` nel corpo della richiesta,
    non nel percorso (stesso bug corretto sopra)."""
    knight = _get_knight_or_404(conn, knight_id)
    armor_name = req.armor_name
    npc_info = _resolve_tavern_npc_info(conn, armor_name)
    if npc_info is None:
        raise HTTPException(status_code=404, detail="PNG sconosciuto.")
    _npc_name, npc_alignment, npc_divinity = npc_info
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Il messaggio non può essere vuoto.")
    player_armor = get_armor(knight["armor_name"], conn)
    relation = get_faction_relation(player_armor["divinity"] if player_armor else "", npc_divinity)
    relationship_before = get_tavern_relationship(conn, knight_id, armor_name)
    affinity_before = relationship_before["affinity"] if relationship_before else RELATION_STARTING_AFFINITY.get(relation, 0)
    response_text, affinity_delta = resolve_tavern_response(req.text, npc_alignment, relation, forced_intent=req.intent, tone=req.tone)
    world_minutes = get_world_minutes(conn)
    add_tavern_message(conn, knight_id, armor_name, world_minutes, "player", req.text.strip())
    add_tavern_message(conn, knight_id, armor_name, world_minutes, "npc", response_text)
    new_affinity = adjust_tavern_affinity(conn, knight_id, armor_name, affinity_delta, world_minutes)
    mission_offer = check_mission_offer(
        npc_divinity, affinity_before, new_affinity, bool(knight["mission_id"])
    )
    if mission_offer:
        offer_text = random.choice(MISSION_OFFER_TEXTS)
        add_tavern_message(conn, knight_id, armor_name, world_minutes, "npc", offer_text)
    return {
        "response": response_text, "affinity": new_affinity, "affinity_delta": affinity_delta,
        "mission_offer": mission_offer, "mission_offer_text": offer_text if mission_offer else None,
    }


@app.get("/roster")
def api_get_roster(conn=Depends(get_db)):
    """La Gerarchia completa (richiesta in chat): tutte le 224 armature
    con chi le occupa - il PNG fisso se libere, il personaggio
    giocatore se reclamate. Ordinata per divinità/fazione/livello."""
    return [dict(r) for r in get_roster(conn)]


@app.get("/world-chronicle")
def api_get_world_chronicle(conn=Depends(get_db)):
    """La Cronaca del Mondo (richiesto in chat): gli eventi accaduti ai
    PNG nel tempo condiviso - morti, ritiri, sparizioni, sostituzioni -
    condivisa da tutti i personaggi, non legata a nessuno in
    particolare. Include anche la data di gioco leggibile di ciascuna
    voce, calcolata qui invece che nel frontend."""
    righe = get_world_chronicle(conn)
    risultato = []
    for r in righe:
        cal = get_calendar_display(r["world_minutes"])
        risultato.append({
            "armor_name": r["armor_name"],
            "entry": r["entry"],
            "date_label": f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}",
        })
    return risultato


@app.get("/institutional-npcs")
def api_get_institutional_npcs():
    """Le figure istituzionali del mondo di gioco (richiesto in chat):
    non giocabili, statiche, un minimo di ambientazione/gdr - Il
    Grande Sacerdote, Pandora, ecc. Nessun accesso al DB, sono dati
    fissi del gioco, non legati a nessun personaggio."""
    return get_institutional_npcs()


@app.get("/divinity-npcs")
def api_get_divinity_npcs():
    """Le Divinità del mondo di gioco (richiesto in chat: "differenzia
    le divinità dalle armature" - il vertice vero di ogni fazione, non
    giocabile per ora). Nessun accesso al DB per il testo, sono dati
    fissi come le Figure Istituzionali - il vero allineamento persistito
    non viene mai restituito qui, resta sempre nascosto."""
    return get_divinity_npcs()


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
        results = RosterManager.advance_week(conn, knight, schedule)
    else:
        results = RosterManager.advance_month(conn, knight, schedule)
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
        cal = get_calendar_display(knight["game_minutes"])
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
        conn, knight, armor, req.action, req.technique_name, req.technique_power, req.battle_state,
        technique_type=req.technique_type,
        technique_launch_desc=req.technique_launch_desc, technique_effect_desc=req.technique_effect_desc,
    )
    if fight_over:
        extra = _handle_fight_conclusion(conn, knight, req.battle_state, winner)
        return {
            "log": log, "fight_over": True, "won": winner == "player",
            "character": _knight_payload(conn, knight), "battle_state": None,
            **extra,
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
    # La difesa è ora una vera scelta del giocatore (richiesto in chat:
    # "Difesa Base + tecniche di difesa", stessa struttura
    # dell'attacco) - non più decisa in automatico dal sistema.
    # Nessuna scelta esplicita = Difesa Base generica.
    if req.defense_technique_name and req.defense_technique_name != "Difesa Base":
        my_defense = {
            "name": req.defense_technique_name,
            "power": req.defense_technique_power or DEFAULT_DEFENSE_POWER,
            "tech_type": req.defense_technique_type or "",
            "launch_desc": req.defense_technique_launch_desc or "",
            "effect_desc": req.defense_technique_effect_desc or "",
        }
    else:
        my_defense = None
    log, fight_over, winner = resolve_react(
        conn, knight, armor, req.action, my_defense, req.battle_state,
        counter_technique_name=req.counter_technique_name, counter_technique_power=req.counter_technique_power,
        counter_technique_type=req.counter_technique_type, counter_technique_launch_desc=req.counter_technique_launch_desc,
        counter_technique_effect_desc=req.counter_technique_effect_desc,
    )
    if fight_over:
        extra = _handle_fight_conclusion(conn, knight, req.battle_state, winner)
        return {
            "log": log, "fight_over": True, "won": winner == "player",
            "character": _knight_payload(conn, knight), "battle_state": None,
            **extra,
        }
    save_knight(conn, knight)
    return {
        "log": log, "fight_over": False,
        "character": _knight_payload(conn, knight), "battle_state": req.battle_state,
    }


@app.get("/characters/{knight_id}/scouted-allies")
def api_get_scouted_allies(knight_id: int, conn=Depends(get_db)):
    """L'Osservatore dello staff (richiesto in chat, dalla roadmap:
    "un Osservatore che segnala PNG con affinità già alta prima
    ancora di parlarci") - sblocca solo con Renown sufficiente
    (has_staff_osservatore); PNG con un'affinità già promettente in
    Taverna, così il giocatore sa dove tornare a parlare senza doverlo
    scoprire per caso."""
    knight = _get_knight_or_404(conn, knight_id)
    if not has_staff_osservatore(knight["renown"]):
        return {"unlocked": False, "allies": []}
    rows = conn.execute(
        """SELECT tr.armor_name, tr.affinity, r.npc_name, a.divinity, a.faction
           FROM tavern_relationships tr
           JOIN roster r ON r.armor_name = tr.armor_name
           JOIN armors a ON a.name = tr.armor_name
           WHERE tr.knight_id = ? AND tr.affinity >= ?
           AND tr.armor_name NOT LIKE '\\_\\_bartender\\_\\_%' ESCAPE '\\'
           ORDER BY tr.affinity DESC""",
        (knight_id, STAFF_OSSERVATORE_AFFINITY_THRESHOLD),
    ).fetchall()
    return {"unlocked": True, "allies": [dict(r) for r in rows]}


class MeditationCompleteRequest(BaseModel):
    success: bool
    sequence_length: int


@app.get("/characters/{knight_id}/meditation")
def api_get_meditation_status(knight_id: int, conn=Depends(get_db)):
    """Lo stato della Meditazione del Cosmo (richiesto in chat, dalla
    roadmap: mini-gioco ricorrente di taglio diverso dagli enigmi di
    logica degli Inferi - qui un esercizio di memoria) - se è
    disponibile ora, quanto manca se non lo è, e quanto sarà lunga la
    prossima sequenza."""
    knight = _get_knight_or_404(conn, knight_id)
    available = can_meditate(knight["last_meditation_minutes"], knight["game_minutes"])
    return {
        "available": available,
        "minutes_until_next": 0 if available else minutes_until_next_meditation(
            knight["last_meditation_minutes"], knight["game_minutes"]
        ),
        "sequence_length": next_sequence_length(knight["meditation_successes"]),
    }


@app.post("/characters/{knight_id}/meditation/start")
def api_start_meditation(knight_id: int, conn=Depends(get_db)):
    """Genera la sequenza vera (richiesto in chat: generata lato
    server, il client la mostra e basta) - non applica ancora nessun
    costo in tempo né tocca il cooldown, quello avviene solo alla
    conclusione del tentativo (persino un tentativo abbandonato a
    metà non deve consumare il rituale di oggi per errore)."""
    knight = _get_knight_or_404(conn, knight_id)
    if not can_meditate(knight["last_meditation_minutes"], knight["game_minutes"]):
        raise HTTPException(status_code=400, detail="Non è ancora ora di meditare di nuovo.")
    length = next_sequence_length(knight["meditation_successes"])
    return {"sequence": generate_sequence(length)}


@app.post("/characters/{knight_id}/meditation/complete")
def api_complete_meditation(knight_id: int, req: MeditationCompleteRequest, conn=Depends(get_db)):
    """Applica l'esito del tentativo (richiesto in chat) - il tempo
    passa e il cooldown scatta SEMPRE, vinca o perda il tentativo (una
    sessione di concentrazione costa comunque tempo, anche se fallita
    a metà) - solo la ricompensa in Volontà e il contatore dei
    successi dipendono dall'aver completato la sequenza per davvero."""
    knight = _get_knight_or_404(conn, knight_id)
    reward = resolve_meditation_reward(req.sequence_length) if req.success else {"volonta": 0}
    if req.success:
        knight["vol"] += reward["volonta"]
        knight["meditation_successes"] += 1
    RosterManager.spend_time(conn, knight, MEDITATION_TIME_MINUTES)
    knight["last_meditation_minutes"] = knight["game_minutes"]
    save_knight(conn, knight)
    return {"character": _knight_payload(conn, knight), "reward": reward}


@app.get("/characters/{knight_id}/defense-team-options")
def api_defense_team_options(knight_id: int, conn=Depends(get_db)):
    """I possibili alleati per "Seleziona Team" nella Difesa a Ondate
    (richiesto in chat) - i compagni della tua fazione, più chiunque
    abbia un legame davvero forte con te in Taverna."""
    knight = _get_knight_or_404(conn, knight_id)
    armor = get_armor(knight["armor_name"], conn)
    return {"candidates": get_defense_team_candidates(conn, knight, armor)}


@app.post("/characters/{knight_id}/defense/start")
def api_defense_start(knight_id: int, req: DefenseStartRequest, conn=Depends(get_db)):
    """Avvia una Difesa a Ondate (richiesto in chat: 3 contro 3,
    ambientazione e fazione nemica casuali, squadra a scelta o
    casuale). Lo stato della battaglia, come per l'Arena, va e viene
    col client ad ogni azione - non è persistito sul personaggio."""
    knight = _get_knight_or_404(conn, knight_id)
    _require_mission_ready(knight)
    if knight["mission_id"]:
        raise HTTPException(status_code=400, detail="Hai già una missione in corso.")
    armor = get_armor(knight["armor_name"], conn)
    chosen = None
    if req.mode == "selected":
        if len(req.ally_armor_names) != UNITS_PER_SIDE - 1:
            raise HTTPException(status_code=400, detail=f"Servono esattamente {UNITS_PER_SIDE - 1} alleati.")
        candidates = {c["armor_name"] for c in get_defense_team_candidates(conn, knight, armor)}
        for name in req.ally_armor_names:
            if name not in candidates:
                raise HTTPException(status_code=400, detail=f"{name} non è un alleato disponibile.")
        chosen = req.ally_armor_names
    state = start_defense_mission(conn, knight, armor, chosen_ally_armor_names=chosen)
    return {"battle_state": state}


@app.post("/characters/{knight_id}/defense/action")
def api_defense_action(knight_id: int, req: DefenseActionRequest, conn=Depends(get_db)):
    """Un'azione nella Difesa a Ondate (richiesto in chat: iniziativa
    stile D&D, ordini semplici agli alleati) - `actor_id` è chi agisce
    in questo momento (tu, o un alleato a cui stai dando un ordine),
    deve corrispondere a chi tocca davvero nell'ordine di iniziativa.
    Dopo l'azione, i turni nemici (e quelli degli alleati non ancora
    ordinati) proseguono da soli finché non torna un turno che
    richiede una decisione."""
    knight = _get_knight_or_404(conn, knight_id)
    state = req.battle_state
    if state.get("outcome") is not None:
        raise HTTPException(status_code=400, detail="La battaglia è già conclusa.")
    actor = state["units"].get(req.actor_id)
    if actor is None or not actor["is_alive"] or actor["side"] != "allies":
        raise HTTPException(status_code=400, detail="Unità non valida, già caduta, o non è un tuo alleato.")
    current = _current_actor(state)
    if current is None or current["id"] != req.actor_id:
        raise HTTPException(status_code=400, detail="Non è il turno di questa unità.")
    resolve_squad_action(
        conn, state, req.actor_id, req.action, target_id=req.target_id,
        technique_name=req.technique_name, technique_power=req.technique_power,
        technique_type=req.technique_type, target_mode=req.target_mode,
    )
    _skip_dead_and_autoresolve_enemies(conn, state)
    result = {"battle_state": state}
    if state["outcome"] is not None:
        # Le tre barre vere anche per i PNG (richiesto in chat) -
        # persiste quanta Vita/Cosmo restano a OGNI unità del roster
        # coinvolta (alleati veri e nemici, MAI il giocatore stesso -
        # le sue statistiche vivono sul personaggio, non sul roster).
        for unit in state["units"].values():
            if unit["id"] != "player" and unit.get("is_roster_linked"):
                apply_npc_damage(conn, unit["armor_name"], unit["vita_cur"], unit["cosmo_cur"], knight["game_minutes"])
        waves_completed = state["total_waves"] if state["outcome"] == "victory" else state["wave_number"] - 1
        reward = resolve_defense_reward(waves_completed, state["outcome"] == "victory")
        knight["denaro"] += reward["denaro"]
        knight["renown"] += RENOWN_DEFENSE_PER_WAVE * waves_completed + (RENOWN_DEFENSE_VICTORY_BONUS if state["outcome"] == "victory" else 0)
        if reward["cosmo_max"]:
            knight["cosmo_max"] += reward["cosmo_max"]
            knight["cosmo_cur"] = knight["cosmo_max"]
        save_knight(conn, knight)
        cal = get_calendar_display(knight["game_minutes"])
        if state["outcome"] == "victory":
            add_biography_entry(
                conn, knight["id"], knight["game_minutes"],
                f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} difende "
                f"{state['setting']} da {state['enemy_faction']}, respingendo tutte le ondate.",
            )
        else:
            add_biography_entry(
                conn, knight["id"], knight["game_minutes"],
                f"{cal['day_of_month']} {cal['month_name']}, Anno {cal['year']}: {knight['raw_name']} viene "
                f"sopraffatto difendendo {state['setting']}, dopo aver respinto {waves_completed} ondate.",
            )
        result["reward"] = reward
        result["character"] = _knight_payload(conn, knight)
    return result


@app.post("/characters/{knight_id}/defense/abandon")
def api_defense_abandon(knight_id: int, req: DefenseAbandonRequest, conn=Depends(get_db)):
    """Il pulsante di resa nella Difesa a Ondate (richiesto in chat:
    "manca il pulsante per arrendersi" - dopo aver corretto il
    combattimento perché il giocatore controlli solo il proprio
    personaggio, gli alleati agiscono da soli e la battaglia può
    protrarsi anche quando si vorrebbe smettere). Stesso principio
    già seguito per le altre missioni (POST /mission/abandon): chi
    abbandona di sua volontà non porta a casa nessuna ricompensa,
    nemmeno parziale per le ondate già respinte."""
    _get_knight_or_404(conn, knight_id)
    state = req.battle_state
    abandon_defense_mission(state)
    return {"battle_state": state}


@app.post("/characters/{knight_id}/arena/retreat")
def api_arena_retreat(knight_id: int, conn=Depends(get_db)):
    knight = _get_knight_or_404(conn, knight_id)
    finalize_fight(knight)
    save_knight(conn, knight)
    return {"character": _knight_payload(conn, knight)}
