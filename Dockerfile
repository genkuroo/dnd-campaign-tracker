# D&D Campaign Tracker — production image (served by gunicorn on Fly.io).
FROM python:3.12-slim

# Don't buffer stdout/stderr (so logs show up live) or write .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first so this layer caches across code-only changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY . .

# The Fly volume mounts at /data and holds the SQLite DB + uploaded avatars.
# Symlink the static avatars dir onto the volume so uploads persist across
# deploys and existing /static/avatars/... URLs keep working unchanged. The
# target is created on demand (os.makedirs) when the first avatar is uploaded.
RUN rm -rf static/avatars && ln -s /data/avatars static/avatars
RUN rm -rf static/maps && ln -s /data/maps static/maps

EXPOSE 8080

# gunicorn serves the WSGI app. --preload imports the app once in the master
# (running init_db migrations exactly once) before forking workers, avoiding a
# migration race on first boot. 2 workers is ample for a small group and keeps
# SQLite write contention low; threads add light I/O concurrency.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", \
     "--timeout", "60", "--preload", "app:app"]
