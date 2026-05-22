# Swiss IT Jobs Analytics

[English](../../README.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Italiano](README.it.md)

Swiss IT Jobs Analytics è uno strumento che analizza migliaia di annunci di lavoro nel mercato svizzero per identificare le competenze, le tecnologie e i percorsi di carriera più richiesti, aiutando a capire cosa imparare oggi per restare competitivi domani.

Guarda il sito ora - https://vivalabit.github.io/swiss-it-jobs-analytics/

Fonti attuali:

- `LinkedIn`
- `jobs.ch`
- `jobscout24.ch`
- `jobup.ch`
- `swissdevjobs.ch`

Il dataset viene deduplicato tra le fonti a livello di posizione lavorativa.
Quando lo stesso annuncio è pubblicato su più portali di lavoro, viene conteggiato una sola volta nelle statistiche pubbliche.

Il progetto è ancora in corso, quindi statistiche e struttura possono cambiare.

Il sito pubblico pubblica istantanee aggregate del mercato svizzero del lavoro IT, costruite a partire da dataset elaborati di annunci provenienti da più portali. Evidenzia segnali generali come volume degli annunci, attività dei datori di lavoro, domanda di competenze, fasce salariali, concentrazione geografica, distribuzione dei livelli di seniority e modalità di lavoro.


## Cosa copre questo progetto

Questo progetto è progettato per rispondere a domande pratiche e basate sui dati sul mercato del lavoro:

- Quali ruoli sono attualmente più richiesti
- Quali competenze e tecnologie compaiono più frequentemente
- Quali cantoni e città hanno la più alta concentrazione di annunci di lavoro
- Come si distribuisce la domanda tra i livelli di seniority
- Come differiscono le fasce salariali comparabili tra le categorie di ruolo
- Quali competenze sono effettivamente valorizzate dai datori di lavoro

<img src="../img/image.png" width="900">

**Le statistiche coprono gli annunci pubblicati dal 2026 in poi.**


***Le agenzie di collocamento sono escluse.***

## Metodologia

Raccogliamo annunci di lavoro da diverse fonti (LinkedIn, jobs.ch, jobscout24.ch, jobup.ch, swissdevjobs.ch), li salviamo in database locali per ciascun provider, quindi li mappiamo su uno schema comune e generiamo statistiche aggregate basate sul dataset combinato. Durante la fase di consolidamento usiamo la deduplicazione basata sull'identità dell'annuncio all'interno di ogni fonte, per evitare che importazioni duplicate gonfino le statistiche.

Successivamente, ogni annuncio viene normalizzato: azienda, località, cantone, seniority, modalità di lavoro e campi salariali vengono standardizzati, mentre categoria del ruolo, competenze, linguaggi di programmazione, framework/librerie e altri attributi analitici vengono estratti dal testo e dai campi strutturati. I salari, se disponibili, vengono convertiti in un formato annuale comparabile in CHF, così da poter calcolare sintesi e suddivisioni per ruolo e seniority.

Dopo questa fase, agenzie e intermediari di reclutamento vengono esclusi dal campione complessivo. Questo è importante: nelle nostre statistiche pubbliche vogliamo monitorare specificamente il mercato diretto del lavoro, non l'attività degli intermediari, che possono ripubblicare più volte posizioni simili e distorcere il quadro della domanda. Le eccezioni sono gestite sulla base di una lista normalizzata di società di collocamento/reclutamento note e dei loro alias.

Gli annunci vengono inoltre analizzati con l'IA: i filtri software standard spesso non riescono a riconoscere tutte le informazioni rilevanti e possono trascurare dettagli importanti. L'IA non sostituisce questi filtri e non inventa dati, ma lavora insieme a essi per fornire un'analisi più approfondita e accurata.
