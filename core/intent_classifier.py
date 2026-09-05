"""Il riconoscimento di intenti per la Taverna, su testo scritto
liberamente dal giocatore (richiesto in chat: "vorrei lasciare
scrivere al pg la frase... i tasti di atteggiamento solo per il modo
con cui la dice"). Sostituisce il precedente riconoscimento a sole
parole chiave fisse (troppo rigido: bastava scrivere "sei molto
abile" invece di "sei bravo" per non farsi capire) con un confronto
di similarità testuale vera (TF-IDF + coseno, scikit-learn) contro un
insieme di frasi di esempio scritte per ciascun intento - la stessa
tecnica, in scala ridotta, con cui un motore di ricerca decide quali
pagine assomigliano di più a una query.

Scelta deliberata (richiesto in chat: "cerca una libreria gratuita"),
discussa con l'utente prima di implementarla: scikit-learn invece di
alternative più pesanti (Rasa NLU, modelli Hugging Face) - nessun
modello enorme da scaricare, nessun servizio separato da mantenere,
risposta in millisecondi su CPU pura. Il prezzo di questa scelta è
che capisce bene solo ciò che assomiglia abbastanza agli esempi
scritti qui sotto - da qui l'importanza di scriverne di vari, non
solo sinonimi dello stesso stampo.

Analyzer a n-grammi di CARATTERE (non di parola) apposta: l'italiano
coniuga/declina molto (bravo/brava/bravi/bravissimo), e un confronto
per parole intere perderebbe la somiglianza tra forme diverse della
stessa radice - i n-grammi di carattere la colgono comunque, senza
bisogno di un lemmatizzatore vero e proprio (che richiederebbe una
libreria più pesante, tipo spaCy)."""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Frasi di esempio per ciascun intento (richiesto in chat: "capire il
# 90% delle frasi") - non solo sinonimi dello stesso stampo, ma
# strutture diverse (affermazioni, domande, imperativi) per coprire
# meglio i modi reali in cui qualcuno scriverebbe la stessa intenzione.
INTENT_EXAMPLES = {
    "saluto": [
        "Ciao", "Salve", "Buongiorno", "Buonasera", "Ehi, come va",
        "Ben trovato", "Salute a te", "Ti saluto", "Piacere di vederti",
        "Ciao a te", "Buondì", "Ehilà", "Un saluto",
    ],
    "saluto_finale": [
        "Devo andare", "Ci vediamo", "Arrivederci", "Alla prossima",
        "Vado via ora", "Ora ti lascio", "È ora che vada", "Addio",
        "Ci si rivede presto", "Devo proprio andare", "Parto, a presto",
        "Ti saluto e vado",
    ],
    "ordina_da_bere": [
        "Portami qualcosa da bere", "Vorrei una birra", "Del vino, per favore",
        "Ho sete, cosa mi consigli", "Offro io un giro di bevande",
        "Dammi il tuo migliore drink", "Qualcosa di forte da bere",
        "Posso avere da bere", "Mi versi qualcosa", "Un bicchiere, grazie",
        "Cosa avete da bere qui", "Ho una sete tremenda", "Muoio di sete",
        "Mi porti una bevanda fresca", "Vorrei bere qualcosa", "Sono assetato",
    ],
    "complimento": [
        "Sei davvero forte", "Complimenti per il tuo Cosmo", "Sei molto abile",
        "Mi hai impressionato", "Che tecnica notevole", "Sei un guerriero eccezionale",
        "Ammiro il tuo coraggio", "Sei una leggenda", "Ben fatto, davvero",
        "Il tuo allenamento si vede", "Sei fortissimo", "Che spettacolo di combattente",
        "Sei bravo", "Sei brava", "Quanto sei bravo", "Sei davvero in gamba",
        "Che classe che hai", "Sei proprio un fenomeno",
    ],
    "insulto": [
        "Sei uno stupido", "Mi fai pena", "Sei patetico", "Non vali niente",
        "Sei un vigliacco", "Mi fai schifo", "Sei ridicolo", "Che idiota",
        "Non sei niente di speciale", "Fai proprio pena a vederti",
        "Sei inutile", "Ti disprezzo", "Sei un buono a nulla", "Non combini mai niente",
        "Sei una nullità", "Fai solo scena, non vali nulla", "Sei un fallito",
    ],
    "sfida": [
        "Ti sfido a duello", "Battiamoci, se hai coraggio", "Vuoi combattere",
        "Sono pronto a sfidarti", "Che ne dici di uno scontro", "Hai paura di me",
        "Dimostrami quanto vali in combattimento", "Affrontiamoci",
        "Voglio misurarmi con te", "Sfida accettata o hai paura",
        "Combattiamo, qui e ora", "Non hai il coraggio di affrontarmi",
        "Prova a battermi se ci riesci", "Vuoi provare la mia forza in un duello",
    ],
    "domanda_su_mondo": [
        "Ci sono novità", "Cosa succede nel Santuario", "Sai qualcosa di nuovo",
        "Che notizie hai", "Cosa sai delle missioni in corso", "Cosa ne pensi della situazione",
        "Si dice qualcosa di interessante in giro", "Novità dalle altre fazioni",
        "Cosa sta succedendo di recente", "Hai sentito qualche voce",
        "Si parla di una nuova minaccia", "Qualcuno parla di una guerra imminente",
    ],
    "domanda_su_di_te": [
        "Chi sei", "Parlami di te", "Raccontami la tua storia", "Cosa fai qui",
        "Di dove vieni", "Qual è il tuo nome", "Come ti chiami", "Come stai",
        "Da quanto tempo sei un Cavaliere", "Parlami del tuo passato",
        "Cosa ti ha portato qui", "Sotto quale Maestro ti sei allenato",
        "Da quanti anni combatti per la tua Dea", "Chi ti ha addestrato",
        "Qual è la tua armatura", "Con quale fazione combatti",
    ],
}

CONFIDENCE_THRESHOLD = 0.30  # PLACEHOLDER: sotto questa soglia di similarità, il gioco chiede di ripetere - alzata rispetto al primo tentativo (0.18 lasciava passare anche testo senza senso, vedi test in chat)

_vectorizer: TfidfVectorizer | None = None
_intent_vectors = None
_intent_labels: list[str] = []


def _ensure_classifier_built() -> None:
    """Costruisce il classificatore una sola volta (richiesto per non
    rifare il calcolo del vocabolario ad ogni singolo messaggio) - le
    chiamate successive lo trovano già pronto."""
    global _vectorizer, _intent_vectors, _intent_labels
    if _vectorizer is not None:
        return
    phrases: list[str] = []
    labels: list[str] = []
    for intent, examples in INTENT_EXAMPLES.items():
        for phrase in examples:
            phrases.append(phrase)
            labels.append(intent)
    _vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=True)
    _intent_vectors = _vectorizer.fit_transform(phrases)
    _intent_labels = labels


def classify_intent(text: str) -> tuple[str | None, float]:
    """L'intento più simile al testo scritto dal giocatore (richiesto
    in chat: testo libero, non più solo pulsanti) - None se nessun
    intento supera la soglia minima di somiglianza (il 10% di casi che
    il gioco non capisce, per cui chiede di ripetere). Restituisce
    anche il punteggio di similarità, utile per il debug/taratura
    della soglia."""
    text = (text or "").strip()
    if not text:
        return None, 0.0
    _ensure_classifier_built()
    text_vector = _vectorizer.transform([text])
    similarities = cosine_similarity(text_vector, _intent_vectors)[0]
    best_index = similarities.argmax()
    best_score = float(similarities[best_index])
    if best_score < CONFIDENCE_THRESHOLD:
        return None, best_score
    return _intent_labels[best_index], best_score
