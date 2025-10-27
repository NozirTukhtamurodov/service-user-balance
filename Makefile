.PHONY: help run stop migrate tests test-unit test-integration

# Default target
.DEFAULT_GOAL := help

# Variables
COMPOSE_FILE := docker-compose.yml
TEST_COMPOSE_FILE := docker-compose.test.yml
APP_SERVICE := application

# Help target
help: ## Show available commands
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Application
run: ## Start the application
	@echo "🚀 Starting the application..."
	docker-compose up --build -d

stop: ## Stop all containers
	@echo "🛑 Stopping containers..."
	docker-compose down

# Database
migrate: ## Run database migrations
	@echo "📊 Running database migrations..."
	docker-compose exec $(APP_SERVICE) alembic upgrade head

# Testing
tests: ## Run all tests
	@echo "🧪 Running all tests..."
	docker-compose -f $(TEST_COMPOSE_FILE) up -d test-db test-redis
	docker-compose -f $(TEST_COMPOSE_FILE) run --rm test-all
	docker-compose -f $(TEST_COMPOSE_FILE) down

test-unit: ## Run unit tests only
	@echo "🧪 Running unit tests..."
	docker-compose -f $(TEST_COMPOSE_FILE) up -d test-redis
	docker-compose -f $(TEST_COMPOSE_FILE) run --rm test-unit
	docker-compose -f $(TEST_COMPOSE_FILE) down

test-integration: ## Run integration tests only
	@echo "🔧 Running integration tests..."
	docker-compose -f $(TEST_COMPOSE_FILE) up -d test-db test-redis
	docker-compose -f $(TEST_COMPOSE_FILE) run --rm test-integration
	docker-compose -f $(TEST_COMPOSE_FILE) down