"""
Motore dei tiri di dado, in stile D&D.

Rispetto alla versione originale di Gemini:
- calculate_ac non usa più una mappa hardcoded per rango armatura
  (Bronzo/Argento/Oro/...), che copriva solo una manciata di casi e
  andava riscritta a mano ogni volta che si aggiungeva una casta.
  Usa invece direttamente il campo `level` (0-100) del catalogo
  armature reale, scalato in un bonus continuo.
- use_technique/resolve_technique_damage sono marcati chiaramente
  come PLACEHOLDER: la formula "Potenza tecnica × Dado" (l'idea
  discussa in chat) non è ancora stata fissata nel dettaglio -
  la lasciamo per la fase "dinamiche di gioco", di proposito
  separata dalla struttura. Qui c'è una versione minima e
  funzionante, sostituibile senza toccare il resto del motore.
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
    def resolve_attack(attacker_str: int, defender_ac: int) -> tuple[bool, int, int]:
        """Tiro per colpire: d20 + Mod Forza vs CA difensore.
        Restituisce (colpito, tiro_dado, totale)."""
        str_mod = DnDEngine.get_modifier(attacker_str)
        rolls, total = DnDEngine.roll_dice(20, 1, str_mod)
        hit = total >= defender_ac
        return hit, rolls[0], total

    @staticmethod
    def resolve_technique_damage(technique_power: int, armor_level: int) -> tuple[int, int]:
        """
        PLACEHOLDER - formula provvisoria in attesa della discussione
        sulle dinamiche di combattimento (Potenza tecnica x Dado).

        Versione attuale (minima, per far girare il motore):
        danno = (potenza_tecnica / 10) arrotondato, moltiplicato per un
        fattore 0.5-1.0 dato dal tiro di dado (invece di potenza intera
        x dado, per evitare i numeri fuori scala di cui abbiamo parlato
        in chat - es. potenza 95 x d20 = fino a 1900).

        Restituisce (tiro_dado_grezzo, danno_finale).
        """
        faces = DnDEngine.dice_faces_for_armor_level(armor_level)
        rolls, _ = DnDEngine.roll_dice(faces, 1)
        dice_roll = rolls[0]
        dice_factor = 0.5 + (dice_roll / faces) * 0.5  # range 0.5 - 1.0
        damage = round((technique_power / 10) * dice_factor)
        return dice_roll, max(1, damage)

    @staticmethod
    def use_technique(attacker: dict, defender_ac: int, technique_cost: int,
                       technique_power: int, armor_level: int) -> tuple[bool, str, int]:
        """
        Esegue l'attacco speciale consumando Cosmo:
        - controlla il Cosmo disponibile
        - tira per colpire (d20 + Mod Forza vs CA difensore)
        - se colpisce, calcola il danno con resolve_technique_damage
          (placeholder, vedi sopra)
        """
        if attacker["cosmo_cur"] < technique_cost:
            return False, "Cosmo insufficiente per eseguire la tecnica!", 0

        attacker["cosmo_cur"] -= technique_cost

        hit, dice_roll, attack_total = DnDEngine.resolve_attack(attacker["str"], defender_ac)

        if hit:
            _, damage = DnDEngine.resolve_technique_damage(technique_power, armor_level)
            return True, f"**COLPITO!** ({attack_total} vs CA {defender_ac}). Danni inflitti: {damage}", damage
        else:
            return False, f"**MANCATO!** ({attack_total} vs CA {defender_ac})", 0
