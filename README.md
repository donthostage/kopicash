# КопиКэш

КопиКэш сравнивает ожидаемый кэшбэк по картам перед покупкой. Приложение и инструкция по настройке AITunnel находятся в [`advisor/`](advisor/README.md).

## Локальный запуск

```bash
cd advisor
python -m pip install -r requirements.txt
python -m unittest -q
python -m uvicorn advisor:app --host 127.0.0.1 --port 8766
```

## Ручное развёртывание

В каталоге `advisor/` находятся Dockerfile для бэкенда и фронтенда, конфигурация Compose и проверка запущенной версии. [Проверки и откат на ВМ](advisor/docs/gitlab-deploy.md).
