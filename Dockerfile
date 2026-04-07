<<<<<<< HEAD
# Imagem base -- Python 3.12 leve
FROM python:3.12-slim

# Pasta de trabalho dentro do container
WORKDIR /app

# Copia e instala dependencias primeiro (aproveita cache do Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o resto do codigo
COPY bot.py .
COPY config.py .
COPY resumo.py .

# Comando que roda quando o container iniciar
CMD ["python3", "bot.py"]
=======
# Imagem base -- Python 3.12 leve
FROM python:3.12-slim

# Pasta de trabalho dentro do container
WORKDIR /app

# Copia e instala dependencias primeiro (aproveita cache do Docker)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Cria diretorio de logs
RUN mkdir -p /app/logs

# Copia o pacote src completo
COPY src/ ./src/

# Comando que roda quando o container iniciar
CMD ["python", "-m", "src.bot"]
>>>>>>> feat/new-market-design
