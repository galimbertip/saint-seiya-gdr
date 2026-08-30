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

# Soglia fissa per le prove a dado delle tappe (richiesto in chat:
# tutto l'addestramento dev'essere interattivo) - PLACEHOLDER come le
# altre formule di bilanciamento in questo file, mai tarata sul serio.
SKILL_CHECK_THRESHOLD = 14


def resolve_skill_check(knight: dict, stat: str) -> bool:
    """Un vero tiro di dado sulla statistica indicata di una tappa -
    d20 + metà della statistica, contro una soglia fissa. Si può
    fallire (richiesto in chat), non è un successo garantito."""
    roll = random.randint(1, 20) + knight[stat] // 2
    return roll >= SKILL_CHECK_THRESHOLD


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


# Le 20 tappe (richiesto in chat: tutto l'addestramento dev'essere
# interattivo, non solo la Prova Finale) - ogni tappa ha un "type":
#   narrative  -> solo testo, un pulsante Continua (i momenti di puro
#                 racconto: arrivo, annuncio, ecc. - non ogni singolo
#                 istante ha bisogno di un meccanismo)
#   skill_check -> un vero tiro di dado sulla statistica indicata,
#                 dietro un pulsante "Prova" - si può fallire e
#                 riprovare, o accettare il fallimento e andare avanti
#                 comunque (vedi resolve_skill_check)
#   choice     -> 2-3 scelte reali, ciascuna con un esito narrativo
#                 diverso e un piccolo premio permanente ad una
#                 statistica
#   spar       -> un vero scontro leggero contro un compagno (stesso
#                 motore della Prova Finale, ma "di prova": non conta
#                 ai fini della sconfitta, si avanza comunque)
# {master}/{companion1}/{companion2}/{tech1}/{tech2} sono sostituiti
# con i dati veri del personaggio quando la tappa viene mostrata (vedi
# render_stage). Numerate da 1 (non 0) per parlare meglio con chi legge
# il codice - training_stage=0 vuol dire "non ancora iniziato",
# training_stage=N vuol dire "ha completato la tappa N".
TRAINING_STAGES = [
    {
        "type": "narrative",
        "title": "Il primo giorno",
        "text": ("{master}, che porta {master_armor}, ti accoglie senza troppe cerimonie: sarà lui a "
                  "guidarti nell'addestramento che ti porterà, se lo supererai, a indossare {your_armor}. "
                  "Al suo fianco, due facce nuove quanto la tua: {companion1} e {companion2}, altri due "
                  "aspiranti alla stessa {your_armor} - solo uno di voi tre, alla fine, la indosserà "
                  "davvero. \"Da oggi in poi\", dice {master}, \"non siete più chi eravate prima di "
                  "arrivare qui.\""),
    },
    {
        "type": "choice_check",
        "title": "Le prime fatiche",
        "text": ("Corsa, flessioni, ore a reggere pesi che sembrano non finire mai. {companion1} crolla "
                  "a terra due volte prima di mezzogiorno; tu non stai molto meglio. Come vuoi affrontarla?"),
        "approaches": [
            {"label": "Spingere sul fisico puro", "stat": "con"},
            {"label": "Trovare il ritmo con la mente, non col corpo", "stat": "vol"},
        ],
        "success_text": ("Il tuo corpo regge più di quanto pensassi - {master} annuisce appena, il segno "
                          "più vicino a un complimento che concede."),
        "failure_text": ("Non ce la fai a reggere il ritmo fino in fondo - ti fermi prima degli altri, le "
                          "gambe che tremano. {master} non dice nulla, ma non serve."),
    },
    {
        "type": "narrative",
        "title": "Cos'è il Cosmo",
        "text": ("\"Tutto ciò che esiste\", spiega {master}, \"è fatto delle stesse particelle "
                  "infinitesimali - e dentro ognuno di voi arde un piccolo universo. Quello è il vostro "
                  "Cosmo. Il vostro compito, da qui in avanti, è imparare ad accenderlo.\""),
    },
    {
        "type": "choice_check",
        "title": "Il primo tentativo",
        "text": "Ti concentri, cerchi quella scintilla di cui parla {master}. Come provi a raggiungerla?",
        "approaches": [
            {"label": "Concentrarti in silenzio assoluto", "stat": "vol"},
            {"label": "Lasciarti guidare dall'istinto del corpo", "stat": "dex"},
        ],
        "success_text": ("Per un istante brevissimo, qualcosa si muove dentro di te - non è ancora la "
                          "vera scintilla, ma è la prima volta che la senti passare."),
        "failure_text": ("Niente aura, niente calore. Solo la frustrazione di {companion2} che ride della "
                          "propria stessa goffaggine, e la tua che non fa altrettanto ridere."),
    },
    {
        "type": "choice_check",
        "title": "La prova dei limiti",
        "text": "{master} vi porta al limite del corpo - una prova di resistenza vera. Come resisti?",
        "approaches": [
            {"label": "Stringere i denti e incassare", "stat": "con"},
            {"label": "Trovare la forza nella determinazione", "stat": "vol"},
        ],
        "success_text": ("Resisti oltre il punto in cui il corpo chiedeva di fermarsi. {companion1} ce la "
                          "fa per un soffio, proprio come te."),
        "failure_text": ("Il corpo cede prima della mente - crolli a terra, sconfitto dalla fatica più che "
                          "da un avversario. Ci riproverai."),
    },
    {
        "type": "narrative",
        "title": "La scintilla",
        "text": ("Succede quando meno te lo aspetti: una fitta al petto, un calore che sale, e per un "
                  "istante l'aria intorno a te vibra visibilmente. \"Ecco\", dice {master}, quasi senza "
                  "sorpresa. \"Ora sai cosa cercare.\""),
    },
    {
        "type": "narrative",
        "title": "Lo studio della prima tecnica",
        "text": ("{master} ti mostra, con calma, i princìpi di {tech1} - non ancora come eseguirla, solo "
                  "perché funziona: dove nasce il movimento, dove va incanalato il Cosmo, cosa deve "
                  "succedere perché il colpo non sia solo un pugno con un nome altisonante."),
    },
    {
        "type": "choice_check",
        "title": "I primi fallimenti",
        "text": "Provi {tech1} decine di volte, cercando la sensazione giusta. Come provi ad arrivarci?",
        "approaches": [
            {"label": "Ripetere il gesto finché non è perfetto", "stat": "tec"},
            {"label": "Fermarti a capire la teoria prima di riprovare", "stat": "vol"},
        ],
        "success_text": ("Qualcosa comincia a funzionare - non ancora perfetto, ma abbastanza vicino da "
                          "farti capire che sei sulla strada giusta."),
        "failure_text": ("Niente. Troppo debole, o nella direzione sbagliata, o senza la scintilla del "
                          "Cosmo dietro. {companion2} osserva e prova a darti consigli che, sospetti, non "
                          "capisce nemmeno lui."),
    },
    {
        "type": "choice_check",
        "title": "La padronanza",
        "text": "È il momento di dimostrare di aver davvero imparato {tech1}. Come ti presenti alla prova?",
        "approaches": [
            {"label": "Fidarti dell'istinto, senza pensarci troppo", "stat": "dex"},
            {"label": "Applicare la tecnica con metodo, passo per passo", "stat": "tec"},
        ],
        "success_text": ("Il movimento è giusto - il corpo, il Cosmo, l'intenzione, tutto insieme nello "
                          "stesso istante. {tech1} lascia il segno che deve lasciare. {master} annuisce: "
                          "\"Cominci a vedere quello che c'è oltre la superficie delle cose, adesso.\""),
        "failure_text": ("Ancora no - manca quel qualcosa che rende {tech1} una tecnica vera, e non solo "
                          "un gesto vuoto. Ci riproverai."),
    },
    {
        "type": "narrative",
        "title": "Lo studio della seconda tecnica",
        "text": ("Con la prima tecnica ormai nelle mani, {master} introduce {tech2} - più sottile della "
                  "prima, dice, e per questo più difficile da controllare davvero, non solo da eseguire."),
    },
    {
        "type": "choice_check",
        "title": "La pratica",
        "text": "{tech2} si rifiuta di venire naturale quanto la prima. Come insisti?",
        "approaches": [
            {"label": "Insistere con la ripetizione", "stat": "tec"},
            {"label": "Osservare {master} e imitarlo con calma", "stat": "vol"},
        ],
        "success_text": ("Qualcosa si sblocca - {tech2} comincia ad avere senso, anche se resta più "
                          "sottile e difficile da controllare della prima."),
        "failure_text": ("{companion1} la impara più in fretta di te, e per un momento è difficile non "
                          "lasciarsi mordere dall'invidia."),
    },
    {
        "type": "choice_check",
        "title": "La seconda padronanza",
        "text": "L'ultimo passo prima di poter dire di conoscere davvero {tech2}. Come chiudi il cerchio?",
        "approaches": [
            {"label": "Fidarti della forza del corpo", "stat": "str"},
            {"label": "Rifinire ogni dettaglio con precisione", "stat": "tec"},
        ],
        "success_text": ("Arriva anche questa - {tech2} eseguita come deve essere, senza più doverci "
                          "pensare ad ogni singolo passaggio. Due tecniche vere, ora, non più solo teoria "
                          "raccontata da {master}."),
        "failure_text": "{tech2} resta ostinata, un passo oltre la tua portata per oggi. Domani sarà un altro giorno.",
    },
    {
        "type": "choice_check",
        "title": "Il Sesto Senso",
        "text": "\"C'è un modo di percepire il Cosmo altrui\", spiega {master}, \"prima ancora che un colpo arrivi.\" Come ci provi?",
        "approaches": [
            {"label": "Aprire la mente al Cosmo altrui", "stat": "vol"},
            {"label": "Affinare i sensi fisici", "stat": "dex"},
        ],
        "success_text": ("Per un istante, senti qualcosa muoversi nell'aria prima ancora di vederlo - un "
                          "affinamento dell'attenzione che, ti accorgi, avevi già cominciato ad avere."),
        "failure_text": "Non senti nulla, per ora - solo il vuoto silenzio di un'attenzione non ancora abbastanza affinata.",
    },
    {
        "type": "choice_check",
        "title": "La prova del dolore",
        "text": ("{master} non risparmia nessuno, in questa prova - il corpo che chiede di fermarsi, la "
                  "mente che deve imparare a non ascoltarlo. Come resisti?"),
        "approaches": [
            {"label": "Resistere con la forza di volontà", "stat": "vol"},
            {"label": "Distrarre la mente dal dolore fisico", "stat": "con"},
        ],
        "success_text": ("Resisti, oltre il punto in cui avresti voluto arrenderti. {companion2} non ce "
                          "la fa al primo tentativo - tu sì."),
        "failure_text": ("Il dolore vince, questa volta - ti fermi prima del necessario. Non è una "
                          "sconfitta, solo un limite da spostare un po' più in là."),
    },
    {
        "type": "spar",
        "title": "Fianco a fianco",
        "text": ("Il primo vero allenamento a due contro uno, tu e {companion1} contro {companion2} a "
                  "turno. Non è la Prova Finale - è solo pratica vera, con un avversario vero."),
    },
    {
        "type": "choice",
        "title": "Il momento di dubbio",
        "text": ("C'è un giorno, verso la fine, in cui ti chiedi seriamente se sei tagliato per questo. "
                  "{master} se ne accorge, e ti lascia scegliere come affrontarlo."),
        "options": [
            {"label": "Parlarne apertamente con {master}", "bonus_stat": "vol",
             "outcome_text": ("{master} ti ascolta senza interromperti, poi dice solo: \"Il dubbio non è "
                               "debolezza. È debolezza smettere per colpa sua.\" Qualcosa dentro di te si assesta.")},
            {"label": "Sfogarti allenandoti ancora più duramente", "bonus_stat": "con",
             "outcome_text": "Non parli con nessuno - ti alleni finché il dubbio non ha più fiato per farsi sentire. Funziona, più o meno."},
            {"label": "Confidarti con {companion1}", "bonus_stat": None,
             "outcome_text": "Scopri che anche {companion1} ha avuto lo stesso pensiero, la stessa notte. Non risolve nulla, ma pesa meno portato in due."},
        ],
    },
    {
        "type": "choice",
        "title": "Lo stile personale",
        "text": ("Le ultime settimane non aggiungono più nulla di nuovo da imparare - rifiniscono quello "
                  "che c'è già. Come vuoi affinare il tuo modo di combattere?"),
        "options": [
            {"label": "Colpire più forte, rischiare di più", "bonus_stat": "str",
             "outcome_text": "Il tuo stile si fa più aggressivo, meno prudente - ogni colpo cerca di essere quello decisivo."},
            {"label": "Restare in piedi più a lungo di chiunque altro", "bonus_stat": "con",
             "outcome_text": "Impari a incassare, a resistere, a logorare l'avversario più che abbatterlo di colpo."},
            {"label": "Anticipare invece di reagire", "bonus_stat": "dex",
             "outcome_text": "Affini l'istinto, il tempismo - il modo in cui senti un colpo arrivare prima ancora che parta davvero."},
        ],
    },
    {
        "type": "narrative",
        "title": "L'annuncio",
        "text": ("\"È tempo\", dice {master} una mattina, senza preamboli. \"L'addestramento non prova "
                  "nulla finché non viene messo alla prova. Preparati: la Prova Finale è vicina.\""),
    },
    {
        "type": "narrative",
        "title": "L'ultima notte",
        "text": ("La notte prima della Prova Finale non dorme quasi nessuno. Ripassi ogni tecnica nella "
                  "testa, ripensi ad ogni fatica delle ultime settimane, e ti chiedi se basterà. "
                  "{companion1} e {companion2}, in silenzio, sembrano chiedersi la stessa cosa."),
    },
    {
        "type": "narrative",
        "title": "La Prova Finale",
        "text": ("È il momento della verità: tutto quello che hai imparato messo alla prova in un solo "
                  "scontro, senza reti di sicurezza."),
    },
]


def _fill_placeholders(text: str, ctx: dict) -> str:
    """Applica i segnaposto {master}/{companion1}/ecc. a una stringa
    qualunque - usata per il testo principale di una tappa, ma anche
    per i testi di successo/fallimento e le opzioni di scelta, che
    hanno la stessa esigenza."""
    return text.format(**ctx)


def build_stage_context(master_name: str, master_armor_name: str, companion1: str,
                         companion2: str, techniques: list[dict], your_armor_name: str = "") -> dict:
    """Costruisce il dizionario dei segnaposto per una tappa - condiviso
    tra render_stage e i nuovi endpoint di prova/scelta (richiesto in
    chat: tutto l'addestramento dev'essere interattivo), così non si
    duplica la stessa logica in più punti."""
    tech1_name = techniques[0]["name"] if len(techniques) > 0 else "la prima tecnica"
    tech2_name = techniques[1]["name"] if len(techniques) > 1 else "la seconda tecnica"
    return {
        "master": master_name, "master_armor": master_armor_name, "companion1": companion1,
        "companion2": companion2, "tech1": tech1_name, "tech2": tech2_name, "your_armor": your_armor_name,
    }


def render_stage(stage_number: int, master_name: str, master_armor_name: str,
                  companion1: str, companion2: str, techniques: list[dict],
                  your_armor_name: str = "") -> dict:
    """Restituisce il contenuto della tappa `stage_number` (1-indicizzata),
    con i nomi veri del personaggio al posto dei segnaposto - la forma
    del contenuto dipende dal 'type' della tappa (narrative/skill_check/
    choice/spar, richiesto in chat: tutto l'addestramento dev'essere
    interattivo, non solo testo da leggere)."""
    stage = TRAINING_STAGES[stage_number - 1]
    ctx = build_stage_context(master_name, master_armor_name, companion1, companion2, techniques, your_armor_name)

    result = {
        "stage_number": stage_number, "total_stages": TOTAL_STAGES, "type": stage["type"],
        "title": stage["title"], "text": _fill_placeholders(stage["text"], ctx),
        "master_name": master_name, "master_armor_name": master_armor_name,
        "companion1_name": companion1, "companion2_name": companion2, "your_armor_name": your_armor_name,
    }
    if stage["type"] == "choice_check":
        result["approaches"] = [
            {"label": _fill_placeholders(a["label"], ctx), "index": i}
            for i, a in enumerate(stage["approaches"])
        ]
    elif stage["type"] == "choice":
        result["options"] = [
            {"label": _fill_placeholders(opt["label"], ctx), "index": i}
            for i, opt in enumerate(stage["options"])
        ]
    return result


def generate_trial_opponent(conn: sqlite3.Connection, opponent_is_master: bool, opponent_name: str,
                             master_armor_name: str, player_armor: dict) -> dict:
    """Costruisce un avversario VERO per il motore di combattimento
    (richiesto in chat: "fammi combattere davvero", non un tiro di
    dado narrato) - stessa forma di arena_manager.generate_opponent,
    così la Prova Finale usa esattamente lo stesso motore di battaglia
    di un normale scontro in Arena (movimento, tecniche, Contrattacco,
    tutto).
    Contro il Maestro: la SUA armatura vera, molto più forte.
    Contro un compagno: la STESSA armatura per cui si sta addestrando
    anche il personaggio (corretto in chat: fedeltà al canone - più
    aspiranti competono per la stessa Cloth, non per armature diverse
    - non più "un pari della tua fascia" con un'armatura a caso)."""
    armor_name = master_armor_name if opponent_is_master else player_armor["name"]

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
