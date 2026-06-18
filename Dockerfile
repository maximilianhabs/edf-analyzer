# MNE läuft stabil auf 3.9 — bewusste Wahl gegen FSL-Python 3.12
FROM python:3.9-slim-bookworm

# Systemlibs für MNE (OpenBLAS/scipy) und ReportLab (Fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        libopenblas-dev \
        libfreetype6 \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies zuerst (besseres Layer-Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App-Code
COPY . .

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false", \
     "--server.maxUploadSize=200"]
