"""
Motore dei tiri di dado, in stile D&D.

Rispetto alla versione originale di Gemini:
- calculate_ac non usa più una mappa hardcoded per rango armatura
  (Bronzo/Argento/Oro/...), che copriva solo una manciata di casi e
  andava riscritta a mano ogni volta che si aggiungeva una casta.
  Usa invece direttamente il campo `level` (0-100) del catalogo
  armature reale, scalato in un bonus continuo.
- resolve_attack e resolve_technique_damage sono state ricalibrate in
  chat dopo aver diagnosticato uno squilibrio strutturale (la CA
  cresceva con due ingredienti, il tiro per colpire con uno solo) e
  un danno troppo piccolo rispetto ai pool di Cosmo - vedi i commenti
  sulle due funzioni per i dettagli.
- L'orchestrazione vera del combattimento vive in core/arena_manager.py
  (resolve_turn), non più qui: use_technique() (metodo minimo di primo
  abbozzo) è stata rimossa perché ormai codice morto.
"""
import random


class DnDEngine:

    @staticmethod
    def get_modifier(score: int) -> int:
        """Modificatore di caratteristica, stile D&D 5e."""
        return (score - 10) // 2

    @staticmethod
    def roll_dice(faces: int, count: int = 1, modifier: int = 0) -> tuple[list[int], int]:
        """Lancia `count` dadi da `faces` facce, restituisce (tiri singoli, totale+modificatore)."""
        rolls = [random.randint(1, faces) for _ in range(count)]
        return rolls, sum(rolls) + modifier

    @staticmethod
    def calculate_ac(dex_mod: int, armor_level: int, cosmo_level: int) -> int:
        """
        Classe Armatura (CA):
        - Base: 10 + Mod. Destrezza
        - Bonus armatura: level (0-100) del catalogo / 10 -> range 0-10
          (un'armatura di livello 80 dà +8, una di livello 20 dà +2:
          scala continua, niente più categorie fisse)
        - Bonus Cosmo: +1 ogni 5 livelli di sintonia Cosmo
        """
        armor_bonus = armor_level // 10
        cosmo_bonus = cosmo_level // 5
        return 10 + dex_mod + armor_bonus + cosmo_bonus

    @staticmethod
    def dice_faces_for_armor_level(armor_level: int) -> int:
        """
        Determina il dado usato per lanciare le tecniche in base al
        livello dell'armatura (l'idea di 'un Bronze tira un dado più
        debole di un Gold'). Soglie PLACEHOLDER - da confermare quando
        affrontiamo le dinamiche di combattimento vere e proprie.
        """
        if armor_level < 20:
            return 6
        elif armor_level < 40:
            return 8
        elif armor_level < 60:
            return 12
        elif armor_level < 80:
            return 20
        else:
            return 20  # armature altissime: dado d20, eventuale bonus a parte

    @staticmethod
    def resolve_attack(attacker_str: int, attacker_armor_level: int, defender_ac: int,
                        mode: str = "normale") -> tuple[bool, int, int]:
        """Tiro per colpire: d20 + Mod Forza + bonus armatura vs CA difensore.

        Il bonus armatura sul tiro per colpire (armor_level // 10, la
        STESSA scala del bonus armatura sulla CA) è la correzione
        chiave decisa in chat dopo aver diagnosticato perché era così
        difficile colpire: la CA cresceva con DUE ingredienti (Destrezza
        E livello armatura del difensore), mentre il tiro per colpire
        cresceva con UNO solo (Forza dell'attaccante) - nessuna
        simmetria tra attacco e difesa. Ora entrambi i lati scalano
        allo stesso modo col livello armatura, e la differenza vera la
        fa solo il divario di livello reale tra i due combattenti (che
        è giusto che conti), non uno squilibrio strutturale nella formula.

        mode: 'normale' (un dado), 'vantaggio' (due dadi, tieni il
        migliore) o 'svantaggio' (due dadi, tieni il peggiore) - regola
        classica D&D, richiesta in chat per dare più profondità tattica
        (un imprevisto, una posizione scomoda, ecc. possono concedere
        l'uno o l'altro).

        1 naturale sul dado TENUTO = fallimento SEMPRE, a prescindere dal
        totale (sfiga colossale). 20 naturale = successo SEMPRE (successo
        della madonna) - regola classica D&D, richiesta in chat.
        Restituisce (colpito, tiro_dado_grezzo_tenuto, totale)."""
        str_mod = DnDEngine.get_modifier(attacker_str)
        armor_bonus = attacker_armor_level // 10

        if mode == "vantaggio":
            rolls, _ = DnDEngine.roll_dice(20, 2)
            natural = max(rolls)
        elif mode == "svantaggio":
            rolls, _ = DnDEngine.roll_dice(20, 2)
            natural = min(rolls)
        else:
            rolls, _ = DnDEngine.roll_dice(20, 1)
            natural = rolls[0]

        total = natural + str_mod + armor_bonus
        if natural == 1:
            hit = False
        elif natural == 20:
            hit = True
        else:
            hit = total >= defender_ac
        return hit, natural, total

    @staticmethod
    def resolve_technique_damage(technique_power: int, armor_level: int,
                                  attacker_tec_mod: int = 0, defender_con_mod: int = 0) -> tuple[int, int]:
        """
        Formula del danno, ricalibrata in chat dopo aver verificato che
        quella precedente (potenza/10 x fattore dado) dava colpi da 6-7
        danni contro pool di Cosmo da 100-250 - servivano 15-30 colpi
        per chiudere uno scontro, troppi. Con potenza/6 un colpo medio
        (potenza ~80) fa sui 10 danni, uno forte (potenza ~95) sui 12,
        un Attacco Base (potenza 20) resta debole com'è giusto che sia
        (~2-3 danni) - un combattimento tipico ora dovrebbe chiudersi
        in una decina abbondante di colpi andati a segno, non trenta.

        attacker_tec_mod: la Tecnica di chi attacca si aggiunge al
        danno grezzo - chi è più abile nell'eseguire le proprie
        tecniche le rende più incisive (richiesto in chat: Tecnica non
        faceva letteralmente nulla in combattimento).
        defender_con_mod: la Costituzione di chi difende si sottrae al
        danno subito (una corazza naturale) - non tocca la probabilità
        di essere colpiti (quella resta Destrezza), solo quanto fa
        male il colpo quando arriva.

        Restituisce (tiro_dado_grezzo, danno_finale)."""
        faces = DnDEngine.dice_faces_for_armor_level(armor_level)
        rolls, _ = DnDEngine.roll_dice(faces, 1)
        dice_roll = rolls[0]
        dice_factor = 0.5 + (dice_roll / faces) * 0.5  # range 0.5 - 1.0
        raw_damage = round((technique_power / 6) * dice_factor) + attacker_tec_mod
        damage = max(1, raw_damage - defender_con_mod)
        return dice_roll, damage

    @staticmethod
    def resolve_saving_throw(stat_score: int, dc: int) -> bool:
        """Tiro salvezza generico: d20 + modificatore della caratteristica
        vs una soglia fissa (DC). Successo = True. Pensato riusabile per
        qualunque futura resistenza, non solo Volontà contro gli stati
        (richiesto in chat: dare un ruolo vero alla Volontà)."""
        mod = DnDEngine.get_modifier(stat_score)
        _, total = DnDEngine.roll_dice(20, 1, mod)
        return total >= dc
