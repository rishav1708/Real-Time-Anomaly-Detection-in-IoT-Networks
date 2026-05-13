FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install "fastapi==0.111.0" "uvicorn[standard]==0.29.0" websockets==12.0 && \
    pip install influxdb-client==1.43.0 python-dotenv==1.0.1 pydantic==2.7.1 httpx==0.27.0

COPY . .

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
