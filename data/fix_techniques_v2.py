"""
Correzione DEFINITIVA di data/techniques.csv - rimpiazza sia il
precedente fix_techniques.py sia la parte "techniques.csv" di
fix_canon_rebuild.py, che insieme avevano un bug di scrittura serio
(univano i campi con una virgola "a mano", senza le virgolette che
servono quando un campo contiene già una virgola al suo interno -
come capita spesso nelle descrizioni in prosa) - corrotto il file ad
ogni riscrittura successiva. Qui la scrittura usa il modulo csv
standard di Python (csv.writer), che gestisce da solo le virgolette
dove servono davvero.

PRIMA DI USARE QUESTO SCRIPT: ripristina l'originale pulito da git,
dal terminale del progetto:

    git checkout dca0998 -- data/techniques.csv
    wc -l data/techniques.csv   # deve dare 223

Poi:
    python3 data/fix_techniques_v2.py                # anteprima, non tocca nulla
    python3 data/fix_techniques_v2.py --applica       # applica sul serio (con backup)

Cosa fa:
1) Rimuove le righe duplicate (stessa Divinità+Armatura) - tiene solo
   la prima occorrenza di ciascuna.
2) Corregge Athena/Orione (Saint Seiya Omega): tecnica1 -> "Ignis
   Fatuus", tecnica2 -> "Ignis Fatuus Saltare" (nomi canonici veri, da
   Episode G/Omega - verificato in chat).
3) Aggiorna la Fazione di Athena/Sestante da "Silver Saint" a "Bronze
   Saint", per restare coerente con la stessa correzione già fatta su
   armors.csv (Sextans Yulij è confermato Bronze, non Silver).
"""
import csv
import sys
from pathlib import Path

APPLICA = "--applica" in sys.argv
DATA_DIR = Path(__file__).resolve().parent if Path(__file__).resolve().parent.name == "data" else Path("data")
TECHNIQUES_PATH = DATA_DIR / "techniques.csv"


def leggi_csv_con_fix_virgolette(path: Path) -> tuple[list[str], list[list[str]]]:
    """Stessa logica di lettura di core/data_loader.py: toglie la
    coppia di virgolette esterne per riga SE presenti (bug noto
    dell'export originale), poi parsa con csv.reader vero - che sa già
    gestire correttamente i campi con virgole interne, purché siano
    tra virgolette come da standard CSV."""
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


def scrivi_csv_standard(path: Path, header: list[str], rows: list[list[str]]) -> None:
    """Scrittura CSV VERA (richiesto in chat, dopo il bug di scrittura
    a mano) - usa csv.writer, che avvolge tra virgolette SOLO i campi
    che ne hanno davvero bisogno (quelli con una virgola, una
    virgoletta o un a-capo al loro interno), invece di unire i campi
    con una virgola nuda che poi si confonde con le virgole già
    presenti nel testo delle descrizioni. Compatibile al 100% con la
    lettura già presente in core/data_loader.py: quella toglie le
    virgolette esterne SOLO se una riga le ha per intero (il vecchio
    bug), altrimenti la lascia invariata - un CSV scritto in modo
    standard come questo non ha mai quel problema, quindi passa
    inalterato."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def backup(path: Path) -> None:
    backup_path = path.with_suffix(path.suffix + ".bak2")
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Backup salvato in {backup_path}")


CORREZIONI_TECNICA = [
    # (Divinità, Armatura, indice_colonna_tecnica, nuovo_valore)
    ("Athena", "Orione (Saint Seiya Omega)", "tecnica1", "Ignis Fatuus"),
    ("Athena", "Orione (Saint Seiya Omega)", "tecnica2", "Ignis Fatuus Saltare"),
]
CORREZIONI_FAZIONE = [
    # (Divinità, Armatura, Fazione_attesa, Fazione_nuova)
    ("Athena", "Sestante", "Silver Saint", "Bronze Saint"),
]


def main() -> None:
    if not TECHNIQUES_PATH.exists():
        print(f"ERRORE: {TECHNIQUES_PATH} non trovato.")
        return

    header, rows = leggi_csv_con_fix_virgolette(TECHNIQUES_PATH)
    try:
        idx_divinita = header.index("Divinità")
        idx_fazione = header.index("Fazione")
        idx_armatura = header.index("Armatura")
    except ValueError as e:
        print(f"ERRORE: intestazione inattesa ({e}) - il file potrebbe essere già corrotto. Ripristina da git prima di continuare.")
        return

    print(f"Righe lette (escluso intestazione): {len(rows)}")

    # 1) Deduplicazione: tiene solo la prima occorrenza di ciascuna
    # coppia (Divinità, Armatura).
    viste = set()
    righe_pulite = []
    scartate = []
    for row in rows:
        chiave = (row[idx_divinita], row[idx_armatura])
        if chiave in viste:
            scartate.append(row)
            continue
        viste.add(chiave)
        righe_pulite.append(row)

    print(f"\nRighe duplicate trovate (stessa Divinità+Armatura): {len(scartate)}")
    for row in scartate[:10]:
        print(f"  - {row[idx_divinita]} / {row[idx_armatura]}")
    if len(scartate) > 10:
        print(f"  ... e altre {len(scartate) - 10}")

    # 2) Correzioni di nome tecnica.
    correzioni_applicate = []
    for row in righe_pulite:
        for divinita, armatura, colonna, nuovo_valore in CORREZIONI_TECNICA:
            if row[idx_divinita] == divinita and row[idx_armatura] == armatura:
                idx_colonna = header.index(colonna)
                vecchio = row[idx_colonna]
                if vecchio != nuovo_valore:
                    correzioni_applicate.append((armatura, colonna, vecchio, nuovo_valore))
                    row[idx_colonna] = nuovo_valore

    print(f"\nCorrezioni di tecnica trovate: {len(correzioni_applicate)}")
    for armatura, colonna, vecchio, nuovo in correzioni_applicate:
        print(f"  - {armatura} / {colonna}: '{vecchio}' -> '{nuovo}'")

    # 3) Correzioni di Fazione.
    fazioni_applicate = []
    for row in righe_pulite:
        for divinita, armatura, fazione_attesa, fazione_nuova in CORREZIONI_FAZIONE:
            if row[idx_divinita] == divinita and row[idx_armatura] == armatura and row[idx_fazione] == fazione_attesa:
                fazioni_applicate.append((armatura, fazione_attesa, fazione_nuova))
                row[idx_fazione] = fazione_nuova

    print(f"\nCorrezioni di Fazione trovate: {len(fazioni_applicate)}")
    for armatura, vecchia, nuova in fazioni_applicate:
        print(f"  - {armatura}: '{vecchia}' -> '{nuova}'")

    if not APPLICA:
        print(f"\n--- ANTEPRIMA SOLTANTO: nessun file è stato toccato. ---")
        print(f"Righe che risulterebbero alla fine: {len(righe_pulite)}")
        print("Se ti convince, esegui di nuovo con: python3 data/fix_techniques_v2.py --applica")
        return

    backup(TECHNIQUES_PATH)
    scrivi_csv_standard(TECHNIQUES_PATH, header, righe_pulite)
    print(f"\nFatto. Righe finali (escluso intestazione): {len(righe_pulite)}")


if __name__ == "__main__":
    main()
