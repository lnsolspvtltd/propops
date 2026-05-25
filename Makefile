.PHONY: help up down logs build rebuild clean test frontend-install backend-install db-reset health

help:
	@echo "PropOps Development Commands"
	@echo ""
	@echo "  make up              - Start all services (postgres, backend, frontend, adminer)"
	@echo "  make down            - Stop all services"
	@echo "  make rebuild         - Rebuild Docker images and start"
	@echo "  make logs            - Stream logs from all services"
	@echo "  make logs-backend    - Stream backend logs only"
	@echo "  make logs-frontend   - Stream frontend logs only"
	@echo "  make clean           - Remove all containers, volumes, and build artifacts"
	@echo "  make db-reset        - Drop and recreate database"
	@echo "  make health          - Check health of all services"
	@echo "  make test-backend    - Run backend tests"
	@echo "  make backend-install - Install backend dependencies"
	@echo "  make frontend-install- Install frontend dependencies"
	@echo ""
	@echo "Quick Start:"
	@echo "  1. cp .env.example .env"
	@echo "  2. make up"
	@echo "  3. Open http://localhost:3000"

up:
	docker-compose up --build

down:
	docker-compose down

rebuild:
	docker-compose down
	docker-compose up --build

logs:
	docker-compose logs -f

logs-backend:
	docker-compose logs -f backend

logs-frontend:
	docker-compose logs -f frontend

logs-db:
	docker-compose logs -f postgres

health:
	@echo "Checking service health..."
	@docker-compose exec -T backend curl -s http://localhost:8000/api/v1/health | jq . || echo "Backend: DOWN"
	@echo "Frontend: http://localhost:3000"
	@echo "Adminer (DB UI): http://localhost:8081"
	@docker-compose exec -T postgres pg_isready -U postgres -d propops && echo "Database: UP" || echo "Database: DOWN"

clean:
	docker-compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true

db-reset:
	docker-compose exec -T postgres psql -U postgres -d propops -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	@echo "Database schema reset. Restart containers to reinitialize."

test-backend:
	docker-compose exec -T backend pytest tests/ -v --cov=backend --cov-report=term-missing

backend-install:
	docker-compose run --rm backend pip install -r requirements.txt

frontend-install:
	docker-compose run --rm frontend npm install

shell-backend:
	docker-compose exec backend bash

shell-frontend:
	docker-compose exec frontend sh

shell-db:
	docker-compose exec postgres psql -U postgres -d propops
---