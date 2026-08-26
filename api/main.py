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
    get_armor, get_techniques_for_armor, list_armors_for_player_level,
)
from core.character_factory import (
    create_knight, get_knight, list_knights, delete_knight, save_knight,
    ArmorNotFoundError, ArmorLevelTooHighError,
)
from core.fm_manager import (
    RosterManager, get_calendar_display, parse_weekly_schedule,
    serialize_weekly_schedule, TRAINING_FOCUS_OPTIONS,
)
from core.arena_manager import find_defensive_technique, get_unlocked_senses
from api.arena_session import start_battle, resolve_declare, resolve_react, finalize_fight

app = FastAPI(title="Saint Seiya: Sacro Imperio API")

# Sviluppo: aperto a tutte le origini. Quando ci sarà un frontend vero
# con un suo indirizzo fisso, restringiamo a quello soltanto.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _init_schema_once() -> None:
    """Crea le tabelle e carica il catalogo armature dai CSV - va fatto
    UNA SOLA VOLTA all'avvio del processo, non ad ogni richiesta
    (il refresh del catalogo fa oltre 200 upsert, sarebbe uno spreco
    farlo per ogni singola chiamata API)."""
    conn = get_connection()
    init_db(conn)
    refresh_armors_catalog(conn)
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


class TrainRequest(BaseModel):
    mode: Literal["settimana", "mese"]
    schedule: list[str]  # fino a 7 focus, uno per giorno della griglia


class ArenaDeclareRequest(BaseModel):
    action: Literal["attacca", "carica"]
    technique_name: Optional[str] = None
    technique_power: Optional[int] = None
    battle_state: dict


class ArenaReactRequest(BaseModel):
    defend: bool
    battle_state: dict


# --------------------------- Serializzazione ---------------------------

def _knight_payload(conn, knight: dict) -> dict:
    """Impacchetta un knight con tutto il contesto che il frontend
    normalmente dovrebbe richiedere separatamente (armatura, tecniche,
    calendario, sensi) - una sola chiamata invece di quattro."""
    armor = get_armor(knight["armor_name"], conn)
    techniques = [dict(t) for t in get_techniques_for_armor(knight["armor_name"], conn)]
    calendar = get_calendar_display(knight["game_minutes"])
    senses = get_unlocked_senses(knight["player_level"])
    return {
        **knight,
        "armor": dict(armor) if armor else None,
        "techniques": techniques,
        "calendar": calendar,
        "senses": senses,
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
    return {"status": "ok", "app": "Saint Seiya: Sacro Imperio"}


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
        knight = create_knight(conn, req.raw_name, req.armor_name, req.player_level)
    except (ArmorNotFoundError, ArmorLevelTooHighError) as e:
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


@app.get("/armors/{armor_name}/techniques")
def api_armor_techniques(armor_name: str, conn=Depends(get_db)):
    return [dict(t) for t in get_techniques_for_armor(armor_name, conn)]


# --------------------------- Allenamento ---------------------------

@app.post("/characters/{knight_id}/train")
def api_train(knight_id: int, req: TrainRequest, conn=Depends(get_db)):
    knight = _get_knight_or_404(conn, knight_id)

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

    return {
        "log": [{"day": d, "focus": f, "message": m} for d, f, m in results],
        "character": _knight_payload(conn, knight),
    }


# --------------------------- Arena ---------------------------

@app.post("/characters/{knight_id}/arena/opponent")
def api_arena_new_opponent(knight_id: int, difficulty: str = "medio", conn=Depends(get_db)):
    """Genera un nuovo avversario. difficulty: 'facile' | 'medio' |
    'difficile' - sposta il livello dell'avversario cercato rispetto al
    tuo. Il battle_state restituito va conservato dal chiamante (es.
    nello stato della pagina web) e rimandato indietro ad ogni chiamata
    successiva - il server non lo ricorda tra una richiesta e l'altra."""
    knight = _get_knight_or_404(conn, knight_id)
    armor = get_armor(knight["armor_name"], conn)

    battle_state = start_battle(conn, knight, armor, difficulty=difficulty)
    return {"battle_state": battle_state}


@app.post("/characters/{knight_id}/arena/declare")
def api_arena_declare(knight_id: int, req: ArenaDeclareRequest, conn=Depends(get_db)):
    """Metà 1 del round: dichiari Attacca o Carica."""
    knight = _get_knight_or_404(conn, knight_id)
    armor = get_armor(knight["armor_name"], conn)

    if req.action == "attacca" and (not req.technique_name or req.technique_power is None):
        raise HTTPException(status_code=400, detail="Serve una tecnica (nome e potenza) per attaccare")

    log, fight_over, winner = resolve_declare(
        knight, armor, req.action, req.technique_name, req.technique_power, req.battle_state
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
