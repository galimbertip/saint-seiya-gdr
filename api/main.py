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

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from database.db_manager import (
    get_connection, init_db, refresh_armors_catalog,
    get_armor, get_techniques_for_armor, list_armors_for_player_level, get_roster,
)
from core.character_factory import (
    create_knight, get_knight, list_knights, delete_knight, save_knight,
    ArmorNotFoundError, ArmorLevelTooHighError, ArmorAlreadyClaimedError, ensure_roster_populated,
)
from core.fm_manager import (
    RosterManager, get_calendar_display, parse_weekly_schedule,
    serialize_weekly_schedule, TRAINING_FOCUS_OPTIONS,
)
from core.arena_manager import find_defensive_technique, get_unlocked_senses, calculate_movement_points
from core.version import APP_VERSION
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
    battle_state: dict


class ArenaReactRequest(BaseModel):
    defend: bool
    battle_state: dict


# --------------------------- Serializzazione ---------------------------

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
    return _FRONTEND_PATH.read_text(encoding="utf-8")


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
            build=req.build or "Media",
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


# --------------------------- Catalogo armature ---------------------------

@app.get("/armors")
def api_list_armors(player_level: int = 1, conn=Depends(get_db)):
    return [dict(a) for a in list_armors_for_player_level(player_level, conn)]


@app.get("/roster")
def api_get_roster(conn=Depends(get_db)):
    """La Gerarchia completa (richiesta in chat): tutte le 224 armature
    con chi le occupa - il PNG fisso se libere, il personaggio
    giocatore se reclamate. Ordinata per divinità/fazione/livello."""
    return [dict(r) for r in get_roster(conn)]


@app.get("/armors/{armor_name}/techniques")
def api_armor_techniques(armor_name: str, conn=Depends(get_db)):
    return [dict(t) for t in get_techniques_for_armor(armor_name, conn)]


# --------------------------- Allenamento ---------------------------

@app.post("/characters/{knight_id}/train")
def api_train(knight_id: int, req: TrainRequest, conn=Depends(get_db)):
    knight = _get_knight_or_404(conn, knight_id)
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
    )

    if fight_over:
        finalize_fight(knight)
        save_knight(conn, knight)
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
    """Metà 2 del round: reagisci (Difenditi o Incassa) a un attacco
    già dichiarato dall'avversario (visto in anticipo)."""
    knight = _get_knight_or_404(conn, knight_id)
    armor = get_armor(knight["armor_name"], conn)

    if req.battle_state.get("pending_opponent_technique") is None:
        raise HTTPException(status_code=400, detail="Nessun attacco in sospeso a cui reagire")

    my_techniques = [dict(t) for t in get_techniques_for_armor(knight["armor_name"], conn)]
    my_defense = find_defensive_technique(my_techniques)

    log, fight_over, winner = resolve_react(knight, armor, req.defend, my_defense, req.battle_state)

    if fight_over:
        finalize_fight(knight)
        save_knight(conn, knight)
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
