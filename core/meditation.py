"""La Meditazione del Cosmo (richiesto in chat, dalla roadmap:
"mini-giochi ricorrenti... di taglio diverso dagli enigmi delle Prove
degli Inferi" - quelli sono enigmi di LOGICA, questo è un esercizio di
MEMORIA/concentrazione, per dare varietà reale di genere, non solo un
altro indovinello). Un'attività ricorrente e a tempo (non infinita:
un cooldown la rende un rituale quotidiano, non un grinding senza
limiti), tematicamente legata al controllo del proprio Cosmo -
riprodurre a memoria una sequenza crescente di impulsi, come
allenare la propria concentrazione prima di un combattimento vero.

A differenza degli enigmi degli Inferi (che vivono lato server, una
domanda con risposte fisse), qui la sequenza viene generata e
verificata lato CLIENT (nessun dato sensibile in gioco, è un
esercizio di memoria contro se stessi) - il server si occupa solo di
applicare il cooldown e la ricompensa quando il client dichiara il
risultato, stesso principio di leggerezza già seguito per la
Taverna."""

import random

# Il cooldown (richiesto in chat, implicito: un rituale ricorrente,
# non un'attività ripetibile all'infinito nello stesso momento) -
# PLACEHOLDER, come le altre soglie del progetto.
MEDITATION_COOLDOWN_MINUTES = 12 * 60  # circa due volte al giorno di gioco

# Quanto costa in tempo di gioco fare l'esercizio, a prescindere
# dall'esito - una sessione di concentrazione vera richiede comunque
# tempo, anche se fallisce a metà.
MEDITATION_TIME_MINUTES = 30

# La lunghezza della sequenza da ricordare, in base a quante volte il
# personaggio l'ha già superata con successo in passato (richiesto
# implicito: un esercizio che resta una sfida vera anche per un
# personaggio più esperto, non sempre la stessa difficoltà banale).
# PLACEHOLDER.
MEDITATION_BASE_LENGTH = 4
MEDITATION_LENGTH_PER_SUCCESS = 1
MEDITATION_MAX_LENGTH = 12

# La ricompensa: Volontà (non Cosmo massimo) apposta - la Meditazione
# è concentrazione mentale, non allenamento fisico, merita di
# alimentare una statistica diversa dal solito Cosmo massimo di ogni
# altra attività. Cresce con la lunghezza della sequenza superata,
# così una sequenza più lunga vale davvero di più.
MEDITATION_VOLONTA_PER_LENGTH = 1  # +1 Volontà ogni tot anelli della sequenza, vedi resolve_meditation_reward


def next_sequence_length(meditation_successes: int) -> int:
    """Quanto deve essere lunga la prossima sequenza (richiesto in
    chat, implicito: resta una sfida anche più avanti) - cresce con
    quante volte il personaggio l'ha già superata, con un tetto
    massimo oltre il quale non diventa più lunga (altrimenti
    diventerebbe impossibile da memorizzare, non più una sfida
    divertente)."""
    length = MEDITATION_BASE_LENGTH + meditation_successes * MEDITATION_LENGTH_PER_SUCCESS
    return min(length, MEDITATION_MAX_LENGTH)


def generate_sequence(length: int) -> list[int]:
    """La sequenza vera da mostrare al giocatore - 4 simboli possibili
    (0-3), come nel classico gioco Simon Says. Generata lato server e
    inviata al client, così il client non deve inventarsela da solo
    (evita che qualcuno la modifichi via console del browser per
    darsi ragione da solo - non è un problema grave qui, ma è
    comunque la scelta più pulita)."""
    return [random.randint(0, 3) for _ in range(length)]


def resolve_meditation_reward(sequence_length: int) -> dict:
    """La ricompensa per aver completato correttamente una sequenza di
    questa lunghezza - più lunga la sequenza, più Volontà guadagnata.
    PLACEHOLDER, come le altre formule di ricompensa del progetto."""
    volonta_gain = max(1, sequence_length // 3) * MEDITATION_VOLONTA_PER_LENGTH
    return {"volonta": volonta_gain}


def can_meditate(last_meditation_minutes: int, world_minutes: int) -> bool:
    """Se è passato abbastanza tempo dall'ultima Meditazione (richiesto
    in chat, implicito: un rituale ricorrente, non un'attività
    ripetibile senza limiti) - True anche se non si è mai meditato
    prima (last_meditation_minutes a 0)."""
    if last_meditation_minutes <= 0:
        return True
    return world_minutes - last_meditation_minutes >= MEDITATION_COOLDOWN_MINUTES


def minutes_until_next_meditation(last_meditation_minutes: int, world_minutes: int) -> int:
    """Quanti minuti di gioco mancano al prossimo tentativo consentito -
    0 se già disponibile ora. Utile per mostrare "torna tra X ore" nel
    frontend invece di un generico "non disponibile"."""
    if can_meditate(last_meditation_minutes, world_minutes):
        return 0
    return MEDITATION_COOLDOWN_MINUTES - (world_minutes - last_meditation_minutes)
