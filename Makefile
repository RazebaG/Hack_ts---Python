.PHONY: all help test smoke eval run docker-build docker-run

all: test smoke

help:
	@echo "Comandos disponíveis (HACKA/TS 2026 - Issue #28 & Deploy):"
	@echo "  make test         - Executa a suite de testes unitários com pytest"
	@echo "  make smoke        - Sobe a API local e valida os 7 casos-chave e CORS"
	@echo "  make eval         - Roda a avaliação de perguntas e respostas (/api/perguntar)"
	@echo "  make run          - Inicia o servidor da API FastAPI na porta 8000"
	@echo "  make docker-build - Constrói a imagem Docker do backend"
	@echo "  make docker-run   - Executa o container Docker na porta 8000"

test:
	pytest -q

smoke:
	bash scripts/smoke.sh

eval:
	python -m eval.rodar

run:
	uvicorn app.main:app --reload --port 8000

docker-build:
	docker build -t acme-normas-backend:latest .

docker-run:
	docker run -p 8000:8000 --env-file .env acme-normas-backend:latest
