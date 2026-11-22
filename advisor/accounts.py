import hashlib
import hmac
import re
import secrets
import time
from threading import Lock

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from catalog import connect

AUTH_COOKIE = 'advisor_auth'
SESSION_SECONDS = 30 * 86400
TOKEN_PATTERN = re.compile(r'[A-Za-z0-9_-]{43}')


def token_digest(token):
    return hashlib.sha256(token.encode('ascii')).digest()


def account(db, request):
    token = request.cookies.get(AUTH_COOKIE, '')
    if not TOKEN_PATTERN.fullmatch(token):
        return None
    return db.execute('''SELECT a.id, a.username FROM auth_sessions s JOIN accounts a ON a.id=s.account_id
                         WHERE s.digest=? AND s.expires_at>?''', (token_digest(token), int(time.time()))).fetchone()


def password_hash(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=65536, r=8, p=1, maxmem=128*1024**2)


def credentials(body):
    name, password = body.get('username'), body.get('password')
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,32}', name.strip()):
        return None
    if not isinstance(password, str) or not 12 <= len(password) <= 128 or any(0xD800 <= ord(c) <= 0xDFFF for c in password):
        return None
    return name.strip().lower(), password


def start_session(db, account_id, request):
    now = int(time.time())
    db.execute('DELETE FROM auth_sessions WHERE expires_at <= ?', (now,))
    old = request.cookies.get(AUTH_COOKIE, '')
    if TOKEN_PATTERN.fullmatch(old):
        db.execute('DELETE FROM auth_sessions WHERE digest=?', (token_digest(old),))
    token = secrets.token_urlsafe(32)
    db.execute('INSERT INTO auth_sessions VALUES (?, ?, ?)', (token_digest(token), account_id, now + SESSION_SECONDS))
    return token


def login_response(request, username, token, status):
    response = JSONResponse({'username': username}, status)
    response.set_cookie(AUTH_COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        samesite='strict', secure=request.url.scheme == 'https')
    return response


def mount_accounts(app, db_path, guest_id):
    lock = Lock()
    attempts = {}
    # Single-worker MVP guard. Apply a shared limit at the ingress for public use.
    def rate_allowed(request):
        key = request.client.host if request.client else 'unknown'
        now = time.monotonic()
        with lock:
            for ip in list(attempts):
                if attempts[ip][0] <= now:
                    del attempts[ip]
            if key not in attempts and len(attempts) >= 4096:
                return False
            deadline, count = attempts.get(key, (now + 60, 0))
            if count >= 10:
                return False
            attempts[key] = deadline, count + 1
            return True

    @app.get('/api/auth/me')
    def me(request: Request):
        with connect(db_path) as db:
            user = account(db, request)
        return {'username': user[1] if user else None}

    @app.post('/api/auth/register', status_code=201)
    def register(body: dict, request: Request):
        if not rate_allowed(request):
            return JSONResponse({'code': 'try_later'}, 429, headers={'Retry-After': '60'})
        values = credentials(body)
        transfer = body.get('transferGuestCards', False)
        if not values or type(transfer) is not bool:
            return JSONResponse({'code': 'invalid_credentials'}, 422)
        username, password = values
        salt = secrets.token_bytes(16)
        digest = password_hash(password, salt)
        with connect(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            if account(db, request):
                return JSONResponse({'code': 'logout_first'}, 409)
            user_id = secrets.token_hex(16)
            result = db.execute('INSERT OR IGNORE INTO accounts VALUES (?, ?, ?, ?)', (user_id, username, salt, digest))
            if result.rowcount != 1:
                return JSONResponse({'code': 'username_taken'}, 409)
            guest = guest_id(request)
            if transfer and guest:
                owner = 'account:' + user_id
                db.execute('UPDATE manual_cards SET session=? WHERE session=?', (owner, guest))
                db.execute('UPDATE saved SET session=? WHERE session=?', (owner, guest))
            token = start_session(db, user_id, request)
        response = login_response(request, username, token, 201)
        if transfer and guest:
            response.delete_cookie('advisor_session', httponly=True, samesite='strict',
                                   secure=request.url.scheme == 'https')
        return response

    @app.post('/api/auth/login')
    def login(body: dict, request: Request):
        if not rate_allowed(request):
            return JSONResponse({'code': 'try_later'}, 429, headers={'Retry-After': '60'})
        values = credentials(body)
        if not values:
            return JSONResponse({'code': 'wrong_credentials'}, 401)
        username, password = values
        with connect(db_path) as db:
            row = db.execute('SELECT id, salt, password_hash FROM accounts WHERE username=?', (username,)).fetchone()
        verified = password_hash(password, row[1] if row else bytes(16))
        if not row or not hmac.compare_digest(row[2], verified):
            return JSONResponse({'code': 'wrong_credentials'}, 401)
        with connect(db_path) as db:
            token = start_session(db, row[0], request)
        return login_response(request, username, token, 200)

    @app.post('/api/auth/logout', status_code=204)
    def logout(request: Request):
        token = request.cookies.get(AUTH_COOKIE, '')
        if TOKEN_PATTERN.fullmatch(token):
            with connect(db_path) as db:
                db.execute('DELETE FROM auth_sessions WHERE digest=?', (token_digest(token),))
        response = Response(status_code=204)
        response.delete_cookie(AUTH_COOKIE, httponly=True, samesite='strict', secure=request.url.scheme == 'https')
        return response
