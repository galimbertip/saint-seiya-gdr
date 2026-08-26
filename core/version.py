"""
Versionamento dell'app.

Formato: PG_Vx.y.z
  x = MAJOR - cambio strutturale grosso (es. nuova architettura, nuovo motore)
  y = MINOR - nuova funzionalità/schermata completata
  z = PATCH - correzione di un bug

Il changelog qui sotto è la cronologia delle versioni concordate in chat.
Si aggiorna insieme al codice, non a posteriori.
"""

APP_VERSION = "PG_V2.1.0"

CHANGELOG = [
    {
        "version": "PG_V0.1.0",
        "desc": "Prima schermata GUI funzionante (PySide6): creazione personaggio con tema "
                "scuro/oro/blu cosmo, tabella armature filtrata per livello giocatore, filtri "
                "Divinità/Fazione a cascata, anteprima tecniche, validazione armatura+livello "
                "tramite character_factory.",
    },
    {
        "version": "PG_V0.1.1",
        "desc": "Fix: refresh_armors_catalog() falliva con 'FOREIGN KEY constraint failed' "
                "se esisteva già un personaggio salvato, perché cancellava e ricreava tutte le "
                "armature invece di aggiornarle. Ora usa UPSERT sulle armature e non tocca mai "
                "righe referenziate da un cavaliere esistente. Aggiunto anche il logging "
                "centralizzato (core/app_logger.py, cartella logs/, retention 24h).",
    },
    {
        "version": "PG_V0.2.0",
        "desc": "Aggiunta la Scheda del Cavaliere (ui/character_sheet.py): cosmo, statistiche, "
                "livello/XP, stamina, età, tecniche reali con descrizione. Scritto main.py "
                "definitivo che collega creazione e scheda con un QStackedWidget: all'avvio "
                "mostra la scheda se esiste già un personaggio, altrimenti la creazione. "
                "Primo giro end-to-end completo: dati CSV -> database -> motore -> GUI.",
    },
    {
        "version": "PG_V0.3.0",
        "desc": "Schermata iniziale (ui/start_screen.py): elenco partite salvate + Continua/"
                "Nuova Partita, invece del caricamento automatico dell'ultimo personaggio. "
                "Aggiunta la sidebar di navigazione (ui/game_screen.py) con Scheda Cavaliere/"
                "Arena del Santuario/Centro Allenamento - le ultime due sono segnaposto "
                "onesti (spiegano cosa manca) in attesa delle dinamiche di gioco vere.",
    },
    {
        "version": "PG_V0.4.0",
        "desc": "Centro Allenamento vero e funzionante (ui/training_screen.py), icone vere "
                "(qtawesome) al posto delle emoji nella sidebar, eliminazione salvataggi ed "
                "'Esci'/'Salva ed Esci' nel menu. Introdotto il CALENDARIO DI GIOCO: ogni "
                "azione (allenamento o riposo) fa avanzare knight['game_day'] di un giorno "
                "intero, invece di essere istantanea - risolve la crescita troppo veloce "
                "segnalata. Barra calendario (Anno/Mese/Giorno) sempre visibile in "
                "GameScreen. L'età ora cresce davvero nel tempo (ogni 360 giorni = un anno), "
                "invece di restare fissa a 15. Migrazione DB automatica e retrocompatibile "
                "per i salvataggi già esistenti (game_day aggiunta con ALTER TABLE).",
    },
    {
        "version": "PG_V0.5.0",
        "desc": "PROGRAMMA SETTIMANALE stile Football Manager: sostituiti i pulsanti di "
                "allenamento istantaneo con 7 tendine (una per giorno) + 'Avanza Settimana', "
                "che applica tutto il programma in un colpo solo (core: RosterManager."
                "advance_week). Risolve il problema del 'click compulsivo su un solo focus': "
                "ora ogni avanzamento allena in modo bilanciato su più statistiche. Il "
                "programma si salva (weekly_schedule) e viene riproposto la volta dopo. "
                "Fix: il giorno ora avanza SEMPRE in apply_daily_training, anche quando il "
                "personaggio è troppo esausto per allenarsi (prima quel caso non faceva "
                "passare il giorno, rompendo il conteggio esatto dei 7 giorni settimanali). "
                "Migrazione DB automatica anche per weekly_schedule.",
    },
    {
        "version": "PG_V0.6.0",
        "desc": "RISCHIO INFORTUNIO: allenarsi da esausto non è più bloccato in automatico - "
                "si può forzare, ma si rischia di perdere un punto statistica invece di "
                "guadagnarlo (probabilità variabile per tipo di allenamento). Aggiunti due "
                "nuovi tipi di allenamento a tema ('Cascata del Sacrificio' per Costituzione, "
                "più duro; 'Sparring con i Compagni', stat casuale tra Forza/Destrezza/"
                "Costituzione, rischio più alto) ACCANTO a quelli esistenti, senza rinominarli "
                "(compatibilità con i programmi già salvati). Aggiunto 'Avanza Mese' - ripete "
                "lo stesso programma settimanale per 30 giorni, niente bisogno di 30 tendine. "
                "Il log dei risultati ora scorre in un'area dedicata invece di allungare la "
                "finestra all'infinito.",
    },
    {
        "version": "PG_V0.7.0",
        "desc": "ARENA DEL SANTUARIO funzionante (core/arena_manager.py, ui/arena_screen.py): "
                "combattimento a turni contro un avversario generato dal catalogo armature "
                "(livello comparabile al tuo, tecniche vere). Il Cosmo attuale fa da 'punti "
                "vita' per entrambi. Bug di bilanciamento trovato e corretto durante i test: "
                "passare il Cosmo reale (100-250) dentro calculate_ac faceva esplodere la "
                "Classe Armatura a 40+, rendendo impossibile colpire anche con un 20 naturale "
                "- il bonus 'sintonia cosmica' alla CA è stato azzerato (COSMO_ATTUNEMENT_FOR_AC "
                "in arena_manager.py) finché non progettiamo quella statistica come cosa "
                "separata dal Cosmo-HP. A fine scontro (vittoria/sconfitta/ritirata) il Cosmo "
                "si ricarica al massimo (placeholder, nessun recupero graduale ancora) e "
                "passa un giorno di gioco, coerente col calendario. Rimosso "
                "ArenaPlaceholderScreen, non più necessario.",
    },
    {
        "version": "PG_V0.8.0",
        "desc": "COMBATTIMENTO A 3 AZIONI + SENSI DEL COSMO. Il turno secco 'io attacco, tu "
                "attacchi' diventa Attacca/Difendi/Carica il Cosmo, scelti da entrambi i "
                "combattenti e risolti insieme (matrice di risoluzione). Difendi usa la "
                "tecnica difensiva vera se l'armatura ne ha una (30% del catalogo, verificato "
                "in chat), altrimenti una Parata generica. Aggiunti i Sensi del Cosmo, "
                "verificati sul canone (ricerca web in chat) e legati al player_level: Sesto "
                "(liv.3, sblocca Carica il Cosmo), Settimo (liv.10, si risveglia DA SOLO sotto "
                "il 20% di Cosmo, bonus x2 più forte di una Carica normale x1.5), Ottavo "
                "(liv.20, sopravvivi con 1 Cosmo al colpo che ti finirebbe, una volta a "
                "scontro), Nono (liv.50, dichiarato ma senza effetto meccanico - riservato al "
                "futuro). Due bug trovati e corretti durante i test: il Settimo Senso scattava "
                "OGNI turno sotto soglia invece che una volta sola (bonus infinito gratis); "
                "'Carica il Cosmo' non bruciava mai Cosmo davvero nonostante il design lo "
                "prevedesse. Aggiunta un'etichetta che mostra quali Sensi sono sbloccati.",
    },
    {
        "version": "PG_V0.9.0",
        "desc": "TURNO 'DICHIARA POI REAGISCI' invece di scelta simultanea alla cieca - "
                "segnalato in chat come il motivo per cui il combattimento sembrava 'finto' "
                "(un dado contro un dado nascosto, nessuna vera lettura dell'avversario). "
                "Ricerca in chat su sistemi di combattimento simili (Action Point systems, "
                "priority/stack di Magic: The Gathering, il combat system del gioco ufficiale "
                "Saint Seiya Awakening) per orientare la scelta. Ora ogni round ha due metà: "
                "TU dichiari (Attacca/Carica) e l'avversario reagisce d'istinto (più probabile "
                "difendersi se è già in crisi); poi l'AVVERSARIO dichiara e TU VEDI quale "
                "tecnica sta arrivando (nome e potenza) prima di scegliere se Difenderti o "
                "Incassare - non più una scelta pre-impostata alla cieca. 'Difendi' non è più "
                "un'azione proattiva nel menu: è una scelta reattiva, disponibile solo quando "
                "sei sotto attacco. core/arena_manager.py: choose_opponent_action ora sceglie "
                "solo Attacca/Carica; nuova opponent_reacts() con probabilità di difesa che "
                "cresce se l'avversario è messo male (testato: ~24% sano, ~62% in crisi).",
    },
    {
        "version": "PG_V1.0.0",
        "desc": "OROLOGIO UNIVERSALE A MINUTI, sostituisce il vecchio 'ogni azione = 1 giorno "
                "intero' - cambio strutturale grosso, richiesto in chat per poter incatenare "
                "azioni diverse nello stesso giorno di gioco (es. allenamento al Cosmo la "
                "mattina, poi Arena nel pomeriggio, invece di essere bloccati a un'azione al "
                "giorno). Nuova colonna knights.game_minutes (fonte di verità, sostituisce "
                "game_day che resta solo per compatibilità/cronologia), migrazione automatica "
                "e testata per i salvataggi esistenti (converte il giorno raggiunto in minuti "
                "equivalenti, a mezzanotte, senza perdere progressi). RosterManager.spend_time() "
                "sostituisce advance_day(): ogni azione ha una durata propria in minuti "
                "(TRAINING_MINUTES_BY_FOCUS: Riposo 8h, Cascata/Sparring 6h, altri 4h; Arena: "
                "ARENA_ROUND_MINUTES=15 min per mezzo-round, non più 1 giorno fisso a fine "
                "scontro). get_calendar_display ora mostra anche l'ora (formato "
                "'Anno X — Mese, giorno Y, ore HH:MM'). GameScreen: la barra superiore mostra "
                "ora anche Cosmo e Stamina sempre visibili in ogni schermata (richiesto in "
                "chat, necessario per decidere se concatenare azioni senza entrare in ogni "
                "sezione per saperlo), aggiornata ad ogni round in Arena, non solo a fine "
                "scontro. NOTA: 'Avanza Settimana/Mese' nell'Allenamento non corrisponde più "
                "esattamente a 7/30 giorni di calendario (dipende dalla durata dei focus "
                "scelti) - la griglia settimanale resta comoda per pianificare ma il nome è "
                "ormai una convenzione, non una promessa esatta; una revisione della UI di "
                "quella schermata resta un lavoro futuro, segnalato in chat.",
    },
    {
        "version": "PG_V2.0.0",
        "desc": "WEBAPP: nuova architettura in affiancamento al desktop, richiesta fin dal "
                "primo giorno (voleva poterci giocare ovunque, testare anche dal PC di lavoro "
                "senza poter installare nulla). Nuovo backend FastAPI (api/main.py, "
                "api/arena_session.py) che riusa di peso la logica già in core/ - stesso motore, "
                "nuova porta d'accesso via HTTP invece che pulsanti Qt. Nuovo frontend "
                "(web/index.html, pagina singola HTML/JS senza framework) servito dallo stesso "
                "backend su /app, stesso indirizzo per evitare problemi di CORS/URL mutevoli su "
                "Codespaces. Sviluppato e testato passo passo da GitHub Codespaces (browser "
                "puro, zero installazioni), compreso un giro di debug reale su sessioni scadute "
                "e tunnel morti.\n"
                "ARENA: Livelli di sfida (facile/medio/difficile, sposta il livello "
                "dell'avversario cercato). Vantaggio/Svantaggio nel motore dadi (due dadi, "
                "tieni il migliore/peggiore). Imprevisti Fase 1 (eventi 'usa e getta' con "
                "probabilità ~15% a mezzo-round: danno diretto o vantaggio/svantaggio sul tiro, "
                "con causa narrativa intrecciata nella frase, non più un'etichetta a parte). "
                "Imprevisti Fase 2 - V1 (Veleno vero: danno per 3 round poi svanisce, dal "
                "catalogo tecniche già isolato tempo fa; Pietrificazione/Intrappolamento "
                "rimandati apposta, toccherebbero il flusso dei turni). Fallimenti/colpi "
                "critici narrati con frasi variabili invece di un'etichetta fissa.\n"
                "BUG VERI trovati e corretti in sessione (elenco perché non banali): il "
                "messaggio del danno restava quello grezzo anche quando Carica/critico lo "
                "moltiplicavano dopo (poteva sembrare che difendersi AUMENTASSE il danno); una "
                "schivata vera mostrava comunque 'ti difendi con Parata' appiccicato sopra; "
                "Carica consumata anche su un colpo mancato, sprecata senza motivo; uscire "
                "dall'Arena a metà scontro (senza Ritirati) lasciava il Cosmo bloccato basso per "
                "sempre, mai più recuperabile; Allenamento e Arena condividevano per errore la "
                "stessa variabile di log, mostrando la cronaca sbagliata nella scheda sbagliata; "
                "connessione DB condivisa tra richieste, rischio di rottura intermittente con "
                "più thread (mai capitato, trovato a revisione).\n"
                "Il Cosmo ora si rigenera passivamente col tempo fuori dall'Arena (fedele al "
                "canone: un cavaliere che non combatte si riprende), proporzionale alle ore "
                "passate qualunque sia l'attività - mai durante un combattimento. Level up "
                "annuncia i nuovi Sensi sbloccati nello stesso messaggio, invece di scoprirli "
                "per caso provando i pulsanti.",
    },
    {
        "version": "PG_V2.1.0",
        "desc": "IMPREVISTI FASE 2 completata: Pietrificazione/Intrappolamento come Paralisi vera "
                "(blocca un turno intero), affiancata al Veleno già collaudato in PG_V2.0.0. "
                "Rimandata apposta la prima volta perché tocca il flusso dei turni (non solo un "
                "numero che scende) - qui resolve_declare distingue esplicitamente 'sei "
                "bloccato, salti l'azione ma il tempo passa comunque' da 'agisci normalmente', "
                "sia per il giocatore che per l'avversario, testato anche il caso in cui "
                "Veleno e Paralisi sono attivi insieme sullo stesso combattente. Aggiunta "
                "status_applied_message() condivisa (Veleno='è avvelenato', Paralisi='è "
                "pietrificato') invece di messaggi scritti a mano in due punti diversi. "
                "Barre del Cosmo in Arena ora in scala assoluta condivisa tra i due "
                "combattenti (chi ha più Cosmo massimo ha la barra fisicamente più lunga, non "
                "più solo la percentuale) - segnalato in chat: con Cosmo massimo diverso ma "
                "percentuali vicine, le barre sembravano identiche.",
    },
]
