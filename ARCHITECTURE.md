# Balance Service - Архитектура

## 1. Развертывание в Kubernetes

### Основные компоненты
- **Deployment**: Stateless приложение с возможностью горизонтального масштабирования
- **ConfigMap/Secret**: Конфигурация и секретные данные (DB credentials, Redis)
- **Service**: Внутренний доступ к подам
- **Ingress**: Внешний доступ через API Gateway

### Deployment конфигурация
```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: balance-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: balance-service
  template:
    spec:
      containers:
      - name: balance-service
        image: balance-service:latest
        ports:
        - containerPort: 8000
        env:
          - name: DB_HOST
            value: "postgres-service"
          - name: DB_PASSWORD
            valueFrom:
              secretKeyRef:
                name: db-secret
                key: password
          - name: REDIS_HOST
            value: "redis-service"
          - name: ENVIRONMENT
            value: "production"
        
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
        
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "200m"
```

### Зависимости для DevOps
- **PostgreSQL**: Managed DB или Helm chart
- **Redis**: Managed Redis или Helm chart  
- **Secrets**: DB и Redis credentials через Kubernetes Secrets
- **Security Context**: Pod Security Standards compliance

## 2. Кеширование для повышения производительности

### Рекомендации по кешированию
- **Read-only операции**: Кеширование GET /users/{id}, GET /transactions/{uid}
- **Статические данные**: Пользовательская информация (имя, дата создания)
- **НЕ кешировать**: Баланс пользователя (критичные финансовые данные)
- **Cache-aside pattern**: Проверка кеша → БД → обновление кеша

### Стратегии кеширования
```python
# ✅ Безопасное кеширование пользователя (только статические данные)
@cache(key="user:{user_id}", ttl=600)  # 10 минут
async def get_user_info_cached(user_id: str) -> UserInfo:
    user = await user_repository.get_by_id(user_id)
    # Кешируем только неизменяемые данные
    return UserInfo(id=user.id, name=user.name, created_at=user.created_at)

# ❌ НЕ кешировать баланс - риск несогласованности данных
# Баланс должен всегда читаться из БД для обеспечения консистентности
async def get_user_balance(user_id: str) -> Decimal:
    return await transaction_repository.get_user_current_balance(user_id)
```

### Инвалидация кеша
- **TTL-based**: Автоматическое истечение для статических данных
- **Event-based**: Инвалидация при изменении пользовательской информации
- **Tag-based**: Групповая инвалидация по пользователям

### ⚠️ Важно: Финансовые данные
- **Баланс**: Всегда читать из БД, никогда не кешировать
- **Транзакции**: Кешировать только после подтверждения записи в БД
- **Консистентность**: Приоритет точности данных над производительностью

## 3. Гарантия обработки транзакции ровно 1 раз

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

## 4. Уведомление других сервисов

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

## 5. Контроль качества работы сервиса

### Мониторинг
- **DataDog** (рекомендуется): All-in-one решение с метриками, логами, traces и APM
- **Prometheus + Grafana**: Альтернативное open-source решение для метрик
- **Jaeger/Zipkin**: Distributed tracing (если не используется DataDog APM)
- **ELK Stack**: Централизованные логи (альтернатива DataDog Logs)
- **OpenTelemetry**: Стандартизированное инструментирование для всех решений

### Преимущества DataDog
- **Unified Platform**: Метрики, логи, traces, алерты в одном интерфейсе
- **APM Integration**: Автоматический trace_id correlation между логами и traces
- **Infrastructure Monitoring**: K8s pods, containers, databases из коробки
- **Custom Dashboards**: Business метрики и SLA мониторинг
- **Intelligent Alerting**: ML-based anomaly detection

### Ключевые метрики
- Latency: P50, P95, P99 времени ответа API
- Error Rate: 4xx/5xx ошибки по endpoints
- Throughput: RPS по операциям
- Database: Connection pool, query duration, slow queries
- Redis: Idempotency conflicts, connection pool
- Cache: Hit rate, miss rate, eviction rate, average response time
- Business: Successful transactions/minute, revenue per transaction

### Качество кода
- **Pre-commit hooks**: Black, isort, mypy, flake8
- **CI/CD pipeline**: Автоматические тесты на каждый PR
- **Coverage**: Минимум 90% покрытия кода тестами
- **Security scanning**: Проверка зависимостей на уязвимости

## 6. Гарантия неотрицательного баланса

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
