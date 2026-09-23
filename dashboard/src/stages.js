/*
  Explanatory copy for each pipeline stage, removal reason and PII entity type.
  Every number on the page comes from pipeline_summary.json / curated.jsonl;
  this file only explains what those keys mean.
*/
import {
  FileText,
  Sparkles,
  Copy,
  Filter,
  ShieldCheck,
  PackageCheck,
} from "lucide-react";

export const STAGES = {
  extract: {
    title: "PDF extraction",
    icon: FileText,
    unit: "PDFs",
    summary: "Pulls the text layer out of every source PDF.",
    detail:
      "Each RBI circular, FIU-IND guideline and bank KYC/AML policy is opened with pdfplumber and its text is read page by page. A PDF with no text layer (a scanned image) produces nothing and is dropped here, since recovering it would need OCR.",
  },
  clean_langid: {
    title: "Cleaning and language ID",
    icon: Sparkles,
    unit: "documents",
    summary: "Normalises text and keeps only substantive English documents.",
    detail:
      "Strips control characters and bare page-number lines, collapses whitespace, then runs language detection on each document. Documents that are too short to be useful or not in English are removed before any chunking happens.",
  },
  dedup: {
    title: "Deduplication",
    icon: Copy,
    unit: "chunks",
    summary: "Splits documents into chunks, then removes exact and near duplicates.",
    detail:
      "Documents are split into fixed-size word windows. Exact copies are caught with SHA-256 hashes; near copies with MinHash + LSH over 5-word shingles. Near duplicates are then classified: the same regulatory clause copied across different banks' policies is counted as cross-document boilerplate, while repetition inside one PDF (running headers, repeated tables) is counted as intra-document noise.",
  },
  quality_filter: {
    title: "Quality filtering",
    icon: Filter,
    unit: "chunks",
    summary: "Drops noisy chunks and tags regulatory content.",
    detail:
      "Heuristic filters remove chunks that are mostly numbers or symbols, too short, or highly repetitive. Surviving chunks are tagged with the BFSI regulatory terms they contain (KYC, AML, CDD, PEP, STR and others) and a density score, so training can weight substantive regulatory text over passing mentions.",
  },
  pii_redact: {
    title: "PII redaction",
    icon: ShieldCheck,
    unit: "chunks",
    summary: "Replaces personal and institutional identifiers with typed placeholders.",
    detail:
      "Runs after deduplication, never before, because dedup depends on stable content hashes. Pattern matchers find PAN, Aadhaar, email, phone, PIN code, date, CIN, SWIFT/BIC and account numbers; spaCy NER finds person names next to a personal title such as “Mr.” or “Name:”. Ambiguous matches are checked against surrounding context: a digit run next to “Fax” or “Tel” is kept as a phone number, and a SWIFT-shaped word is redacted only when a SWIFT/BIC label is nearby.",
  },
  output: {
    title: "JSONL output",
    icon: PackageCheck,
    unit: "chunks",
    summary: "Writes the fine-tuning-ready corpus.",
    detail:
      "Each surviving chunk is written as one JSON line containing its text and metadata: source file, chunk ID, whether PII was redacted, and its regulatory tags and density score.",
  },
};

export const REASONS = {
  extraction_failed: "No text layer (scanned PDF)",
  too_short: "Too short",
  non_english: "Not English",
  exact_duplicate: "Exact duplicate",
  cross_doc_boilerplate: "Cross-document boilerplate",
  intra_doc_near_duplicate: "Near duplicate within a document",
  too_few_words: "Too few words",
  low_alpha_ratio: "Mostly numbers or symbols",
  high_symbol_ratio: "Too many symbols",
  low_lexical_diversity: "Highly repetitive text",
  low_quality_classifier: "Rejected by quality classifier",
};

export const ENTITIES = {
  PINCODE: { label: "PIN code", note: "Six-digit Indian postal code" },
  EMAIL: { label: "Email address", note: "Personal or officer email" },
  DATE: { label: "Date", note: "DD/MM/YYYY or DD-MM-YYYY" },
  PHONE: { label: "Phone number", note: "Indian mobile, with or without +91" },
  CIN: { label: "Corporate Identity Number", note: "21-character MCA company ID" },
  SWIFT_BIC: { label: "SWIFT / BIC code", note: "Redacted only when labelled" },
  PERSON_NAME: { label: "Person name", note: "spaCy NER, title-gated" },
  PAN: { label: "PAN", note: "Income-tax permanent account number" },
  AADHAAR: { label: "Aadhaar number", note: "12-digit UIDAI number" },
  ACCOUNT_NUMBER: { label: "Account number", note: "Only with banking context" },
  ACCOUNT_NUMBER_SUPPRESSED: {
    label: "Kept: phone or fax number",
    note: "Account-shaped, but context showed Fax/Tel",
  },
};

export function reasonLabel(key) {
  return REASONS[key] || key.replaceAll("_", " ");
}

export function entityLabel(key) {
  return ENTITIES[key]?.label || key.replaceAll("_", " ");
}
