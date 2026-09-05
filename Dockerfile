# PyBlog - minimal Docker image.
# No dependencies to install: only Python is needed.
#
# Build:  docker build -t pyblog .
# Run:    docker run -p 8000:8000 -v $(pwd)/data:/app pyblog
# (or, more conveniently: docker compose up)

FROM python:3.12-slim

WORKDIR /app

# We only copy what's strictly needed: the entry point, the engine, the
# templates and the CSS/JS sources. If you mount a volume on /app
# (recommended, see docker-compose.yml), these files get overwritten by yours.
COPY pyblog.py .
COPY core/ ./core/
COPY templates/ ./templates/
COPY static/ ./static/

EXPOSE 8000

# Inside the container the server MUST listen on 0.0.0.0, otherwise it
# would be unreachable from outside the container itself.
# Port 8000 should still be exposed only to localhost or behind a
# reverse proxy with HTTPS (see nginx.conf.example and DEPLOY-REMOTO.md).
CMD ["python3", "pyblog.py", "serve", "8000", "0.0.0.0"]
