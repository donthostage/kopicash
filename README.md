# КопиКэш

КопиКэш сравнивает ожидаемый кэшбэк по картам перед покупкой. Приложение и инструкция по настройке AITunnel находятся в [`advisor/`](advisor/README.md).

## Локальный запуск

```bash
cd advisor
python -m pip install -r requirements.txt
python -m unittest -q
python -m uvicorn advisor:app --host 127.0.0.1 --port 8766
```

## Проверки и развёртывание

GitHub Actions запускает тесты API, браузерный сценарий и сборку образов. Развёртывание на существующую ВМ через GitLab и Spirit настраивается отдельно. [Настройка, проверки и откат](advisor/docs/gitlab-deploy.md).
