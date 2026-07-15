.PHONY: help reset reset-prod reset-env reset-redis dev dev-test logs

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Reset / Scratch ──────────────────────────────────────────────────────────

reset: ## ⚠ Full reset (mock mode): rebuild, wipe .env, flush Redis — ready for the setup wizard
	@echo "⚠️  Resetting TuneBox to factory state (TESTING=true mock mode)..."
	@printf 'PLEX_TOKEN=\nPLEX_SERVER_NAME=\nCLIENT_NAME=\nPLEX_USERNAME=\nADMIN_TOKEN=\n' > .env
	@TESTING=true docker compose up -d --build 2>/dev/null
	@TESTING=true docker compose restart backend 2>/dev/null
	@echo "   Waiting for backend to be ready..."
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do \
		if curl -sf http://localhost:8000/api/auth/status > /dev/null 2>&1; then \
			break; \
		fi; \
		sleep 1; \
	done
	@docker compose exec -T redis redis-cli FLUSHALL > /dev/null
	@echo "✅ Done — server is reset in mock mode and Redis is flushed."
	@echo ""
	@echo "   Now in EVERY browser you want to reset, open DevTools console and run:"
	@echo "     localStorage.clear()"
	@echo "   Then refresh the page. You should see the Setup Wizard."

reset-prod: ## ⚠ Full reset (production mode): rebuild, wipe .env, flush Redis — requires real Plex credentials
	@echo "⚠️  Resetting TuneBox to factory state (production mode)..."
	@printf 'PLEX_TOKEN=\nPLEX_SERVER_NAME=\nCLIENT_NAME=\nPLEX_USERNAME=\nADMIN_TOKEN=\n' > .env
	@docker compose up -d --build 2>/dev/null
	@docker compose restart backend 2>/dev/null
	@echo "   Waiting for backend to be ready..."
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do \
		if curl -sf http://localhost:8000/api/auth/status > /dev/null 2>&1; then \
			break; \
		fi; \
		sleep 1; \
	done
	@docker compose exec -T redis redis-cli FLUSHALL > /dev/null
	@echo "✅ Done — server is reset in production mode and Redis is flushed."
	@echo ""
	@echo "   Now in EVERY browser you want to reset, open DevTools console and run:"
	@echo "     localStorage.clear()"
	@echo "   Then refresh the page. You should see the Setup Wizard."

reset-env: ## Wipe .env credentials only (does not flush Redis or restart)
	@printf 'PLEX_TOKEN=\nPLEX_SERVER_NAME=\nCLIENT_NAME=\nPLEX_USERNAME=\nADMIN_TOKEN=\n' > .env
	@echo "✅ .env cleared. Restart the backend to pick up changes:"
	@echo "   docker compose restart backend"

reset-redis: ## Flush all Redis keys (clears queue + cached auth state)
	@docker compose exec redis redis-cli FLUSHALL
	@echo "✅ Redis flushed."

# ─── Dev ─────────────────────────────────────────────────────────────────────

dev: ## Start the full stack (production mode)
	docker compose up -d

dev-test: ## Start the full stack with TESTING=true (mock Plex auth)
	TESTING=true docker compose up -d

logs: ## Follow backend logs
	docker compose logs -f backend
