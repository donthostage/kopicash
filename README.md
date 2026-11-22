# КопиКэш

КопиКэш сравнивает ожидаемый кэшбэк по картам перед покупкой. Приложение и инструкция по настройке AITunnel находятся в [`advisor/`](advisor/README.md).

## Локальный запуск

```bash
cd advisor
python -m pip install -r requirements.txt
python -m unittest -q
python -m uvicorn advisor:app --host 127.0.0.1 --port 8766
```

## Тесты

Из каталога `advisor`:

```bash
python -m pip install -r requirements-test.txt
python -m unittest -q
python -m playwright install chromium
python tests/run_browser.py
python tests/run_browser.py --full
```

Браузерные тесты сами запускают локальный сервер с временной SQLite-базой.
Если Chromium уже установлен, можно указать путь к нему через `CHROMIUM_PATH`
и пропустить `playwright install chromium`.

После ручного релиза запустите smoke на публичном адресе,
подставив точный SHA релиза:

```bash
python deploy/smoke.py "$DEMO_URL" --revision "$RELEASE_SHA" --require-frontend
```

Полный браузерный прогон проверяет также журнал, планирование, ошибки расчёта
и форму после распознавания. Ответ OCR подставляется в браузере: доступность
AITunnel и реальные телефоны этим прогоном не проверяются.

## Ручное развёртывание

В каталоге `advisor/` находятся Dockerfile для бэкенда и фронтенда, конфигурация Compose и проверка запущенной версии. [Проверки и откат на ВМ](advisor/docs/gitlab-deploy.md).
