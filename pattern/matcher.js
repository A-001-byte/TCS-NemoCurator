function tokenize(text) {
  return String(text)
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((word) => word.length > 2);
}

function termFrequency(tokens) {
  const counts = {};

  for (const token of tokens) {
    counts[token] = (counts[token] || 0) + 1;
  }

  const total = tokens.length || 1;

  for (const token of Object.keys(counts)) {
    counts[token] = counts[token] / total;
  }

  return counts;
}

function buildVocabulary(documents) {
  const vocabulary = new Set();

  for (const document of documents) {
    const text =
      typeof document === "string"
        ? document
        : document.text;

    for (const token of tokenize(text)) {
      vocabulary.add(token);
    }
  }

  return [...vocabulary];
}

function inverseDocumentFrequency(documents, vocabulary) {
  const idf = {};

  for (const word of vocabulary) {
    let documentCount = 0;

    for (const document of documents) {
      const text =
        typeof document === "string"
          ? document
          : document.text;

      const tokens = new Set(tokenize(text));

      if (tokens.has(word)) {
        documentCount++;
      }
    }

    idf[word] =
      Math.log(
        (documents.length + 1) /
        (documentCount + 1)
      ) + 1;
  }

  return idf;
}

function vectorize(text, vocabulary, idf) {
  const tokens = tokenize(text);
  const tf = termFrequency(tokens);

  return vocabulary.map(
    (word) => (tf[word] || 0) * idf[word]
  );
}

function cosineSimilarity(vectorA, vectorB) {
  let dotProduct = 0;
  let magnitudeA = 0;
  let magnitudeB = 0;

  for (let i = 0; i < vectorA.length; i++) {
    dotProduct += vectorA[i] * vectorB[i];
    magnitudeA += vectorA[i] ** 2;
    magnitudeB += vectorB[i] ** 2;
  }

  if (magnitudeA === 0 || magnitudeB === 0) {
    return 0;
  }

  return (
    dotProduct /
    (Math.sqrt(magnitudeA) *
      Math.sqrt(magnitudeB))
  );
}

export function findBestMatch(inputDocument, corpus) {
  if (!corpus || corpus.length === 0) {
    return {
      classification: "No Match",
      similarity: 0,
      matchedDocument: null,
    };
  }

  const allDocuments = [
    ...corpus,
    inputDocument,
  ];

  const vocabulary = buildVocabulary(allDocuments);

  const idf = inverseDocumentFrequency(
    allDocuments,
    vocabulary
  );

  const inputVector = vectorize(
    inputDocument,
    vocabulary,
    idf
  );

  let bestMatch = null;
  let bestScore = 0;

  corpus.forEach((document, index) => {
    const documentVector = vectorize(
      document.text,
      vocabulary,
      idf
    );

    const score = cosineSimilarity(
      inputVector,
      documentVector
    );

    if (score > bestScore) {
      bestScore = score;

      bestMatch = {
        ...document,
        similarity: score,
        index,
      };
    }
  });

  let classification = "Low Similarity";

  if (bestScore >= 0.7) {
    classification = "High Similarity";
  } else if (bestScore >= 0.4) {
    classification = "Moderate Similarity";
  }

  return {
    classification,
    similarity: Number(bestScore.toFixed(3)),
    matchedDocument: bestMatch,
  };
}