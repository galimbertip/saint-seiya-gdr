"""
Tema visivo dell'app: palette Saint Seiya (oro divino, blu cosmo, sfondo
notte). QSS è il "CSS" di Qt: si applica una volta sola con
app.setStyleSheet(build_stylesheet()) e ridisegna ogni widget standard.
"""

COLORS = {
    "bg_darkest": "#0B0F1A",     # sfondo finestra principale
    "bg_panel": "#141B2E",        # pannelli/card
    "bg_panel_alt": "#1B2438",     # righe alternate in liste/tabelle
    "border": "#2A3550",            # bordi sottili
    "gold": "#D4AF37",               # oro - Gold Saint, elementi divini
    "gold_dim": "#8A7229",            # oro spento - hover/disabled
    "cosmo_blue": "#3FA9F5",           # blu cosmo - energia, evidenziazioni
    "cosmo_blue_dim": "#245A7C",        # blu spento
    "text_primary": "#EAE6DA",           # testo principale, bianco caldo
    "text_secondary": "#9BA3B7",          # testo secondario/muto
    "danger": "#C0392B",                   # errori, HP critico
    "success": "#3FA96A",                   # conferme, riposo completato
}


def build_stylesheet() -> str:
    c = COLORS
    return f"""
    QWidget {{
        background-color: {c['bg_darkest']};
        color: {c['text_primary']};
        font-family: "Segoe UI", Arial, sans-serif;
        font-size: 13px;
    }}

    QFrame#card {{
        background-color: {c['bg_panel']};
        border: 1px solid {c['border']};
        border-radius: 10px;
    }}

    QLabel#headerTitle {{
        color: {c['gold']};
        font-size: 22px;
        font-weight: 600;
    }}

    QLabel#sectionTitle {{
        color: {c['cosmo_blue']};
        font-size: 15px;
        font-weight: 600;
    }}

    QLabel#hint {{
        color: {c['text_secondary']};
        font-size: 12px;
    }}

    QLineEdit {{
        background-color: {c['bg_panel_alt']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 8px 10px;
        color: {c['text_primary']};
    }}
    QLineEdit:focus {{
        border: 1px solid {c['cosmo_blue']};
    }}

    QPushButton {{
        background-color: {c['gold_dim']};
        color: {c['bg_darkest']};
        border: none;
        border-radius: 6px;
        padding: 9px 18px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {c['gold']};
    }}
    QPushButton:disabled {{
        background-color: {c['border']};
        color: {c['text_secondary']};
    }}

    QPushButton#secondary {{
        background-color: transparent;
        color: {c['cosmo_blue']};
        border: 1px solid {c['cosmo_blue_dim']};
    }}
    QPushButton#secondary:hover {{
        border: 1px solid {c['cosmo_blue']};
        background-color: {c['bg_panel_alt']};
    }}

    QPushButton#navButton {{
        background-color: transparent;
        color: {c['text_secondary']};
        border: none;
        border-radius: 6px;
        padding: 10px 14px;
        text-align: left;
        font-weight: 500;
    }}
    QPushButton#navButton:hover {{
        background-color: {c['bg_panel_alt']};
        color: {c['text_primary']};
    }}
    QPushButton#navButtonActive {{
        background-color: {c['bg_panel_alt']};
        color: {c['gold']};
        border: none;
        border-left: 3px solid {c['gold']};
        border-radius: 0px;
        padding: 10px 14px 10px 11px;
        text-align: left;
        font-weight: 600;
    }}

    QTableWidget {{
        background-color: {c['bg_panel']};
        alternate-background-color: {c['bg_panel_alt']};
        gridline-color: {c['border']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        selection-background-color: {c['cosmo_blue_dim']};
        selection-color: {c['text_primary']};
    }}
    QHeaderView::section {{
        background-color: {c['bg_panel_alt']};
        color: {c['gold']};
        padding: 6px;
        border: none;
        border-bottom: 1px solid {c['border']};
        font-weight: 600;
    }}

    QProgressBar {{
        background-color: {c['bg_panel_alt']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        text-align: center;
        color: {c['text_primary']};
        height: 16px;
    }}
    QProgressBar::chunk {{
        background-color: {c['cosmo_blue']};
        border-radius: 5px;
    }}

    QScrollBar:vertical {{
        background: {c['bg_darkest']};
        width: 10px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['border']};
        border-radius: 5px;
        min-height: 20px;
    }}
    """
