"""
Rimuove le ultime 3 righe orfane rimaste in data/techniques.csv dopo
cleanup_orphan_techniques.py - non sono state trovate da quello script
probabilmente per un disallineamento di caratteri invisibili (spazi
non standard, apostrofi in codifica diversa) tra il nome scritto a
mano lì e quello vero nel file. Qui il confronto è per CONTENUTO
(sottostringa), non per uguaglianza esatta di stringa - molto più
tollerante a differenze di questo tipo.

Uso:
    python3 data/cleanup_orphan_techniques_2.py                # anteprima
    python3 data/cleanup_orphan_techniques_2.py --applica       # applica sul serio (con backup)
"""
import csv
import sys
from pathlib import Path

APPLICA = "--applica" in sys.argv
DATA_DIR = Path(__file__).resolve().parent if Path(__file__).resolve().parent.name == "data" else Path("data")
TECHNIQUES_PATH = DATA_DIR / "techniques.csv"

# Confronto per sottostringa (non uguaglianza esatta) - basta che il
# nome nella riga CONTENGA una di queste parole chiave distintive.
PAROLE_CHIAVE_DA_RIMUOVERE = ["Carina", "Coma Berenices", "Lynx"]


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
    backup_path = path.with_suffix(path.suffix + ".bak4")
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Backup salvato in {backup_path}")


def main() -> None:
    if not TECHNIQUES_PATH.exists():
        print("ERRORE: techniques.csv non trovato.")
        return

    header, rows = leggi_csv(TECHNIQUES_PATH)
    idx_armatura = header.index("Armatura")

    print(f"Righe lette: {len(rows)}")

    righe_finali = []
    rimosse = []
    for row in rows:
        nome = row[idx_armatura]
        if any(parola in nome for parola in PAROLE_CHIAVE_DA_RIMUOVERE):
            rimosse.append(nome)
        else:
            righe_finali.append(row)

    print(f"\nRighe trovate e rimosse (confronto per sottostringa): {len(rimosse)}")
    for nome in rimosse:
        print(f"  - {repr(nome)}")  # repr mostra anche eventuali caratteri invisibili/strani

    if not APPLICA:
        print(f"\n--- ANTEPRIMA SOLTANTO: nessun file è stato toccato. ---")
        print(f"Righe che risulterebbero alla fine: {len(righe_finali)}")
        print("Se ti convince, esegui di nuovo con: python3 data/cleanup_orphan_techniques_2.py --applica")
        return

    backup(TECHNIQUES_PATH)
    scrivi_csv(TECHNIQUES_PATH, header, righe_finali)
    print(f"\nFatto. Righe finali (escluso intestazione): {len(righe_finali)}")


if __name__ == "__main__":
    main()
