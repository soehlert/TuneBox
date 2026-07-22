.PHONY: help dev reset reset-env reset-redis logs

# Default to TESTING=true (mock Plex library mode) for easy local development
TESTING ?= true
COMPOSE_CMD = TESTING=$(TESTING) docker compose

help: ## Show this help menu
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

dev: ## Start full stack in dev mode (TESTING=true mock Plex library by default; use TESTING=false make dev for live Plex)
	@echo "🚀 Starting TuneBox containers (TESTING=$(TESTING))..."
	$(COMPOSE_CMD) up -d

reset: ## ⚠ Factory reset (wipes .env credentials, rebuilds containers, flushes Redis)
	@echo "⚠️ Resetting TuneBox to factory state (TESTING=$(TESTING))..."
	@printf 'PLEX_TOKEN=\nPLEX_SERVER_NAME=\nCLIENT_NAME=\nPLEX_USERNAME=\nADMIN_TOKEN=\n' > .env
	@$(COMPOSE_CMD) up -d --build 2>/dev/null
	@$(COMPOSE_CMD) restart backend 2>/dev/null
	@echo "   Waiting for backend service to become ready..."
	@for i in $$(seq 1 15); do \
		if curl -sf http://localhost:8000/api/auth/status > /dev/null 2>&1; then \
			break; \
		fi; \
		sleep 1; \
	done
	@docker compose exec -T redis redis-cli FLUSHALL > /dev/null
	@echo "✅ Done — TuneBox is reset (TESTING=$(TESTING)) and Redis is flushed."
	@echo ""
	@echo "   In every browser instance you wish to reset, open DevTools console and run:"
	@echo "     localStorage.clear()"
	@echo "   Then refresh the page to see the Setup Wizard."

reset-env: ## Wipe .env credentials file only (does not flush Redis or restart containers)
	@printf 'PLEX_TOKEN=\nPLEX_SERVER_NAME=\nCLIENT_NAME=\nPLEX_USERNAME=\nADMIN_TOKEN=\n' > .env
	@echo "✅ .env cleared. Restart the backend to apply changes:"
	@echo "   docker compose restart backend"

reset-redis: ## Flush all keys in Redis (clears active queue and playback state)
	docker compose exec redis redis-cli FLUSHALL
	@echo "✅ Redis flushed."

logs: ## Follow live backend logs
	docker compose logs -f backend
