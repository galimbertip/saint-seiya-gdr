"""La Renown di fazione (richiesto in chat, dalla roadmap di
evoluzione: "Renown/reputazione di fazione... un personaggio guadagna
Renown completando missioni per un'organizzazione, e il rango sale
con soglie crescenti") - un punteggio persistente di reputazione col
PERSONAGGIO GIOCATORE presso la propria fazione, separato
dall'affinità individuale della Taverna (quella è con UN singolo PNG,
questa è con la fazione intera). Cresce completando missioni,
sblocca un titolo onorifico mostrato in Gerarchia."""

# Le soglie (crescenti, richiesto in chat: "il rango sale con soglie
# crescenti") - PLACEHOLDER, come le altre curve di progressione del
# progetto, da tarare insieme col tempo.
RENOWN_TITLES = [
    (0, "Novizio"),
    (50, "Riconosciuto"),
    (150, "Rispettato"),
    (300, "Onorato"),
    (500, "Veterano"),
    (800, "Leggenda della propria Casa"),
]

# Quanta Renown vale ciascun tipo di traguardo (richiesto in chat:
# "le missioni esistenti... darebbero già Renown oltre alla
# ricompensa in Dracme") - PLACEHOLDER.
RENOWN_SCALATA_COMPLETE = 50
RENOWN_GRAPH_MISSION_COMPLETE = 20
RENOWN_TOURNAMENT_PER_ROUND = 10
RENOWN_TOURNAMENT_CHAMPION_BONUS = 30
RENOWN_INFERI_COMPLETE = 25
RENOWN_DEFENSE_PER_WAVE = 15
RENOWN_DEFENSE_VICTORY_BONUS = 40


def renown_title(renown: int) -> str:
    """Il titolo onorifico corrispondente al punteggio di Renown attuale
    (richiesto in chat) - le soglie sono ordinate crescenti,
    restituisce l'ultima raggiunta."""
    title = RENOWN_TITLES[0][1]
    for threshold, name in RENOWN_TITLES:
        if renown >= threshold:
            title = name
        else:
            break
    return title


def renown_next_threshold(renown: int) -> tuple[int, str] | None:
    """La prossima soglia da raggiungere (valore, titolo) - None se il
    personaggio ha già raggiunto il titolo più alto previsto. Utile
    per mostrare "quanto manca" in una schermata futura, non ancora
    usata da nessuna parte per ora."""
    for threshold, name in RENOWN_TITLES:
        if renown < threshold:
            return threshold, name
    return None
