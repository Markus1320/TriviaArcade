#!/usr/bin/env bash
# Deploy main to the home server. Run from the repository root (Git Bash on Windows works).
#
# 1. Push main to GitHub and refuse to continue unless CI for that commit is green.
# 2. On the server: git pull, docker compose up -d --build, and run the importer if
#    config/import.yaml changed since the last successful deploy.
# 3. Check the backend health endpoint through Caddy.
#
# The server's .env and data/ folder are managed there and never touched by this script.
set -euo pipefail

SERVER="${DEPLOY_SERVER:-markus@arcade.local}"
SERVER_DIR="${DEPLOY_DIR:-/home/markus/TriviaArcade}"
REPO="Markus1320/TriviaArcade"

if [ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]; then
  echo "deploy: not on main" >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "deploy: working tree is not clean" >&2
  exit 1
fi

git push origin main
sha="$(git rev-parse HEAD)"

echo "deploy: waiting for CI on $sha"
for _ in $(seq 1 60); do
  state="$(curl -fsS "https://api.github.com/repos/$REPO/actions/runs?head_sha=$sha" |
    python -c "import json,sys
runs = json.load(sys.stdin)['workflow_runs']
print(' '.join(f\"{r['status']}:{r['conclusion']}\" for r in runs) or 'none')")"
  case "$state" in
    "completed:success") break ;;
    *completed:*) echo "deploy: CI is not green ($state), aborting" >&2; exit 1 ;;
  esac
  sleep 15
done
if [ "$state" != "completed:success" ]; then
  echo "deploy: CI did not finish in time ($state), aborting" >&2
  exit 1
fi

ssh -o BatchMode=yes "$SERVER" bash -s -- "$SERVER_DIR" "$sha" <<'REMOTE'
set -euo pipefail
cd "$1"
expected="$2"
marker=.git/last-deployed-commit

previous="$(cat "$marker" 2>/dev/null || git rev-parse HEAD)"
git pull --ff-only
if [ "$(git rev-parse HEAD)" != "$expected" ]; then
  echo "deploy: server is at $(git rev-parse HEAD), expected $expected" >&2
  exit 1
fi

docker compose up -d --build --wait --wait-timeout 300

if ! git diff --quiet "$previous" HEAD -- config/import.yaml; then
  echo "deploy: config/import.yaml changed since $previous, running the importer"
  # </dev/null: otherwise the container reads the rest of this script from stdin.
  docker compose run --rm --build -T importer </dev/null
else
  echo "deploy: config/import.yaml unchanged, no import"
fi

port="$(docker compose port caddy 80 | head -n1 | sed 's/.*://')"
curl -fsS "http://127.0.0.1:$port/api/health"
echo
echo "$expected" > "$marker"
echo "deploy: $expected is live"
REMOTE
