# Makefile для Docker-команд

.PHONY: up build down logs clean test

# Основные команды
up: ## Запустить контейнеры в фоновом режиме
	docker-compose up -d

build: ## Пересобрать контейнеры
	docker-compose build --no-cache

down: ## Остановить и удалить контейнеры
	docker-compose down

logs: ## Просмотр логов (используйте: make logs service=web)
	docker-compose logs -f $(service)

clean: ## Остановить контейнеры и удалить volumes
	docker-compose down -v

# Команды для разработки
dev: ## Запустить с hot-reload (без демона)
	docker-compose up

bash: ## Зайти в контейнер web (интерактивная сессия)
	docker-compose exec web bash

test: ## Запустить тесты
	docker-compose exec web pytest

# Утилиты
psql: ## Подключиться к PostgreSQL
	docker-compose exec postgres psql -U postgres -d app_db

redis-cli: ## Подключиться к Redis
	docker-compose exec redis redis-cli

mongo-shell: ## Подключиться к MongoDB shell
	docker-compose exec mongo mongosh

# Помощь
help: ## Показать эту справку
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'