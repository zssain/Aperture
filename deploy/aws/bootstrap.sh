#!/usr/bin/env bash
# One-command bring-up for a single free-tier EC2 box (Ubuntu 24.04).
# Run it on the instance after connecting:
#
#   curl -fsSL https://raw.githubusercontent.com/zssain/Aperture/demo-polish/deploy/aws/bootstrap.sh | bash
#
# It installs Docker, adds swap (a t3.micro only has 1 GB RAM), clones the repo,
# builds the lean single-box stack, runs migrations, seeds the demo, and prints the URL.
set -euo pipefail

REPO="https://github.com/zssain/Aperture.git"
BRANCH="demo-polish"
DIR="$HOME/Aperture"
COMPOSE="-f docker-compose.prod.yml -f docker-compose.aws.yml"

echo "==> 1/6  Installing git, Docker and the Compose plugin"
sudo apt-get update -y
sudo apt-get install -y git curl
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER" || true   # takes effect on next login; we use sudo below

echo "==> 2/6  Adding 4 GB swap (protects the build/runtime from OOM on 1 GB RAM)"
if [ ! -f /swapfile ]; then
  sudo fallocate -l 4G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> 3/6  Fetching the code ($BRANCH)"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch origin "$BRANCH" && git -C "$DIR" checkout "$BRANCH" && git -C "$DIR" pull --ff-only
else
  git clone -b "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"

echo "==> 4/6  Detecting this box's public URL"
TOKEN="$(curl -s -X PUT 'http://169.254.169.254/latest/api/token' -H 'X-aws-ec2-metadata-token-ttl-seconds: 300' || true)"
IP="$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 || true)"
if [ -z "$IP" ]; then
  echo "!!  Could not read the public IP from instance metadata; falling back to localhost."
  echo "    After it starts, edit FRONTEND_ORIGIN / PUBLIC_URL to http://<your public IP> and re-run 'up'."
  IP="localhost"
fi
export PUBLIC_URL="http://$IP"
echo "    PUBLIC_URL=$PUBLIC_URL"

echo "==> 5/6  Building and starting the stack (first build takes ~10-15 min on t3.micro)"
sudo -E docker compose $COMPOSE build
sudo -E docker compose $COMPOSE up -d

echo "    waiting for the API to become healthy…"
for _ in $(seq 1 60); do
  if sudo docker compose $COMPOSE ps api | grep -q healthy; then break; fi
  sleep 5
done

echo "==> 6/6  Seeding the demo book"
sudo -E docker compose $COMPOSE run --rm api python scripts/seed_demo.py || {
  echo "!!  Seed failed — the DB may still be migrating. Re-run this once it settles:"
  echo "    cd $DIR && sudo -E PUBLIC_URL=$PUBLIC_URL docker compose $COMPOSE run --rm api python scripts/seed_demo.py"
}

echo
echo "======================================================================"
echo " Aperture is up:  $PUBLIC_URL"
echo " Sign in: creditanalyst@aperture.com / policyowner@aperture.com /"
echo "          fraudreviewer@aperture.com / auditor@aperture.com   (password 123456)"
echo
echo " Manage it (from $DIR):"
echo "   sudo docker compose $COMPOSE ps            # status"
echo "   sudo docker compose $COMPOSE logs -f api   # logs"
echo "   sudo docker compose $COMPOSE down          # stop"
echo "======================================================================"
