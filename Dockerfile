FROM python:3.9-slim

WORKDIR /app

RUN apt update && apt install -y --no-install-recommends \
    libpq-dev \
    gcc \
    libffi-dev \
    libssl-dev \
    build-essential

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]