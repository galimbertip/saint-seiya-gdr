"""
Diagnostica: quali armature del catalogo (data/armors.csv) non hanno
NESSUNA tecnica corrispondente in data/techniques.csv né in
data/techniques_extra.csv (se esiste). Stessa identica logica di
lettura di core/data_loader.py (compreso il fix delle virgolette
esterne spurie), così il risultato coincide esattamente con quello
che il gioco vede davvero.

Non tocca nessun file - solo lettura e stampa a schermo. Usalo prima
di qualunque correzione, per sapere esattamente cosa manca.

Uso:
    python3 data/diagnose_missing_techniques.py
"""
import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent if Path(__file__).resolve().parent.name == "data" else Path("data")


def leggi_csv_con_fix_virgolette(path: Path) -> list[dict]:
    """Stessa logica di core/data_loader.py: toglie la coppia di
    virgolette esterne per riga (bug noto dell'export), poi parsa
    normalmente. Se il file non ha quel problema (righe già pulite),
    il fix non cambia nulla - togliere virgolette che non ci sono non
    fa danno."""
    if not path.exists():
        return []
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    fixed_lines = []
    for line in raw_lines:
        line = line.strip()
        if len(line) >= 2 and line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        fixed_lines.append(line)
    return list(csv.DictReader(fixed_lines))


def main() -> None:
    armors_path = DATA_DIR / "armors.csv"
    armors_extra_path = DATA_DIR / "armors_extra.csv"
    techniques_path = DATA_DIR / "techniques.csv"
    techniques_extra_path = DATA_DIR / "techniques_extra.csv"

    armor_rows = leggi_csv_con_fix_virgolette(armors_path)
    armor_extra_rows = leggi_csv_con_fix_virgolette(armors_extra_path)
    technique_rows = leggi_csv_con_fix_virgolette(techniques_path)
    technique_extra_rows = leggi_csv_con_fix_virgolette(techniques_extra_path)

    print(f"Armature lette da armors.csv: {len(armor_rows)}")
    print(f"Armature lette da armors_extra.csv: {len(armor_extra_rows)}")
    print(f"Righe tecniche lette da techniques.csv: {len(technique_rows)}")
    print(f"Righe tecniche lette da techniques_extra.csv: {len(technique_extra_rows)}")

    tutti_i_nomi_armatura = {r["Armatura"].strip() for r in armor_rows if r.get("Armatura")}
    tutti_i_nomi_armatura |= {r["Armatura"].strip() for r in armor_extra_rows if r.get("Armatura")}

    nomi_con_tecniche = {r["Armatura"].strip() for r in technique_rows if r.get("Armatura")}
    nomi_con_tecniche |= {r["Armatura"].strip() for r in technique_extra_rows if r.get("Armatura")}
    # armors_extra.csv, se esiste, porta le proprie tecniche nella
    # stessa riga (fino a 2) - le sue armature contano già come "con
    # tecniche" a prescindere dagli altri due file.
    if armor_extra_rows:
        nomi_con_tecniche |= {r["Armatura"].strip() for r in armor_extra_rows if r.get("tecnica1", "").strip()}

    senza_tecniche = sorted(tutti_i_nomi_armatura - nomi_con_tecniche)
    orfane = sorted(nomi_con_tecniche - tutti_i_nomi_armatura)

    print()
    print(f"=== Armature SENZA nessuna tecnica corrispondente: {len(senza_tecniche)} ===")
    for nome in senza_tecniche:
        print(f"  - {nome}")

    print()
    print(f"=== Nomi con tecniche ma SENZA armatura corrispondente (orfane): {len(orfane)} ===")
    for nome in orfane:
        print(f"  - {nome}")

    if not senza_tecniche and not orfane:
        print()
        print("OK: tutto allineato, ogni armatura ha almeno una tecnica e viceversa.")


if __name__ == "__main__":
    main()
