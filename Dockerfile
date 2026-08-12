# MNE läuft stabil auf 3.9 — bewusste Wahl gegen FSL-Python 3.12
FROM python:3.9-slim-bookworm

# Systemlibs für MNE (OpenBLAS/scipy) und ReportLab (Fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        libopenblas-dev \
        libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Verhindert BLAS-Thread-Oversubscription: mehrere gleichzeitige Streamlit-Sessions
# rufen sonst je einen eigenen MNE/SciPy-Filter auf, der wiederum standardmäßig alle
# Host-Kerne für sich beansprucht (OpenBLAS/OpenMP) — das überlastet den VPS bei
# paralleler Nutzung deutlich schneller, als die Rechenlast selbst rechtfertigt.
ENV OMP_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1
ENV MKL_NUM_THREADS=1

# Dependencies zuerst (besseres Layer-Caching)
COPY requirements.txt requirements-validated.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Optionale, GPL-3.0-lizenzierte Zusatz-Detektoren (py-ecg-detectors). Standardmäßig NICHT
# im Image: ein weitergegebenes Image ist eine Weiterverbreitung, und die soll nicht
# ungefragt Copyleft-Code enthalten. Bewusst dazuholen mit:
#     docker build --build-arg WITH_VALIDATED_DETECTORS=1 -t edf-analyzer .
# Ohne sie läuft die App vollständig; es entfallen nur die Vergleichsdetektoren, und die
# Oberfläche weist das ausdrücklich aus (siehe requirements-validated.txt).
ARG WITH_VALIDATED_DETECTORS=0
RUN if [ "$WITH_VALIDATED_DETECTORS" = "1" ]; then \
        pip install --no-cache-dir -r requirements-validated.txt; \
    fi

# App-Code
COPY . .

# Herkunft im Report: `.dockerignore` schliesst `.git/` aus, im Image gibt es also kein
# Repository, aus dem sich der Commit lesen liesse. Er wird deshalb beim Bauen hereingereicht:
#     docker build --build-arg EDF_BUILD_COMMIT=$(git rev-parse --short HEAD) -t edf-analyzer .
# Fehlt er, steht im Report ausdruecklich "unbekannt" statt einer erfundenen Angabe.
ARG EDF_BUILD_COMMIT=""
ENV EDF_BUILD_COMMIT=$EDF_BUILD_COMMIT

# Nicht als root laufen. Der Container verarbeitet hochgeladene Fremddateien mit einem
# umfangreichen Parser-Stack (MNE, pyedflib, ReportLab) — es gibt keinen Grund, dem
# root-Rechte zu geben. Streamlit braucht ein beschreibbares HOME (Konfiguration, Cache) und
# ein beschreibbares Temp-Verzeichnis (dort liegen die Sitzungs-Uploads, siehe
# core/cleanup.py, das sie nach spätestens ~4 h löscht).
RUN useradd --create-home --uid 10001 edf \
    && chown -R edf:edf /app
USER edf
ENV HOME=/home/edf

EXPOSE 8501

# Healthcheck über Python (curl ist im slim-Image nicht vorhanden).
# WICHTIG: 127.0.0.1 statt localhost — localhost löst im Container auch auf IPv6 (::1)
# auf; Streamlit lauscht nur auf IPv4 → localhost kann je nach Client fehlschlagen.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health').read()==b'ok' else 1)" || exit 1

# Betriebshinweis — Ressourcengrenzen gehören an den Start, nicht ins Image:
#     docker run --memory=2g --cpus=2 --read-only \
#                --tmpfs /tmp:rw,size=1g --tmpfs /home/edf:rw,size=64m \
#                -e EDF_PASSWORD=… edf-analyzer
# Eine 200-MB-EDF wird von MNE vollständig in den Speicher geladen und als float64 gehalten;
# ohne Grenze kann eine einzelne große Datei den Host in den Swap ziehen. Das ist der
# realistische Fall — nicht ein Angreifer, sondern eine legitime lange Aufnahme.

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
