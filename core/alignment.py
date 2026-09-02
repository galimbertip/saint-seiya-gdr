"""L'allineamento vero dei PNG (richiesto in chat, stile D&D a 9
caselle) - assegnato ad ogni PNG del roster (Guardiani delle Case,
Maestri, Figure Istituzionali indirettamente tramite i loro effetti),
MAI mostrato al giocatore: si scopre solo giocando, tentando,
fallendo. Prima ogni Guardiano aveva la STESSA identica soglia di
persuasione, indipendentemente da chi fosse - motivo per cui la
Scalata delle Dodici Case si poteva risolvere per intero con la sola
diplomazia (segnalato in chat, due volte).

Due assi, come da tradizione: Legge/Caos e Bene/Male, incrociati in 9
caselle. Un PNG più Buono è più ricettivo alla persuasione (crede
ancora che ci sia un altro modo); uno più Malvagio è più cinico e
meno disposto a farsi convincere; l'asse Legge/Caos aggiunge una
sfumatura più leggera (i Legali sono più prevedibili, i Caotici più
inclini a sorprendere in un senso o nell'altro)."""

import random

ALIGNMENTS = [
    "Legale Buono", "Neutrale Buono", "Caotico Buono",
    "Legale Neutrale", "Neutrale Puro", "Caotico Neutrale",
    "Legale Malvagio", "Neutrale Malvagio", "Caotico Malvagio",
]


def random_alignment() -> str:
    """Un allineamento a caso, con lieve preferenza per gli allineamenti
    NON estremi (richiesto implicito: se fossero tutti equiprobabili,
    un PNG su nove sarebbe Caotico Malvagio - un po' troppi mostri in
    giro per un mondo che deve restare credibile)."""
    weights = {
        "Legale Buono": 1.2, "Neutrale Buono": 1.3, "Caotico Buono": 1.0,
        "Legale Neutrale": 1.2, "Neutrale Puro": 1.4, "Caotico Neutrale": 1.0,
        "Legale Malvagio": 0.8, "Neutrale Malvagio": 0.7, "Caotico Malvagio": 0.6,
    }
    popolazione = list(weights.keys())
    pesi = list(weights.values())
    return random.choices(popolazione, weights=pesi, k=1)[0]


# Sommato alla soglia di persuasione (richiesto in chat) - positivo
# rende PIÙ difficile convincere, negativo PIÙ facile. PLACEHOLDER
# come le altre formule di bilanciamento di questo progetto.
ALIGNMENT_PERSUASION_MODIFIER = {
    "Legale Buono": -3,
    "Neutrale Buono": -4,
    "Caotico Buono": -2,
    "Legale Neutrale": 0,
    "Neutrale Puro": 0,
    "Caotico Neutrale": 1,
    "Legale Malvagio": 3,
    "Neutrale Malvagio": 4,
    "Caotico Malvagio": 5,
}

# Una frase in più dopo il testo (già scritto, specifico per Casa) di
# fallimento della persuasione (richiesto in chat: MAI nominare
# l'allineamento, solo lasciarlo trapelare dal tono) - scelta a caso
# tra quelle del "gruppo" giusto, non sempre la stessa.
ALIGNMENT_FAILURE_FLAVOR = {
    "Legale Buono": [
        "Nei suoi occhi c'è quasi rammarico, ma il dovere resta il dovere.",
        "\"Se ci fosse un altro modo\", sembra dire il suo sguardo, \"lo avrei già scelto.\"",
    ],
    "Neutrale Buono": [
        "Per un istante sembra sul punto di cedere, poi si ricompone.",
        "\"Mi dispiace davvero\", dice, e sembra sincero.",
    ],
    "Caotico Buono": [
        "Ride, quasi divertito dal tuo tentativo, prima di tornare serio.",
        "\"Bel tentativo\", concede, \"ma non abbastanza.\"",
    ],
    "Legale Neutrale": [
        "Le regole sono le regole, e lo dice come se chiudesse un libro.",
        "Non c'è rancore nella sua voce, solo la fermezza di chi segue un ordine.",
    ],
    "Neutrale Puro": [
        "Ti osserva con un'indifferenza che pesa più di qualunque minaccia.",
        "Non sembra nemmeno considerare seriamente le tue parole.",
    ],
    "Caotico Neutrale": [
        "Il suo umore cambia a metà frase, e la finestra che si era aperta si richiude di colpo.",
        "\"Chissà\", mormora, come se la decisione non dipendesse nemmeno da lui.",
    ],
    "Legale Malvagio": [
        "Nei suoi occhi c'è qualcosa di più freddo del semplice dovere.",
        "\"Le regole servono anche a schiacciare chi si illude di poterle piegare\", dice, quasi con piacere.",
    ],
    "Neutrale Malvagio": [
        "Non gli importa affatto delle tue ragioni - solo di quello che ci guadagna lui.",
        "Ti valuta come si valuta un ostacolo, non una persona.",
    ],
    "Caotico Malvagio": [
        "Sorride in un modo che non promette nulla di buono.",
        "Le tue parole sembrano quasi divertirlo, nel modo sbagliato.",
    ],
}

# Stessa idea, ma per la persuasione RIUSCITA - un accenno del perché
# ha ceduto, sempre senza nominare l'allineamento.
ALIGNMENT_SUCCESS_FLAVOR = {
    "Legale Buono": ["Annuisce lentamente: \"Le tue ragioni sono giuste. Non ti fermerò.\""],
    "Neutrale Buono": ["I suoi occhi si addolciscono. \"Va bene. Passa.\""],
    "Caotico Buono": ["Scoppia a ridere. \"Mi hai convinto - e mi sei anche simpatico.\""],
    "Legale Neutrale": ["Considera le tue parole come clausole di un accordo, e le trova valide."],
    "Neutrale Puro": ["Scrolla le spalle, come se la cosa non lo riguardasse più di tanto."],
    "Caotico Neutrale": ["Decide sul momento, seguendo un capriccio più che una vera convinzione."],
    "Legale Malvagio": ["Calcola che lasciarti passare gli convenga più che fermarti - nient'altro."],
    "Neutrale Malvagio": ["Ti lascia andare con un sorriso che promette di rivedersi, un giorno."],
    "Caotico Malvagio": ["Ti lascia passare solo perché, in fondo, preferisce vedere cosa succede dopo."],
}


def persuasion_flavor_line(alignment: str, success: bool) -> str:
    """Una frase in più da aggiungere al testo (già scritto, specifico
    per Casa) di successo/fallimento - mai la stessa due volte di
    fila, mai il nome dell'allineamento."""
    pool = ALIGNMENT_SUCCESS_FLAVOR if success else ALIGNMENT_FAILURE_FLAVOR
    opzioni = pool.get(alignment) or pool["Neutrale Puro"]
    return random.choice(opzioni)


# Effetti più ampi (richiesto in chat): l'allineamento sposta anche il
# comportamento in combattimento, non solo la persuasione - un
# avversario più Malvagio è più aggressivo e meno paziente (carica di
# rado, preferisce colpire), uno più Buono è più misurato (carica più
# spesso, un duello onorevole più che una gara di violenza pura). Le
# differenze restano volutamente leggere - non deve sembrare un'altra
# difficoltà mascherata, solo una sfumatura di stile che si nota nel
# tempo. (peso_attacco, peso_carica) - sostituisce i pesi fissi
# 0.8/0.2 usati finora da choose_opponent_action.
ALIGNMENT_COMBAT_WEIGHTS = {
    "Legale Buono": (0.75, 0.25),
    "Neutrale Buono": (0.78, 0.22),
    "Caotico Buono": (0.72, 0.28),
    "Legale Neutrale": (0.80, 0.20),
    "Neutrale Puro": (0.80, 0.20),
    "Caotico Neutrale": (0.82, 0.18),
    "Legale Malvagio": (0.85, 0.15),
    "Neutrale Malvagio": (0.88, 0.12),
    "Caotico Malvagio": (0.90, 0.10),
}


def combat_action_weights(alignment: str) -> tuple[float, float]:
    """I pesi (attacca, carica) per la scelta dell'azione proattiva di
    un avversario (richiesto in chat) - quelli di default
    (Legale Neutrale/Neutrale Puro, 0.80/0.20) se l'allineamento non è
    riconosciuto o è vuoto (retrocompatibilità con avversari generati
    prima di questa modifica)."""
    return ALIGNMENT_COMBAT_WEIGHTS.get(alignment, (0.80, 0.20))


# Lo stesso vale per il peso dei destini nella simulazione del mondo
# (richiesto in chat) - un PNG più Malvagio è leggermente più incline
# a sparire in circostanze losche o a morire in un duello, uno più
# Buono più incline a un ritiro pacifico. Le tre categorie sono le
# stesse di core.world_sim.NPC_FATE_OPTIONS (morte, ritiro, sparizione)
# - qui solo un moltiplicatore per categoria, non frasi nuove.
ALIGNMENT_FATE_CATEGORY_WEIGHTS = {
    "Legale Buono": (0.7, 1.3, 0.8),
    "Neutrale Buono": (0.6, 1.4, 0.8),
    "Caotico Buono": (0.8, 1.1, 1.1),
    "Legale Neutrale": (1.0, 1.0, 1.0),
    "Neutrale Puro": (1.0, 1.0, 1.0),
    "Caotico Neutrale": (1.1, 0.9, 1.2),
    "Legale Malvagio": (1.2, 0.8, 1.1),
    "Neutrale Malvagio": (1.3, 0.7, 1.2),
    "Caotico Malvagio": (1.5, 0.6, 1.4),
}  # (morte, ritiro, sparizione)
