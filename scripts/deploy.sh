#!/usr/bin/env bash
# Deploy main to the home server. Run from the repository root (Git Bash on Windows works):
#
#   bash scripts/deploy.sh
#
# 1. Push main to GitHub and stop unless CI for that commit is green.
# 2. On the server: git pull, then rebuild and restart the game container.
# 3. Check /api/health on the game's port.
#
# The server needs neither Neo4j nor an LLM: new questions arrive with pool/ in git.
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

# Ask GitHub every 15 seconds, for up to 15 minutes, how the CI run of this commit went.
echo "deploy: waiting for CI on $sha"
state="none"
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

# Everything between REMOTE and REMOTE runs on the server.
ssh -o BatchMode=yes "$SERVER" bash -s -- "$SERVER_DIR" "$sha" <<'REMOTE'
set -euo pipefail
cd "$1"
expected="$2"

git pull --ff-only
if [ "$(git rev-parse HEAD)" != "$expected" ]; then
  echo "deploy: server is at $(git rev-parse HEAD), expected $expected" >&2
  exit 1
fi

# --remove-orphans stops and removes containers of services no longer in
# docker-compose.yml (the classic caddy, backend and postgres). Their volumes are kept.
docker compose up -d --build --wait --wait-timeout 300 --remove-orphans
# The server never runs the offline part: stop and remove its containers if any are left
# (the classic version ran Neo4j here). Volumes are kept; nothing happens when none run.
docker compose --profile offline rm --stop --force neo4j importer poolgen

port="$(docker compose port game 8000 | head -n1 | sed 's/.*://')"
curl -fsS "http://127.0.0.1:$port/api/health"
echo
echo "deploy: $expected is live"
REMOTE
