"""Gateway configuration."""

import os
from typing import Optional

# RabbitMQ settings
AMQP_URL: str = os.getenv("AMQP_URL", "amqp://guest:guest@localhost/")
RPC_TIMEOUT: float = float(os.getenv("RPC_TIMEOUT", "30.0"))

# Gateway settings
SERVICE_NAME: str = "gateway"
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
