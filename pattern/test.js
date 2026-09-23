import { findBestMatch } from "./matcher.js";

const corpus = [
  {
    source_file: "kyc_document_1.pdf",
    text: "Customer KYC verification includes PAN card, Aadhaar, address proof, customer identity and account details.",
  },
  {
    source_file: "kyc_document_2.pdf",
    text: "Bank customer verification requires identity proof, address proof, PAN details and account information.",
  },
  {
    source_file: "aml_document.pdf",
    text: "Suspicious transaction monitoring includes unusual transactions, beneficiary details, transaction amount and risk indicators.",
  },
];

const incomingDocument =
  "The customer submitted PAN details, identity proof, address proof and bank account information for KYC verification.";

const result = findBestMatch(incomingDocument, corpus);

console.log("=== Stream D Pattern Matching Test ===");
console.log("Classification:", result.classification);
console.log("Similarity:", result.similarity);
console.log(
  "Matched document:",
  result.matchedDocument?.source_file || "None"
);