"""Il combattimento multi-unità (richiesto in chat: "difesa a ondate a
squadre" - 3 contro 3, iniziativa in stile D&D, ordini semplici agli
alleati, squadra fissa che non si rigenera tra un'ondata e l'altra -
chi cade resta caduto). Riusa le funzioni di calcolo del danno già
esistenti (resolve_turn, resolve_defense) - qui si orchestrano solo
TURNI e BERSAGLI in più, non si reinventa la matematica del
combattimento.

Per questa prima versione, deliberatamente: nessun terreno, nessuna
posizione/mappa, nessuno stato (veleno/paralisi), nessun Imprevisto -
il nucleo del loop multi-unità prima, gli arricchimenti già presenti
nell'Arena 1v1 dopo, se servirà. Lo stato del combattimento (squad
state) è un dizionario transitorio, va e viene col client ad ogni
azione - stesso principio del battle_state dell'Arena, solo con più
unità dentro."""

import random

from core.arena_manager import (
    resolve_turn, resolve_defense, technique_cosmo_cost, BASE_ATTACK_POWER,
    CHARGE_TURNS_DURATION, CHARGE_COSMO_RESTORE, CHARGE_POWER_BONUS,
)
from core.dnd_engine import DnDEngine
from core.training_path import build_opponent_from_armor
from database.db_manager import get_armor, get_roster_entry

DEFENSE_MISSION_ID = "difesa_a_ondate"
UNITS_PER_SIDE = 3
TOTAL_WAVES = 4

DEFENSE_REWARD_DENARO_PER_WAVE = 150
DEFENSE_REWARD_DENARO_CHAMPION = 1000
DEFENSE_REWARD_COSMO_MAX_CHAMPION = 40

# La soglia di affinità per un "legame particolarmente buono" con un
# PNG (richiesto in chat: "buoni buoni buoni, sennò è una farsa") -
# volutamente più alta della soglia di reclutamento missioni della
# Taverna (10) - qui non basta essere in buoni rapporti, serve una
# fiducia vera prima che qualcuno rischi la vita al tuo fianco.
DEFENSE_BOND_AFFINITY_THRESHOLD = 25

# Le ambientazioni (richiesto in chat: "un'ambientazione che cambia
# ogni volta") - un luogo diverso da difendere ad ogni tentativo.
DEFENSE_SETTINGS = [
    "il Villaggio di Rodorio", "le Rovine del Tempio Esterno", "il Porto del Sacro Imperio",
    "la Foresta ai piedi del Santuario", "il Ponte di Confine", "l'Accampamento dei Pellegrini",
    "le Terrazze del Colosseo Sacro", "la Valle dei Sette Venti", "il Passo di Star Hill",
    "le Rovine dell'Antico Osservatorio", "il Mercato del Villaggio", "la Piana dei Cento Fuochi",
]


def pick_defense_setting() -> str:
    return random.choice(DEFENSE_SETTINGS)


def pick_enemy_faction(conn, player_divinity: str) -> str:
    """La fazione che attacca (richiesto in chat: "ovviamente non potrà
    essere la fazione del mio pg") - scelta a caso tra tutte le altre
    presenti nel catalogo."""
    rows = conn.execute("SELECT DISTINCT divinity FROM armors WHERE divinity != ?", (player_divinity,)).fetchall()
    divinities = [r["divinity"] for r in rows]
    return random.choice(divinities)


def get_defense_team_candidates(conn, knight: dict, armor: dict, limit_faction: int = 12) -> list[dict]:
    """I possibili alleati per "Seleziona Team" (richiesto in chat) -
    un campione di Cavalieri della TUA fazione, più chiunque abbia
    un'affinità DAVVERO alta con te in Taverna (richiesto in chat:
    "buoni buoni buoni, sennò è una farsa") - questi ultimi possono
    venire anche da un'altra fazione: un legame vero conta più della
    politica. `limit_faction`: quanti compagni di fazione mostrare al
    massimo (con fazioni da 80+ armature, mostrarle tutte sarebbe
    ingestibile in un menu)."""
    faction_rows = conn.execute(
        "SELECT r.armor_name, r.npc_name FROM roster r JOIN armors a ON a.name = r.armor_name "
        "WHERE a.divinity = ? AND a.name != ? AND r.claimed_by_knight_id IS NULL",
        (armor["divinity"], knight["armor_name"]),
    ).fetchall()
    faction_candidates = [dict(r) for r in faction_rows]
    random.shuffle(faction_candidates)
    faction_candidates = faction_candidates[:limit_faction]
    for c in faction_candidates:
        c["source"] = "fazione"

    bond_rows = conn.execute(
        "SELECT armor_name, affinity FROM tavern_relationships WHERE knight_id = ? AND affinity >= ? "
        "AND armor_name NOT LIKE '\\_\\_bartender\\_\\_%' ESCAPE '\\'",
        (knight["id"], DEFENSE_BOND_AFFINITY_THRESHOLD),
    ).fetchall()
    seen_armor_names = {c["armor_name"] for c in faction_candidates} | {knight["armor_name"]}
    bond_candidates = []
    for row in bond_rows:
        if row["armor_name"] in seen_armor_names:
            continue
        roster_entry = get_roster_entry(conn, row["armor_name"])
        if roster_entry is None or roster_entry["claimed_by_knight_id"] is not None:
            continue
        bond_candidates.append({
            "armor_name": row["armor_name"], "npc_name": roster_entry["npc_name"],
            "source": "legame", "affinity": row["affinity"],
        })

    return faction_candidates + bond_candidates


def _build_unit_from_armor(conn, armor_name: str, display_name: str, side: str, unit_id: str) -> dict:
    """Un'unità della battaglia (giocatore, alleato o nemico) - stessa
    forma per tutti, costruita riusando build_opponent_from_armor per
    non duplicare la logica di generazione delle statistiche."""
    base = build_opponent_from_armor(conn, armor_name, display_name)
    base["id"] = unit_id
    base["side"] = side
    base["is_alive"] = True
    base["is_defending"] = False
    base["charged_turns"] = 0
    return base


def _pick_distinct_armors(conn, divinity: str, count: int, exclude: set[str]) -> list[str]:
    """`count` nomi di armatura distinti di questa divinità, escludendo
    quelli già usati (per non avere due unità identiche nella stessa
    battaglia)."""
    rows = conn.execute("SELECT name FROM armors WHERE divinity = ?", (divinity,)).fetchall()
    candidates = [r["name"] for r in rows if r["name"] not in exclude]
    random.shuffle(candidates)
    chosen = candidates[:count]
    while len(chosen) < count and candidates:
        chosen.append(random.choice(candidates))
    return chosen


def _build_wave_enemies(conn, enemy_faction: str, wave_number: int, exclude_armor_names: set[str]) -> list[dict]:
    """I 3 nemici di quest'ondata - un'armatura diversa dalle
    precedenti quando possibile, per varietà tra un'ondata e l'altra."""
    armor_names = _pick_distinct_armors(conn, enemy_faction, UNITS_PER_SIDE, exclude_armor_names)
    enemies = []
    for i, armor_name in enumerate(armor_names):
        guardian_name = get_house_guardian_name(conn, armor_name)
        unit = _build_unit_from_armor(conn, armor_name, guardian_name, "enemies", f"enemy_{wave_number}_{i}")
        enemies.append(unit)
    return enemies


def get_house_guardian_name(conn, armor_name: str) -> str:
    """Il nome del PNG del roster per questa armatura, se esiste -
    stesso principio già usato altrove nel progetto (Maestro,
    Guardiano di Casa: non generato a caso se esiste già un nome
    fisso)."""
    entry = get_roster_entry(conn, armor_name)
    if entry:
        return entry["npc_name"]
    return random.choice(["Marco", "Elena", "Kenji", "Yusuf", "Ingrid"]) + " Ignoto"


def roll_initiative(units: list[dict]) -> list[str]:
    """L'iniziativa in stile D&D (richiesto in chat) - d20 + modificatore
    di Destrezza per ciascuna unità viva, ordine decrescente."""
    rolled = []
    for unit in units:
        if not unit["is_alive"]:
            continue
        _, total = DnDEngine.roll_dice(20, 1, DnDEngine.get_modifier(unit["dex"]))
        rolled.append((total, unit["id"]))
    rolled.sort(key=lambda pair: pair[0], reverse=True)
    return [unit_id for _total, unit_id in rolled]


def start_defense_mission(conn, knight: dict, armor: dict, chosen_ally_armor_names: list[str] | None = None) -> dict:
    """Genera l'intera missione di difesa: ambientazione, fazione
    nemica, la squadra (te + 2 alleati) e la prima ondata di 3 nemici,
    con l'iniziativa già tirata (richiesto in chat: 3 contro 3,
    ambientazione e fazione che cambiano ogni volta, mai la tua stessa
    fazione). `chosen_ally_armor_names` (richiesto in chat: "seleziona
    team" invece del solo team casuale) - se forniti, usa PROPRIO
    quei due alleati (dalla tua fazione o un legame forte in Taverna);
    altrimenti sceglie a caso dalla tua sola fazione, come prima."""
    setting = pick_defense_setting()
    enemy_faction = pick_enemy_faction(conn, armor["divinity"])

    player_unit = _build_unit_from_armor(conn, knight["armor_name"], knight["raw_name"], "allies", "player")
    # Il giocatore usa le PROPRIE statistiche vere, non quelle
    # "standard" derivate dal solo livello armatura (a differenza di
    # alleati e nemici, che sono PNG generati sul momento).
    player_unit.update({
        "str": knight["str"], "dex": knight["dex"], "con": knight["con"],
        "tec": knight["tec"], "vol": knight["vol"],
        "vita_cur": knight["vita_cur"], "vita_max": knight["vita_max"],
        "cosmo_cur": knight["cosmo_cur"], "cosmo_max": knight["cosmo_max"],
        "name": knight["raw_name"],
    })

    if chosen_ally_armor_names:
        ally_armor_names = chosen_ally_armor_names[:UNITS_PER_SIDE - 1]
    else:
        ally_armor_names = _pick_distinct_armors(conn, armor["divinity"], UNITS_PER_SIDE - 1, {knight["armor_name"]})
    allies = [player_unit]
    for i, armor_name in enumerate(ally_armor_names):
        guardian_name = get_house_guardian_name(conn, armor_name)
        allies.append(_build_unit_from_armor(conn, armor_name, guardian_name, "allies", f"ally_{i}"))

    used_armor_names = {u["armor_name"] for u in allies} | {knight["armor_name"]}
    enemies = _build_wave_enemies(conn, enemy_faction, 1, used_armor_names)

    all_units = allies + enemies
    state = {
        "setting": setting,
        "enemy_faction": enemy_faction,
        "wave_number": 1,
        "total_waves": TOTAL_WAVES,
        "units": {u["id"]: u for u in all_units},
        "initiative_order": roll_initiative(all_units),
        "turn_index": 0,
        "round_number": 1,
        "log": [f"L'allarme risuona: {enemy_faction} attacca {setting}, e la tua squadra si schiera per difenderlo."],
        "outcome": None,  # None | "victory" | "defeat"
    }
    _skip_dead_and_autoresolve_enemies(conn, state, just_acted=False)
    return state


def _alive_units(state: dict, side: str) -> list[dict]:
    return [u for u in state["units"].values() if u["side"] == side and u["is_alive"]]


def _current_actor(state: dict) -> dict | None:
    order = state["initiative_order"]
    if not order:
        return None
    idx = state["turn_index"] % len(order)
    return state["units"][order[idx]]


def _advance_turn_index(state: dict) -> None:
    """Passa al prossimo turno, saltando le unità cadute nel frattempo -
    e facendo scattare un nuovo round (col relativo scadere della
    Carica) ogni volta che si torna in cima all'ordine di iniziativa."""
    order = state["initiative_order"]
    if not order:
        return
    for _ in range(len(order)):
        state["turn_index"] += 1
        if state["turn_index"] >= len(order):
            state["turn_index"] = 0
            state["round_number"] += 1
            for unit in state["units"].values():
                if unit["charged_turns"] > 0:
                    unit["charged_turns"] -= 1
        actor = state["units"][order[state["turn_index"]]]
        if actor["is_alive"]:
            return


def _pick_ai_target(state: dict, actor: dict) -> dict | None:
    """Bersaglio scelto dall'IA (per i nemici, e per gli alleati quando
    il giocatore non dà un ordine specifico) - preferisce chi ha meno
    Vita, per concentrare il fuoco in modo credibile."""
    opposing_side = "allies" if actor["side"] == "enemies" else "enemies"
    candidates = _alive_units(state, opposing_side)
    if not candidates:
        return None
    return min(candidates, key=lambda u: u["vita_cur"])


def _pick_ai_technique(actor: dict) -> dict:
    """La tecnica scelta dall'IA - una a caso tra quelle permesse dal
    Cosmo disponibile, altrimenti l'Attacco Base."""
    affordable = [t for t in actor["techniques"] if technique_cosmo_cost(t["name"], t["power"]) <= actor["cosmo_cur"]]
    if not affordable or random.random() < 0.25:
        return {"name": "Attacco Base", "power": BASE_ATTACK_POWER, "tech_type": None}
    return random.choice(affordable)


CRITICAL_FUMBLE_BACKFIRE_CHANCE = 0.4  # PLACEHOLDER: quanto spesso un 1 naturale si rivolta contro un compagno


def _apply_single_attack(conn, state: dict, actor: dict, target: dict, name: str, power: int) -> None:
    """Risolve UN colpo (attaccante, bersaglio, tecnica) e applica tutto
    quello che ne consegue - danno, morte, e il possibile rimbalzo di
    un fallimento critico contro un compagno dell'attaccante (richiesto
    in chat: "il danno critico... si può rivoltare contro uno o più
    compagni"). Funzione condivisa tra l'attacco a bersaglio singolo e
    ciascun colpo di un attacco ad area."""
    dmg, msg, natural_roll = resolve_turn(
        actor["name"], actor["str"], actor["tec"], actor["armor_level"],
        target["name"], target["dex"], target["con"], target["armor_level"],
        name, power,
    )
    if actor["charged_turns"] > 0 and dmg > 0:
        dmg = round(dmg * CHARGE_POWER_BONUS)
    if dmg > 0 and target["is_defending"]:
        dmg = resolve_defense(dmg, None)
    if dmg > 0 and target["charged_turns"] > 0:
        dmg = round(dmg * (2 - CHARGE_POWER_BONUS))  # la Carica riduce anche il danno SUBITO

    target["vita_cur"] = max(0, target["vita_cur"] - dmg)
    state["log"].append(msg if dmg > 0 else f"{actor['name']} attacca {target['name']}, ma manca il colpo.")
    if target["vita_cur"] <= 0:
        target["is_alive"] = False
        state["log"].append(f"{target['name']} è fuori combattimento.")

    # Il fallimento critico può rivoltarsi contro un compagno
    # dell'attaccante stesso (richiesto in chat) - un dettaglio che non
    # esiste nell'Arena 1v1 (lì non c'è nessun compagno da colpire per
    # sbaglio) - solo in una possibilità delle volte, non sempre, e mai
    # a catena (un solo rimbalzo, non altri rimbalzi dal rimbalzo).
    if natural_roll == 1 and random.random() < CRITICAL_FUMBLE_BACKFIRE_CHANCE:
        teammates = [u for u in _alive_units(state, actor["side"]) if u["id"] != actor["id"]]
        if teammates:
            victim = random.choice(teammates)
            back_dmg, back_msg, _ = resolve_turn(
                actor["name"], actor["str"], actor["tec"], actor["armor_level"],
                victim["name"], victim["dex"], victim["con"], victim["armor_level"],
                name, max(1, power // 2),  # un rimbalzo, non il colpo pieno
            )
            if back_dmg > 0:
                victim["vita_cur"] = max(0, victim["vita_cur"] - back_dmg)
                state["log"].append(f"Il fallimento si rivolta contro {victim['name']}! {back_msg}")
                if victim["vita_cur"] <= 0:
                    victim["is_alive"] = False
                    state["log"].append(f"{victim['name']} è fuori combattimento, colpito dalla propria squadra.")


def resolve_squad_action(conn, state: dict, actor_id: str, action: str,
                          target_id: str | None = None, technique_name: str | None = None,
                          technique_power: int | None = None, technique_type: str | None = None,
                          target_mode: str = "singolo") -> None:
    """Risolve UN turno di UNA unità (richiesto in chat, iniziativa
    stile D&D) - `action`: 'attacca' | 'difendi' | 'carica'.
    `target_mode` (richiesto in chat): 'singolo' colpisce un solo
    bersaglio a piena potenza, 'area' divide la potenza della stessa
    tecnica tra TUTTI gli avversari vivi - lo stesso Cosmo speso, ma
    danno per bersaglio più basso quanti più nemici ci sono: una vera
    scelta tattica, non solo un'opzione in più. Muta `state` in place,
    aggiungendo righe a state['log']."""
    actor = state["units"][actor_id]
    if not actor["is_alive"]:
        return
    actor["is_defending"] = False

    if action == "carica":
        actor["cosmo_cur"] = min(actor["cosmo_max"], actor["cosmo_cur"] + CHARGE_COSMO_RESTORE)
        actor["charged_turns"] = CHARGE_TURNS_DURATION
        state["log"].append(f"{actor['name']} si concentra e ricarica il proprio Cosmo.")
    elif action == "difendi":
        actor["is_defending"] = True
        state["log"].append(f"{actor['name']} si mette sulla difensiva.")
    elif action == "attacca":
        name = technique_name or "Attacco Base"
        power = technique_power if technique_power is not None else BASE_ATTACK_POWER
        cost = technique_cosmo_cost(name, power)
        if cost > actor["cosmo_cur"]:
            name, power, technique_type = "Attacco Base", BASE_ATTACK_POWER, None
            cost = 0
        actor["cosmo_cur"] -= cost

        opposing_side = "enemies" if actor["side"] == "allies" else "allies"

        if target_mode == "area":
            targets = _alive_units(state, opposing_side)
            if not targets:
                return
            split_power = max(1, power // len(targets))
            state["log"].append(f"{actor['name']} scatena {name} a tutto campo, colpendo {len(targets)} avversari in una volta.")
            for t in targets:
                if t["is_alive"]:  # un bersaglio precedente potrebbe essere già caduto in questo stesso attacco
                    _apply_single_attack(conn, state, actor, t, name, split_power)
        else:
            target = state["units"].get(target_id) if target_id else None
            if target is None or not target["is_alive"]:
                target = _pick_ai_target(state, actor)
            if target is None:
                return
            _apply_single_attack(conn, state, actor, target, name, power)



AI_AREA_ATTACK_CHANCE = 0.2  # PLACEHOLDER: quanto spesso l'IA (nemici, e alleati senza ordine) sceglie un attacco ad area invece che su un solo bersaglio


def _autoresolve_ai_turn(conn, state: dict) -> None:
    """Un turno interamente deciso dall'IA - nemici sempre, alleati solo
    quando il giocatore non specifica un bersaglio (richiesto in chat:
    ordini semplici, non obbligatori ad ogni turno). Anche l'IA, ogni
    tanto, sceglie di attaccare a tutto campo invece che un singolo
    bersaglio (richiesto in chat) - solo se ha senso, cioè se il lato
    avversario ha più di un'unità viva."""
    actor = _current_actor(state)
    if actor is None:
        return
    opposing_side = "enemies" if actor["side"] == "allies" else "allies"
    technique = _pick_ai_technique(actor)
    if len(_alive_units(state, opposing_side)) > 1 and random.random() < AI_AREA_ATTACK_CHANCE:
        resolve_squad_action(
            conn, state, actor["id"], "attacca", target_mode="area",
            technique_name=technique["name"], technique_power=technique["power"],
            technique_type=technique.get("tech_type"),
        )
        return
    target = _pick_ai_target(state, actor)
    if target is None:
        return
    resolve_squad_action(
        conn, state, actor["id"], "attacca", target_id=target["id"],
        technique_name=technique["name"], technique_power=technique["power"],
        technique_type=technique.get("tech_type"),
    )


def _check_wave_and_mission_outcome(conn, state: dict) -> None:
    """Controlla se l'ondata attuale è stata respinta, se serve farne
    arrivare una nuova, o se la missione è vinta/persa (richiesto in
    chat: squadra fissa, chi cade resta caduto - nessun rinforzo tra
    un'ondata e l'altra, solo nemici nuovi)."""
    player = state["units"]["player"]
    if not player["is_alive"]:
        state["outcome"] = "defeat"
        state["log"].append("Sei caduto in battaglia. La difesa fallisce qui.")
        return
    if not _alive_units(state, "allies"):
        state["outcome"] = "defeat"
        state["log"].append("L'intera squadra è caduta. La difesa fallisce qui.")
        return

    if _alive_units(state, "enemies"):
        return  # l'ondata attuale non è ancora finita

    if state["wave_number"] >= state["total_waves"]:
        state["outcome"] = "victory"
        state["log"].append(f"L'ultima ondata è respinta - {state['setting']} è al sicuro.")
        return

    state["wave_number"] += 1
    state["log"].append(f"L'ondata è respinta! Un'altra ondata di {state['enemy_faction']} si avvicina.")
    used_armor_names = {u["armor_name"] for u in state["units"].values() if u["is_alive"]}
    new_enemies = _build_wave_enemies(conn, state["enemy_faction"], state["wave_number"], used_armor_names)
    for enemy in new_enemies:
        state["units"][enemy["id"]] = enemy
    state["initiative_order"] = roll_initiative(list(state["units"].values()))
    state["turn_index"] = 0


def _skip_dead_and_autoresolve_enemies(conn, state: dict, just_acted: bool = True) -> None:
    """Chiamata SUBITO DOPO aver risolto un'azione (`just_acted=True`,
    il caso normale) o all'avvio della missione (`just_acted=False`,
    nessuna azione ancora avvenuta) - controlla l'esito
    dell'ondata/missione, avanza il turno UNA VOLTA se serve (bug
    corretto: prima non avanzava mai dopo un'azione del giocatore o di
    un alleato, restando bloccati sullo stesso turno per sempre), e fa
    proseguire da sola l'IA nemica finché non tocca di nuovo a un lato
    alleato. Un cambio d'ondata azzera già da solo l'indice del turno
    (vedi _check_wave_and_mission_outcome) - in quel caso NON si deve
    avanzare oltre, altrimenti si salterebbe la prima unità del nuovo
    ordine."""
    if state["outcome"] is not None:
        return

    if just_acted:
        wave_before = state["wave_number"]
        _check_wave_and_mission_outcome(conn, state)
        if state["outcome"] is not None:
            return
        if state["wave_number"] == wave_before:
            _advance_turn_index(state)
    else:
        _check_wave_and_mission_outcome(conn, state)
        if state["outcome"] is not None:
            return

    for _ in range(50):  # tetto di sicurezza, non dovrebbe mai servire davvero
        actor = _current_actor(state)
        if actor is None or actor["side"] == "allies":
            return
        _autoresolve_ai_turn(conn, state)
        wave_before = state["wave_number"]
        _check_wave_and_mission_outcome(conn, state)
        if state["outcome"] is not None:
            return
        if state["wave_number"] == wave_before:
            _advance_turn_index(state)
