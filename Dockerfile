# The bfsi-curate command, with its dependencies, for people who only want to run it.
#
#   docker build -t bfsi-curate .
#   docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/data" bfsi-curate run /data/pdfs -o /data/out
#
# CPU only: the default pipeline needs no GPU. The optional GLiNER and DeBERTa models are not in this image.
FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /src
COPY pyproject.toml README.md ./
COPY pipeline ./pipeline
RUN pip install . && rm -rf /src

# Run as an ordinary user. /data is where the caller mounts their PDFs and receives the output.
RUN useradd --create-home --uid 1000 curator && mkdir /data && chown curator /data
USER curator
WORKDIR /data

ENTRYPOINT ["bfsi-curate"]
CMD ["--help"]
