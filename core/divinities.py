"""Le Divinità come vere entità del mondo di gioco (richiesto in chat:
"attualmente le divinità sono viste come armature - differenziamole").
Non giocabili per ora - "per giocare questo personaggio dovremmo
creare un nuovo modo di giocare" (richiesto in chat) - esistono per
dare un vertice vero alla gerarchia di ciascuna fazione, sopra le
Figure Istituzionali.

Stesso principio già seguito per le Figure Istituzionali: nomi
mitologici di dominio comune (Athena, Ade, Zeus...) o titoli/epiteti,
mai un nome di personaggio originale specifico dell'opera. Testo
interamente originale.

Ogni Divinità ha un'armatura di vertice associata (già presente nel
catalogo, la più alta di livello per quella fazione) e un vero
allineamento persistito (richiesto in chat, esteso anche a loro) - che
può cambiare con una "reincarnazione" (richiesto in chat): un evento
MOLTO più raro della successione delle Figure Istituzionali, perché
qui non si tratta di un cambio di carica ma della Divinità stessa che
muore e rinasce in un nuovo ospite."""

DIVINITY_NPCS = [
    {
        "id": "divinity-athena",
        "name": "Athena",
        "divinity": "Athena",
        "armor_name": "Athena",
        "role": "Dea della saggezza e della guerra giusta, protettrice del Sacro Imperio e dell'umanità",
        "description": (
            "Rinasce in un corpo umano ogni volta che il mondo ne ha davvero bisogno, senza "
            "ricordare granché delle vite precedenti finché il proprio Cosmo non si risveglia del "
            "tutto. Governa più con la fiducia che con l'autorità - lascia che il Grande Sacerdote "
            "amministri i dettagli del Santuario, riservandosi le decisioni che nessun altro "
            "dovrebbe prendere al posto suo."
        ),
        "quote": "Non chiedo ai miei Cavalieri di vincere. Chiedo che non smettano mai di provarci.",
    },
    {
        "id": "divinity-hades",
        "name": "Ade",
        "divinity": "Hades",
        "armor_name": "Surplice di Hades",
        "role": "Signore degli Inferi, sovrano dei morti e delle anime dannate",
        "description": (
            "Dorme per secoli nel proprio Surplice, in attesa del momento in cui il rancore verso "
            "la superficie diventa troppo forte per restare sopito. Considera la vita un prestito "
            "temporaneo e la morte l'unica vera proprietà che gli spetti di diritto - un punto di "
            "vista che rende ogni negoziazione con lui, nella migliore delle ipotesi, breve."
        ),
        "quote": "Ogni cosa viva mi appartiene già. Discuto solo i tempi della consegna.",
    },
    {
        "id": "divinity-black-saint",
        "name": "Il Maestro Oscuro",
        "divinity": "Black Saint",
        "armor_name": "Black Gold Cloth dell'Ariete",
        "role": "Non una vera divinità, ma il volto e la volontà dietro le Black Cloth e le Black Gold Cloth corrotte",
        "description": (
            "Non ha un tempio, non ha un culto - ha solo Cavalieri caduti e armature private del "
            "proprio onore, riforgiate nell'ombra. Chi ne parla lo fa sempre con un titolo, mai con "
            "un nome: nessuno è mai stato abbastanza vicino, e vivo, per saperne di più."
        ),
        "quote": "L'onore è un lusso che i vinti non possono più permettersi.",
    },
    {
        "id": "divinity-odino",
        "name": "Odino",
        "divinity": "Odino",
        "armor_name": "God Robe Divina di Odino",
        "role": "Padre di Tutti, sovrano di Asgard e signore dei Guerrieri Divini",
        "description": (
            "Parla raramente in prima persona, preferendo agire attraverso chi porta la sua God "
            "Robe - un'estensione della propria volontà più che un semplice comandante. Giudica il "
            "valore di chiunque dal modo in cui affronta il gelo di Valhalla, convinto che il "
            "coraggio vero si misuri solo nella sofferenza sopportata in silenzio."
        ),
        "quote": "Il ghiaccio non uccide chi è degno. Lo temprà, o lo scarta.",
    },
    {
        "id": "divinity-nettuno",
        "name": "Poseidone",
        "divinity": "Nettuno",
        "armor_name": "Scale di Poseidone",
        "role": "Sovrano degli Abissi, signore dei Sette Mari e dei Generali Marina",
        "description": (
            "Riposa negli abissi più a lungo di quanto governi apertamente, lasciando ai suoi "
            "Generali il compito di far rispettare la propria autorità sulle Colonne dei Sette "
            "Mari. Considera la terraferma un errore temporaneo nella storia del pianeta - una "
            "fase che, prima o poi, l'acqua correggerà da sola."
        ),
        "quote": "La terra ricorderà per sempre chi era qui prima di lei.",
    },
    {
        "id": "divinity-apollo",
        "name": "Apollo",
        "divinity": "Apollo",
        "armor_name": "Kamui / Glory di Apollo",
        "role": "Dio della luce e delle arti, spesso in ombra rispetto alla sorella Athena",
        "description": (
            "Porta la propria Kamui come un ricordo di un tempo in cui la luce non aveva bisogno "
            "di giustificarsi a nessuno. Colto e paziente più della maggior parte delle altre "
            "divinità, ma capace di un orgoglio freddo quando sente il proprio operato messo in "
            "discussione dai figli di Zeus più giovani."
        ),
        "quote": "La luce non chiede permesso per esistere. Chiede solo di essere vista.",
    },
    {
        "id": "divinity-ares",
        "name": "Ares",
        "divinity": "Ares",
        "armor_name": "Galaxy di Marte (Mars)",
        "role": "Dio della guerra, patrono di conflitti che non hanno mai davvero bisogno di una ragione",
        "description": (
            "Non ha bisogno di un motivo per desiderare un campo di battaglia - gli basta che ce ne "
            "sia uno. La sua Galaxy Armor porta i segni di scontri che nessun cronista ha mai osato "
            "raccontare per intero. Rispetta la forza più della causa per cui viene usata."
        ),
        "quote": "Chiedimi perché combatto, e avrai già perso la domanda giusta da fare.",
    },
    {
        "id": "divinity-saturno",
        "name": "Crono di Saturno",
        "divinity": "Saturno",
        "armor_name": "Chronotector di Saturno",
        "role": "Titano del tempo, signore della corrente che tutto consuma e tutto rinnova",
        "description": (
            "Misura ogni cosa in ere, non in giorni - una prospettiva che rende quasi tutto ciò che "
            "gli umani considerano urgente, ai suoi occhi, trascurabile. Il Chronotector che porta "
            "non segna le ore: le decide."
        ),
        "quote": "Ciò che chiami eternità, io lo chiamo un pomeriggio.",
    },
    {
        "id": "divinity-crono",
        "name": "Kronos",
        "divinity": "Crono",
        "armor_name": "Soma della Falce (Megas Drepanon)",
        "role": "Titano primordiale, padre degli dèi dell'Olimpo e sovrano di un'era che precede tutte le altre",
        "description": (
            "Più antico di quasi ogni altra cosa con cui un Cavaliere possa mai incrociare il "
            "Cosmo, porta la propria Soma come il ricordo di un potere che nessuna era successiva "
            "ha mai davvero eguagliato. Guarda gli dèi più giovani con la pazienza tollerante di "
            "chi sa di poter aspettare più a lungo di chiunque altro."
        ),
        "quote": "Ho visto nascere e cadere troppi troni per temerne uno nuovo.",
    },
    {
        "id": "divinity-eris",
        "name": "Eris",
        "divinity": "Eris",
        "armor_name": "Eris Cloth / Mela d'Oro",
        "role": "Dea della discordia, seminatrice di conflitti tra fazioni che altrimenti non si sarebbero mai incontrate",
        "description": (
            "Non combatte quasi mai in prima persona - preferisce lasciare che siano gli altri a "
            "farlo, mentre osserva da lontano quale scintilla attecchisce meglio. La propria Cloth "
            "porta il peso simbolico di una sola mela dorata, ma il conflitto che ne è nato non si è "
            "mai davvero placato."
        ),
        "quote": "Basta un piccolo dono al posto sbagliato, e il resto lo fate da soli.",
    },
    {
        "id": "divinity-lucifero",
        "name": "Lucifero",
        "divinity": "Lucifero",
        "armor_name": "Armatura del Diavolo (Lucifero)",
        "role": "Signore di un dominio infernale distinto dagli Inferi di Ade, sovrano di demoni propri",
        "description": (
            "Governa un angolo di oscurità che nemmeno Ade rivendica apertamente. La sua Armatura "
            "del Diavolo non protegge tanto quanto promette - a chiunque sia disposto ad ascoltare "
            "fino in fondo, e quasi nessuno lo è mai stato senza pentirsene."
        ),
        "quote": "Non offro scelte migliori. Offro solo scelte più oneste.",
    },
    {
        "id": "divinity-artemide",
        "name": "Artemide",
        "divinity": "Artemide",
        "armor_name": "Glory/Corazza di Artemide",
        "role": "Dea della caccia e della luna, sorella gemella di Apollo e patrona di chi non risponde a nessun re",
        "description": (
            "Preferisce i confini selvaggi ai saloni dorati degli altri Olimpi, e la propria Glory "
            "lo dimostra: pensata per muoversi, non per essere ammirata immobile su un trono. Fedele "
            "a chi la segue, spietata con chi tradisce quella fedeltà."
        ),
        "quote": "La luna non illumina chi si nasconde da lei. Lo trova e basta.",
    },
    {
        "id": "divinity-zeus",
        "name": "Zeus",
        "divinity": "Zeus",
        "armor_name": "Armatura Divina (Kamui) di Zeus",
        "role": "Re degli dèi dell'Olimpo, padre (riconosciuto o meno) di gran parte del pantheon in gioco",
        "description": (
            "Governa più per accordi taciti tra pari che per un vero comando universale - persino "
            "gli altri Olimpi rispondono a lui più per convenienza che per sottomissione vera. La "
            "propria Kamui è un ricordo di un'autorità che nessuno, nemmeno lui, oserebbe più "
            "definire assoluta."
        ),
        "quote": "Regnare non significa essere obbediti. Significa restare l'unico che nessuno osa sfidare per primo.",
    },
]


def get_divinity_npcs() -> list[dict]:
    """Tutte le Divinità del mondo di gioco."""
    return DIVINITY_NPCS


def get_divinity_npc(divinity: str) -> dict | None:
    """La Divinità associata a questa fazione/divinity (il campo del
    catalogo armors), o None se non esiste (non dovrebbe mai succedere
    per una delle 13 fazioni note)."""
    for npc in DIVINITY_NPCS:
        if npc["divinity"] == divinity:
            return npc
    return None
