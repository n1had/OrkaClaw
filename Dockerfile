# ── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build
# Output: /app/frontend/dist/


# ── Stage 2: Python backend ───────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy built frontend into backend/static/ so FastAPI can serve it
COPY --from=frontend-builder /app/frontend/dist ./backend/static/

WORKDIR /app/backend

EXPOSE 8000

# Azure App Service / Container Apps sets PORT env var — fall back to 8000
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
