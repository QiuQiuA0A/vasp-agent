FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/

ENV VASP_API_KEY=""
ENV CORS_ORIGINS="*"
ENV ALLOWED_HOSTS="*"
ENV VASP_POTCAR_LIBRARY=/potcar
ENV VASP_MAX_UPLOAD_MB=50

VOLUME ["/potcar"]

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
