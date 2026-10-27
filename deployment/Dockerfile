FROM python:3.12-slim
WORKDIR /app
COPY requirements-runtime.lock ./
# Optional wheel mirror for offline/restricted-network builds.
ARG PIP_FIND_LINKS
ARG PIP_NO_INDEX
RUN pip install --no-cache-dir -r requirements-runtime.lock
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps . && useradd --create-home twinguard
USER twinguard
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "twinguard.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
