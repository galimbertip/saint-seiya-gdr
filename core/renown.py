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


# Lo staff oltre al solo Maestro (richiesto in chat, dalla roadmap:
# "Football Manager - staff, non solo il singolo Maestro: scout,
# medici, allenatori... trasformerebbe il tempo speso in gestione da
# puramente reattivo a proattivo"). Sbloccato dalla Renown invece che
# comprato o assegnato a mano - un aggancio concreto in più alla
# reputazione di fazione, non un sistema scollegato dal resto.
# PLACEHOLDER, come le altre soglie/curve del progetto.
STAFF_MEDICO_RENOWN_THRESHOLD = 150   # la stessa soglia del titolo "Rispettato"
STAFF_MEDICO_REGEN_MULTIPLIER = 1.5   # +50% al recupero passivo di Vita/Cosmo

STAFF_OSSERVATORE_RENOWN_THRESHOLD = 300  # la stessa soglia del titolo "Onorato"
STAFF_OSSERVATORE_AFFINITY_THRESHOLD = 15  # più basso della soglia "legame forte" (25) della Difesa a Ondate - qui basta un rapporto promettente, non già solido


def has_staff_medico(renown: int) -> bool:
    """Il Medico (richiesto in chat) accelera il recupero passivo di
    Vita e Cosmo - sbloccato quando la fazione ti riconosce
    abbastanza da assegnartene uno, non comprato con le Dracme."""
    return renown >= STAFF_MEDICO_RENOWN_THRESHOLD


def regen_multiplier(renown: int) -> float:
    """Il moltiplicatore da applicare al recupero passivo di Vita/Cosmo
    (richiesto in chat) - 1.0 (nessun effetto) finché non si sblocca
    il Medico, altrimenti il bonus vero."""
    return STAFF_MEDICO_REGEN_MULTIPLIER if has_staff_medico(renown) else 1.0


def has_staff_osservatore(renown: int) -> bool:
    """L'Osservatore (richiesto in chat: "un Osservatore che segnala
    PNG con affinità già alta prima ancora di parlarci") - sbloccato a
    una soglia di Renown più alta del Medico, dato che è un vantaggio
    informativo più ampio (tutta la Taverna, non solo il tuo corpo)."""
    return renown >= STAFF_OSSERVATORE_RENOWN_THRESHOLD
