#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$EUID" -ne 0 ]]; then
    echo 'Run with sudo from the Advisor checkout.' >&2
    exit 1
fi
source_files=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
public_host=${1:-}
if [[ -n "$public_host" && ! "$public_host" =~ ^[a-z0-9-]+\.vm\.prodcontest\.com$ ]]; then
    echo 'Expected a VM hostname under vm.prodcontest.com.' >&2
    exit 1
fi
if ! systemctl is-active --quiet advisor.service &&
   [[ -n "$(ss -H -ltn 'sport = :8766')" ]]; then
    echo 'Port 8766 is already in use. Leaving the existing service in place.' >&2
    exit 1
fi
if ! command -v git >/dev/null || ! command -v curl >/dev/null || ! python3 -c 'import venv, ensurepip' 2>/dev/null; then
    apt-get update
    apt-get install -y git curl python3-venv
fi
if ! id advisor >/dev/null 2>&1; then
    useradd --system --home-dir /var/lib/advisor --shell /usr/sbin/nologin advisor
fi

install -d -m 0755 /opt/advisor /opt/advisor/bin /opt/advisor/releases
install -d -m 0750 -o advisor -g advisor /opt/advisor/source /var/lib/advisor
install -m 0755 "$source_files/update.sh" /opt/advisor/bin/update
install -m 0644 "$source_files/advisor.service" "$source_files/advisor-update.service" \
    "$source_files/advisor-update.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable advisor.service
systemctl start advisor-update.service
systemctl enable --now advisor-update.timer

if [[ -n "$public_host" ]]; then
    if [[ -e /etc/caddy/Caddyfile ]] && ! grep -Fxq '# Advisor staging' /etc/caddy/Caddyfile; then
        echo 'Caddy is already configured. Add a site for the VM hostname with upstream 127.0.0.1:8766.'
        exit 0
    fi
    if ! systemctl is-active --quiet caddy &&
       { [[ -n "$(ss -H -ltn 'sport = :80')" ]] || [[ -n "$(ss -H -ltn 'sport = :443')" ]]; }; then
        echo 'Port 80 or 443 is already in use. Keep the existing web server and add an upstream on 127.0.0.1:8766.'
        exit 0
    fi
    if ! command -v caddy >/dev/null; then
        apt-get update
        apt-get install -y caddy
    fi
    config=$(mktemp)
    trap 'rm -f -- "$config"' EXIT
    printf '# Advisor staging\n%s {\n    reverse_proxy 127.0.0.1:8766\n}\n' "$public_host" >"$config"
    caddy validate --adapter caddyfile --config "$config"
    install -m 0644 "$config" /etc/caddy/Caddyfile
    systemctl enable caddy
    systemctl reload-or-restart caddy
    printf 'Check HTTPS from another network: https://%s/\n' "$public_host"
fi
