/*
  Corpus similarity search (Stream D, Saachi): TF-IDF vectors + cosine
  similarity against the curated corpus. Logic moved here unchanged from
  App.jsx; rankMatches() returns the ranked list so the UI can show runners-up.
*/

export const CANDIDATE_LIMIT = 60;
export const HIGH_SIMILARITY = 0.7;
export const MODERATE_SIMILARITY = 0.4;

export function tokenize(text) {
  return String(text)
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((word) => word.length > 2);
}

function createTermCounts(tokens) {
  const counts = new Map();
  for (const token of tokens) {
    counts.set(token, (counts.get(token) || 0) + 1);
  }
  return counts;
}

export function prepareCorpus(corpus) {
  const documentFrequency = new Map();
  const documents = corpus.map((document) => {
    const tokens = tokenize(document.text);
    const counts = createTermCounts(tokens);
    const uniqueWords = new Set(counts.keys());
    for (const word of uniqueWords) {
      documentFrequency.set(word, (documentFrequency.get(word) || 0) + 1);
    }
    return { ...document, counts, tokenCount: tokens.length, uniqueWords };
  });
  return { documents, documentFrequency, totalDocuments: documents.length };
}

function getIdf(word, preparedCorpus) {
  const df = preparedCorpus.documentFrequency.get(word) || 0;
  return Math.log((preparedCorpus.totalDocuments + 1) / (df + 1)) + 1;
}

/* Cheap word-overlap prefilter so cosine similarity runs only on the most
   relevant candidates instead of the whole corpus. */
function getCandidateDocuments(inputText, preparedCorpus) {
  const inputWords = new Set(tokenize(inputText));
  return preparedCorpus.documents
    .map((document) => {
      let overlap = 0;
      for (const word of inputWords) {
        if (document.uniqueWords.has(word)) overlap++;
      }
      return { document, overlap };
    })
    .filter((item) => item.overlap > 0)
    .sort((a, b) => b.overlap - a.overlap)
    .slice(0, CANDIDATE_LIMIT)
    .map((item) => item.document);
}

function cosineSimilarity(inputCounts, inputTotal, document, preparedCorpus) {
  const documentTotal = document.tokenCount || 1;
  let dot = 0;
  let inputMag = 0;
  let documentMag = 0;
  const allWords = new Set([...inputCounts.keys(), ...document.counts.keys()]);

  for (const word of allWords) {
    const idf = getIdf(word, preparedCorpus);
    const inputValue = ((inputCounts.get(word) || 0) / inputTotal) * idf;
    const documentValue = ((document.counts.get(word) || 0) / documentTotal) * idf;
    dot += inputValue * documentValue;
    inputMag += inputValue * inputValue;
    documentMag += documentValue * documentValue;
  }

  if (inputMag === 0 || documentMag === 0) return 0;
  return dot / (Math.sqrt(inputMag) * Math.sqrt(documentMag));
}

export function classify(score) {
  if (score >= HIGH_SIMILARITY) return "High similarity";
  if (score >= MODERATE_SIMILARITY) return "Moderate similarity";
  return "Low similarity";
}

export function rankMatches(inputText, preparedCorpus, limit = 5) {
  const inputTokens = tokenize(inputText);
  const inputCounts = createTermCounts(inputTokens);
  const inputTotal = inputTokens.length || 1;
  const candidates = getCandidateDocuments(inputText, preparedCorpus);

  return {
    candidatesScored: candidates.length,
    matches: candidates
      .map((document) => ({
        document,
        score: cosineSimilarity(inputCounts, inputTotal, document, preparedCorpus),
      }))
      .filter((match) => match.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, limit),
  };
}
