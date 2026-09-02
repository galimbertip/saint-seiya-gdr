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
from core.alignment import random_alignment, ALIGNMENT_FATE_CATEGORY_WEIGHTS
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
# per il destino dei compagni in core.apprentice_fates). Riscritte in
# chat: molte più varianti (con solo 3 capitava di leggere lo stesso
# identico testo su armature diverse nella stessa sessione), più
# romanzate (Saint Seiya "indora la pillola", non fatti nudi e crudi),
# e con cura a non usare mai un aggettivo o un participio che debba
# concordare con il genere del PNG (i nomi generati non portano un
# genere tracciato - "stanco"/"stanca" non si può scegliere a caso).
NPC_FATE_CATEGORIES = {
    # Morte in combattimento - la più rara delle tre categorie.
    "morte": [
        "muore in un duello che nessuno ha visto, e l'armatura resta orfana per un po', in attesa di chi saprà meritarla.",
        "cade in battaglia lontano dal Santuario, e la notizia raggiunge il Sacro Imperio solo molto più tardi, come un sussurro tra i corridoi.",
        "non fa ritorno da una missione mai autorizzata, e nessuno osa chiedere altro.",
        "combatte un'ultima battaglia contro un nemico che nessuno riesce a identificare, e non ne resta altro che il nome.",
        "si spegne lontano da ogni Cosmo amico, e la notizia arriva al Santuario solo molto più tardi.",
    ],
    # Ritiro - la più comune.
    "ritiro": [
        "appende l'armatura al muro di una casa lontana dal Santuario: la guerra senza fine ha eroso ogni voglia di restare.",
        "si congeda dal Sacro Imperio senza clamore, in cerca altrove di una pace che qui non ha mai trovato.",
        "sceglie una vita senza Cosmo da bruciare né nemici da affrontare all'alba, e nessuno osa biasimarla.",
        "posa l'armatura con lo stesso gesto lento di chi ha già dato tutto quello che aveva da dare.",
        "lascia il Santuario per sempre: la stanchezza di contare le vittorie invece dei giorni vissuti in pace ha vinto su tutto il resto.",
        "si ritira senza una parola di troppo - chi resta capisce comunque, senza bisogno di spiegazioni.",
    ],
    # Sparizione - a metà tra le due.
    "sparizione": [
        "sparisce una notte senza lasciare traccia, lasciando solo domande dietro di sé.",
        "scompare nel nulla, come se il Sacro Imperio stesso ne avesse perso ogni memoria.",
        "esce per una pattuglia di routine e non fa più ritorno - c'è chi parla di fuga, chi teme di peggio.",
        "svanisce durante un lungo viaggio verso confini che nessuno ha mai osato attraversare.",
    ],
}
# Il peso di base di ciascuna categoria (somma delle vecchie liste
# piatte: 5×0.05, 6×~0.085, 4×0.0625) - moltiplicato poi per
# ALIGNMENT_FATE_CATEGORY_WEIGHTS (richiesto in chat, effetti più
# ampi) in base al vero allineamento del PNG.
NPC_FATE_CATEGORY_BASE_WEIGHTS = {"morte": 0.25, "ritiro": 0.50, "sparizione": 0.25}

# Il tempo che serve a un nuovo aspirante per essere pronto a
# raccogliere un'armatura lasciata libera (richiesto in chat: "sarebbe
# meglio dire che comincia l'addestramento", non che diventa Cavaliere
# di colpo) - stesso ordine di grandezza dell'apprendistato del
# giocatore. PLACEHOLDER, da tarare insieme se serve.
NPC_TRAINING_DURATION_MINUTES = 120 * WORLD_TICK_MINUTES_PER_DAY

# Le ferite come stato intermedio (richiesto in chat: "il Cavaliere
# della Fiamma viene attaccato da uno Specter, perde, riporta ferite -
# magari dopo un po' muore per le ferite") - una parte degli eventi
# "notevoli" di un PNG occupato, invece di andare dritti a un destino
# finale, lo lascia FERITO ma ancora al proprio posto: il vero rischio
# arriva nei giorni successivi, non subito. PLACEHOLDER, come le altre
# probabilità di questo modulo.
NPC_INJURY_CHANCE_SHARE = 0.35  # quota degli eventi "notevoli" che diventa un ferimento invece di un destino diretto
NPC_INJURY_RECOVERY_CHANCE_PER_DAY = 0.02  # una volta ferito, buona probabilità di guarire col tempo
NPC_INJURY_DEATH_CHANCE_PER_DAY = 0.006    # ma anche un rischio vero di non farcela

# (testo, etichetta) - l'etichetta viene riusata nel testo di morte
# per le ferite, se le cose vanno male più avanti.
NPC_INJURY_CAUSES = [
    ("viene attaccato da uno Specter durante una pattuglia isolata, e ne esce ferito.", "quell'attacco"),
    ("perde un duello non richiesto contro un rivale mai identificato, riportando ferite serie.", "quel duello"),
    ("si fa male in un incidente durante l'addestramento - niente di scenico, solo sfortuna.", "quell'incidente"),
    ("torna da una missione con ferite che tarderanno a guarire.", "quella missione"),
    ("viene colto di sorpresa da un'imboscata ai confini del proprio territorio.", "quell'imboscata"),
]

NPC_INJURY_DEATH_TEXTS = [
    "non si riprende mai del tutto dalle ferite di {cause_label}, e alla fine cede.",
    "si spegne per le conseguenze di {cause_label}, lontano dai riflettori che raramente si accendono per i Cavalieri comuni.",
    "perde la propria battaglia più silenziosa - quella contro le ferite di {cause_label} - senza che quasi nessuno se ne accorga.",
]

NPC_INJURY_RECOVERY_TEXTS = [
    "si rimette in piedi, più lentamente di quanto avrebbe voluto, ma si rimette.",
    "torna al proprio posto, con qualche cicatrice in più e la stessa determinazione di sempre.",
    "guarisce dalle proprie ferite - il tempo, per una volta, gioca a favore.",
]


# Chi inizia l'addestramento per un'armatura lasciata libera (richiesto
# in chat) - una riga di Cronaca a parte da quella della partenza, non
# più un'unica frase con "X se ne va, Y raccoglie l'eredità" che dava
# l'idea di un passaggio di consegne istantaneo.
NPC_TRAINING_START_TEXTS = [
    "{name} si presenta al Santuario chiedendo di essere addestrato per raccogliere l'armatura {armor}, rimasta senza custode.",
    "Si dice che {name} abbia già cominciato ad allenarsi per meritare l'armatura {armor} - il nome, per ora, è solo una voce tra le tante.",
    "{name} inizia il proprio addestramento, sognando di diventare il nuovo portatore dell'armatura {armor}.",
    "Un nuovo aspirante, {name}, muove i primi passi verso l'armatura {armor} - la strada da percorrere è ancora lunga.",
]

# Chi completa l'addestramento e diventa davvero il nuovo Cavaliere
# (richiesto in chat) - solo ORA, non subito dopo la partenza del
# predecessore.
NPC_GRADUATION_TEXTS = [
    "{name} supera la propria prova e diventa il nuovo Cavaliere dell'armatura {armor}.",
    "Dopo mesi di addestramento, {name} è finalmente pronto a indossare l'armatura {armor}.",
    "L'armatura {armor} ha un nuovo portatore: {name} ha guadagnato il diritto di indossarla.",
    "{name} conclude il proprio addestramento e prende il posto che spettava all'armatura {armor}.",
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


def resolve_npc_fate(alignment: str = "") -> str:
    """Un destino narrativo per UN PNG che lascia il proprio posto
    (richiesto in chat) - stesso principio di
    core.apprentice_fates.resolve_companion_fate, qui applicato ai PNG
    del mondo invece che ai compagni d'addestramento. `alignment`
    (richiesto in chat, effetti più ampi): il vero allineamento del
    PNG pesa quale CATEGORIA di destino è più probabile (un Malvagio
    più incline a una fine violenta o a sparire in circostanze losche,
    un Buono più incline a un ritiro pacifico) - la scelta della frase
    specifica dentro la categoria resta uniforme."""
    multipliers = ALIGNMENT_FATE_CATEGORY_WEIGHTS.get(alignment, (1.0, 1.0, 1.0))
    categories = list(NPC_FATE_CATEGORY_BASE_WEIGHTS.keys())  # ["morte", "ritiro", "sparizione"], stesso ordine dei moltiplicatori
    weighted = [NPC_FATE_CATEGORY_BASE_WEIGHTS[cat] * mult for cat, mult in zip(categories, multipliers)]
    category = random.choices(categories, weights=weighted, k=1)[0]
    return random.choice(NPC_FATE_CATEGORIES[category])


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


def _start_departure(conn, row, fate_text: str, current_world_minutes: int) -> list[dict]:
    """La sequenza condivisa 'qualcuno lascia il proprio posto, un
    aspirante inizia l'addestramento' - usata sia da una partenza
    diretta sia da una morte per ferite (richiesto in chat), per non
    duplicare la stessa logica due volte."""
    events = []
    departure_entry = f"{row['npc_name']} di {row['armor_name']} {fate_text}"
    add_world_event(conn, current_world_minutes, row["armor_name"], departure_entry)

    candidate = generate_full_name()
    training_ready = current_world_minutes + NPC_TRAINING_DURATION_MINUTES
    start_text = random.choice(NPC_TRAINING_START_TEXTS).format(name=candidate, armor=row["armor_name"])
    add_world_event(conn, current_world_minutes, row["armor_name"], start_text)

    conn.execute(
        """UPDATE roster SET npc_status = 'training', npc_training_candidate = ?,
           npc_training_ready_minutes = ?, npc_fate = ?, npc_injured = 0, npc_injury_cause = '',
           last_world_event_minutes = ?
           WHERE armor_name = ?""",
        (candidate, training_ready, f"{row['npc_name']} {fate_text}", current_world_minutes, row["armor_name"]),
    )
    events.append({"armor_name": row["armor_name"], "entry": departure_entry})
    events.append({"armor_name": row["armor_name"], "entry": start_text})
    return events


def _tick_injured_npcs(conn, elapsed_minutes: int, current_world_minutes: int) -> list[dict]:
    """Chi è già ferito (richiesto in chat) rischia ad ogni controllo di
    guarire, di peggiorare fino a morirne, o semplicemente di restare
    ferito com'è - non tutto si risolve nello stesso tick in cui è
    successo."""
    events = []
    rows = conn.execute(
        "SELECT * FROM roster WHERE claimed_by_knight_id IS NULL AND npc_status = 'occupied' AND npc_injured = 1"
    ).fetchall()
    for row in rows:
        if _roll_chance(elapsed_minutes, NPC_INJURY_DEATH_CHANCE_PER_DAY):
            death_text = random.choice(NPC_INJURY_DEATH_TEXTS).format(cause_label=row["npc_injury_cause"])
            events.extend(_start_departure(conn, row, death_text, current_world_minutes))
        elif _roll_chance(elapsed_minutes, NPC_INJURY_RECOVERY_CHANCE_PER_DAY):
            recovery_text = random.choice(NPC_INJURY_RECOVERY_TEXTS)
            entry = f"{row['npc_name']} di {row['armor_name']} {recovery_text}"
            conn.execute(
                "UPDATE roster SET npc_injured = 0, npc_injury_cause = '' WHERE armor_name = ?",
                (row["armor_name"],),
            )
            add_world_event(conn, current_world_minutes, row["armor_name"], entry)
            events.append({"armor_name": row["armor_name"], "entry": entry})
    return events


def _tick_common_npc_departures(conn, elapsed_minutes: int, current_world_minutes: int) -> list[dict]:
    """Fase 1 (richiesto in chat): un PNG occupato e SANO ha un evento
    notevole - una parte diretta subito (come prima), una parte esce
    invece ferito e resta al proprio posto (vedi _tick_injured_npcs per
    cosa gli succede nei giorni seguenti). L'armatura, quando si
    libera, non passa subito a un nuovo occupante - un aspirante
    inizia SOLO ORA il proprio addestramento (vedi
    _tick_common_npc_graduations per quando lo completa davvero)."""
    events = []
    rows = conn.execute(
        "SELECT * FROM roster WHERE claimed_by_knight_id IS NULL AND npc_alive = 1 "
        "AND npc_status = 'occupied' AND npc_injured = 0"
    ).fetchall()
    for row in rows:
        if not _roll_chance(elapsed_minutes, NPC_EVENT_CHANCE_PER_DAY):
            continue
        if random.random() < NPC_INJURY_CHANCE_SHARE:
            cause_text, cause_label = random.choice(NPC_INJURY_CAUSES)
            entry = f"{row['npc_name']} di {row['armor_name']} {cause_text}"
            conn.execute(
                "UPDATE roster SET npc_injured = 1, npc_injury_cause = ? WHERE armor_name = ?",
                (cause_label, row["armor_name"]),
            )
            add_world_event(conn, current_world_minutes, row["armor_name"], entry)
            events.append({"armor_name": row["armor_name"], "entry": entry})
        else:
            fate = resolve_npc_fate(row["npc_alignment"])
            events.extend(_start_departure(conn, row, fate, current_world_minutes))
    return events


def _tick_common_npc_graduations(conn, current_world_minutes: int) -> list[dict]:
    """Fase 2 (richiesto in chat): un aspirante che ha completato il
    proprio addestramento diventa finalmente il nuovo occupante -
    niente più passaggio di consegne istantaneo tra chi parte e chi
    arriva."""
    events = []
    rows = conn.execute(
        "SELECT * FROM roster WHERE claimed_by_knight_id IS NULL AND npc_status = 'training' "
        "AND npc_training_ready_minutes <= ?",
        (current_world_minutes,),
    ).fetchall()
    for row in rows:
        graduation_text = random.choice(NPC_GRADUATION_TEXTS).format(
            name=row["npc_training_candidate"], armor=row["armor_name"]
        )
        add_world_event(conn, current_world_minutes, row["armor_name"], graduation_text)
        conn.execute(
            """UPDATE roster SET npc_name = ?, npc_status = 'occupied', npc_generation = npc_generation + 1,
               npc_training_candidate = '', npc_training_ready_minutes = 0, npc_alignment = ?
               WHERE armor_name = ?""",
            (row["npc_training_candidate"], random_alignment(), row["armor_name"]),
        )
        events.append({"armor_name": row["armor_name"], "entry": graduation_text})
    return events


def tick_world_events(conn, elapsed_minutes: int, current_world_minutes: int) -> list[dict]:
    """Simula quello che succede nel mondo condiviso nel tempo appena
    trascorso (richiesto in chat) - PNG comuni, Figure Istituzionali, ed
    eventi di mondo puramente narrativi. Restituisce l'elenco degli
    eventi accaduti in QUESTA chiamata (quasi sempre vuoto), e li
    scrive anche nella Cronaca del Mondo persistente. Un'armatura
    lasciata libera NON passa subito a un nuovo occupante (richiesto in
    chat: prima sembrava un passaggio di consegne istantaneo) - un
    aspirante inizia l'addestramento, e solo dopo un tempo realistico
    (vedi NPC_TRAINING_DURATION_MINUTES) diventa il nuovo Cavaliere.
    `current_world_minutes`: il punto ASSOLUTO dell'orologio del mondo
    in cui si sta verificando l'evento, per la data della Cronaca -
    diverso da `elapsed_minutes`, che è solo la durata trascorsa dal
    controllo precedente."""
    if elapsed_minutes <= 0:
        return []

    events = []
    events.extend(_tick_injured_npcs(conn, elapsed_minutes, current_world_minutes))
    events.extend(_tick_common_npc_departures(conn, elapsed_minutes, current_world_minutes))
    events.extend(_tick_common_npc_graduations(conn, current_world_minutes))
    events.extend(_tick_institutional_events(conn, elapsed_minutes, current_world_minutes))

    divinities = [r["divinity"] for r in conn.execute("SELECT DISTINCT divinity FROM armors").fetchall()]
    events.extend(_tick_world_flavor_events(conn, elapsed_minutes, current_world_minutes, divinities))

    conn.commit()
    return events
