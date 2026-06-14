FROM python:3.12-slim
WORKDIR /app
COPY common/ ./common/
RUN pip install ./common
COPY gateway/ ./gateway/
RUN pip install ./gateway
WORKDIR /app/gateway
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
