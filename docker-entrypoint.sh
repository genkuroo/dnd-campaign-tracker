#!/bin/sh
# Prepares the data directory, then hands off to the real command.
set -e

DATA_DIR="${DND_DATA_DIR:-.}"
mkdir -p "$DATA_DIR"

# A public demo/staging instance seeds its own synthetic campaign (mirrors
# stock-tracker's docker-entrypoint.sh). Guarded on the legacy single-file
# path not existing so a container restart never wipes already-seeded data,
# and so this can never touch a real campaign if DEMO is ever set by
# mistake. Seeding there (not into campaigns/) is deliberate: init_db()'s
# normal multi-campaign bootstrap already knows how to adopt a legacy
# campaign.db as the first campaign — the same path a pre-multi-campaign
# install upgrades through — so this needs no separate seeding logic.
if [ "$DEMO" = "1" ] && [ ! -f "$DATA_DIR/campaign.db" ]; then
	echo "DEMO=1 and no database present — seeding synthetic data"
	DND_DB_PATH="$DATA_DIR/campaign.db" python seed_test_db.py
fi

exec "$@"
