# ---- Stage 1: build the React frontend ----
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# Empty API URL = the browser calls the same server that served the page.
ENV VITE_API_BASE_URL=""
RUN npm run build

# ---- Stage 2: Python backend that also serves the built frontend ----
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs containers as user id 1000.
RUN useradd -m -u 1000 appuser
WORKDIR /app

# CPU-only torch keeps the image much smaller than the default CUDA build.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY data/ ./data/
COPY --from=frontend /frontend/dist ./frontend/dist
RUN chown -R appuser:appuser /app
USER appuser

ENV HF_HOME=/app/data/hf_cache
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
