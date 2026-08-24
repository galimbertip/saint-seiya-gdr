"""
Modelli dati del gioco.
Nessuna logica qui dentro: solo strutture. La logica sta in data_loader,
dnd_engine, fm_manager.
"""
from dataclasses import dataclass, field


@dataclass
class Technique:
    name: str
    tech_type: str          # es. "Fisico/Armi", "Cosmico/Spirito"...
    launch_desc: str        # descrizione del lancio
    effect_desc: str        # descrizione dell'effetto
    power: int              # 0-100, scala Foglio16

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.tech_type,
            "launch_desc": self.launch_desc,
            "effect_desc": self.effect_desc,
            "power": self.power,
        }


@dataclass
class Armor:
    divinity: str            # es. "Athena", "Odino", "Nettuno"...
    faction: str              # es. "Gold Saint", "Generale Abissale (Sea General)"
    name: str                  # es. "Scale di Chrysaor"
    level: int                  # 0-100, forza complessiva dell'armatura (Foglio17)
    min_player_level: int        # livello minimo del giocatore per poterla scegliere
    techniques: list[Technique] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "divinity": self.divinity,
            "faction": self.faction,
            "name": self.name,
            "level": self.level,
            "min_player_level": self.min_player_level,
            "techniques": [t.to_dict() for t in self.techniques],
        }


@dataclass
class Knight:
    id: int | None
    formal_name: str
    raw_name: str
    armor_name: str
    faction: str
    divinity: str
    cosmo_cur: int
    cosmo_max: int
    str_: int
    dex: int
    con: int
    tec: int
    vol: int
    # Campi FM-style, assenti nello schema vecchio: li aggiungiamo qui,
    # il DB verrà esteso di conseguenza in db_manager.py
    player_level: int = 1
    xp: int = 0
    stamina: int = 100
    age: int = 15
