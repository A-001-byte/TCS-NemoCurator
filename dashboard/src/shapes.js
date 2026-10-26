/* What each optional snapshot file must look like for its panel to show; anything else hides the panel. */

export const isSummary = (data) => Boolean(data) && Array.isArray(data.stages) && data.stages.length > 0;

export const isDocTypeReport = (data) =>
  Boolean(data) &&
  Array.isArray(data.per_document) &&
  Array.isArray(data.per_type) &&
  typeof data.accuracy?.by_family === "number" &&
  typeof data.caption === "string";

export const isTokenReport = (data) =>
  Boolean(data) &&
  Array.isArray(data.per_document) &&
  typeof data.total_tokens === "number" &&
  typeof data.tokenizer === "string";
