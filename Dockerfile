# Imagem base -- Python 3.11 leve
FROM python:3.11-slim

# Pasta de trabalho dentro do container
WORKDIR /app

# Copia e instala dependencias primeiro (aproveita cache do Docker)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Cria diretorio de logs
RUN mkdir -p /app/logs

# Copia o pacote src completo
COPY src/ ./src/

# Entry-point generico para permitir override por comando no ECS/EventBridge.
# Exemplo:
# - python src/check_sl_tp.py
# - python src/analysis_llm.py
ENTRYPOINT ["python"]
CMD ["src/analysis_llm.py"]
