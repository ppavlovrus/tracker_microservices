# Gateway - API Gateway для Task Tracker

API Gateway для микросервисной архитектуры Task Tracker. Принимает HTTP запросы и маршрутизирует их к соответствующим микросервисам через RabbitMQ.

## Архитектура

```
HTTP Client → Gateway (FastAPI) → RabbitMQ → Microservices → PostgreSQL
```

Gateway **не имеет прямого доступа к базе данных**. Вся коммуникация с микросервисами происходит через RabbitMQ (RPC pattern).

## Установка

```bash
# Установить зависимости (из корня gateway/)
pip install -e .

# Или с dev зависимостями
pip install -e ".[dev]"
```

## Конфигурация

Создайте `.env` файл в корне gateway/:

```bash
# RabbitMQ
AMQP_URL=amqp://guest:guest@localhost/
RPC_TIMEOUT=30.0

# Gateway
SERVICE_NAME=gateway
HOST=0.0.0.0
PORT=8000

# Logging
LOG_LEVEL=INFO
```

## Запуск

### Вариант 1: Python

```bash
python -m src.main
```

### Вариант 2: Uvicorn

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Вариант 3: Из любой директории

```bash
cd /path/to/gateway
python src/main.py
```

## API Endpoints

### Health Check

```bash
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "gateway",
  "rabbitmq_connected": true
}
```

### Tasks

#### Создать задачу

```bash
POST /tasks
Content-Type: application/json

{
  "title": "New Task",
  "description": "Task description",
  "creator_id": 1,
  "status_id": 1,
  "deadline_start": "2024-01-01",
  "deadline_end": "2024-01-31"
}
```

**Response:** `201 Created`
```json
{
  "id": 123,
  "title": "New Task",
  "description": "Task description",
  "status_id": 1,
  "creator_id": 1,
  "deadline_start": "2024-01-01",
  "deadline_end": "2024-01-31",
  "created_at": "2024-01-01T12:00:00",
  "updated_at": "2024-01-01T12:00:00"
}
```

#### Получить задачу

```bash
GET /tasks/{task_id}
```

**Response:** `200 OK` (см. выше) или `404 Not Found`

#### Список задач

```bash
GET /tasks?limit=10&offset=0
```

**Response:** `200 OK`
```json
{
  "tasks": [...],
  "total": 42,
  "limit": 10,
  "offset": 0
}
```

#### Обновить задачу

```bash
PUT /tasks/{task_id}
Content-Type: application/json

{
  "title": "Updated Task",
  "status_id": 2
}
```

**Response:** `200 OK` (см. выше) или `404 Not Found`

#### Удалить задачу

```bash
DELETE /tasks/{task_id}
```

**Response:** `204 No Content` или `404 Not Found`

## Тестирование

### Примеры с curl

```bash
# Создать задачу
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Task",
    "description": "Testing",
    "creator_id": 1
  }'

# Получить задачу
curl http://localhost:8000/tasks/1

# Список задач
curl "http://localhost:8000/tasks?limit=5&offset=0"

# Обновить задачу
curl -X PUT http://localhost:8000/tasks/1 \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated Title",
    "status_id": 2
  }'

# Удалить задачу
curl -X DELETE http://localhost:8000/tasks/1
```

### Swagger UI

После запуска Gateway, откройте в браузере:

**http://localhost:8000/docs**

## Структура проекта

```
gateway/
├── src/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + lifespan
│   ├── config.py            # Конфигурация
│   ├── api/
│   │   ├── routers/
│   │   │   ├── tasks.py     # Tasks endpoints ✅
│   │   │   ├── users.py     # Users endpoints (TODO)
│   │   │   ├── tags.py      # Tags endpoints (TODO)
│   │   │   ├── attachments.py
│   │   │   ├── comments.py
│   │   │   └── auth.py
│   │   └── schemas/
│   │       ├── task.py      # Task DTOs ✅
│   │       └── ...
├── pyproject.toml
├── README.md
└── .env.example
```

## Зависимости

- `fastapi>=0.104.0` - Web framework
- `uvicorn[standard]>=0.24.0` - ASGI server
- `task_tracker_common>=0.1.3` - Общие компоненты (RabbitMQClient)

## Troubleshooting

### Ошибка: "Service temporarily unavailable"

**Причина:** RabbitMQ client не инициализирован.

**Решение:**
1. Проверьте, что RabbitMQ запущен
2. Проверьте `AMQP_URL` в конфигурации
3. Проверьте логи Gateway

### Ошибка: "Tasks service timeout"

**Причина:** Tasks микросервис не отвечает или не запущен.

**Решение:**
1. Убедитесь, что Tasks Service запущен
2. Проверьте, что Tasks Service слушает очередь `tasks.commands`
3. Увеличьте `RPC_TIMEOUT` в конфигурации

### Ошибка подключения к RabbitMQ

**Решение:**
```bash
# Запустить RabbitMQ
docker-compose -f docker-compose.rabbitmq.yml up -d

# Проверить статус
docker ps | grep rabbitmq
```

## Следующие шаги

1. ✅ Gateway для Tasks готов
2. 📝 Реализовать Tasks Service (микросервис)
3. 📝 Протестировать end-to-end
4. 📝 Добавить роутеры для Users, Tags, и т.д.

## Документация

- **RabbitMQ Client:** `../common/RABBITMQ_CLIENT_USAGE.md`
- **Architecture:** `../ARCHITECTURE_OVERVIEW.md`
- **Quick Start:** `../QUICKSTART.md`

---

**Версия:** 0.1.0  
**Статус:** ✅ Tasks endpoints готовы
