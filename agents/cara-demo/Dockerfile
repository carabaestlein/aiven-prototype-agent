# Aiven Runtime uses the repository ROOT as build context.
# Local: docker build -f agents/cara-demo/Dockerfile .
FROM python:3.12.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
ENV LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false
WORKDIR /app
COPY agents/cara-demo/requirements.txt agents/cara-demo/constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt \
    && useradd --uid 10001 --create-home starter
COPY agents/cara-demo/app.py agents/cara-demo/settings.py agents/cara-demo/service.py agents/cara-demo/workflow.py agents/cara-demo/telemetry.py ./
COPY agents/cara-demo/static ./static
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=4)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--limit-concurrency", "20", "--timeout-graceful-shutdown", "60"]
