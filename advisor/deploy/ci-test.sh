#!/usr/bin/env bash
set -Eeuo pipefail
release=$(mktemp -d)
server=''
cleanup() {
    if [[ -n "$server" ]]; then kill "$server" 2>/dev/null || true; wait "$server" 2>/dev/null || true; fi
    rm -rf -- "$release"
}
trap cleanup EXIT
git archive "${CI_COMMIT_SHA:?}" advisor/ | tar -x -C "$release"
cd "$release/advisor"
python -m pip install -r requirements.txt
python -m pip check
python -m unittest -v
for script in deploy/*.sh; do bash -n "$script"; done
python -m pip install playwright==1.58.0
python -m playwright install --with-deps chromium
export ADVISOR_DB="$release/ci.sqlite3"
python - <<'PY'
import os
from catalog import SEED, import_catalog
import_catalog(os.environ['ADVISOR_DB'], [
    dict(rule, validFrom='2000-01-01', validUntilExclusive='2100-01-01', updatedOn='2000-01-01')
    for rule in SEED
])
PY
python -m uvicorn advisor:app --host 127.0.0.1 --port 8766 &
server=$!
for attempt in $(seq 1 15); do
    if python deploy/smoke.py http://127.0.0.1:8766 --revision "$CI_COMMIT_SHA"; then
        python tests/browser_mvp.py --revision "$CI_COMMIT_SHA"
        python tests/browser_checkout_edges.py http://127.0.0.1:8766
        python tests/browser_plan.py http://127.0.0.1:8766
        exit 0
    fi
    sleep 1
done
exit 1
