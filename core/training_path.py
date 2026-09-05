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

from database.db_manager import get_roster_entry, get_armor, get_techniques_for_armor, get_world_minutes
from core.arena_manager import generate_full_name, generate_distinct_full_names
from core.alignment import random_alignment
from core.world_sim import apply_npc_regen

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
    nome_maestro = roster_entry["npc_name"] if roster_entry else generate_full_name()
    return nome_maestro, armatura_maestro


def generate_companions(exclude_name: str = "") -> tuple[str, str]:
    """Genera due compagni di addestramento (richiesto in chat: fin
    dall'inizio, non solo per la Prova Finale) - nessuna armatura
    propria, sono aspiranti come il personaggio. Stesso generatore di
    nomi già usato per gli avversari in Arena (coerenti per gruppo
    culturale - richiesto in chat). `exclude_name` evita che un
    compagno finisca per chiamarsi esattamente come il Maestro."""
    exclude = (exclude_name,) if exclude_name else ()
    c1, c2 = generate_distinct_full_names(2, exclude=exclude)
    return c1, c2


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
        "text": ("Il tuo viaggio termina tra {location} - lì, {master}, che porta l'armatura "
                  "{master_armor} come un manto di stelle, ti accoglie senza una sola parola di troppo: "
                  "sarà lui a forgiarti, giorno dopo giorno, nel Cavaliere che sei destinato a diventare, "
                  "se il tuo Cosmo saprà ardere abbastanza da meritare l'armatura {your_armor}. Al suo "
                  "fianco, due ombre incerte quanto la tua: {companion1} e {companion2}, altri due "
                  "aspiranti chiamati dallo stesso destino verso la stessa armatura - solo uno di voi tre, "
                  "quando tutto sarà finito, la indosserà davvero. \"Da oggi\", dice {master}, con una voce "
                  "che non ammette repliche, \"non siete più chi eravate. O diventerete Cavalieri, o non "
                  "sarete stati nulla.\""),
    },
    {
        "type": "choice_check",
        "title": "Le prime fatiche",
        "text": ("Il sole non è ancora sorto e il tuo corpo già urla. Corsa, flessioni, pesi che sembrano "
                  "macigni caduti dal cielo - {companion1} crolla a terra due volte prima di mezzogiorno, "
                  "il fiato spezzato. Il tuo corpo trema quanto il suo. Come rispondi alla fatica che vuole "
                  "spezzarti?"),
        "approaches": [
            {"label": "Spingere il corpo oltre ogni limite", "stat": "con"},
            {"label": "Piegare la fatica con la sola forza della mente", "stat": "vol"},
        ],
        "success_text": ("Qualcosa dentro di te non si spezza, oggi - resisti oltre il punto in cui il "
                          "corpo giurava di doversi fermare. {master} ti osserva un istante di troppo: il "
                          "segno più vicino a un elogio che concederà mai."),
        "failure_text": ("Il corpo cede prima dell'orgoglio - crolli nella polvere, le gambe che tremano "
                          "come rami spezzati dal vento. {master} non dice nulla. Non serve: il silenzio "
                          "pesa più di qualunque parola."),
    },
    {
        "type": "narrative",
        "title": "Cos'è il Cosmo",
        "text": ("\"Tutto ciò che esiste nell'universo\", tuona {master}, la voce carica di un peso quasi "
                  "religioso, \"è fatto delle stesse infinite particelle - le stelle, le montagne, il "
                  "sangue nelle vostre vene. E dentro ognuno di voi arde, sepolto, un piccolo universo "
                  "tutto suo. Quello è il vostro Cosmo. Da oggi, il vostro unico compito è imparare a "
                  "farlo esplodere.\""),
    },
    {
        "type": "choice_check",
        "title": "Il primo tentativo",
        "text": ("Chiudi gli occhi. Cerchi quella scintilla di cui parla {master} - il fuoco che dovrebbe "
                  "ardere sotto la pelle e non arde ancora. Come provi a strapparlo al silenzio del tuo "
                  "stesso corpo?"),
        "approaches": [
            {"label": "Sprofondare nel silenzio più assoluto", "stat": "vol"},
            {"label": "Lasciare che sia il corpo, non la mente, a cercarlo", "stat": "dex"},
        ],
        "success_text": ("Per un solo istante - un battito di ciglia, non di più - qualcosa si muove nel "
                          "profondo del tuo petto. Non è ancora la vera scintilla. Ma per la prima volta, "
                          "sai che esiste."),
        "failure_text": ("Niente. Nessuna aura, nessun calore, solo il silenzio ostinato di un corpo che "
                          "non vuole ancora obbedire. {companion2} ride della propria goffaggine; tu non "
                          "trovi nulla da ridere."),
    },
    {
        "type": "choice_check",
        "title": "La prova dei limiti",
        "text": ("{master} vi conduce oltre ogni confine conosciuto del corpo - non un allenamento, una "
                  "vera prova di sopravvivenza, il tipo che si supera solo quando la mente smette di "
                  "implorare pietà per la carne. Come resisti, quando ogni fibra del tuo corpo ti grida di "
                  "fermarti?"),
        "approaches": [
            {"label": "Stringere i denti e incassare, senza pensare", "stat": "con"},
            {"label": "Aggrapparti alla sola forza della volontà", "stat": "vol"},
        ],
        "success_text": ("Resisti oltre il punto in cui credevi che il tuo corpo dovesse spezzarsi. "
                          "{companion1} ce la fa per un soffio, proprio come te - due sopravvissuti, non "
                          "ancora due Cavalieri."),
        "failure_text": ("Il corpo cede dove la volontà non basta - crolli, sconfitto non da un nemico ma "
                          "dai tuoi stessi limiti. Ci riproverai: non hai altra scelta."),
    },
    {
        "type": "narrative",
        "title": "La scintilla",
        "text": ("Succede quando meno te lo aspetti, come un fulmine a ciel sereno: una fitta al petto, un "
                  "calore che sale dal profondo, e per un istante l'aria stessa intorno a te vibra, "
                  "visibile a occhio nudo. \"Ecco\", dice {master}, quasi senza sorpresa, come se sapesse "
                  "da sempre che sarebbe successo. \"Ora sai cosa cercare. Ora comincia il vero "
                  "addestramento.\""),
    },
    {
        "type": "narrative",
        "title": "Lo studio della prima tecnica",
        "text": ("{master} ti mostra, con la pazienza di chi ha ripetuto lo stesso gesto migliaia di "
                  "volte, i princìpi segreti di {tech1} - non ancora come eseguirla, ma perché esiste: da "
                  "dove nasce il movimento, come il Cosmo vi si deve fondere, cosa deve accadere perché un "
                  "colpo smetta di essere un semplice pugno e diventi qualcosa di più vicino a un "
                  "miracolo."),
    },
    {
        "type": "choice_check",
        "title": "I primi fallimenti",
        "text": ("Provi {tech1} decine, centinaia di volte, cercando quella sensazione che {master} non "
                  "riesce a spiegare a parole - si sente, non si insegna. Come cerchi di afferrarla?"),
        "approaches": [
            {"label": "Ripetere il gesto fino allo sfinimento", "stat": "tec"},
            {"label": "Fermarti a capire prima di colpire ancora", "stat": "vol"},
        ],
        "success_text": ("Qualcosa comincia, finalmente, a funzionare - non ancora perfetto, ma abbastanza "
                          "vicino da farti intuire che la strada è quella giusta."),
        "failure_text": ("Niente. Ancora niente. Troppo debole, o storto, o vuoto della scintilla del "
                          "Cosmo che dovrebbe animarlo. {companion2} osserva e prova a darti consigli che, "
                          "sospetti, non capisce nemmeno lui."),
    },
    {
        "type": "choice_check",
        "title": "La padronanza",
        "text": ("È il momento della verità: dimostrare, una volta per tutte, di aver fatto tua {tech1}. "
                  "Come ti presenti alla prova che deciderà se hai davvero imparato qualcosa?"),
        "approaches": [
            {"label": "Fidarti ciecamente dell'istinto", "stat": "dex"},
            {"label": "Applicare ogni dettaglio con metodo assoluto", "stat": "tec"},
        ],
        "success_text": ("Il movimento è perfetto - corpo, Cosmo, intenzione, tutto fuso nello stesso "
                          "istante irripetibile. {tech1} lascia il segno che deve lasciare, e per un "
                          "momento il mondo intero sembra fermarsi a guardare. {master} annuisce, gli occhi "
                          "che per un istante tradiscono qualcosa di simile all'orgoglio: \"Ora cominci a "
                          "vedere oltre la superficie delle cose.\""),
        "failure_text": ("Ancora no. Manca quella scintilla che rende {tech1} una vera arma, e non solo un "
                          "gesto vuoto ripetuto a memoria. Ci riproverai, e questa volta sarà diverso."),
    },
    {
        "type": "narrative",
        "title": "Lo studio della seconda tecnica",
        "text": ("Con {tech1} ormai scolpita nelle mani, {master} introduce {tech2} - più sottile, più "
                  "subdola della prima, dice, e proprio per questo molto più difficile da domare davvero, "
                  "non solo da eseguire."),
    },
    {
        "type": "choice_check",
        "title": "La pratica",
        "text": ("{tech2} si rifiuta di venire naturale quanto la prima, come se avesse una volontà tutta "
                  "sua. {companion2} sembra impararla più in fretta di te. Come insisti?"),
        "approaches": [
            {"label": "Insistere fino a spezzarti pur di riuscire", "stat": "tec"},
            {"label": "Osservare {master} in silenzio e imitarne ogni respiro", "stat": "vol"},
        ],
        "success_text": ("Qualcosa, finalmente, si sblocca - {tech2} comincia ad avere un senso, anche se "
                          "resta più sfuggente e difficile da domare della prima."),
        "failure_text": ("{companion2} continua a superarti in questo, e per un istante è impossibile non "
                          "lasciarsi mordere dall'invidia più cruda."),
    },
    {
        "type": "choice_check",
        "title": "La seconda padronanza",
        "text": "L'ultimo, decisivo passo prima di poter dire di conoscere davvero {tech2}. Come chiudi il cerchio?",
        "approaches": [
            {"label": "Fidarti della pura forza del corpo", "stat": "str"},
            {"label": "Rifinire ogni dettaglio fino alla perfezione", "stat": "tec"},
        ],
        "success_text": ("Arriva anche questa, alla fine - {tech2} eseguita come deve essere, senza più "
                          "doverci pensare, come se fosse sempre stata parte di te. Due tecniche vere, ora, "
                          "non più solo teoria raccontata da {master}: due armi forgiate nel sangue e nel "
                          "sudore."),
        "failure_text": "{tech2} resta ostinata, un passo oltre la tua portata per oggi. Domani sarà un altro giorno di sangue e sudore.",
    },
    {
        "type": "choice_check",
        "title": "Il Sesto Senso",
        "text": ("\"C'è un modo di percepire il Cosmo altrui\", spiega {master}, la voce che si fa quasi "
                  "un sussurro carico di mistero, \"prima ancora che un colpo parta, prima ancora che un "
                  "nemico si muova.\" Come cerchi di raggiungere questa soglia proibita ai più?"),
        "approaches": [
            {"label": "Aprire la mente al Cosmo che ti circonda", "stat": "vol"},
            {"label": "Affinare all'estremo i sensi del corpo", "stat": "dex"},
        ],
        "success_text": ("Per un solo istante, senti qualcosa muoversi nell'aria prima ancora di vederlo - "
                          "un affinamento dell'attenzione che, ti accorgi con un brivido, avevi già "
                          "cominciato a possedere senza saperlo."),
        "failure_text": "Non senti nulla, per ora - solo il vuoto silenzio di un'attenzione ancora troppo acerba per varcare quella soglia.",
    },
    {
        "type": "choice_check",
        "title": "La prova del dolore",
        "text": ("{master} non concede sconti a nessuno, in questa prova: il corpo che implora di "
                  "fermarsi, la mente che deve imparare a non ascoltarlo senza però smettere di proteggerlo "
                  "dall'autodistruzione. Come resisti al dolore che ti vuole in ginocchio?"),
        "approaches": [
            {"label": "Aggrapparti alla forza pura della volontà", "stat": "vol"},
            {"label": "Distrarre la mente lontano dal dolore del corpo", "stat": "con"},
        ],
        "success_text": ("Resisti, oltre il punto in cui avresti giurato di dover cedere. {companion2} non "
                          "ce la fa al primo tentativo - tu sì, e per un istante ti senti quasi invincibile."),
        "failure_text": ("Il dolore vince, questa volta - ti fermi prima del necessario. Non è una "
                          "sconfitta: è solo un limite che dovrai spostare più in là, con sangue e "
                          "ostinazione."),
    },
    {
        "type": "spar",
        "title": "Fianco a fianco",
        "text": ("Il primo vero scontro fianco a fianco: tu e {companion1} contro {companion2}, a turno, "
                  "in un allenamento che assomiglia sempre più a una battaglia vera. Non è la Prova Finale "
                  "- ma il tuo Cosmo, oggi, non lo sa ancora distinguere."),
    },
    {
        "type": "choice",
        "title": "Il momento di dubbio",
        "text": ("C'è un giorno, verso la fine di questo cammino di sangue e fatica, in cui ti chiedi "
                  "seriamente se sei degno di tutto questo. {master} se ne accorge, e ti lascia scegliere "
                  "come affrontare il fantasma del dubbio."),
        "options": [
            {"label": "Parlarne apertamente con {master}", "bonus_stat": "vol",
             "outcome_text": ("{master} ti ascolta senza interromperti nemmeno una volta, poi pronuncia "
                               "solo una frase, come una sentenza: \"Il dubbio non è debolezza. È debolezza "
                               "lasciare che ti fermi.\" Qualcosa, dentro di te, si assesta per sempre.")},
            {"label": "Sfogarti allenandoti fino a cadere", "bonus_stat": "con",
             "outcome_text": "Non parli con nessuno - ti alleni finché il dubbio non ha più fiato per farsi sentire sopra il rombo del tuo stesso cuore. Funziona, più o meno, come funziona sempre."},
            {"label": "Confidarti con {companion1}", "bonus_stat": None,
             "outcome_text": "Scopri, con un sollievo quasi doloroso, che anche {companion1} porta lo stesso identico fantasma addosso da settimane. Non risolve nulla. Ma pesa molto meno, portato in due."},
        ],
    },
    {
        "type": "choice",
        "title": "Lo stile personale",
        "text": ("Le ultime settimane non aggiungono più nulla di nuovo da imparare - scolpiscono, "
                  "rifiniscono, bruciano via ciò che è superfluo di quello che già possiedi. Come vuoi che "
                  "il tuo Cosmo, da oggi, parli per te in battaglia?"),
        "options": [
            {"label": "Colpire più forte, rischiare tutto", "bonus_stat": "str",
             "outcome_text": "Il tuo stile si fa una lama sola, tagliente e senza esitazioni - ogni colpo cerca di essere quello decisivo, quello che chiude lo scontro per sempre."},
            {"label": "Restare in piedi più a lungo di chiunque altro", "bonus_stat": "con",
             "outcome_text": "Impari a incassare, a resistere, a logorare l'avversario invece di abbatterlo di colpo - una montagna che nessuna tempesta riesce a spostare."},
            {"label": "Anticipare invece di reagire", "bonus_stat": "dex",
             "outcome_text": "Affini l'istinto, il tempismo, il modo in cui senti un colpo arrivare prima ancora che parta davvero - un'ombra che nessuno riesce mai a colpire per prima."},
        ],
    },
    {
        "type": "narrative",
        "title": "L'annuncio",
        "text": ("\"È tempo\", dice {master} una mattina, senza preamboli, la voce che pesa come un "
                  "macigno. \"L'addestramento non prova nulla finché non viene messo davanti alla morte, "
                  "anche solo per finta. Preparati: la Prova Finale è vicina, e da essa non tornerai la "
                  "stessa persona che sei oggi.\""),
    },
    {
        "type": "narrative",
        "title": "L'ultima notte",
        "text": ("La notte prima della Prova Finale, nessuno dei tre dorme davvero. Ripassi ogni tecnica "
                  "nella mente, ripensi a ogni fatica, a ogni caduta, a ogni volta che avresti voluto "
                  "arrenderti e non l'hai fatto - e ti chiedi, con un nodo in gola, se tutto questo "
                  "basterà. {companion1} e {companion2}, in silenzio, fissano lo stesso soffitto, "
                  "chiedendosi la stessa identica cosa."),
    },
    {
        "type": "narrative",
        "title": "La Prova Finale",
        "text": ("È giunto il momento della verità assoluta: tutto quello che hai imparato, tutto quello "
                  "che sei diventato, messo alla prova in un solo, decisivo scontro. Senza reti di "
                  "sicurezza. Senza scuse. Solo il tuo Cosmo, contro tutto il resto."),
    },
]


def _fill_placeholders(text: str, ctx: dict) -> str:
    """Applica i segnaposto {master}/{companion1}/ecc. a una stringa
    qualunque - usata per il testo principale di una tappa, ma anche
    per i testi di successo/fallimento e le opzioni di scelta, che
    hanno la stessa esigenza."""
    return text.format(**ctx)


def build_stage_context(master_name: str, master_armor_name: str, companion1: str,
                         companion2: str, techniques: list[dict], your_armor_name: str = "",
                         own_armor: dict | None = None) -> dict:
    """Costruisce il dizionario dei segnaposto per una tappa - condiviso
    tra render_stage e i nuovi endpoint di prova/scelta (richiesto in
    chat: tutto l'addestramento dev'essere interattivo), così non si
    duplica la stessa logica in più punti. `own_armor`, se fornita,
    aggiunge anche {location} - la location geografica
    dell'addestramento (richiesto in chat)."""
    tech1_name = techniques[0]["name"] if len(techniques) > 0 else "la prima tecnica"
    tech2_name = techniques[1]["name"] if len(techniques) > 1 else "la seconda tecnica"
    location = get_training_location(own_armor, techniques) if own_armor else DEFAULT_TRAINING_LOCATION
    return {
        "master": master_name, "master_armor": master_armor_name, "companion1": companion1,
        "companion2": companion2, "tech1": tech1_name, "tech2": tech2_name, "your_armor": your_armor_name,
        "location": location,
    }


def render_stage(stage_number: int, master_name: str, master_armor_name: str,
                  companion1: str, companion2: str, techniques: list[dict],
                  your_armor_name: str = "", own_armor: dict | None = None) -> dict:
    """Restituisce il contenuto della tappa `stage_number` (1-indicizzata),
    con i nomi veri del personaggio al posto dei segnaposto - la forma
    del contenuto dipende dal 'type' della tappa (narrative/skill_check/
    choice/spar, richiesto in chat: tutto l'addestramento dev'essere
    interattivo, non solo testo da leggere). `own_armor`, se fornita,
    aggiunge anche la location geografica dell'addestramento."""
    stage = TRAINING_STAGES[stage_number - 1]
    ctx = build_stage_context(master_name, master_armor_name, companion1, companion2, techniques, your_armor_name, own_armor)

    result = {
        "stage_number": stage_number, "total_stages": TOTAL_STAGES, "type": stage["type"],
        "title": stage["title"], "text": _fill_placeholders(stage["text"], ctx),
        "master_name": master_name, "master_armor_name": master_armor_name,
        "companion1_name": companion1, "companion2_name": companion2, "your_armor_name": your_armor_name,
        "location": ctx["location"],
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


# --- Location geografica dell'addestramento (richiesto in chat) -----------
# Prima i casi speciali per divinità/fazione (fedeltà al canone dove
# esiste un legame forte e noto), poi si ricade sull'elemento
# prevalente delle tecniche dell'armatura - stessa logica concettuale
# già usata per i temi dell'Arena (Ghiaccio->Siberia ecc.), qui
# applicata all'armatura per cui ci si addestra, non alla provenienza
# del personaggio.
FACTION_TRAINING_LOCATIONS = {}
DIVINITY_TRAINING_LOCATIONS = {
    "Black Saint": "l'Isola della Regina Nera, avvolta in una nebbia che non si dirada mai",
    "Hades": "le gelide profondità ai confini del Regno dei Morti",
    "Nettuno": "gli abissi sommersi del Regno dei Sette Mari",
    "Odino": "le lande ghiacciate di Asgard, sferzate dal vento del nord",
    "Zeus": "le vette perennemente innevate dell'Olimpo",
    "Crono": "un tempio dimenticato dal tempo, ai margini del mondo conosciuto",
    "Saturno": "una fortezza scavata nella roccia più antica della Terra",
    "Eris": "una landa desolata dove regna solo la discordia",
    "Lucifero": "un abisso di fuoco e ombra, lontano da ogni luce",
    "Apollo": "le rive assolate dell'Egeo, dove nasce ogni alba",
    "Artemide": "una foresta sacra dove nessun cacciatore osa entrare",
    "Ares": "un campo di battaglia dimenticato, ancora fumante",
}
ELEMENT_TRAINING_LOCATIONS = {
    "ghiaccio": "le distese ghiacciate della Siberia",
    "fuoco": "le dune infuocate di un deserto senza nome",
    "cosmico": "le colline sacre nei pressi di Atene",
    "fisico": "le rovine di un antico colosseo di pietra",
    "psichico": "l'ombra millenaria di antiche piramidi",
}
DEFAULT_TRAINING_LOCATION = "un luogo la cui posizione esatta nessuno, al di fuori del Santuario, conosce davvero"


def get_training_location(armor: dict, techniques: list[dict]) -> str:
    """La location geografica dell'addestramento per una data armatura
    (richiesto in chat) - fedele al canone dove il legame è forte e
    noto (fazione o divinità), altrimenti dedotta dall'elemento
    prevalente delle sue tecniche vere."""
    if armor["faction"] in FACTION_TRAINING_LOCATIONS:
        return FACTION_TRAINING_LOCATIONS[armor["faction"]]
    if armor["divinity"] in DIVINITY_TRAINING_LOCATIONS:
        return DIVINITY_TRAINING_LOCATIONS[armor["divinity"]]
    for t in techniques:
        tech_type = (t.get("tech_type") or "").lower()
        for element, location in ELEMENT_TRAINING_LOCATIONS.items():
            if element in tech_type:
                return location
    return DEFAULT_TRAINING_LOCATION


def build_opponent_from_armor(conn: sqlite3.Connection, armor_name: str, display_name: str) -> dict:
    """Costruisce un avversario VERO per il motore di combattimento, a
    partire da un'armatura reale del catalogo - stessa forma di
    arena_manager.generate_opponent. Condivisa tra la Prova Finale
    dell'apprendistato e i duelli delle Missioni (richiesto in chat),
    invece di duplicare la stessa logica in più punti. Le tre barre
    (richiesto in chat) ora sono quelle VERE e persistite del PNG, non
    più sempre generate al massimo - un PNG che ha perso un duello di
    recente arriva debole, proprio come farebbe il giocatore. Le
    statistiche str/dex/con/tec/vol (richiesto in chat: "sono tutte
    identiche per ogni PNG a parità di livello armatura - nessuna
    varianza") ora sono quelle VERE e persistite, generate con un
    profilo ineguale invece che uniformi."""
    armor = get_armor(armor_name, conn)
    techniques = [dict(t) for t in get_techniques_for_armor(armor_name, conn)]
    uniform_stat = 10 + armor["level"] // 10  # ripiego, usato solo se il PNG non ha ancora statistiche vere generate

    world_minutes = get_world_minutes(conn)
    roster_entry = apply_npc_regen(conn, armor_name, world_minutes)
    if roster_entry and roster_entry["npc_vita_max"] > 0:
        # Le statistiche vere e persistite (richiesto in chat) - già
        # aggiornate dal recupero nel tempo appena applicato sopra.
        cosmo_cur, cosmo_max = roster_entry["npc_cosmo_cur"], roster_entry["npc_cosmo_max"]
        vita_cur, vita_max = roster_entry["npc_vita_cur"], roster_entry["npc_vita_max"]
        alignment = roster_entry["npc_alignment"] or random_alignment()
    else:
        # Sentinella "mai inizializzato" (non dovrebbe succedere dopo
        # ensure_roster_populated, ma resta un ripiego sicuro) - stessa
        # formula di prima, generata al volo senza persisterla.
        cosmo_cur = cosmo_max = 100 + armor["level"]
        vita_cur = vita_max = 100 + uniform_stat * 2
        alignment = (roster_entry["npc_alignment"] if roster_entry else "") or random_alignment()

    if roster_entry and roster_entry["npc_str"] > 0:
        stat_str, stat_dex, stat_con = roster_entry["npc_str"], roster_entry["npc_dex"], roster_entry["npc_con"]
        stat_tec, stat_vol = roster_entry["npc_tec"], roster_entry["npc_vol"]
    else:
        # Stesso ripiego di sicurezza di sopra - un PNG non ancora
        # migrato alle statistiche vere usa il vecchio valore uniforme.
        stat_str = stat_dex = stat_con = stat_tec = stat_vol = uniform_stat

    return {
        "name": f"{display_name} di {armor_name}",
        "armor_name": armor_name,
        "divinity": armor["divinity"],
        "faction": armor["faction"],
        "armor_level": armor["level"],
        "cosmo_cur": cosmo_cur,
        "cosmo_max": cosmo_max,
        "vita_cur": vita_cur,
        "vita_max": vita_max,
        "str": stat_str,
        "dex": stat_dex,
        "con": stat_con,
        "tec": stat_tec,
        "vol": stat_vol,
        "origin": "",
        "techniques": techniques,
        "alignment": alignment,
        # Marcatore esplicito (richiesto in chat, tre barre vere per i
        # PNG): questo avversario è il PNG CANONICO del roster, non un
        # nome nuovo generato al volo come per gli avversari casuali
        # dell'Arena (core.arena_manager.generate_opponent) - solo per
        # questi ha senso persistere il danno subito, dato che
        # rappresentano sempre la STESSA persona da uno scontro
        # all'altro.
        "is_roster_linked": True,
    }


def generate_trial_opponent(conn: sqlite3.Connection, opponent_is_master: bool, opponent_name: str,
                             master_armor_name: str, player_armor: dict) -> dict:
    """Costruisce l'avversario della Prova Finale (richiesto in chat:
    "fammi combattere davvero", non un tiro di dado narrato) - così la
    Prova Finale usa esattamente lo stesso motore di battaglia di un
    normale scontro in Arena (movimento, tecniche, Contrattacco, tutto).
    Contro il Maestro: la SUA armatura vera, molto più forte.
    Contro un compagno: la STESSA armatura per cui si sta addestrando
    anche il personaggio (corretto in chat: fedeltà al canone - più
    aspiranti competono per la stessa Cloth, non per armature diverse
    - non più "un pari della tua fascia" con un'armatura a caso)."""
    armor_name = master_armor_name if opponent_is_master else player_armor["name"]
    return build_opponent_from_armor(conn, armor_name, opponent_name)
