#!/usr/bin/env python3
"""
Script sicuro per "marchiare" il frontend con GPverse.

Uso (nel tuo Codespace, nella root del repo):
    python3 brand_gpverse.py                # ANTEPRIMA — non scrive nulla
    python3 brand_gpverse.py --applica       # applica davvero le modifiche

Cosa fa:
  1. Aggiunge "GPverse" al <title> della scheda del browser.
  2. Inserisce una piccola scritta stile neon ciano "GPverse" nella
     schermata iniziale (renderStartPage), subito sotto "Sacro Imperio".

Come tutti gli script precedenti di questa sessione:
  - non scrive MAI senza --applica
  - crea sempre un backup (web/index.html.bak_gpverse) prima di toccare il file
  - se una delle stringhe da sostituire non viene trovata ESATTAMENTE,
    lo script si ferma e non tocca nulla (niente modifiche parziali)
"""
import argparse
import shutil
import sys
from pathlib import Path

TARGET = Path("web/index.html")
BACKUP = Path("web/index.html.bak_gpverse")

# --- Edit 1: titolo della scheda browser -----------------------------------
OLD_TITLE = "<title>Saint Seiya: Sacro Imperio</title>"
NEW_TITLE = "<title>Saint Seiya: Sacro Imperio — GPverse</title>"

# --- Edit 2: scritta neon nella schermata iniziale --------------------------
# Punto di aggancio: la riga esistente col sottotitolo "Sacro Imperio" + versione.
OLD_SUBTITLE_LINE = (
    'wrap.append(el("p", { class: "hint" }, "Sacro Imperio" '
    '+ (state.appVersion ? ` · ${state.appVersion}` : "")));'
)

GPVERSE_NEON_BLOCK = (
    OLD_SUBTITLE_LINE
    + "\n    wrap.append(el(\"p\", {\n"
    + '      style: "margin-top:4px;font-size:11px;letter-spacing:2px;'
    + "text-transform:uppercase;color:#3FF2F2;"
    + "text-shadow:0 0 6px #3FF2F2,0 0 14px #1FB8C9;\"\n"
    + "    }, \"GPverse\"));"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--applica",
        action="store_true",
        help="Applica davvero le modifiche (senza, è solo anteprima).",
    )
    args = parser.parse_args()

    if not TARGET.exists():
        print(f"ERRORE: non trovo {TARGET}. Esegui lo script dalla root del repo.")
        return 1

    original = TARGET.read_text(encoding="utf-8")
    content = original

    errors = []

    # --- Edit 1 ---
    if OLD_TITLE in content:
        count_title = content.count(OLD_TITLE)
        if count_title != 1:
            errors.append(
                f"Trovate {count_title} occorrenze del tag <title> atteso "
                f"(me ne aspettavo 1). Nessuna modifica applicata al titolo."
            )
        else:
            content = content.replace(OLD_TITLE, NEW_TITLE, 1)
            print("[OK] Titolo scheda browser → aggiornato con 'GPverse'.")
    else:
        errors.append(
            "Non ho trovato la riga esatta del <title> che mi aspettavo:\n"
            f"    {OLD_TITLE}\n"
            "Il file potrebbe essere cambiato dall'ultima volta: incollami "
            "la riga <title> reale e aggiorno lo script."
        )

    # --- Edit 2 ---
    if OLD_SUBTITLE_LINE in content:
        count_sub = content.count(OLD_SUBTITLE_LINE)
        if count_sub != 1:
            errors.append(
                f"Trovate {count_sub} occorrenze della riga del sottotitolo "
                f"attesa (me ne aspettavo 1). Nessuna scritta GPverse aggiunta."
            )
        else:
            content = content.replace(OLD_SUBTITLE_LINE, GPVERSE_NEON_BLOCK, 1)
            print("[OK] Schermata iniziale → aggiunta scritta neon 'GPverse'.")
    else:
        errors.append(
            "Non ho trovato la riga esatta del sottotitolo 'Sacro Imperio' "
            "che mi aspettavo in renderStartPage():\n"
            f"    {OLD_SUBTITLE_LINE}\n"
            "Il file potrebbe essere cambiato dall'ultima volta: incollami "
            "la funzione renderStartPage() reale e aggiorno lo script."
        )

    if errors:
        print("\n--- ATTENZIONE: una o più modifiche non sono state trovate ---")
        for e in errors:
            print(f"- {e}")
        if content == original:
            print("\nNessuna modifica applicata (nessuna delle due stringhe attese è stata trovata).")
            return 1
        else:
            print(
                "\nAlmeno una modifica è stata individuata correttamente; "
                "procedo SOLO con quella, se confermi con --applica."
            )

    if content == original:
        print("Nessuna modifica da applicare.")
        return 0

    if not args.applica:
        print("\n--- ANTEPRIMA (nessun file modificato) ---")
        print("Esegui di nuovo con --applica per scrivere davvero le modifiche.")
        return 0

    shutil.copy2(TARGET, BACKUP)
    TARGET.write_text(content, encoding="utf-8")
    print(f"\n[FATTO] Backup salvato in {BACKUP}")
    print(f"[FATTO] {TARGET} aggiornato con il branding GPverse.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
