# Task Tracker Microservices

Система управления задачами на основе микросервисной архитектуры с RabbitMQ

## 🏗️ Архитектура

```
┌─────────────────┐
│  HTTP Clients   │
└────────┬────────┘
         ↓
┌─────────────────────────────┐
│  Gateway (FastAPI)          │
│  - REST API                 │
│  - Валидация                │
│  - Request-Reply RabbitMQ   │
└────────┬────────────────────┘
         ↓
    RabbitMQ Broker
         ↓
┌────────┴────────┬────────────┬─────────────┐
│                 │            │             │
▼                 ▼            ▼             ▼
Tasks Service   Users       Tags        Comments
(Worker)        Service     Service     Service
```

## 🚀 Быстрый старт

```bash
# 1. Запустите зависимости
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
docker run -d --name postgres -e POSTGRES_PASSWORD=qwerty -p 5432:5432 postgres:15

# 2. Установите зависимости
source venv/bin/activate
cd common && pip install -e . && cd ..

# 3. Примените миграции
cd common && alembic upgrade head && cd ..

# 4. Запустите сервисы
# Терминал 1: Tasks Service
python -m services.tasks.main

# Терминал 2: Gateway
python -m gateway.src.main

# 5. Тестируйте
curl -X POST http://localhost:8000/tasks/ \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Task", "status_id": 1}'
```

Подробнее: **[QUICKSTART.md](./QUICKSTART.md)**

## 📚 Документация

- **[QUICKSTART.md](./QUICKSTART.md)** - Быстрый старт за 5 минут
- **[ARCHITECTURE_OVERVIEW.md](./ARCHITECTURE_OVERVIEW.md)** - Архитектура и примеры кода
- **[RABBITMQ_SETUP.md](./RABBITMQ_SETUP.md)** - Установка RabbitMQ и troubleshooting
- **[REPOSITORIES_OVERVIEW.md](./REPOSITORIES_OVERVIEW.md)** - Обзор репозиториев
- **[SCHEMAS_OVERVIEW.md](./SCHEMAS_OVERVIEW.md)** - Обзор DTO схем

## 🧩 Компоненты

### Gateway Service
- **Порт:** 8000
- **Технологии:** FastAPI, aio-pika
- **Функции:**
  - REST API endpoints
  - Валидация запросов (Pydantic)
  - Отправка команд в RabbitMQ
  - Request-Reply паттерн

### Tasks Service
- **Очередь:** `tasks.commands`
- **Технологии:** asyncpg, aio-pika
- **Функции:**
  - Обработка команд для задач
  - CRUD операции
  - Назначение пользователей и тегов

### Common Package (`task_tracker_common`)
- **Назначение:** Общий код для всех сервисов
- **Содержит:**
  - RabbitMQ клиенты
  - Базовые репозитории
  - Структуры команд и событий
  - SQLAlchemy модели
  - Alembic миграции

## 🛠️ Технологии

- **Python 3.9+**
- **FastAPI** - REST API Gateway
- **RabbitMQ** - Message Broker
- **PostgreSQL** - База данных
- **asyncpg** - Async PostgreSQL драйвер
- **aio-pika** - Async RabbitMQ клиент
- **Pydantic** - Валидация данных
- **SQLAlchemy** - ORM для миграций
- **Alembic** - Миграции БД

## 📂 Структура проекта

```
tracker_microservices/
├── common/                      # Общий пакет
│   ├── task_tracker_common/
│   │   ├── db/                 # Модели и конфигурация БД
│   │   ├── repository/         # Базовые репозитории
│   │   ├── messaging/          # RabbitMQ клиенты
│   │   └── dto/                # Базовые DTO
│   └── alembic/                # Миграции
├── gateway/                     # API Gateway
│   └── src/
│       ├── main.py             # FastAPI приложение
│       ├── messaging/          # Gateway RabbitMQ клиент
│       └── api/
│           ├── routers/        # REST endpoints
│           └── schemas/        # Pydantic DTOs
└── services/                    # Микросервисы
    ├── tasks/
    │   ├── main.py             # Entry point
    │   └── src/
    │       ├── workers/        # RabbitMQ consumers
    │       ├── handlers/       # Бизнес-логика
    │       ├── repositories/   # DB операции
    │       └── schemas/        # DTOs
    ├── users/
    ├── tags/
    ├── comments/
    └── attachments/
```

## 🔄 Паттерны взаимодействия

### Request-Reply (Реализовано)
```
Client → Gateway → RabbitMQ → Service → Database
                      ↓           ↓
Client ← Gateway ← RabbitMQ ← Service
```

**Используется для:** CRUD операции

### Event-Driven (TODO)
```
Service → RabbitMQ (Events) → Multiple Services
```

**Будет использоваться для:**
- `task.created` → уведомления
- `task.deleted` → очистка связанных данных
- `user.deleted` → обновление задач

## 🎯 Текущий статус

### ✅ Реализовано
- [x] Common package с RabbitMQ клиентами
- [x] Gateway Service с REST API
- [x] Tasks Service worker
- [x] Request-Reply паттерн
- [x] Базовые CRUD операции для задач
- [x] Репозитории для всех сущностей
- [x] DTO схемы для всех сущностей

### 🚧 В разработке
- [ ] Аутентификация (JWT)
- [ ] Остальные микросервисы (Users, Tags, Comments, Attachments)
- [ ] Event-driven communication
- [ ] Мониторинг и логирование

### 📋 Планируется
- [ ] Distributed tracing (Jaeger)
- [ ] Prometheus metrics
- [ ] Docker Compose для всей системы
- [ ] CI/CD pipeline
- [ ] Kubernetes deployment

## 🧪 Тестирование

```bash
# Health check
curl http://localhost:8000/health

# Создать задачу
curl -X POST http://localhost:8000/tasks/ \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New Task",
    "description": "Task description",
    "status_id": 1,
    "deadline_start": "2024-01-20",
    "deadline_end": "2024-01-30"
  }'

# Получить задачу
curl http://localhost:8000/tasks/1

# Обновить задачу
curl -X PUT http://localhost:8000/tasks/1 \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated Task", "status_id": 2}'

# Список задач
curl http://localhost:8000/tasks/?limit=10&offset=0

# Назначить пользователей
curl -X POST http://localhost:8000/tasks/1/assign-users \
  -H "Content-Type: application/json" \
  -d '{"user_ids": [1, 2, 3]}'

# Назначить теги
curl -X POST http://localhost:8000/tasks/1/assign-tags \
  -H "Content-Type: application/json" \
  -d '{"tag_ids": [1, 2]}'

# Удалить задачу
curl -X DELETE http://localhost:8000/tasks/1
```

## 📊 Мониторинг

### RabbitMQ Management UI
- URL: http://localhost:15672
- Логин: `guest` / Пароль: `guest`

### Gateway Swagger UI
- URL: http://localhost:8000/docs

## 🔧 Конфигурация

### Переменные окружения

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=qwerty
DB_NAME=task_tracker

# RabbitMQ
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Gateway
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8000
RPC_TIMEOUT=10
```

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

MIT License

## 👤 Author

Pavel Pavlov

---

**Версия:** 0.1.0  
**Последнее обновление:** Декабрь 2024
