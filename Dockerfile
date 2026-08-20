ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    PORT=8080

WORKDIR /app

RUN groupadd --system spklu \
    && useradd --system --gid spklu --home-dir /app spklu

COPY requirements.txt constraints.txt ./
RUN python -m pip install --no-cache-dir \
    -r requirements.txt \
    -c constraints.txt

# Source dan dataset tetap dimiliki root serta hanya dapat dibaca user runtime.
# Hanya ledger/laporan yang memerlukan direktori tulis khusus.
COPY . .
RUN install -d -o spklu -g spklu -m 0750 /app/reports/generated

USER spklu

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"

CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
