"""
Logica di orchestrazione di un combattimento in Arena, indipendente da
FastAPI - stesso principio di core/: separare la logica di gioco (che
si può testare senza server, senza rete, senza librerie esterne) dal
modo in cui la si espone (qui: endpoint HTTP invece di pulsanti Qt).

Uno "stato di battaglia" (battle_state, un semplice dict con solo dati
di base: numeri, stringhe, dict annidati - niente oggetti custom)
viaggia avanti e indietro tra client e server ad ogni richiesta HTTP:
il server non tiene nessuna memoria tra una chiamata e l'altra
(stateless, come si conviene a un'API web vera - così funziona anche
con più schede del browser aperte, o riavviando il server a metà
combattimento).

Ogni funzione qui muta `knight` e `battle_state` IN PLACE (stessi dict
passati dal chiamante) e restituisce solo (log, fight_over, winner) -
il chiamante (l'endpoint FastAPI) decide cosa farne (salvare su DB,
restituire come risposta HTTP).
"""
from typing import Optional

from core.arena_manager import (
    generate_opponent, resolve_turn, choose_opponent_action, opponent_reacts,
    resolve_defense, find_defensive_technique, get_unlocked_senses,
    format_damage_message, maybe_trigger_event, maybe_apply_status, tick_statuses, status_applied_message,
    DEFAULT_DEFENSE_POWER, SEVENTH_SENSE_COSMO_RATIO, SEVENTH_SENSE_MULTIPLIER,
    CHARGE_COSMO_COST, CHARGE_DAMAGE_MULTIPLIER, DEFAULT_DIFFICULTY,
)
from core.fm_manager import RosterManager, ARENA_ROUND_MINUTES


def start_battle(conn, knight: dict, armor: dict, difficulty: str = DEFAULT_DIFFICULTY) -> dict:
    """Genera un nuovo avversario e lo stato di battaglia iniziale.
    difficulty: 'facile' | 'medio' | 'difficile' - sposta il livello
    dell'avversario cercato rispetto al tuo (vedi arena_manager)."""
    opponent = generate_opponent(conn, armor["level"], exclude_armor_name=armor["name"], difficulty=difficulty)
    return {
        "opponent": opponent,
        "player_charge_multiplier": 1.0,
        "opponent_charge_multiplier": 1.0,
        "seventh_sense_used": False,
        "eighth_sense_used": False,
        "pending_opponent_technique": None,
        "player_statuses": [],
        "opponent_statuses": [],
    }


def apply_charge(damage: int, is_player: bool, battle_state: dict) -> int:
    """Se chi attacca aveva un bonus di carica attivo (Carica normale o
    Settimo Senso), lo applica e lo consuma - MA SOLO se l'attacco è
    andato a segno. Prima, un colpo mancato consumava comunque la
    carica senza che servisse a nulla (bug segnalato in chat: 15 di
    Cosmo spesi per una carica sprecata su una schivata) - ora la
    carica resta valida finché non centra davvero un colpo."""
    if damage == 0:
        return damage  # schivata: la carica NON si consuma, resta per il prossimo tentativo

    key = "player_charge_multiplier" if is_player else "opponent_charge_multiplier"
    if battle_state[key] > 1.0:
        multiplier = battle_state[key]
        battle_state[key] = 1.0
        return round(damage * multiplier)
    return damage


def check_seventh_sense(knight: dict, battle_state: dict, log: list[str]) -> None:
    """Si risveglia da solo sotto una soglia critica di Cosmo, una
    volta a combattimento (non un pulsante - vedi discussione in chat
    sul canone di Saint Seiya)."""
    if battle_state["seventh_sense_used"]:
        return
    senses = get_unlocked_senses(knight["player_level"])
    if not senses["settimo"]:
        return
    threshold = knight["cosmo_max"] * SEVENTH_SENSE_COSMO_RATIO
    if 0 < knight["cosmo_cur"] <= threshold:
        battle_state["player_charge_multiplier"] = max(
            battle_state["player_charge_multiplier"], SEVENTH_SENSE_MULTIPLIER
        )
        battle_state["seventh_sense_used"] = True
        log.append(
            f"⚡ {knight['raw_name']} risveglia il SETTIMO SENSO! "
            f"Il prossimo attacco sarà devastante."
        )


def check_eighth_sense(knight: dict, battle_state: dict, log: list[str]) -> None:
    """Trascende la morte, una volta a combattimento."""
    if knight["cosmo_cur"] > 0:
        return
    senses = get_unlocked_senses(knight["player_level"])
    if senses["ottavo"] and not battle_state["eighth_sense_used"]:
        battle_state["eighth_sense_used"] = True
        knight["cosmo_cur"] = 1
        log.append(
            f"✨ {knight['raw_name']} trascende la morte con l'OTTAVO SENSO "
            f"e resta in piedi con l'ultimo respiro di Cosmo!"
        )


def check_fight_over(knight: dict, opponent: dict) -> tuple[bool, Optional[str]]:
    if opponent["cosmo_cur"] <= 0:
        return True, "player"
    if knight["cosmo_cur"] <= 0:
        return True, "opponent"
    return False, None


def resolve_declare(knight: dict, armor: dict, action: str, technique_name: Optional[str],
                     technique_power: Optional[int], battle_state: dict,
                     technique_type: Optional[str] = None) -> tuple[list[str], bool, Optional[str]]:
    """Metà 1 del round: il giocatore dichiara (Attacca o Carica). Se
    attacca, l'avversario reagisce d'istinto (automatico); poi
    l'avversario dichiara la SUA mossa - se attacca, il round si ferma
    qui (pending_opponent_technique impostato) e aspetta resolve_react.
    Se il giocatore o l'avversario sono paralizzati (Pietrificazione/
    Intrappolamento), quel lato salta la propria azione per un round -
    il tempo passa comunque, il round prosegue normalmente.
    Muta `knight` e `battle_state` in place.
    Restituisce (log, fight_over, winner)."""
    opponent = battle_state["opponent"]
    log: list[str] = []

    # Stati attivi (Veleno/Paralisi) sul giocatore: si applicano a inizio del suo turno.
    status_msgs, player_blocked = tick_statuses(
        knight["raw_name"], knight, battle_state.setdefault("player_statuses", [])
    )
    log.extend(status_msgs)
    fight_over, winner = check_fight_over(knight, opponent)
    if fight_over:
        return log, True, winner

    if player_blocked:
        log.append(f"{knight['raw_name']} non riesce ad agire questo turno!")
        aging_msg = RosterManager.spend_time(knight, ARENA_ROUND_MINUTES)
        if aging_msg:
            log.append(aging_msg)
        fight_over, winner = check_fight_over(knight, opponent)
        if fight_over:
            return log, True, winner
    else:
        # Imprevisto: una possibilità indipendente ad ogni mezzo-round.
        roll_mode = "normale"
        cause_phrase = None
        event = maybe_trigger_event(knight, opponent)
        if event:
            log.append(event["message"])
            roll_mode = event["roll_mode"]
            cause_phrase = event.get("cause_phrase")
            fight_over, winner = check_fight_over(knight, opponent)
            if fight_over:
                return log, True, winner

        if action == "attacca":
            dmg, msg = resolve_turn(
                knight["raw_name"], knight["str"], armor["level"],
                opponent["name"], opponent["dex"], opponent["armor_level"],
                technique_name, technique_power, roll_mode=roll_mode, cause_phrase=cause_phrase,
            )
            dmg = apply_charge(dmg, True, battle_state)
            msg = format_damage_message(msg, dmg)  # riallinea il testo se la Carica ha cambiato il danno

            if dmg == 0:
                # Schivata vera (il tiro per colpire ha già fallito): niente
                # da difendere, la reazione dell'avversario non ha senso.
                log.append(msg)
            else:
                defense = opponent_reacts(opponent)
                if defense:
                    reduced = resolve_defense(dmg, defense["power"])
                    opponent["cosmo_cur"] = max(0, opponent["cosmo_cur"] - reduced)
                    log.append(f"{msg} — {opponent['name']} para con {defense['name']}, il danno scende a {reduced}.")
                else:
                    opponent["cosmo_cur"] = max(0, opponent["cosmo_cur"] - dmg)
                    log.append(msg)

                status = maybe_apply_status(technique_type, technique_power)
                if status:
                    battle_state.setdefault("opponent_statuses", []).append(status)
                    log.append(status_applied_message(opponent["name"], technique_name, status))
        else:  # carica
            knight["cosmo_cur"] = max(1, knight["cosmo_cur"] - CHARGE_COSMO_COST)
            battle_state["player_charge_multiplier"] = max(
                battle_state["player_charge_multiplier"], CHARGE_DAMAGE_MULTIPLIER
            )
            log.append(f"{knight['raw_name']} carica il Cosmo, pronto a colpire più forte.")

        aging_msg = RosterManager.spend_time(knight, ARENA_ROUND_MINUTES)
        if aging_msg:
            log.append(aging_msg)

        fight_over, winner = check_fight_over(knight, opponent)
        if fight_over:
            return log, True, winner

    # Stati attivi (Veleno/Paralisi) sull'avversario: si applicano a inizio del SUO turno.
    opp_status_msgs, opponent_blocked = tick_statuses(
        opponent["name"], opponent, battle_state.setdefault("opponent_statuses", [])
    )
    log.extend(opp_status_msgs)
    fight_over, winner = check_fight_over(knight, opponent)
    if fight_over:
        return log, True, winner

    if opponent_blocked:
        log.append(f"{opponent['name']} non riesce ad agire questo turno!")
        battle_state["pending_opponent_technique"] = None
        return log, False, None

    opp_action, detail = choose_opponent_action(opponent)
    if opp_action == "carica":
        opponent["cosmo_cur"] = max(1, opponent["cosmo_cur"] - CHARGE_COSMO_COST)
        battle_state["opponent_charge_multiplier"] = max(
            battle_state["opponent_charge_multiplier"], CHARGE_DAMAGE_MULTIPLIER
        )
        log.append(f"{opponent['name']} carica il proprio Cosmo per il prossimo colpo.")
        aging_msg = RosterManager.spend_time(knight, ARENA_ROUND_MINUTES)
        if aging_msg:
            log.append(aging_msg)
        battle_state["pending_opponent_technique"] = None
    else:
        battle_state["pending_opponent_technique"] = detail
        log.append(f"⚔ {opponent['name']} si prepara a colpire con {detail['name']}!")

    return log, False, None


def resolve_react(knight: dict, armor: dict, defend: bool,
                   my_defensive_technique: Optional[dict],
                   battle_state: dict) -> tuple[list[str], bool, Optional[str]]:
    """Metà 2 del round: il giocatore reagisce all'attacco già
    dichiarato dall'avversario (visto in anticipo, non una scelta alla
    cieca). Muta `knight` e `battle_state` in place.
    Restituisce (log, fight_over, winner)."""
    opponent = battle_state["opponent"]
    t = battle_state["pending_opponent_technique"]
    log: list[str] = []

    # Imprevisto: una possibilità indipendente ad ogni mezzo-round.
    roll_mode = "normale"
    cause_phrase = None
    event = maybe_trigger_event(knight, opponent)
    if event:
        log.append(event["message"])
        roll_mode = event["roll_mode"]
        cause_phrase = event.get("cause_phrase")
        fight_over, winner = check_fight_over(knight, opponent)
        if fight_over:
            return log, True, winner

    dmg2, msg2 = resolve_turn(
        opponent["name"], opponent["str"], opponent["armor_level"],
        knight["raw_name"], knight["dex"], armor["level"], t["name"], t["power"],
        roll_mode=roll_mode, cause_phrase=cause_phrase,
    )
    dmg2 = apply_charge(dmg2, False, battle_state)
    msg2 = format_damage_message(msg2, dmg2)  # riallinea il testo se la Carica ha cambiato il danno

    if dmg2 == 0:
        # Schivata vera: niente da difendere, la scelta Difenditi/Incassa
        # non ha inciso su un colpo che non è mai arrivato.
        log.append(msg2)
    elif defend:
        defense_technique = my_defensive_technique or {"name": "Parata", "power": DEFAULT_DEFENSE_POWER}
        reduced = resolve_defense(dmg2, defense_technique["power"])
        knight["cosmo_cur"] = max(0, knight["cosmo_cur"] - reduced)
        log.append(f"{msg2} — ti difendi con {defense_technique['name']}, il danno scende a {reduced}.")
    else:
        knight["cosmo_cur"] = max(0, knight["cosmo_cur"] - dmg2)
        log.append(msg2)

    if dmg2 > 0:
        status = maybe_apply_status(t.get("tech_type", ""), t["power"])
        if status:
            battle_state.setdefault("player_statuses", []).append(status)
            log.append(status_applied_message(knight["raw_name"], t["name"], status))

    check_eighth_sense(knight, battle_state, log)
    check_seventh_sense(knight, battle_state, log)

    aging_msg = RosterManager.spend_time(knight, ARENA_ROUND_MINUTES)
    if aging_msg:
        log.append(aging_msg)

    battle_state["pending_opponent_technique"] = None

    fight_over, winner = check_fight_over(knight, opponent)
    return log, fight_over, winner


def finalize_fight(knight: dict) -> None:
    """Placeholder come nella versione desktop: recupero completo del
    Cosmo a fine scontro, in attesa di un sistema di recupero graduale."""
    knight["cosmo_cur"] = knight["cosmo_max"]
