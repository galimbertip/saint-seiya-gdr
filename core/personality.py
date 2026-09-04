"""Il sistema Tratto/Ideale/Legame/Difetto per i PNG (richiesto in
chat, dal documento di roadmap: "caratterizzazione più profonda dei
PNG" - risolve un punto rimasto in sospeso fin dall'inizio del
progetto). Stesso principio già consolidato altrove (allineamento
mai mostrato, generato una volta e persistito): quattro frasi brevi
che danno personalità vera a un PNG con un tocco leggero - nessuna
nuova interfaccia complessa, un piccolo blocco di testo ovunque un
PNG viene già mostrato (Taverna, Gerarchia, missioni).

Il Tratto, il Legame e il Difetto sono generici (non legati
all'allineamento - un'abitudine caratteriale o un attaccamento
affettivo non dipendono dall'essere buoni o malvagi). L'Ideale invece
è per forza legato al proprio umore (stesso sistema a 3 categorie già
usato altrove nel progetto, buono/neutrale/malvagio) - un ideale è
per definizione una dichiarazione morale."""

import random

TRAITS = [
    "Si allena anche quando nessuno guarda, per abitudine più che per disciplina.",
    "Parla raramente di sé, ma ascolta tutto quello che gli altri raccontano.",
    "Tiene sempre un piccolo oggetto del proprio villaggio d'origine addosso.",
    "Ride più facilmente del previsto, anche nei momenti sbagliati.",
    "Non dimentica mai un volto, anche a distanza di anni.",
    "Cammina sempre un passo indietro rispetto agli altri, per abitudine di guardia.",
    "Ripete a mezza voce le proprie tecniche mentre le richiama alla mente.",
    "Ha un debole per il cibo del proprio regno d'origine, ovunque si trovi.",
    "Non si siede mai con le spalle rivolte a una porta.",
    "Conta i propri passi quando è nervoso.",
]

IDEALS_BY_MOOD = {
    "buono": [
        "Protezione. Nessuno dovrebbe combattere le proprie battaglie da solo.",
        "Lealtà. Un giuramento fatto vale più della propria vita.",
        "Speranza. Anche nella notte più buia, qualcuno deve restare a guardare le stelle.",
        "Sacrificio. Il proprio dolore non conta, se serve a risparmiarlo a un altro.",
    ],
    "neutrale": [
        "Equilibrio. Ogni forza ha bisogno di un contrappeso, anche la propria.",
        "Maestria. Perfezionare la propria tecnica è l'unico vero obiettivo che conta.",
        "Tradizione. Le regole della propria Casa esistono per un motivo, anche quando non lo si capisce.",
        "Sopravvivenza. Il domani conta più di qualsiasi principio di oggi.",
    ],
    "malvagio": [
        "Potere. Chi è debole non merita di dettare le regole a chi è forte.",
        "Dominio. Il mondo appartiene a chi ha il coraggio di prenderselo.",
        "Vendetta. Un torto subito non si dimentica, si restituisce con gli interessi.",
        "Disprezzo. La compassione è solo un'altra parola per debolezza.",
    ],
}

BONDS = [
    "Deve tutto al proprio Maestro, e lo sa.",
    "Ha un fratello minore che spera un giorno di poter proteggere da Cavaliere.",
    "Porta ancora il lutto per un compagno d'addestramento perso anni fa.",
    "Il proprio villaggio d'origine non sa che è diventato un Cavaliere.",
    "Deve un debito d'onore a qualcuno che non ha mai potuto ripagare.",
    "Si considera in debito con la propria Casa per averlo accolto quando nessun altro lo avrebbe fatto.",
    "Ha promesso a qualcuno, ormai lontano, che sarebbe tornato.",
    "Il proprio nome è stato scelto in onore di un Cavaliere caduto prima di lui.",
    "Custodisce una lettera mai spedita a qualcuno che ha lasciato indietro.",
    "Considera un rivale di lunga data più prezioso di molti alleati.",
]

FLAWS = [
    "Non chiede mai aiuto, nemmeno quando ne avrebbe disperatamente bisogno.",
    "Sottovaluta sistematicamente gli avversari che sembrano meno addestrati di lui.",
    "Fatica a fidarsi di chi non ha già dimostrato il proprio valore in combattimento.",
    "Un'antica umiliazione lo rende impulsivo ogni volta che qualcuno mette in dubbio il suo onore.",
    "Tende a promettere più di quanto possa davvero mantenere.",
    "Non sopporta di perdere, nemmeno in questioni che contano poco.",
    "Fatica a perdonare un tradimento, reale o percepito che sia.",
    "Si isola quando è ferito, invece di cercare aiuto.",
    "Ha una vena di orgoglio che lo spinge a rifiutare consigli non richiesti.",
    "Fatica a credere che qualcuno possa aiutarlo senza secondi fini.",
]


def generate_personality(mood: str) -> dict:
    """Genera un Tratto/Ideale/Legame/Difetto per un nuovo PNG - `mood`
    è l'umore a 3 categorie già derivato dall'allineamento vero
    (core.tavern.alignment_to_mood), non l'allineamento stesso: solo
    l'Ideale ne tiene conto, gli altri tre sono generici."""
    ideals = IDEALS_BY_MOOD.get(mood, IDEALS_BY_MOOD["neutrale"])
    return {
        "trait": random.choice(TRAITS),
        "ideal": random.choice(ideals),
        "bond": random.choice(BONDS),
        "flaw": random.choice(FLAWS),
    }
