"""Check a running release against the mandatory purchase scenario."""
import argparse
import json
import sys
from urllib.request import Request, urlopen


def read(base, path, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    headers = {} if body is None else {'Content-Type': 'application/json'}
    with urlopen(Request(base + path, data=body, headers=headers), timeout=2) as response:
        return response.read()


def check(base, revision=None, *, require_frontend=False):
    amount, category = 250_000, 'supermarkets'
    health = json.loads(read(base, '/healthz'))
    if health.get('status') != 'ok' or (revision is not None and health.get('revision') != revision):
        raise ValueError(f'Unexpected health status or revision: {health}')
    if require_frontend and (not revision or read(base, '/frontend-revision').strip() != revision.encode()):
        raise ValueError('Unexpected frontend revision')
    if not read(base, '/'):
        raise ValueError('Home page is empty')
    categories = json.loads(read(base, '/api/categories'))
    if category not in categories:
        raise ValueError('Supermarkets are missing')
    products = json.loads(read(base, '/api/cards?categoryId=' + category))
    expected = []
    for card in products:
        for rule in card['rules']:
            if rule['categoryId'] != category or rule['minAmountKopecks'] > amount:
                continue
            raw = (amount * rule['rateBps'] + 5000) // 10_000
            cap = rule['limitKopecks']
            expected.append((card['cardId'], raw if cap is None else min(raw, cap)))
    expected.sort(key=lambda row: (-row[1], row[0]))

    payload = dict(categoryId=category, amountKopecks=amount, scope='all')
    result = json.loads(read(base, '/api/recommendations', payload))
    matches = [(row['cardId'], row['cashbackKopecks']) for row in result['allMatches']]
    top = [(row['cardId'], row['cashbackKopecks']) for row in result['top3']]
    if len({card for card, _ in expected}) < 3 or matches != expected or top != expected[:3]:
        raise ValueError('The supermarket ranking does not match the active catalog')
    if result != json.loads(read(base, '/api/recommendations', payload)):
        raise ValueError('The mandatory recommendation is not repeatable')
    return top


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url')
    parser.add_argument('--revision')
    parser.add_argument('--require-frontend', action='store_true')
    args = parser.parse_args()
    try:
        print('Advisor release smoke passed:', check(args.base_url.rstrip('/'), args.revision,
                                                     require_frontend=args.require_frontend))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'Advisor release smoke failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
