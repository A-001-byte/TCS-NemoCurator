import {
  LayoutDashboard,
  Workflow,
  Library,
  ShieldCheck,
  Files,
  Search,
  Upload,
  Scale,
  Tags,
  Hash,
} from "lucide-react";

/* `optional` sections appear only when their snapshot file loads (see buildSections). */
export const ALL_SECTIONS = [
  { id: "overview", title: "Overview", icon: LayoutDashboard },
  { id: "pipeline", title: "Pipeline", icon: Workflow },
  { id: "corpus", title: "Corpus quality", icon: Library },
  { id: "tokens", title: "Token statistics", icon: Hash, optional: "tokens" },
  { id: "nemo", title: "NeMo comparison", icon: Scale },
  { id: "doctypes", title: "Document types", icon: Tags, optional: "doctypes" },
  { id: "pii", title: "PII redaction", icon: ShieldCheck },
  { id: "documents", title: "Source documents", icon: Files },
  { id: "search", title: "Similarity search", icon: Search },
  { id: "run", title: "Process documents", icon: Upload },
];

export const buildSections = (available) => ALL_SECTIONS.filter((s) => !s.optional || available[s.optional]);
