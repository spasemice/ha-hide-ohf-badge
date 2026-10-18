FROM python:3.14-alpine

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY app.py patcher.py status.py ./
CMD ["python3", "/app/app.py"]
