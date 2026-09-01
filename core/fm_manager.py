"""
Gestione allenamento e crescita del personaggio, stile Football Manager.

CAMBIO PRINCIPALE DI QUESTO GIRO: l'orologio non conta più in GIORNI
INTERI (game_day, dove ogni azione = 1 giorno fisso) ma in MINUTI
(game_minutes, fonte di verità unica). Ogni azione ha una durata reale
diversa - un Riposo (dormire) dura più di una sessione di allenamento,
un round in Arena dura minuti, non un giorno intero. Questo è quello
che permette la cosa che il giocatore ha chiesto in chat: allenarsi al
Cosmo la mattina e sfidare qualcuno in Arena lo stesso giorno, invece
di essere bloccati a "un'azione = un giorno" ovunque.

game_day resta nel database per compatibilità/cronologia ma non è più
la fonte di verità: si legge/scrive solo game_minutes da qui in avanti.

Rispetto alle versioni precedenti:
- knight['stamina'] esiste davvero (colonna reale in knights).
- il focus di allenamento copre tutte e 5 le statistiche del personaggio.
- progressione a XP/livello personaggio (player_level).
- allenarsi da esausto non è bloccato in automatico: si può forzare, ma
  si rischia un INFORTUNIO (perde un punto invece di guadagnarlo).
- tipi di allenamento a tema Saint Seiya (Cascata del Sacrificio,
  Sparring con i Compagni) accanto a quelli originali, mai rinominati
  (compatibilità con i programmi settimanali già salvati).

NOTA come per dnd_engine.py: le SOGLIE numeriche (costo stamina, xp per
salire di livello, quanti punti guadagni, probabilità di infortunio,
durata in minuti di ogni azione) sono PLACEHOLDER funzionanti, non
valori definitivi - li tariamo insieme quando affrontiamo il
bilanciamento vero e proprio. La struttura è quella buona.
"""
import random
from database.db_manager import advance_world_minutes
from datetime import datetime, timedelta

from core.arena_manager import get_unlocked_senses

# --- Tipi di allenamento --------------------------------------------------
TRAINING_FOCUS_OPTIONS = [
    "Cosmo", "Forza", "Destrezza", "Costituzione", "Tecnica", "Volontà",
    "Cascata del Sacrificio", "Sparring con i Compagni",
    "Riposo",
]

_STAT_COLUMN_BY_FOCUS = {
    "Forza": "str",
    "Destrezza": "dex",
    "Costituzione": "con",
    "Tecnica": "tec",
    "Volontà": "vol",
    "Cascata del Sacrificio": "con",
}

_STAT_LABELS = {"str": "Forza", "dex": "Destrezza", "con": "Costituzione", "tec": "Tecnica", "vol": "Volontà"}

_STAMINA_COST_RANGES = {
    "Cascata del Sacrificio": (15, 25),
    "Sparring con i Compagni": (12, 22),
}
_DEFAULT_STAMINA_COST_RANGE = (10, 20)

_INJURY_CHANCE_OVERRIDES = {
    "Sparring con i Compagni": 0.5,
    "Cascata del Sacrificio": 0.4,
}
_DEFAULT_INJURY_CHANCE = 0.3
_INJURY_STAT_LOSS = 1

XP_PER_TRAINING_SESSION = 10  # placeholder

WEEKDAY_NAMES = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

DEFAULT_WEEKLY_SCHEDULE = ["Cosmo", "Forza", "Destrezza", "Costituzione", "Tecnica", "Volontà", "Riposo"]
DEFAULT_WEEKLY_SCHEDULE_STR = ",".join(DEFAULT_WEEKLY_SCHEDULE)

# --- Calendario (a minuti) -------------------------------------------------
MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR
# DAYS_PER_MONTH ora serve SOLO per "Avanza Mese" nell'allenamento
# (quante sessioni di fila = un mese di training) - non più per il
# calendario, che è reale (vedi get_calendar_display più sotto).
DAYS_PER_MONTH = 30

MONTH_NAMES = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]

# --- Durata in minuti di ogni azione ---------------------------------------
# PLACEHOLDER: quanto dura "nella finzione" ogni cosa. Un Riposo è un
# sonno vero (8 ore), un allenamento normale mezza giornata, i due tipi
# più duri (Cascata/Sparring) un po' di più. Un round in Arena dura
# minuti, non ore - è uno scambio di colpi, non una sessione.
TRAINING_MINUTES_BY_FOCUS = {
    "Riposo": 8 * MINUTES_PER_HOUR,
    "Cascata del Sacrificio": 6 * MINUTES_PER_HOUR,
    "Sparring con i Compagni": 6 * MINUTES_PER_HOUR,
}
DEFAULT_TRAINING_MINUTES = 4 * MINUTES_PER_HOUR

ARENA_ROUND_MINUTES = 15  # un mezzo-turno di combattimento (dichiari + reagisce l'altro)

# --- Recupero del Cosmo fuori dal combattimento -----------------------
# Fedele al canone (discusso in chat): un Cavaliere che non sta
# combattendo si riprende col tempo, a prescindere da cosa fa
# (allenarsi o riposare) - l'importante è non essere in battaglia.
# Qui il recupero è proporzionale alle ORE che passano quel giorno, non
# legato a un singolo tipo di allenamento: un giorno di riposo (8 ore)
# recupera più della metà rispetto a mezza giornata di allenamento
# duro (6 ore) o normale (4 ore), semplicemente perché è passato più
# tempo. In Arena invece il Cosmo NON si rigenera mai da solo - lì sei
# in combattimento, per definizione.
COSMO_REGEN_PER_HOUR = 2  # PLACEHOLDER: da tarare insieme


def parse_weekly_schedule(schedule_str: str) -> list[str]:
    """Da stringa CSV (come salvata nel DB) a lista di 7 focus. Tollerante:
    se la stringa è vuota, sporca, o più corta di 7 giorni, completa con
    Riposo invece di sollevare un errore - i salvataggi vecchi non
    devono rompersi."""
    days = schedule_str.split(",") if schedule_str else []
    days = [d.strip() for d in days]
    days = [d if d in TRAINING_FOCUS_OPTIONS else "Riposo" for d in days]
    while len(days) < 7:
        days.append("Riposo")
    return days[:7]


def serialize_weekly_schedule(days: list[str]) -> str:
    """Da lista di 7 focus a stringa CSV per il salvataggio nel DB."""
    return ",".join(days[:7])


# Il calendario del mondo (richiesto in chat, come in Football Manager:
# un solo calendario condiviso da tutti i personaggi e i PNG, non più
# uno personale a testa) parte da questa data fissa - "l'inizio del
# mondo" del gioco. world_minutes (vedi database.db_manager) sono i
# minuti trascorsi da qui, condivisi da chiunque.
WORLD_EPOCH = "2026-01-06T08:00:00"


def get_calendar_display(world_minutes: int) -> dict:
    """Calendario REALE, condiviso da tutti (richiesto in chat, stile
    Football Manager: giocare la propria partita fa avanzare il tempo
    per tutti, non solo per te) - world_minutes sommati a WORLD_EPOCH
    con l'aritmetica reale di datetime - niente più calendario fittizio
    a 360 giorni: mesi di lunghezza vera, anni bisestili compresi,
    gratis grazie a datetime. I nomi dei mesi restano quelli scritti a
    mano in MONTH_NAMES (in italiano) invece di strftime('%B'), che
    dipenderebbe dalla lingua del sistema."""
    current = datetime.fromisoformat(WORLD_EPOCH) + timedelta(minutes=world_minutes)

    return {
        "year": current.year,
        "month_index": current.month - 1,
        "month_name": MONTH_NAMES[current.month - 1],
        "day_of_month": current.day,
        "hour": current.hour,
        "minute": current.minute,
        "label": f"{current.day} {MONTH_NAMES[current.month - 1]} {current.year} — ore {current.hour:02d}:{current.minute:02d}",
    }


class RosterManager:

    @staticmethod
    def spend_time(conn, knight: dict, minutes: int) -> str:
        """Fa avanzare l'orologio del MONDO (richiesto in chat, stile
        Football Manager: un solo calendario condiviso da tutti, non
        più uno personale a testa) di `minutes` minuti - la funzione
        che TUTTE le azioni del gioco chiamano ora (allenamento,
        combattimento, in futuro qualsiasi altra cosa), ciascuna con la
        propria durata, invece del vecchio 'ogni azione = 1 giorno
        fisso'. `knight["game_minutes"]` resta aggiornato per
        compatibilità con tutto il codice esistente che lo legge, ma
        ora rispecchia sempre lo stesso valore condiviso da chiunque -
        non è più un conteggio personale. Gestisce l'invecchiamento
        quando si supera un anno. Restituisce un messaggio SOLO se
        scatta un compleanno, stringa vuota altrimenti. Muta `knight`
        in place."""
        previous_year = get_calendar_display(knight["game_minutes"])["year"]
        knight["game_minutes"] = advance_world_minutes(conn, minutes)
        new_year = get_calendar_display(knight["game_minutes"])["year"]

        if new_year > previous_year:
            knight["age"] += (new_year - previous_year)
            return f"🎂 È passato un altro anno! {knight['raw_name']} ora ha {knight['age']} anni."
        return ""

    @staticmethod
    def apply_daily_training(conn, knight: dict, focus: str) -> str:
        """Una sessione di allenamento: consuma stamina, migliora una
        statistica (o riposa), assegna un po' di XP, e fa passare il
        tempo corrispondente a QUEL focus (non più un giorno fisso per
        tutti - vedi TRAINING_MINUTES_BY_FOCUS). Muta `knight` in place.

        Se il personaggio è troppo esausto, la sessione NON viene
        bloccata in automatico: si forza comunque, ma rischia un
        INFORTUNIO (perde un punto invece di guadagnarlo). Il tempo
        passa sempre, in ogni caso - anche in caso di infortunio."""
        if focus not in TRAINING_FOCUS_OPTIONS:
            return f"Focus di allenamento sconosciuto: {focus!r}"

        if focus == "Riposo":
            recovered = min(100 - knight["stamina"], 40)
            knight["stamina"] = min(100, knight["stamina"] + 40)
            msg = f"{knight['raw_name']} si è riposato, recuperando {recovered} di stamina."
        else:
            lo, hi = _STAMINA_COST_RANGES.get(focus, _DEFAULT_STAMINA_COST_RANGE)
            stamina_cost = random.randint(lo, hi)
            forced_while_exhausted = knight["stamina"] < stamina_cost
            knight["stamina"] = max(0, knight["stamina"] - stamina_cost)

            injury_chance = _INJURY_CHANCE_OVERRIDES.get(focus, _DEFAULT_INJURY_CHANCE)
            injured = forced_while_exhausted and random.random() < injury_chance

            if injured:
                msg = RosterManager._apply_injury(knight, focus)
            else:
                msg = RosterManager._apply_training_gain(knight, focus)
                if forced_while_exhausted:
                    msg = f"{msg} (si è spinto oltre la stanchezza, rischiando grosso)"
                xp_msg = RosterManager.add_xp(knight, XP_PER_TRAINING_SESSION)
                if xp_msg:
                    msg = f"{msg} {xp_msg}"

        minutes = TRAINING_MINUTES_BY_FOCUS.get(focus, DEFAULT_TRAINING_MINUTES)

        # Recupero passivo del Cosmo: proporzionale alle ore di questa
        # attività, sempre (non solo con Riposo) - il tempo cura, non
        # importa cosa stai facendo, basta non essere in Arena.
        cosmo_recovered = min(
            knight["cosmo_max"] - knight["cosmo_cur"],
            round(minutes / 60 * COSMO_REGEN_PER_HOUR),
        )
        if cosmo_recovered > 0:
            knight["cosmo_cur"] += cosmo_recovered
            msg = f"{msg} (+{cosmo_recovered} Cosmo recuperato)"

        aging_msg = RosterManager.spend_time(conn, knight, minutes)
        if aging_msg:
            msg = f"{msg} {aging_msg}"

        return msg

    @staticmethod
    def _apply_training_gain(knight: dict, focus: str) -> str:
        if focus == "Cosmo":
            gain = random.randint(1, 3)
            knight["cosmo_max"] += gain
            return f"Allenamento intenso! Il Cosmo massimo di {knight['raw_name']} è aumentato di +{gain}."

        if focus == "Sparring con i Compagni":
            column = random.choice(["str", "dex", "con"])
            knight[column] += 1
            return (f"Sparring acceso! {_STAT_LABELS[column]} di {knight['raw_name']} "
                    f"è aumentata a {knight[column]}.")

        column = _STAT_COLUMN_BY_FOCUS[focus]
        knight[column] += 1
        return f"Esercizi completati! {focus} di {knight['raw_name']} è aumentata a {knight[column]}."

    @staticmethod
    def _apply_injury(knight: dict, focus: str) -> str:
        if focus == "Cosmo":
            loss = min(knight["cosmo_max"], _INJURY_STAT_LOSS)
            knight["cosmo_max"] -= loss
            return (f"⚠️ {knight['raw_name']} si è allenato troppo stanco e si è infortunato! "
                    f"Cosmo massimo -{loss}.")

        column = random.choice(["str", "dex", "con"]) if focus == "Sparring con i Compagni" \
            else _STAT_COLUMN_BY_FOCUS[focus]
        loss = max(0, min(knight[column] - 1, _INJURY_STAT_LOSS))
        knight[column] -= loss
        return (f"⚠️ {knight['raw_name']} si è allenato troppo stanco e si è infortunato! "
                f"{_STAT_LABELS[column]} -{loss}.")

    @staticmethod
    def advance_week(conn, knight: dict, schedule: list[str]) -> list[tuple[str, str, str]]:
        """Applica 7 sessioni di allenamento di fila (una per 'giorno'
        della griglia settimanale). ATTENZIONE (cambiato in questo giro):
        con l'orologio a minuti, 7 sessioni NON corrispondono più
        necessariamente a 7 giorni di calendario - dipende dalla durata
        di ciascun focus scelto (7 Riposo = 56 ore reali = poco più di 2
        giorni; 7 Cascata del Sacrificio = 42 ore = meno di 2 giorni).
        La griglia resta comoda per pianificare 7 sessioni in sequenza,
        ma il nome 'Settimana' è ormai più una convenzione che una
        promessa esatta di 7 giorni di calendario."""
        results = []
        for day_name, focus in zip(WEEKDAY_NAMES, schedule):
            msg = RosterManager.apply_daily_training(conn, knight, focus)
            results.append((day_name, focus, msg))
        return results

    @staticmethod
    def advance_month(conn, knight: dict, schedule: list[str]) -> list[tuple[str, str, str]]:
        """Applica 30 sessioni di allenamento di fila (stesso programma
        settimanale ripetuto), stessa nota di advance_week sul tempo
        reale che ne consegue."""
        results = []
        sessions_done = 0
        week_num = 1
        while sessions_done < DAYS_PER_MONTH:
            sessions_this_round = min(7, DAYS_PER_MONTH - sessions_done)
            for day_name, focus in zip(WEEKDAY_NAMES[:sessions_this_round], schedule[:sessions_this_round]):
                msg = RosterManager.apply_daily_training(conn, knight, focus)
                results.append((f"Sett.{week_num} {day_name}", focus, msg))
            sessions_done += sessions_this_round
            week_num += 1
        return results

    @staticmethod
    def xp_to_next_level(player_level: int) -> int:
        """PLACEHOLDER: curva di progressione, da tarare con le dinamiche vere."""
        return player_level * 100

    @staticmethod
    def add_xp(knight: dict, amount: int) -> str:
        """Aggiunge XP e gestisce eventuali salite di livello (una alla
        volta). Muta `knight` in place. Restituisce un messaggio SOLO se
        c'è stato un level up (stringa vuota altrimenti) - e se quel
        level up sblocca un nuovo Senso, lo annuncia nella stessa riga
        (richiesto in chat: prima il giocatore lo scopriva solo per
        caso, provando i pulsanti in Arena)."""
        knight["xp"] += amount

        threshold = RosterManager.xp_to_next_level(knight["player_level"])
        if knight["xp"] < threshold:
            return ""

        previous_senses = get_unlocked_senses(knight["player_level"])
        knight["xp"] -= threshold
        knight["player_level"] += 1
        knight["cosmo_max"] += 5  # PLACEHOLDER: bonus di livello
        new_senses = get_unlocked_senses(knight["player_level"])

        msg = (f"🎉 {knight['raw_name']} è salito al livello {knight['player_level']}! "
               f"(Cosmo massimo +5)")

        sense_labels = {
            "sesto": "Sesto Senso (sblocca Carica il Cosmo)",
            "settimo": "Settimo Senso (si risveglia da solo in punto di rottura)",
            "ottavo": "Ottavo Senso (sopravvivi al colpo che ti finirebbe)",
            "nono": "Nono Senso",
        }
        for key, label in sense_labels.items():
            if new_senses[key] and not previous_senses[key]:
                msg += f" 🌟 Hai sbloccato il {label}!"

        return msg
