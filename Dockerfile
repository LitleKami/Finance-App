# --- Purpose Wallet MVP ---
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first so this layer is cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the actual application code
COPY . .

# Railway (and most PaaS hosts) inject $PORT at runtime; ${PORT:-8000}
# falls back to 8000 if it's ever unset (e.g. running the image directly
# without a platform setting it). Explicit "sh -c" guarantees the shell
# actually expands the variable — some invocation paths (a raw `docker run`,
# certain platform "custom command" fields) skip shell expansion otherwise,
# which is what causes literal "$PORT" text to reach uvicorn.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
