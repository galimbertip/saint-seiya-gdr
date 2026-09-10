"""
Script da eseguire in Codespaces, dentro la cartella del progetto,
per applicare le correzioni trovate durante la verifica canone.

USO IN DUE PASSI (sicurezza, dopo l'incidente di sovrascrittura):

  1) Prima ESEGUI SOLO L'ANTEPRIMA, senza toccare nulla:
       python3 fix_techniques.py

     Ti mostra esattamente cosa farebbe (la correzione di Orione, e
     l'elenco di righe che considera duplicate) SENZA scrivere niente
     sul disco.

  2) Se l'elenco ti convince, esegui DAVVERO con:
       python3 fix_techniques.py --applica

     Solo in questo caso scrive sul file (con backup automatico
     prima, in data/techniques.csv.bak).

Legge data/techniques.csv (il file VERO, quello sul disco) - non
un file ricostruito a mano in chat, per evitare l'errore di
trascrizione già capitato una volta.
"""
import csv
import io
import shutil
import sys
from pathlib import Path

PATH = Path("data/techniques.csv")
BACKUP_PATH = Path("data/techniques.csv.bak")


def leggi_righe_vere(path: Path) -> list[list[str]]:
    """Legge il file rispettando il bug delle virgolette esterne per
    riga (stesso fix già usato in core/data_loader.py._read_quoted_csv)."""
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    fixed_lines = []
    for line in raw_lines:
        line = line.strip()
        if len(line) >= 2 and line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        fixed_lines.append(line)
    return list(csv.reader(fixed_lines))


def scrivi_righe(path: Path, righe: list[list[str]]) -> None:
    """Riscrive nello STESSO formato originale (ogni riga avvolta in
    virgolette esterne), per non rompere la compatibilità col fix già
    presente in data_loader.py."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(righe)
    righe_testo = buf.getvalue().splitlines()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for riga in righe_testo:
            f.write(f'"{riga}"\n')


def trova_correzioni_e_duplicati(dati: list[list[str]]):
    """Analizza i dati e restituisce (correzioni_tecnica, indici_da_rimuovere,
    dettagli_duplicati) senza modificare nulla - usata sia per
    l'anteprima che per l'applicazione vera, stessa identica logica."""
    correzioni = []
    for riga in dati:
        if riga[0] == "Athena" and riga[2] == "Orione (Saint Seiya Omega)":
            correzioni.append(riga)

    viste = set()
    indici_da_rimuovere = []
    dettagli_duplicati = []
    for i, riga in enumerate(dati):
        chiave = (riga[0], riga[2])
        if chiave in viste:
            indici_da_rimuovere.append(i)
            dettagli_duplicati.append((riga[0], riga[2], riga[3] if len(riga) > 3 else ""))
        else:
            viste.add(chiave)

    return correzioni, indici_da_rimuovere, dettagli_duplicati


def main():
    applica = "--applica" in sys.argv

    if not PATH.exists():
        print(f"ERRORE: non trovo {PATH} - esegui questo script dalla cartella principale del progetto.")
        return

    righe = leggi_righe_vere(PATH)
    header, dati = righe[0], righe[1:]
    print(f"Righe lette (escluso intestazione): {len(dati)}")

    correzioni, indici_da_rimuovere, dettagli_duplicati = trova_correzioni_e_duplicati(dati)

    print(f"\n=== Correzione di tecnica (Orione Saint Seiya Omega) ===")
    if correzioni:
        print("Trovata la riga - verrà cambiata tecnica1 in 'Ignis Fatuus' e tecnica2 in 'Ignis Fatuus Saltare'.")
    else:
        print("ATTENZIONE: non trovata nessuna riga 'Athena, Orione (Saint Seiya Omega)' - nessuna correzione da applicare qui.")

    print(f"\n=== Righe considerate duplicate (stessa Divinità+Armatura) ===")
    print(f"Trovate {len(dettagli_duplicati)} righe che verrebbero rimosse (tenuta solo la prima occorrenza di ciascuna):\n")
    for divinita, armatura, tecnica1 in dettagli_duplicati:
        print(f"  - {divinita} / {armatura}  (tecnica1 attuale nella riga scartata: \"{tecnica1}\")")

    if not applica:
        print(f"\n--- ANTEPRIMA SOLTANTO: nessun file è stato toccato. ---")
        print(f"Se l'elenco sopra ti convince, esegui di nuovo con: python3 fix_techniques.py --applica")
        return

    shutil.copy(PATH, BACKUP_PATH)
    print(f"\nBackup salvato in {BACKUP_PATH}")

    for riga in correzioni:
        riga[3] = "Ignis Fatuus"
        riga[8] = "Ignis Fatuus Saltare"

    dati_puliti = [riga for i, riga in enumerate(dati) if i not in set(indici_da_rimuovere)]

    righe_finali = [header] + dati_puliti
    scrivi_righe(PATH, righe_finali)

    print(f"\nFatto. Righe finali (escluso intestazione): {len(dati_puliti)}")
    print(f"Se qualcosa non va, ripristina con: cp {BACKUP_PATH} {PATH}")


if __name__ == "__main__":
    main()
