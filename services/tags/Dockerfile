FROM python:3.12-slim
WORKDIR /app
COPY common/ ./common/
RUN pip install ./common
COPY services/tags/ ./services/tags/
RUN pip install ./services/tags
WORKDIR /app/services/tags
CMD ["python", "main.py"]
