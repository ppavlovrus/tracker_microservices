FROM python:3.12-slim
WORKDIR /app
COPY common/ ./common/
RUN pip install ./common
COPY services/attachments/ ./services/attachments/
RUN pip install ./services/attachments
WORKDIR /app/services/attachments
CMD ["python", "main.py"]
