FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py *.json ./
COPY deploy/smoke.py deploy/smoke.py
USER 10001:10001
EXPOSE 8766
CMD ["python", "-m", "uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "8766", "--no-access-log"]
