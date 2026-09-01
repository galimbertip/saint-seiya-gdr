"""Il mondo che vive per conto suo (richiesto in chat) - i PNG del
roster (quelli NON reclamati da un personaggio giocatore) possono
morire, ritirarsi, o essere sostituiti col passare del tempo
condiviso, indipendentemente dal giocatore - proprio come in Football
Manager le altre squadre giocano le proprie partite mentre tu giochi
la tua. Include anche le Figure Istituzionali (richiesto in chat: pure
loro cambiano nel tempo, non restano fisse per sempre) e un pool di
eventi di mondo puramente narrativi (guerre sfiorate, presagi legati
alle divinità, fatti che non riguardano direttamente nessun Cavaliere)
- questi ultimi non muovono nessuno stato di gioco, sono solo Cronaca.

Una simulazione leggera e probabilistica, non un motore narrativo
completo: bassa probabilità per singolo PNG, per sentirsi vivo nel
tempo senza essere caotico o richiedere una vera IA per ciascuno.
Chiamata da core.fm_manager.RosterManager.spend_time ogni volta che il
tempo avanza abbastanza (un giorno pieno) da giustificare il
ricalcolo - richiamarla ad ogni minuscolo avanzamento (es. un mezzo
round di combattimento) sarebbe inutilmente costoso."""

import random

from core.arena_manager import generate_full_name
from core.institutional_npcs import INSTITUTIONAL_NPCS
from database.db_manager import add_world_event

WORLD_TICK_MINUTES_PER_DAY = 1440

# Probabilità che un singolo PNG non reclamato abbia un evento notevole
# in UN giorno di tempo condiviso - bassa apposta (con oltre 200
# armature nel catalogo, anche una probabilità piccola genera comunque
# eventi visibili nell'arco di settimane di gioco). PLACEHOLDER da
# tarare insieme, come le altre formule di bilanciamento del progetto.
# Ricalibrata in chat: con il ritmo REALE del tempo di gioco (una
# sessione di allenamento consuma 4-8 ore, non un giorno intero - 2
# "mesi" cliccati in interfaccia avanzano il mondo di appena una
# dozzina di giorni, non 60), il valore precedente (0.0005) dava una
# media di poco più di un evento atteso per un'intera sessione di
# gioco prolungata - capitava facilmente zero per puro caso. Alzata a
# un ritmo più affidabile da notare. PLACEHOLDER, da tarare ancora
# insieme se serve.
NPC_EVENT_CHANCE_PER_DAY = 0.0015

# Le Figure Istituzionali (richiesto in chat) - probabilità PER
# CIASCUNA delle 4, più alta di quella di un singolo PNG comune (sono
# solo 4, non 228 - "qualche evento in più", non uno raro quanto un
# singolo PNG) ma comunque un evento importante, non frequente.
INSTITUTIONAL_EVENT_CHANCE_PER_DAY = 0.004

# Eventi di mondo puramente narrativi (richiesto in chat: guerre tra
# fazioni che non coinvolgono il giocatore, presagi legati alle
# divinità, fatti che non riguardano nessun Cavaliere in particolare) -
# non muovono nessuno stato di gioco, solo Cronaca. Frequenza "media",
# come le Figure Istituzionali: più di un singolo PNG, ma non
# quotidiana. {a} e {b} vengono riempiti con due divinità a caso,
# diverse tra loro, quando il testo li prevede.
WORLD_FLAVOR_EVENT_CHANCE_PER_DAY = 0.004
WORLD_FLAVOR_EVENTS = [
    "Voci di scontri ai confini tra {a} e {b} agitano il Sacro Imperio per qualche settimana, prima che la crisi rientri da sola.",
    "Una carestia colpisce le terre ai piedi dei domini di {a}; più di un Cavaliere destina parte delle proprie razioni ai villaggi vicini.",
    "Una cometa insolitamente luminosa attraversa il cielo notturno - gli astronomi del Sacro Imperio la leggono come un presagio, anche se nessuno concorda su cosa presagisca.",
    "Un boato scuote per un istante i cieli sopra i domini di {a}: si dice che il suo Cosmo abbia vacillato, prima di tornare a bruciare come sempre.",
    "Un terremoto minore scuote una delle regioni sacre; i danni sono lievi, ma i sacerdoti locali lo interpretano come un monito.",
    "Rifugiati in fuga da un conflitto lontano tra {a} e {b} chiedono asilo ai confini del Sacro Imperio - la loro richiesta divide i Cavalieri più di quanto ci si aspettasse.",
    "Un'eclissi inattesa oscura il sole a mezzogiorno; per alcuni istanti, in tutto il Sacro Imperio, ci si ferma a guardare il cielo.",
    "Mercanti di ritorno dai domini di {a} raccontano di un raccolto straordinario, il migliore da generazioni - qualcuno lo lega a un favore divino, altri solo al clima.",
]

# Per lo più un ritiro o una sparizione; la morte vera in duello resta
# minoritaria, non l'esito predefinito (stesso principio già seguito
# per il destino dei compagni in core.apprentice_fates).
NPC_FATE_OPTIONS = [
    ("muore in un duello mai raccontato, e l'armatura resta orfana per un po' prima che qualcuno la raccolga.", 0.3),
    ("si ritira dalla vita da Cavaliere, stanco di una guerra che sembra non finire mai.", 0.4),
    ("sparisce senza lasciare traccia - c'è chi dice sia fuggito, chi dice di peggio.", 0.3),
]

# Le Figure Istituzionali restano volutamente ANONIME anche dopo un
# cambio (richiesto in chat, coerente con come sono già scritte in
# core/institutional_npcs.py: maschere, volti nascosti, identità mai
# rivelate) - l'evento racconta il PASSAGGIO, mai un nome proprio.
INSTITUTIONAL_SUCCESSION_TEXTS = {
    "grande-sacerdote": (
        "La maschera dorata del Grande Sacerdote passa a un nuovo volto, in una cerimonia "
        "che nessuno al di fuori del Tempio ha potuto vedere. Il Santuario non si è fermato "
        "nemmeno per un giorno."
    ),
    "pandora": (
        "Un nuovo volto amministra ora il Castello di Hades in nome del Signore degli Inferi - "
        "della precedente amministratrice, negli Inferi, non si parla più."
    ),
    "generale-dei-sette-mari": (
        "Un nuovo Generale Supremo prende il comando dei Sette Mari - le Colonne non hanno mai "
        "smesso di rispondere a quel titolo, chiunque lo porti."
    ),
    "guardiano-di-asgard": (
        "Un nuovo Guardiano veglia ora sul Palazzo di Valhalla - l'armatura d'inverno è passata "
        "di mano. Il gelo no."
    ),
}


def resolve_npc_fate() -> str:
    """Un destino narrativo per UN PNG che lascia il proprio posto
    (richiesto in chat) - stesso principio di
    core.apprentice_fates.resolve_companion_fate, qui applicato ai PNG
    del mondo invece che ai compagni d'addestramento."""
    roll = random.random()
    cumulative = 0.0
    for text, weight in NPC_FATE_OPTIONS:
        cumulative += weight
        if roll < cumulative:
            return text
    return NPC_FATE_OPTIONS[-1][0]


def _roll_chance(elapsed_minutes: int, chance_per_day: float) -> bool:
    """Un singolo tiro, con la probabilità cumulata sull'intero periodo
    trascorso in un colpo solo (non un tiro al giorno per ogni giorno -
    un'approssimazione ragionevole per probabilità così basse, molto
    più efficiente con periodi lunghi)."""
    days = elapsed_minutes / WORLD_TICK_MINUTES_PER_DAY
    chance = 1 - (1 - chance_per_day) ** days
    return random.random() < chance


def _tick_institutional_events(conn, elapsed_minutes: int, current_world_minutes: int) -> list[dict]:
    """Le Figure Istituzionali cambiano nel tempo anche loro (richiesto
    in chat) - restano anonime, l'evento racconta solo il passaggio di
    consegne, mai un nome proprio (coerente con come sono già scritte:
    maschere, volti nascosti)."""
    events = []
    for npc in INSTITUTIONAL_NPCS:
        if not _roll_chance(elapsed_minutes, INSTITUTIONAL_EVENT_CHANCE_PER_DAY):
            continue
        text = INSTITUTIONAL_SUCCESSION_TEXTS.get(npc["id"])
        if not text:
            continue
        add_world_event(conn, current_world_minutes, npc["name"], text)
        events.append({"armor_name": npc["name"], "entry": text})
    return events


def _tick_world_flavor_events(conn, elapsed_minutes: int, current_world_minutes: int, divinities: list[str]) -> list[dict]:
    """Eventi di mondo puramente narrativi (richiesto in chat: guerre
    tra fazioni che non coinvolgono il giocatore, presagi, fatti che
    non riguardano nessun Cavaliere in particolare) - non muovono
    nessuno stato di gioco, solo Cronaca."""
    events = []
    if not _roll_chance(elapsed_minutes, WORLD_FLAVOR_EVENT_CHANCE_PER_DAY):
        return events
    template = random.choice(WORLD_FLAVOR_EVENTS)
    if "{a}" in template or "{b}" in template:
        if len(divinities) < 2:
            return events
        a, b = random.sample(divinities, 2)
        text = template.format(a=a, b=b)
    else:
        text = template
    add_world_event(conn, current_world_minutes, "Il Mondo", text)
    events.append({"armor_name": "Il Mondo", "entry": text})
    return events


def tick_world_events(conn, elapsed_minutes: int, current_world_minutes: int) -> list[dict]:
    """Simula quello che succede nel mondo condiviso nel tempo appena
    trascorso (richiesto in chat) - PNG comuni, Figure Istituzionali, ed
    eventi di mondo puramente narrativi. Restituisce l'elenco degli
    eventi accaduti in QUESTA chiamata (quasi sempre vuoto), e li
    scrive anche nella Cronaca del Mondo persistente. Chi viene
    sostituito lascia comunque una Cloth abitata subito da un
    successore (fedele al canone: le armature raramente restano
    vacanti a lungo) - il PNG precedente resta come nota in npc_fate e
    come riga della Cronaca. `current_world_minutes`: il punto
    ASSOLUTO dell'orologio del mondo in cui si sta verificando
    l'evento, per la data della Cronaca - diverso da `elapsed_minutes`,
    che è solo la durata trascorsa dal controllo precedente."""
    if elapsed_minutes <= 0:
        return []

    events = []
    rows = conn.execute(
        "SELECT * FROM roster WHERE claimed_by_knight_id IS NULL AND npc_alive = 1"
    ).fetchall()
    for row in rows:
        if not _roll_chance(elapsed_minutes, NPC_EVENT_CHANCE_PER_DAY):
            continue
        fate = resolve_npc_fate()
        new_name = generate_full_name()
        chronicle_entry = f"{row['npc_name']} di {row['armor_name']} {fate} {new_name} ne raccoglie l'eredità."
        conn.execute(
            """UPDATE roster SET npc_name = ?, npc_generation = npc_generation + 1,
               npc_fate = ?, last_world_event_minutes = last_world_event_minutes + ?
               WHERE armor_name = ?""",
            (new_name, f"{row['npc_name']} {fate}", elapsed_minutes, row["armor_name"]),
        )
        add_world_event(conn, current_world_minutes, row["armor_name"], chronicle_entry)
        events.append({
            "armor_name": row["armor_name"],
            "old_name": row["npc_name"],
            "new_name": new_name,
            "fate": fate,
        })

    events.extend(_tick_institutional_events(conn, elapsed_minutes, current_world_minutes))

    divinities = [r["divinity"] for r in conn.execute("SELECT DISTINCT divinity FROM armors").fetchall()]
    events.extend(_tick_world_flavor_events(conn, elapsed_minutes, current_world_minutes, divinities))

    conn.commit()
    return events
