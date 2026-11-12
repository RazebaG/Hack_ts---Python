.PHONY: all help test smoke eval run

all: test smoke

help:
	@echo "Comandos disponíveis (HACKA/TS 2026 - Issue #28):"
	@echo "  make test   - Executa a suite de testes unitários com pytest"
	@echo "  make smoke  - Sobe a API local e valida os 7 casos-chave e CORS"
	@echo "  make eval   - Roda a avaliação de perguntas e respostas (/api/perguntar)"
	@echo "  make run    - Inicia o servidor da API FastAPI na porta 8000"

test:
	pytest -q

smoke:
	bash scripts/smoke.sh

eval:
	python -m eval.rodar

run:
	uvicorn app.main:app --reload --port 8000
