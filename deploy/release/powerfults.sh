#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
action=${1:-start}
case "$action" in start|stop|restart|logs|status|init) ;; *) echo "Usage: sh powerfults.sh [start|stop|restart|logs|status|init]" >&2; exit 2 ;; esac
export POWERFULTS_VERSION
POWERFULTS_VERSION=$(cat .release-version)
created_config=false
if [ ! -f backend.env ]; then
  (umask 077; cp backend.env.example backend.env)
  echo "Created backend.env. Set TS3 / TS6 and TSMusicBot connection settings, then restart."
  created_config=true
fi
mkdir -p data
if [ "$action" = init ]; then exit 0; fi
if [ "$created_config" = true ] && { [ "$action" = start ] || [ "$action" = restart ]; }; then
  echo "Edit backend.env, then run start again."
  exit 0
fi
command -v docker >/dev/null 2>&1 || { echo "Install Docker with Compose v2 first (see README.md)." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Start Docker Desktop / Docker Engine first; Linux containers are required." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2.20+ is required." >&2; exit 1; }
compose() { docker compose --project-directory "$PWD" -f compose.yml "$@"; }
start() {
  if [ -f images.tar ]; then
    machine=$(docker info --format '{{.Architecture}}')
    case "$machine" in x86_64|amd64) machine=amd64 ;; aarch64|arm64) machine=arm64 ;; esac
    expected=$(cat .release-arch)
    [ "$machine" = "$expected" ] || { echo "This archive is $expected, but Docker is $machine. Download the matching CPU archive." >&2; exit 1; }
    if ! docker image inspect "powerfults-backend:$POWERFULTS_VERSION" "powerfults-frontend:$POWERFULTS_VERSION" >/dev/null 2>&1; then
      docker load --input images.tar
    fi
    compose up -d --no-build --pull never --wait --wait-timeout 180
  else
    compose up -d --build --wait --wait-timeout 180
  fi
  echo "PowerfulTS is ready: http://localhost:${POWERFULTS_PORT:-8080}"
}
case "$action" in
  start) start ;;
  stop) compose down ;;
  restart) compose down; start ;;
  logs) compose logs -f --tail 100 ;;
  status) compose ps ;;
esac
