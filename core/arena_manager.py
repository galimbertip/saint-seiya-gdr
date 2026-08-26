"""
Gestore dell'Arena del Santuario.

Decisione di design (discussa in chat): l'avversario non è scritto a
mano né è un altro giocatore (nessuna infrastruttura di rete) - viene
GENERATO dal catalogo armature che abbiamo già: si pesca un'armatura di
livello comparabile al tuo, le si danno le sue tecniche vere, e diventa
un "rivale" per lo scontro. Zero dati nuovi da inventare.

Il Cosmo attuale (cosmo_cur) fa da "punti vita" in combattimento, sia
per il giocatore che per l'avversario - niente nuovo campo HP, e resta
in tema (il Cosmo si affievolisce sotto i colpi).

NOTA come per dnd_engine.py e fm_manager.py: le soglie (tolleranza di
livello per l'avversario, potenza dell'Attacco Base, recupero Cosmo a
fine scontro) sono PLACEHOLDER funzionanti, da tarare insieme.
"""
import random
import sqlite3

from core.dnd_engine import DnDEngine
from database.db_manager import get_techniques_for_armor

OPPONENT_LEVEL_TOLERANCE = 20  # cerca avversari con livello armatura entro +-20 dal punto scelto
BASE_ATTACK_POWER = 20  # "Attacco Base": nessuna tecnica richiesta, ma debole

# --- Livelli di sfida --------------------------------------------------
# Spostano il CENTRO della ricerca dell'avversario rispetto al tuo
# livello armatura, invece di cercare sempre "un avversario pari a te".
DIFFICULTY_LEVEL_OFFSET = {
    "facile": -20,
    "medio": 0,
    "difficile": 20,
}
DEFAULT_DIFFICULTY = "medio"

# PLACEHOLDER: bonus di "sintonia cosmica" alla Classe Armatura.
# calculate_ac si aspettava un valore piccolo (0-100 circa), ma qui il
# Cosmo attuale fa da HP e vale 100-250+ - usarlo direttamente fa
# esplodere la CA a 40+ (vedi test in chat: nessun colpo va a segno in
# 30 round). Anche un valore fisso "moderato" tipo 50 si è rivelato
# comunque troppo alto: con dex_mod+armor_bonus la CA arrivava a 25,
# irraggiungibile per un tiro d20+1 (max 21) - IMPOSSIBILE colpire
# anche con un 20 naturale. Per ora azzerato del tutto, finché non
# progettiamo "sintonia cosmica" come statistica separata e bilanciata.
COSMO_ATTUNEMENT_FOR_AC = 0


def generate_opponent(conn: sqlite3.Connection, player_armor_level: int,
                       exclude_armor_names: set[str] | None = None,
                       difficulty: str = DEFAULT_DIFFICULTY) -> dict:
    """Genera un avversario dal catalogo armature. Il livello cercato è
    il tuo livello SPOSTATO in base alla difficoltà scelta (facile:
    più debole di te; difficile: più forte di te) - non più sempre
    "un avversario pari a te". exclude_armor_names: un insieme di nomi
    da escludere (la tua armatura, e/o altri avversari già proposti
    nella stessa "sala d'attesa" - vedi generate_opponent_candidates).
    Se non trova nessuna armatura nella tolleranza (es. livelli
    estremi), allarga la ricerca a tutto il catalogo piuttosto che
    fallire."""
    exclude_armor_names = exclude_armor_names or set()
    offset = DIFFICULTY_LEVEL_OFFSET.get(difficulty, 0)
    target_level = player_armor_level + offset

    rows = conn.execute(
        "SELECT * FROM armors WHERE ABS(level - ?) <= ?",
        (target_level, OPPONENT_LEVEL_TOLERANCE),
    ).fetchall()

    candidates = [r for r in rows if r["name"] not in exclude_armor_names]
    if not candidates:
        all_rows = conn.execute("SELECT * FROM armors").fetchall()
        candidates = [r for r in all_rows if r["name"] not in exclude_armor_names] or list(all_rows)

    armor = random.choice(candidates)
    techniques = [dict(t) for t in get_techniques_for_armor(armor["name"], conn)]
    cosmo = 100 + armor["level"]

    return {
        "name": f"Rivale in {armor['name']}",
        "armor_name": armor["name"],
        "divinity": armor["divinity"],
        "faction": armor["faction"],
        "armor_level": armor["level"],
        "cosmo_cur": cosmo,
        "cosmo_max": cosmo,
        "str": 10 + armor["level"] // 10,
        "dex": 10 + armor["level"] // 10,
        "con": 10 + armor["level"] // 10,
        "tec": 10 + armor["level"] // 10,
        "vol": 10 + armor["level"] // 10,
        "techniques": techniques,
    }


def generate_opponent_candidates(conn: sqlite3.Connection, player_armor_level: int,
                                  exclude_armor_name: str | None = None,
                                  difficulty: str = DEFAULT_DIFFICULTY,
                                  count: int = 5) -> list[dict]:
    """Genera `count` avversari candidati - una "sala d'attesa" tra cui
    scegliere, invece di un solo avversario imposto a caso (richiesto
    in chat). Evita di riproporre due volte la stessa armatura tra i
    candidati, quando il catalogo lo permette."""
    candidates: list[dict] = []
    excluded_names: set[str] = {exclude_armor_name} if exclude_armor_name else set()

    attempts = 0
    max_attempts = count * 5  # margine per quando il catalogo è troppo piccolo per 'count' nomi distinti
    while len(candidates) < count and attempts < max_attempts:
        attempts += 1
        opponent = generate_opponent(conn, player_armor_level, exclude_armor_names=excluded_names, difficulty=difficulty)
        excluded_names.add(opponent["armor_name"])
        candidates.append(opponent)

    return candidates


CRITICAL_FUMBLE_FLAVORS = [
    "inciampa e perde l'equilibrio, restando scoperto",
    "il colpo gli si ritorce contro: una fitta improvvisa lo blocca",
    "scivola e sbatte a terra, mancando il bersaglio di netto",
    "il Cosmo si ribella per un istante, disorientandolo completamente",
]

CRITICAL_HIT_FLAVORS = [
    "trova un varco perfetto nella difesa avversaria",
    "scarica tutta la potenza del Cosmo in un colpo devastante",
    "centra in pieno il punto debole dell'avversario",
]


def resolve_turn(attacker_name: str, attacker_str: int, attacker_tec: int, attacker_armor_level: int,
                  defender_name: str, defender_dex: int, defender_con: int, defender_armor_level: int,
                  technique_name: str, technique_power: int,
                  roll_mode: str = "normale", cause_phrase: str | None = None) -> tuple[int, str]:
    """Risolve un turno d'attacco riusando DnDEngine (CA, tiro per
    colpire, danno) - qui si orchestra soltanto, nessuna nuova formula.
    attacker_tec/defender_con: Tecnica di chi attacca aumenta il danno
    inflitto, Costituzione di chi difende lo riduce - richiesto in
    chat: prima queste due statistiche non contavano nulla in
    combattimento, solo Forza e Destrezza.
    roll_mode: 'normale' | 'vantaggio' | 'svantaggio' - concesso da un
    Imprevisto (vedi maybe_trigger_event) o da altre condizioni future.
    cause_phrase: la spiegazione NARRATIVA del perché (es. "abbagliato
    dal sole") - se non fornita, si usa una frase generica. Deciso in
    chat: niente più etichette nude tipo '[SVANTAGGIO]', la causa entra
    dentro la frase del colpo.
    Un 1 naturale è sempre un fallimento critico (una disgrazia fisica
    vera, pescata a caso - non solo un'etichetta); un 20 naturale è
    sempre un successo e raddoppia il danno (colpo critico) - regole
    richieste in chat.
    Restituisce (danno_inflitto, messaggio_di_log)."""
    defender_ac = DnDEngine.calculate_ac(
        DnDEngine.get_modifier(defender_dex), defender_armor_level, COSMO_ATTUNEMENT_FOR_AC
    )
    hit, dice_roll, attack_total = DnDEngine.resolve_attack(attacker_str, attacker_armor_level, defender_ac, mode=roll_mode)

    if roll_mode == "svantaggio":
        prefix_note = f" ({cause_phrase})" if cause_phrase else " (in difficoltà)"
    elif roll_mode == "vantaggio":
        prefix_note = f" ({cause_phrase})" if cause_phrase else " (con un'apertura perfetta)"
    else:
        prefix_note = ""

    if not hit:
        if dice_roll == 1:
            flavor = random.choice(CRITICAL_FUMBLE_FLAVORS)
            return 0, f"{attacker_name} lancia {technique_name}{prefix_note}... {flavor}! (1 naturale)"
        # "ma" implica un contrasto (aveva un aiuto ma ha fallito comunque -
        # ha senso con il Vantaggio); con lo Svantaggio la schivata non è
        # una sorpresa, è la conseguenza diretta della causa - "e" invece
        # di "ma" (corretto in chat).
        connector = "e" if roll_mode == "svantaggio" else "ma"
        return 0, f"{attacker_name} lancia {technique_name}{prefix_note}, {connector} {defender_name} schiva! ({attack_total} vs CA {defender_ac})"

    attacker_tec_mod = DnDEngine.get_modifier(attacker_tec)
    defender_con_mod = DnDEngine.get_modifier(defender_con)
    _, damage = DnDEngine.resolve_technique_damage(
        technique_power, attacker_armor_level, attacker_tec_mod=attacker_tec_mod, defender_con_mod=defender_con_mod
    )
    if dice_roll == 20:
        damage *= 2
        flavor = random.choice(CRITICAL_HIT_FLAVORS)
        return damage, (f"{attacker_name} colpisce con {technique_name}{prefix_note}: {flavor}! "
                         f"({attack_total} vs CA {defender_ac}) — Danno: {damage} (raddoppiato)")
    return damage, (f"{attacker_name} colpisce con {technique_name}{prefix_note}! "
                     f"({attack_total} vs CA {defender_ac}) — Danno: {damage}")


def format_damage_message(msg: str, actual_damage: int) -> str:
    """resolve_turn scrive il danno GREZZO dentro il messaggio (' — Danno: N').
    Se il danno viene poi modificato (bonus di Carica/Settimo Senso,
    applicato DOPO che il messaggio è già stato costruito), il numero
    scritto nel testo resta quello vecchio e non corrisponde più a
    quello davvero applicato - bug trovato in chat: un messaggio poteva
    dire 'Danno: 6 ... il danno scende a 8' (scende da 6 a un numero
    più alto, contraddittorio). Questa funzione riallinea il testo al
    danno vero, DOPO che eventuali moltiplicatori sono stati applicati
    ma PRIMA di un'eventuale riduzione da difesa (quella si aggiunge
    come frase separata, non sostituisce questo numero)."""
    marker = " — Danno: "
    idx = msg.find(marker)
    if idx == -1:
        return msg  # messaggio di schivata: nessun danno da correggere
    return msg[:idx] + f"{marker}{actual_damage}"


def choose_opponent_technique(opponent: dict) -> tuple[str, int, str]:
    """Sceglie una tecnica a caso tra quelle dell'avversario, o l'Attacco
    Base se non ne ha nessuna. Restituisce (nome, potenza, tech_type) -
    il tech_type serve a maybe_apply_status per riconoscere le tecniche
    che lasciano un effetto (Veleno, per ora)."""
    if opponent["techniques"]:
        t = random.choice(opponent["techniques"])
        return t["name"], t["power"], t.get("tech_type", "")
    return "Attacco Base", BASE_ATTACK_POWER, ""


# --- Sensi del Cosmo ------------------------------------------------------
# Soglie legate al player_level (il livello del PERSONAGGIO, non
# dell'armatura), coerenti col canone di Saint Seiya (verificato in
# chat): il Settimo Senso "brucia il Cosmo al massimo" e nei Bronze
# Saint si risveglia da solo in punto di rottura - qui lo traduco in un
# trigger automatico sotto una soglia critica di Cosmo, non un
# pulsante. L'Ottavo (trascendere la morte) idem: automatico, una
# volta a combattimento. Il Nono (Big Will, ascesa alla divinità) è
# dichiarato ma senza effetto meccanico per ora - fuori portata.
SESTO_SENSO_LEVEL = 3
SETTIMO_SENSO_LEVEL = 10
OTTAVO_SENSO_LEVEL = 20
NONO_SENSO_LEVEL = 50  # placeholder narrativo, nessun effetto meccanico oggi

SEVENTH_SENSE_COSMO_RATIO = 0.2  # sotto il 20% del Cosmo massimo
SEVENTH_SENSE_MULTIPLIER = 2.0

CHARGE_COSMO_COST = 15
CHARGE_DAMAGE_MULTIPLIER = 1.5

DEFAULT_DEFENSE_POWER = 10  # "Parata" generica, per chi non ha una tecnica difensiva


def get_unlocked_senses(player_level: int) -> dict:
    """Quali sensi sono sbloccati al livello personaggio dato."""
    return {
        "sesto": player_level >= SESTO_SENSO_LEVEL,
        "settimo": player_level >= SETTIMO_SENSO_LEVEL,
        "ottavo": player_level >= OTTAVO_SENSO_LEVEL,
        "nono": player_level >= NONO_SENSO_LEVEL,
    }


def find_defensive_technique(techniques: list[dict]) -> dict | None:
    """Cerca una tecnica di tipo 'Difensivo/...' tra quelle date. Solo il
    30% circa delle armature ne ha una (verificato in chat) - se non
    c'è, chi chiama userà la Parata generica (DEFAULT_DEFENSE_POWER)."""
    for t in techniques:
        if "difensiv" in (t.get("tech_type") or "").lower():
            return t
    return None


def resolve_defense(raw_damage: int, defense_technique_power: int | None) -> int:
    """Riduce il danno grezzo in base alla potenza della tecnica
    difensiva (o della Parata generica, se non ne hai una)."""
    defense_power = defense_technique_power if defense_technique_power is not None else DEFAULT_DEFENSE_POWER
    reduction = round(defense_power / 10)
    return max(0, raw_damage - reduction)


def choose_opponent_action(opponent: dict) -> tuple[str, dict | None]:
    """Sceglie l'azione PROATTIVA dell'avversario: Attacca o Carica.
    Difendi non è più una scelta proattiva 'alla cieca' - è reattiva
    (vedi opponent_reacts), decisa solo quando è l'avversario a SUBIRE
    un attacco, non quando lo dichiara lui."""
    action = random.choices(["attacca", "carica"], weights=[0.8, 0.2])[0]

    if action == "attacca":
        name, power, tech_type = choose_opponent_technique(opponent)
        return "attacca", {"name": name, "power": power, "tech_type": tech_type}
    return "carica", None


def opponent_reacts(opponent: dict) -> dict | None:
    """Decide SE l'avversario si difende dal colpo appena dichiarato
    contro di lui (reattivo: la scelta avviene dopo aver 'visto' il tuo
    attacco, non prima). Più probabile se il suo Cosmo è già basso -
    un avversario messo male para più spesso. Restituisce la tecnica
    usata per difendersi (vera o Parata generica), o None se incassa."""
    cosmo_ratio = opponent["cosmo_cur"] / max(opponent["cosmo_max"], 1)
    defend_chance = 0.25 + (0.35 if cosmo_ratio < 0.3 else 0.0)
    if random.random() > defend_chance:
        return None

    defensive = find_defensive_technique(opponent["techniques"])
    if defensive:
        return dict(defensive)
    return {"name": "Parata", "power": DEFAULT_DEFENSE_POWER, "tech_type": "Difensivo"}


# --- Imprevisti (Fase 1: eventi "usa e getta", un solo round) --------------
# Richiesti in chat: una nevicata improvvisa, un sasso lanciato dalle
# tribune, ecc. Fase 1 apposta - niente stati che durano nel tempo
# (quello è la Fase 2, servirebbe tracciare qualcosa round dopo round)
# e niente terzo combattente (Fase 3, tocca la struttura dei turni).
# Ogni evento o fa un piccolo danno diretto immediato, o concede
# vantaggio/svantaggio al tiro di QUESTO round soltanto - non lascia
# nessuno stato dietro di sé.
EVENT_CHANCE = 0.15  # placeholder: 15% di probabilità ad ogni mezzo-round
EVENT_FLAT_DAMAGE_RANGE = (1, 4)

RANDOM_EVENTS = [
    {"name": "Una spettatrice dalle tribune lancia un sasso a sorpresa", "effect": "danno_casuale"},
    {"name": "Una nevicata improvvisa rende il terreno scivoloso", "effect": "svantaggio",
     "cause_phrase": "scivola sul terreno ghiacciato"},
    {"name": "Un raggio di sole abbaglia l'Arena", "effect": "svantaggio",
     "cause_phrase": "abbagliato dal sole"},
    {"name": "Una folata di vento gelido disturba la concentrazione", "effect": "svantaggio",
     "cause_phrase": "distratto dal vento gelido"},
    {"name": "Il pubblico esplode in un boato che carica d'entusiasmo", "effect": "vantaggio",
     "cause_phrase": "spinto dal boato della folla"},
    {"name": "Il terreno cede leggermente sotto i piedi", "effect": "danno_casuale"},
]


def maybe_trigger_event(knight: dict, opponent: dict) -> dict | None:
    """Con probabilità EVENT_CHANCE, pesca un Imprevisto e lo applica
    subito. Un evento 'danno_casuale' modifica knight/opponent in place
    e non tocca il tiro; un evento 'vantaggio'/'svantaggio' non tocca
    subito nessun Cosmo, ma dice al chiamante come tirare IL PROSSIMO
    attacco di questo round (vedi 'roll_mode' in resolve_turn).
    Restituisce {'message': str, 'roll_mode': str} o None se non scatta
    nulla questo round."""
    if random.random() > EVENT_CHANCE:
        return None

    event = random.choice(RANDOM_EVENTS)

    if event["effect"] == "danno_casuale":
        dmg = random.randint(*EVENT_FLAT_DAMAGE_RANGE)
        if random.random() < 0.5:
            knight["cosmo_cur"] = max(0, knight["cosmo_cur"] - dmg)
            colpito = knight["raw_name"]
        else:
            opponent["cosmo_cur"] = max(0, opponent["cosmo_cur"] - dmg)
            colpito = opponent["name"]
        return {
            "message": f"🎲 IMPREVISTO: {event['name']}! {colpito} subisce {dmg} di danno diretto.",
            "roll_mode": "normale",
            "cause_phrase": None,
        }

    return {
        "message": f"🎲 IMPREVISTO: {event['name']}!",
        "roll_mode": event["effect"],  # 'vantaggio' o 'svantaggio' per il prossimo tiro
        "cause_phrase": event.get("cause_phrase"),  # la frase da intrecciare nel messaggio del colpo
    }


# --- Imprevisti Fase 2 -----------------------------------------------------
# Il catalogo ha diversi tipi di tecnica oltre a quelle offensive pure
# (Veleno, Intrappolamento, Pietrificazione, Autocura - isolati la
# prima volta quando abbiamo controllato le tecniche difensive).
#
# V1 (collaudata prima): Veleno, danno che dura ROUNDS_LEFT round.
# V2 (qui): Pietrificazione/Intrappolamento come Paralisi - bloccano un
# turno intero. Rimandata apposta la prima volta perché tocca il
# flusso dei turni (chi dichiara, chi reagisce), non solo un numero
# che scende - va tenuta separata dalla risoluzione dell'azione scelta
# dal giocatore, non sommata dentro.
STATUS_SAVE_DC = 14  # soglia del tiro salvezza di Volontà contro Veleno/Paralisi

STATUS_RULES = {
    "veleno": {"kind": "veleno", "duration": 3},
    "pietrificazione": {"kind": "paralisi", "duration": 1},
    "intrappolamento": {"kind": "paralisi", "duration": 1},
}


def maybe_apply_status(tech_type: str, technique_power: int) -> dict | None:
    """Se la tecnica appena andata a segno è di un tipo che conosciamo
    (Veleno, Pietrificazione, Intrappolamento), restituisce lo stato da
    aggiungere al bersaglio. None per una tecnica 'normale' o per
    l'Attacco Base (che non ha nessun tech_type)."""
    tech_type_lower = (tech_type or "").lower()
    for keyword, rule in STATUS_RULES.items():
        if keyword in tech_type_lower:
            if rule["kind"] == "veleno":
                return {
                    "kind": "veleno",
                    "rounds_left": rule["duration"],
                    "damage_per_round": max(1, technique_power // 20),
                }
            return {"kind": "paralisi", "rounds_left": rule["duration"]}
    return None


def status_applied_message(target_name: str, technique_name: str, status: dict) -> str:
    """Il messaggio da mostrare quando un colpo lascia un effetto sul
    bersaglio - diverso a seconda del tipo di stato inflitto."""
    if status["kind"] == "veleno":
        return f"⚠️ {target_name} è avvelenato da {technique_name}!"
    return f"🥶 {target_name} è pietrificato da {technique_name}!"


def status_resisted(defender_vol: int) -> bool:
    """Tiro salvezza di Volontà contro un nuovo Veleno/Paralisi - se
    supera la soglia STATUS_SAVE_DC, l'effetto non si applica affatto
    (il colpo fa comunque il suo danno normale, solo l'effetto extra
    viene resistito). Richiesto in chat: dare un ruolo vero alla
    Volontà, prima non contava nulla in combattimento."""
    return DnDEngine.resolve_saving_throw(defender_vol, STATUS_SAVE_DC)


def tick_statuses(fighter_name: str, fighter: dict, statuses: list[dict]) -> tuple[list[str], bool]:
    """Applica gli effetti degli stati ATTIVI su `fighter` a inizio del
    suo turno (danno da Veleno, blocco da Paralisi), poi fa scadere di
    un round chi è arrivato a zero. Muta `statuses` in place (rimuove
    quelli scaduti quando la lista viene ricostruita dal chiamante).
    Restituisce (messaggi, bloccato) - bloccato=True se questo turno il
    personaggio è paralizzato e non può agire: il chiamante deve
    saltare la sua azione (vedi resolve_declare), non risolverla
    normalmente."""
    messages = []
    blocked = False
    still_active = []

    for status in statuses:
        if status["kind"] == "veleno":
            dmg = status["damage_per_round"]
            fighter["cosmo_cur"] = max(0, fighter["cosmo_cur"] - dmg)
            messages.append(f"☠️ {fighter_name} soffre per il Veleno! -{dmg} Cosmo.")
        elif status["kind"] == "paralisi":
            blocked = True
            messages.append(f"🥶 {fighter_name} è paralizzato e non riesce a muoversi!")

        status["rounds_left"] -= 1
        if status["rounds_left"] > 0:
            still_active.append(status)
        else:
            kind_label = "Veleno" if status["kind"] == "veleno" else "Paralisi"
            messages.append(f"L'effetto {kind_label} su {fighter_name} è svanito.")

    statuses[:] = still_active
    return messages, blocked
