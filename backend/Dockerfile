FROM python:3.12.9-slim

WORKDIR /app

# Install system dependencies for ICMP probes and tc netem chaos
RUN apt-get update -qq \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
       iputils-ping iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Install production Python dependencies (dev deps are in requirements-dev.txt)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# NOTE: Container runs as root because the chaos lab feature requires NET_ADMIN
# capability for tc netem traffic control. In a production deployment without
# chaos, remove cap_add and switch to a non-root user.
#   RUN useradd --create-home netpulse && chown -R netpulse:netpulse /app
#   USER netpulse

# ── Chaos feature note ──────────────────────────────────────────────
# [LEGACY/LAB] Node chaos, and [V2/LAB] tc-netem network chaos operate
# exclusively inside the container's network namespace. Host networking is
# never touched. Both features are visually separated in the dashboard.
#
# Without chaos, the container can run as a non-root user by uncommenting
# the USER directive above and removing cap_add from docker-compose.yml.

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

EXPOSE 8000

# Separate migration and server start. In production, run migrations as a release step
# before starting new containers. For this single-VM demo, run both on startup.
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
