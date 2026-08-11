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

EXPOSE 8501

# Healthcheck über Python (curl ist im slim-Image nicht vorhanden).
# WICHTIG: 127.0.0.1 statt localhost — localhost löst im Container auch auf IPv6 (::1)
# auf; Streamlit lauscht nur auf IPv4 → localhost kann je nach Client fehlschlagen.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health').read()==b'ok' else 1)" || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
