"""
Unica fonte di verità per armature e tecniche.

Sostituisce armors_db.json (statico, incompleto) e la fetch live da
Google Sheet + lo scraper Wikipedia (che di fatto non verificava mai
nulla: restituiva sempre verified=True). Qui carichiamo direttamente
i CSV esportati a mano, offline, senza dipendenze di rete.

File sorgente (in data/):
  armors.csv            Foglio17 - catalogo armature: Divinità, Fazione,
                         Armatura, Livello (0-100), min_level
  techniques.csv         Foglio16 - fino a 3 tecniche per armatura
  techniques_extra.csv    Foglio18 - tecniche per le 64 armature che nel
                         Foglio16 ne erano prive (stesso nome Armatura
                         di armors.csv)
  armors_extra.csv         Foglio19 - le 6 armature che nel Foglio16
                         avevano tecniche ma nomi non combacianti col
                         Foglio17; qui hanno nome corretto + Livello/
                         min_level + proprie tecniche (fino a 2)

NOTA sul bug del Foglio16: il file esportato ha ogni riga avvolta da
virgolette esterne spurie (probabile bug dell'export Google Sheets),
per cui un csv.reader "ingenuo" legge l'intero file come una sola
colonna. Qui lo ripariamo togliendo la coppia di virgolette esterne
riga per riga, prima di ri-parsare normalmente. techniques_extra.csv e
armors_extra.csv sono CSV standard e non hanno questo problema.
"""
import csv
from pathlib import Path

from core.models import Armor, Technique

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ARMORS_CSV = DATA_DIR / "armors.csv"
TECHNIQUES_CSV = DATA_DIR / "techniques.csv"
TECHNIQUES_EXTRA_CSV = DATA_DIR / "techniques_extra.csv"
ARMORS_EXTRA_CSV = DATA_DIR / "armors_extra.csv"


def _safe_int(value, default=0):
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def _read_plain_csv(path: Path) -> list[dict]:
    """Lettura CSV standard, senza fix particolari."""
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_quoted_csv(path: Path) -> list[dict]:
    """Applica il fix delle virgolette esterne spurie (bug export Foglio16), poi parsa."""
    with open(path, encoding="utf-8") as f:
        raw_lines = f.read().splitlines()

    fixed_lines = []
    for line in raw_lines:
        line = line.strip()
        if len(line) >= 2 and line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        fixed_lines.append(line)

    return list(csv.DictReader(fixed_lines))


def _extract_techniques(row: dict) -> list[Technique]:
    """Da una riga estrae le tecniche presenti (fino a 3, alcune fonti ne
    hanno solo 1 o 2), ignorando gli slot vuoti."""
    techniques = []
    for i in (1, 2, 3):
        name = (row.get(f"tecnica{i}") or "").strip()
        if not name:
            continue
        techniques.append(
            Technique(
                name=name,
                tech_type=(row.get(f"tipo{i}") or "Generica").strip(),
                launch_desc=(row.get(f"descrizionetecnica{i}") or "").strip(),
                effect_desc=(row.get(f"effettotecnica{i}") or "").strip(),
                power=_safe_int(row.get(f"potenzatecnica{i}"), default=5),
            )
        )
    return techniques


def load_armors_database(
    armors_path: Path = ARMORS_CSV,
    techniques_path: Path = TECHNIQUES_CSV,
    techniques_extra_path: Path = TECHNIQUES_EXTRA_CSV,
    armors_extra_path: Path = ARMORS_EXTRA_CSV,
) -> dict[str, Armor]:
    """Restituisce un dizionario {nome_armatura: Armor}, unendo le 4 fonti.
    Segnala su stdout eventuali disallineamenti residui, invece di
    fallire silenziosamente."""

    armor_rows = _read_plain_csv(armors_path)
    technique_rows = _read_quoted_csv(techniques_path)
    technique_extra_rows = _read_plain_csv(techniques_extra_path) if techniques_extra_path.exists() else []
    armor_extra_rows = _read_plain_csv(armors_extra_path) if armors_extra_path.exists() else []

    # Indicizza le tecniche base per nome armatura
    techniques_by_armor: dict[str, list[Technique]] = {}
    for row in technique_rows:
        armor_name = (row.get("Armatura") or "").strip()
        if not armor_name:
            continue
        techniques_by_armor[armor_name] = _extract_techniques(row)

    # Applica le tecniche "extra" (Foglio18): riempiono le armature che
    # nella fonte base ne erano prive
    for row in technique_extra_rows:
        armor_name = (row.get("Armatura") or "").strip()
        if not armor_name:
            continue
        techniques_by_armor[armor_name] = _extract_techniques(row)

    # Catalogo armature base (Foglio17)
    armors: dict[str, Armor] = {}
    for row in armor_rows:
        name = (row.get("Armatura") or "").strip()
        if not name:
            continue
        armors[name] = Armor(
            divinity=(row.get("Divinità") or "").strip(),
            faction=(row.get("Fazione") or "").strip(),
            name=name,
            level=_safe_int(row.get("Livello"), default=1),
            min_player_level=_safe_int(row.get("min_level"), default=1),
            techniques=techniques_by_armor.get(name, []),
        )

    # Armature "extra" (Foglio19): le 6 che prima erano orfane, ora con
    # nome corretto, Livello/min_level propri e proprie tecniche
    for row in armor_extra_rows:
        name = (row.get("Armatura") or "").strip()
        if not name:
            continue
        armors[name] = Armor(
            divinity=(row.get("Divinità") or "").strip(),
            faction=(row.get("Fazione") or "").strip(),
            name=name,
            level=_safe_int(row.get("Livello"), default=1),
            min_player_level=_safe_int(row.get("min_level"), default=1),
            techniques=_extract_techniques(row),
        )

    # Diagnostica residua
    missing_techniques = [n for n, a in armors.items() if not a.techniques]
    all_technique_sources = set(techniques_by_armor) | {
        (r.get("Armatura") or "").strip() for r in armor_extra_rows
    }
    orphan_techniques = all_technique_sources - set(armors)

    if orphan_techniques:
        print(f"[data_loader] ATTENZIONE: {len(orphan_techniques)} nomi con tecniche non "
              f"ancora presenti nel catalogo armature: {sorted(orphan_techniques)}")
    if missing_techniques:
        print(f"[data_loader] ATTENZIONE: {len(missing_techniques)} armature ancora senza "
              f"nessuna tecnica: {missing_techniques}")
    if not orphan_techniques and not missing_techniques:
        print(f"[data_loader] OK: {len(armors)} armature, tutte con almeno una tecnica, "
              f"nessun disallineamento residuo.")

    return armors


if __name__ == "__main__":
    db = load_armors_database()
    print(f"\nCaricate {len(db)} armature totali.\n")

    for sample_name in ("Scale di Chrysaor", "Armatura Divina (Kamui) di Zeus", "Lince"):
        armor = db.get(sample_name)
        if not armor:
            print(f"--- {sample_name}: NON TROVATA ---\n")
            continue
        print(f"--- {armor.name} ({armor.divinity} / {armor.faction}) "
              f"Livello {armor.level}, min_level {armor.min_player_level} ---")
        for t in armor.techniques:
            print(f"   • {t.name} [{t.tech_type}] potenza {t.power}")
        print()
