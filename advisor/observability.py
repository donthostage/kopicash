import json
import logging
import secrets
from collections import Counter
from datetime import UTC, datetime
from threading import Lock
from time import perf_counter

from fastapi.responses import JSONResponse, PlainTextResponse


def mount_observability(app):
    logger = logging.getLogger('advisor')
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
        logger.setLevel(logging.INFO)
        logger.propagate = False
    requests = Counter()
    durations = Counter()
    lock = Lock()

    @app.get('/metrics', include_in_schema=False)
    def metrics():
        lines = ['# TYPE advisor_http_requests_total counter', '# TYPE advisor_http_request_duration_seconds summary']
        with lock:
            for (method, route, status), count in sorted(requests.items()):
                labels = f'method="{method}",route="{route}",status="{status}"'
                lines.extend((f'advisor_http_requests_total{{{labels}}} {count}',
                              f'advisor_http_request_duration_seconds_count{{{labels}}} {count}',
                              f'advisor_http_request_duration_seconds_sum{{{labels}}} {durations[method, route, status]:.6f}'))
        return PlainTextResponse('\n'.join(lines) + '\n', media_type='text/plain; version=0.0.4',
                                 headers={'Cache-Control': 'no-store'})

    @app.middleware('http')
    async def monitor(request, call_next):
        req_id = secrets.token_hex(12)
        start = perf_counter()
        error = None
        try:
            origin = request.headers.get('origin')
            if request.url.path.startswith('/api/') and request.method in {'POST', 'PUT', 'DELETE', 'PATCH'} and (
                request.headers.get('sec-fetch-site') == 'cross-site' or (origin is not None and origin != str(request.base_url).rstrip('/'))
            ):
                response = JSONResponse({'code': 'foreign_origin'}, 403)
            else:
                response = await call_next(request)
        except Exception as exc:
            error = type(exc).__name__
            response = JSONResponse({'code': 'internal_error'}, 500)
        response.headers['X-Request-ID'] = req_id
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        route = getattr(request.scope.get('route'), 'path', '<unmatched>')
        method = request.method if request.method in {'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'} else 'OTHER'
        status = response.status_code
        elapsed = perf_counter() - start
        if route != '/metrics':
            with lock:
                requests[method, route, status] += 1
                durations[method, route, status] += elapsed
            event = dict(event='http_request', timestamp=datetime.now(UTC).isoformat(), request_id=req_id,
                         method=method, route=route, status=status, duration_ms=round(elapsed * 1000, 2))
            if error:
                event['error_type'] = error
            logger.log(logging.ERROR if status >= 500 else logging.INFO, json.dumps(event))
        return response
