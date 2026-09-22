FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt requirements-llm.txt ./
ARG INSTALL_LLM=false
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_LLM" = "true" ]; then pip install --no-cache-dir -r requirements-llm.txt; fi

COPY backend ./backend
COPY web ./web
COPY mock ./mock
COPY prompts ./prompts
COPY policy.yaml ./policy.yaml

RUN useradd -m app && mkdir -p /data && chown app /data
USER app

ENV DB_PATH=/data/accessbell.db \
    MOCK_MODE=true \
    LLM_PROVIDER=stub

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4)"

CMD ["python", "-m", "backend"]