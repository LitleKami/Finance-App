# --- Purpose Wallet MVP ---
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first so this layer is cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the actual application code
COPY . .

# Railway (and most PaaS hosts) inject $PORT at runtime; default to 8000 for local/plain Docker runs
ENV PORT=8000
EXPOSE 8000

# Shell form so $PORT expands; matches the Procfile command used on Railway
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
