#!/usr/bin/env bash
#
# Sets up (or updates) AvianAcoustics on a fresh Ubuntu 24.04 server:
# PostgreSQL, the FastAPI backend with BirdNET, database migrations,
# the React frontend, and Caddy in front of both.
#
#   https://<domain>/         web app (static build)
#   https://<domain>/api/...  backend API (Let's Encrypt certificate,
#                             obtained and renewed by Caddy)
#   http://<server>:8000      plain HTTP for the field devices, limited
#                             to POST /api/v1/recordings and /health
#
# The backend itself listens on 127.0.0.1 only.
#
# Run on the server as a sudo-capable user (the domain is remembered,
# so later runs can omit it):
#
#     sudo bash setup_server.sh avianacoustics.indonesiacentral.cloudapp.azure.com
#
# Safe to re-run: it pulls the latest code from GitHub, reinstalls
# dependencies, applies new migrations, rebuilds the frontend and
# restarts the services. Secrets generated on the first run are kept
# in /opt/birdcall/app/backend/.env and reused.

set -euo pipefail

REPO_URL="https://github.com/Harshana1004/birdcall-monitoring-system.git"
BRANCH="main"

APP_USER="birdcall"
APP_HOME="/opt/birdcall"
APP_DIR="${APP_HOME}/app"
VENV_DIR="${APP_HOME}/venv"
ENV_FILE="${APP_DIR}/backend/.env"

DB_NAME="birdcall_db"
DB_USER="birdcall_user"
SERVICE="birdcall-backend"
BACKEND_PORT=8001   # uvicorn, loopback only
DEVICE_PORT=8000    # Caddy, plain HTTP for devices

WEB_ROOT="/var/www/avianacoustics"
DOMAIN_FILE="${APP_HOME}/domain"
NODE_MAJOR=22

DEVICE_CODE="ESP32-DEV-01"

log() { printf '\n==> %s\n' "$*"; }

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0 <domain>" >&2
  exit 1
fi

DOMAIN="${1:-}"
if [[ -z "${DOMAIN}" && -f "${DOMAIN_FILE}" ]]; then
  DOMAIN="$(cat "${DOMAIN_FILE}")"
fi
if [[ -z "${DOMAIN}" ]]; then
  echo "Usage: sudo bash $0 <domain>   (e.g. avianacoustics.indonesiacentral.cloudapp.azure.com)" >&2
  exit 1
fi

# ------------------------------------------------------------
log "Installing system packages"
# ------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y \
  git curl openssl gnupg ca-certificates \
  python3 python3-venv python3-dev build-essential \
  postgresql postgresql-contrib \
  libsndfile1 ffmpeg \
  ufw unattended-upgrades

# Automatic security updates.
dpkg-reconfigure -f noninteractive unattended-upgrades

# ------------------------------------------------------------
log "Ensuring swap space (BirdNET/TensorFlow memory peaks)"
# ------------------------------------------------------------
if ! swapon --show | grep -q '/swapfile'; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ------------------------------------------------------------
log "Creating service user and fetching code"
# ------------------------------------------------------------
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "${APP_HOME}" --shell /usr/sbin/nologin "${APP_USER}"
fi

echo "${DOMAIN}" > "${DOMAIN_FILE}"

if [[ -d "${APP_DIR}/.git" ]]; then
  sudo -u "${APP_USER}" git -C "${APP_DIR}" fetch --quiet origin "${BRANCH}"
  sudo -u "${APP_USER}" git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
else
  sudo -u "${APP_USER}" git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

# ------------------------------------------------------------
log "Configuring PostgreSQL"
# ------------------------------------------------------------
systemctl enable --now postgresql

# Reuse the password from an existing .env, otherwise generate one.
DB_PASSWORD=""
if [[ -f "${ENV_FILE}" ]]; then
  DB_PASSWORD="$(sed -n "s|^DATABASE_URL=postgresql+asyncpg://${DB_USER}:\([^@]*\)@.*|\1|p" "${ENV_FILE}")"
fi
if [[ -z "${DB_PASSWORD}" ]]; then
  DB_PASSWORD="$(openssl rand -hex 24)"
fi

# Device API key (X-Device-Key) for ROI uploads: keep an existing one
# so deployed devices keep working, otherwise generate one.
DEVICE_API_KEY=""
if [[ -f "${ENV_FILE}" ]]; then
  DEVICE_API_KEY="$(sed -n 's|^DEVICE_API_KEY=\(.*\)$|\1|p' "${ENV_FILE}")"
fi
if [[ -z "${DEVICE_API_KEY}" ]]; then
  DEVICE_API_KEY="$(openssl rand -hex 32)"
fi

# Signing key for user login tokens: keep it so users stay signed in
# across redeploys, otherwise generate one.
JWT_SECRET_KEY=""
if [[ -f "${ENV_FILE}" ]]; then
  JWT_SECRET_KEY="$(sed -n 's|^JWT_SECRET_KEY=\(.*\)$|\1|p' "${ENV_FILE}")"
fi
if [[ -z "${JWT_SECRET_KEY}" ]]; then
  JWT_SECRET_KEY="$(openssl rand -hex 48)"
fi

if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1; then
  sudo -u postgres psql -q -c "ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}';"
else
  sudo -u postgres psql -q -c "CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}';"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  sudo -u postgres createdb -O "${DB_USER}" "${DB_NAME}"
fi

# ------------------------------------------------------------
log "Writing backend configuration (${ENV_FILE})"
# ------------------------------------------------------------
cat > "${ENV_FILE}" <<EOF
APP_NAME=BirdCall Monitoring Backend
APP_VERSION=0.1.0
APP_ENVIRONMENT=production
DEBUG=false

DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}

DEVICE_API_KEY=${DEVICE_API_KEY}
JWT_SECRET_KEY=${JWT_SECRET_KEY}
ACCESS_TOKEN_EXPIRE_MINUTES=720

ALLOWED_AUDIO_EXTENSIONS=wav

BIRDNET_MODEL_NAME=BirdNET
BIRDNET_MODEL_VERSION=2.4
BIRDNET_BACKEND=tf
BIRDNET_MIN_CONFIDENCE=0.25
BIRDNET_MAX_PREDICTIONS_PER_INTERVAL=10
BIRDNET_MODEL_LOADING_TIMEOUT_SECONDS=120

DEFAULT_TIMEZONE=Asia/Colombo
CORS_ORIGINS=["https://${DOMAIN}","http://localhost:5173"]

ROI_DURATION_TOLERANCE_SECONDS=0.25
MAX_ROI_DURATION_SECONDS=30.0
MAX_EDGE_METADATA_SIZE_BYTES=8192
EOF
chown "${APP_USER}:${APP_USER}" "${ENV_FILE}"
chmod 600 "${ENV_FILE}"

# ------------------------------------------------------------
log "Installing Python dependencies (TensorFlow is large; this takes a few minutes)"
# ------------------------------------------------------------
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  sudo -u "${APP_USER}" python3 -m venv "${VENV_DIR}"
fi
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --quiet --upgrade pip wheel
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --quiet -r "${APP_DIR}/backend/requirements.txt"
# The async engine needs greenlet, which newer SQLAlchemy only pulls in
# via the [asyncio] extra. Install it explicitly in case the
# requirements on GitHub predate that fix.
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --quiet "sqlalchemy[asyncio]"

# ------------------------------------------------------------
log "Applying database migrations"
# ------------------------------------------------------------
( cd "${APP_DIR}/database" && sudo -u "${APP_USER}" "${VENV_DIR}/bin/alembic" upgrade head )

# ------------------------------------------------------------
log "Installing systemd service (${SERVICE})"
# ------------------------------------------------------------
cat > "/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=AvianAcoustics backend (FastAPI + BirdNET)
After=network-online.target postgresql.service
Wants=network-online.target
Requires=postgresql.service

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}/backend
Environment=TF_CPP_MIN_LOG_LEVEL=2
ExecStart=${VENV_DIR}/bin/uvicorn src.server:app --host 127.0.0.1 --port ${BACKEND_PORT} --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable "${SERVICE}"
systemctl restart "${SERVICE}"

# ------------------------------------------------------------
log "Building the frontend"
# ------------------------------------------------------------
# Vite 8 needs Node 20.19+/22.12+; Ubuntu 24.04 ships 18.
if ! node -e 'process.exit(+process.versions.node.split(".")[0] >= 22 ? 0 : 1)' 2>/dev/null; then
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
  apt-get install -y nodejs
fi

FRONTEND_DIR="${APP_DIR}/frontend"
( cd "${FRONTEND_DIR}" && sudo -u "${APP_USER}" npm ci --no-audit --no-fund )
# Empty base URL: the API is served from the same origin under /api.
( cd "${FRONTEND_DIR}" && sudo -u "${APP_USER}" env VITE_API_BASE_URL="" npm run build )
if grep -rqs "127.0.0.1:8000" "${FRONTEND_DIR}/dist"; then
  echo "Frontend build still points at the development API; aborting." >&2
  exit 1
fi

# Caddy cannot read inside ${APP_HOME}; serve a copy from /var/www.
rm -rf "${WEB_ROOT}.new"
cp -r "${FRONTEND_DIR}/dist" "${WEB_ROOT}.new"
chmod -R a+rX "${WEB_ROOT}.new"
rm -rf "${WEB_ROOT}"
mv "${WEB_ROOT}.new" "${WEB_ROOT}"

# ------------------------------------------------------------
log "Installing and configuring Caddy (HTTPS for ${DOMAIN})"
# ------------------------------------------------------------
if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
fi

cat > /etc/caddy/Caddyfile <<EOF
# Managed by deploy/setup_server.sh -- edits are overwritten.

${DOMAIN} {
	encode zstd gzip

	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options nosniff
		Referrer-Policy strict-origin-when-cross-origin
		-Server
	}

	@backend path /api/* /health /ready /docs /redoc /openapi.json
	handle @backend {
		reverse_proxy 127.0.0.1:${BACKEND_PORT}
	}

	# Single-page app: unknown paths fall back to index.html.
	handle {
		root * ${WEB_ROOT}
		try_files {path} /index.html
		file_server
	}

	@hashed path /assets/*
	header @hashed Cache-Control "public, max-age=31536000, immutable"
	@html path / /index.html
	header @html Cache-Control "no-cache"
}

# Field devices: plain HTTP (no TLS on the modem yet), upload and
# health check only. Everything else stays behind HTTPS.
http://:${DEVICE_PORT} {
	@upload {
		method POST
		path /api/v1/recordings
	}
	handle @upload {
		reverse_proxy 127.0.0.1:${BACKEND_PORT}
	}
	handle /health {
		reverse_proxy 127.0.0.1:${BACKEND_PORT}
	}
	handle {
		respond 404
	}
}
EOF
caddy fmt --overwrite /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl enable caddy
# Restart rather than reload, so port 8000 (freed by the old
# 0.0.0.0:8000 backend on the first run) is bound cleanly.
systemctl restart caddy

# ------------------------------------------------------------
log "Configuring firewall (SSH, HTTP/HTTPS and device port ${DEVICE_PORT})"
# ------------------------------------------------------------
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow "${DEVICE_PORT}/tcp"
ufw --force enable

# ------------------------------------------------------------
log "Waiting for the backend to come up"
# ------------------------------------------------------------
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/ready" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -fsS "http://127.0.0.1:${BACKEND_PORT}/ready" && echo

# ------------------------------------------------------------
log "Registering device ${DEVICE_CODE}"
# ------------------------------------------------------------
# Creating devices through the API needs an admin login, so the row is
# ensured directly. It starts without owner or claim code: sign in as
# the admin and use "Regenerate claim code" to hand it out.
psql_app() { sudo -u postgres psql -d "${DB_NAME}" -v ON_ERROR_STOP=1 -tAq "$@"; }
DEVICE_ID="$(psql_app -c "SELECT id FROM devices WHERE device_code = '${DEVICE_CODE}';")"
if [[ -z "${DEVICE_ID}" ]]; then
  DEVICE_ID="$(psql_app -c "
    INSERT INTO devices (id, device_code, name, description, is_active, created_at, updated_at)
    VALUES (gen_random_uuid(), '${DEVICE_CODE}', 'ESP32-S3 field device',
            'ESP32-S3-DevKitC-1 (N16R8) + INMP441 + SIMA7670C 4G', true, now(), now())
    RETURNING id;" | head -n 1)"
fi

PUBLIC_IP="$(curl -fsS -4 https://api.ipify.org 2>/dev/null || echo '<this server public IP>')"

# ------------------------------------------------------------
log "Checking public endpoints"
# ------------------------------------------------------------
# Caddy obtains the certificate in the background; give it a minute.
HTTPS_OK=0
for _ in $(seq 1 20); do
  if curl -fsS --max-time 10 "https://${DOMAIN}/health" >/dev/null 2>&1; then
    HTTPS_OK=1
    break
  fi
  sleep 3
done
if [[ "${HTTPS_OK}" -eq 1 ]]; then
  echo "https://${DOMAIN}/health OK"
else
  echo "WARNING: https://${DOMAIN} is not answering yet. Check that the DNS"
  echo "         name resolves to ${PUBLIC_IP}, that the Azure NSG allows"
  echo "         ports 80 and 443, and the log: sudo journalctl -u caddy -n 50"
fi
if curl -fsS --max-time 10 "http://127.0.0.1:${DEVICE_PORT}/health" >/dev/null 2>&1; then
  echo "Device port ${DEVICE_PORT} OK"
else
  echo "WARNING: device port ${DEVICE_PORT} is not answering."
fi

cat <<EOF

============================================================
 AvianAcoustics is running.

   Web app : https://${DOMAIN}
   API docs: https://${DOMAIN}/docs
   Backend : sudo systemctl status ${SERVICE}   (logs: sudo journalctl -u ${SERVICE} -f)
   Proxy   : sudo systemctl status caddy        (logs: sudo journalctl -u caddy -f)

 The first account registered in the web app becomes the admin.

 Firmware settings (firmware/birdcall_device/include/config.h):

   BACKEND_HOST = "${PUBLIC_IP}"
   BACKEND_PORT = ${DEVICE_PORT}
   DEVICE_ID    = "${DEVICE_ID}"   // ${DEVICE_CODE}

 Device API key (firmware/birdcall_device/include/secrets.h --
 git-ignored, never commit it):

   DEVICE_API_KEY = "${DEVICE_API_KEY}"
============================================================
EOF

# Warn if the deployed backend predates the key check.
if ! grep -q "require_device_key" "${APP_DIR}/backend/src/api/recordings.py"; then
  echo
  echo "WARNING: the backend code on GitHub does not check DEVICE_API_KEY yet."
  echo "         Push the API-key change and run this script again."
fi
