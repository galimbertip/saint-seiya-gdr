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

AGGIORNAMENTO (richiesto in chat): tick_statuses ora restituisce anche
se il combattente è CONFUSO (Psichico) - non blocca il turno come
Paralisi/Paralisi Parziale, costringe invece il prossimo attacco a
tirare in svantaggio. Dato che la Confusione può restare attiva per
più round, e un round è fatto di DUE metà (resolve_declare poi
resolve_react, a volte con un contrattacco dentro resolve_react
stesso), il flag va salvato in battle_state appena calcolato
(player_confused_this_round / opponent_confused_this_round) così resta
disponibile per qualunque attacco di QUEL lato avvenga in quel round,
anche a metà round successiva.
"""
from typing import Optional
import random

from core.arena_manager import (
    generate_opponent, generate_opponent_candidates, resolve_turn, choose_opponent_action, opponent_reacts,
    resolve_defense, get_unlocked_senses,
    format_damage_message, maybe_trigger_event, maybe_apply_status, tick_statuses, status_applied_message,
    status_resisted, calculate_movement_points, try_move, wander_opponent,
    check_attack_range, movement_uses_turn, range_effect, combine_roll_modes, distance_between,
    origin_affinity_modifier, maybe_create_terrain_effect, tick_terrain_effects, position_in_ice_patch,
    apply_flame_damage, apply_mud_penalty, pick_arena_theme, cycle_modifier, cycle_narrative,
    PLAYER_START_POSITION, OPPONENT_START_POSITION,
    DEFAULT_DEFENSE_POWER, SEVENTH_SENSE_COSMO_RATIO, SEVENTH_SENSE_MULTIPLIER,
    CHARGE_TURNS_DURATION, CHARGE_COSMO_RESTORE, CHARGE_POWER_BONUS, DEFAULT_DIFFICULTY, DEFENSE_SUCCESS_FLAVORS,
    BASE_ATTACK_POWER, technique_cosmo_cost,
)
from core.fm_manager import RosterManager, ARENA_ROUND_MINUTES
from core.world_sim import get_faction_disposition


def list_opponent_candidates(conn, armor: dict, difficulty: str = DEFAULT_DIFFICULTY, count: int = 5) -> list[dict]:
    """La 'sala d'attesa': genera `count` avversari tra cui scegliere,
    invece di uno solo imposto a caso (richiesto in chat)."""
    return generate_opponent_candidates(conn, armor["level"], exclude_armor_name=armor["name"],
                                         difficulty=difficulty, count=count)


def start_battle(conn, knight: dict, armor: dict, difficulty: str = DEFAULT_DIFFICULTY,
                  opponent: dict | None = None) -> dict:
    """Costruisce lo stato di battaglia iniziale. Se `opponent` è già
    stato scelto (dalla sala d'attesa), lo usa direttamente; altrimenti
    ne genera uno nuovo a caso (comportamento di prima, tenuto per
    compatibilità/test).
    difficulty: 'facile' | 'medio' | 'difficile' - sposta il livello
    dell'avversario cercato rispetto al tuo (vedi arena_manager),
    usato solo se `opponent` non è già dato."""
    if opponent is None:
        opponent = generate_opponent(conn, armor["level"], exclude_armor_names={armor["name"]}, difficulty=difficulty)
    return {
        "opponent": opponent,
        "player_charge_multiplier": 1.0,
        "opponent_charge_multiplier": 1.0,
        "player_charged_turns": 0,   # le tre barre (richiesto in chat): quanti turni restano al bonus di Carica
        "opponent_charged_turns": 0,
        "seventh_sense_used": False,
        "eighth_sense_used": False,
        "pending_opponent_technique": None,
        "player_statuses": [],
        "opponent_statuses": [],
        "player_confused_this_round": False,
        "opponent_confused_this_round": False,
        "player_position": dict(PLAYER_START_POSITION),
        "opponent_position": dict(OPPONENT_START_POSITION),
        "last_effect": None,
        "player_moved_this_round": 0.0,
        "terrain_effects": [],
        "arena_theme": pick_arena_theme(opponent.get("origin", "")),
    }


def move_player(knight: dict, battle_state: dict, target_x: float, target_y: float) -> list[str]:
    """Sposta il giocatore verso (target_x, target_y), entro i suoi
    Punti Movimento - se il bersaglio è troppo lontano, si ferma al
    massimo raggiungibile invece di rifiutare lo spostamento.
    Nessun costo in tempo per il movimento in sé (tolto in chat: era
    ridondante con la perdita del turno per movimento eccessivo,
    pagare minuti extra E perdere l'attacco per la stessa causa era un
    doppio conto). La distanza percorsa si accumula in
    battle_state['player_moved_this_round'] - se supera metà dei Punti
    Movimento, il prossimo 'attacca' di questo round verrà rifiutato
    (vedi resolve_declare); qui lo si segnala SUBITO, al momento dello
    spostamento, non solo dopo che si è già tentato di attaccare
    (corretto in chat: prima si scopriva solo a cose fatte).
    Muove anche l'avversario di un piccolo passo a caso (Fase 1:
    'sembrare vivo', nessun effetto tattico). Muta `knight` e
    `battle_state` in place. Restituisce i messaggi di log."""
    log: list[str] = []
    battle_state["last_effect"] = None  # muoversi non è un colpo, niente da disegnare sulla mappa
    movement_points = calculate_movement_points(knight["player_level"], knight["age"])
    movement_points_prima_del_fango = movement_points
    movement_points = apply_mud_penalty(movement_points, battle_state["player_position"], battle_state.get("terrain_effects", []))
    if movement_points < movement_points_prima_del_fango:
        log.append(f"🟤 {knight['raw_name']} è nel fango: Punti Movimento dimezzati per questo spostamento.")

    moved_fully, new_pos, distance_moved, blocked_by_crater = try_move(
        battle_state["player_position"], target_x, target_y, movement_points,
        terrain_effects=battle_state.get("terrain_effects", []),
    )
    battle_state["player_position"] = new_pos
    battle_state["player_moved_this_round"] = battle_state.get("player_moved_this_round", 0.0) + distance_moved

    if moved_fully:
        log.append(f"{knight['raw_name']} si sposta di {distance_moved:.1f} unità.")
    elif blocked_by_crater:
        log.append(f"🕳️ Un cratere blocca il passaggio! {knight['raw_name']} si ferma a {distance_moved:.1f} unità.")
    else:
        log.append(
            f"{knight['raw_name']} tenta di raggiungere il punto indicato, ma i suoi Punti "
            f"Movimento ({movement_points}) bastano solo per {distance_moved:.1f} unità."
        )

    if movement_uses_turn(battle_state["player_moved_this_round"], movement_points):
        log.append(f"⚠️ {knight['raw_name']} si è mosso troppo: non potrà attaccare in questo round (potrà comunque Caricare).")

    battle_state["opponent_position"] = wander_opponent(battle_state["opponent_position"])

    return log


def apply_charge(damage: int, is_player: bool, battle_state: dict) -> int:
    """Se chi attacca aveva un bonus di carica attivo (Settimo Senso,
    da un colpo solo, o il bonus pluri-turno di Carica - richiesto in
    chat, le tre barre), lo applica - il Settimo Senso si consuma, il
    bonus di Carica NO (dura più turni, scade da solo - vedi
    tick_charge_turns). MA SOLO se l'attacco è andato a segno: un
    colpo mancato non deve sprecare nulla."""
    if damage == 0:
        return damage  # schivata: nessun bonus si consuma, resta per il prossimo tentativo

    key = "player_charge_multiplier" if is_player else "opponent_charge_multiplier"
    if battle_state[key] > 1.0:
        multiplier = battle_state[key]
        battle_state[key] = 1.0
        damage = round(damage * multiplier)

    turns_key = "player_charged_turns" if is_player else "opponent_charged_turns"
    if battle_state.get(turns_key, 0) > 0:
        damage = round(damage * CHARGE_POWER_BONUS)
    return damage


def apply_charge_defense(damage: int, is_player_defending: bool, battle_state: dict) -> int:
    """Il lato difensivo del bonus di Carica (richiesto in chat, le tre
    barre: 'sia attacco che difesa') - riduce il danno SUBITO se chi
    incassa il colpo ha un bonus di Carica attivo, indipendentemente
    dall'aver usato o meno una tecnica difensiva vera (si sommano)."""
    if damage <= 0:
        return damage
    turns_key = "player_charged_turns" if is_player_defending else "opponent_charged_turns"
    if battle_state.get(turns_key, 0) > 0:
        return max(0, round(damage / CHARGE_POWER_BONUS))
    return damage


def check_seventh_sense(knight: dict, battle_state: dict, log: list[str]) -> None:
    """Si risveglia da solo sotto una soglia critica di VITA (corretto
    in chat: prima controllava il Cosmo, ma con le tre barre separate
    è la Vita a rappresentare "vicino alla morte" - il Cosmo è solo
    una risorsa per le tecniche, non ha più senso narrativo bruciarlo
    per risvegliare un Senso), una volta a combattimento (non un
    pulsante - vedi discussione in chat sul canone di Saint Seiya)."""
    if battle_state["seventh_sense_used"]:
        return
    senses = get_unlocked_senses(knight["player_level"])
    if not senses["settimo"]:
        return
    threshold = knight["vita_max"] * SEVENTH_SENSE_COSMO_RATIO
    if 0 < knight["vita_cur"] <= threshold:
        battle_state["player_charge_multiplier"] = max(
            battle_state["player_charge_multiplier"], SEVENTH_SENSE_MULTIPLIER
        )
        battle_state["seventh_sense_used"] = True
        log.append(
            f"⚡ {knight['raw_name']} risveglia il SETTIMO SENSO! "
            f"Il prossimo attacco sarà devastante."
        )


def check_eighth_sense(knight: dict, battle_state: dict, log: list[str]) -> None:
    """Trascende la morte, una volta a combattimento - controlla la
    VITA ora, non più il Cosmo (stessa correzione di check_seventh_sense
    qui sopra)."""
    if knight["vita_cur"] > 0:
        return
    senses = get_unlocked_senses(knight["player_level"])
    if senses["ottavo"] and not battle_state["eighth_sense_used"]:
        battle_state["eighth_sense_used"] = True
        knight["vita_cur"] = 1
        log.append(
            f"✨ {knight['raw_name']} trascende la morte con l'OTTAVO SENSO "
            f"e resta in piedi con l'ultimo respiro di Vita!"
        )


def check_fight_over(knight: dict, opponent: dict) -> tuple[bool, Optional[str]]:
    if opponent["vita_cur"] <= 0:
        return True, "player"
    if knight["vita_cur"] <= 0:
        return True, "opponent"
    return False, None


def resolve_declare(conn, knight: dict, armor: dict, action: str, technique_name: Optional[str],
                     technique_power: Optional[int], battle_state: dict,
                     technique_type: Optional[str] = None, technique_launch_desc: Optional[str] = None,
                     technique_effect_desc: Optional[str] = None) -> tuple[list[str], bool, Optional[str]]:
    """Metà 1 del round: il giocatore dichiara (Attacca o Carica). Se
    attacca, l'avversario reagisce d'istinto (automatico); poi
    l'avversario dichiara la SUA mossa - se attacca, il round si ferma
    qui (pending_opponent_technique impostato) e aspetta resolve_react.
    Se il giocatore o l'avversario sono paralizzati (Pietrificazione/
    Intrappolamento/Paralisi Parziale da Elettrico), quel lato salta la
    propria azione per un round - il tempo passa comunque, il round
    prosegue normalmente. Se sono Confusi (Psichico), agiscono
    normalmente ma il loro prossimo attacco tira in svantaggio (vedi
    combine_roll_modes più sotto).
    Muta `knight` e `battle_state` in place.
    Restituisce (log, fight_over, winner)."""
    opponent = battle_state["opponent"]
    log: list[str] = []
    terrain_effects = battle_state.setdefault("terrain_effects", [])

    # Le Fiamme (Fase 3) bruciano chi ci si trova, ogni round - PRIMA di
    # farle scadere, così una zona al suo ultimo round di vita fa
    # comunque danno prima di sparire.
    flame_msg_player = apply_flame_damage(knight["raw_name"], knight, battle_state["player_position"], terrain_effects)
    if flame_msg_player:
        log.append(flame_msg_player)
    flame_msg_opponent = apply_flame_damage(opponent["name"], opponent, battle_state["opponent_position"], terrain_effects)
    if flame_msg_opponent:
        log.append(flame_msg_opponent)

    # Il Ghiaccio/Fiamme/Fango (Fase 3) scadono di un round ad ogni
    # chiamata - i crateri restano per sempre (rounds_left=None), non
    # toccati qui. Nessun messaggio quando scadono, sarebbe rumore: la
    # mappa li mostra già sparire da sola.
    tick_terrain_effects(terrain_effects)

    # Il bonus di Carica scade di un turno ad ogni round, per entrambi
    # (richiesto in chat, le tre barre) - un conto alla rovescia
    # semplice, non un'altra tecnica coinvolta.
    if battle_state.get("player_charged_turns", 0) > 0:
        battle_state["player_charged_turns"] -= 1
    if battle_state.get("opponent_charged_turns", 0) > 0:
        battle_state["opponent_charged_turns"] -= 1

    # L'avversario si muove un po' a caso ad ogni round (Fase 1: solo
    # per "sembrare vivo" sulla mappa, nessun effetto tattico - vedi
    # arena_manager.wander_opponent). Nessun messaggio di log per
    # questo, sarebbe troppo rumoroso ad ogni singolo round.
    battle_state["opponent_position"] = wander_opponent(
        battle_state.setdefault("opponent_position", dict(OPPONENT_START_POSITION))
    )

    # Stati attivi (Veleno/Bruciatura/Paralisi/Paralisi Parziale/
    # Confusione) sul giocatore: si applicano a inizio del suo turno.
    status_msgs, player_blocked, player_confused = tick_statuses(
        knight["raw_name"], knight, battle_state.setdefault("player_statuses", [])
    )
    log.extend(status_msgs)
    # Salvato in battle_state (richiesto in chat) - la Confusione può
    # restare attiva anche per il resto del round, incluso un eventuale
    # contrattacco dentro resolve_react, non solo per l'attacco
    # eventualmente risolto qui sotto nello stesso mezzo-round.
    battle_state["player_confused_this_round"] = player_confused
    fight_over, winner = check_fight_over(knight, opponent)
    if fight_over:
        return log, True, winner

    if player_blocked:
        log.append(f"{knight['raw_name']} non riesce ad agire questo turno!")
        battle_state["last_effect"] = None
        aging_msg = RosterManager.spend_time(conn, knight, ARENA_ROUND_MINUTES)
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
            movement_points = calculate_movement_points(knight["player_level"], knight["age"])
            moved_too_much = movement_uses_turn(battle_state.get("player_moved_this_round", 0.0), movement_points)
            out_of_range = not moved_too_much and not check_attack_range(
                battle_state["player_position"], battle_state["opponent_position"], technique_name
            )
            # Il Cosmo come risorsa per le tecniche (richiesto in chat,
            # le tre barre): l'Attacco Base resta sempre gratuito, le
            # tecniche vere costano Cosmo proporzionale alla potenza -
            # senza abbastanza, si ricade sull'Attacco Base invece di
            # bloccare il turno (il frontend dovrebbe già disabilitare
            # il pulsante, questo resta solo un controllo di sicurezza).
            cosmo_cost = technique_cosmo_cost(technique_name, technique_power)
            insufficient_cosmo = cosmo_cost > 0 and knight["cosmo_cur"] < cosmo_cost
            if insufficient_cosmo:
                # Non abbastanza Cosmo per la tecnica scelta (richiesto
                # in chat) - si ricade sull'Attacco Base invece di
                # sprecare il turno; il frontend dovrebbe già impedire
                # di arrivare qui disabilitando il pulsante.
                technique_name, technique_power, technique_type = "Attacco Base", BASE_ATTACK_POWER, None
                technique_launch_desc = technique_effect_desc = None
                cosmo_cost = 0
        else:
            moved_too_much = False
            out_of_range = False
            insufficient_cosmo = False

        # L'azzeramento vale per QUALUNQUE azione dichiarata (attacca O
        # carica) - bug corretto in chat: prima avveniva solo dentro il
        # ramo 'attacca', quindi muoversi un po' e poi scegliere
        # 'carica' lasciava il conteggio "appeso" ai round successivi,
        # bloccando un attacco futuro anche senza essersi mossi in quel
        # turno specifico.
        battle_state["player_moved_this_round"] = 0.0

        if action == "attacca":
            if moved_too_much:
                log.append(f"{knight['raw_name']} si è mosso troppo per attaccare anche in questo round!")
                battle_state["last_effect"] = None
            elif out_of_range:
                log.append(f"{knight['raw_name']} è troppo lontano per colpire con {technique_name} da qui!")
                battle_state["last_effect"] = None
            else:
                # Il Cosmo si spende nel momento in cui si tenta la
                # tecnica, colpisca o meno (richiesto in chat, le tre
                # barre) - hai comunque "acceso" il tuo Cosmo per quel
                # gesto.
                knight["cosmo_cur"] -= cosmo_cost
                distance = distance_between(battle_state["player_position"], battle_state["opponent_position"])
                range_mode, range_power_mult = range_effect(distance, technique_name)
                # Ghiaccio (Fase 3): se sei TU a stare sulla chiazza quando
                # attacchi, sei meno preciso - scivoloso sotto i piedi.
                ice_mode = "svantaggio" if position_in_ice_patch(
                    battle_state["player_position"], battle_state.get("terrain_effects", [])
                ) else "normale"
                # Confusione (richiesto in chat, espansione stati): se
                # sei confuso, il tuo attacco tira in svantaggio - stesso
                # meccanismo già usato per Imprevisti/distanza/Ghiaccio,
                # combinato con combine_roll_modes invece di una logica
                # separata.
                confusion_mode = "svantaggio" if player_confused else "normale"
                combined_mode = combine_roll_modes(
                    combine_roll_modes(combine_roll_modes(roll_mode, range_mode), ice_mode), confusion_mode
                )
                if roll_mode == "normale":
                    if range_mode == "svantaggio":
                        cause_phrase = "il colpo arriva da lontano, meno preciso"
                    elif ice_mode == "svantaggio":
                        cause_phrase = "scivola sul ghiaccio, meno preciso"
                    elif confusion_mode == "svantaggio":
                        cause_phrase = "ancora confuso, fatica a mettere a fuoco il bersaglio"

                dmg, msg, _natural_roll = resolve_turn(
                    knight["raw_name"], knight["str"], knight["tec"], armor["level"],
                    opponent["name"], opponent["dex"], opponent["con"], opponent["armor_level"],
                    technique_name, technique_power, roll_mode=combined_mode, cause_phrase=cause_phrase,
                    launch_desc=technique_launch_desc if technique_name != "Attacco Base" else None,
                    effect_desc=technique_effect_desc if technique_name != "Attacco Base" else None,
                )
                dmg = round(dmg * range_power_mult)
                # Affinità elementale di provenienza (richiesta in chat):
                # bonus se attacchi con l'elemento di casa tuo, resistenza
                # se l'avversario incassa un colpo del suo.
                dmg = round(dmg * origin_affinity_modifier(knight.get("origin", ""), technique_type, as_attacker=True))
                dmg = round(dmg * origin_affinity_modifier(opponent.get("origin", ""), technique_type, as_attacker=False))
                dmg = apply_charge(dmg, True, battle_state)
                msg = format_damage_message(msg, dmg)  # riallinea il testo se la Carica/distanza/affinità ha cambiato il danno

                if dmg == 0:
                    # Schivata vera (il tiro per colpire ha già fallito): niente
                    # da difendere, la reazione dell'avversario non ha senso.
                    log.append(msg)
                    battle_state["last_effect"] = {"attacker": "player", "outcome": "miss", "tech_type": technique_type}
                else:
                    defense = opponent_reacts(opponent)
                    if defense:
                        reduced = resolve_defense(dmg, defense["power"])
                        reduced = apply_charge_defense(reduced, False, battle_state)
                        opponent["vita_cur"] = max(0, opponent["vita_cur"] - reduced)
                        log.append(f"{msg} — {opponent['name']} para con {defense['name']}, il danno scende a {reduced}.")
                        battle_state["last_effect"] = {"attacker": "player", "outcome": "blocked", "tech_type": technique_type}
                        final_damage_dealt = reduced
                    else:
                        dmg = apply_charge_defense(dmg, False, battle_state)
                        msg = format_damage_message(msg, dmg)  # riallinea di nuovo: la Carica difensiva ha appena cambiato il danno
                        opponent["vita_cur"] = max(0, opponent["vita_cur"] - dmg)
                        log.append(msg)
                        battle_state["last_effect"] = {"attacker": "player", "outcome": "hit", "tech_type": technique_type}
                        final_damage_dealt = dmg

                    # Effetti sul terreno (Fase 3): un colpo di Ghiaccio o
                    # abbastanza devastante lascia un segno sulla mappa,
                    # nel punto d'impatto (la posizione dell'avversario).
                    terrain_effect = maybe_create_terrain_effect(
                        battle_state["opponent_position"], technique_type, final_damage_dealt
                    )
                    if terrain_effect:
                        battle_state.setdefault("terrain_effects", []).append(terrain_effect)
                        if terrain_effect["kind"] == "ghiaccio":
                            log.append("❄️ Il colpo lascia una chiazza di ghiaccio sul terreno!")
                        else:
                            log.append("🕳️ Il colpo apre un cratere nel terreno!")

                    status = maybe_apply_status(technique_type, technique_power)
                    if status:
                        if status_resisted(opponent["vol"]):
                            log.append(f"💪 {opponent['name']} resiste all'effetto con la sua Volontà!")
                        else:
                            battle_state.setdefault("opponent_statuses", []).append(status)
                            log.append(status_applied_message(opponent["name"], technique_name, status))
        else:  # carica
            # Le tre barre (richiesto in chat): Carica non spende più
            # Cosmo per un bonus da un colpo solo - ora recupera Cosmo
            # e concede un bonus di potenza (attacco E difesa) per
            # alcuni turni, con un raffreddamento: non si può
            # ricaricare finché il bonus precedente non è scaduto.
            if battle_state["player_charged_turns"] > 0:
                log.append(f"{knight['raw_name']} è già carico - il bonus non è ancora scaduto, non serve ricaricare.")
            else:
                restored = min(knight["cosmo_max"] - knight["cosmo_cur"], CHARGE_COSMO_RESTORE)
                knight["cosmo_cur"] += restored
                battle_state["player_charged_turns"] = CHARGE_TURNS_DURATION
                log.append(
                    f"{knight['raw_name']} carica il Cosmo (+{restored} Cosmo) - più forte in attacco e "
                    f"in difesa per i prossimi {CHARGE_TURNS_DURATION} turni."
                )
            battle_state["last_effect"] = None

        aging_msg = RosterManager.spend_time(conn, knight, ARENA_ROUND_MINUTES)
        if aging_msg:
            log.append(aging_msg)

        fight_over, winner = check_fight_over(knight, opponent)
        if fight_over:
            return log, True, winner

    # Stati attivi (Veleno/Bruciatura/Paralisi/Paralisi Parziale/
    # Confusione) sull'avversario: si applicano a inizio del SUO turno.
    opp_status_msgs, opponent_blocked, opponent_confused = tick_statuses(
        opponent["name"], opponent, battle_state.setdefault("opponent_statuses", [])
    )
    log.extend(opp_status_msgs)
    # Salvato in battle_state (richiesto in chat) - resta disponibile
    # per quando l'attacco dell'avversario viene davvero risolto in
    # resolve_react, alla metà successiva dello stesso round.
    battle_state["opponent_confused_this_round"] = opponent_confused
    fight_over, winner = check_fight_over(knight, opponent)
    if fight_over:
        return log, True, winner

    if opponent_blocked:
        log.append(f"{opponent['name']} non riesce ad agire questo turno!")
        battle_state["pending_opponent_technique"] = None
        return log, False, None

    opp_action, detail = choose_opponent_action(opponent, get_faction_disposition(conn, opponent.get("divinity", "")))
    if opp_action == "carica":
        # Stesso raffreddamento del giocatore (richiesto in chat) - se
        # l'IA "vorrebbe" ricaricare ma è già carica, il turno va
        # comunque sprecato (stessa penalità che avrebbe un giocatore
        # umano che clicca Carica per errore mentre è già attivo).
        if battle_state["opponent_charged_turns"] > 0:
            log.append(f"{opponent['name']} è già carico - il turno passa senza effetto.")
        else:
            restored = min(opponent["cosmo_max"] - opponent["cosmo_cur"], CHARGE_COSMO_RESTORE)
            opponent["cosmo_cur"] += restored
            battle_state["opponent_charged_turns"] = CHARGE_TURNS_DURATION
            log.append(f"{opponent['name']} carica il proprio Cosmo (+{restored}) - più forte per alcuni turni.")
        aging_msg = RosterManager.spend_time(conn, knight, ARENA_ROUND_MINUTES)
        if aging_msg:
            log.append(aging_msg)
        battle_state["pending_opponent_technique"] = None
    else:
        # Il Cosmo come risorsa vale anche per l'avversario (richiesto
        # in chat, le tre barre: "l'IA deve rispettare lo stesso
        # vincolo") - se non può permettersi la tecnica scelta, ricade
        # sull'Attacco Base, gratuito.
        opp_cosmo_cost = technique_cosmo_cost(detail["name"], detail["power"])
        if opp_cosmo_cost > 0 and opponent["cosmo_cur"] < opp_cosmo_cost:
            detail = {"name": "Attacco Base", "power": BASE_ATTACK_POWER, "tech_type": ""}
            opp_cosmo_cost = 0
        opponent["cosmo_cur"] -= opp_cosmo_cost
        battle_state["pending_opponent_technique"] = detail
        log.append(f"⚔ {opponent['name']} si prepara a colpire con {detail['name']}!")

    return log, False, None


def resolve_react(conn, knight: dict, armor: dict, action: str,
                   my_defensive_technique: Optional[dict],
                   battle_state: dict, counter_technique_name: Optional[str] = None,
                   counter_technique_power: Optional[int] = None, counter_technique_type: Optional[str] = None,
                   counter_technique_launch_desc: Optional[str] = None,
                   counter_technique_effect_desc: Optional[str] = None) -> tuple[list[str], bool, Optional[str]]:
    """Metà 2 del round: il giocatore reagisce all'attacco già
    dichiarato dall'avversario (visto in anticipo, non una scelta alla
    cieca). action: 'difenditi' | 'contrattacca' | 'incassa' (richiesto
    in chat, terza opzione oltre alle due originarie).
    'difenditi': come prima, danno ridotto dalla tecnica difensiva (o
    Parata), il giocatore non attacca.
    'contrattacca': il colpo avversario arriva PIENO, non ridotto per
    niente (stesso trattamento di 'incassa') - ma subito dopo il
    giocatore lancia indietro una SUA tecnica offensiva
    (counter_technique_*), risolta come un vero attacco a sé stante
    (Imprevisto proprio, portata, affinità elementale, effetti sul
    terreno - tutto uguale a un attacco dichiarato normalmente). Un
    vero scambio di colpi, rischioso da entrambi i lati.
    'incassa': come prima, danno pieno, nessuna reazione.
    Muta `knight` e `battle_state` in place.
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

    # Ghiaccio (Fase 3): se l'AVVERSARIO sta sulla chiazza mentre
    # attacca lui, è lui a essere meno preciso.
    ice_mode = "svantaggio" if position_in_ice_patch(
        battle_state["opponent_position"], battle_state.get("terrain_effects", [])
    ) else "normale"
    # Confusione (richiesto in chat, espansione stati): se l'avversario
    # era stato confuso quando i suoi stati sono stati aggiornati in
    # resolve_declare, questo suo attacco (che si risolve solo ora)
    # tira in svantaggio.
    opponent_confused = battle_state.get("opponent_confused_this_round", False)
    confusion_mode = "svantaggio" if opponent_confused else "normale"
    combined_mode = combine_roll_modes(combine_roll_modes(roll_mode, ice_mode), confusion_mode)
    if roll_mode == "normale":
        if ice_mode == "svantaggio":
            cause_phrase = "scivola sul ghiaccio, meno preciso"
        elif confusion_mode == "svantaggio":
            cause_phrase = "ancora confuso, fatica a mettere a fuoco il bersaglio"

    dmg2, msg2, _natural_roll2 = resolve_turn(
        opponent["name"], opponent["str"], opponent["tec"], opponent["armor_level"],
        knight["raw_name"], knight["dex"], knight["con"], armor["level"], t["name"], t["power"],
        roll_mode=combined_mode, cause_phrase=cause_phrase,
        launch_desc=t.get("launch_desc") if t["name"] != "Attacco Base" else None,
        effect_desc=t.get("effect_desc") if t["name"] != "Attacco Base" else None,
    )
    dmg2 = round(dmg2 * origin_affinity_modifier(opponent.get("origin", ""), t.get("tech_type", ""), as_attacker=True))
    dmg2 = round(dmg2 * origin_affinity_modifier(knight.get("origin", ""), t.get("tech_type", ""), as_attacker=False))
    dmg2 = apply_charge(dmg2, False, battle_state)
    msg2 = format_damage_message(msg2, dmg2)  # riallinea il testo se la Carica ha cambiato il danno

    if dmg2 == 0:
        # Schivata vera: niente da difendere, la scelta di reazione non
        # ha inciso su un colpo che non è mai arrivato.
        log.append(msg2)
        battle_state["last_effect"] = {"attacker": "opponent", "outcome": "miss", "tech_type": t.get("tech_type", "")}
    elif action == "difenditi":
        defense_technique = my_defensive_technique or {"name": "Difesa Base", "power": DEFAULT_DEFENSE_POWER}
        reduced = resolve_defense(dmg2, defense_technique["power"])
        # Ciclo elementale (richiesto in chat): se la tua tecnica
        # difensiva ha un elemento del ciclo, viene confrontata con
        # l'elemento dell'attacco - più efficace se lo batte, meno se
        # ne è battuta. La Parata generica non ha un elemento proprio
        # (nessun tech_type), quindi resta sempre neutra (moltiplicatore
        # 1.0, invariata).
        cycle_mod = cycle_modifier(defense_technique.get("tech_type", ""), t.get("tech_type", ""))
        reduced = max(0, round(reduced / cycle_mod))
        reduced = apply_charge_defense(reduced, True, battle_state)
        cycle_msg = cycle_narrative(defense_technique.get("tech_type", ""), t.get("tech_type", ""))
        knight["vita_cur"] = max(0, knight["vita_cur"] - reduced)
        # Intreccio lancio+effetto della tecnica difensiva (richiesto in
        # chat: prima si vedeva solo il nome, "ti difendi con X" e
        # basta - la descrizione propria della tecnica non veniva mai
        # usata) - con più varianti drammatiche per non ripetersi.
        if defense_technique.get("launch_desc"):
            defense_clause = f"{defense_technique['name']} ({defense_technique['launch_desc']})"
        else:
            defense_clause = defense_technique["name"]
        defense_flavor = random.choice(DEFENSE_SUCCESS_FLAVORS)
        effect_note = f" - {defense_technique['effect_desc']}" if defense_technique.get("effect_desc") else ""
        log.append(f"{msg2} — ti difendi con {defense_clause}: {defense_flavor}{effect_note}, il danno scende a {reduced}.")
        if cycle_msg:
            log.append(cycle_msg)
        battle_state["last_effect"] = {"attacker": "opponent", "outcome": "blocked", "tech_type": t.get("tech_type", "")}
        final_damage_dealt2 = reduced
    else:
        # 'contrattacca' e 'incassa' prendono il colpo PIENO, senza
        # riduzione da tecnica difensiva - il contrattacco non
        # protegge, è tutto rischio in cambio della possibilità di
        # ferire (richiesto in chat). Il bonus difensivo di Carica
        # (richiesto in chat, le tre barre) si applica comunque: essere
        # carichi rende più solidi a prescindere da come si reagisce.
        dmg2 = apply_charge_defense(dmg2, True, battle_state)
        msg2 = format_damage_message(msg2, dmg2)  # riallinea di nuovo: la Carica difensiva ha appena cambiato il danno
        knight["vita_cur"] = max(0, knight["vita_cur"] - dmg2)
        log.append(msg2)
        battle_state["last_effect"] = {"attacker": "opponent", "outcome": "hit", "tech_type": t.get("tech_type", "")}
        final_damage_dealt2 = dmg2

    if dmg2 > 0:
        terrain_effect2 = maybe_create_terrain_effect(
            battle_state["player_position"], t.get("tech_type", ""), final_damage_dealt2
        )
        if terrain_effect2:
            battle_state.setdefault("terrain_effects", []).append(terrain_effect2)
            if terrain_effect2["kind"] == "ghiaccio":
                log.append("❄️ Il colpo lascia una chiazza di ghiaccio sul terreno!")
            else:
                log.append("🕳️ Il colpo apre un cratere nel terreno!")

        status = maybe_apply_status(t.get("tech_type", ""), t["power"])
        if status:
            if status_resisted(knight["vol"]):
                log.append(f"💪 {knight['raw_name']} resiste all'effetto con la sua Volontà!")
            else:
                battle_state.setdefault("player_statuses", []).append(status)
                log.append(status_applied_message(knight["raw_name"], t["name"], status))

    check_eighth_sense(knight, battle_state, log)
    check_seventh_sense(knight, battle_state, log)

    fight_over, winner = check_fight_over(knight, opponent)
    if fight_over:
        battle_state["pending_opponent_technique"] = None
        return log, True, winner

    # --- Contrattacco (richiesto in chat) -----------------------------
    # Un vero attacco a sé stante: stesso trattamento di un attacco
    # dichiarato normalmente (Imprevisto proprio, portata, ghiaccio,
    # Confusione, affinità elementale, effetti sul terreno) - solo che
    # avviene qui, subito dopo aver incassato il colpo avversario per
    # intero.
    if action == "contrattacca" and counter_technique_name:
        # Il Cosmo come risorsa vale anche per il contrattacco
        # (richiesto in chat, le tre barre) - stesso trattamento
        # dell'attacco dichiarato: senza abbastanza, ricade
        # sull'Attacco Base.
        counter_cosmo_cost = technique_cosmo_cost(counter_technique_name, counter_technique_power)
        if counter_cosmo_cost > 0 and knight["cosmo_cur"] < counter_cosmo_cost:
            counter_technique_name = "Attacco Base"
            counter_technique_power = BASE_ATTACK_POWER
            counter_technique_type = None
            counter_technique_launch_desc = counter_technique_effect_desc = None
            counter_cosmo_cost = 0

        roll_mode3 = "normale"
        cause_phrase3 = None
        event3 = maybe_trigger_event(knight, opponent)
        if event3:
            log.append(event3["message"])
            roll_mode3 = event3["roll_mode"]
            cause_phrase3 = event3.get("cause_phrase")
            fight_over, winner = check_fight_over(knight, opponent)
            if fight_over:
                battle_state["pending_opponent_technique"] = None
                return log, True, winner

        out_of_range3 = not check_attack_range(
            battle_state["player_position"], battle_state["opponent_position"], counter_technique_name
        )
        if out_of_range3:
            log.append(f"{knight['raw_name']} è troppo lontano per colpire con {counter_technique_name} in contrattacco!")
        else:
            # Il Cosmo si spende nel tentativo, colpisca o meno
            # (richiesto in chat, stessa logica dell'attacco dichiarato).
            knight["cosmo_cur"] -= counter_cosmo_cost
            distance3 = distance_between(battle_state["player_position"], battle_state["opponent_position"])
            range_mode3, range_power_mult3 = range_effect(distance3, counter_technique_name)
            ice_mode3 = "svantaggio" if position_in_ice_patch(
                battle_state["player_position"], battle_state.get("terrain_effects", [])
            ) else "normale"
            # Confusione (richiesto in chat): la stessa Confusione del
            # giocatore, calcolata a inizio round in resolve_declare,
            # resta valida anche per il contrattacco a metà round
            # successiva - salvata in battle_state proprio per questo.
            player_confused = battle_state.get("player_confused_this_round", False)
            confusion_mode3 = "svantaggio" if player_confused else "normale"
            combined_mode3 = combine_roll_modes(
                combine_roll_modes(combine_roll_modes(roll_mode3, range_mode3), ice_mode3), confusion_mode3
            )
            if roll_mode3 == "normale":
                if range_mode3 == "svantaggio":
                    cause_phrase3 = "il colpo arriva da lontano, meno preciso"
                elif ice_mode3 == "svantaggio":
                    cause_phrase3 = "scivola sul ghiaccio, meno preciso"
                elif confusion_mode3 == "svantaggio":
                    cause_phrase3 = "ancora confuso, fatica a mettere a fuoco il bersaglio"

            dmg3, msg3, _natural_roll3 = resolve_turn(
                knight["raw_name"], knight["str"], knight["tec"], armor["level"],
                opponent["name"], opponent["dex"], opponent["con"], opponent["armor_level"],
                counter_technique_name, counter_technique_power, roll_mode=combined_mode3, cause_phrase=cause_phrase3,
                launch_desc=counter_technique_launch_desc if counter_technique_name != "Attacco Base" else None,
                effect_desc=counter_technique_effect_desc if counter_technique_name != "Attacco Base" else None,
            )
            dmg3 = round(dmg3 * range_power_mult3)
            dmg3 = round(dmg3 * origin_affinity_modifier(knight.get("origin", ""), counter_technique_type, as_attacker=True))
            dmg3 = round(dmg3 * origin_affinity_modifier(opponent.get("origin", ""), counter_technique_type, as_attacker=False))
            # Ciclo elementale (richiesto in chat): la TUA tecnica di
            # contrattacco contro l'elemento dell'attacco che ti ha
            # appena colpito - un vero scontro diretto tra due tecniche.
            dmg3 = round(dmg3 * cycle_modifier(counter_technique_type, t.get("tech_type", "")))
            dmg3 = apply_charge(dmg3, True, battle_state)
            msg3 = format_damage_message(msg3, dmg3)
            cycle_msg3 = cycle_narrative(counter_technique_type, t.get("tech_type", ""))
            if cycle_msg3:
                log.append(cycle_msg3)

            if dmg3 == 0:
                log.append(msg3)
                battle_state["last_effect"] = {"attacker": "player", "outcome": "miss", "tech_type": counter_technique_type}
            else:
                opp_defense = opponent_reacts(opponent)
                if opp_defense:
                    reduced3 = resolve_defense(dmg3, opp_defense["power"])
                    reduced3 = apply_charge_defense(reduced3, False, battle_state)
                    opponent["vita_cur"] = max(0, opponent["vita_cur"] - reduced3)
                    log.append(f"{msg3} — {opponent['name']} para con {opp_defense['name']}, il danno scende a {reduced3}.")
                    battle_state["last_effect"] = {"attacker": "player", "outcome": "blocked", "tech_type": counter_technique_type}
                    final_damage3 = reduced3
                else:
                    dmg3 = apply_charge_defense(dmg3, False, battle_state)
                    msg3 = format_damage_message(msg3, dmg3)  # riallinea di nuovo: la Carica difensiva ha appena cambiato il danno
                    opponent["vita_cur"] = max(0, opponent["vita_cur"] - dmg3)
                    log.append(msg3)
                    battle_state["last_effect"] = {"attacker": "player", "outcome": "hit", "tech_type": counter_technique_type}
                    final_damage3 = dmg3

                terrain_effect3 = maybe_create_terrain_effect(
                    battle_state["opponent_position"], counter_technique_type, final_damage3
                )
                if terrain_effect3:
                    battle_state.setdefault("terrain_effects", []).append(terrain_effect3)
                    if terrain_effect3["kind"] == "ghiaccio":
                        log.append("❄️ Il colpo lascia una chiazza di ghiaccio sul terreno!")
                    else:
                        log.append("🕳️ Il colpo apre un cratere nel terreno!")

                status3 = maybe_apply_status(counter_technique_type, counter_technique_power)
                if status3:
                    if status_resisted(opponent["vol"]):
                        log.append(f"💪 {opponent['name']} resiste all'effetto con la sua Volontà!")
                    else:
                        battle_state.setdefault("opponent_statuses", []).append(status3)
                        log.append(status_applied_message(opponent["name"], counter_technique_name, status3))

            fight_over, winner = check_fight_over(knight, opponent)
            if fight_over:
                battle_state["pending_opponent_technique"] = None
                return log, True, winner

    aging_msg = RosterManager.spend_time(conn, knight, ARENA_ROUND_MINUTES)
    if aging_msg:
        log.append(aging_msg)

    battle_state["pending_opponent_technique"] = None

    fight_over, winner = check_fight_over(knight, opponent)
    return log, fight_over, winner


def finalize_fight(knight: dict) -> None:
    """Le tre barre (richiesto in chat) - niente più guarigione
    istantanea a fine scontro: Vita, Cosmo e Stamina si recuperano ora
    gradualmente col tempo (riposo, allenamento - vedi
    RosterManager.apply_daily_training), non di colpo. Il vecchio
    comportamento era esplicitamente un placeholder "in attesa di un
    sistema di recupero graduale" - quel sistema ora esiste. Funzione
    lasciata vuota (non rimossa) per non dover toccare tutti i punti
    che la richiamano a fine combattimento."""
    pass
