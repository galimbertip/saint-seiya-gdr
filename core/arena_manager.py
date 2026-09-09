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

AGGIORNAMENTO (richiesto in chat): il sistema di stati (Veleno,
Pietrificazione/Intrappolamento) esisteva già, ma copriva solo 3
elementi su quelli usati davvero nel catalogo tecniche. Esteso con
Fuoco (Bruciatura, stesso meccanismo del Veleno), Elettrico (Paralisi
a PROBABILITÀ - diversa da quella totale di Pietrificazione/
Intrappolamento, che resta garantita) e Psichico (Confusione - non
blocca il turno, costringe a tirare in svantaggio, riusando lo stesso
meccanismo di vantaggio/svantaggio già usato per gli Imprevisti e la
distanza, invece di inventare un sistema di "probabilità di mancare"
separato)."""
import random
import sqlite3

from core.dnd_engine import DnDEngine
from core.alignment import random_alignment, combat_action_weights
from database.db_manager import get_techniques_for_armor

OPPONENT_LEVEL_TOLERANCE = 20  # cerca avversari con livello armatura entro +-20 dal punto scelto
# La tolleranza raddoppia finché il pool non raggiunge questa soglia
# (corretto in chat: poca varietà per le armature di livello molto
# basso, dove ±20 lasciava solo 7-8 candidate) - un tetto oltre il
# quale ci si ferma comunque, anche se il pool resta piccolo (livelli
# davvero estremi, ai bordi del catalogo).
MIN_OPPONENT_POOL_SIZE = 20
MAX_OPPONENT_LEVEL_TOLERANCE = 160
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

# Nomi/cognomi per gli avversari generati - segnalato in chat: "Rivale
# in Piccolo Cavallo" suona male con certi nomi d'armatura più goffi in
# italiano. Un nome vero davanti (stesso stile di "Nome di Armatura"
# usato per il giocatore) ammorbidisce la frase in ogni caso. Elenco
# volutamente piccolo e generico, non collegato a nessuna provenienza
# specifica (quella è una scelta narrativa del giocatore, non qui).
NAME_POOLS = {
    # Nomi e cognomi raggruppati per area culturale (corretto in chat:
    # prima erano due liste piatte mescolate del tutto a caso, capitava
    # di ottenere accostamenti senza senso come "Andrei Rodriguez" -
    # ogni nome generato ora pesca nome E cognome dallo STESSO gruppo.
    # Ampliato molto rispetto a prima, e con qualche gruppo nuovo.
    "Italia": {
        "first": ["Marco", "Andrea", "Luca", "Giulia", "Sofia", "Alessandro", "Francesca",
                   "Matteo", "Chiara", "Davide", "Elena", "Simone", "Valentina", "Riccardo",
                   "Martina", "Lorenzo", "Federica", "Gabriele", "Alessia", "Tommaso"],
        "last": ["Rossi", "Romano", "Bianchi", "Ferrari", "Esposito", "Russo", "Colombo",
                  "Ricci", "Marino", "Greco", "Bruno", "Gallo", "Conti", "De Luca", "Mancini",
                  "Costa", "Giordano", "Rizzo", "Lombardi", "Moretti"],
    },
    "Russia": {
        "first": ["Aleksei", "Dmitri", "Ivan", "Elena", "Anastasia", "Nikolai", "Mikhail",
                   "Olga", "Boris", "Tatiana", "Sergei", "Natalia", "Viktor", "Yelena",
                   "Pavel", "Irina", "Andrei", "Ksenia", "Vladimir", "Marina"],
        "last": ["Volkov", "Petrova", "Ivanov", "Sokolov", "Kuznetsova", "Popov", "Novikova",
                  "Morozov", "Volkova", "Fedorov", "Orlova", "Belov", "Zaitseva", "Egorov",
                  "Golubev", "Sorokina", "Vasiliev", "Kozlova", "Antonov", "Baranova"],
    },
    "Spagna": {
        "first": ["Diego", "Carlos", "Isabel", "Javier", "Lucia", "Miguel", "Marta",
                   "Sergio", "Elena", "Pablo", "Cristina", "Alvaro", "Nuria", "Ruben",
                   "Beatriz", "Adrian", "Rocio", "Ivan", "Pilar", "Hugo"],
        "last": ["Fernandez", "Garcia", "Lopez", "Martinez", "Gonzalez", "Sanchez",
                  "Perez", "Gomez", "Diaz", "Alvarez", "Moreno", "Munoz", "Romero",
                  "Navarro", "Iglesias", "Vega", "Serrano", "Blanco", "Suarez", "Cano"],
    },
    "America Latina": {
        "first": ["Rafael", "Rodrigo", "Valentina", "Santiago", "Camila", "Mateo", "Paula",
                   "Alejandro", "Gabriela", "Emiliano", "Ximena", "Nicolas", "Renata",
                   "Sebastian", "Daniela", "Joaquin", "Fernanda", "Tomas", "Antonella", "Bruno"],
        "last": ["Hernandez", "Torres", "Ramirez", "Vasquez", "Castro", "Morales", "Reyes",
                  "Flores", "Gutierrez", "Jimenez", "Ortiz", "Chavez", "Mendoza", "Aguilar",
                  "Vargas", "Contreras", "Rojas", "Guerrero", "Paredes", "Salazar"],
    },
    "Brasile/Portogallo": {
        "first": ["Lucas", "Beatriz", "Mateus", "Ana", "Rafael", "Juliana", "Gustavo",
                   "Larissa", "Thiago", "Camila", "Bruno", "Fernanda", "Diego", "Patricia",
                   "Felipe", "Vitoria", "Andre", "Carolina", "Rodrigo", "Amanda"],
        "last": ["Silva", "Alves", "Pereira", "Santos", "Oliveira", "Souza", "Costa",
                  "Ferreira", "Rodrigues", "Almeida", "Nascimento", "Carvalho", "Araujo",
                  "Ribeiro", "Barbosa", "Cardoso", "Correia", "Teixeira", "Monteiro", "Pinto"],
    },
    "Cina": {
        "first": ["Chen", "Wei", "Jin", "Mei", "Tao", "Xiu", "Feng", "Lian", "Hao", "Ying",
                   "Bo", "Fang", "Jian", "Xia", "Qiang", "Na", "Yun", "Peng", "Lan", "Rong"],
        "last": ["Wang", "Zhang", "Chen", "Liu", "Huang", "Wu", "Li", "Yang", "Zhao",
                  "Xu", "Sun", "Ma", "Zhu", "Hu", "Guo", "He", "Gao", "Lin", "Luo", "Zheng"],
    },
    "Giappone": {
        "first": ["Yuki", "Kenji", "Hiroshi", "Ryo", "Sakura", "Hana", "Kazuki", "Akira",
                   "Yumi", "Daiki", "Rina", "Sota", "Emi", "Haruto", "Nanami", "Kaito",
                   "Yui", "Shota", "Aoi", "Ren"],
        "last": ["Takeda", "Yamamoto", "Sato", "Suzuki", "Nakamura", "Watanabe", "Kobayashi",
                  "Inoue", "Kimura", "Hayashi", "Saito", "Shimizu", "Yamaguchi", "Matsumoto",
                  "Ikeda", "Yoshida", "Yamada", "Sasaki", "Endo", "Fujita"],
    },
    "Corea": {
        "first": ["Min-jun", "So-yeon", "Tae-woo", "Ji-eun", "Hyun-woo", "Yu-jin", "Seo-yun",
                   "Jun-ho", "Ha-eun", "Do-yoon", "Eun-ji", "Jae-min", "Su-bin", "Min-seo",
                   "Woo-jin", "Ye-jin", "Sung-min", "Ga-eun"],
        "last": ["Kim", "Park", "Lee", "Choi", "Jung", "Kang", "Cho", "Yoon", "Jang", "Lim",
                  "Han", "Oh", "Seo", "Shin", "Kwon", "Hwang", "Ahn", "Song", "Yoo", "Hong"],
    },
    "Scandinavia": {
        "first": ["Sven", "Astrid", "Bjorn", "Freya", "Erik", "Ingrid", "Lars", "Sigrid",
                   "Magnus", "Elin", "Oskar", "Maja", "Anders", "Karin", "Gustav", "Nora",
                   "Henrik", "Linnea", "Filip", "Saga"],
        "last": ["Nilsson", "Andersson", "Larsen", "Hansen", "Berg", "Lindqvist", "Karlsson",
                  "Johansson", "Eriksson", "Olsen", "Pedersen", "Nielsen", "Svensson",
                  "Gustafsson", "Holm", "Lund", "Dahl", "Bergstrom", "Sandberg", "Lindgren"],
    },
    "Germania": {
        "first": ["Hans", "Greta", "Klaus", "Stefan", "Katarina", "Ingrid", "Wolfgang",
                   "Ursula", "Dieter", "Helga", "Jurgen", "Monika", "Werner", "Brigitte",
                   "Frank", "Sabine", "Rainer", "Petra", "Uwe", "Karin"],
        "last": ["Muller", "Schmidt", "Weber", "Wagner", "Fischer", "Becker", "Hoffmann",
                  "Schulz", "Koch", "Bauer", "Richter", "Klein", "Wolf", "Schroeder",
                  "Neumann", "Braun", "Zimmermann", "Krause", "Lange", "Werner"],
    },
    "Francia": {
        "first": ["Pierre", "Camille", "Antoine", "Isabelle", "Jean", "Marie", "Nicolas",
                   "Sophie", "Julien", "Claire", "Thomas", "Celine", "Laurent", "Aurelie",
                   "Vincent", "Manon", "Olivier", "Charlotte", "Mathieu", "Louise"],
        "last": ["Moreau", "Dubois", "Rousseau", "Lefebvre", "Bernard", "Martin", "Petit",
                  "Durand", "Leroy", "Simon", "Laurent", "Michel", "Garnier", "Faure",
                  "Andre", "Mercier", "Blanc", "Guerin", "Boyer", "Fontaine"],
    },
    "India": {
        "first": ["Priya", "Ravi", "Ananya", "Arjun", "Meera", "Vikram", "Kavya", "Rohan",
                   "Divya", "Aditya", "Neha", "Karan", "Pooja", "Sanjay", "Anjali", "Rahul",
                   "Shreya", "Vikas", "Deepika", "Amit"],
        "last": ["Singh", "Sharma", "Kumar", "Patel", "Gupta", "Reddy", "Rao", "Nair",
                  "Iyer", "Menon", "Chopra", "Malhotra", "Verma", "Joshi", "Desai",
                  "Kapoor", "Mehta", "Bhat", "Pillai", "Choudhury"],
    },
    "Mondo Arabo": {
        "first": ["Ahmed", "Layla", "Yusuf", "Zara", "Omar", "Fatima", "Karim", "Amira",
                   "Hassan", "Nadia", "Tariq", "Yasmin", "Khalid", "Rania", "Samir",
                   "Leila", "Bilal", "Noor", "Malik", "Salma"],
        "last": ["Al-Rashid", "Hassan", "Ibrahim", "Khoury", "Farouk", "Mansour", "Saleh",
                  "Haddad", "Aziz", "Karam", "Nasser", "Qureshi", "Zaidi", "Rahman",
                  "Sultan", "Habib", "Karimi", "Youssef", "Fares", "Jaber"],
    },
    "Africa Occidentale": {
        "first": ["Adaeze", "Kwame", "Chidinma", "Kofi", "Amara", "Ifeoma", "Kwabena",
                   "Ngozi", "Yaw", "Chinelo", "Kojo", "Adaobi", "Emeka", "Efua", "Obinna",
                   "Akosua", "Chukwu", "Ama", "Nnamdi", "Abena"],
        "last": ["Okafor", "Mensah", "Adeyemi", "Diallo", "Okonkwo", "Boateng", "Eze",
                  "Owusu", "Nwosu", "Asante", "Chukwu", "Osei", "Balogun", "Appiah",
                  "Uche", "Danso", "Adebayo", "Yeboah", "Nnamdi", "Agyeman"],
    },
    "Africa Meridionale": {
        "first": ["Thabo", "Naledi", "Sipho", "Lindiwe", "Themba", "Nomvula", "Bongani",
                   "Zanele", "Sizwe", "Thandiwe", "Mandla", "Nokuthula", "Vusi", "Precious",
                   "Lwazi", "Ntombi", "Sibusiso", "Zodwa"],
        "last": ["Ndlovu", "Dlamini", "Nkosi", "Khumalo", "Mokoena", "Sithole", "Zulu",
                  "Mahlangu", "Radebe", "Ngcobo", "Mthembu", "Sibeko", "Molefe", "Tshabalala",
                  "Nkomo", "Mabaso", "Cele", "Buthelezi"],
    },
    "Grecia": {
        "first": ["Nikos", "Despina", "Dimitri", "Calista", "Costas", "Xanthe", "Alexandros",
                   "Eleni", "Yannis", "Sofia", "Apostolos", "Ariadne", "Stavros", "Ioanna",
                   "Petros", "Katerina", "Vasilis", "Theodora"],
        "last": ["Papadopoulos", "Georgiadis", "Konstantinidis", "Nikolopoulos",
                  "Christopoulos", "Antoniou", "Antonopoulos", "Anastasiou", "Alexiou",
                  "Savvidis", "Vasiliadis", "Stavridis", "Andreou", "Angelopoulos",
                  "Dimitriou", "Papadakis", "Moraitis", "Karagiannis"],
    },
    "Polonia": {
        "first": ["Kacper", "Zofia", "Tomasz", "Agnieszka", "Wojciech", "Magdalena",
                   "Krzysztof", "Anna", "Pawel", "Katarzyna", "Michal", "Ewa", "Piotr",
                   "Joanna", "Grzegorz", "Barbara"],
        "last": ["Kowalski", "Nowak", "Wisniewski", "Wojcik", "Kaminski", "Lewandowski",
                  "Zielinski", "Szymanski", "Dabrowski", "Kozlowski", "Jankowski",
                  "Mazur", "Kwiatkowski", "Krawczyk", "Piotrowski", "Grabowski"],
    },
    "Vietnam": {
        "first": ["Minh", "Linh", "Hoang", "Mai", "Duc", "Huong", "Nam", "Thao", "Tuan",
                   "Trang", "Khanh", "Anh", "Phuong", "Long", "Ngoc", "Quang"],
        "last": ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Phan", "Vu", "Dang", "Bui",
                  "Do", "Ho", "Ngo", "Duong", "Ly"],
    },
    "Turchia": {
        "first": ["Emre", "Elif", "Mehmet", "Zeynep", "Burak", "Aylin", "Can", "Selin",
                   "Kerem", "Deniz", "Baris", "Ipek", "Yusuf", "Ceren", "Onur", "Gizem"],
        "last": ["Yilmaz", "Kaya", "Demir", "Sahin", "Celik", "Yildiz", "Aydin", "Ozturk",
                  "Arslan", "Dogan", "Kilic", "Aslan", "Cetin", "Ozdemir"],
    },
}


def generate_full_name() -> str:
    """Un nome completo, coerente (richiesto in chat) - pesca nome E
    cognome dallo STESSO gruppo culturale, non più due liste piatte
    mescolate a caso."""
    group = random.choice(list(NAME_POOLS.values()))
    return f"{random.choice(group['first'])} {random.choice(group['last'])}"


def generate_distinct_full_names(n: int, exclude: tuple[str, ...] = ()) -> list[str]:
    """`n` nomi completi, ciascuno del proprio gruppo scelto a parte,
    evitando ripetizioni esatte tra loro o con `exclude` (richiesto in
    chat: capitava per puro caso che un compagno finisse per chiamarsi
    come il Maestro, pescando da liste piccole)."""
    names: list[str] = []
    attempts = 0
    while len(names) < n and attempts < n * 20:
        attempts += 1
        candidate = generate_full_name()
        if candidate not in names and candidate not in exclude:
            names.append(candidate)
    while len(names) < n:  # non dovrebbe mai servire, con pool così ampi
        names.append(generate_full_name())
    return names



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
    La tolleranza si allarga da sola quando il pool è troppo piccolo
    (corretto in chat: "poca rotazione/varietà anche col tasto
    ricarica" - capitava alle armature di livello molto basso, dove il
    catalogo ha pochi esemplari vicini, ±20 lasciava solo 7-8
    candidate) - non più tutto-o-niente (allargava a TUTTO il
    catalogo, ma solo se restava letteralmente zero candidate)."""
    exclude_armor_names = exclude_armor_names or set()
    offset = DIFFICULTY_LEVEL_OFFSET.get(difficulty, 0)
    target_level = player_armor_level + offset

    candidates: list = []
    tolerance = OPPONENT_LEVEL_TOLERANCE
    while len(candidates) < MIN_OPPONENT_POOL_SIZE and tolerance <= MAX_OPPONENT_LEVEL_TOLERANCE:
        rows = conn.execute(
            "SELECT * FROM armors WHERE ABS(level - ?) <= ?",
            (target_level, tolerance),
        ).fetchall()
        candidates = [r for r in rows if r["name"] not in exclude_armor_names]
        tolerance *= 2

    if not candidates:
        all_rows = conn.execute("SELECT * FROM armors").fetchall()
        candidates = [r for r in all_rows if r["name"] not in exclude_armor_names] or list(all_rows)

    armor = random.choice(candidates)
    techniques = [dict(t) for t in get_techniques_for_armor(armor["name"], conn)]
    cosmo = 100 + armor["level"]
    con_value = 10 + armor["level"] // 10
    vita = 100 + con_value * 2  # stessa formula di VITA_BASE/VITA_PER_CON in character_factory.py

    opponent_full_name = generate_full_name()
    return {
        "name": f"{opponent_full_name} di {armor['name']}",
        "armor_name": armor["name"],
        "divinity": armor["divinity"],
        "faction": armor["faction"],
        "armor_level": armor["level"],
        "cosmo_cur": cosmo,
        "cosmo_max": cosmo,
        "vita_cur": vita,
        "vita_max": vita,
        "str": 10 + armor["level"] // 10,
        "dex": 10 + armor["level"] // 10,
        "con": con_value,
        "tec": 10 + armor["level"] // 10,
        "vol": 10 + armor["level"] // 10,
        "origin": random.choice(list(ORIGIN_ELEMENT_AFFINITY.keys())),
        "techniques": techniques,
        # Un allineamento fresco ad ogni incontro (richiesto in chat,
        # effetti più ampi) - a differenza dei PNG del roster, un
        # avversario d'Arena generato al volo non ha un'identità
        # persistente, quindi non ha senso salvarlo: sposta comunque
        # il comportamento in combattimento per QUESTO scontro.
        "alignment": random_alignment(),
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
    "un crampo improvviso gli irrigidisce il braccio nel momento peggiore",
    "il terreno cede sotto il suo stesso peso, rovinando la mira",
    "perde per un istante il controllo del proprio Cosmo, tradito dal suo stesso corpo",
    "un ricordo doloroso gli attraversa la mente proprio mentre colpisce",
    "il fiato gli manca a metà movimento, lasciandolo scoperto",
    "il polso gira male e il colpo si perde nel vuoto",
    "un fulmine di dolore da una ferita vecchia lo blocca sul più bello",
    "la propria stessa energia gli si rivolta contro, disperdendosi senza controllo",
    "si muove un istante troppo presto, tradendo l'intera sequenza",
    "l'avversario legge il movimento prima ancora che si completi, e lui lo sa già",
    "il colpo perde ogni forza a un soffio dal bersaglio, come se il Cosmo stesso si fosse spento",
]

CRITICAL_HIT_FLAVORS = [
    "trova un varco perfetto nella difesa avversaria",
    "scarica tutta la potenza del Cosmo in un colpo devastante",
    "centra in pieno il punto debole dell'avversario",
    "il tempo sembra rallentare nell'istante esatto dell'impatto",
    "ogni fibra del corpo converge in un solo, imparabile momento",
    "il Cosmo brucia più intensamente che mai, e il colpo lo dimostra",
    "l'avversario non ha nemmeno il tempo di capire cosa lo abbia colpito",
    "settimane di addestramento si condensano in un singolo istante perfetto",
    "il colpo arriva esattamente dove doveva, senza un briciolo di esitazione",
    "qualcosa di più profondo del semplice talento guida il gesto fino in fondo",
    "l'aria stessa sembra vibrare intorno all'impatto",
    "è il colpo che ricorderà per il resto della sua vita, vinca o perda",
    "il Cosmo esplode in una fiammata che nemmeno lui si aspettava",
    "ogni dubbio svanisce nel momento esatto in cui il pugno trova il bersaglio",
    "la Cloth stessa sembra amplificare quella furia in un unico, perfetto istante",
]

NORMAL_HIT_FLAVORS = [
    "il colpo arriva dritto a segno",
    "non c'è tempo per schivare: il colpo si abbatte in pieno",
    "l'avversario incassa senza riuscire a spostarsi in tempo",
    "il Cosmo si scarica sul bersaglio con tutta la forza voluta",
    "un colpo pulito, senza fronzoli, che lascia il segno",
    "il gesto si completa esattamente come previsto, e fa male",
    "l'avversario capisce troppo tardi da dove sarebbe arrivato il colpo",
    "il corpo obbedisce perfettamente all'intenzione, senza sbavature",
    "non è il colpo più spettacolare, ma è quello giusto, al momento giusto",
    "il Cosmo accompagna il gesto fino in fondo, senza disperdersi",
]

DODGE_FLAVORS = [
    "un movimento all'ultimo istante basta a lasciare il colpo nel vuoto",
    "il corpo si sposta per istinto puro, un attimo prima che sia troppo tardi",
    "l'aria fischia a un soffio dalla pelle, ma il colpo non trova nulla da colpire",
    "un balzo laterale trasforma quello che poteva essere un colpo pesante in niente",
    "il Sesto Senso, se c'è, sussurra il pericolo un istante prima che diventi reale",
    "il colpo si perde a pochi centimetri dal bersaglio, che ormai non c'è più",
    "una torsione del busto basta a far scivolare via il pericolo",
    "il terreno stesso sembra offrire l'appoggio giusto per l'unico passo che serviva",
]

DEFENSE_SUCCESS_FLAVORS = [
    "regge l'urto senza cedere di un passo",
    "assorbe il colpo lasciando che il Cosmo ne disperda buona parte della furia",
    "il danno arriva comunque, ma molto meno di quanto avrebbe potuto",
    "la difesa tiene, anche se il contraccolpo si fa sentire",
    "riesce a smorzare il colpo appena in tempo",
    "il corpo incassa meno di quanto l'avversario sperasse",
]


def resolve_turn(attacker_name: str, attacker_str: int, attacker_tec: int, attacker_armor_level: int,
                  defender_name: str, defender_dex: int, defender_con: int, defender_armor_level: int,
                  technique_name: str, technique_power: int,
                  roll_mode: str = "normale", cause_phrase: str | None = None,
                  launch_desc: str | None = None, effect_desc: str | None = None) -> tuple[int, str, int]:
    """Risolve un turno d'attacco riusando DnDEngine (CA, tiro per
    colpire, danno) - qui si orchestra soltanto, nessuna nuova formula.
    Restituisce (danno_inflitto, messaggio_di_log, tiro_naturale_grezzo)
    - il terzo valore (richiesto in chat, il combattimento a squadre:
    un 1 naturale può rivoltarsi contro un compagno) espone il dado
    grezzo così i chiamanti possono reagire a un 1/20 naturale senza
    dover ritirare i dadi una seconda volta.
    attacker_tec/defender_con: Tecnica di chi attacca aumenta il danno
    inflitto, Costituzione di chi difende lo riduce - richiesto in
    chat: prima queste due statistiche non contavano nulla in
    combattimento, solo Forza e Destrezza.
    roll_mode: 'normale' | 'vantaggio' | 'svantaggio' - concesso da un
    Imprevisto (vedi maybe_trigger_event), dalla Confusione (vedi
    tick_statuses) o da altre condizioni.
    cause_phrase: la spiegazione NARRATIVA del perché (es. "abbagliato
    dal sole") - se non fornita, si usa una frase generica. Deciso in
    chat: niente più etichette nude tipo '[SVANTAGGIO]', la causa entra
    dentro la frase del colpo.
    launch_desc/effect_desc: la descrizione propria della tecnica, già
    scritta per ognuna nel catalogo (richiesto in chat: prima veniva
    mostrata a parte, secca, prima del numero - ora è intrecciata nella
    stessa frase dell'esito, e l'effetto - mai usato finora - compare
    accanto al danno). Se assenti (Attacco Base), si ricade su un
    messaggio più semplice.
    Un 1 naturale è sempre un fallimento critico (una disgrazia fisica
    vera, pescata a caso - non solo un'etichetta); un 20 naturale è
    sempre un successo e raddoppia il danno (colpo critico) - regole
    richieste in chat."""
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

    # La descrizione di lancio, intrecciata nella frase invece che
    # mostrata a parte (richiesto in chat) - solo per le tecniche vere,
    # l'Attacco Base resta semplice per non appesantire ogni singolo
    # round con una frase fissa ripetuta all'infinito. Un trattino,
    # non un altro due punti, per non appesantire la lettura quando
    # più tardi arriva quello che introduce l'esito.
    launch_clause = f" — {launch_desc}" if launch_desc else ""

    if not hit:
        if dice_roll == 1:
            flavor = random.choice(CRITICAL_FUMBLE_FLAVORS)
            return 0, f"{attacker_name} tenta {technique_name}{launch_clause}{prefix_note}... {flavor}! (1 naturale)", dice_roll
        # "ma" implica un contrasto (aveva un aiuto ma ha fallito comunque -
        # ha senso con il Vantaggio); con lo Svantaggio la schivata non è
        # una sorpresa, è la conseguenza diretta della causa - "e" invece
        # di "ma" (corretto in chat).
        connector = "e" if roll_mode == "svantaggio" else "ma"
        dodge_flavor = random.choice(DODGE_FLAVORS)
        return 0, (f"{attacker_name} scaglia {technique_name}{launch_clause}{prefix_note}, {connector} "
                    f"{dodge_flavor}: {defender_name} schiva! ({attack_total} vs CA {defender_ac})"), dice_roll

    attacker_tec_mod = DnDEngine.get_modifier(attacker_tec)
    defender_con_mod = DnDEngine.get_modifier(defender_con)
    _, damage = DnDEngine.resolve_technique_damage(
        technique_power, attacker_armor_level, attacker_tec_mod=attacker_tec_mod, defender_con_mod=defender_con_mod
    )
    # L'effetto della tecnica (mai usato finora, richiesto in chat) va
    # PRIMA del marcatore "— Danno: " - format_damage_message (vedi
    # sotto) cancella tutto ciò che segue quel marcatore quando
    # riallinea il numero dopo Carica/portata/affinità, quindi qualunque
    # cosa dopo andrebbe persa.
    effect_clause = f" - {effect_desc}" if effect_desc else ""
    if dice_roll == 20:
        damage *= 2
        flavor = random.choice(CRITICAL_HIT_FLAVORS)
        return damage, (f"{attacker_name} scatena {technique_name}{launch_clause}{prefix_note}: {flavor}!{effect_clause} "
                         f"({attack_total} vs CA {defender_ac}, colpo raddoppiato) — Danno: {damage}"), dice_roll
    flavor = random.choice(NORMAL_HIT_FLAVORS)
    return damage, (f"{attacker_name} colpisce con {technique_name}{launch_clause}{prefix_note}: {flavor}.{effect_clause} "
                     f"({attack_total} vs CA {defender_ac}) — Danno: {damage}"), dice_roll


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
    Base se non ne ha nessuna (o se le ha tutte puramente difensive -
    bug corretto in chat: prima l'avversario poteva scegliere a caso
    anche una tecnica solo difensiva per ATTACCARE, che non ha senso;
    le tecniche marcate "Entrambe" restano invece candidate valide).
    Restituisce (nome, potenza, tech_type) - il tech_type serve a
    maybe_apply_status per riconoscere le tecniche che lasciano un
    effetto (Veleno, Fuoco, Elettrico, Psichico, Pietrificazione/
    Intrappolamento)."""
    offensive_eligible = [
        t for t in opponent["techniques"]
        if "difensiv" not in (t.get("tech_type") or "").lower() or "entrambe" in (t.get("tech_type") or "").lower()
    ]
    if offensive_eligible:
        t = random.choice(offensive_eligible)
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

# Le tre barre (richiesto in chat): il Cosmo smette di fare da vita e
# diventa una risorsa vera per le tecniche - l'Attacco Base resta
# sempre gratuito. "Carica il Cosmo" cambia verso: non spende più
# Cosmo per un bonus da un colpo solo, ora fa perdere il turno per
# RECUPERARE Cosmo e ottenere un bonus di potenza (attacco E difesa)
# per alcuni turni di fila - con un raffreddamento: non si può
# ricaricare finché il bonus precedente non è scaduto, altrimenti
# alternando carica/attacco si diventerebbe invincibili (discusso in
# chat). Tutti PLACEHOLDER come le altre formule di bilanciamento.
TECHNIQUE_COSMO_COST_DIVISOR = 10
CHARGE_TURNS_DURATION = 3    # quanti turni dura il bonus dopo una Carica
CHARGE_COSMO_RESTORE = 30    # quanto Cosmo si recupera caricando
CHARGE_POWER_BONUS = 1.3     # +30% al danno inflitto, -30% al danno subito, mentre il bonus è attivo


def technique_cosmo_cost(technique_name: str, technique_power) -> int:
    """Il Cosmo come risorsa per le tecniche (richiesto in chat): zero
    per l'Attacco Base, altrimenti proporzionale alla potenza. Usata
    sia per il giocatore sia per l'avversario, così l'IA rispetta lo
    stesso vincolo."""
    if technique_name == "Attacco Base" or not technique_power:
        return 0
    return max(1, technique_power // TECHNIQUE_COSMO_COST_DIVISOR)

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


# --- Mappa 2D dell'Arena (Fase 1: griglia e posizione, solo visiva) --------
# Richiesta in chat, sequenziata a fasi come gli Imprevisti. Fase 1:
# fondamenta di stato e visive - una griglia 10x10 usata come "righello"
# per misurare le distanze (il movimento a schermo è libero/continuo,
# non a caselle - deciso in chat, stile Football Manager più che
# scacchiera D&D), i due combattenti hanno una posizione, ci si può
# muovere PRIMA di dichiarare un'azione. La distanza NON blocca ancora
# nulla (si può sempre attaccare, indipendentemente da dove si è) -
# quello è lavoro della Fase 2, quando la mappa toccherà per davvero le
# scelte tattiche e non solo l'occhio.
GRID_SIZE = 10

PLAYER_START_POSITION = {"x": 1.5, "y": 5.0}
OPPONENT_START_POSITION = {"x": 8.5, "y": 5.0}


def calculate_movement_points(player_level: int, age: int) -> int:
    """Quante unità di griglia un personaggio può percorrere in un solo
    spostamento. PLACEHOLDER (come le altre formule non ancora
    bilanciate): base 3, +1 ogni 5 livelli personaggio, -1 ogni 10 anni
    oltre i 25 (un cavaliere più anziano è un filo meno agile) -
    richiesto in chat: età e livello personaggio, non il Cosmo.
    Tenuto tra 2 e 9 perché la griglia è 10x10: oltre 9 non avrebbe
    senso (attraverseresti tutta l'arena in un colpo solo)."""
    age_penalty = max(0, (age - 25) // 10)
    points = 3 + player_level // 5 - age_penalty
    return max(2, min(9, points))


def distance_between(pos_a: dict, pos_b: dict) -> float:
    """Distanza in linea retta tra due posizioni sulla griglia."""
    return ((pos_a["x"] - pos_b["x"]) ** 2 + (pos_a["y"] - pos_b["y"]) ** 2) ** 0.5


def clamp_to_grid(x: float, y: float) -> dict:
    """Tiene una posizione dentro i bordi della griglia (0-GRID_SIZE)."""
    return {"x": max(0.0, min(GRID_SIZE, x)), "y": max(0.0, min(GRID_SIZE, y))}


def try_move(current_pos: dict, target_x: float, target_y: float,
             movement_points: int, terrain_effects: list[dict] | None = None) -> tuple[bool, dict, float, bool]:
    """Verifica e risolve uno spostamento verso (target_x, target_y).
    Se la distanza richiesta supera i Punti Movimento disponibili, il
    personaggio si ferma al massimo raggiungibile in quella direzione
    invece di fallire lo spostamento (più comodo da giocare: cliccare
    'un po' troppo lontano' ti porta comunque il più vicino possibile
    a dove volevi, non ti nega il movimento).
    terrain_effects (Fase 3): se il percorso attraversa un cratere, ci
    si ferma appena prima - vedi clip_path_for_craters.
    Nessun costo in tempo qui (tolto in chat: era ridondante con la
    perdita del turno per movimento eccessivo della Fase 2 - pagare
    minuti EXTRA in più, oltre a perdere l'attacco del round, era un
    doppio conto per la stessa causa). Il tempo passa comunque tramite
    il costo normale del round quando si dichiara un'azione.
    Restituisce (mosso_per_intero, nuova_posizione, distanza_percorsa,
    bloccato_da_cratere) - l'ultimo serve al chiamante per dare un
    messaggio giusto (non è colpa dei Punti Movimento, stavolta)."""
    target = clamp_to_grid(target_x, target_y)
    requested_distance = distance_between(current_pos, target)

    if requested_distance <= movement_points:
        new_pos = target
        moved_fully = True
        distance_moved = requested_distance
    else:
        # Ci si ferma lungo la stessa direzione, al massimo raggiungibile.
        ratio = movement_points / requested_distance if requested_distance > 0 else 0
        new_pos = clamp_to_grid(
            current_pos["x"] + (target["x"] - current_pos["x"]) * ratio,
            current_pos["y"] + (target["y"] - current_pos["y"]) * ratio,
        )
        moved_fully = False
        distance_moved = movement_points

    blocked_by_crater = False
    if terrain_effects:
        clipped = clip_path_for_craters(current_pos, new_pos, terrain_effects)
        if clipped != new_pos:
            new_pos = clipped
            moved_fully = False
            blocked_by_crater = True
            distance_moved = distance_between(current_pos, new_pos)

    return moved_fully, new_pos, distance_moved, blocked_by_crater


def wander_opponent(current_pos: dict) -> dict:
    """Sposta l'avversario di un piccolo passo a caso - Fase 1: solo
    per 'sembrare vivo' sullo schermo, nessun effetto tattico (richiesto
    in chat). Un piccolo raggio fisso, non i suoi Punti Movimento veri -
    non sta scegliendo strategicamente dove andare, sta solo
    dimenandosi un po'."""
    wander_radius = 1.2
    dx = random.uniform(-wander_radius, wander_radius)
    dy = random.uniform(-wander_radius, wander_radius)
    return clamp_to_grid(current_pos["x"] + dx, current_pos["y"] + dy)


# --- Mappa 2D: Fase 2 (portata delle tecniche e vincoli reali) ------------
# Qui la posizione INIZIA a contare per davvero, non solo per l'occhio
# (richiesto in chat, sequenziato come gli Imprevisti). Semplificazione
# dichiarata sulla portata: non modelliamo la portata precisa di ogni
# singola tecnica del catalogo (centinaia di casi diversi) - solo la
# distinzione 'ho una tecnica vera' (colpisce a distanza, come ci si
# aspetta da energia/tecniche Saint Seiya) contro 'sto solo tirando
# pugni' (l'Attacco Base, che richiede stare vicini).
MELEE_RANGE = 2.0  # entro questa distanza, anche l'Attacco Base funziona
HEAVY_MOVEMENT_RATIO = 0.5  # oltre metà dei Punti Movimento spesi in un round, niente attacco quel round


def is_technique_ranged(technique_name: str) -> bool:
    """Le tecniche vere (qualunque nome diverso da 'Attacco Base')
    colpiscono a distanza. Solo l'Attacco Base richiede stare vicini."""
    return technique_name != "Attacco Base"


def check_attack_range(attacker_pos: dict, defender_pos: dict, technique_name: str) -> bool:
    """True se l'attacco è a portata da dove ci si trova ora."""
    if is_technique_ranged(technique_name):
        return True
    return distance_between(attacker_pos, defender_pos) <= MELEE_RANGE


def movement_uses_turn(distance_moved_this_round: float, movement_points: int) -> bool:
    """True se ci si è mossi abbastanza da consumare tutto il turno -
    oltre metà dei propri Punti Movimento in un solo round."""
    return distance_moved_this_round > movement_points * HEAVY_MOVEMENT_RATIO


LONG_RANGE = 6.0  # oltre questa distanza, anche un attacco a distanza perde smalto
LONG_RANGE_DAMAGE_MULTIPLIER = 0.8


def range_effect(distance: float, technique_name: str) -> tuple[str, float]:
    """Come la distanza modifica un attacco A DISTANZA (le tecniche
    vere - l'Attacco Base ha già il suo vincolo di portata secco, vedi
    check_attack_range, e non riceve qui nessuna penalità aggiuntiva).
    Richiesto in chat: la distanza doveva contare anche in modo
    graduale quando si è comunque a portata, non solo come
    porta/non-porta. Oltre LONG_RANGE: meno preciso (svantaggio sul
    tiro) e un po' più debole; entro LONG_RANGE nessun effetto per ora.
    Restituisce (roll_mode, moltiplicatore_danno)."""
    if not is_technique_ranged(technique_name):
        return "normale", 1.0
    if distance > LONG_RANGE:
        return "svantaggio", LONG_RANGE_DAMAGE_MULTIPLIER
    return "normale", 1.0


def combine_roll_modes(mode_a: str, mode_b: str) -> str:
    """Combina due modificatori di tiro (es. un Imprevisto e la
    distanza) - vantaggio e svantaggio insieme si annullano a vicenda,
    regola classica D&D, invece di sommarsi o di sceglierne uno a caso."""
    if mode_a == mode_b:
        return mode_a
    modes = {mode_a, mode_b}
    if "vantaggio" in modes and "svantaggio" in modes:
        return "normale"
    return mode_a if mode_a != "normale" else mode_b


# --- Mappa 2D: Fase 3 (effetti sul terreno) --------------------------
# Richiesto in chat, ultimo pezzo della sequenza mappa: il terreno
# stesso diventa parte della battaglia, non solo i combattenti. Quattro
# effetti, ciascuno con una firma meccanica DIVERSA (non varianti
# estetiche dello stesso effetto - richiesto in chat):
#   Ghiaccio  -> chiazza TEMPORANEA, svantaggio sul proprio tiro
#   Fuoco     -> zona di Fiamme TEMPORANEA, danno continuo a chi ci sta sopra
#   Acqua     -> Fango TEMPORANEO, dimezza i Punti Movimento di chi ci si trova
#   (danno alto, qualunque elemento) -> cratere PERMANENTE, blocca il passaggio
# La griglia resta continua (non a caselle, deciso nella Fase 1) - gli
# effetti sono zone circolari con un centro e un raggio, non celle
# colorate.
ICE_PATCH_RADIUS = 1.3
ICE_PATCH_DURATION_ROUNDS = 4

FLAME_ZONE_RADIUS = 1.2
FLAME_ZONE_DURATION_ROUNDS = 3
FLAME_ZONE_DAMAGE_PER_ROUND = 3

MUD_ZONE_RADIUS = 1.3
MUD_ZONE_DURATION_ROUNDS = 4
MUD_MOVEMENT_PENALTY_RATIO = 0.5  # dimezza i Punti Movimento di chi ci si trova

CRATER_RADIUS = 0.9
CRATER_DAMAGE_THRESHOLD = 15  # un colpo che fa almeno questo danno lascia un cratere


def maybe_create_terrain_effect(position: dict, tech_type: str, damage: int) -> dict | None:
    """Se il colpo appena andato a segno lascia un effetto sul terreno,
    lo restituisce (None altrimenti) - il chiamante lo aggiunge a
    battle_state['terrain_effects']. Gli elementi naturali (Ghiaccio,
    Fuoco, Acqua) hanno priorità sul cratere: un colpo abbastanza forte
    da fare da cratere ma con un elemento riconosciuto lascia comunque
    il segno del suo elemento, non un buco nel terreno (più coerente
    narrativamente - il ghiaccio non scava, il fuoco non incrina)."""
    tech_type_lower = (tech_type or "").lower()
    if "ghiaccio" in tech_type_lower:
        return {"kind": "ghiaccio", "x": position["x"], "y": position["y"],
                "radius": ICE_PATCH_RADIUS, "rounds_left": ICE_PATCH_DURATION_ROUNDS}
    if "fuoco" in tech_type_lower:
        return {"kind": "fiamme", "x": position["x"], "y": position["y"],
                "radius": FLAME_ZONE_RADIUS, "rounds_left": FLAME_ZONE_DURATION_ROUNDS}
    if "acqua" in tech_type_lower:
        return {"kind": "fango", "x": position["x"], "y": position["y"],
                "radius": MUD_ZONE_RADIUS, "rounds_left": MUD_ZONE_DURATION_ROUNDS}
    if damage >= CRATER_DAMAGE_THRESHOLD:
        return {"kind": "cratere", "x": position["x"], "y": position["y"],
                "radius": CRATER_RADIUS, "rounds_left": None}  # None = permanente per lo scontro
    return None


def tick_terrain_effects(effects: list[dict]) -> None:
    """Fa scadere gli effetti temporanei (Ghiaccio/Fiamme/Fango) di un
    round; i crateri (rounds_left=None) restano per sempre, come da
    specifica. Muta `effects` in place (rimuove quelli scaduti)."""
    still_active = []
    for e in effects:
        if e["rounds_left"] is None:
            still_active.append(e)
            continue
        e["rounds_left"] -= 1
        if e["rounds_left"] > 0:
            still_active.append(e)
    effects[:] = still_active


def position_in_ice_patch(position: dict, effects: list[dict]) -> bool:
    """True se la posizione data è dentro una chiazza di Ghiaccio ancora
    attiva - chi ci sta sopra è meno preciso (svantaggio sul suo tiro)."""
    return any(
        e["kind"] == "ghiaccio" and distance_between(position, e) <= e["radius"]
        for e in effects
    )


def apply_flame_damage(fighter_name: str, fighter: dict, position: dict, effects: list[dict]) -> str | None:
    """Se la posizione è dentro una zona di Fiamme ancora attiva,
    infligge il danno continuo e restituisce il messaggio di log (None
    se non ci si trova dentro nessuna). Chiamata una volta a testa ad
    ogni round, come il Veleno - ma qui è il TERRENO a bruciare, non un
    effetto legato al combattente."""
    for e in effects:
        if e["kind"] == "fiamme" and distance_between(position, e) <= e["radius"]:
            fighter["cosmo_cur"] = max(0, fighter["cosmo_cur"] - FLAME_ZONE_DAMAGE_PER_ROUND)
            return f"🔥 {fighter_name} è nelle fiamme! -{FLAME_ZONE_DAMAGE_PER_ROUND} Cosmo."
    return None


def apply_mud_penalty(movement_points: int, position: dict, effects: list[dict]) -> int:
    """Se ci si trova nel Fango, i Punti Movimento disponibili per
    questo spostamento sono dimezzati - il terreno viscido rallenta
    fisicamente, un effetto diverso dal Ghiaccio (che tocca la
    precisione, non la velocità)."""
    in_mud = any(
        e["kind"] == "fango" and distance_between(position, e) <= e["radius"]
        for e in effects
    )
    if in_mud:
        return max(1, round(movement_points * MUD_MOVEMENT_PENALTY_RATIO))
    return movement_points


def clip_path_for_craters(current_pos: dict, target_pos: dict, effects: list[dict]) -> dict:
    """Se il percorso in linea retta verso target_pos attraversa un
    cratere, ci si ferma appena prima di entrarci - i crateri bloccano
    il passaggio (richiesto in chat). Approssimato campionando il
    segmento a piccoli passi (sufficiente alla scala della mappa,
    non serve una vera intersezione geometrica cerchio-retta).

    Bug corretto (richiesto in chat): se ci si trova GIÀ dentro un
    cratere (es. l'avversario ne ha appena aperto uno proprio sotto i
    piedi), quel cratere non deve bloccare il movimento - altrimenti
    ogni tentativo di uscirne veniva fermato a distanza 0, intrappolando
    il personaggio per sempre. Un cratere in cui non ci si trova già
    continua invece a bloccare regolarmente l'ingresso."""
    all_craters = [e for e in effects if e["kind"] == "cratere"]
    # I crateri in cui ci si trova già non contano come ostacolo per
    # QUESTO movimento - si può sempre uscire da dove si è intrappolati.
    craters = [c for c in all_craters if distance_between(current_pos, c) > c["radius"]]
    if not craters:
        return target_pos
    steps = 24
    last_safe = dict(current_pos)
    for i in range(1, steps + 1):
        t = i / steps
        candidate = {
            "x": current_pos["x"] + (target_pos["x"] - current_pos["x"]) * t,
            "y": current_pos["y"] + (target_pos["y"] - current_pos["y"]) * t,
        }
        if any(distance_between(candidate, c) <= c["radius"] for c in craters):
            return last_safe
        last_safe = candidate
    return target_pos


# --- Provenienza: gerarchia geografica e affinità elementale ---------------
# Prima la Provenienza era un elenco piatto di 10 nazioni (segnalato in
# chat: troppo scarno). Ora è un vero albero Continente -> Macrozona ->
# Nazione, con più nazioni possibili incluse - l'affinità elementale
# resta legata alla MACROZONA (non a ogni singola nazione: con un
# centinaio di nazioni sarebbe stato ingestibile assegnarne una a testa
# in modo sensato, mentre un continente/regione condivide un clima e
# un immaginario più coerenti). GEO_ORIGINS è la fonte di verità unica
# (anche per il frontend, che la legge da GET /geo-origins) -
# ORIGIN_ELEMENT_AFFINITY viene DERIVATA da qui, non scritta a mano.
GEO_ORIGINS = {
    "Europa": {
        "Nord Europa": {"element": "ghiaccio", "countries": ["Svezia", "Norvegia", "Finlandia", "Danimarca", "Islanda"]},
        "Europa Orientale": {"element": "ghiaccio", "countries": ["Russia", "Ucraina", "Bielorussia", "Polonia", "Lituania", "Lettonia", "Estonia"]},
        "Europa Mediterranea": {"element": "cosmico", "countries": ["Grecia", "Italia", "Spagna", "Portogallo", "Malta", "Cipro"]},
        "Europa Occidentale": {"element": "fisico", "countries": ["Francia", "Germania", "Regno Unito", "Irlanda", "Belgio", "Paesi Bassi", "Lussemburgo", "Svizzera", "Austria"]},
        "Balcani e Europa Centrale": {"element": "fisico", "countries": ["Serbia", "Croazia", "Romania", "Bulgaria", "Slovenia", "Bosnia ed Erzegovina", "Albania", "Macedonia del Nord", "Montenegro", "Ungheria"]},
    },
    "Asia": {
        "Asia Orientale": {"element": "cosmico", "countries": ["Giappone", "Cina", "Corea del Sud", "Corea del Nord", "Taiwan", "Mongolia"]},
        "Asia Meridionale": {"element": "psichico", "countries": ["India", "Pakistan", "Bangladesh", "Sri Lanka", "Nepal", "Bhutan"]},
        "Asia Sud-Orientale": {"element": "fuoco", "countries": ["Thailandia", "Vietnam", "Indonesia", "Filippine", "Malesia", "Singapore", "Myanmar", "Cambogia", "Laos"]},
        "Medio Oriente": {"element": "fuoco", "countries": ["Arabia Saudita", "Emirati Arabi Uniti", "Iran", "Iraq", "Israele", "Turchia", "Giordania", "Libano", "Qatar", "Kuwait"]},
        "Asia Centrale": {"element": "ghiaccio", "countries": ["Kazakistan", "Uzbekistan", "Turkmenistan", "Kirghizistan", "Tagikistan"]},
    },
    "Africa": {
        "Africa del Nord": {"element": "psichico", "countries": ["Egitto", "Marocco", "Algeria", "Tunisia", "Libia"]},
        "Africa Occidentale": {"element": "fisico", "countries": ["Nigeria", "Ghana", "Senegal", "Costa d'Avorio", "Mali"]},
        "Africa Orientale": {"element": "fisico", "countries": ["Kenya", "Etiopia", "Tanzania", "Uganda", "Somalia"]},
        "Africa Australe": {"element": "fisico", "countries": ["Sudafrica", "Zimbabwe", "Botswana", "Namibia", "Mozambico"]},
        "Africa Centrale": {"element": "fuoco", "countries": ["Repubblica Democratica del Congo", "Camerun", "Angola", "Gabon"]},
    },
    "Nord America": {
        "America Settentrionale": {"element": "ghiaccio", "countries": ["Canada", "Stati Uniti", "Groenlandia"]},
        "Centro America e Caraibi": {"element": "fuoco", "countries": ["Messico", "Cuba", "Giamaica", "Repubblica Dominicana", "Panama", "Costa Rica", "Guatemala"]},
    },
    "Sud America": {
        "Sud America Tropicale": {"element": "fuoco", "countries": ["Brasile", "Colombia", "Venezuela", "Ecuador", "Perù"]},
        "Sud America Australe": {"element": "fisico", "countries": ["Argentina", "Cile", "Uruguay", "Paraguay", "Bolivia"]},
    },
    "Oceania": {
        "Oceania": {"element": "fisico", "countries": ["Australia", "Nuova Zelanda", "Figi", "Papua Nuova Guinea", "Samoa"]},
    },
}


def _build_origin_affinity() -> dict[str, str]:
    """Deriva {nazione: elemento} da GEO_ORIGINS - una sola fonte di
    verità, invece di un elenco scritto a mano che potrebbe disallinearsi."""
    flat = {}
    for macrozones in GEO_ORIGINS.values():
        for zone in macrozones.values():
            for country in zone["countries"]:
                flat[country] = zone["element"]
    return flat


ORIGIN_ELEMENT_AFFINITY = _build_origin_affinity()
AFFINITY_ATTACK_BONUS = 1.15
AFFINITY_DEFENSE_RESISTANCE = 0.85


def origin_affinity_modifier(origin: str, tech_type: str, as_attacker: bool) -> float:
    """Restituisce il moltiplicatore di danno dovuto all'affinità
    elementale della Provenienza (1.0 se non c'è corrispondenza)."""
    affinity = ORIGIN_ELEMENT_AFFINITY.get(origin)
    if not affinity or affinity not in (tech_type or "").lower():
        return 1.0
    return AFFINITY_ATTACK_BONUS if as_attacker else AFFINITY_DEFENSE_RESISTANCE


# --- Mappa 2D: Fase 4 (arene multiple) --------------------------------
# Ultima fase della sequenza mappa, richiesta in chat: puramente
# estetica, nessuna nuova meccanica. L'arena viene scelta in base
# all'elemento affine della PROVENIENZA dell'avversario (che già
# conosciamo, vedi ORIGIN_ELEMENT_AFFINITY) - un rivale del ghiaccio ti
# sfida in un'arena innevata, uno del fuoco in un deserto, ecc. Più
# sensato di un tema scelto a caso senza nessun legame con lo scontro.
ARENA_THEMES_BY_ELEMENT = {
    "ghiaccio": "siberia",
    "fuoco": "deserto",
    "cosmico": "atene",
    "fisico": "colosseo",
    "psichico": "piramidi",
}
DEFAULT_ARENA_THEME = "atene"


def pick_arena_theme(opponent_origin: str) -> str:
    """Sceglie il tema grafico dell'arena in base alla provenienza
    dell'avversario. Se la provenienza non ha un'affinità elementale
    nota (o è vuota), usa Atene come sfondo predefinito."""
    element = ORIGIN_ELEMENT_AFFINITY.get(opponent_origin)
    return ARENA_THEMES_BY_ELEMENT.get(element, DEFAULT_ARENA_THEME)


# --- Tecniche personalizzate ------------------------------------------
# Richiesto in chat: i giocatori possono creare nuove tecniche, ma
# devono essere "correlate" all'armatura o al background del
# personaggio, e pesate sul livello attuale. Invece di provare a
# giudicare un testo libero (nessuno strumento di comprensione
# semantica affidabile per questo), la correlazione è garantita dalla
# STRUTTURA: l'elemento della nuova tecnica deve essere uno di quelli
# già presenti nelle tecniche vere dell'armatura, o l'affinità della
# Provenienza - un elenco chiuso, non testo libero.
CUSTOM_TECHNIQUE_UNLOCK_LEVELS = [5, 15, 30, 50]  # ogni soglia raggiunta = +1 slot


def custom_technique_slots(player_level: int) -> int:
    """Quanti slot di tecnica personalizzata sono sbloccati al livello
    dato - una soglia raggiunta, uno slot in più."""
    return sum(1 for lvl in CUSTOM_TECHNIQUE_UNLOCK_LEVELS if player_level >= lvl)


def calculate_custom_technique_power(player_level: int) -> int:
    """Pesa la potenza di una tecnica personalizzata sul livello
    attuale del personaggio (richiesto in chat) - PLACEHOLDER come le
    altre formule di bilanciamento in questo file, mai tarata sul
    serio: scala da 60 (livello 1) a 95 (livello 50 o oltre), la stessa
    scala delle tecniche vere del catalogo per le armature più forti.
    Mai scelta dal giocatore, per evitare abusi."""
    return 60 + min(player_level, 50) * 35 // 50


def allowed_custom_technique_elements(armor_techniques: list[dict], origin: str) -> list[str]:
    """Gli elementi ammessi per una tecnica personalizzata di questo
    personaggio: quelli già presenti nel tech_type delle sue tecniche
    vere (es. 'Cosmico/Fisico' -> 'Cosmico', 'Fisico'), più l'affinità
    elementale della sua Provenienza, se ne ha una. Elenco chiuso e
    ordinato, mostrato come scelta - non testo libero.
    IMPORTANTE (richiesto in chat: "come fai a dargli una reale
    manifestazione in game?" per le tecniche personalizzate) - questa
    funzione limita solo QUALI elementi si possono scegliere; l'effetto
    di stato che ne deriva (Veleno, Bruciatura, Paralisi, Confusione,
    Pietrificazione/Intrappolamento) è deciso da maybe_apply_status più
    sotto, che legge il tech_type SCELTO QUI e si comporta in modo
    identico sia per una tecnica del catalogo sia per una personalizzata
    - stesso meccanismo, nessun trattamento speciale per l'una o l'altra."""
    elements = set()
    for t in armor_techniques:
        for word in (t.get("tech_type") or "").split("/"):
            word = word.strip()
            if word:
                elements.add(word)
    affinity = ORIGIN_ELEMENT_AFFINITY.get(origin)
    if affinity:
        elements.add(affinity.capitalize())
    return sorted(elements)


# --- Ciclo elementale circolare -----------------------------------------
# Richiesto in chat: gli stessi 5 elementi già usati per l'affinità di
# Provenienza, ma qui in un cerchio - ognuno forte contro il successivo,
# debole contro il precedente, come sasso-carta-forbice a 5 vie
# (Ghiaccio spegne la lucidità dello Psichico, l'Illusione psichica
# disorienta il Cosmico, il Cosmico travolge il Fisico puro, il Fisico
# resiste e spegne il Fuoco, il Fuoco scioglie il Ghiaccio - chiude il
# cerchio). Si applica SOLO quando due tecniche si scontrano
# direttamente (un Contrattacco contro l'attacco che lo ha causato, o
# una tecnica difensiva vera contro l'attacco che para) - non ai colpi
# dichiarati a freddo, dove non c'è una tecnica avversaria con cui
# confrontarsi (lì resta l'affinità di Provenienza, un sistema diverso
# e già esistente, non toccato da questo).
ELEMENT_CYCLE = ["ghiaccio", "psichico", "cosmico", "fisico", "fuoco"]
CYCLE_ADVANTAGE_MULTIPLIER = 1.15
CYCLE_DISADVANTAGE_MULTIPLIER = 0.85


def _cycle_element(tech_type: str) -> str | None:
    """Trova il primo elemento del ciclo presente nel tech_type dato, o
    None se la tecnica non usa nessuno dei 5 elementi del ciclo (es.
    Veleno, Illusione, Armi... - non tutte le tecniche del catalogo
    rientrano nel ciclo)."""
    tech_type_lower = (tech_type or "").lower()
    for element in ELEMENT_CYCLE:
        if element in tech_type_lower:
            return element
    return None


def cycle_modifier(attacker_tech_type: str, defender_tech_type: str) -> float:
    """Il moltiplicatore di danno dato dal ciclo elementale, quando due
    tecniche si scontrano direttamente. 1.0 se uno dei due elementi non
    è nel ciclo, o se sono lo stesso elemento (nessun vantaggio)."""
    att = _cycle_element(attacker_tech_type)
    dfn = _cycle_element(defender_tech_type)
    if att is None or dfn is None or att == dfn:
        return 1.0
    idx = ELEMENT_CYCLE.index(att)
    if dfn == ELEMENT_CYCLE[(idx + 1) % len(ELEMENT_CYCLE)]:
        return CYCLE_ADVANTAGE_MULTIPLIER  # l'attaccante ha il vantaggio del ciclo
    if dfn == ELEMENT_CYCLE[(idx - 1) % len(ELEMENT_CYCLE)]:
        return CYCLE_DISADVANTAGE_MULTIPLIER  # l'attaccante è in svantaggio
    return 1.0  # elementi non adiacenti nel ciclo, nessun effetto


def cycle_narrative(attacker_tech_type: str, defender_tech_type: str) -> str | None:
    """Una riga di narrazione quando il ciclo elementale scatta (in un
    senso o nell'altro) - None se non c'è nessun effetto da segnalare."""
    modifier = cycle_modifier(attacker_tech_type, defender_tech_type)
    if modifier == CYCLE_ADVANTAGE_MULTIPLIER:
        att = _cycle_element(attacker_tech_type).capitalize()
        dfn = _cycle_element(defender_tech_type).capitalize()
        return f"🌀 {att} ha la meglio su {dfn}!"
    if modifier == CYCLE_DISADVANTAGE_MULTIPLIER:
        att = _cycle_element(attacker_tech_type).capitalize()
        dfn = _cycle_element(defender_tech_type).capitalize()
        return f"🌀 {dfn} tiene testa a {att}!"
    return None


def resolve_defense(raw_damage: int, defense_technique_power: int | None) -> int:
    """Riduce il danno grezzo in base alla potenza della tecnica
    difensiva (o della Parata generica, se non ne hai una)."""
    defense_power = defense_technique_power if defense_technique_power is not None else DEFAULT_DEFENSE_POWER
    reduction = round(defense_power / 10)
    return max(0, raw_damage - reduction)


def choose_opponent_action(opponent: dict, faction_disposition: str = "neutrale") -> tuple[str, dict | None]:
    """Sceglie l'azione PROATTIVA dell'avversario: Attacca o Carica.
    Difendi non è più una scelta proattiva 'alla cieca' - è reattiva
    (vedi opponent_reacts), decisa solo quando è l'avversario a SUBIRE
    un attacco, non quando lo dichiara lui. I pesi dipendono dal vero
    allineamento dell'avversario (richiesto in chat, effetti più
    ampi): un Malvagio è più aggressivo e meno paziente, un Buono più
    misurato. `faction_disposition` (richiesto in chat, "i modi di
    agire delle fazioni"): un tocco leggero in più dalla leadership
    della sua fazione, sopra all'allineamento personale - una
    sfumatura, non un'altra difficoltà mascherata."""
    attack_weight, charge_weight = combat_action_weights(opponent.get("alignment", ""), faction_disposition)
    action = random.choices(["attacca", "carica"], weights=[attack_weight, charge_weight])[0]

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


# --- Stati di combattimento -----------------------------------------------
# V1 (collaudata prima): Veleno (danno nel tempo), Pietrificazione/
# Intrappolamento come Paralisi TOTALE (bloccano un turno intero con
# certezza - coerente col tema: essere pietrificati o intrappolati non
# lascia scampo).
#
# V2 (richiesto in chat, espansione): il catalogo usa anche altri
# elementi ricorrenti che non avevano ancora un effetto meccanico -
# Fuoco, Elettrico, Psichico. Aggiunti con una firma DIVERSA ciascuno,
# non varianti dello stesso meccanismo:
#   Fuoco     -> Bruciatura: stesso meccanismo del Veleno (danno nel
#                tempo), ma un effetto a sé (non si sommano: un
#                bersaglio già bruciato colpito di nuovo dal Fuoco
#                rinfresca la Bruciatura, non ne accumula una seconda -
#                stessa idea già vista in core/status_effects.py)
#   Elettrico -> Paralisi PARZIALE: a differenza di Pietrificazione/
#                Intrappolamento (sempre garantita), qui il blocco è a
#                PROBABILITÀ, tirata ad ogni turno finché l'effetto
#                dura - una scossa non ti lascia paralizzato con
#                certezza ad ogni istante, ti coglie a tratti
#   Psichico  -> Confusione: NON blocca il turno - costringe a tirare
#                in svantaggio, riusando lo stesso meccanismo già
#                esistente per gli Imprevisti e la distanza
#                (combine_roll_modes) invece di una nuova logica di
#                "probabilità di mancare" scollegata dal resto
STATUS_SAVE_DC = 14  # soglia del tiro salvezza di Volontà contro qualunque nuovo stato

STATUS_RULES = {
    "veleno": {"kind": "veleno", "duration": 3},
    "pietrificazione": {"kind": "paralisi", "duration": 1},
    "intrappolamento": {"kind": "paralisi", "duration": 1},
    "fuoco": {"kind": "bruciatura", "duration": 3},
    "elettrico": {"kind": "paralisi_parziale", "duration": 2, "chance": 0.45},
    "psichico": {"kind": "confusione", "duration": 3},
}


def maybe_apply_status(tech_type: str, technique_power: int) -> dict | None:
    """Se la tecnica appena andata a segno è di un tipo che conosciamo,
    restituisce lo stato da aggiungere al bersaglio. None per una
    tecnica 'normale' o per l'Attacco Base (che non ha nessun
    tech_type). Il primo elemento riconosciuto nel tech_type vince
    (una tecnica composita tipo 'Fuoco/Fisico' applica Bruciatura)."""
    tech_type_lower = (tech_type or "").lower()
    for keyword, rule in STATUS_RULES.items():
        if keyword not in tech_type_lower:
            continue
        if rule["kind"] in ("veleno", "bruciatura"):
            return {
                "kind": rule["kind"],
                "rounds_left": rule["duration"],
                "damage_per_round": max(1, technique_power // 20),
            }
        if rule["kind"] == "paralisi_parziale":
            return {"kind": "paralisi_parziale", "rounds_left": rule["duration"], "chance": rule["chance"]}
        if rule["kind"] == "confusione":
            return {"kind": "confusione", "rounds_left": rule["duration"]}
        return {"kind": "paralisi", "rounds_left": rule["duration"]}  # pietrificazione/intrappolamento
    return None


def status_applied_message(target_name: str, technique_name: str, status: dict) -> str:
    """Il messaggio da mostrare quando un colpo lascia un effetto sul
    bersaglio - diverso a seconda del tipo di stato inflitto."""
    labels = {
        "veleno": f"⚠️ {target_name} è avvelenato da {technique_name}!",
        "bruciatura": f"🔥 {target_name} prende fuoco per colpa di {technique_name}!",
        "paralisi": f"🥶 {target_name} è pietrificato da {technique_name}!",
        "paralisi_parziale": f"⚡ {target_name} è scosso da {technique_name} - rischia di paralizzarsi ad ogni turno!",
        "confusione": f"💫 {target_name} è confuso da {technique_name} - i suoi colpi saranno meno precisi!",
    }
    return labels.get(status["kind"], f"{target_name} subisce un effetto da {technique_name}.")


def status_resisted(defender_vol: int) -> bool:
    """Tiro salvezza di Volontà contro un nuovo stato - se supera la
    soglia STATUS_SAVE_DC, l'effetto non si applica affatto (il colpo
    fa comunque il suo danno normale, solo l'effetto extra viene
    resistito). Richiesto in chat: dare un ruolo vero alla Volontà,
    prima non contava nulla in combattimento. Vale per qualunque stato,
    non solo Veleno/Paralisi originari."""
    return DnDEngine.resolve_saving_throw(defender_vol, STATUS_SAVE_DC)


def tick_statuses(fighter_name: str, fighter: dict, statuses: list[dict]) -> tuple[list[str], bool, bool]:
    """Applica gli effetti degli stati ATTIVI su `fighter` a inizio del
    suo turno (danno da Veleno/Bruciatura, blocco da Paralisi/Paralisi
    Parziale), poi fa scadere di un round chi è arrivato a zero. Muta
    `statuses` in place (rimuove quelli scaduti quando la lista viene
    ricostruita dal chiamante).
    Restituisce (messaggi, bloccato, in_svantaggio):
    - bloccato=True se questo turno il personaggio non può agire
      affatto (Paralisi totale, o Paralisi Parziale quando la
      probabilità scatta questo giro) - il chiamante deve saltare la
      sua azione, non risolverla normalmente.
    - in_svantaggio=True se la Confusione è attiva: il personaggio PUÒ
      agire, ma il suo prossimo attacco va tirato in svantaggio - il
      chiamante lo combina con combine_roll_modes insieme agli altri
      modificatori (Imprevisti, distanza, Ghiaccio) invece di gestirlo
      a parte."""
    messages = []
    blocked = False
    confused = False
    still_active = []

    for status in statuses:
        if status["kind"] in ("veleno", "bruciatura"):
            dmg = status["damage_per_round"]
            fighter["cosmo_cur"] = max(0, fighter["cosmo_cur"] - dmg)
            label = "Veleno" if status["kind"] == "veleno" else "Bruciatura"
            icon = "☠️" if status["kind"] == "veleno" else "🔥"
            messages.append(f"{icon} {fighter_name} soffre per la {label}! -{dmg} Cosmo.")
        elif status["kind"] == "paralisi":
            blocked = True
            messages.append(f"🥶 {fighter_name} è paralizzato e non riesce a muoversi!")
        elif status["kind"] == "paralisi_parziale":
            if random.random() < status["chance"]:
                blocked = True
                messages.append(f"⚡ {fighter_name} viene scosso e perde il turno!")
        elif status["kind"] == "confusione":
            confused = True
            messages.append(f"💫 {fighter_name} è ancora confuso.")

        status["rounds_left"] -= 1
        if status["rounds_left"] > 0:
            still_active.append(status)
        else:
            kind_labels = {
                "veleno": "Veleno", "bruciatura": "Bruciatura", "paralisi": "Paralisi",
                "paralisi_parziale": "Paralisi", "confusione": "Confusione",
            }
            messages.append(f"L'effetto {kind_labels.get(status['kind'], status['kind'])} su {fighter_name} è svanito.")

    statuses[:] = still_active
    return messages, blocked, confused
