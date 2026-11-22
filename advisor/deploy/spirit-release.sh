#!/usr/bin/env bash
set -Eeuo pipefail

image=${1:?image required}
revision=${2:?revision required}
compose_file=${3:?compose file required}
frontend_file="${compose_file%/*}/docker-compose.frontend.yml"
[[ "$revision" =~ ^[0-9a-f]{40}$ ]]
[[ "$image" =~ ^registry\.spirit\.t-education\.com/[a-zA-Z0-9._/-]+:advisor-[0-9a-f]{40}$ && "${image##*:}" == "advisor-$revision" ]]
[[ -f "$compose_file" && -f "$frontend_file" && -d /var/lib/advisor && -f /etc/advisor.env ]]
if command -v systemctl >/dev/null && systemctl is-active --quiet advisor.service advisor-update.timer advisor-update.service; then
    echo 'Stop and disable the legacy Advisor updater before the one-time cutover.' >&2
    exit 1
fi

ADVISOR_UID=$(stat -c %u /var/lib/advisor)
ADVISOR_GID=$(stat -c %g /var/lib/advisor)
export ADVISOR_UID ADVISOR_GID
[[ "$ADVISOR_UID" != 0 ]] || { echo 'Advisor data directory must have a non-root owner.' >&2; exit 1; }
export ADVISOR_IMAGE="$image" ADVISOR_REVISION="$revision"
export ADVISOR_FRONTEND_IMAGE="${image%:*}:advisor-frontend-$revision"
files=(-f "$compose_file" -f "$frontend_file")
compose() { docker compose --project-name advisor-spirit "${files[@]}" "$@"; }
previous=$(compose ps -q advisor)
previous_image='' previous_revision='' previous_frontend_image=''
previous_files=()
if [[ -n "$previous" ]]; then
    previous_image=$(docker inspect -f '{{.Image}}' "$previous")
    previous_revision=$(docker inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$previous")
    [[ "$previous_revision" =~ ^[0-9a-f]{40}$ ]] || { echo 'Cannot identify previous release; stopping before changing containers.' >&2; exit 1; }
    previous_dir="${compose_file%/*}/../$previous_revision"
    if [[ -f "$previous_dir/docker-compose.yml" && -f "$previous_dir/docker-compose.frontend.yml" ]]; then
        previous_files=(-f "$previous_dir/docker-compose.yml" -f "$previous_dir/docker-compose.frontend.yml")
        previous_frontend=$(compose ps -q frontend)
        [[ -n "$previous_frontend" ]] || { echo 'Cannot identify previous frontend; stopping before changing containers.' >&2; exit 1; }
        previous_frontend_image=$(docker inspect -f '{{.Image}}' "$previous_frontend")
    elif [[ -f "$previous_dir/compose.yml" ]]; then
        previous_files=(-f "$previous_dir/compose.yml")
    else
        echo 'Previous Compose file is missing; stopping before changing containers.' >&2
        exit 1
    fi
fi
compose pull advisor frontend
smoke() {
    local frontend=$1
    local -a args=(http://127.0.0.1:8766 --revision "$ADVISOR_REVISION")
    if [[ "$frontend" == yes ]]; then args+=(--require-frontend); fi
    for ((attempt=0; attempt<20; attempt++)); do
        if [[ "$frontend" == yes ]]; then
            if python3 "$smoke_file" "${args[@]}"; then return 0; fi
        elif compose exec -T advisor python deploy/smoke.py "${args[@]}"; then
            return 0
        fi
        sleep 2
    done
    return 1
}
smoke_file="${compose_file%/*}/smoke.py"
[[ -r "$smoke_file" ]] || { echo 'Missing release smoke script.' >&2; exit 1; }
if compose up -d --no-build --pull never advisor frontend && smoke yes; then
    echo "Deployed $revision"
    exit 0
fi
if [[ -n "$previous_image" ]]; then
    # A first cutover rollback must free the port before recreating the old backend.
    if [[ -z "$previous_frontend_image" ]]; then compose stop frontend || true; fi
    files=("${previous_files[@]}")
    export ADVISOR_IMAGE="$previous_image" ADVISOR_REVISION="$previous_revision"
    services=(advisor)
    had_frontend=no
    if [[ -n "$previous_frontend_image" ]]; then
        export ADVISOR_FRONTEND_IMAGE="$previous_frontend_image"
        services+=(frontend)
        had_frontend=yes
    fi
    compose up -d --no-build --pull never "${services[@]}" && smoke "$had_frontend" && echo "Rolled back to $previous_revision" >&2
else
    compose stop frontend advisor
fi
exit 1
