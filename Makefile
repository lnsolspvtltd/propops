.PHONY: help up down logs logs-backend logs-frontend logs-postgres build rebuild clean test shell-backend shell-postgres

help:
	@echo "PropOps Local Dev — Docker Compose Commands"
	@echo ""
	@echo "Usage:"
	@echo "  make up              Start all services (postgres, backend, frontend, adminer)"
	@echo "  make down            Stop all services"
	@echo "  make logs            Tail logs from all services"
	@echo "  make logs-backend    Tail backend logs only"
	@echo "  make logs-frontend   Tail frontend logs only"
	@echo "  make logs-postgres   Tail postgres logs only"
	@echo "  make build           Build Docker images (with --build flag)"
	@echo "  make rebuild         Rebuild images from scratch (no cache)"
	@echo "  make clean           Remove containers, volumes, and networks"
	@echo "  make shell-backend   Open shell in backend container"
	@echo "  make shell-postgres  Open psql shell in postgres"
	@echo "  make test            Run backend tests"
	@echo ""
	@echo "Services:"
	@echo "  Backend:   http://localhost:8000"
	@echo "  Frontend:  http://localhost:3000"
	@echo "  Adminer:   http://localhost:8080 (DB admin UI)"
	@echo "  Postgres:  localhost:5432"
	@echo ""

up:
	docker-compose up --build

down:
	docker-compose down

logs:
	docker-compose logs -f

logs-backend:
	docker-compose logs -f backend

logs-frontend:
	docker-compose logs -f frontend

logs-postgres:
	docker-compose logs -f postgres

build:
	docker-compose build

rebuild:
	docker-compose build --no-cache

clean:
	docker-compose down -v
	docker compose down -v --remove-orphans

shell-backend:
	docker-compose exec backend /bin/bash

shell-postgres:
	docker-compose exec postgres psql -U postgres -d propops

test:
	docker-compose exec backend pytest -v --cov=backend --cov-report=term-missing

.DEFAULT_GOAL := help
