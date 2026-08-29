"""Il percorso di Apprendistato (richiesto in chat): prima di diventare
un Cavaliere vero e proprio, ogni personaggio che nasce a livello 1
(un vero esordiente, non un "veterano" dichiarato tale già in
creazione con un livello più alto) deve completare un addestramento
in 20 tappe, guidato da un Maestro e affiancato da due compagni,
prima di poter mettere piede in Arena.

Il Maestro NON è generato a caso (richiesto in chat: "abbiamo già i
PNG in Gerarchia") - è il PNG che occupa già la fazione di rango più
alto della stessa divinità dell'armatura scelta, calcolato con lo
stesso criterio (livello medio della fazione) già usato per ordinare
la Gerarchia. Se la propria fazione è già la più alta della divinità,
il Maestro arriva dalla stessa fascia (un pari/leggenda, non un
gradino sopra che non esiste).

I due compagni di addestramento sono generati da subito (richiesto in
chat: "così facciamo già i primi allenamenti assieme"), con lo stesso
generatore di nomi già usato per gli avversari - non hanno un'armatura
propria, sono aspiranti come il personaggio.

Il testo delle tappe è tutto originale, scritto per questo progetto,
ispirato ad elementi autentici e ricorrenti nell'opera (il Cosmo come
energia interiore da "accendere", l'addestramento fisico estremo, il
rapporto maestro-allievo, la prova finale contro un compagno o il
Maestro) ma senza riprendere nessuna scena, dialogo o personaggio
specifico dell'opera originale.
"""

import random
import sqlite3

from database.db_manager import get_roster_entry, get_armor, get_techniques_for_armor
from core.arena_manager import OPPONENT_FIRST_NAMES, OPPONENT_SURNAMES

TOTAL_STAGES = 20

# A quali tappe corrisponde una salita di livello (richiesto in chat:
# livello 2 dopo la lezione sul Cosmo, livello 3 dopo la prima tecnica
# - coincide apposta con la soglia già esistente del Sesto Senso -
# livello 4 dopo la seconda tecnica, livello 5 solo se si supera la
# Prova Finale, gestita a parte).
LEVEL_UP_AFTER_STAGE = {3: 2, 9: 3, 12: 4}

FINAL_TRIAL_STAGE = TOTAL_STAGES  # 20
KNIGHTHOOD_LEVEL = 5

# Se si fallisce la Prova Finale (richiesto in chat: dev'essere
# possibile fallire), si torna a questa tappa per prepararsi di nuovo,
# invece di poter ritentare all'infinito senza conseguenze.
RETRY_STAGE_ON_FAILURE = 18


def select_master(conn: sqlite3.Connection, divinity: str, faction: str) -> tuple[str, str]:
    """Sceglie il Maestro per un apprendista di questa divinità/fazione
    - un PNG GIÀ ESISTENTE in Gerarchia (richiesto in chat, non uno
    generato a caso), della fazione di rango più alto nella stessa
    divinità (stesso criterio del livello medio già usato per ordinare
    la Gerarchia). Se la propria fazione è già la più alta, il Maestro
    arriva dalla stessa fascia. Restituisce (nome_maestro,
    nome_armatura_del_maestro)."""
    righe = conn.execute(
        "SELECT faction, level, name FROM armors WHERE divinity = ?", (divinity,)
    ).fetchall()

    per_fazione: dict[str, list[sqlite3.Row]] = {}
    for r in righe:
        per_fazione.setdefault(r["faction"], []).append(r)

    livello_medio = {f: sum(r["level"] for r in armi) / len(armi) for f, armi in per_fazione.items()}
    livello_proprio = livello_medio.get(faction, 0)

    fasce_superiori = [f for f, lv in livello_medio.items() if lv > livello_proprio]
    if fasce_superiori:
        # Il gradino IMMEDIATAMENTE superiore, non il vertice assoluto
        # della divinità (corretto in chat: un Bronze Saint non viene
        # affidato a chi indossa la Cloth di Athena stessa, un salto
        # troppo grande - un Silver o poco più, come nell'opera).
        fascia_maestro = min(fasce_superiori, key=lambda f: livello_medio[f])
    else:
        fascia_maestro = faction  # già alla fascia più alta - un pari/leggenda

    armatura_maestro = random.choice(per_fazione[fascia_maestro])["name"]
    roster_entry = get_roster_entry(conn, armatura_maestro)
    nome_maestro = roster_entry["npc_name"] if roster_entry else f"{random.choice(OPPONENT_FIRST_NAMES)} {random.choice(OPPONENT_SURNAMES)}"
    return nome_maestro, armatura_maestro


def generate_companions(exclude_name: str = "") -> tuple[str, str]:
    """Genera due compagni di addestramento (richiesto in chat: fin
    dall'inizio, non solo per la Prova Finale) - nessuna armatura
    propria, sono aspiranti come il personaggio. Stesso generatore di
    nomi già usato per gli avversari in Arena. `exclude_name` evita che
    un compagno finisca per chiamarsi esattamente come il Maestro -
    pescando dallo stesso piccolo elenco di nomi, è capitato per puro
    caso durante i test."""
    for _ in range(20):  # tentativi ampiamente sufficienti, la collisione è rara
        nomi = random.sample(OPPONENT_FIRST_NAMES, 2)
        cognomi = random.sample(OPPONENT_SURNAMES, 2)
        c1, c2 = f"{nomi[0]} {cognomi[0]}", f"{nomi[1]} {cognomi[1]}"
        if exclude_name not in (c1, c2):
            return c1, c2
    return c1, c2  # non dovrebbe mai arrivarci, ma non blocchiamo la creazione per questo


# Le 20 tappe. {master}/{companion1}/{companion2}/{tech1}/{tech2} sono
# sostituiti con i dati veri del personaggio quando la tappa viene
# mostrata (vedi render_stage). Numerate da 1 (non 0) per parlare
# meglio con chi legge il codice - training_stage=0 vuol dire "non
# ancora iniziato", training_stage=N vuol dire "ha completato la
# tappa N".
TRAINING_STAGES = [
    {
        "title": "Il primo giorno",
        "text": ("{master}, che porta {master_armor}, ti accoglie senza troppe cerimonie: sarà lui a "
                  "guidarti nell'addestramento che ti porterà, se lo supererai, a indossare {your_armor}. "
                  "Al suo fianco, due facce nuove quanto la tua: {companion1} e {companion2}, altri due "
                  "aspiranti che affronteranno lo stesso cammino. \"Da oggi in poi\", dice {master}, "
                  "\"non siete più chi eravate prima di arrivare qui.\""),
    },
    {
        "title": "Le prime fatiche",
        "text": ("Corsa, flessioni, ore a reggere pesi che sembrano non finire mai. {companion1} crolla "
                  "a terra due volte prima di mezzogiorno; tu non stai molto meglio. {master} osserva in "
                  "silenzio, senza mai intervenire - lascia che sia la fatica stessa a insegnare."),
    },
    {
        "title": "Cos'è il Cosmo",
        "text": ("\"Tutto ciò che esiste\", spiega {master}, \"è fatto delle stesse particelle "
                  "infinitesimali - e dentro ognuno di voi arde un piccolo universo. Quello è il vostro "
                  "Cosmo. Il vostro compito, da qui in avanti, è imparare ad accenderlo.\""),
    },
    {
        "title": "Il primo tentativo",
        "text": ("Ti concentri, stringi i pugni, cerchi quella scintilla di cui parla {master} - e non "
                  "succede nulla. Niente aura, niente calore, solo la frustrazione di {companion2} che "
                  "ride della propria stessa goffaggine, e la tua che non fa altrettanto ridere."),
    },
    {
        "title": "La prova dei limiti",
        "text": ("{master} vi porta al limite del corpo - non un allenamento, una prova di resistenza "
                  "vera, il tipo che si supera solo quando la mente smette di dire al corpo di fermarsi. "
                  "{companion1} ce la fa per un soffio. Tu stringi i denti e resisti."),
    },
    {
        "title": "La scintilla",
        "text": ("Succede quando meno te lo aspetti: una fitta al petto, un calore che sale, e per un "
                  "istante l'aria intorno a te vibra visibilmente. \"Ecco\", dice {master}, quasi senza "
                  "sorpresa. \"Ora sai cosa cercare.\""),
    },
    {
        "title": "Lo studio della prima tecnica",
        "text": ("{master} ti mostra, con calma, i princìpi di {tech1} - non ancora come eseguirla, solo "
                  "perché funziona: dove nasce il movimento, dove va incanalato il Cosmo, cosa deve "
                  "succedere perché il colpo non sia solo un pugno con un nome altisonante."),
    },
    {
        "title": "I primi fallimenti",
        "text": ("Provi {tech1} decine di volte. Le prime non succede nulla. Poi qualcosa, ma sbagliato "
                  "- troppo debole, o nella direzione sbagliata, o senza la scintilla del Cosmo dietro. "
                  "{companion2} osserva e prova a darti consigli che, sospetti, non capisce nemmeno lui."),
    },
    {
        "title": "La padronanza",
        "text": ("Poi, di colpo, il movimento è giusto - il corpo, il Cosmo, l'intenzione, tutto insieme "
                  "nello stesso istante. {tech1} lascia il segno che deve lasciare. {master} annuisce: "
                  "\"Cominci a vedere quello che c'è oltre la superficie delle cose, adesso.\""),
    },
    {
        "title": "Lo studio della seconda tecnica",
        "text": ("Con la prima tecnica ormai nelle mani, {master} introduce {tech2} - più sottile della "
                  "prima, dice, e per questo più difficile da controllare davvero, non solo da eseguire."),
    },
    {
        "title": "La pratica",
        "text": ("{tech2} si rifiuta di venire naturale quanto la prima. {companion1} la impara più in "
                  "fretta di te, e per un momento è difficile non lasciarsi mordere dall'invidia - finché "
                  "non ricordi che nessuno qui sta gareggiando con nessun altro, se non con se stesso."),
    },
    {
        "title": "La seconda padronanza",
        "text": ("Arriva anche questa, alla fine - {tech2} eseguita come deve essere, senza più doverci "
                  "pensare ad ogni singolo passaggio. Due tecniche vere, ora, non più solo teoria "
                  "raccontata da {master}."),
    },
    {
        "title": "Il Sesto Senso",
        "text": ("\"C'è un modo di percepire il Cosmo altrui\", spiega {master}, \"prima ancora che un "
                  "colpo arrivi.\" Non è qualcosa che si impara di colpo - è un affinamento lento di "
                  "un'attenzione che, ti accorgi, hai già cominciato ad avere."),
    },
    {
        "title": "La prova del dolore",
        "text": ("{master} non risparmia nessuno, in questa prova - il corpo che chiede di fermarsi, la "
                  "mente che deve imparare a non ascoltarlo senza per questo smettere di proteggerlo. "
                  "{companion2} non la supera al primo tentativo. Tu, forse, nemmeno."),
    },
    {
        "title": "Fianco a fianco",
        "text": ("Il primo vero allenamento a due contro uno, tu e {companion1} contro {companion2} a "
                  "turno, poi invertiti. Non c'è vittoria o sconfitta che conti davvero - solo il modo "
                  "in cui, senza accorgervene, avete cominciato a coprirvi le spalle a vicenda."),
    },
    {
        "title": "Il momento di dubbio",
        "text": ("C'è un giorno, verso la fine, in cui ti chiedi seriamente se sei tagliato per questo. "
                  "{master} se ne accorge - non ti consola, non ti dice che è tutto a posto. Ti dice solo: "
                  "\"Il dubbio non è debolezza. È debolezza smettere per colpa sua.\""),
    },
    {
        "title": "Lo stile personale",
        "text": ("Le ultime settimane non aggiungono più nulla di nuovo da imparare - rifiniscono quello "
                  "che c'è già. Il modo in cui ti muovi, in cui carichi un colpo, in cui reagisci quando "
                  "sei messo alle strette: comincia ad assomigliare a te, non più solo a {master}."),
    },
    {
        "title": "L'annuncio",
        "text": ("\"È tempo\", dice {master} una mattina, senza preamboli. \"L'addestramento non prova "
                  "nulla finché non viene messo alla prova. Preparati: la Prova Finale è vicina.\""),
    },
    {
        "title": "L'ultima notte",
        "text": ("La notte prima della Prova Finale non dorme quasi nessuno. Ripassi ogni tecnica nella "
                  "testa, ripensi ad ogni fatica delle ultime settimane, e ti chiedi se basterà. "
                  "{companion1} e {companion2}, in silenzio, sembrano chiedersi la stessa cosa."),
    },
    {
        "title": "La Prova Finale",
        "text": ("È il momento della verità: tutto quello che hai imparato messo alla prova in un solo "
                  "scontro, senza reti di sicurezza."),
    },
]


def render_stage(stage_number: int, master_name: str, master_armor_name: str,
                  companion1: str, companion2: str, techniques: list[dict],
                  your_armor_name: str = "") -> dict:
    """Restituisce il titolo e il testo della tappa `stage_number`
    (1-indicizzata), con i nomi veri del personaggio al posto dei
    segnaposto."""
    stage = TRAINING_STAGES[stage_number - 1]
    tech1_name = techniques[0]["name"] if len(techniques) > 0 else "la prima tecnica"
    tech2_name = techniques[1]["name"] if len(techniques) > 1 else "la seconda tecnica"
    text = stage["text"].format(
        master=master_name, master_armor=master_armor_name, companion1=companion1, companion2=companion2,
        tech1=tech1_name, tech2=tech2_name, your_armor=your_armor_name,
    )
    return {
        "stage_number": stage_number, "total_stages": TOTAL_STAGES, "title": stage["title"], "text": text,
        "master_name": master_name, "master_armor_name": master_armor_name,
        "companion1_name": companion1, "companion2_name": companion2, "your_armor_name": your_armor_name,
    }


def generate_trial_opponent(conn: sqlite3.Connection, opponent_is_master: bool, opponent_name: str,
                             master_armor_name: str, player_armor: dict) -> dict:
    """Costruisce un avversario VERO per il motore di combattimento
    (richiesto in chat: "fammi combattere davvero", non un tiro di
    dado narrato) - stessa forma di arena_manager.generate_opponent,
    così la Prova Finale usa esattamente lo stesso motore di battaglia
    di un normale scontro in Arena (movimento, tecniche, Contrattacco,
    tutto).
    Contro il Maestro: la SUA armatura vera, molto più forte.
    Contro un compagno: un'armatura a caso della TUA stessa
    divinità/fazione - un pari, un altro aspirante alla tua fascia."""
    if opponent_is_master:
        armor_name = master_armor_name
    else:
        pari = conn.execute(
            "SELECT name FROM armors WHERE divinity = ? AND faction = ? AND name != ?",
            (player_armor["divinity"], player_armor["faction"], player_armor["name"]),
        ).fetchall()
        armor_name = random.choice(pari)["name"] if pari else player_armor["name"]

    armor = get_armor(armor_name, conn)
    techniques = [dict(t) for t in get_techniques_for_armor(armor_name, conn)]
    cosmo = 100 + armor["level"]
    return {
        "name": f"{opponent_name} di {armor_name}",
        "armor_name": armor_name,
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
        "origin": "",
        "techniques": techniques,
    }
