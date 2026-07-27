# ============================================================
# Dockerfile — Backend FastAPI (Future Lab Control Center)
# ============================================================
FROM python:3.10-slim

WORKDIR /app

# Instala ferramentas básicas de rede para health check (ping, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia dependências e instala pacotes Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação backend
COPY . /app/

EXPOSE 8000

CMD ["python3", "main.py"]
