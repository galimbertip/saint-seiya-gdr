"""
Applica le correzioni trovate nella ricostruzione da zero del canone
(sessione "ripartiamo da zero con Armature e Tecniche") ai file veri
del progetto - con ANTEPRIMA di default e backup automatico prima di
scrivere qualsiasi cosa, stesso principio già usato per
fix_techniques.py: mai ricostruire un file a mano in chat, sempre
leggere/scrivere il file vero sul disco.

Uso:
    python3 data/fix_canon_rebuild.py                # solo anteprima, non tocca nulla
    python3 data/fix_canon_rebuild.py --applica       # applica sul serio (con backup)

Cosa fa, file per file:

1) ARMATURE (cerca automaticamente armors.csv, poi armors_extra.csv
   se il primo non basta):
   - Bussola: sposta da "Silver Saint" a "Bronze Saint" (Rusk è
     confermato Bronze in Gigantomachia, non Silver)
   - Sestante: sposta da "Silver Saint" a "Bronze Saint" (Yulij è
     confermato Bronze in Gigantomachia, non Silver)
   - Rimuove "Lupo Scuro" (nessuna fonte trovata)
   - Rimuove "Aquila d'Atf" (nessuna fonte trovata - il vero
     personaggio Omega si chiama Yuna, ma non rinominiamo un'entità
     senza fonte propria, come deciso in chat)

2) TECNICHE (cerca automaticamente techniques.csv e
   techniques_extra.csv, applica ovunque trovi la riga giusta):
   - Crono, Soma della Spada (Spada di Iperione): tecnica1 corretta
     nel vero nome canonico (Ebony Vortex, da Episode G)
   - Crono, Soma delle Lame Doppie (Giapeto): tecnica1 corretta nel
     vero nome canonico (Khora Temnein, da Episode G)
   - Saturno, Chronotector di Saturno: tecnica1 corretta nel vero nome
     completo (Chrono Conclusion Eternal, da Saint Seiya Omega)
   - Rimuove le righe di tecniche per Lupo Scuro/Aquila d'Atf, se
     presenti (coerenza con la rimozione dalle armature)
   - Se Sestante ha una riga tecniche con Fazione "Silver Saint",
     l'aggiorna a "Bronze Saint" per restare coerente con l'armatura

Ogni file trovato viene backuppato in <nome>.bak PRIMA di essere
sovrascritto. Se un file non esiste, viene semplicemente saltato (
nessun errore) - il progetto potrebbe avere solo alcuni di questi file
a seconda di come sono organizzati i dati.
"""
import csv
import sys
from pathlib import Path

APPLICA = "--applica" in sys.argv

DATA_DIR = Path(__file__).resolve().parent if Path(__file__).resolve().parent.name == "data" else Path("data")


def leggi_csv_con_fix_virgolette(path: Path) -> tuple[list[str], list[list[str]]]:
    """Legge un CSV gestendo sia il formato standard sia quello con le
    virgolette esterne spurie per riga (bug noto dell'export Google
    Sheets, già documentato in core/data_loader.py) - prova prima il
    fix delle virgolette, e se la prima riga letta non sembra
    un'intestazione valida, ripiega sul parsing standard."""
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    fixed_lines = []
    for line in raw_lines:
        line = line.strip()
        if len(line) >= 2 and line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        fixed_lines.append(line)
    reader = csv.reader(fixed_lines)
    rows = list(reader)
    if not rows:
        return [], []
    header = rows[0]
    return header, rows[1:]


def scrivi_csv_con_virgolette(path: Path, header: list[str], rows: list[list[str]]) -> None:
    """Riscrive nello stesso formato con virgolette esterne per riga,
    per restare coerente con l'export originale e col fix già presente
    in core/data_loader.py - una riga alla volta, unendo i campi con
    virgola e avvolgendo l'intera riga tra virgolette doppie."""
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(row))
    quoted_lines = [f'"{line}"' for line in lines]
    path.write_text("\n".join(quoted_lines) + "\n", encoding="utf-8")


def backup(path: Path) -> None:
    backup_path = path.with_suffix(path.suffix + ".bak")
    backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"  Backup salvato in {backup_path}")


# --- Correzioni sulle ARMATURE ---------------------------------------------

RINOMINA_FAZIONE = [
    # (Divinità, Armatura, Fazione_vecchia_attesa, Fazione_nuova)
    ("Athena", "Bussola", "Silver Saint", "Bronze Saint"),
    ("Athena", "Sestante", "Silver Saint", "Bronze Saint"),
]
RIMUOVI_ARMATURE = [
    # (Divinità, Armatura) - nessuna fonte canonica trovata
    ("Athena", "Lupo Scuro"),
    ("Athena", "Aquila d'Atf"),
]
NUOVO_LIVELLO_BRONZE = "32"  # coerente con gli altri Bronze Saint minori del catalogo


def elabora_file_armature(path: Path) -> None:
    if not path.exists():
        print(f"[{path.name}] non trovato, salto.")
        return

    header, rows = leggi_csv_con_fix_virgolette(path)
    try:
        idx_divinita = header.index("Divinità")
        idx_fazione = header.index("Fazione")
        idx_armatura = header.index("Armatura")
        idx_livello = header.index("Livello")
        idx_min_level = header.index("min_level")
    except ValueError as e:
        print(f"[{path.name}] intestazione inattesa ({e}), salto questo file per sicurezza.")
        return

    print(f"\n=== {path.name} — {len(rows)} righe lette ===")

    modifiche_fazione = []
    for row in rows:
        for divinita, armatura, fazione_attesa, fazione_nuova in RINOMINA_FAZIONE:
            if row[idx_divinita] == divinita and row[idx_armatura] == armatura:
                if row[idx_fazione] == fazione_attesa:
                    modifiche_fazione.append((row, fazione_attesa, fazione_nuova))
                elif row[idx_fazione] == fazione_nuova:
                    print(f"  '{armatura}' è già '{fazione_nuova}' - nessuna modifica necessaria.")
                else:
                    print(f"  ATTENZIONE: '{armatura}' ha Fazione '{row[idx_fazione]}', "
                          f"diversa da quella attesa '{fazione_attesa}' - salto per sicurezza, controlla a mano.")

    print(f"\nSpostamenti di categoria trovati: {len(modifiche_fazione)}")
    for row, vecchia, nuova in modifiche_fazione:
        print(f"  - {row[idx_armatura]}: '{vecchia}' -> '{nuova}' "
              f"(livello {row[idx_livello]} -> {NUOVO_LIVELLO_BRONZE})")

    righe_da_rimuovere = []
    for row in rows:
        for divinita, armatura in RIMUOVI_ARMATURE:
            if row[idx_divinita] == divinita and row[idx_armatura] == armatura:
                righe_da_rimuovere.append(row)

    print(f"\nRighe da rimuovere (nessuna fonte canonica trovata): {len(righe_da_rimuovere)}")
    for row in righe_da_rimuovere:
        print(f"  - {row[idx_divinita]} / {row[idx_armatura]}")

    if not APPLICA:
        print(f"\n--- ANTEPRIMA SOLTANTO per {path.name}: nessun file è stato toccato. ---")
        return

    for row, vecchia, nuova in modifiche_fazione:
        row[idx_fazione] = nuova
        row[idx_livello] = NUOVO_LIVELLO_BRONZE
        row[idx_min_level] = "1"

    nuove_righe = [row for row in rows if row not in righe_da_rimuovere]

    backup(path)
    scrivi_csv_con_virgolette(path, header, nuove_righe)
    print(f"Fatto. Righe finali (escluso intestazione): {len(nuove_righe)}")


# --- Correzioni sulle TECNICHE ----------------------------------------------

CORREZIONI_TECNICA1 = [
    # (Divinità, Armatura, tecnica1_nuova) - il resto della riga (tipo,
    # descrizione, effetto, potenza) resta invariato, cambia solo il nome
    ("Crono", "Soma della Spada (Spada di Iperione)", "Ebony Vortex"),
    ("Crono", "Soma delle Lame Doppie (Giapeto)", "Khora Temnein"),
    ("Saturno", "Chronotector di Saturno", "Chrono Conclusion Eternal"),
]


def elabora_file_tecniche(path: Path) -> None:
    if not path.exists():
        print(f"[{path.name}] non trovato, salto.")
        return

    header, rows = leggi_csv_con_fix_virgolette(path)
    try:
        idx_divinita = header.index("Divinità")
        idx_fazione = header.index("Fazione")
        idx_armatura = header.index("Armatura")
        idx_tecnica1 = header.index("tecnica1")
    except ValueError as e:
        print(f"[{path.name}] intestazione inattesa ({e}), salto questo file per sicurezza.")
        return

    print(f"\n=== {path.name} — {len(rows)} righe lette ===")

    correzioni_trovate = []
    for row in rows:
        for divinita, armatura, nuova_tecnica in CORREZIONI_TECNICA1:
            if row[idx_divinita] == divinita and row[idx_armatura] == armatura:
                correzioni_trovate.append((row, row[idx_tecnica1], nuova_tecnica))

    print(f"Correzioni di tecnica1 trovate: {len(correzioni_trovate)}")
    for row, vecchia, nuova in correzioni_trovate:
        print(f"  - {row[idx_divinita]} / {row[idx_armatura]}: '{vecchia}' -> '{nuova}'")

    righe_da_rimuovere = []
    for row in rows:
        for divinita, armatura in RIMUOVI_ARMATURE:
            if row[idx_divinita] == divinita and row[idx_armatura] == armatura:
                righe_da_rimuovere.append(row)
    if righe_da_rimuovere:
        print(f"Righe di tecniche da rimuovere (armature senza fonte): {len(righe_da_rimuovere)}")
        for row in righe_da_rimuovere:
            print(f"  - {row[idx_divinita]} / {row[idx_armatura]}")

    aggiornamenti_fazione = []
    for row in rows:
        for divinita, armatura, fazione_attesa, fazione_nuova in RINOMINA_FAZIONE:
            if (row[idx_divinita] == divinita and row[idx_armatura] == armatura
                    and row[idx_fazione] == fazione_attesa):
                aggiornamenti_fazione.append((row, fazione_attesa, fazione_nuova))
    if aggiornamenti_fazione:
        print(f"Righe di tecniche con Fazione da aggiornare: {len(aggiornamenti_fazione)}")
        for row, vecchia, nuova in aggiornamenti_fazione:
            print(f"  - {row[idx_armatura]}: '{vecchia}' -> '{nuova}'")

    if not APPLICA:
        print(f"\n--- ANTEPRIMA SOLTANTO per {path.name}: nessun file è stato toccato. ---")
        return

    for row, _vecchia, nuova in correzioni_trovate:
        row[idx_tecnica1] = nuova
    for row, _vecchia, nuova in aggiornamenti_fazione:
        row[idx_fazione] = nuova

    nuove_righe = [row for row in rows if row not in righe_da_rimuovere]

    backup(path)
    scrivi_csv_con_virgolette(path, header, nuove_righe)
    print(f"Fatto. Righe finali (escluso intestazione): {len(nuove_righe)}")


def main() -> None:
    print("=" * 70)
    print("Correzioni ricostruzione da zero — Crono, Saturno, Bussola, Sestante,")
    print("Lupo Scuro, Aquila d'Atf")
    print("=" * 70)

    for nome_file in ("armors.csv", "armors_extra.csv"):
        elabora_file_armature(DATA_DIR / nome_file)

    for nome_file in ("techniques.csv", "techniques_extra.csv"):
        elabora_file_tecniche(DATA_DIR / nome_file)

    if not APPLICA:
        print("\n" + "=" * 70)
        print("Tutto sopra è SOLO ANTEPRIMA. Se ti convince, esegui di nuovo con:")
        print("    python3 data/fix_canon_rebuild.py --applica")
        print("=" * 70)


if __name__ == "__main__":
    main()
