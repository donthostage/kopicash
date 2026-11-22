"""Run browser regressions on a disposable server. Never target the deployed wallet."""
import argparse
import os
import subprocess
import sys
from pathlib import Path
from tempfile import mkdtemp

from browser_checkout_edges import check as checkout_edges
from browser_mvp import ROOT, isolated_server, run as full_wallet
from browser_plan import check as monthly_plan
from browser_catalog import check as catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='Also run the full wallet, checkout edges and monthly plan')
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--chromium-executable', default=os.getenv('CHROMIUM_PATH'))
    args = parser.parse_args()
    env = os.environ.copy()
    if args.chromium_executable:
        env['CHROMIUM_PATH'] = args.chromium_executable
    catalog(args.chromium_executable)
    subprocess.run([sys.executable, str(ROOT / 'tests/browser_wallet_limits.py')], check=True, env=env)
    if args.full:
        artifacts = args.artifacts or Path(mkdtemp(prefix='kopicash-e2e-'))
        print(f'Browser screenshots: {artifacts.resolve()}', flush=True)
        full_wallet(args.chromium_executable, artifacts, None)
        with isolated_server() as base:
            checkout_edges(base, args.chromium_executable)
        with isolated_server() as base:
            monthly_plan(base, args.chromium_executable)
    print('Browser regression suite passed.', flush=True)


if __name__ == '__main__':
    main()
