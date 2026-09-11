"""
Rimuove le 3 righe duplicate "Athena, Corona Saint" (Carina/Berenice/
Lynx) da data/techniques_extra.csv - stesso duplicato già corretto in
armors.csv tempo fa (tenuta solo la versione "Apollo, Corona Saint
(Cavaliere della Corona)", quella davvero canonica).

Uso:
    python3 data/fix_extra_duplicates.py                # anteprima
    python3 data/fix_extra_duplicates.py --applica       # applica sul serio (con backup)
"""
import csv
import sys
from pathlib import Path

APPLICA = "--applica" in sys.argv
DATA_DIR = Path(__file__).resolve().parent if Path(__file__).resolve().parent.name == "data" else Path("data")
PATH = DATA_DIR / "techniques_extra.csv"

RIGHE_DA_RIMUOVERE = [
    ("Athena", "Corona Saint", "Carina"),        # sottostringa nel nome armatura
    ("Athena", "Corona Saint", "Coma Berenices"),
    ("Athena", "Corona Saint", "Lynx"),
]


def leggi_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    fixed_lines = []
    for line in raw_lines:
        line = line.strip()
        if len(line) >= 2 and line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        fixed_lines.append(line)
    rows = list(csv.reader(fixed_lines))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def scrivi_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def backup(path: Path) -> None:
    backup_path = path.with_suffix(path.suffix + ".bak")
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Backup salvato in {backup_path}")


def main() -> None:
    if not PATH.exists():
        print(f"ERRORE: {PATH} non trovato.")
        return

    header, rows = leggi_csv(PATH)
    idx_divinita = header.index("Divinità")
    idx_fazione = header.index("Fazione")
    idx_armatura = header.index("Armatura")

    print(f"Righe lette: {len(rows)}")

    righe_finali = []
    rimosse = []
    for row in rows:
        match = False
        for divinita, fazione, sottostringa in RIGHE_DA_RIMUOVERE:
            if row[idx_divinita] == divinita and row[idx_fazione] == fazione and sottostringa in row[idx_armatura]:
                match = True
                break
        if match:
            rimosse.append(row[idx_armatura])
        else:
            righe_finali.append(row)

    print(f"\nRighe trovate e rimosse: {len(rimosse)}")
    for nome in rimosse:
        print(f"  - {nome}")

    if not APPLICA:
        print(f"\n--- ANTEPRIMA SOLTANTO: nessun file è stato toccato. ---")
        print(f"Righe che risulterebbero alla fine: {len(righe_finali)}")
        print("Se ti convince, esegui di nuovo con: python3 data/fix_extra_duplicates.py --applica")
        return

    backup(PATH)
    scrivi_csv(PATH, header, righe_finali)
    print(f"\nFatto. Righe finali (escluso intestazione): {len(righe_finali)}")


if __name__ == "__main__":
    main()
