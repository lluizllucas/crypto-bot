# Imagem base -- Python 3.11 leve
FROM python:3.11-slim

# Pasta de trabalho dentro do container
WORKDIR /app

# Copia e instala dependencias primeiro (aproveita cache do Docker)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Cria diretorio de logs
RUN mkdir -p /app/logs
ENV PYTHONPATH=/app

# Copia o pacote src completo
COPY src/ ./src/

# Entry-point generico para permitir override por comando no ECS/EventBridge.
# Use sempre modulo (-m) para sys.path incluir /app e `import src` funcionar.
# Exemplos:
# - python -m src.check_sl_tp
# - python -m src.analysis_llm
# - python -m src.bot
ENTRYPOINT ["python"]
CMD ["-m", "src.analysis_llm"]
