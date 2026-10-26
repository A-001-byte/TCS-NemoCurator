# Security and data handling

## Reporting a problem

Use GitHub's private vulnerability reporting (the repository's **Security** tab) if it is enabled. Otherwise open an
issue that describes the problem in general terms, **without exploit details or any personal data**, and a maintainer
will move the conversation to a private channel.

## What this software handles

It processes banking and KYC regulatory PDFs. The documents in `data/raw/` are public. Real customer documents should be
processed on the machine that holds them: the library and the command line need no network, and nothing is sent anywhere.

Network access happens only for the optional parts: the first use of the `tiktoken` encoding, the optional
GLiNER and DeBERTa models (downloaded from Hugging Face), and installing packages.

## Personal-data redaction: what it is and is not

- Redaction is **rule-based** (regular expressions with context checks, a checksum for Aadhaar numbers, and spaCy for
  person names). It reduces exposure; it is **not a guarantee** that every personal identifier is found.
- Person-name detection depends on the spaCy model `en_core_web_sm`. If it cannot load, names are **not** redacted;
  the CLI prints a warning, the run summary carries `name_detection_error`, and the dashboard shows an alert.
- On the public corpus, most redacted items are official contact details printed in public documents (government
  emails, office PIN codes). The pipeline redacts them anyway.
- The dashboard snapshots in `dashboard/public/` publish the **pipeline output** (already redacted) and PII examples
  whose original value is partly masked. `python -m pipeline.refresh_snapshots` refuses to publish if the curated output
  still contains data its own redactor would replace.

## The local API (`python -m pipeline.server`, `bfsi-curate serve`)

- It listens on `127.0.0.1` by default and has **no authentication**. A warning is logged if you bind a public address;
  do not expose it to an untrusted network.
- Uploads are limited to 10 PDFs and 30 MB per request, must start with `%PDF`, and file names are stripped of any folder
  part. Every run happens in its own temporary folder.
- One run at a time: a second upload during a run or a refresh is answered with `409`.

## Repository hygiene

No secrets are used or stored by this project. `.env` files are ignored by Git. Never commit personal data, access
tokens or local paths; CI and `tests/test_refresh.py` check the published snapshots for leaked identifiers and paths.
