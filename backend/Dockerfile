FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run migrations (non-fatal — log the result, then always start the API so a
# migration hiccup can't take the whole service down) then serve. Production image: no --reload.
CMD ["sh", "-c", "echo '[boot] alembic upgrade head ...'; alembic upgrade head 2>&1; echo \"[boot] alembic_exit=$?\"; exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
