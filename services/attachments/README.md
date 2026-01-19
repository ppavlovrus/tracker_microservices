# Attachments Service

Микросервис для работы с вложениями к задачам в системе Task Tracker.

## Описание

Attachments Service отвечает за:
- Создание записей о вложениях к задачам
- Получение информации о вложениях
- Удаление вложений
- Список вложений для конкретной задачи

**Примечание**: Этот сервис работает только с метаданными вложений (filename, content_type, storage_path, size). Само хранение файлов реализовано не здесь.

## Команды RabbitMQ

Сервис слушает очередь `attachments.commands` и обрабатывает следующие команды:

### 1. create_attachment
Создать запись о вложении.

```json
{
  "command": "create_attachment",
  "data": {
    "task_id": 1,
    "filename": "document.pdf",
    "content_type": "application/pdf",
    "storage_path": "/uploads/2025/01/document.pdf",
    "size_bytes": 1024000
  }
}
```

### 2. get_attachment
Получить информацию о вложении.

```json
{
  "command": "get_attachment",
  "data": {
    "id": 1
  }
}
```

### 3. delete_attachment
Удалить вложение.

```json
{
  "command": "delete_attachment",
  "data": {
    "id": 1
  }
}
```

### 4. list_attachments_by_task
Получить список вложений для задачи.

```json
{
  "command": "list_attachments_by_task",
  "data": {
    "task_id": 1
  }
}
```

## Запуск

### Установка зависимостей

```bash
pip install -e .
```

### Запуск сервиса

```bash
python main.py
```

## Переменные окружения

См. файл `env.example`.

## База данных

Сервис использует таблицу `attachment`:
- `id` - ID вложения
- `task_id` - ID задачи
- `filename` - Имя файла
- `content_type` - MIME-тип файла
- `storage_path` - Путь к файлу в хранилище
- `size_bytes` - Размер файла в байтах
- `uploaded_at` - Дата и время загрузки

## Архитектура

- `main.py` - Точка входа, RabbitMQ consumer
- `config.py` - Конфигурация сервиса
- `src/handlers/` - Обработчики команд
- `src/repositories/` - Работа с БД
