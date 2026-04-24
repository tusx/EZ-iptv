FROM python:3-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=run:app

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.py ./
COPY README.md ./

RUN mkdir -p /app/instance

EXPOSE 8091

CMD ["gunicorn", "--bind", "0.0.0.0:8091", "--workers", "2", "run:app"]
