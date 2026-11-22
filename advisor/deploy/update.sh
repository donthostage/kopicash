#!/usr/bin/env bash
set -Eeuo pipefail

base=/opt/advisor
repository="$base/source"
case "${ADVISOR_DEPLOY_SOURCE:-github}" in
    github) remote=https://github.com/a05314158/advisor.git ;;
    gitlab) remote=git@gitlab.t-education.com:hack-ovb-06/sdk.git ;;
    *) echo 'Unknown ADVISOR_DEPLOY_SOURCE (expected github or gitlab).' >&2; exit 2 ;;
esac
ref=refs/heads/deploy/staging

exec 9>"$base/update.lock"
flock -n 9 || exit 0

as_advisor() {
    runuser -u advisor -- "$@"
}

if [[ ! -d "$repository/objects" ]]; then
    as_advisor git init --bare "$repository"
fi
as_advisor env GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=yes' \
    git --git-dir="$repository" fetch --no-tags --depth=1 "$remote" "$ref"
revision=$(as_advisor git --git-dir="$repository" rev-parse 'FETCH_HEAD^{commit}')
[[ "$revision" =~ ^[0-9a-f]{40}$ ]]
previous=$(readlink "$base/current" || true)
if [[ "$previous" == "$base/releases/$revision" ]]; then
    exit 0
fi
if [[ -f "$base/failed" && "$(<"$base/failed")" == "$revision" ]]; then
    echo "Revision $revision already failed its health check; waiting for the next revision."
    exit 0
fi

release="$base/releases/$revision"
if [[ ! -f "$release/.prepared" ]]; then
    install -d -o advisor -g advisor "$release"
    as_advisor git --git-dir="$repository" archive "$revision" | as_advisor tar -xf - -C "$release"
    as_advisor python3 -m venv "$release/.venv"
    as_advisor "$release/.venv/bin/python" -m pip install --disable-pip-version-check -r "$release/requirements.txt"
    chown -R root:root "$release"
    touch "$release/.prepared"
fi

switch_to() {
    ln -sfn "$1" "$base/.next"
    mv -Tf "$base/.next" "$base/current"
}

switch_to "$release"
if systemctl restart advisor.service; then
    for ((attempt=0; attempt<15; attempt++)); do
        if as_advisor python3 "$release/deploy/smoke.py" http://127.0.0.1:8766 --revision "$revision"; then
            echo "Deployed $revision"
            exit 0
        fi
        sleep 1
    done
fi

printf '%s\n' "$revision" >"$base/failed"
echo "Health check failed for $revision" >&2
if [[ -n "$previous" ]]; then
    switch_to "$previous"
    systemctl restart advisor.service
else
    systemctl stop advisor.service
    unlink "$base/current"
fi
exit 1
