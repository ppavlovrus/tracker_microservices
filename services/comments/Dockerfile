FROM python:3.12-slim
WORKDIR /app
COPY common/ ./common/
RUN pip install ./common
COPY services/comments/ ./services/comments/
RUN pip install ./services/comments
WORKDIR /app/services/comments
CMD ["python", "main.py"]
