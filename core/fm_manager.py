"""
Gestione allenamento e crescita del personaggio, stile Football Manager.

Rispetto alla versione originale di Gemini:
- knight['stamina'] ora esiste davvero (colonna reale in knights, non
  più un campo scritto a mano che il DB non aveva).
- il focus di allenamento copre tutte e 5 le statistiche del personaggio
  (str, dex, con, tec, vol), non solo Forza Fisica + Cosmo.
- aggiunta la progressione a XP/livello personaggio (player_level),
  altro campo che nello schema vecchio non esisteva.
- ogni azione (allenamento o riposo) fa passare un giorno intero di
  gioco (knight['game_day']), invece di essere istantanea. L'età
  cresce di conseguenza nel tempo reale di gioco.
- NOVITÀ: allenarsi da esausto non è più bloccato in automatico - puoi
  forzarlo, ma rischi un INFORTUNIO (perdi un punto statistica invece
  di guadagnarlo). Decide il giocatore quanto rischiare, il programma
  settimanale/mensile permette di correggere la rotta in anticipo se
  vede il cavaliere stanco.
- NOVITÀ: nuovi tipi di allenamento a tema Saint Seiya (Cascata del
  Sacrificio, Sparring con i Compagni), aggiunti ACCANTO a quelli
  esistenti - i nomi vecchi (Forza, Cosmo, ecc.) restano invariati
  apposta, per non rompere i programmi settimanali già salvati.

NOTA come per dnd_engine.py: le SOGLIE numeriche (costo stamina, xp per
salire di livello, quanti punti guadagni, probabilità di infortunio,
giorni per anno) sono PLACEHOLDER funzionanti, non valori definitivi -
li tariamo insieme quando affrontiamo il bilanciamento vero e proprio.
La struttura (quali campi cambiano, come si aggiornano) è quella buona.
"""
import random

# --- Tipi di allenamento --------------------------------------------------
# I primi 6 + Riposo sono quelli originali (NON rinominare: sono già
# salvati nei programmi settimanali esistenti). Gli ultimi 2 sono nuovi.
TRAINING_FOCUS_OPTIONS = [
    "Cosmo", "Forza", "Destrezza", "Costituzione", "Tecnica", "Volontà",
    "Cascata del Sacrificio", "Sparring con i Compagni",
    "Riposo",
]

# Mappa focus -> colonna knights da incrementare (i focus speciali -
# Cosmo, Sparring, Riposo - sono gestiti a parte, non stanno qui)
_STAT_COLUMN_BY_FOCUS = {
    "Forza": "str",
    "Destrezza": "dex",
    "Costituzione": "con",
    "Tecnica": "tec",
    "Volontà": "vol",
    "Cascata del Sacrificio": "con",  # variante più dura della Costituzione
}

_STAT_LABELS = {"str": "Forza", "dex": "Destrezza", "con": "Costituzione", "tec": "Tecnica", "vol": "Volontà"}

# Range costo stamina per focus (default 10-20, alcuni costano di più)
_STAMINA_COST_RANGES = {
    "Cascata del Sacrificio": (15, 25),
    "Sparring con i Compagni": (12, 22),
}
_DEFAULT_STAMINA_COST_RANGE = (10, 20)

# Probabilità di infortunio se ti alleni da esausto (default 30%, lo
# sparring è più rischioso perché è un combattimento vero)
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

DAYS_PER_MONTH = 30  # placeholder, calendario semplificato
MONTHS_PER_YEAR = 12
DAYS_PER_YEAR = DAYS_PER_MONTH * MONTHS_PER_YEAR  # 360

MONTH_NAMES = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]


def parse_weekly_schedule(schedule_str: str) -> list[str]:
    """Da stringa CSV (come salvata nel DB) a lista di 7 focus. Tollerante:
    se la stringa è vuota, sporca, o più corta di 7 giorni, completa con
    Riposo invece di sollevare un errore - i salvataggi vecchi (prima che
    esistesse questa colonna) non devono rompersi."""
    days = schedule_str.split(",") if schedule_str else []
    days = [d.strip() for d in days]
    days = [d if d in TRAINING_FOCUS_OPTIONS else "Riposo" for d in days]
    while len(days) < 7:
        days.append("Riposo")
    return days[:7]


def serialize_weekly_schedule(days: list[str]) -> str:
    """Da lista di 7 focus a stringa CSV per il salvataggio nel DB."""
    return ",".join(days[:7])


def get_calendar_display(game_day: int) -> dict:
    """Converte il contatore grezzo game_day (1, 2, 3, ...) in
    Anno/Mese/Giorno leggibili. Calendario semplificato apposta
    (12 mesi x 30 giorni = 360 giorni/anno): non è un calendario reale,
    è solo il ritmo del gioco."""
    zero_based = game_day - 1
    year = zero_based // DAYS_PER_YEAR + 1
    day_in_year = zero_based % DAYS_PER_YEAR
    month_index = day_in_year // DAYS_PER_MONTH  # 0-11
    day_of_month = day_in_year % DAYS_PER_MONTH + 1  # 1-30
    return {
        "year": year,
        "month_index": month_index,
        "month_name": MONTH_NAMES[month_index],
        "day_of_month": day_of_month,
        "label": f"Anno {year} — {MONTH_NAMES[month_index]}, giorno {day_of_month}",
    }


class RosterManager:

    @staticmethod
    def apply_daily_training(knight: dict, focus: str) -> str:
        """Allenamento quotidiano: consuma stamina, migliora una statistica
        (o riposa), assegna un po' di XP, e fa passare un giorno intero di
        gioco (con eventuale invecchiamento). Muta `knight` in place.

        Se il personaggio è troppo esausto, l'allenamento NON viene più
        bloccato in automatico: si forza comunque, ma rischia un
        infortunio (perde un punto invece di guadagnarlo). Il giorno
        avanza sempre, in ogni caso - anche in caso di infortunio."""
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

        # Qualsiasi azione (anche il riposo, anche un infortunio) fa
        # passare un giorno intero.
        aging_msg = RosterManager.advance_day(knight)
        if aging_msg:
            msg = f"{msg} {aging_msg}"

        return msg

    @staticmethod
    def _apply_training_gain(knight: dict, focus: str) -> str:
        """Applica il guadagno normale di un allenamento riuscito."""
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
        """Applica la penalità in caso di infortunio: perde un punto
        invece di guadagnarlo, niente XP per questa sessione."""
        if focus == "Cosmo":
            loss = min(knight["cosmo_max"], _INJURY_STAT_LOSS)
            knight["cosmo_max"] -= loss
            return (f"⚠️ {knight['raw_name']} si è allenato troppo stanco e si è infortunato! "
                    f"Cosmo massimo -{loss}.")

        column = random.choice(["str", "dex", "con"]) if focus == "Sparring con i Compagni" \
            else _STAT_COLUMN_BY_FOCUS[focus]
        loss = max(0, min(knight[column] - 1, _INJURY_STAT_LOSS))  # non scende mai sotto 1
        knight[column] -= loss
        return (f"⚠️ {knight['raw_name']} si è allenato troppo stanco e si è infortunato! "
                f"{_STAT_LABELS[column]} -{loss}.")

    @staticmethod
    def advance_week(knight: dict, schedule: list[str]) -> list[tuple[str, str, str]]:
        """Applica un programma settimanale intero (7 giorni) in un colpo
        solo, riusando apply_daily_training per ciascun giorno. `schedule`
        è una lista di 7 focus, uno per giorno (Lunedì...Domenica).
        Restituisce una lista di tuple (nome_giorno, focus, messaggio)
        per costruire il log in UI."""
        results = []
        for day_name, focus in zip(WEEKDAY_NAMES, schedule):
            msg = RosterManager.apply_daily_training(knight, focus)
            results.append((day_name, focus, msg))
        return results

    @staticmethod
    def advance_month(knight: dict, schedule: list[str]) -> list[tuple[str, str, str]]:
        """Applica lo stesso programma settimanale ripetuto per un mese
        intero (DAYS_PER_MONTH giorni, di norma 30 = 4 settimane + 2
        giorni). Niente 30 tendine da gestire: si riusa il programma
        settimanale già impostato. Restituisce una lista di tuple
        (etichetta_giorno, focus, messaggio)."""
        results = []
        days_done = 0
        week_num = 1
        while days_done < DAYS_PER_MONTH:
            days_this_round = min(7, DAYS_PER_MONTH - days_done)
            for day_name, focus in zip(WEEKDAY_NAMES[:days_this_round], schedule[:days_this_round]):
                msg = RosterManager.apply_daily_training(knight, focus)
                results.append((f"Sett.{week_num} {day_name}", focus, msg))
            days_done += days_this_round
            week_num += 1
        return results

    @staticmethod
    def advance_day(knight: dict, days: int = 1) -> str:
        """Fa avanzare il calendario del personaggio. Restituisce un
        messaggio SOLO se è appena scattato un nuovo anno (compleanno),
        stringa vuota altrimenti. Muta `knight` in place."""
        previous_year = get_calendar_display(knight["game_day"])["year"]
        knight["game_day"] += days
        new_year = get_calendar_display(knight["game_day"])["year"]

        if new_year > previous_year:
            knight["age"] += (new_year - previous_year)
            return f"🎂 È passato un altro anno! {knight['raw_name']} ora ha {knight['age']} anni."
        return ""

    @staticmethod
    def xp_to_next_level(player_level: int) -> int:
        """PLACEHOLDER: curva di progressione, da tarare con le dinamiche vere."""
        return player_level * 100

    @staticmethod
    def add_xp(knight: dict, amount: int) -> str:
        """Aggiunge XP e gestisce eventuali salite di livello (una alla
        volta, per non saltare livelli in un colpo solo). Muta `knight`
        in place. Restituisce un messaggio SOLO se c'è stato un level up
        (stringa vuota altrimenti)."""
        knight["xp"] += amount

        threshold = RosterManager.xp_to_next_level(knight["player_level"])
        if knight["xp"] < threshold:
            return ""

        knight["xp"] -= threshold
        knight["player_level"] += 1
        # PLACEHOLDER: bonus di livello. Per ora +2 punti totali a scelta
        # futura, qui semplicemente distribuiti su Cosmo massimo.
        knight["cosmo_max"] += 5
        return (f"🎉 {knight['raw_name']} è salito al livello {knight['player_level']}! "
                f"(Cosmo massimo +5)")
