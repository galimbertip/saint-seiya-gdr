"""Figure istituzionali del Sacro Imperio (richiesto in chat): non
giocabili, esistono per dare un minimo di ambientazione/gdr al mondo
di gioco, sullo stesso principio dei due esempi fatti in chat (Il
Grande Sacerdote, Pandora). Testo interamente originale, scritto per
questo progetto - nessuna riga di dialogo o descrizione ripresa
dall'opera originale.

Per restare coerenti con come è stato costruito il resto del progetto
(i cavalieri, giocatori o PNG, hanno sempre nomi originali generati,
mai i nomi dei personaggi del manga/anime), ogni figura qui usa un
TITOLO/RUOLO dove il canone lo prevede già come tale ('Il Grande
Sacerdote' è una carica, non un nome proprio) o un nome mitologico
preesistente e di dominio comune (es. 'Pandora', dalla mitologia
greca, non un'invenzione originale della serie) - mai un nome di
personaggio originale specifico dell'opera."""

INSTITUTIONAL_NPCS = [
    {
        "id": "grande-sacerdote",
        "name": "Il Grande Sacerdote",
        "divinity": "Athena",
        "role": "Guida il Santuario in assenza della Dea, custode delle Dodici Case dello Zodiaco",
        "description": (
            "Una maschera dorata ne nasconde sempre il volto, anche nelle udienze private. "
            "Parla poco e non alza mai la voce: chi lo ha sentito dire due volte la stessa cosa "
            "non è sopravvissuto abbastanza a lungo per raccontarlo. Amministra il Santuario, "
            "convoca i Cavalieri, decide chi merita di attraversare le Dodici Case - tutto "
            "nel nome di Athena, che pochi hanno il privilegio di vedere di persona."
        ),
        "quote": "Il Santuario non dorme mai, cavaliere. E nemmeno io.",
    },
    {
        "id": "pandora",
        "name": "Pandora",
        "divinity": "Hades",
        "role": "Amministra il Castello di Hades e gli Inferi in nome del suo Signore",
        "description": (
            "Cresciuta all'ombra del trono, non porta armatura né combatte in prima persona - "
            "non le serve. Basta un suo cenno perché uno Specter attraversi il Muro dei Lamenti "
            "senza fare domande. Fredda con gli estranei, quasi materna con chi le è fedele, "
            "considera ogni Cavaliere di Athena un intruso in un luogo che, a suo dire, "
            "appartiene di diritto ai morti."
        ),
        "quote": "Gli Inferi non fanno eccezioni. Nemmeno per una Dea.",
    },
    {
        "id": "generale-dei-sette-mari",
        "name": "Il Generale Supremo dei Sette Mari",
        "divinity": "Nettuno",
        "role": "Comanda i Generali Marina e le Colonne dei Sette Mari in nome del Sovrano degli Abissi",
        "description": (
            "Vive più tempo sott'acqua che in superficie, e si vede: la pelle ha il colore "
            "pallido di chi non conosce il sole da anni. Ogni Colonna dei Sette Mari risponde "
            "a lui prima che al proprio Generale - un sistema che ha retto per secoli, e che "
            "non ha intenzione di cambiare per nessun Cavaliere di terraferma."
        ),
        "quote": "La terra vi ha resi arroganti. Il mare non perdona l'arroganza.",
    },
    {
        "id": "guardiano-di-asgard",
        "name": "Il Guardiano di Asgard",
        "divinity": "Odino",
        "role": "Veglia sul Palazzo di Valhalla e sui Guerrieri Divini in nome del Padre di Tutti",
        "description": (
            "Un'armatura d'inverno permanente, coperta di brina anche nelle sale riscaldate del "
            "palazzo. Parla di rado, e quando lo fa sceglie ogni parola come se pesasse un debito "
            "d'onore. Giudica gli stranieri dal modo in cui reggono il freddo prima ancora che "
            "dal modo in cui combattono."
        ),
        "quote": "Asgard non si conquista con la Forza. Si conquista con l'inverno che porti dentro.",
    },
]


def get_institutional_npcs() -> list[dict]:
    """Tutte le figure istituzionali del mondo di gioco."""
    return INSTITUTIONAL_NPCS


def get_institutional_npc(npc_id: str) -> dict | None:
    """Una figura istituzionale specifica, o None se l'id non esiste."""
    for npc in INSTITUTIONAL_NPCS:
        if npc["id"] == npc_id:
            return npc
    return None
