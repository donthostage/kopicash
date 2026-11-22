#!/usr/bin/env bash
set -Eeuo pipefail
: "${DEPLOY_HOST:?}" "${DEPLOY_USER:?}" "${DEPLOY_KEY:?}"
: "${CI_COMMIT_SHA:?}" "${CI_REPOSITORY_URL:?}" "${CI_DEFAULT_BRANCH:?}"
[[ "$DEPLOY_HOST" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ && "$DEPLOY_HOST" != CHANGE_ME_VM_IP ]]
[[ "$DEPLOY_USER" =~ ^[a-z_][a-z0-9_-]*$ && "$CI_COMMIT_SHA" =~ ^[0-9a-f]{40}$ ]]
image="${DOCKER_ARTIFACTORY_REGISTRY}/${CI_PROJECT_ROOT_NAMESPACE}/${CI_PROJECT_NAME}:advisor-${CI_COMMIT_SHA}"
[[ "$image" =~ ^registry\.spirit\.t-education\.com/[a-zA-Z0-9._/-]+:advisor-[0-9a-f]{40}$ ]]
latest=$(git ls-remote --exit-code "$CI_REPOSITORY_URL" "refs/heads/$CI_DEFAULT_BRANCH")
if [[ "${latest%%$'\t'*}" != "$CI_COMMIT_SHA" ]]; then
    echo 'A newer commit is on the default branch; skip Advisor deployment.'
    exit 0
fi
command -v ssh >/dev/null || (apt-get update -qq && apt-get install -y -qq --no-install-recommends openssh-client)
chmod 600 "$DEPLOY_KEY"
known_hosts=$(mktemp)
trap 'rm -f -- "$known_hosts"' EXIT
read -r key_type key_blob < advisor/deploy/spirit-vm-ed25519.pub
[[ "$key_type" == ssh-ed25519 && "$key_blob" =~ ^[A-Za-z0-9+/]+={0,2}$ ]]
printf '%s %s %s\n' "$DEPLOY_HOST" "$key_type" "$key_blob" > "$known_hosts"
opts=(-i "$DEPLOY_KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o GlobalKnownHostsFile=/dev/null
      -o HostKeyAlgorithms=ssh-ed25519 -o "UserKnownHostsFile=$known_hosts")
vm="$DEPLOY_USER@$DEPLOY_HOST"
remote_dir=".advisor-releases/$CI_COMMIT_SHA"
ssh "${opts[@]}" "$vm" "mkdir -p '$remote_dir'"
scp "${opts[@]}" advisor/deploy/docker-compose.yml advisor/deploy/docker-compose.frontend.yml advisor/deploy/smoke.py "$vm:$remote_dir/"
sudo_prefix=''
if [[ "$DEPLOY_USER" != root ]]; then sudo_prefix='sudo -n '; fi
ssh "${opts[@]}" "$vm" "${sudo_prefix}bash -s -- '$image' '$CI_COMMIT_SHA' '$remote_dir/docker-compose.yml'" < advisor/deploy/spirit-release.sh
