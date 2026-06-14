FROM python:3.12-slim
WORKDIR /app
COPY common/ ./common/
RUN pip install ./common
COPY services/users/ ./services/users/
RUN pip install ./services/users
WORKDIR /app/services/users
CMD ["python", "main.py"]
