FROM python:3.12-slim

WORKDIR /app

COPY common/ ./common/
RUN pip install ./common
COPY services/tasks/ ./services/tasks/
RUN pip install ./services/tasks

WORKDIR /app/services/tasks

CMD ["python", "main.py"]