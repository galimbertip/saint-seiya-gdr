"""
Versionamento dell'app.

Formato: PG_Vx.y.z
  x = MAJOR - cambio strutturale grosso (es. nuova architettura, nuovo motore)
  y = MINOR - nuova funzionalità/schermata completata
  z = PATCH - correzione di un bug

Il changelog qui sotto è la cronologia delle versioni concordate in chat.
Si aggiorna insieme al codice, non a posteriori.
"""

APP_VERSION = "PG_V3.0.0"

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
    {
        "version": "PG_V2.2.0",
        "desc": "BILANCIAMENTO DEL DANNO, il pezzo mai affrontato sul serio da quando esiste "
                "l'Arena. Diagnosi in chat: la Classe Armatura del difensore cresceva con DUE "
                "ingredienti (Destrezza + livello armatura), il tiro per colpire con UNO solo "
                "(Forza) - nessuna simmetria. Ora resolve_attack aggiunge il livello armatura "
                "ANCHE all'attaccante, stessa scala della CA. Formula del danno alzata da "
                "potenza/10 a potenza/6 (un colpo medio passa da ~6 a ~10 danni). Misurato "
                "prima/dopo: colpire un pari livello 35%→56%, colpire uno più forte 15%→35%, "
                "lunghezza tipica di uno scontro 30-60+ round→10-24 round, vittorie contro "
                "Facile/Difficile 95%/25% (mai misurato prima). Rimossa DnDEngine.use_technique, "
                "codice morto da tempo (l'orchestrazione vera vive in arena_manager.resolve_turn).\n"
                "STATISTICHE: Costituzione, Tecnica e Volontà non contavano letteralmente nulla "
                "in combattimento (solo Forza e Destrezza venivano usate) - segnalato in chat. "
                "Ora: Costituzione del difensore riduce il danno subito; Tecnica dell'attaccante "
                "aumenta il danno inflitto; Volontà dà un tiro salvezza per resistere del tutto "
                "a Veleno/Paralisi (nuovo DnDEngine.resolve_saving_throw, generico, riusabile per "
                "future resistenze). Gli avversari generati in Arena ora hanno anche Costituzione/"
                "Tecnica/Volontà (prima solo Forza/Destrezza), scalate come le altre col livello "
                "armatura.",
    },
    {
        "version": "PG_V2.3.0",
        "desc": "TAVERNA: 13 taverne separate per regno, con mappa interattiva a griglia (stesso "
                "principio di posizionamento già usato in Arena) - segnalino libero, taverniere "
                "fisso per regno, tavoli con occupanti che si rimescolano nel tempo. Dialogo con "
                "riconoscimento di intenti (saluto, sfida, domanda sul mondo...) più pulsanti di "
                "argomento e di tono (stile Football Manager: Sorriso caloroso/Braccia aperte/"
                "Sguardo freddo) che amplificano o smorzano l'effetto sull'affinità. Relazioni tra "
                "fazioni (alleata/neutrale/diffidente/ostile) che moltiplicano quanto pesano gesti "
                "positivi e negativi. Oltre una soglia di affinità, il PNG offre spontaneamente la "
                "missione del proprio regno. Bug corretto: l'armor_name con '/' rompeva il routing "
                "HTTP quando passato nell'URL - spostato in query string/corpo della richiesta.",
    },
    {
        "version": "PG_V2.4.0",
        "desc": "TORNEI a eliminazione diretta: Le Guerre Galattiche (solo Bronze Saint, 3 round) e "
                "il Torneo delle Stelle Libere (iscrizione aperta a chiunque, 4 round). Tabellone "
                "generato per intero all'iscrizione, con incontri futuri 'fantasma' (simulati "
                "internamente confrontando i livelli) mai rivelati in anticipo al giocatore - solo "
                "'Vincente Round X Incontro Y' finché non tocca davvero giocarli. Perdere un round "
                "chiude il torneo, nessun ritentativo, ricompensa proporzionale ai round superati.",
    },
    {
        "version": "PG_V2.5.0",
        "desc": "PROVE DEGLI INFERI: infiltrazione fino alla Sala dei Tre Giudici (Radamanthys/"
                "Minosse/Aiacos, le vere Surplice di Wyvern/Garuda/Griffon). Cinque prove in "
                "sequenza con un livello di allerta che sale sui fallimenti - alla soglia, "
                "un'imboscata (uno Spettro) interrompe la prova invece del solito tentativo; "
                "vincerla fa scendere l'allerta ma non a zero. Versione iniziale a tiro di dado "
                "pesato dalla statistica, poi SOSTITUITA su segnalazione diretta ('non un "
                "lanciadadi, mettiamo indovinelli') con 50 enigmi veri scritti a mano (10 per ogni "
                "prova, scelti a caso ad ogni tentativo, persistiti finché non si risponde per non "
                "pescarne uno nuovo ad ogni ricarica della pagina).",
    },
    {
        "version": "PG_V2.6.0",
        "desc": "DIFESA A ONDATE: il capitolo più grosso della sessione, motore di combattimento "
                "multi-unità scritto da zero (core/squad_battle.py) - 3 contro 3, iniziativa vera "
                "in stile D&D (tutte le unità di entrambi i lati in un unico ordine, non più turni "
                "1v1), 4 ondate, squadra fissa (chi cade resta caduto). Selezione team prima "
                "dell'inizio: casuale dalla propria fazione, oppure a scelta tra i compagni di "
                "fazione E chiunque abbia un legame davvero forte in Taverna (soglia alta apposta, "
                "anche da un'altra fazione). Attacco a bersaglio singolo o a tutto campo (stessa "
                "tecnica, potenza divisa tra i bersagli) scelto ad ogni turno. Il fallimento "
                "critico (1 naturale) può rivoltarsi contro un compagno della propria squadra, non "
                "solo mancare il colpo - richiesto esplicitamente in chat, esteso resolve_turn "
                "perché esponesse il tiro grezzo senza rompere l'Arena 1v1 che lo usa già. Due bug "
                "veri trovati e corretti giocando la battaglia fino in fondo, non a revisione: il "
                "turno non avanzava mai dopo un'azione del giocatore/alleato (bloccato per sempre "
                "sullo stesso attore); con fazioni piccole (es. Zeus, 4 armature) la quarta ondata "
                "restava vuota perché l'esclusione delle armature già usate si accumulava da tutte "
                "le ondate precedenti invece delle sole unità ancora vive. Corretto anche un caso "
                "limite più sottile: un alleato scelto per legame forte da un'altra fazione, se "
                "caduto in battaglia, poteva ricomparire come nemico in un'ondata successiva della "
                "stessa fazione - risolto tracciando la squadra alleata come esclusione fissa per "
                "l'intera missione, non solo tra le unità vive.",
    },
    {
        "version": "PG_V2.7.0",
        "desc": "TRE BARRE VERE ANCHE PER I PNG: vita/cosmo/stamina dei PNG canonici del roster "
                "(Maestri, Guardiani, avversari dei tornei, alleati/nemici della Difesa a Ondate) "
                "ora sono persistite sul roster, non più generate sempre al massimo ad ogni "
                "incontro - un PNG battuto di recente arriva ancora debole, e recupera nel tempo "
                "con gli stessi tassi già usati per il giocatore. Distinzione voluta dagli "
                "avversari CASUALI dell'Arena (generate_opponent, nome sempre nuovo apposta): quelli "
                "restano ephemeral come prima, non rappresentano mai la stessa persona due volte.",
    },
    {
        "version": "PG_V3.0.0",
        "desc": "GERARCHIA VERA PER FAZIONE - cambio strutturale, non solo una nuova funzionalità: "
                "le Divinità (nuovo core/divinities.py, 13 entità con armatura di vertice reale del "
                "catalogo) e le Figure Istituzionali ora hanno un vero allineamento persistito, "
                "mai mostrato, che cambia con una successione (Figure Istituzionali) o una "
                "reincarnazione molto più rara (Divinità - la Divinità stessa muore e rinasce, non "
                "solo un cambio di carica). La disposizione dell'intera fazione (media pesata tra "
                "allineamento della Divinità e della sua Figura Istituzionale, dove esiste) ora "
                "influenza anche lei i destini dei PNG comuni nella simulazione del mondo e "
                "l'aggressività dell'IA in combattimento - sopra al peso già dato dall'allineamento "
                "personale del singolo PNG, non al suo posto. La schermata Gerarchia è stata "
                "ricostruita per intero: non più un blocco globale di Figure Istituzionali separato "
                "da un elenco piatto di armature, ma una vera piramide dentro ogni card di fazione "
                "(Divinità -> Figura Istituzionale -> Cavalieri per grado, dai più alti scendendo - "
                "prima l'ordine era invertito). Bug di import circolare scoperto e aggirato: "
                "core.world_sim importa già da core.arena_manager, quindi core.arena_manager non "
                "può calcolare la disposizione di fazione da sé (ciclo) - la calcola il chiamante "
                "in api/arena_session.py e la passa come stringa alle funzioni di livello più "
                "basso, che restano pure. Recupero di changelog: questa voce e le cinque precedenti "
                "(da PG_V2.3.0) erano già in gioco da tempo ma non erano mai state registrate qui - "
                "disciplina di aggiornare la versione insieme al codice, non a posteriori, da "
                "riprendere sul serio da qui in avanti.",
    },
]
