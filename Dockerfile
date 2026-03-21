FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Data directory for persistent SQLite DB
RUN mkdir -p /data && \
    # If betbrain.db exists at build time, copy it into /data as seed
    cp betbrain.db /data/seed.db 2>/dev/null || true

# Entrypoint: copy seed DB to volume mount if volume is empty, then start
CMD ["sh", "-c", "\
  if [ ! -f /data/betbrain.db ] && [ -f /data/seed.db ]; then \
    cp /data/seed.db /data/betbrain.db; \
  elif [ ! -f /data/betbrain.db ]; then \
    cp betbrain.db /data/betbrain.db 2>/dev/null || touch /data/betbrain.db; \
  fi && \
  ln -sf /data/betbrain.db /app/betbrain.db && \
  exec gunicorn --bind 0.0.0.0:5556 --workers 1 --timeout 600 dashboard.app:app \
"]

EXPOSE 5556
