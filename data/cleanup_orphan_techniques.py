"""
Ripulisce le righe "orfane" di data/techniques.csv - nomi di tecniche
che puntano ad armature ormai rimosse o rinominate durante le
correzioni del canone (vedi le sessioni precedenti: Black Gold/Silver
Saint eliminati, Cassiopea/Delfino/Corona Boreale/Piccolo Cavallo
spostati sotto Saintia, Leda tolta come duplicato di Reda, ecc.).

Un caso speciale: "Robe di Hecate" - prima di cancellarla, lo script
cerca in armors.csv un'armatura che contenga "Hecate" nel nome (es.
"Robe di Hecate (Vecchia/Giovane)") - se la trova, RINOMINA la riga
invece di cancellarla, così Artemide/Hecate non perde le sue tecniche
vere per un semplice disallineamento di nome.

Uso:
    python3 data/cleanup_orphan_techniques.py                # anteprima
    python3 data/cleanup_orphan_techniques.py --applica       # applica sul serio (con backup)
"""
import csv
import sys
from pathlib import Path

APPLICA = "--applica" in sys.argv
DATA_DIR = Path(__file__).resolve().parent if Path(__file__).resolve().parent.name == "data" else Path("data")
ARMORS_PATH = DATA_DIR / "armors.csv"
TECHNIQUES_PATH = DATA_DIR / "techniques.csv"

# Le 28 righe genuinamente obsolete (armature rimosse durante le
# correzioni del canone, nessuna sostituzione da cercare) - vengono
# rimosse senza tentare nessun abbinamento.
NOMI_DA_RIMUOVERE = [
    "Black Cloth del Leone Minore", "Black Cloth del Lupo", "Black Cloth dell'Idra",
    "Black Cloth dell'Orsa", "Black Cloth dell'Unicorno",
    "Black Gold Cloth dei Gemelli", "Black Gold Cloth del Cancro", "Black Gold Cloth del Capricorno",
    "Black Gold Cloth del Leone", "Black Gold Cloth dell'Ariete", "Black Gold Cloth della Vergine",
    "Black Silver Cloth del Cane Maggiore", "Black Silver Cloth dell'Altare",
    "Black Silver Cloth dell'Aquila", "Black Silver Cloth della Lucertola", "Black Silver Cloth di Perseo",
    "Carina / Carena (Atlas)", "Cassiopea", "Chioma di Berenice (Bronze Saint)",
    "Coma Berenices / Chioma di B. (Berenice)", "Corona Boreale", "Delfino", "Leda",
    "Lince (Saint Seiya Omega)", "Loto - Aghora", "Lynx / Lince (Jaoh)", "Piccolo Cavallo",
    "Tarantola - Aracne",
]
NOME_DA_RIALLINEARE = "Robe di Hecate"  # trattato a parte, vedi sopra


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
    backup_path = path.with_suffix(path.suffix + ".bak3")
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Backup salvato in {backup_path}")


def main() -> None:
    if not ARMORS_PATH.exists() or not TECHNIQUES_PATH.exists():
        print("ERRORE: armors.csv o techniques.csv non trovati.")
        return

    armors_header, armors_rows = leggi_csv(ARMORS_PATH)
    idx_armor_name = armors_header.index("Armatura")
    nomi_armature_reali = {row[idx_armor_name] for row in armors_rows}

    tech_header, tech_rows = leggi_csv(TECHNIQUES_PATH)
    idx_tech_armor = tech_header.index("Armatura")

    print(f"Righe tecniche lette: {len(tech_rows)}")

    # Cerca un'armatura vera che contenga "Hecate" nel nome, per
    # riallineare invece di cancellare.
    candidati_hecate = [n for n in nomi_armature_reali if "Hecate" in n]
    riallineamento_hecate = None
    if candidati_hecate:
        nuovo_nome = candidati_hecate[0]
        if len(candidati_hecate) > 1:
            print(f"ATTENZIONE: trovate {len(candidati_hecate)} armature con 'Hecate' nel nome: {candidati_hecate} - uso la prima, controlla a mano se sono più di una davvero.")
        riallineamento_hecate = nuovo_nome
        print(f"\nTrovato riallineamento per '{NOME_DA_RIALLINEARE}': '{riallineamento_hecate}'")
    else:
        print(f"\nNessuna armatura con 'Hecate' nel nome trovata in armors.csv - '{NOME_DA_RIALLINEARE}' verrà rimossa come le altre.")

    righe_finali = []
    rimosse = []
    riallineate = []
    for row in tech_rows:
        nome = row[idx_tech_armor]
        if nome == NOME_DA_RIALLINEARE and riallineamento_hecate:
            row[idx_tech_armor] = riallineamento_hecate
            riallineate.append((nome, riallineamento_hecate))
            righe_finali.append(row)
        elif nome in NOMI_DA_RIMUOVERE or (nome == NOME_DA_RIALLINEARE and not riallineamento_hecate):
            rimosse.append(nome)
        else:
            righe_finali.append(row)

    print(f"\nRighe rimosse (armature obsolete, nessuna corrispondenza trovata): {len(rimosse)}")
    for nome in rimosse:
        print(f"  - {nome}")

    print(f"\nRighe riallineate (nome corretto invece di rimosse): {len(riallineate)}")
    for vecchio, nuovo in riallineate:
        print(f"  - '{vecchio}' -> '{nuovo}'")

    if not APPLICA:
        print(f"\n--- ANTEPRIMA SOLTANTO: nessun file è stato toccato. ---")
        print(f"Righe che risulterebbero alla fine: {len(righe_finali)}")
        print("Se ti convince, esegui di nuovo con: python3 data/cleanup_orphan_techniques.py --applica")
        return

    backup(TECHNIQUES_PATH)
    scrivi_csv(TECHNIQUES_PATH, tech_header, righe_finali)
    print(f"\nFatto. Righe finali (escluso intestazione): {len(righe_finali)}")


if __name__ == "__main__":
    main()
