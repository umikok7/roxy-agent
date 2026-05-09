SHELL := /bin/bash

.PHONY: bootstrap up down restart status health logs backend-logs frontend-logs desktop-logs reindex-kb help

help:
	@echo "Targets:"
	@echo "  make bootstrap     Install Python/frontend/desktop dependencies"
	@echo "  make up            Start qdrant + backend + frontend + desktop"
	@echo "  make down          Stop all services"
	@echo "  make restart       Restart all services"
	@echo "  make status        Show service status"
	@echo "  make health        Check service health"
	@echo "  make logs SERVICE=backend LINES=100"
	@echo "  make backend-logs  Tail backend log"
	@echo "  make frontend-logs Tail frontend log"
	@echo "  make desktop-logs  Tail desktop log"
	@echo "  make reindex-kb    Rebuild knowledge base index"

bootstrap:
	@./scripts/devctl.sh bootstrap

up:
	@./scripts/devctl.sh up

down:
	@./scripts/devctl.sh down

restart:
	@./scripts/devctl.sh restart

status:
	@./scripts/devctl.sh status

health:
	@./scripts/devctl.sh health

logs:
	@./scripts/devctl.sh logs $(or $(SERVICE),backend) $(or $(LINES),50)

backend-logs:
	@./scripts/devctl.sh logs backend $(or $(LINES),50)

frontend-logs:
	@./scripts/devctl.sh logs frontend $(or $(LINES),50)

desktop-logs:
	@./scripts/devctl.sh logs desktop $(or $(LINES),50)

reindex-kb:
	@./scripts/devctl.sh reindex-kb
