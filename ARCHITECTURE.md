# Balance Service - Архитектура

## 1. Развертывание в Kubernetes

### Основные компоненты
- **Deployment**: Stateless приложение с возможностью горизонтального масштабирования
- **ConfigMap/Secret**: Конфигурация и секретные данные (DB credentials, Redis)
- **Service**: Внутренний доступ к подам
- **Ingress**: Внешний доступ через API Gateway

### Требования к окружению
```yaml
# deployment.yaml
env:
  - name: DB_HOST
    value: "postgres-service"
  - name: REDIS_HOST  
    value: "redis-service"
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: db-secret
        key: password
```

## 2. Гарантия обработки транзакции ровно 1 раз

### Реализованные механизмы
- **Idempotency Service**: Redis-хранилище состояний операций с уникальными ключами
- **Database Transactions**: Атомарные операции с SELECT FOR UPDATE
- **UUID Transaction IDs**: Предотвращение дублирования

### Требования к соседним сервисам
- Передача **Idempotency-Key** в заголовках HTTP запросов
- Передача **X-Trace-Id** для отслеживания цепочки запросов в distributed tracing
- Обработка статус-кодов: 409 (Conflict), 400 (идемпотентная ошибка)
- Retry логика с экспоненциальным backoff

### Рекомендации для внутренних сервисов
- **Trace ID propagation**: Прокидывание trace_id через все HTTP/gRPC вызовы
- **Structured logging**: Логирование с trace_id для корреляции запросов
- **OpenTelemetry**: Стандартизированное трейсинг между микросервисами

## 3. Уведомление других сервисов

### Event-driven подход
```python
# После успешной транзакции
async def notify_services(transaction: TransactionResponse, trace_id: str):
    event = {
        "event_type": "transaction_created",
        "user_id": transaction.user_id,
        "amount": transaction.amount,
        "new_balance": user.balance,
        "timestamp": transaction.created_at,
        "trace_id": trace_id  # Для отслеживания цепочки операций
    }
    
    # Message Queue (RabbitMQ/Kafka) с trace context
    await message_broker.publish("transactions", event, headers={"X-Trace-Id": trace_id})
    
    # HTTP Webhooks (для критичных сервисов)
    await webhook_client.notify(ADVERTISING_SERVICE_URL, event)
```

### Архитектура уведомлений
- **Message Queue** (RabbitMQ/Kafka): Асинхронные уведомления
- **Webhooks**: Синхронные критичные уведомления
- **Retry механизм**: Повторные попытки при сбоях
- **Dead Letter Queue**: Обработка неуспешных уведомлений

## 4. Контроль качества работы сервиса

### Мониторинг
- **Prometheus + Grafana**: Метрики приложения и инфраструктуры
- **DataDog/Jaeger/Zipkin**: Distributed tracing с trace_id для отслеживания запросов
- **ELK Stack**: Централизованные логи с correlation_id и trace_id
- **OpenTelemetry**: Автоматическое инструментирование HTTP/gRPC вызовов

### Ключевые метрики
- Latency: P50, P95, P99 времени ответа API
- Error Rate: 4xx/5xx ошибки по endpoints
- Throughput: RPS по операциям
- Database: Connection pool, query duration
- Redis: Cache hit rate, idempotency conflicts

### Качество кода
- **Pre-commit hooks**: Black, isort, mypy, flake8
- **CI/CD pipeline**: Автоматические тесты на каждый PR
- **Coverage**: Минимум 90% покрытия кода тестами
- **Security scanning**: Проверка зависимостей на уязвимости

## 5. Гарантия неотрицательного баланса

### Реализованная защита
```python
# Database constraint
balance = Column(Decimal, CheckConstraint('balance >= 0'), nullable=False)

# Application logic
async def calculate_withdrawal_balance(current_balance: Decimal, amount: Decimal) -> Decimal:
    new_balance = current_balance - amount
    if new_balance < 0:
        raise InsufficientFundsError(f"Insufficient funds. Current: {current_balance}, Required: {amount}")
    return new_balance

# Atomic transaction with lock
async with transaction():
    user = await get_user_with_lock(user_id)  # SELECT FOR UPDATE
    new_balance = calculate_withdrawal_balance(user.balance, amount)
    await update_user_balance(user_id, new_balance)
```

### Многоуровневая защита
1. **Database Level**: CHECK constraint на уровне БД
2. **Application Level**: Валидация в бизнес-логике
3. **Concurrent Safety**: SELECT FOR UPDATE блокировка
4. **Transaction Atomicity**: Rollback при любой ошибке

