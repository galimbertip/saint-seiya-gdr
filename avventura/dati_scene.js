// Dati delle scene. Le coordinate sono nei pixel dell'IMMAGINE ORIGINALE (1376x768):
// il motore le converte da solo nel mondo di gioco 320x180.
// walk   = poligono convesso (4 punti) dove Seiya può camminare
// scala  = [yLontano, scalaLontano, yVicino, scalaVicino]  (prospettiva)
// hotspot: r = [x, y, larghezza, altezza]; exit = uscita verso un'altra scena
const SCENE = {

  colle_villaggio: {
    nome: "Ai piedi del Santuario",
    img: "sfondo_colle_villaggio.png",
    walk: [[520,765],[880,765],[800,530],[690,530]],
    scala: [530, 0.32, 765, 0.5],
    hotspot: [
      { id:"sentiero", nome:"Sentiero del Grande Tempio", r:[650,380,230,170],
        exit:{ a:"piazza_grande_tempio", pos:[700,742] },
        guarda:"Il sentiero sale tra i templi fino al Grande Tempio." },
      { id:"casa", nome:"La mia casa", r:[365,505,165,165],
        exit:{ a:"camera_personale", pos:[760,742] },
        guarda:"La mia stanza al Santuario. Non è molto, ma è mia." },
      { id:"taverna", nome:"Taverna", r:[925,515,155,165],
        exit:{ a:"taverna", pos:[650,742] },
        guarda:"La taverna del villaggio. Dentro c'è sempre un camino acceso." },
      { id:"tempio", nome:"Grande Tempio", r:[790,25,300,185],
        guarda:"Il Grande Tempio, in cima alla rocca. Lassù si decide il destino del Santuario." },
      { id:"nubi", nome:"Mare di nubi", r:[0,260,450,508],
        guarda:"Il Santuario sta sopra le nuvole, lontano da tutto." }
    ]
  },

  piazza_grande_tempio: {
    nome: "Piazza del Grande Tempio",
    img: "sfondo_piazza_grande_tempio.png",
    walk: [[60,748],[1320,748],[1100,612],[260,612]],
    scala: [612, 0.58, 748, 0.84],
    hotspot: [
      { id:"giu", nome:"Villaggio", r:[420,736,560,32], exit:{ a:"colle_villaggio", pos:[690,560] },
        guarda:"La strada che scende al villaggio." },
      { id:"sx", nome:"Centro Allenamento", r:[0,560,70,200], exit:{ a:"centro_allenamento", pos:[1200,740] },
        guarda:"Da quella parte si trova il campo di allenamento." },
      { id:"dx", nome:"Arena del Santuario", r:[1306,560,70,200], exit:{ a:"arena", pos:[420,690] },
        guarda:"L'arena dove i cavalieri si sfidano." },
      { id:"scale", nome:"Grande Tempio", r:[760,230,200,250], approach:[850,612],
        exit:{ a:"tempio_athena_interno", pos:[690,735] },
        guarda:"La scalinata del Grande Tempio. Quanti passi servono per arrivare lassù?" },
      { id:"statua", nome:"Statua di Atena", r:[640,240,120,360], approach:[700,612],
        guarda:"La statua di Atena, con lancia e scudo. Veglia su tutto il Santuario.",
        parla:"Atena, dammi la forza di proteggere chi non può farlo.",
        usa:"Meglio non toccarla." },
      { id:"bancarella1", nome:"Bancarella di anfore", r:[320,415,155,175], approach:[400,640],
        guarda:"Anfore, tappeti e frutta. Il mercato è sempre vivace.",
        parla:"Non c'è nessuno al banco, solo qualche anfora.",
        prendi:"Non ho monete con me." },
      { id:"bancarella2", nome:"Bancarelle", r:[900,410,265,205], approach:[1000,650],
        guarda:"Tessuti a strisce e cesti di verdura, in fondo alla piazza.",
        prendi:"Non ho monete con me." }
    ]
  },

  tempio_athena_interno: {
    nome: "Tempio di Atena",
    img: "sfondo_tempio_athena_interno.png",
    walk: [[400,742],[980,742],[860,562],[520,562]],
    scala: [562, 0.55, 742, 0.95],
    hotspot: [
      { id:"giu", nome:"Piazza", r:[380,740,620,28], exit:{ a:"piazza_grande_tempio", pos:[850,620] },
        guarda:"Si torna alla piazza." },
      { id:"passaggio", nome:"Passaggio del Grande Sacerdote", r:[790,350,95,200], approach:[820,570],
        exit:{ a:"sala_grande_sacerdote", pos:[690,730] },
        guarda:"Un passaggio laterale porta alla sala del Grande Sacerdote." },
      { id:"statua", nome:"Statua di Atena", r:[590,150,200,400], approach:[690,570],
        guarda:"Atena in persona, scolpita nel marmo, con la Nike nella mano. Sembra guardarmi.",
        parla:"Ti proteggerò, qualunque cosa accada.",
        usa:"Non oso." },
      { id:"bracieri", nome:"Bracieri", r:[170,190,110,150],
        guarda:"I bracieri non si spengono mai." },
      { id:"stendardi", nome:"Stendardi", r:[545,355,60,120],
        guarda:"Stendardi blu e oro, i colori di Atena." }
    ]
  },

  sala_grande_sacerdote: {
    nome: "Sala del Grande Sacerdote",
    img: "sfondo_sala_grande_sacerdote.png",
    walk: [[260,746],[1120,746],[900,632],[480,632]],
    scala: [632, 0.6, 746, 0.9],
    hotspot: [
      { id:"giu", nome:"Tempio di Atena", r:[480,740,420,28], exit:{ a:"tempio_athena_interno", pos:[820,580] },
        guarda:"Si torna al tempio." },
      { id:"sx", nome:"Salita alle Case d'Oro", r:[0,300,130,430], exit:{ a:"scalinata_12_case", pos:[690,745] },
        guarda:"Da qui si sale verso le dodici Case d'Oro." },
      { id:"trono", nome:"Trono", r:[590,310,210,290], approach:[700,634],
        guarda:"Il trono del Grande Sacerdote, inciso con i dodici segni dello zodiaco.",
        parla:"Nessuno risponde. Il trono è vuoto.",
        usa:"Non mi permetterei mai di sedermi lì." },
      { id:"cupola", nome:"Cupola stellata", r:[300,0,780,300],
        guarda:"Le costellazioni brillano sulla cupola, come se il cielo fosse entrato nella sala." },
      { id:"stendardi", nome:"Stendardi", r:[170,150,130,330],
        guarda:"Stendardi viola e oro, un po' consumati." }
    ]
  },

  scalinata_12_case: {
    nome: "Scalinata delle Dodici Case",
    img: "sfondo_scalinata_12_case.png",
    walk: [[430,762],[900,762],[800,605],[620,605]],
    scala: [605, 0.34, 762, 0.46],
    hotspot: [
      { id:"giu", nome:"Sala del Grande Sacerdote", r:[400,745,520,23], exit:{ a:"sala_grande_sacerdote", pos:[300,735] },
        guarda:"Si torna alla sala del Grande Sacerdote." },
      { id:"prima", nome:"Prima Casa d'Oro", r:[675,55,145,95], approach:[700,610],
        exit:{ a:"casa_oro_ingresso", pos:[560,745] },
        guarda:"La prima delle dodici Case. Da qui comincia la salita." },
      { id:"case", nome:"Case d'Oro", r:[180,110,400,420],
        guarda:"Le Case d'Oro, una sopra l'altra. In ciascuna c'è un Gold Saint a custodirla.",
        usa:"Prima devo superare la prima Casa." },
      { id:"case2", nome:"Case d'Oro", r:[780,200,300,330],
        guarda:"Altre Case, più in alto. Quanta strada ancora." },
      { id:"nubi", nome:"Mare di nubi", r:[1000,520,376,248],
        guarda:"Sotto di noi, solo nuvole." }
    ]
  },

  casa_oro_ingresso: {
    nome: "Ingresso di una Casa d'Oro",
    img: "sfondo_casa_oro_ingresso.png",
    walk: [[330,748],[780,748],[790,540],[520,540]],
    scala: [540, 0.55, 748, 0.95],
    hotspot: [
      { id:"giu", nome:"Scalinata", r:[330,700,420,68], exit:{ a:"scalinata_12_case", pos:[690,640] },
        guarda:"La scalinata che torna giù." },
      { id:"porta", nome:"Porta d'oro", r:[500,290,170,260], approach:[600,640],
        exit:{ a:"casa_oro_interno", pos:[640,742] },
        guarda:"Una porta d'oro, decorata con le figure dello zodiaco.",
        apri:"Spingo la porta ed entro.", spingi:"Spingo la porta ed entro." },
      { id:"zodiaco", nome:"Disco zodiacale", r:[560,70,175,175],
        guarda:"Il disco con i dodici segni, sopra la porta." },
      { id:"braciere1", nome:"Braciere", r:[470,520,105,110],
        guarda:"Una fiamma sacra arde nel braciere." },
      { id:"braciere2", nome:"Braciere", r:[860,480,100,120],
        guarda:"Il fuoco della Casa. Non si spegne mai." }
    ]
  },

  casa_oro_interno: {
    nome: "Interno di una Casa d'Oro",
    img: "sfondo_casa_oro_interno.png",
    walk: [[250,755],[1120,755],[1000,602],[380,602]],
    scala: [602, 0.58, 755, 0.92],
    hotspot: [
      { id:"giu", nome:"Uscita", r:[400,740,500,28], exit:{ a:"casa_oro_ingresso", pos:[600,700] },
        guarda:"L'uscita sulla terrazza." },
      { id:"altare", nome:"Altare", r:[630,360,115,115], approach:[690,604],
        guarda:"Un altare dorato, nel fondo della sala.",
        usa:"Qui, un tempo, un Gold Saint pregava." },
      { id:"statue", nome:"Statue di cavalieri", r:[85,350,125,270],
        guarda:"Due cavalieri di pietra montano la guardia, immobili." },
      { id:"statue2", nome:"Statue di cavalieri", r:[1160,350,125,270],
        guarda:"La statua sembra seguirmi con lo sguardo. Forse è solo l'ombra." },
      { id:"colonne", nome:"Colonne istoriate", r:[250,150,200,400],
        guarda:"Colonne d'oro incise con i segni dello zodiaco, uno per uno." }
    ]
  },

  arena: {
    nome: "Arena del Santuario",
    img: "sfondo_arena.png",
    walk: [[300,705],[1100,705],[1000,475],[380,475]],
    scala: [475, 0.46, 705, 0.82],
    hotspot: [
      { id:"giu", nome:"Piazza del Grande Tempio", r:[480,740,420,28], exit:{ a:"piazza_grande_tempio", pos:[1220,690] },
        guarda:"Si esce verso la piazza." },
      { id:"sabbia", nome:"Sabbia dell'arena", r:[330,430,760,280], floor:true,
        guarda:"La sabbia è ancora segnata dall'ultimo scontro.",
        usa:"__sfida__" },
      { id:"porta", nome:"Porta di legno", r:[810,285,165,175], approach:[800,480],
        guarda:"Da quella porta entrano gli sfidanti." },
      { id:"statue", nome:"Statue di guerrieri", r:[40,70,1300,260],
        guarda:"Statue di antichi cavalieri sorvegliano le gradinate." }
    ]
  },

  centro_allenamento: {
    nome: "Centro Allenamento",
    img: "sfondo_centro_allenamento.png",
    walk: [[260,762],[1180,762],[1020,505],[460,505]],
    scala: [505, 0.48, 762, 0.9],
    hotspot: [
      { id:"sx", nome:"Piazza del Grande Tempio", r:[0,420,160,348], exit:{ a:"piazza_grande_tempio", pos:[130,740] },
        guarda:"Il colonnato porta alla piazza." },
      { id:"manichino", nome:"Manichino da allenamento", r:[780,265,135,120], approach:[820,520],
        guarda:"Un manichino di paglia. Non si lamenta mai.",
        usa:"__colpisci__", parla:"Non mi risponde. Meglio così." },
      { id:"manichino2", nome:"Manichino da allenamento", r:[385,265,75,120], approach:[440,520],
        guarda:"Un altro manichino, un po' consumato.",
        usa:"__colpisci__" },
      { id:"armi", nome:"Rastrelliera delle armi", r:[950,310,175,200], approach:[960,520],
        guarda:"Spade e lance. Un cavaliere però combatte a mani nude.",
        prendi:"Le armi non fanno per me." },
      { id:"pesi", nome:"Pesi", r:[1180,455,200,150], approach:[1150,640],
        guarda:"Pesi di pietra, per chi vuole diventare più forte.",
        usa:"__pesi__" },
      { id:"campo", nome:"Campo", r:[460,480,700,250], floor:true, usa:"__carica__",
        guarda:"Il campo di allenamento. Qui si diventa cavalieri." }
    ]
  },

  taverna: {
    nome: "Taverna",
    img: "sfondo_taverna.png",
    walk: [[200,762],[1100,762],[900,525],[400,525]],
    scala: [525, 0.55, 762, 1.0],
    hotspot: [
      { id:"giu", nome:"Villaggio", r:[300,742,700,26], exit:{ a:"colle_villaggio", pos:[1000,742] },
        guarda:"La porta sul villaggio." },
      { id:"camino", nome:"Camino", r:[1060,380,310,230], approach:[1000,600],
        guarda:"Un camino acceso. Qui ci si riposa davvero.",
        usa:"__scalda__" },
      { id:"bancone", nome:"Bancone", r:[90,390,560,300], approach:[550,630],
        guarda:"Un lungo bancone di legno, pieno di boccali.",
        parla:"Nessuno serve al bancone, per ora.",
        prendi:"Non rubo nelle taverne." },
      { id:"scaffali", nome:"Scaffali di bottiglie", r:[90,100,310,300],
        guarda:"Bottiglie verdi e boccali di peltro, in fila." },
      { id:"tavoli", nome:"Tavoli", r:[550,500,500,260], floor:true,
        guarda:"Tavoli rotondi, con una candela accesa." }
    ]
  },

  camera_personale: {
    nome: "La mia stanza",
    img: "sfondo_camera_personale.png",
    walk: [[110,755],[960,755],[1010,595],[390,595]],
    scala: [595, 0.62, 755, 1.0],
    hotspot: [
      { id:"giu", nome:"Villaggio", r:[160,742,700,26], exit:{ a:"colle_villaggio", pos:[460,742] },
        guarda:"La porta, sul villaggio." },
      { id:"letto", nome:"Letto", r:[500,330,300,235], approach:[640,598],
        guarda:"Un letto semplice, di paglia e legno.",
        usa:"__riposa__" },
      { id:"baule", nome:"Baule", r:[730,490,235,170], approach:[800,660],
        guarda:"Il baule dove tengo la mia armatura.",
        apri:"__armatura__", usa:"__armatura__" },
      { id:"cassa", nome:"Cassa di legno", r:[1100,480,276,288],
        guarda:"Una cassa piena di attrezzi di allenamento." },
      { id:"scrivania", nome:"Scrivania", r:[80,370,265,240], approach:[330,650],
        guarda:"Una pergamena, una piuma e un po' d'inchiostro. Il mio diario.",
        usa:"Per ora non ho niente da scrivere." },
      { id:"finestra", nome:"Finestra", r:[230,90,190,240],
        guarda:"Fuori, le montagne sotto le stelle." },
      { id:"stendardo", nome:"Stendardo dell'aquila", r:[555,95,170,205],
        guarda:"Lo stendardo del Santuario." }
    ]
  }
};

const PARTENZA = { scena: "piazza_grande_tempio", pos: [700, 690] };
