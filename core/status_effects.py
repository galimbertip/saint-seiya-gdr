"""Gli effetti di stato (richiesto in chat: "gli elementi delle
tecniche non fanno niente di meccanico" - trovato confrontando col
resto del genere RPG a turni, dove un elemento tipicamente produce un
vero effetto persistente, non solo il danno immediato). Un colpo
"Veleno" ora avvelena per davvero, non è solo un'etichetta narrativa.

STESSO sistema per le tecniche del catalogo E per quelle personalizzate
create dai giocatori (richiesto in chat: "come fai a dargli una reale
manifestazione in game?") - entrambe passano dalla stessa funzione
`get_status_effect_for_technique`, che legge solo la stringa
dell'elemento (tech_type), non chi ha creato la tecnica. Un giocatore
che sceglie "Elettrico" per la propria tecnica personalizzata ottiene
esattamente lo stesso effetto di paralisi di una tecnica "Elettrico"
già scritta nei dati - nessuna differenza di trattamento.

PLACEHOLDER, come le altre formule di bilanciamento del progetto:
durate, percentuali e danni per turno sono valori funzionanti ma non
definitivi, da tarare insieme con la simulazione Monte Carlo (vedi
core.balance_simulator)."""

import random

# Un effetto per famiglia di elemento (richiesto in chat) - il
# riconoscimento è per SOTTOSTRINGA sul tech_type (stesso principio
# già usato altrove nel progetto, es. isDefensive() nel frontend, che
# cerca "difensiv" dentro una stringa composita come
# "Ghiaccio/Cosmico/Difensivo") - una tecnica può avere più elementi
# scritti insieme, il primo che trova un effetto riconosciuto vince.
#
# "kind" spiega COME l'effetto agisce meccanicamente:
#   "dot"          -> danno ad ogni turno per `duration` turni
#   "skip_chance"  -> probabilità di saltare il turno, ogni turno, per `duration` turni
#   "miss_chance"  -> probabilità aggiuntiva di mancare un attacco, per `duration` turni
#   "no_action"    -> salta il turno GARANTITO (non a probabilità) per `duration` turni
ELEMENT_STATUS_EFFECTS = {
    "fuoco": {"name": "Bruciatura", "kind": "dot", "duration": 3, "value": 6},
    "veleno": {"name": "Avvelenamento", "kind": "dot", "duration": 4, "value": 8},
    "ghiaccio": {"name": "Congelamento", "kind": "skip_chance", "duration": 2, "value": 0.35},
    "elettrico": {"name": "Paralisi", "kind": "skip_chance", "duration": 2, "value": 0.45},
    "psichico": {"name": "Confusione", "kind": "miss_chance", "duration": 3, "value": 0.30},
    "illusione": {"name": "Confusione", "kind": "miss_chance", "duration": 3, "value": 0.30},
    "intrappolamento": {"name": "Immobilizzato", "kind": "no_action", "duration": 1, "value": None},
}

# L'ordine conta (richiesto implicito: una tecnica composita come
# "Ghiaccio/Cosmico" deve scegliere Ghiaccio, non restare senza
# effetto solo perché "Cosmico" non ne ha uno) - controllati in
# quest'ordine, il primo trovato nella stringa vince. "Fisico" e
# "Cosmico" restano SENZA effetto di stato apposta: sono gli elementi
# "generici" del gioco, portano solo danno diretto - dare un effetto
# anche a loro renderebbe ogni singola tecnica del gioco una fonte di
# status, appiattendo la scelta invece di arricchirla.
_ELEMENT_CHECK_ORDER = ["intrappolamento", "veleno", "elettrico", "ghiaccio", "fuoco", "psichico", "illusione"]


def get_status_effect_for_technique(tech_type: str) -> dict | None:
    """L'effetto di stato che questa tecnica infligge, in base al suo
    elemento (richiesto in chat) - None se l'elemento non ne ha uno
    riconosciuto (es. Fisico, Cosmico, o un tech_type vuoto/sconosciuto).
    Funziona identicamente per tecniche del catalogo e personalizzate:
    non guarda altro che questa stringa."""
    lowered = (tech_type or "").lower()
    for keyword in _ELEMENT_CHECK_ORDER:
        if keyword in lowered:
            return dict(ELEMENT_STATUS_EFFECTS[keyword])  # copia, mai l'originale condiviso
    return None


def apply_status_effect(active_effects: list[dict], new_effect: dict) -> list[dict]:
    """Aggiunge (o RINFRESCA, se già presente) un effetto attivo sulla
    lista di un combattente - deciso di proposito di non farli
    accumulare all'infinito (5 Bruciature attive sullo stesso
    bersaglio sarebbero ingestibili e poco leggibili): la stessa
    Bruciatura colpita di nuovo torna semplicemente a durare
    `duration` turni pieni, invece di sommarsi alla precedente."""
    updated = [e for e in active_effects if e["name"] != new_effect["name"]]
    updated.append({**new_effect, "turns_remaining": new_effect["duration"]})
    return updated


def tick_status_effects(active_effects: list[dict]) -> tuple[int, list[str], list[dict]]:
    """Applica gli effetti "dot" (danno nel tempo) per questo turno e
    fa scadere di 1 la durata di TUTTI gli effetti attivi (dot inclusi)
    - va chiamata una volta a inizio turno, PRIMA che il combattente
    agisca. Restituisce (danno totale da applicare, messaggi
    descrittivi, lista aggiornata senza gli effetti appena scaduti)."""
    total_damage = 0
    messages = []
    remaining = []
    for effect in active_effects:
        if effect["kind"] == "dot":
            total_damage += effect["value"]
            messages.append(f"{effect['name']} infligge {effect['value']} danni.")
        turns_left = effect["turns_remaining"] - 1
        if turns_left > 0:
            remaining.append({**effect, "turns_remaining": turns_left})
        else:
            messages.append(f"{effect['name']} svanisce.")
    return total_damage, messages, remaining


def resolve_turn_start_modifiers(active_effects: list[dict]) -> dict:
    """Cosa succede al combattente PRIMA di poter scegliere un'azione
    questo turno (richiesto in chat: paralisi/immobilizzazione devono
    davvero impedire di agire, non essere solo decorative) - va
    chiamata dopo tick_status_effects, con la lista già aggiornata.
    Restituisce {"skip_turn": bool, "reason": str|None,
    "miss_chance_bonus": float} - il chiamante (il motore di
    combattimento) decide COSA fare con queste informazioni, questo
    modulo si limita a calcolarle."""
    skip_turn = False
    reason = None
    miss_chance_bonus = 0.0
    for effect in active_effects:
        if effect["kind"] == "no_action":
            skip_turn = True
            reason = effect["name"]
        elif effect["kind"] == "skip_chance" and not skip_turn:
            if random.random() < effect["value"]:
                skip_turn = True
                reason = effect["name"]
        elif effect["kind"] == "miss_chance":
            miss_chance_bonus += effect["value"]
    return {"skip_turn": skip_turn, "reason": reason, "miss_chance_bonus": miss_chance_bonus}
