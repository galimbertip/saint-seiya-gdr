"""Le Missioni (richiesto in chat): una sezione a parte dell'Arena, con
duelli veri E ruolate vere - non solo combattimento. La prima e per ora
unica missione è "La Scalata delle Dodici Case": l'ordine delle Case è
fisso (è proprio il punto, fedele al canone), ma ad OGNI Casa c'è un
vero bivio - tentare di convincere il Guardiano a lasciarti passare, o
sfidarlo subito a duello.

I Guardiani non sono generati a caso - sono i PNG già esistenti in
Gerarchia per quell'armatura (stesso principio del Maestro
nell'apprendistato).

Testo interamente originale, ispirato ai segni zodiacali che danno il
nome alle Case (senza riprendere personaggi o scene specifiche
dell'opera originale)."""

import json
import random
import sqlite3

from database.db_manager import get_roster_entry, get_armor
from core.training_path import build_opponent_from_armor
from core.arena_manager import generate_opponent, generate_opponent_candidates
from core.alignment import ALIGNMENT_PERSUASION_MODIFIER, persuasion_flavor_line

MISSION_ID = "dodici_case"
TOTAL_HOUSES = 12

# L'ordine è fisso e noto (fedeltà al canone, richiesto in chat) - non
# si diramano le CASE, si diramano le SCELTE dentro ciascuna.
HOUSE_ORDER = [
    "Ariete", "Toro", "Gemelli", "Cancro", "Leone", "Vergine",
    "Bilancia", "Scorpione", "Sagittario", "Capricorno", "Acquario", "Pesci",
]

PERSUADE_STAT = "vol"
PERSUADE_THRESHOLD = 15  # un filo più dura delle prove d'addestramento - qui sei di fronte a un Gold Saint

# Ricompensa a scalata completata (richiesto in chat: Cosmo/denaro,
# indipendentemente da quante Case hai parlato invece di combattuto).
# PLACEHOLDER come le altre formule di bilanciamento di questo
# progetto, mai tarata sul serio.
COSMO_MAX_REWARD = 30
DENARO_REWARD = 500

HOUSES = {
    "Ariete": {
        "arrival": ("La prima Casa si apre davanti a te senza porte né guardie visibili - solo un "
                    "silenzio innaturale, carico di attesa. {guardian} ti osserva da lontano, immobile, "
                    "come se ti conoscesse già da prima che tu nascessi."),
        "persuade_prompt": "Il suo sguardo non è ostile - solo valutativo. Provi a parlargli?",
        "persuade_success": ("\"Chi supera questa Casa senza spargere sangue\", dice {guardian}, quasi tra "
                              "sé, \"ha già dimostrato qualcosa che molti non capiscono mai.\" Si scosta, e "
                              "la strada verso la Casa successiva si apre."),
        "persuade_failure": ("{guardian} scuote appena la testa. \"Le parole non bastano, qui. Dimostralo "
                              "con il Cosmo, non con la lingua.\" Non c'è più spazio per parlare."),
        "duel_intro": "{guardian} si mette in guardia, calmo come chi ha già vinto mille volte questo stesso scontro.",
    },
    "Toro": {
        "arrival": ("La seconda Casa trema sotto i tuoi passi prima ancora che tu ne varchi la soglia - "
                    "come se il pavimento stesso riconoscesse il peso di chi vi cammina sopra. {guardian} "
                    "ti aspetta al centro della sala, una montagna di muscoli e Cosmo represso."),
        "persuade_prompt": "Non sembra il tipo che si lascia convincere facilmente. Ci provi comunque?",
        "persuade_success": ("{guardian} scoppia in una risata profonda, quasi affettuosa. \"Hai più "
                              "coraggio a parlarmi così che a sfidarmi. Passa, ragazzo. Oggi mi hai "
                              "divertito abbastanza.\""),
        "persuade_failure": ("\"Nessuno passa la Casa del Toro senza sudare\", ringhia {guardian}, gli "
                              "occhi che si accendono di una luce pericolosa. \"Nemmeno con le parole più "
                              "dolci del mondo.\""),
        "duel_intro": "{guardian} pianta i piedi a terra come radici - una forza che sembra impossibile da spostare.",
    },
    "Gemelli": {
        "arrival": ("La terza Casa gioca con i tuoi sensi fin dal primo passo - corridoi che sembrano "
                    "girare su se stessi, ombre che si muovono senza una fonte di luce. {guardian} appare "
                    "e scompare più volte prima di fermarsi davvero, come se stesse decidendo quale "
                    "versione di sé mostrarti."),
        "persuade_prompt": "Con qualcuno che gioca sempre su due piani, capire quale sia sincero è la sfida vera. Tenti il dialogo?",
        "persuade_success": ("\"Interessante\", mormora {guardian}, il volto per un istante privo di "
                              "qualunque maschera. \"Hai visto oltre l'illusione senza nemmeno provarci. "
                              "Vai pure - ti sei guadagnato la sincerità, almeno per oggi.\""),
        "persuade_failure": ("{guardian} sorride, ma è un sorriso che non promette nulla di buono. "
                              "\"Le parole, qui, valgono meno di un'illusione ben fatta. Vediamo cosa vale "
                              "il tuo Cosmo, invece.\""),
        "duel_intro": "La sala intera sembra sdoppiarsi per un istante, e {guardian} attacca da una direzione che non ti aspettavi.",
    },
    "Cancro": {
        "arrival": ("La quarta Casa accoglie con un freddo che non ha nulla a che fare con la temperatura "
                    "- l'aria stessa sa di qualcosa di sepolto da tempo. {guardian} siede su un trono di "
                    "pietra scura, circondato da un silenzio che sembra inghiottire ogni suono."),
        "persuade_prompt": "Qui la morte sembra di casa più della vita. Provi comunque a farti ascoltare?",
        "persuade_success": ("{guardian} ti fissa a lungo, come se stesse pesando la tua anima sulla "
                              "bilancia. \"Raro, chi entra qui senza tremare. Va'. Non tutti meritano di "
                              "finire in questa Casa prima del tempo.\""),
        "persuade_failure": ("\"Questa è la Casa dei morti\", sussurra {guardian}, quasi con dolcezza. "
                              "\"E i morti non ascoltano suppliche.\""),
        "duel_intro": "{guardian} si alza dal trono con un movimento lento, quasi cerimoniale, come se il duello fosse già un funerale annunciato.",
    },
    "Leone": {
        "arrival": ("La quinta Casa ruggisce di orgoglio ancora prima che tu ne veda il padrone - "
                    "colonne dorate, un calore quasi solare che ti avvolge appena metti piede oltre la "
                    "soglia. {guardian} ti aspetta a petto nudo, la fierezza scolpita in ogni muscolo."),
        "persuade_prompt": "L'orgoglio, qui, è tutto. Provi a fare leva su quello, invece che sulla forza?",
        "persuade_success": ("{guardian} scoppia in una risata piena, sincera. \"Mi piace chi ha il "
                              "coraggio di parlarmi negli occhi invece di tremare. Passa pure - non hai "
                              "nulla da dimostrarmi oggi.\""),
        "persuade_failure": ("\"Un vero Leone\", dice {guardian}, gli occhi che si accendono, \"non lascia "
                              "passare nessuno senza prima vedere di cosa è fatto.\""),
        "duel_intro": "{guardian} avanza senza fretta, la certezza di chi non ha mai davvero temuto un avversario.",
    },
    "Vergine": {
        "arrival": ("La sesta Casa è immersa in un silenzio quasi sacro - nessun rumore, nessun movimento, "
                    "solo {guardian}, seduto in meditazione, gli occhi chiusi come se il mondo esterno non "
                    "lo riguardasse più."),
        "persuade_prompt": "Sembra già altrove, oltre le cose terrene. Tenti comunque di raggiungerlo con le parole?",
        "persuade_success": ("{guardian} apre gli occhi solo per un istante. \"Chi cerca la verità con "
                              "sincerità\", dice, la voce piatta e serena, \"non ha bisogno di attraversare "
                              "il dolore per meritare di proseguire.\" Torna a chiudere gli occhi: il "
                              "cammino è libero."),
        "persuade_failure": ("\"Le parole sono ombre della verità\", risponde {guardian} senza aprire "
                              "nemmeno gli occhi. \"Solo nel combattimento un'anima si rivela davvero.\""),
        "duel_intro": "{guardian} si alza con un movimento fluido, quasi distaccato, come se il duello stesso fosse solo un altro esercizio di meditazione.",
    },
    "Bilancia": {
        "arrival": ("La settima Casa è dominata da un'enorme bilancia sospesa nel vuoto, i piatti "
                    "perfettamente in equilibrio. {guardian} vi si erge accanto, il volto impossibile da "
                    "leggere, come se stesse già soppesando ogni tua singola azione passata."),
        "persuade_prompt": "Qui tutto viene giudicato, pesato, misurato. Provi a perorare la tua causa?",
        "persuade_success": ("La bilancia oscilla appena, poi si assesta. \"L'equilibrio\", dice "
                              "{guardian}, \"non richiede sempre sangue per essere rispettato. Vai - il "
                              "tuo piatto pende dalla parte giusta, per oggi.\""),
        "persuade_failure": ("\"Le parole sono leggere\", dice {guardian}, osservando la bilancia restare "
                              "immobile. \"Solo le azioni hanno un vero peso, qui.\""),
        "duel_intro": "{guardian} si mette in posizione con la precisione fredda di chi valuta ogni mossa come se fosse già scritta su una bilancia invisibile.",
    },
    "Scorpione": {
        "arrival": ("L'ottava Casa è la più temuta di tutte, e lo capisci nell'istante stesso in cui la "
                    "attraversi - un veleno invisibile sembra impregnare l'aria stessa. {guardian} ti "
                    "aspetta con un sorriso che non promette nulla di buono."),
        "persuade_prompt": "L'orgoglio dello Scorpione è leggendario quanto il suo veleno. Ci provi comunque a ragionare con lui?",
        "persuade_success": ("{guardian} inclina la testa, quasi sorpreso. \"Nessuno mi aveva mai parlato "
                              "così, in questa Casa. Rispetto il coraggio più della supplica. Vai pure - "
                              "oggi ti risparmio il veleno.\""),
        "persuade_failure": ("\"Il mio orgoglio\", sibila {guardian}, \"non si piega a nessuna parola. Solo "
                              "il Cosmo può convincermi a lasciarti passare - vinto, non chiesto.\""),
        "duel_intro": "{guardian} solleva la mano come se già stringesse un pungiglione invisibile, gli occhi carichi di un orgoglio feroce.",
    },
    "Sagittario": {
        "arrival": ("La nona Casa profuma d'onore più che di pietra - stendardi, archi appesi alle pareti "
                    "come trofei di battaglie vinte con lealtà. {guardian} ti accoglie a viso scoperto, "
                    "senza trucchi né ombre."),
        "persuade_prompt": "Qui l'onore conta più di tutto. Provi a fare appello proprio a quello?",
        "persuade_success": ("{guardian} annuisce lentamente, gli occhi che brillano d'approvazione. "
                              "\"Chi mi parla con onestà merita onestà in cambio. Vai pure - hai già vinto "
                              "la prova più importante, quella del carattere.\""),
        "persuade_failure": ("\"L'onore\", dice {guardian}, la voce ferma ma non ostile, \"si dimostra "
                              "nell'azione, non nelle parole. E io devo vedere il tuo, prima di lasciarti "
                              "proseguire.\""),
        "duel_intro": "{guardian} solleva un arco invisibile fatto di puro Cosmo, la mira già puntata su di te.",
    },
    "Capricorno": {
        "arrival": ("La decima Casa è austera, spoglia, priva di qualunque fronzolo - solo pietra nuda e "
                    "una disciplina che si respira nell'aria stessa. {guardian} ti aspetta in una postura "
                    "perfettamente immobile, come se fosse scolpito nella roccia."),
        "persuade_prompt": "La disciplina ferrea di questa Casa non lascia molto spazio alle parole. Tenti comunque?",
        "persuade_success": ("\"La disciplina\", dice {guardian}, senza muovere un muscolo, \"si riconosce "
                              "anche nelle parole, quando sono sincere. Vai - hai dimostrato più controllo "
                              "di molti che ho visto combattere.\""),
        "persuade_failure": ("\"Solo il ferro riconosce il ferro\", risponde {guardian}, immobile. \"Le "
                              "parole si piegano troppo facilmente per convincermi di qualcosa.\""),
        "duel_intro": "{guardian} non si muove nemmeno quando ti avvicini - un muro di disciplina e Cosmo che aspetta solo il momento giusto per colpire.",
    },
    "Acquario": {
        "arrival": ("L'undicesima Casa è gelida in un modo che va oltre la temperatura - un freddo "
                    "assoluto, quasi cosmico, che sembra rallentare persino i tuoi pensieri. {guardian} ti "
                    "osserva con un distacco totale, come se nulla al mondo potesse davvero toccarlo."),
        "persuade_prompt": "Un cuore così freddo sembra impossibile da scaldare con le parole. Ci provi comunque?",
        "persuade_success": ("{guardian} resta impassibile, ma qualcosa nei suoi occhi si ammorbidisce "
                              "appena. \"Raro, un calore sincero in un luogo come questo. Vai pure - il "
                              "gelo, oggi, non ti riguarda.\""),
        "persuade_failure": ("\"Il calore delle parole\", dice {guardian}, la voce piatta come ghiaccio, "
                              "\"si spegne facilmente qui. Vedremo se il tuo Cosmo resiste meglio.\""),
        "duel_intro": "L'aria intorno a {guardian} si fa visibilmente più fredda, come se lo zero assoluto stesso si preparasse a colpire.",
    },
    "Pesci": {
        "arrival": ("L'ultima Casa prima del trono di Athena è la più ingannevole di tutte - un giardino "
                    "di fiori splendidi il cui profumo nasconde un veleno mortale. {guardian} cammina tra "
                    "quei fiori con una grazia quasi innaturale, bellissimo e pericoloso in egual misura."),
        "persuade_prompt": "La bellezza di questo luogo nasconde la sua vera natura. Provi a guardare oltre, e a parlargli?",
        "persuade_success": ("{guardian} si ferma tra i fiori, un'espressione quasi malinconica sul volto. "
                              "\"Non capita spesso che qualcuno veda oltre il profumo dei miei fiori. Vai "
                              "pure - sei l'ultima prova prima del trono, e l'hai già superata a modo tuo.\""),
        "persuade_failure": ("\"Anche i fiori più belli\", dice {guardian}, cogliendone uno con delicatezza "
                              "innaturale, \"nascondono spine che nessuna parola può disarmare.\""),
        "duel_intro": "{guardian} solleva un fiore che sembra innocuo quanto qualunque altro - sai già che non lo è.",
    },
}


def get_house_guardian(conn: sqlite3.Connection, house_armor_name: str) -> str:
    """Il Guardiano di una Casa - il PNG già esistente in Gerarchia per
    quell'armatura (richiesto in chat, stesso principio del Maestro
    nell'apprendistato: non generato a caso)."""
    entry = get_roster_entry(conn, house_armor_name)
    return entry["npc_name"] if entry else f"{random.choice(['Marco', 'Elena', 'Kenji'])} Ignoto"


def resolve_persuasion(knight: dict, guardian_alignment: str = "") -> bool:
    """Un vero tiro di dado per il tentativo di persuasione (richiesto
    in chat: la possibilità di convincere un Guardiano a lasciarti
    passare senza combattere) - un filo più dura delle prove
    dell'addestramento, qui sei di fronte a un Gold Saint.
    `guardian_alignment` (richiesto in chat, stile D&D): l'allineamento
    vero del Guardiano sposta la soglia - un PNG più Buono è più
    ricettivo, uno più Malvagio più cinico. Prima ogni Guardiano aveva
    la STESSA soglia, motivo per cui la Scalata si poteva risolvere
    per intero con la sola diplomazia (segnalato in chat)."""
    modifier = ALIGNMENT_PERSUASION_MODIFIER.get(guardian_alignment, 0)
    roll = random.randint(1, 20) + knight[PERSUADE_STAT] // 2
    return roll >= PERSUADE_THRESHOLD + modifier


def get_house_content(house_number: int, guardian_name: str) -> dict:
    """Il contenuto testuale della Casa `house_number` (1-12), con il
    nome vero del Guardiano al posto del segnaposto."""
    house_name = HOUSE_ORDER[house_number - 1]
    content = HOUSES[house_name]
    return {
        "house_number": house_number, "total_houses": TOTAL_HOUSES, "house_name": house_name,
        "guardian_name": guardian_name,
        "arrival": content["arrival"].format(guardian=guardian_name),
        "persuade_prompt": content["persuade_prompt"],
        "persuade_success": content["persuade_success"].format(guardian=guardian_name),
        "persuade_failure": content["persuade_failure"].format(guardian=guardian_name),
        "duel_intro": content["duel_intro"].format(guardian=guardian_name),
    }


# --- Seconda missione: "Le Colonne dei Sette Mari" -----------------------
# Richiesta in chat: a differenza della Scalata (ordine fisso, fedele
# al canone), qui i bivi portano DAVVERO a strade diverse - un vero
# grafo di nodi, non solo lo stesso percorso con un bivio laterale ad
# ogni tappa. Una scelta iniziale (ingresso aperto o passaggio
# nascosto) porta a nodi diversi che poi si ricongiungono prima della
# scelta morale centrale (liberare il prigioniero o no - con una
# conseguenza vera, ritardata, sul finale), e infine lo scontro
# decisivo contro Triton.
COLONNE_MISSION_ID = "colonne_sette_mari"
COLONNE_START_NODE = "arrivo"

SEA_GENERAL_ARMORS = [
    "Scale del Dragone Marino", "Scale delle Sirene (Siren)", "Scale di Chrysaor",
    "Scale di Kraken", "Scale di Scylla", "Scale di Lymnades", "Scale del Cavallo Marino (Sea Horse)",
]
TRITON_ARMOR = "Scale di Triton"

ASGARD_MISSION_ID = "gelo_di_valhalla"
ASGARD_START_NODE = "arrivo"

GOD_WARRIOR_ARMORS = [
    "God Robe di Alfa (Dubhe)", "God Robe di Beta (Merak)", "God Robe di Gamma (Phecda)",
    "God Robe di Delta (Megrez)", "God Robe di Epsilon (Alioth)", "God Robe di Zeta (Mizar)",
    "God Robe di Zeta Ombra (Alcor)", "God Robe di Eta (Benetnasch)", "God Robe di Gullinbursti",
    "God Robe di Midgard", "God Robe di Hræsvelgr", "God Robe di Grani", "God Robe di Níðhöggr",
    "God Robe di Tanngrisnir", "God Robe di Eikþyrnir", "God Robe di Garmr", "God Robe di Gryphon",
]
ODIN_ARMOR = "God Robe Divina di Odino"

COLONNE_NODES = {
    "arrivo": {
        "type": "choice",
        "text": ("Le acque cambiano colore ben prima che tu veda le Colonne dei Sette Mari emergere "
                  "dall'oscurità dell'abisso - un tempio sommerso che sembra respirare di luce propria, "
                  "come se fosse vivo. Come vuoi avvicinarti?"),
        "options": [
            {"label": "Entrare apertamente dalle Colonne principali", "next": "guardia_principale",
             "outcome_text": ("Decidi di non nasconderti. Se il Regno di Poseidone vuole fermarti, dovrà "
                               "farlo alla luce - o a quel poco di luce che filtra fin quaggiù.")},
            {"label": "Cercare un passaggio nascosto sotto le correnti", "next": "passaggio_nascosto",
             "outcome_text": ("La cautela, questa volta, ti sembra la scelta più saggia. Ti immergi più a "
                               "fondo, lasciando che le correnti ti inghiottano nell'oscurità.")},
        ],
    },
    "guardia_principale": {
        "type": "duel",
        "armor_pool": SEA_GENERAL_ARMORS,
        "intro": ("{guardian}, uno dei sette Generali degli Abissi, ti aspetta proprio davanti al "
                   "cancello - nessuna sorpresa, nessun inganno: solo la forza pura del mare al suo comando."),
        "win_next": "prigioniero",
        "lose_next": "guardia_principale",
    },
    "passaggio_nascosto": {
        "type": "skill_check",
        "stat": "dex",
        "text": ("Le correnti sotterranee sono un labirinto che pochi conoscono - ti muovi con la massima "
                  "cautela, cercando di non farti notare dalle sentinelle che pattugliano l'oscurità."),
        "success_text": ("Scivoli tra le correnti come un'ombra silenziosa - nessuno sembra essersi "
                          "accorto di te. Il cuore del tempio è ormai a portata di mano."),
        "failure_text": ("Una corrente ti tradisce proprio quando credevi di essere quasi passato - le "
                          "acque si agitano, e sai già cosa significa."),
        "success_next": "prigioniero",
        "failure_next": "imboscata",
    },
    "imboscata": {
        "type": "duel",
        "armor_pool": SEA_GENERAL_ARMORS,
        "intro": ("Le correnti si agitano intorno a te: sei stato scoperto. {guardian} emerge "
                   "dall'oscurità con la furia di chi non ama gli intrusi silenziosi più di quelli aperti."),
        "win_next": "prigioniero",
        "lose_next": "imboscata",
    },
    "prigioniero": {
        "type": "choice",
        "text": ("Oltre un cancello di corallo pietrificato, scorgi una figura incatenata da chissà "
                  "quanto tempo - un marinaio, forse un Cavaliere caduto in disgrazia. Ti implora con gli "
                  "occhi, prima ancora che con le parole, di liberarlo."),
        "options": [
            {"label": "Fermarti a liberarlo, a rischio di perdere tempo prezioso", "next": "duello_finale", "flag": "helped_prisoner",
             "outcome_text": ("Ti fermi, nonostante il rischio, e spezzi le catene con un colpo secco. Il "
                               "prigioniero ti guarda incredulo, poi sparisce tra le correnti senza una "
                               "parola - ma qualcosa nei suoi occhi promette che non dimenticherà.")},
            {"label": "Ignorarlo e proseguire verso il cuore del tempio", "next": "duello_finale",
             "outcome_text": ("Ti volti dall'altra parte e prosegui. Non è il momento per le distrazioni, "
                               "ti dici - anche se qualcosa, dentro, non ne è del tutto convinto.")},
        ],
    },
    "duello_finale": {
        "type": "duel",
        "armor": TRITON_ARMOR,
        "intro": ("{guardian} ti attende nella sala del trono, la fedeltà a Poseidone incisa in ogni "
                   "singolo gesto. Non è un Generale come gli altri: è l'ultima, vera barriera prima del "
                   "cuore del Regno dei Sette Mari."),
        "win_next": "fine",
        "lose_next": "duello_finale",
    },
    "fine": {
        "type": "ending",
        "text": ("Triton cade in ginocchio, la Cloth incrinata ma lo sguardo ancora fiero. Le Colonne dei "
                  "Sette Mari sono, per oggi, tue da attraversare. Il Regno di Poseidone ricorderà il tuo "
                  "nome."),
        "text_with_flag": {
            "helped_prisoner": ("Triton cade in ginocchio, la Cloth incrinata. Alle tue spalle, il "
                                 "prigioniero che hai liberato ti raggiunge, ancora debole ma vivo: "
                                 "\"Non dimenticherò questo\", dice, prima di sparire tra le correnti. Le "
                                 "Colonne dei Sette Mari sono, per oggi, tue da attraversare - e qualcuno, "
                                 "da qualche parte, ti deve ancora un debito."),
        },
        "bonus_with_flag": {"helped_prisoner": {"denaro": 150}},
    },
}

ASGARD_NODES = {
    "arrivo": {
        "type": "choice",
        "text": ("L'aria si fa gelida ben prima che tu scorga Valhalla - un palazzo di ghiaccio che sembra "
                  "scolpito dal cielo stesso, sotto un'aurora che non smette mai di ardere. Come vuoi "
                  "avvicinarti?"),
        "options": [
            {"label": "Attraversare apertamente il Ponte di Ghiaccio", "next": "guardia_del_ponte",
             "outcome_text": ("Scegli la strada diretta. Se Asgard vuole fermarti, che lo faccia alla luce "
                               "dell'aurora, non nell'ombra.")},
            {"label": "Scendere nelle grotte glaciali sotto il palazzo", "next": "passaggio_nascosto",
             "outcome_text": ("Il gelo delle grotte è un rischio in sé, ma meglio quello che farsi notare "
                               "prima ancora di aver capito con chi hai a che fare.")},
        ],
    },
    "guardia_del_ponte": {
        "type": "duel",
        "armor_pool": GOD_WARRIOR_ARMORS,
        "intro": ("{guardian}, un Guerriero Divino, ti sbarra il Ponte di Ghiaccio - la sua God Robe "
                   "risuona di un potere antico, che sembra provenire dal cielo stesso più che dalla terra."),
        "win_next": "bracciale",
        "lose_next": "guardia_del_ponte",
    },
    "passaggio_nascosto": {
        "type": "skill_check",
        "stat": "con",
        "text": ("Le grotte sotto Valhalla sono uno scheletro di ghiaccio scavato da correnti d'aria "
                  "gelide - resistere al freddo, qui, conta più della velocità o della forza."),
        "success_text": ("Il tuo corpo regge il gelo più a lungo di quanto pensassi - attraversi le grotte "
                          "senza che nessuno se ne accorga."),
        "failure_text": ("Il freddo ti tradisce proprio a metà strada: un tremito, un passo falso, e il "
                          "rumore che ne segue non passa inosservato."),
        "success_next": "bracciale",
        "failure_next": "imboscata_glaciale",
    },
    "imboscata_glaciale": {
        "type": "duel",
        "armor_pool": GOD_WARRIOR_ARMORS,
        "intro": ("Il gelo stesso sembra essersi mosso per intrappolarti: sei stato scoperto. {guardian} "
                   "emerge dalle grotte, la God Robe che scintilla di un freddo tagliente quanto la sua "
                   "ostilità."),
        "win_next": "bracciale",
        "lose_next": "imboscata_glaciale",
    },
    "bracciale": {
        "type": "choice",
        "text": ("Incastonato in un blocco di ghiaccio millenario, scorgi un frammento del Bracciale del "
                  "Nibelungen - dicono che chi lo indossa attinga a un potere immenso, e che quel potere, "
                  "prima o poi, pretenda un prezzo."),
        "options": [
            {"label": "Prendere il frammento e sentirne subito la potenza", "next": "duello_finale", "flag": "used_ring_power",
             "outcome_text": ("Lo stacchi dal ghiaccio, e nell'istante in cui lo sfiori un calore innaturale "
                               "ti attraversa il braccio - potere vero, ma con un retrogusto che non ti "
                               "convince del tutto.")},
            {"label": "Lasciarlo intatto, diffidando di un potere che sa già di inganno", "next": "duello_finale",
             "outcome_text": ("Ti allontani dal blocco di ghiaccio senza toccarlo. Qualunque cosa prometta, "
                               "preferisci restare quello che sei.")},
        ],
    },
    "duello_finale": {
        "type": "duel",
        "armor": ODIN_ARMOR,
        "intro": ("{guardian} ti attende nella sala del trono di Valhalla, avvolto dal Cosmo di Odino "
                   "stesso. Non è un Guerriero Divino come gli altri: è l'ultima, vera barriera prima del "
                   "cuore gelato di Asgard."),
        "win_next": "fine",
        "lose_next": "duello_finale",
    },
    "fine": {
        "type": "ending",
        "text": ("Il Guerriero Divino cade in ginocchio sul ghiaccio, la God Robe incrinata ma lo sguardo "
                  "ancora fiero. Valhalla è, per oggi, tua da attraversare. Il Regno di Asgard ricorderà il "
                  "tuo nome."),
        "text_with_flag": {
            "used_ring_power": ("Il Guerriero Divino cade in ginocchio, ma la tua stessa vittoria ti lascia "
                                 "un retrogusto amaro: il potere del Bracciale del Nibelungen ha lasciato un "
                                 "segno che non svanirà in fretta. Valhalla è, per oggi, tua da attraversare "
                                 "- ma qualcosa, dentro di te, non è più del tutto come prima."),
        },
        "bonus_with_flag": {"used_ring_power": {"denaro": 200}},
    },
}


# Il registro delle missioni a grafo (richiesto in chat: "molte più
# missioni" - da qui in avanti, aggiungerne una nuova significa solo
# scrivere il grafo dei nodi e registrarlo qui, non duplicare la
# logica di gestione altrove come succedeva prima con le Colonne).
GRAPH_MISSIONS = {
    COLONNE_MISSION_ID: {"start_node": COLONNE_START_NODE, "nodes": COLONNE_NODES, "name": "Le Colonne dei Sette Mari"},
    ASGARD_MISSION_ID: {"start_node": ASGARD_START_NODE, "nodes": ASGARD_NODES, "name": "Il Gelo di Valhalla"},
}

# I tornei (richiesto in chat: "struttura diversa da Nettuno", niente
# grafo di nodi - un vero tabellone a eliminazione diretta, come le
# Guerre Galattiche canoniche). Perdere un round NON permette di
# ritentare (a differenza della Scalata e delle missioni a grafo) - un
# torneo a eliminazione diretta è, per definizione, senza seconde
# possibilità: qui sta la vera differenza di "modus operandi" chiesta
# in chat, non solo un'ambientazione diversa sullo stesso schema.
GALAXIAN_WARS_ID = "galaxian_wars"
FREE_TOURNAMENT_ID = "torneo_stelle_libere"

TOURNAMENT_MISSIONS = {
    GALAXIAN_WARS_ID: {
        "name": "Le Guerre Galattiche",
        "rounds": 3,
        "eligible_faction": "Bronze Saint",  # richiesto in chat: solo per i Bronze Saint, fedele al canone
        "opponent_faction": "Bronze Saint",
        "reward_denaro_per_round": 100,
        "reward_denaro_champion": 500,
        "reward_cosmo_max_champion": 20,
    },
    FREE_TOURNAMENT_ID: {
        "name": "Il Torneo delle Stelle Libere",
        "rounds": 4,
        "eligible_faction": None,  # richiesto in chat: iscrizione libera, indipendente dalla casta
        "opponent_faction": None,  # usa il pool normale per livello, non una fazione fissa
        "reward_denaro_per_round": 150,
        "reward_denaro_champion": 800,
        "reward_cosmo_max_champion": 30,
    },
}

TOURNAMENT_ROUND_NAMES = {1: "primo turno", 2: "secondo turno", 3: "semifinale", 4: "finale"}


def tournament_round_label(tournament_id: str, round_number: int) -> str:
    """Il nome del round in base a quanti ne mancano alla fine
    (richiesto implicito: l'ultimo round di un torneo a 3 è la
    "semifinale" solo se il torneo ne ha 4 in tutto - la finale è
    sempre l'ULTIMO, qualunque sia il numero totale di round)."""
    total = TOURNAMENT_MISSIONS[tournament_id]["rounds"]
    if round_number == total:
        return "finale"
    if round_number == total - 1:
        return "semifinale"
    return f"{round_number}º turno"


def tournament_round_label_with_preposition(tournament_id: str, round_number: int) -> str:
    """Come tournament_round_label, ma con "al"/"alla" già corretto
    davanti (bug corretto in chat: "semifinale" e "finale" sono
    femminili in italiano, "turno" è maschile - "al semifinale" era
    sgrammaticato)."""
    label = tournament_round_label(tournament_id, round_number)
    preposition = "alla" if label in ("semifinale", "finale") else "al"
    return f"{preposition} {label}"


def is_eligible_for_tournament(conn: sqlite3.Connection, knight: dict, tournament_id: str) -> bool:
    """Se questo personaggio può iscriversi al torneo `tournament_id`
    (richiesto in chat: Le Guerre Galattiche solo per i Bronze Saint,
    l'altro torneo aperto a chiunque)."""
    required_faction = TOURNAMENT_MISSIONS[tournament_id]["eligible_faction"]
    if required_faction is None:
        return True
    armor = get_armor(knight["armor_name"], conn)
    return armor is not None and armor["faction"] == required_faction


def generate_tournament_bracket(conn: sqlite3.Connection, knight: dict, tournament_id: str) -> dict:
    """Genera l'INTERO tabellone all'iscrizione (richiesto in chat: "non
    si conosce i partecipanti, il tabellone" - non più un avversario
    pescato alla cieca ad ogni round). Il percorso "fantasma" degli
    altri partecipanti (chi affronta chi, chi vince) è già simulato
    con un confronto di livello - solo il PROPRIO percorso del
    giocatore resta scritto man mano che gioca sul serio. Per la
    visualizzazione, il giocatore viene sempre mostrato come vincitore
    del proprio incontro nei round successivi (se perde per davvero il
    torneo finisce comunque lì, il tabellone mostrato in quel caso
    semplicemente non conterà più)."""
    settings = TOURNAMENT_MISSIONS[tournament_id]
    total_rounds = settings["rounds"]
    total_slots = 2 ** total_rounds

    if settings["opponent_faction"]:
        rows = conn.execute(
            "SELECT * FROM armors WHERE faction = ? AND name != ?",
            (settings["opponent_faction"], knight["armor_name"]),
        ).fetchall()
        pool = list(rows)
        random.shuffle(pool)
        opponent_armors = []
        for row in pool[:total_slots - 1]:
            guardian_name = get_house_guardian(conn, row["name"])
            opponent_armors.append({"name": f"{guardian_name} di {row['name']}", "armor_name": row["name"], "level": row["level"]})
    else:
        player_armor = get_armor(knight["armor_name"], conn)
        candidates = generate_opponent_candidates(
            conn, player_armor["level"], exclude_armor_name=knight["armor_name"], count=total_slots - 1
        )
        opponent_armors = [{"name": c["name"], "armor_name": c["armor_name"], "level": c["armor_level"]} for c in candidates]

    # Se il catalogo non basta per riempire tutti gli slot con nomi
    # distinti (es. Le Guerre Galattiche con pochi Bronze Saint
    # disponibili), si ripete pur di riempire il tabellone.
    while opponent_armors and len(opponent_armors) < total_slots - 1:
        opponent_armors.append(random.choice(opponent_armors))

    player_armor_row = get_armor(knight["armor_name"], conn)
    player_display_name = f"{knight['raw_name']} {knight['surname']}".strip()
    slots = [{"name": player_display_name, "armor_name": knight["armor_name"],
              "level": player_armor_row["level"], "is_player": True}]
    for opp in opponent_armors[:total_slots - 1]:
        slots.append({**opp, "is_player": False})
    random.shuffle(slots)
    player_slot = next(i for i, s in enumerate(slots) if s["is_player"])

    rounds = []
    current_slots = list(range(total_slots))
    for _round_num in range(total_rounds):
        matches = [[current_slots[i], current_slots[i + 1]] for i in range(0, len(current_slots), 2)]
        winners = []
        for a, b in matches:
            if a == player_slot or b == player_slot:
                winners.append(player_slot)
            else:
                level_a, level_b = slots[a]["level"], slots[b]["level"]
                total = max(level_a + level_b, 1)
                winners.append(a if random.random() < level_a / total else b)
        rounds.append({"matches": matches, "winners": winners})
        current_slots = winners

    return {"slots": slots, "player_slot": player_slot, "rounds": rounds, "total_rounds": total_rounds}


def save_tournament_bracket(knight: dict, bracket: dict) -> None:
    """Serializza il tabellone dentro il campo tournament_bracket
    (richiesto in chat) - il chiamante resta comunque responsabile di
    save_knight() per persisterlo davvero."""
    knight["tournament_bracket"] = json.dumps(bracket)


def load_tournament_bracket(knight: dict) -> dict | None:
    if not knight.get("tournament_bracket"):
        return None
    return json.loads(knight["tournament_bracket"])


def get_tournament_opponent_slot(bracket: dict, round_number: int) -> dict:
    """Lo slot dell'avversario del giocatore per questo round, dal
    tabellone già generato (richiesto in chat: deve corrispondere
    DAVVERO a chi si vede nel tabellone, non un altro pescato a
    caso)."""
    round_data = bracket["rounds"][round_number - 1]
    player_slot = bracket["player_slot"]
    for a, b in round_data["matches"]:
        if a == player_slot or b == player_slot:
            return bracket["slots"][b if a == player_slot else a]
    raise ValueError("Il giocatore non compare in nessun incontro di questo round del tabellone.")


def build_tournament_opponent(conn: sqlite3.Connection, bracket: dict, round_number: int) -> dict:
    """L'avversario del round attuale, pronto per il motore di
    combattimento - preso dal tabellone già generato, non più pescato
    alla cieca ad ogni round (richiesto in chat)."""
    slot = get_tournament_opponent_slot(bracket, round_number)
    guardian_name = slot["name"].split(" di ")[0] if " di " in slot["name"] else slot["name"]
    return build_opponent_from_armor(conn, slot["armor_name"], guardian_name)


INFERI_MISSION_ID = "prove_degli_inferi"

# Le cinque prove (richiesto in chat: "Ade a prove", niente grafo di
# nodi né tabellone - una sequenza di prove a dado, con un livello di
# allerta che sale sui fallimenti). Ogni prova usa una statistica
# diversa, per non rendere sempre conveniente lo stesso approccio.
INFERI_STAGES = [
    {"name": "Le Porte del Cocytus",
     "text": ("Il gelo del Cocytus ti stringe le ossa ancora prima di aver attraversato le sue porte "
               "spezzate. Un'iscrizione antica blocca il passaggio - solo chi la risolve può proseguire "
               "senza allertare le sentinelle appostate lungo le mura.")},
    {"name": "I Corridoi di Giudecca",
     "text": ("Le pattuglie di Spettri percorrono i corridoi a ritmi regolari - un enigma inciso su una "
               "delle colonne sembra l'unico modo per calcolare la finestra giusta in cui muoversi senza "
               "essere visto.")},
    {"name": "Il Cimitero degli Spettri Perduti",
     "text": ("Migliaia di anime dimenticate sussurrano tra le tombe un indovinello, sempre lo stesso, come "
               "un disco rotto - rispondere bene è l'unico modo per attraversare senza che la disperazione "
               "che promettono ti faccia perdere l'orientamento.")},
    {"name": "Le Segrete dei Dannati",
     "text": ("Un labirinto di celle e trappole dimenticate da secoli - un vecchio meccanismo a enigmi "
               "regola i passaggi sicuri. Sbagliare significa far scattare un allarme che nessuno, qui "
               "sotto, vorrebbe sentire.")},
    {"name": "La Sala dei Tre Giudici",
     "text": ("La sala dove i Tre Giudici dell'Ade pronunciano le proprie sentenze - qui più che altrove, "
               "un enigma sbagliato significa la fine di tutto.")},
]

INFERI_AMBUSH_THRESHOLD = 3       # a questo livello di allerta, la prossima prova diventa un'imboscata
INFERI_AMBUSH_RESET_ALERT = 1     # dopo aver vinto un'imboscata resti comunque un po' scoperto, non torni a zero

INFERI_REWARD_DENARO_PER_STAGE = 120
INFERI_REWARD_DENARO_CHAMPION = 900
INFERI_REWARD_COSMO_MAX_CHAMPION = 35

# Gli enigmi veri (richiesto in chat: "non un lanciadadi... mettiamo
# indovinelli / giochi di logica" - non un tiro di dado pesato dalla
# statistica, ma una prova vera che il giocatore deve risolvere
# davvero). Dieci varianti per ciascuna delle 5 prove, scelte a caso
# ad ogni tentativo (richiesto in chat: "non 1 fisso per livello, ma
# 10 diversi a rotazione casuale") - jolly abbastanza ampio da non
# ripetersi identico ad ogni tentativo della stessa run. Ogni voce:
# (domanda, [opzioni], indice della risposta corretta).
INFERI_PUZZLES = [
    # Prova 1 - Le Porte del Cocytus (tema: ghiaccio, resistenza, tempo)
    [
        ("Non ho vita, ma posso morire. Non ho polmoni, ma ho bisogno d'aria. Non ho bocca, ma l'acqua mi uccide. Cosa sono?",
         ["Il fuoco", "Il ghiaccio", "Il fiume", "Il vento"], 0),
        ("Completa la sequenza: 1, 1, 2, 3, 5, 8, ?",
         ["11", "12", "13", "15"], 2),
        ("Più ne togli, più diventa grande. Cos'è?",
         ["Una buca", "Una montagna", "Un fiume", "Un ghiacciaio"], 0),
        ("Ho città ma non case, foreste ma non alberi, fiumi ma non una goccia d'acqua vera. Cosa sono?",
         ["Una mappa", "Un sogno", "Uno specchio", "Un ricordo"], 0),
        ("Ghiaccio sta a Freddo come Fuoco sta a...?",
         ["Caldo", "Luce", "Cenere", "Fumo"], 0),
        ("Se tre sentinelle di ghiaccio impiegano 3 ore a sciogliersi sotto lo stesso sole, quante ore impiegano 6 sentinelle identiche?",
         ["3 ore", "6 ore", "9 ore", "1 ora e mezza"], 0),
        ("Sono fatto d'acqua, ma se mi tocchi a mani nude posso farti male. Cosa sono?",
         ["Il ghiaccio", "Il vapore", "La grandine", "La rugiada"], 0),
        ("Quale parola non appartiene al gruppo: Gelo, Brina, Vampa, Neve?",
         ["Gelo", "Brina", "Vampa", "Neve"], 2),
        ("Cammino sempre avanti, non torno mai indietro, e ogni mio passo è un anno che passa. Cosa sono?",
         ["Il tempo", "Il fiume", "Il vento", "Il destino"], 0),
        ("Quale numero completa la sequenza: 100, 81, 64, 49, ?",
         ["36", "42", "30", "40"], 0),
    ],
    # Prova 2 - I Corridoi di Giudecca (tema: furtività, ombre, pattuglie)
    [
        ("Più ce n'è, meno si vede. Cos'è?",
         ["Il buio", "La nebbia", "Il fumo", "Il silenzio"], 0),
        ("Ti seguo sempre ma non mi tocchi mai. Cosa sono?",
         ["L'ombra", "L'eco", "Il destino", "Il ricordo"], 0),
        ("Una pattuglia passa ogni 12 minuti, un'altra ogni 18. Ogni quanti minuti passano insieme?",
         ["30", "36", "24", "18"], 1),
        ("Non ho voce ma ti parlo, non ho gambe ma ti seguo dovunque tu vada nel buio. Cosa sono?",
         ["L'ombra", "Il pensiero", "La paura", "La coscienza"], 0),
        ("Silenzio sta a Rumore come Buio sta a...?",
         ["Luce", "Notte", "Ombra", "Cieco"], 0),
        ("In una fila di sentinelle, la quinta da sinistra è anche la terza da destra. Quante sentinelle ci sono in totale?",
         ["5", "6", "7", "8"], 2),
        ("Più ne prendi, più ne lasci dietro di te. Cosa sono?",
         ["I passi", "I ricordi", "Le impronte", "Il tempo"], 0),
        ("Quale animale è da sempre simbolo di furtività silenziosa nella notte?",
         ["Il gatto", "Il cane", "Il cavallo", "Il toro"], 0),
        ("Completa la sequenza di lettere: A, C, F, J, ?",
         ["N", "O", "P", "M"], 1),
        ("Ho molte chiavi ma nessuna apre una porta. Cosa sono?",
         ["Un pianoforte", "Un mazzo di carte", "Una mappa", "Un enigma"], 0),
    ],
    # Prova 3 - Il Cimitero degli Spettri Perduti (tema: anime, memoria, indovinelli classici)
    [
        ("Cosa cammina al mattino su quattro zampe, a mezzogiorno su due, e alla sera su tre?",
         ["L'uomo", "Il tempo", "La vita", "Il ragno"], 0),
        ("Non sono vivo, ma posso crescere. Non ho polmoni, ma ho bisogno d'aria. Non ho bocca, ma l'acqua mi uccide. Cosa sono?",
         ["Il fuoco", "Un ricordo", "Un'ombra", "Un fantasma"], 0),
        ("Che cosa è tuo, ma lo usano gli altri più spesso di te?",
         ["Il tuo nome", "Il tuo tempo", "Il tuo cuore", "Il tuo destino"], 0),
        ("Ho un volto ma non un corpo, appaio quando c'è luce e scompaio quando non c'è. Cosa sono?",
         ["L'ombra", "Il riflesso", "Il fantasma", "Il ricordo"], 0),
        ("Cosa si può rompere senza mai essere toccato?",
         ["Una promessa", "Un silenzio", "Un cuore", "Uno specchio"], 0),
        ("Sono l'inizio della fine, la fine di ogni luogo. Sono l'inizio dell'eternità, la fine del tempo e dello spazio. Quale lettera sono?",
         ["E", "F", "T", "N"], 0),
        ("Un cimitero ha 100 tombe. Ogni anno ne vengono aggiunte 5. Dopo quanti anni ce ne saranno 150?",
         ["5", "10", "15", "20"], 1),
        ("Non ho occhi ma vedo tutto quello che è stato. Cosa sono?",
         ["La memoria", "Lo specchio", "Il tempo", "Il destino"], 0),
        ("Cosa è pieno di buchi ma trattiene ancora l'acqua?",
         ["Una spugna", "Un setaccio", "Un cesto", "Una rete"], 0),
        ("Due anime dei morti rispondono sempre allo stesso modo a una domanda su se stesse, quale che sia la domanda. Una dice sempre la verità, l'altra mente sempre. Se chiedi a entrambe 'Sei tu quella sincera?', cosa rispondono?",
         ["Entrambe dicono sì", "Entrambe dicono no", "Una dice sì, l'altra no", "Nessuna delle due risponde"], 0),
    ],
    # Prova 4 - Le Segrete dei Dannati (tema: trappole, logica, deduzione)
    [
        ("Due porte, due guardiani: uno mente sempre, l'altro dice sempre la verità. Puoi fare una sola domanda a un solo guardiano per trovare la porta sicura. Qual è la domanda giusta?",
         ["\"Qual è la porta sicura?\"", "\"Sei quello che dice sempre la verità?\"",
          "\"Se chiedessi all'altro guardiano quale porta è sicura, cosa direbbe?\"", "\"Quale porta sceglieresti tu?\""], 2),
        ("Hai 8 sfere identiche, una più pesante delle altre. Con una bilancia a due piatti, in quante pesate minime trovi quella più pesante?",
         ["1", "2", "3", "4"], 1),
        ("Completa la sequenza: 3, 6, 12, 24, ?",
         ["36", "42", "48", "30"], 2),
        ("Un labirinto ha 3 bivi, e ad ogni bivio puoi scegliere tra 2 strade. Quante strade diverse portano in totale alla fine?",
         ["6", "8", "9", "12"], 1),
        ("Quale numero non appartiene al gruppo: 4, 9, 16, 20, 25?",
         ["4", "9", "20", "25"], 2),
        ("Se 5 dannati scavano 5 tunnel in 5 giorni, quanti giorni servono a 10 dannati per scavare 10 tunnel identici?",
         ["5", "10", "2", "25"], 0),
        ("In fila ci sono 10 celle numerate da 1 a 10. Le celle con numero pari sono aperte. Quante celle sono aperte?",
         ["4", "5", "6", "10"], 1),
        ("Completa la sequenza di lettere: B, D, F, H, ?",
         ["I", "J", "K", "G"], 1),
        ("Se A è più alto di B, e B è più alto di C, chi è il più basso dei tre?",
         ["A", "B", "C", "Non si può sapere"], 2),
        ("Una cella si allaga: l'acqua raddoppia ogni minuto e la riempie del tutto al minuto 60. A che minuto era piena a metà?",
         ["30", "45", "59", "55"], 2),
    ],
    # Prova 5 - La Sala dei Tre Giudici (tema: verità, giudizio, gli enigmi più ardui)
    [
        ("Tre Giudici: il primo dice sempre la verità, il secondo mente sempre, il terzo risponde a caso. Di quale dei tre non ti puoi mai fidare, nemmeno per una sola risposta?",
         ["Quello che dice sempre la verità", "Quello che mente sempre", "Quello che risponde a caso", "Nessuno dei tre"], 2),
        ("Cosa è più pesante: un chilo di piume o un chilo di pietre?",
         ["Le piume", "Le pietre", "Pesano uguale", "Dipende dalla bilancia"], 2),
        ("Un Giudice dice: \"Domani mentirò.\" Se oggi ha detto la verità, cosa deve succedere domani perché non si contraddica?",
         ["Deve mentire", "Deve dire la verità", "È un paradosso senza soluzione", "Non è vincolato a nulla"], 0),
        ("Su un piatto della bilancia ci sono 3 pesi da 4 kg, sull'altro un solo peso da 12 kg. Sono in equilibrio?",
         ["Sì", "No, manca 1 kg", "No, manca 2 kg", "No, ne avanza 1 kg"], 0),
        ("Tre anime devono attraversare un ponte di notte con una sola torcia. Il ponte regge al massimo 2 alla volta. Le loro velocità sono 1, 2 e 5 minuti (chi va più piano rallenta chi va più veloce). Qual è il tempo minimo per farle attraversare tutte?",
         ["6 minuti", "7 minuti", "8 minuti", "10 minuti"], 2),
        ("\"Tutti i Giudici sono giusti. Radamanthys è un Giudice.\" Cosa puoi concludere con certezza?",
         ["Radamanthys è giusto", "Radamanthys è ingiusto", "Non si può concludere nulla", "Radamanthys non è un Giudice"], 0),
        ("Completa la sequenza: 2, 6, 12, 20, 30, ?",
         ["36", "40", "42", "44"], 2),
        ("Un'anima onesta dice sempre la verità, una bugiarda mente sempre. Incontri due anime, A e B. A dice: \"Almeno una di noi due mente.\" Chi mente davvero?",
         ["A mente", "B mente", "Entrambe mentono", "Nessuna delle due mente"], 1),
        ("Se nessuna bugia può essere vera, e qualcuno dice \"questa frase che sto dicendo è una bugia\", quella frase è vera o falsa?",
         ["È vera", "È falsa", "È un paradosso: non può essere coerentemente né vera né falsa", "Dipende da chi la dice"], 2),
        ("Un Giudice pesa le anime su una bilancia a due piatti: un'anima pesa quanto 2 piume più 1 pietra, un'altra quanto 3 piume. Se pietra e piuma non pesano uguale, quale delle due anime è più pesante, sapendo che una pietra pesa più di una piuma?",
         ["La prima", "La seconda", "Pesano uguale", "Non si può stabilire con questi dati"], 0),
    ],
]


# Le Surplice degli Spettri comuni (richiesto in chat: le imboscate
# quando l'allerta sale troppo) - livello 50, un gradino sotto ai Tre
# Giudici, per una scalata di difficoltà credibile.
SPECTER_AMBUSH_ARMORS = [
    "Surplice di Minotaur", "Surplice di Worm", "Surplice di Deep", "Surplice di Frog",
    "Surplice di Cyclops", "Surplice di Gorgon", "Surplice di Dullahan", "Surplice di Acheron",
    "Surplice di Behemoth", "Surplice di Necromancer",
]
# I Tre Giudici degli Inferi (richiesto in chat: il vero scontro finale
# dopo le cinque prove) - le Surplice di Radamanthys, Minosse e Aiacos,
# fedeli al canone anche se il catalogo le elenca coi nomi delle
# Surplice piuttosto che dei portatori.
JUDGE_ARMORS = ["Surplice di Wyvern", "Surplice di Garuda", "Surplice di Griffon"]


def pick_inferi_puzzle(stage_index: int) -> tuple[int, dict]:
    """Sceglie un enigma A CASO tra i 10 disponibili per questa prova
    (richiesto in chat: "non 1 fisso per livello, ma 10 diversi a
    rotazione casuale") - restituisce (indice dell'enigma nel pool,
    dict con domanda/opzioni) - l'indice va persistito (mission_flags)
    così la risposta del giocatore si confronta con l'enigma GIUSTO,
    non uno nuovo pescato a caso ad ogni chiamata."""
    pool = INFERI_PUZZLES[stage_index - 1]
    puzzle_index = random.randrange(len(pool))
    question, options, _correct_index = pool[puzzle_index]
    return puzzle_index, {"question": question, "options": options}


def check_inferi_answer(stage_index: int, puzzle_index: int, answer_index: int) -> bool:
    """Confronta la risposta del giocatore con quella giusta per
    l'enigma già scelto (richiesto in chat: una vera prova di logica,
    non un tiro di dado)."""
    pool = INFERI_PUZZLES[stage_index - 1]
    _question, _options, correct_index = pool[puzzle_index]
    return answer_index == correct_index



def get_inferi_stage(stage_index: int) -> dict | None:
    """La prova numero `stage_index` (1-based) - None se l'indice è
    oltre l'ultima prova (significa che è il momento del duello finale
    contro un Giudice, gestito a parte)."""
    if 1 <= stage_index <= len(INFERI_STAGES):
        return INFERI_STAGES[stage_index - 1]
    return None


def resolve_inferi_reward(stages_completed: int, is_champion: bool) -> dict:
    """La ricompensa dell'infiltrazione: una quota per ogni prova
    superata, più un bonus vero solo se arrivi in fondo e superi anche
    il Giudice finale (richiesto implicito, stesso principio già usato
    per i tornei: un tentativo parziale vale comunque qualcosa, ma
    molto meno di un successo completo)."""
    denaro = INFERI_REWARD_DENARO_PER_STAGE * stages_completed
    cosmo_max = 0
    if is_champion:
        denaro += INFERI_REWARD_DENARO_CHAMPION
        cosmo_max = INFERI_REWARD_COSMO_MAX_CHAMPION
    return {"denaro": denaro, "cosmo_max": cosmo_max}


def resolve_tournament_reward(tournament_id: str, rounds_completed: int, is_champion: bool) -> dict:
    """La ricompensa del torneo `tournament_id`: una quota per ogni
    round superato, più un bonus vero solo se lo vinci per intero
    (richiesto implicito: arrivare in semifinale ed essere eliminati
    deve comunque valere qualcosa, ma molto meno che vincerlo)."""
    settings = TOURNAMENT_MISSIONS[tournament_id]
    denaro = settings["reward_denaro_per_round"] * rounds_completed
    cosmo_max = 0
    if is_champion:
        denaro += settings["reward_denaro_champion"]
        cosmo_max = settings["reward_cosmo_max_champion"]
    return {"denaro": denaro, "cosmo_max": cosmo_max}



def get_graph_node_content(mission_id: str, node_id: str, guardian_name: str = "") -> dict:
    """Il contenuto testuale del nodo `node_id` della missione a grafo
    `mission_id`, con il nome vero del Guardiano al posto del
    segnaposto dove serve - generica (richiesto in chat), non più
    specifica delle sole Colonne."""
    node = GRAPH_MISSIONS[mission_id]["nodes"][node_id]
    content = {"node_id": node_id, "type": node["type"]}
    if node["type"] == "choice":
        content["text"] = node["text"]
        content["options"] = [{"label": opt["label"], "index": i} for i, opt in enumerate(node["options"])]
    elif node["type"] == "skill_check":
        content["text"] = node["text"]
        content["stat"] = node["stat"]
    elif node["type"] == "duel":
        content["intro"] = node["intro"].format(guardian=guardian_name)
        content["guardian_name"] = guardian_name
    elif node["type"] == "ending":
        content["text"] = node["text"]
    return content


def pick_graph_duel_armor(mission_id: str, node_id: str) -> str:
    """L'armatura del duello per questo nodo della missione `mission_id`
    - fissa per gli scontri finali, a caso tra il pool per gli altri
    (richiesto in chat: varietà tra un tentativo e l'altro). Generica,
    non più specifica delle sole Colonne."""
    node = GRAPH_MISSIONS[mission_id]["nodes"][node_id]
    if "armor" in node:
        return node["armor"]
    return random.choice(node["armor_pool"])


def resolve_graph_mission_ending(mission_id: str, flags: set[str]) -> dict:
    """Il testo di finale e l'eventuale ricompensa extra della missione
    `mission_id`, in base ai flag accumulati durante il percorso
    (richiesto in chat: una conseguenza vera, ritardata, per la scelta
    morale centrale) - generica, non più specifica delle sole
    Colonne."""
    ending = GRAPH_MISSIONS[mission_id]["nodes"]["fine"]
    text = ending["text"]
    bonus = {}
    for flag_name, alt_text in ending.get("text_with_flag", {}).items():
        if flag_name in flags:
            text = alt_text
            bonus = ending.get("bonus_with_flag", {}).get(flag_name, {})
            break
    return {"text": text, "bonus": bonus}
