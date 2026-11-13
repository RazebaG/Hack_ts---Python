FROM python:3.11-slim

# Evita criação de arquivos .pyc e faz flush imediato do buffer de log
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Diretório de trabalho da aplicação
WORKDIR /app

# Instala dependências de sistema mínimas (curl para healthcheck, tesseract para OCR de digitalização)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências Python em camada separada para cache eficiente
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação e a base do acervo
COPY app/ ./app/
COPY data/ ./data/

# Cria usuário não-privilegiado por boas práticas de segurança
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expõe a porta padrão da API
EXPOSE 8000

# Verificação de saúde embutida no container
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/saude || exit 1

# Comando de inicialização via Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
