"""Simulatore di bilanciamento per il combattimento (richiesto in chat:
"bilanciare i numeri placeholder" - invece di indovinare nuovi numeri
a occhio, si fa combattere il motore vero migliaia di volte e si
guardano i risultati reali). Stesso principio già usato in diversi
progetti open source di bilanciamento RPG a turni (verificato in
chat cercando esempi reali, non solo ipotizzato) - nessuna libreria
speciale serve per questo: Python puro (`random`, un ciclo, un
conteggio) è lo standard per una simulazione di questa scala.

IMPORTANTE - stato di questo file: la funzione `_resolve_one_round`
qui sotto è un'APPROSSIMAZIONE ragionevole del combattimento vero
(basata su quanto discusso finora: tiro d20+statistica, potenza della
tecnica, le tre barre), NON ancora collegata al motore reale
(core/arena_session.py, core/dnd_engine.py) perché non erano
disponibili in questa sessione. Il framework attorno - eseguire N
combattimenti, aggregare percentuali di vittoria e durata media - è
già completo e testato; la parte che va sostituita per avere numeri
DAVVERO affidabili è quella di risoluzione del singolo round, con una
chiamata alla logica vera del gioco (vedi il commento
"DA SOSTITUIRE" più sotto)."""

import random
import statistics


def roll_d20() -> int:
    return random.randint(1, 20)


def _resolve_one_round(attacker: dict, defender: dict, technique_power: int) -> int:
    """PLACEHOLDER - DA SOSTITUIRE con una chiamata alla vera
    risoluzione del round (core.dnd_engine o equivalente), una volta
    disponibile. Qui: un tiro d20 + Tecnica dell'attaccante contro una
    Classe Armatura derivata dalla Destrezza del difensore (stessa
    impalcatura concettuale discussa nel progetto finora) - se il
    colpo arriva, il danno è la potenza della tecnica meno una
    riduzione basata sulla Costituzione del difensore. Restituisce il
    danno inflitto (0 se il colpo manca)."""
    attack_roll = roll_d20() + attacker["tec"] // 3
    defense_class = 10 + defender["dex"] // 3
    if attack_roll < defense_class:
        return 0
    mitigation = defender["con"] // 5
    return max(1, technique_power - mitigation)


def simulate_fight(fighter_a: dict, fighter_b: dict, max_rounds: int = 100) -> dict:
    """Un singolo combattimento simulato fino alla fine (o al limite di
    round, per evitare loop infiniti se nessuno riesce a ferire
    l'altro) - fighter_a e fighter_b sono dict con almeno
    {str, dex, con, tec, vol, vita_max, tecniche: [{"power": N}, ...]}.
    Restituisce chi ha vinto e quanti round è durato."""
    vita_a, vita_b = fighter_a["vita_max"], fighter_b["vita_max"]
    for round_num in range(1, max_rounds + 1):
        tecnica_a = random.choice(fighter_a["tecniche"])
        danno_a = _resolve_one_round(fighter_a, fighter_b, tecnica_a["power"])
        vita_b -= danno_a
        if vita_b <= 0:
            return {"winner": "a", "rounds": round_num}

        tecnica_b = random.choice(fighter_b["tecniche"])
        danno_b = _resolve_one_round(fighter_b, fighter_a, tecnica_b["power"])
        vita_a -= danno_b
        if vita_a <= 0:
            return {"winner": "b", "rounds": round_num}

    return {"winner": "draw", "rounds": max_rounds}  # nessuno dei due ha vinto entro il limite - segnale che i combattimenti durano troppo


def run_balance_simulation(fighter_a: dict, fighter_b: dict, n_simulations: int = 2000) -> dict:
    """Il cuore della simulazione Monte Carlo (richiesto in chat) -
    ripete simulate_fight molte volte (2000 di default: abbastanza per
    stime stabili senza essere lento) e aggrega i risultati in
    statistiche leggibili: chi vince quanto spesso, quanto durano gli
    scontri in media, quanto VARIANO le durate (una deviazione
    standard alta vuol dire scontri molto imprevedibili, a volte
    lampo, a volte interminabili - un segnale di squilibrio a sé, non
    solo la media)."""
    win_counts = {"a": 0, "b": 0, "draw": 0}
    round_counts = []
    for _ in range(n_simulations):
        result = simulate_fight(fighter_a, fighter_b)
        win_counts[result["winner"]] += 1
        round_counts.append(result["rounds"])

    return {
        "n_simulations": n_simulations,
        "win_rate_a": win_counts["a"] / n_simulations,
        "win_rate_b": win_counts["b"] / n_simulations,
        "draw_rate": win_counts["draw"] / n_simulations,
        "avg_rounds": statistics.mean(round_counts),
        "stdev_rounds": statistics.stdev(round_counts) if n_simulations > 1 else 0,
        "min_rounds": min(round_counts),
        "max_rounds": max(round_counts),
    }


def make_test_fighter(level: int, technique_powers: list[int]) -> dict:
    """Un combattente di prova per la simulazione, con le statistiche
    derivate dal livello con la STESSA formula già usata nel gioco
    vero (10 + livello//10, vedi core.training_path.
    build_opponent_from_armor) - così i risultati della simulazione
    riflettono davvero come il gioco genera i suoi avversari, non una
    formula inventata apposta per il test."""
    base_stat = 10 + level // 10
    vita_max = 100 + base_stat * 2
    return {
        "str": base_stat, "dex": base_stat, "con": base_stat, "tec": base_stat, "vol": base_stat,
        "vita_max": vita_max,
        "tecniche": [{"power": p} for p in technique_powers],
    }
