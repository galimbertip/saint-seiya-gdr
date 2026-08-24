"""
Genera una tabella unica (xlsx) che unisce Foglio17 (catalogo armature)
e Foglio16 (tecniche), per revisione manuale dei disallineamenti.
"""
import sys
sys.path.insert(0, "/home/claude/saint_seiya_gdr")

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from core.data_loader import _read_armors_csv, _read_techniques_csv, ARMORS_CSV, TECHNIQUES_CSV

armor_rows = _read_armors_csv(ARMORS_CSV)
technique_rows = _read_techniques_csv(TECHNIQUES_CSV)

techs_by_name = {(r.get("Armatura") or "").strip(): r for r in technique_rows}
armor_names = {(r.get("Armatura") or "").strip() for r in armor_rows}
tech_names = set(techs_by_name.keys())

orphan_techniques = tech_names - armor_names   # nel Foglio16 ma non nel Foglio17
missing_techniques = armor_names - tech_names   # nel Foglio17 ma senza tecniche nel Foglio16

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Armature+Tecniche"

headers = [
    "Divinità", "Fazione", "Armatura", "Livello", "min_level", "Problema",
    "Tecnica 1", "Tipo 1", "Potenza 1", "Lancio 1", "Effetto 1",
    "Tecnica 2", "Tipo 2", "Potenza 2", "Lancio 2", "Effetto 2",
    "Tecnica 3", "Tipo 3", "Potenza 3", "Lancio 3", "Effetto 3",
]
ws.append(headers)
for c in range(1, len(headers) + 1):
    cell = ws.cell(row=1, column=c)
    cell.font = Font(name="Arial", bold=True, color="FFFFFF")
    cell.fill = PatternFill("solid", fgColor="2B5C8F")
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

red_fill = PatternFill("solid", fgColor="F8CBCB")
orange_fill = PatternFill("solid", fgColor="FDE9CB")
normal_font = Font(name="Arial", size=10)

row_idx = 2
for r in armor_rows:
    name = (r.get("Armatura") or "").strip()
    tech_row = techs_by_name.get(name)

    problema = ""
    if name in missing_techniques:
        problema = "Nessuna tecnica nel Foglio16"

    row_data = [
        r.get("Divinità", "").strip(),
        r.get("Fazione", "").strip(),
        name,
        r.get("Livello", ""),
        r.get("min_level", ""),
        problema,
    ]
    for i in (1, 2, 3):
        if tech_row:
            row_data += [
                (tech_row.get(f"tecnica{i}") or "").strip(),
                (tech_row.get(f"tipo{i}") or "").strip(),
                (tech_row.get(f"potenzatecnica{i}") or "").strip(),
                (tech_row.get(f"descrizionetecnica{i}") or "").strip(),
                (tech_row.get(f"effettotecnica{i}") or "").strip(),
            ]
        else:
            row_data += ["", "", "", "", ""]

    ws.append(row_data)
    for c in range(1, len(headers) + 1):
        ws.cell(row=row_idx, column=c).font = normal_font
    if problema:
        for c in range(1, len(headers) + 1):
            ws.cell(row=row_idx, column=c).fill = orange_fill
    row_idx += 1

# Righe extra per le tecniche "orfane" (nel Foglio16 ma senza armatura corrispondente nel Foglio17)
for orphan_name in sorted(orphan_techniques):
    tech_row = techs_by_name[orphan_name]
    row_data = [
        "???", "???", orphan_name, "", "",
        "Nel Foglio16 ma NON trovata nel Foglio17 (nome non combacia?)",
    ]
    for i in (1, 2, 3):
        row_data += [
            (tech_row.get(f"tecnica{i}") or "").strip(),
            (tech_row.get(f"tipo{i}") or "").strip(),
            (tech_row.get(f"potenzatecnica{i}") or "").strip(),
            (tech_row.get(f"descrizionetecnica{i}") or "").strip(),
            (tech_row.get(f"effettotecnica{i}") or "").strip(),
        ]
    ws.append(row_data)
    for c in range(1, len(headers) + 1):
        ws.cell(row=row_idx, column=c).font = normal_font
        ws.cell(row=row_idx, column=c).fill = red_fill
    row_idx += 1

# Larghezze colonne
widths = [12, 26, 32, 8, 9, 34, 26, 14, 9, 34, 30, 26, 14, 9, 34, 30, 26, 14, 9, 34, 30]
for i, w in enumerate(widths, start=1):
    ws.column_dimensions[get_column_letter(i)].width = w

ws.freeze_panes = "A2"
ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{row_idx - 1}"

# Foglio riepilogo
ws2 = wb.create_sheet("Riepilogo")
ws2["A1"] = "Riepilogo controlli"
ws2["A1"].font = Font(name="Arial", bold=True, size=13)
summary = [
    ("Armature totali (Foglio17)", len(armor_names)),
    ("Righe tecniche totali (Foglio16)", len(tech_names)),
    ("Armature senza nessuna tecnica", len(missing_techniques)),
    ("Righe tecniche senza armatura corrispondente", len(orphan_techniques)),
]
for i, (label, val) in enumerate(summary, start=3):
    ws2.cell(row=i, column=1, value=label).font = Font(name="Arial", size=11)
    ws2.cell(row=i, column=2, value=val).font = Font(name="Arial", size=11, bold=True)
ws2.column_dimensions["A"].width = 45
ws2.column_dimensions["B"].width = 12

out_path = "/home/claude/saint_seiya_gdr/data/tabella_revisione_armature.xlsx"
wb.save(out_path)
print("Salvato:", out_path)
print("Righe totali tabella principale:", row_idx - 1)
print("Missing techniques:", len(missing_techniques))
print("Orphan techniques:", len(orphan_techniques))
