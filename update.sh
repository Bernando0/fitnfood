#!/usr/bin/env bash
# Deploy / update the FitnFood bot on the server. Run as root (repo is root-owned):
#   sudo -i bash -c 'cd /var/www/fitnfood && bash update.sh'
set -euo pipefail
cd "$(dirname "$0")"

echo "==> git pull"
git pull --ff-only

if [ ! -d venv ]; then
  echo "==> creating venv"
  python3 -m venv venv
fi

echo "==> installing dependencies"
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q

if [ ! -f .env ]; then
  echo "!! .env is missing — copy .env.example to .env and fill in the secrets before starting."
  exit 1
fi

echo "==> restarting supervisor program"
supervisorctl restart fitnfood || {
  echo "!! program 'fitnfood' not registered yet. Install it once with:"
  echo "   sudo cp deploy/fitnfood.conf /etc/supervisor/conf.d/fitnfood.conf"
  echo "   sudo supervisorctl reread && sudo supervisorctl update"
}

echo "==> done. status:"
supervisorctl status fitnfood || true
