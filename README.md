# Balance Service

Сервис по работе с балансами пользователей на FastAPI + PostgreSQL + Redis.

## 🚀 Запуск проекта

### Docker Compose (рекомендуется)
```bash
# Запустить все сервисы (PostgreSQL, Redis, приложение)
docker-compose up -d

# Применить миграции
make migrate

# Сервис доступен на http://localhost:8000
# Swagger UI: http://localhost:8000/docs
```

### Локальная разработка
```bash
# Установить зависимости
poetry install

# Запустить PostgreSQL и Redis
docker-compose up -d postgres redis

# Применить миграции
make migrate

# Запустить сервис
make run
```

## 🧪 Тестирование

```bash
# Запустить все тесты
make tests

# Только unit тесты
make test-unit

# Только integration тесты  
make test-integration
```

## �️ Миграции

```bash
# Применить миграции
make migrate

# Создать новую миграцию
alembic revision --autogenerate -m "description"

# Откатить последнюю миграцию
alembic downgrade -1
```

## 📡 API Endpoints

- **POST /users** - Создание пользователя
- **GET /users/{user_id}** - Информация о пользователе  
- **GET /users/{user_id}/balance** - Баланс пользователя
- **POST /transactions** - Создание транзакции (DEPOSIT/WITHDRAW)
- **GET /transactions/{transaction_uid}** - Информация о транзакции

Swagger UI доступен по адресу: http://localhost:8000/docs

## 🏗️ Архитектура

Подробная документация по архитектуре и требованиям K8s: [ARCHITECTURE.md](./ARCHITECTURE.md)