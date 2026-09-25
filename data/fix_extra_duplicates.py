"""
Applica a data/techniques_extra.csv tutte le correzioni di tecnica
trovate durante la verifica del canone (sessioni precedenti) ma non
ancora arrivate al vero file - più la rimozione dei 3 duplicati
"Athena, Corona Saint" già noti (stessa cosa che fix_extra_duplicates.py
farebbe, incorporata qui per fare tutto in un solo passaggio).

Uso:
    python3 data/fix_extra_techniques.py                # anteprima
    python3 data/fix_extra_techniques.py --applica       # applica sul serio (con backup)
"""
import csv
import sys
from pathlib import Path

APPLICA = "--applica" in sys.argv
DATA_DIR = Path(__file__).resolve().parent if Path(__file__).resolve().parent.name == "data" else Path("data")
PATH = DATA_DIR / "techniques_extra.csv"

# Righe da rimuovere per intero (duplicati senza fonte canonica -
# tenuta solo la versione "Apollo, Corona Saint").
RIGHE_DA_RIMUOVERE = [
    ("Athena", "Corona Saint", "Carina"),
    ("Athena", "Corona Saint", "Coma Berenices"),
    ("Athena", "Corona Saint", "Lynx"),
]

# Correzioni puntuali: (Divinità, Armatura, colonna, valore_nuovo).
# La colonna può essere "tecnica1"/"tecnica2"/"tecnica3" (il nome) o
# "tipo1"/"tipo2"/"tipo3" (l'elemento).
CORREZIONI = [
    ("Ares", "Galaxy di Marte (Mars)", "tecnica1", "Rubellu Sidus Gungnir"),
    ("Ares", "Galaxy di Marte (Mars)", "tecnica3", "Muro di Marte (Murus Ignis)"),
    ("Hades", "Surplice di Hypnos", "tecnica2", "Incubo Oscuro (Encounter Another Field)"),
    ("Apollo", "Corona Cloth di Carina", "tecnica1", "Corona Ardente (Burning Corona)"),
    ("Apollo", "Corona Cloth della Chioma", "tecnica1", "Capelli d'Oro della Morte (Golden Hair of Death)"),
    ("Apollo", "Corona Cloth della Lince", "tecnica1", "Artiglio Infernale Splendente (Shining Hell Claw)"),
    ("Apollo", "Corona Cloth della Lince", "tipo1", "Fuoco/Fisico"),
    ("Ares", "Galaxy di Romulus (Capo dei Re)", "tecnica1", "Cremito Rupis"),
    ("Ares", "Galaxy di Bacchus", "tipo1", "Acqua"),
    ("Ares", "Galaxy di Vulcanus", "tecnica1", "Valse des Flammes (Waltz of Flames)"),
    ("Ares", "Galaxy di Diana", "tipo1", "Fisico/Fulmine"),
    ("Athena", "Cancro", "tecnica2", "Separazione dell'Anima (Soul Breaker)"),
    ("Athena", "Cancro", "tipo2", "Spirito/Morte"),
    ("Athena", "Pavone", "tecnica1", "Peacock Blizzard"),
    ("Athena", "Pavone", "tipo1", "Acqua/Ghiaccio"),
    ("Athena", "Loto", "tecnica1", "Colpo del Loto (Renge Bakusai Ken)"),
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

    # 1) Rimozione duplicati.
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

    print(f"\nRighe duplicate rimosse: {len(rimosse)}")
    for nome in rimosse:
        print(f"  - {nome}")

    # 2) Correzioni puntuali - "Armatura" qui è confrontata per
    # sottostringa (non uguaglianza esatta) per tollerare le forme
    # complete tipo "Corona Cloth di Carina" vs solo "Carina", e per
    # sicurezza contro eventuali caratteri invisibili come già visto
    # in una correzione precedente.
    correzioni_applicate = []
    for row in righe_finali:
        for divinita, armatura_sub, colonna, nuovo_valore in CORREZIONI:
            if row[idx_divinita] == divinita and armatura_sub in row[idx_armatura]:
                idx_colonna = header.index(colonna)
                vecchio = row[idx_colonna]
                if vecchio != nuovo_valore:
                    correzioni_applicate.append((row[idx_armatura], colonna, vecchio, nuovo_valore))
                    row[idx_colonna] = nuovo_valore

    print(f"\nCorrezioni di tecnica/tipo trovate: {len(correzioni_applicate)}")
    for armatura, colonna, vecchio, nuovo in correzioni_applicate:
        print(f"  - {armatura} / {colonna}: '{vecchio}' -> '{nuovo}'")

    numero_correzioni_attese = len(CORREZIONI)
    if len(correzioni_applicate) != numero_correzioni_attese:
        print(f"\nATTENZIONE: attese {numero_correzioni_attese} correzioni, trovate/applicate {len(correzioni_applicate)}. "
              f"Controlla a mano le righe che non sono state toccate - potrebbe mancare una corrispondenza esatta di nome.")

    if not APPLICA:
        print(f"\n--- ANTEPRIMA SOLTANTO: nessun file è stato toccato. ---")
        print(f"Righe che risulterebbero alla fine: {len(righe_finali)}")
        print("Se ti convince, esegui di nuovo con: python3 data/fix_extra_techniques.py --applica")
        return

    backup(PATH)
    scrivi_csv(PATH, header, righe_finali)
    print(f"\nFatto. Righe finali (escluso intestazione): {len(righe_finali)}")


if __name__ == "__main__":
    main()
