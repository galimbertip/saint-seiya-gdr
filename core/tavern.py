"""La Taverna (richiesto in chat, in origine chiamata impropriamente
"bacheca") - uno spazio dove parlare liberamente con qualunque PNG del
roster, costruendo un rapporto nel tempo. A costo zero (richiesto
esplicitamente in chat): nessuna vera IA dietro, un riconoscimento a
parole chiave che sceglie la risposta più adatta da un pool ampio,
filtrato per il vero allineamento del PNG (mai mostrato, come sempre)
- non capisce davvero quello che scrivi, ma dà un'illusione di
conversazione senza costare nulla. Se non riconosce nessuna parola
chiave, chiede di ripetere con una frase in stile Saint Seiya
(richiesto in chat), non un freddo messaggio d'errore."""

import random

from core.alignment import ALIGNMENTS, random_alignment
from core.arena_manager import generate_full_name
from database.db_manager import (
    get_tavern_bartender, insert_tavern_bartender, get_tavern_seating, set_tavern_seating,
    remove_tavern_seating, get_tavern_last_reshuffle, set_tavern_last_reshuffle,
)

# Ogni allineamento si riduce a uno di tre "umori" per le risposte
# della Taverna (richiesto in chat) - scrivere un pool per ciascuno
# dei 9 allineamenti per ognuno dei 7 intenti sarebbe stato 63 pool da
# scrivere; 3 umori × 7 intenti (21 pool) restano gestibili senza
# perdere la sostanza (un PNG Buono resta accogliente sia che sia
# Legale, Neutrale o Caotico - la sfumatura fine tra i tre resta per
# la persuasione/il combattimento/i destini, dove conta di più).
ALIGNMENT_TO_MOOD = {
    "Legale Buono": "buono", "Neutrale Buono": "buono", "Caotico Buono": "buono",
    "Legale Neutrale": "neutrale", "Neutrale Puro": "neutrale", "Caotico Neutrale": "neutrale",
    "Legale Malvagio": "malvagio", "Neutrale Malvagio": "malvagio", "Caotico Malvagio": "malvagio",
}
MOODS = ("buono", "neutrale", "malvagio")

# Le Taverne separate per regno (richiesto in chat: non un'unica
# Taverna, ma una distinta per ciascuna delle 13 divinità/fazioni del
# catalogo) - se entri in quella di una fazione rivale della tua, i
# PNG partono diffidenti o ostili, non neutrali come in casa propria.
# Coppie non elencate = relazione neutrale di default. Le relazioni
# valgono in entrambi i sensi (Atena-Ade è ostile sia per chi porta
# Atena sia per chi porta Ade).
FACTION_RELATIONS = {
    frozenset({"Athena", "Hades"}): "ostile",
    frozenset({"Athena", "Black Saint"}): "ostile",
    frozenset({"Athena", "Ares"}): "ostile",
    frozenset({"Athena", "Saturno"}): "ostile",
    frozenset({"Athena", "Crono"}): "ostile",
    frozenset({"Athena", "Eris"}): "ostile",
    frozenset({"Athena", "Lucifero"}): "ostile",
    frozenset({"Athena", "Odino"}): "diffidente",
    frozenset({"Athena", "Nettuno"}): "diffidente",
    frozenset({"Athena", "Apollo"}): "diffidente",
    frozenset({"Athena", "Artemide"}): "diffidente",
    frozenset({"Athena", "Zeus"}): "diffidente",
}

# L'affinità di partenza (richiesto in chat: "sicuramente inizialmente
# c'è diffidenza") e i moltiplicatori che rendono la fiducia lenta da
# guadagnare ma facile da perdere con una fazione ostile - "1+1+1+1+1
# può fare 2 o 0" (richiesto in chat): i gesti positivi contano meno
# del solito, quelli negativi contano di più, non è una semplice somma
# lineare uguale per tutti.
RELATION_STARTING_AFFINITY = {"alleata": 3, "neutrale": 0, "diffidente": -5, "ostile": -12}
RELATION_POSITIVE_MULTIPLIER = {"alleata": 1.2, "neutrale": 1.0, "diffidente": 0.6, "ostile": 0.3}
RELATION_NEGATIVE_MULTIPLIER = {"alleata": 0.8, "neutrale": 1.0, "diffidente": 1.3, "ostile": 1.8}

# Ogni Taverna, con il proprio nome in tema (richiesto in chat, 13
# taverne separate) - la chiave è la divinità/fazione così come
# compare in armors.divinity.
TAVERN_REALMS = {
    "Athena": "La Locanda del Santuario",
    "Hades": "La Taverna degli Inferi",
    "Black Saint": "Il Rifugio dei Reietti",
    "Odino": "La Sala di Valhalla",
    "Nettuno": "La Taverna delle Colonne",
    "Apollo": "Il Tempio del Sole",
    "Ares": "L'Accampamento di Marte",
    "Saturno": "Le Rovine di Saturno",
    "Crono": "Il Tempio del Tempo",
    "Eris": "Il Crocevia della Discordia",
    "Lucifero": "L'Ombra di Lucifero",
    "Artemide": "Il Bosco di Artemide",
    "Zeus": "La Sala del Tuono",
}

# Il reclutamento per missione (richiesto in chat): un PNG di questo
# regno può offrirti la missione collegata, ma solo dopo aver costruito
# un minimo di fiducia - PROATTIVAMENTE lui, non solo se gliela chiedi
# tu esplicitamente.
REALM_MISSION_OFFERS = {
    "Athena": "dodici_case",
    "Nettuno": "colonne_sette_mari",
    "Odino": "gelo_di_valhalla",
}
MISSION_OFFER_AFFINITY_THRESHOLD = 10


def get_faction_relation(player_divinity: str, npc_divinity: str) -> str:
    """La relazione tra la fazione del personaggio e quella del PNG
    (richiesto in chat) - alleata se è la STESSA fazione (casa
    propria), altrimenti dal registro FACTION_RELATIONS, neutrale se
    la coppia non è elencata."""
    if player_divinity == npc_divinity:
        return "alleata"
    key = frozenset({player_divinity, npc_divinity})
    return FACTION_RELATIONS.get(key, "neutrale")




def alignment_to_mood(alignment: str) -> str:
    return ALIGNMENT_TO_MOOD.get(alignment, "neutrale")


# (parole chiave, nome intento) - controllate in quest'ordine, la
# prima che trova una corrispondenza vince. I saluti sono controllati
# per primi apposta: messaggi brevi come "ciao" non devono finire
# scambiati per una domanda generica.
INTENT_KEYWORDS = [
    ("saluto_finale", ["addio", "arrivederci", "devo andare", "ci vediamo", "alla prossima", "vado via"]),
    ("saluto", ["ciao", "salve", "salut", "buongiorno", "buonasera", "buondì", "ehi"]),
    ("ordina_da_bere", ["da bere", "un drink", "una birra", "del vino", "qualcosa da bere", "sete", "ordinare", "offro io", "il tuo migliore", "portami"]),
    ("complimento", ["bravo", "brava", "forte", "fortissimo", "fortissima", "ammirevole", "rispetto", "complimenti", "impressionante", "grande", "eccezionale"]),
    ("insulto", ["stupido", "stupida", "idiota", "vigliacco", "vigliacca", "patetico", "patetica", "odio", "disprezzo", "inutile"]),
    ("sfida", ["sfida", "sfidare", "combatt", "duello", "battersi", "battiamoci", "debole", "paura", "coraggio"]),
    ("domanda_su_mondo", ["novità", "notizie", "cosa succede", "missione", "missioni", "santuario", "cosa sai", "cosa ne pensi"]),
    ("domanda_su_di_te", ["chi sei", "parlami di te", "la tua storia", "cosa fai", "di dove vieni", "il tuo nome", "raccontami", "come stai"]),
]

AFFINITY_DELTA = {
    "saluto": 1, "saluto_finale": 0, "domanda_su_di_te": 1, "domanda_su_mondo": 0,
    "complimento": 2, "sfida": 0, "insulto": -3, "ordina_da_bere": 1,
}

TAVERN_RESPONSES = {
    "saluto": {
        "buono": [
            "\"Ben trovato\", dice con un sorriso sincero. \"Siediti pure, se vuoi.\"",
            "Annuisce con calore. \"Che il tuo Cosmo arda tranquillo, oggi.\"",
        ],
        "neutrale": [
            "Annuisce appena, senza troppo entusiasmo ma senza freddezza.",
            "\"Salve\", risponde, tornando quasi subito a quello che stava facendo.",
        ],
        "malvagio": [
            "Ti osserva un istante di troppo prima di rispondere, come se ti stesse già valutando.",
            "\"Guarda chi si vede\", dice, con un tono che non promette nulla di caldo.",
        ],
    },
    "saluto_finale": {
        "buono": [
            "\"Vai tranquillo. Che la strada sia gentile con te.\"",
            "Ti saluta con la mano, davvero dispiaciuto di vederti andare.",
        ],
        "neutrale": [
            "Un cenno del capo, niente di più.",
            "\"D'accordo\", dice, senza troppa enfasi.",
        ],
        "malvagio": [
            "\"Vai pure\", dice, con un sorriso che non arriva agli occhi.",
            "Non risponde subito - solo un lungo sguardo, poi si volta altrove.",
        ],
    },
    "complimento": {
        "buono": [
            "Arrossisce leggermente. \"Sei gentile, ma non ho fatto nulla di speciale.\"",
            "\"Detto da te, conta doppio\", dice, visibilmente commosso.",
        ],
        "neutrale": [
            "\"Fai bene a notarlo\", risponde, con un'alzata di spalle quasi divertita.",
            "Annuisce, come se stesse solo confermando un fatto ovvio.",
        ],
        "malvagio": [
            "\"Lo so già\", dice, con un sorriso compiaciuto che non nasconde nulla.",
            "\"Continua pure\", dice, godendosela apertamente.",
        ],
    },
    "sfida": {
        "buono": [
            "\"Un duello onesto non si rifiuta mai - ma spero tu sia venuto in pace, oggi.\"",
            "Sorride, quasi divertito. \"Un'altra volta, magari - oggi preferisco parlare.\"",
        ],
        "neutrale": [
            "\"Se proprio insisti\", dice, valutandoti con un certo distacco.",
            "Scrolla le spalle. \"Non oggi. Non ho nulla da dimostrarti.\"",
        ],
        "malvagio": [
            "Ride, un suono che non promette nulla di buono. \"Sei sicuro di volerlo, davvero?\"",
            "\"Se cerchi guai\", dice piano, \"li troverai. Ma non qui, non ora.\"",
        ],
    },
    "insulto": {
        "buono": [
            "Il suo sguardo si incrina, ferito più che arrabbiato. \"Non mi aspettavo questo, da te.\"",
            "\"Se hai bisogno di sfogarti, va bene\", dice, con pazienza che sembra costargli fatica.",
        ],
        "neutrale": [
            "Ti guarda con un'indifferenza che pesa più di una risposta.",
            "\"Parole\", dice, e torna a quello che stava facendo.",
        ],
        "malvagio": [
            "Sorride, come se le tue parole gli facessero solo piacere. \"Interessante, da parte tua.\"",
            "\"Ricorderò questo\", dice, con un tono che è più una minaccia che una promessa.",
        ],
    },
    "domanda_su_mondo": {
        "buono": [
            "\"Le cose vanno come vanno sempre - tra momenti di pace e tempeste all'orizzonte.\"",
            "\"Spero solo che tutti tornino a casa sani, alla fine di tutto questo.\"",
        ],
        "neutrale": [
            "\"Non saprei dirti più di quello che sai già tu.\"",
            "\"Le cose cambiano di continuo, da queste parti. Non seguo più tutto quanto.\"",
        ],
        "malvagio": [
            "\"Perché dovrei condividere quello che so, con te?\" dice, ma con un sorriso che lascia intendere che forse lo farà.",
            "\"Il mondo va avanti, con o senza il tuo interessamento\", risponde, quasi annoiato.",
        ],
    },
    "ordina_da_bere": {
        "buono": [
            "Sorride e ti versa qualcosa di caldo, senza nemmeno chiedere cosa preferisci. \"Questo va bene per iniziare.\"",
            "\"Alla tua salute\", dice, alzando il proprio bicchiere insieme al tuo.",
        ],
        "neutrale": [
            "Ti versa qualcosa senza troppi complimenti, e torna a badare al resto del bancone.",
            "\"Subito\", dice, con l'efficienza di chi lo fa cento volte al giorno.",
        ],
        "malvagio": [
            "Ti versa qualcosa con un sorriso che non sai bene come interpretare. \"Offre la casa - stavolta.\"",
            "\"Paghi prima\", dice, secco, prima di versarti qualcosa.",
        ],
    },
    "domanda_su_di_te": {
        "buono": [
            "\"Non c'è molto da raccontare - solo un lungo cammino, come quello di chiunque altro qui.\"",
            "Sorride, quasi timidamente. \"Preferirei ascoltare la tua, di storia, se non ti dispiace.\"",
        ],
        "neutrale": [
            "\"Faccio quello che devo fare. Non c'è molto altro da dire.\"",
            "Ti guarda, valutando se vale la pena raccontarti qualcosa di vero.",
        ],
        "malvagio": [
            "\"Non è affar tuo\", dice, secco, prima di aggiungere: \"ma forse, un giorno, lo sarà.\"",
            "Un sorriso enigmatico. \"Preferisco restare un mistero, se non ti dispiace.\"",
        ],
    },
}

# Se nessuna parola chiave trova corrispondenza (richiesto in chat: "in
# modo da Saint Seiya" di chiedere di ripetere) - drammatico, mai un
# freddo messaggio d'errore.
MISUNDERSTOOD_RESPONSES = [
    "Il tuo Cosmo non è riuscito a farsi comprendere fino in fondo - ripeti, se hai davvero qualcosa da dire.",
    "Le tue parole si perdono nel vento come foglie cadute. Prova ancora, con più chiarezza.",
    "\"Non colgo il senso di quello che dici\", ammette. \"Il Sacro Imperio non ha tempo per gli equivoci - riprova.\"",
    "Ti guarda, confuso. \"Le tue parole arrivano spezzate, come un'eco lontana - dimmelo di nuovo.\"",
    "Un silenzio breve, poi: \"Perdonami, ma non ho colto il senso. Puoi ripetere?\"",
]


def detect_intent(text: str) -> str | None:
    """Il primo intento le cui parole chiave compaiono nel testo
    (richiesto in chat) - None se nessuna corrisponde, nel qual caso
    la Taverna chiede di ripetere."""
    lowered = text.lower()
    for intent, keywords in INTENT_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return intent
    return None


def resolve_tavern_response(text: str, alignment: str, relation: str = "neutrale",
                             forced_intent: str | None = None, tone: str = "neutro") -> tuple[str, int]:
    """Risolve un messaggio del giocatore verso un PNG - restituisce
    (risposta, variazione di affinità). Se non riconosce nessun
    intento, la variazione è 0 e la risposta chiede di ripetere.
    `relation` (richiesto in chat): la relazione tra la fazione del
    personaggio e quella del PNG - con una fazione ostile, i gesti
    positivi contano meno del solito e quelli negativi contano di più
    (fiducia lenta da guadagnare, facile da perdere). `forced_intent`
    (richiesto in chat, pulsanti in stile Football Manager): quando il
    giocatore sceglie un tono da un pulsante invece di scrivere
    liberamente, l'intento è già certo - salta il riconoscimento a
    parole chiave, comprensione garantita al 100%. `tone` (richiesto
    in chat, stessa idea ma per COME lo dici invece che COSA dici, es.
    "Sorriso caloroso" vs "Sguardo freddo") - amplifica o smorza
    l'effetto sull'affinità in entrambe le direzioni."""
    intent = forced_intent if forced_intent in TAVERN_RESPONSES else detect_intent(text)
    if intent is None:
        return random.choice(MISUNDERSTOOD_RESPONSES), 0
    mood = alignment_to_mood(alignment)
    response = random.choice(TAVERN_RESPONSES[intent][mood])
    base_delta = AFFINITY_DELTA.get(intent, 0)
    if base_delta > 0:
        delta = round(base_delta * RELATION_POSITIVE_MULTIPLIER.get(relation, 1.0))
    elif base_delta < 0:
        delta = round(base_delta * RELATION_NEGATIVE_MULTIPLIER.get(relation, 1.0))
    else:
        delta = 0
    delta = round(delta * TAVERN_TONE_MULTIPLIERS.get(tone, 1.0))
    return response, delta


# I pulsanti in stile Football Manager (richiesto in chat: come le
# conferenze stampa) - un tono scelto da un pulsante garantisce la
# comprensione, niente più "non ho capito" quando il giocatore sa già
# cosa vuole dire. Il testo di esempio compare nella cronologia al
# posto di quello scritto a mano, dato che con un pulsante non c'è
# nulla da scrivere.
TAVERN_QUICK_INTENTS = [
    ("saluto", "👋 Saluta", "Ciao."),
    ("complimento", "🎩 Fai un complimento", "Sei davvero notevole, complimenti."),
    ("domanda_su_di_te", "🗣️ Chiedi di lui/lei", "Parlami un po' di te."),
    ("domanda_su_mondo", "❓ Chiedi novità", "Ci sono novità, da queste parti?"),
    ("ordina_da_bere", "🍺 Ordina da bere", "Portami qualcosa da bere."),
    ("sfida", "⚔️ Lancia una sfida", "Che ne dici di uno scontro, prima o poi?"),
    ("insulto", "😠 Insulta", "Non mi sembri poi così temibile."),
    ("saluto_finale", "🚪 Congedati", "Devo andare. Ci vediamo."),
]

# Il TONO con cui dici le cose (richiesto in chat, in stile Football
# Manager - non "cosa dici", ma "come lo dici") - un asse separato
# dall'intento: lo stesso complimento, fatto con un sorriso caloroso
# o a braccia conserte, non pesa allo stesso modo. Si applica sia ai
# pulsanti sopra sia al testo libero. "neutro" è il default se il
# giocatore non ne sceglie uno diverso - nessun effetto, come non
# scegliere reazione in una conferenza stampa.
TAVERN_TONES = [
    ("neutro", "Nessuna reazione", 1.0),
    ("caloroso", "😊 Sorriso caloroso", 1.4),
    ("aperto", "🤗 Braccia aperte", 1.15),
    ("deciso", "💪 Tono deciso", 1.0),
    ("freddo", "🥶 Sguardo freddo", 0.5),
]
TAVERN_TONE_MULTIPLIERS = {key: mult for key, _label, mult in TAVERN_TONES}


# Il testo con cui un PNG offre la missione collegata al proprio regno
# (richiesto in chat) - una riga in più, distinta dalla risposta
# normale, quando la fiducia appena costruita supera la soglia.
MISSION_OFFER_TEXTS = [
    "Ti guarda con un'attenzione nuova. \"Mi fido di te, ormai - abbastanza da chiederti un favore, se sei disposto ad ascoltare.\"",
    "\"Forse è il momento giusto\", dice, come se avesse aspettato apposta questa fiducia. \"C'è una cosa di cui potresti occuparti, se te la senti.\"",
    "Abbassa la voce. \"Non lo chiederei a chiunque - ma a te, forse sì. Hai tempo per un incarico?\"",
]


def check_mission_offer(npc_divinity: str, affinity_before: int, affinity_after: int,
                         knight_has_active_mission: bool) -> str | None:
    """Restituisce l'id della missione offerta se QUESTO messaggio ha
    appena fatto superare la soglia di fiducia (richiesto in chat: il
    PNG offre da solo, non solo se richiesto esplicitamente) - None
    altrimenti (nessuna missione collegata a questo regno, il
    personaggio è già impegnato in un'altra missione, o la soglia non
    è stata appena superata)."""
    mission_id = REALM_MISSION_OFFERS.get(npc_divinity)
    if mission_id is None or knight_has_active_mission:
        return None
    if affinity_before < MISSION_OFFER_AFFINITY_THRESHOLD <= affinity_after:
        return mission_id
    return None


# --- La Taverna a mappa (richiesto in chat) --------------------------
# Non più un semplice elenco da cui scegliere un interlocutore: una
# stanza vera, con un bancone e dei tavoli, dove i PNG del regno
# occupano posti che cambiano nel tempo - stessa idea della mappa
# dell'Arena, applicata qui.

TABLE_LAYOUT = {
    0: {"seats": 3, "label": "Bancone"},
    1: {"seats": 4, "label": "Tavolo 1"},
    2: {"seats": 4, "label": "Tavolo 2"},
    3: {"seats": 4, "label": "Tavolo 3"},
    4: {"seats": 4, "label": "Tavolo 4"},
    5: {"seats": 4, "label": "Tavolo 5"},
}
# Quanti PNG "popolano" la taverna in un dato momento - non tutti
# quelli del regno insieme (con Athena sarebbero oltre 80), solo
# un'istantanea plausibile di chi ci si trova in quel momento.
MAX_SEATED_NPCS = 12

# Ogni quanto tempo condiviso la disposizione PUÒ cambiare (richiesto
# in chat: dinamica, non statica) e quanta gente si sposta ad ogni
# rimescolamento - PLACEHOLDER come le altre costanti di ritmo di
# questo progetto.
TAVERN_RESHUFFLE_MINUTES = 240
RESHUFFLE_FRACTION = 0.3

BARTENDER_INTRO_TEXTS = [
    "\"Benvenuto\", dice senza troppa enfasi, pulendo un bicchiere che non ne aveva bisogno.",
    "Ti osserva un istante, poi torna a badare al proprio bancone.",
    "Un cenno del capo, un bicchiere già pronto - il mestiere, prima di tutto.",
]


def ensure_tavern_bartender(conn, divinity: str) -> dict:
    """Il taverniere di questo regno (richiesto in chat) - generato una
    sola volta, resta lo stesso per sempre (a differenza degli
    avventori ai tavoli, che cambiano)."""
    bartender = get_tavern_bartender(conn, divinity)
    if bartender is None:
        name = generate_full_name()
        alignment = random_alignment()
        insert_tavern_bartender(conn, divinity, name, alignment)
        bartender = get_tavern_bartender(conn, divinity)
    return dict(bartender)


def _eligible_npcs_for_realm(conn, divinity: str) -> list[dict]:
    """I PNG di questo regno che potrebbero comparire nella Taverna
    (richiesto in chat) - solo quelli non reclamati da un giocatore."""
    rows = conn.execute(
        "SELECT r.* FROM roster r JOIN armors a ON a.name = r.armor_name "
        "WHERE a.divinity = ? AND r.claimed_by_knight_id IS NULL",
        (divinity,),
    ).fetchall()
    return [dict(r) for r in rows]


def _all_seat_slots() -> list[tuple[int, int]]:
    """Ogni singolo posto a sedere della mappa (tavolo, indice posto),
    bancone escluso - il bancone si riempie a parte, ha una logica
    leggermente diversa (ci si può stare "in piedi" senza un vero
    posto fisso, richiesto in chat implicitamente dal come funziona un
    vero bancone)."""
    slots = []
    for table_number, info in TABLE_LAYOUT.items():
        if table_number == 0:
            continue
        for seat_index in range(info["seats"]):
            slots.append((table_number, seat_index))
    return slots


def ensure_tavern_seating(conn, divinity: str, world_minutes: int) -> None:
    """La prima volta che qualcuno entra in questa Taverna (richiesto
    in chat), genera una disposizione iniziale - un sottoinsieme
    plausibile dei PNG del regno, sparsi tra i tavoli."""
    existing = get_tavern_seating(conn, divinity)
    if existing:
        return
    candidates = _eligible_npcs_for_realm(conn, divinity)
    if not candidates:
        return
    random.shuffle(candidates)
    slots = _all_seat_slots()
    random.shuffle(slots)
    chosen = candidates[:MAX_SEATED_NPCS]
    for npc, (table_number, seat_index) in zip(chosen, slots):
        set_tavern_seating(conn, divinity, npc["armor_name"], table_number, seat_index)
    conn.commit()
    set_tavern_last_reshuffle(conn, divinity, world_minutes)


def maybe_reshuffle_tavern(conn, divinity: str, world_minutes: int) -> None:
    """La disposizione cambia nel tempo (richiesto in chat: "dinamica,
    la gente si alza, si siede, cambia tavolo") - controllo economico
    (stesso principio già usato per gli eventi del mondo): solo se è
    passato abbastanza tempo condiviso dall'ultimo rimescolamento per
    questo regno."""
    last = get_tavern_last_reshuffle(conn, divinity)
    if world_minutes - last < TAVERN_RESHUFFLE_MINUTES:
        return

    current = get_tavern_seating(conn, divinity)
    occupied_armor_names = {row["armor_name"] for row in current}
    occupied_slots = {(row["table_number"], row["seat_index"]) for row in current}

    # Una quota di chi è seduto se ne va (torna "in giro" per il
    # regno, non più visibile in Taverna finché non ricapita).
    n_to_remove = max(1, round(len(current) * RESHUFFLE_FRACTION))
    to_remove = random.sample(list(current), min(n_to_remove, len(current)))
    for row in to_remove:
        remove_tavern_seating(conn, divinity, row["armor_name"])
        occupied_armor_names.discard(row["armor_name"])
        occupied_slots.discard((row["table_number"], row["seat_index"]))

    # Altrettanti (o quanti ne bastano per restare sotto il tetto)
    # arrivano a occupare posti liberi, pescando tra chi non è già
    # seduto.
    candidates = [
        npc for npc in _eligible_npcs_for_realm(conn, divinity)
        if npc["armor_name"] not in occupied_armor_names
    ]
    random.shuffle(candidates)
    free_slots = [slot for slot in _all_seat_slots() if slot not in occupied_slots]
    random.shuffle(free_slots)
    n_to_add = min(len(to_remove), len(candidates), len(free_slots))
    for npc, (table_number, seat_index) in zip(candidates[:n_to_add], free_slots[:n_to_add]):
        set_tavern_seating(conn, divinity, npc["armor_name"], table_number, seat_index)

    conn.commit()
    set_tavern_last_reshuffle(conn, divinity, world_minutes)
