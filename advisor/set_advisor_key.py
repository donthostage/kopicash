"""Configure or verify the server's AITunnel key."""
import argparse
import getpass
import os
import re
import tempfile
import warnings
from pathlib import Path


KEY = 'ADVISOR_API_KEY'
KEY_FILE = 'ADVISOR_API_KEY_FILE'
ENTRY = re.compile(r'^[ \t]*ADVISOR_API_KEY[ \t]*=')
CHECK_URL = 'https://api.aitunnel.ru/v1/aitunnel/key'


def normalize_key(value):
    value = value.strip().strip('"\'').strip()
    return value if re.fullmatch(r"[!-~]+", value) and not any(c in value for c in "\"'") else ''


def load_key(env_path, *, file_only=False):
    secret_file = os.environ.get(KEY_FILE, '').strip()
    if secret_file:
        try:
            return normalize_key(Path(secret_file).read_text(encoding='utf-8-sig'))
        except FileNotFoundError:
            # Existing installations may still use the environment variable.
            if file_only:
                return ''
        except (OSError, UnicodeError):
            return ''
    value = os.environ.get(KEY, '').strip()
    if value:
        return normalize_key(value)
    try:
        content = env_path.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError):
        return ''
    entries = [line.split('=', 1)[1] for line in content.splitlines() if ENTRY.match(line)]
    return normalize_key(entries[-1]) if entries else ''


def save_key(path: Path, key: str, *, raw=False) -> None:
    if not re.fullmatch(r"[!-~]+", key) or any(char in key for char in "\"'"):
        raise ValueError('Ключ пустой или содержит недопустимые символы.')
    try:
        existing = '' if raw else path.read_bytes().decode('utf-8-sig')
    except FileNotFoundError:
        existing = ''
    newline = '\r\n' if '\r\n' in existing else '\n'
    lines = [line for line in existing.splitlines(keepends=True) if not ENTRY.match(line)]
    text = ''.join(lines)
    if text and not text.endswith(('\r', '\n')):
        text += newline
    text += f'{key}{newline}' if raw else f'{KEY}={key}{newline}'
    pending = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.env.', delete=False) as output:
            pending = Path(output.name)
            output.write(text.encode('utf-8'))
        os.replace(pending, path)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def main():
    env_path = Path(__file__).resolve().with_name('.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, help='Файл ключа для серверного процесса')
    parser.add_argument('--check', action='store_true', help='Проверить авторизацию в AITunnel без отправки изображения')
    args = parser.parse_args()
    if args.check:
        import httpx
        if args.file:
            os.environ[KEY_FILE] = str(args.file)
        key = load_key(env_path, file_only=bool(args.file))
        if not key:
            raise SystemExit('Ключ не найден или недоступен для чтения.')
        try:
            response = httpx.get(CHECK_URL, headers={'Authorization': f'Bearer {key}'}, timeout=15)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise SystemExit(f'AITunnel отклонил проверку: HTTP {error.response.status_code}.') from None
        except httpx.HTTPError:
            raise SystemExit('Не удалось подключиться к AITunnel.') from None
        print('AITunnel принял ключ.')
        return
    target = args.file or os.environ.get(KEY_FILE) or None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            secret = getpass.getpass('Вставьте API-ключ AITunnel и нажмите Enter (ввод скрыт): ').strip()
        save_key(Path(target) if target else env_path, secret, raw=bool(target))
    except (KeyboardInterrupt, EOFError, getpass.GetPassWarning):
        raise SystemExit('Ключ не сохранён. Запустите скрипт в обычном терминале.') from None
    except ValueError as error:
        raise SystemExit(str(error) if type(error) is ValueError else 'Не удалось прочитать существующий .env.') from None
    except OSError:
        raise SystemExit('Не удалось записать ключ. Проверьте доступ к папке назначения.') from None
    print('Ключ сохранён в серверный файл.' if target else 'Ключ сохранён в локальный .env.')
    if not target and os.environ.get(KEY, '').strip():
        print('Переменная ADVISOR_API_KEY имеет приоритет над .env.')


if __name__ == '__main__':
    main()
