FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    PORT=8080

WORKDIR /app

RUN groupadd --system spklu \
    && useradd --system --gid spklu --home-dir /app spklu

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY --chown=spklu:spklu . .
RUN mkdir -p /app/reports/generated \
    && chown -R spklu:spklu /app/reports

USER spklu

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"

CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
