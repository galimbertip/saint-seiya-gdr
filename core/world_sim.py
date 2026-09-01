"""Il mondo che vive per conto suo (richiesto in chat) - i PNG del
roster (quelli NON reclamati da un personaggio giocatore) possono
morire, ritirarsi, o essere sostituiti col passare del tempo
condiviso, indipendentemente dal giocatore - proprio come in Football
Manager le altre squadre giocano le proprie partite mentre tu giochi
la tua.

Una simulazione leggera e probabilistica, non un motore narrativo
completo: bassa probabilità per singolo PNG, per sentirsi vivo nel
tempo senza essere caotico o richiedere una vera IA per ciascuno.
Chiamata da core.fm_manager.RosterManager.spend_time ogni volta che il
tempo avanza abbastanza (un giorno pieno) da giustificare il
ricalcolo - richiamarla ad ogni minuscolo avanzamento (es. un mezzo
round di combattimento) sarebbe inutilmente costoso."""

import random

from core.arena_manager import generate_full_name
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

# Per lo più un ritiro o una sparizione; la morte vera in duello resta
# minoritaria, non l'esito predefinito (stesso principio già seguito
# per il destino dei compagni in core.apprentice_fates).
NPC_FATE_OPTIONS = [
    ("muore in un duello mai raccontato, e l'armatura resta orfana per un po' prima che qualcuno la raccolga.", 0.3),
    ("si ritira dalla vita da Cavaliere, stanco di una guerra che sembra non finire mai.", 0.4),
    ("sparisce senza lasciare traccia - c'è chi dice sia fuggito, chi dice di peggio.", 0.3),
]


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


def tick_world_events(conn, elapsed_minutes: int, current_world_minutes: int) -> list[dict]:
    """Simula quello che succede ai PNG non reclamati nel tempo
    condiviso appena trascorso (richiesto in chat) - restituisce
    l'elenco degli eventi accaduti in QUESTA chiamata (quasi sempre
    vuoto), e li scrive anche nella Cronaca del Mondo persistente
    (richiesto in chat: prima venivano solo restituiti al volo, senza
    lasciare traccia consultabile in seguito). Chi viene sostituito
    lascia comunque una Cloth abitata subito da un successore (fedele
    al canone: le armature raramente restano vacanti a lungo) - il PNG
    precedente resta come nota in npc_fate e come riga della Cronaca.
    `current_world_minutes`: il punto ASSOLUTO dell'orologio del mondo
    in cui si sta verificando l'evento, per la data della Cronaca -
    diverso da `elapsed_minutes`, che è solo la durata trascorsa dal
    controllo precedente."""
    if elapsed_minutes <= 0:
        return []
    days = elapsed_minutes / WORLD_TICK_MINUTES_PER_DAY
    # Probabilità cumulata sull'intero periodo trascorso in un colpo
    # solo, non un tiro al giorno per ogni giorno - un'approssimazione
    # ragionevole per probabilità così basse, molto più efficiente con
    # periodi lunghi (es. un salto di più settimane).
    chance = 1 - (1 - NPC_EVENT_CHANCE_PER_DAY) ** days

    events = []
    rows = conn.execute(
        "SELECT * FROM roster WHERE claimed_by_knight_id IS NULL AND npc_alive = 1"
    ).fetchall()
    for row in rows:
        if random.random() >= chance:
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
    conn.commit()
    return events
