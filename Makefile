.PHONY: help reset reset-env reset-redis dev dev-test logs

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Reset / Scratch ──────────────────────────────────────────────────────────

reset: ## ⚠ Full reset: wipe .env, flush Redis, restart stack (clears ALL state)
	@echo "⚠️  Resetting TuneBox to factory state..."
	@printf 'PLEX_TOKEN=\nPLEX_SERVER_NAME=\nCLIENT_NAME=\nPLEX_USERNAME=\nADMIN_TOKEN=\n' > .env
	@docker compose restart redis backend frontend 2>/dev/null || docker compose up -d
	@echo "✅ Done. Stack restarted with blank .env. Clear browser localStorage too."
	@echo "   In your browser console:  localStorage.clear()"

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
