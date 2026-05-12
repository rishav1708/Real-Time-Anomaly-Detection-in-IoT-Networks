# 🛡️ Real-Time Anomaly Detection in IoT Networks

![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)
![TensorFlow](https://img.shields.io/badge/TensorFlow-2.21-orange?logo=tensorflow)
![React](https://img.shields.io/badge/React-18-61dafb?logo=react)
![Kafka](https://img.shields.io/badge/Apache_Kafka-7.5-231F20?logo=apachekafka)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)

An AI-powered real-time security monitoring system that detects anomalies in IoT network traffic using an ensemble of machine learning models, visualized on a live React dashboard.

## 🏗️ Architecture
## ⚡ Tech Stack

| Layer | Technology |
|-------|-----------|
| Message Broker | Apache Kafka |
| ML Models | Isolation Forest + LSTM Autoencoder |
| ML Libraries | TensorFlow, scikit-learn |
| Backend API | FastAPI + WebSockets |
| Database | InfluxDB (time-series) |
| Frontend | React + Recharts |
| DevOps | Docker Compose |

## 🤖 ML Models

### Isolation Forest
- Unsupervised outlier detection on 9 network features
- Detects: port scans, DDoS, data exfiltration, device malfunctions
- Achieves 99% F1-score on test set

### LSTM Autoencoder
- Time-series reconstruction error detection
- Sequence length: 10 time steps per device
- Threshold set at 95th percentile of normal reconstruction error

### Ensemble Scoring
- Combined score: 0.6 × Isolation Forest + 0.4 × LSTM
- Severity levels: Low / Medium / High / Critical

## 📊 Features

- ✅ Real-time dashboard with WebSocket live updates
- ✅ 6 IoT device types — cameras, thermostats, locks, sensors, gateways, power meters
- ✅ 4 attack types — port scan, data exfiltration, DDoS, device malfunction
- ✅ Ensemble ML — Isolation Forest + LSTM Autoencoder
- ✅ Severity classification — Low, Medium, High, Critical
- ✅ Device health monitoring with per-device scoring
- ✅ Fully containerized with Docker Compose

## 🚀 Quick Start

### Prerequisites
- Docker Desktop
- Python 3.10+
- Node.js 18+

### 1. Clone the repo
```bash
git clone https://github.com/rishav1708/Real-Time-Anomaly-Detection-in-IoT-Networks.git
cd Real-Time-Anomaly-Detection-in-IoT-Networks
```

### 2. Start infrastructure
```bash
docker compose up -d
docker compose ps   # verify all 3 containers are running
```

### 3. Set up Python environment
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install numpy==1.26.4 scikit-learn==1.5.0 tensorflow==2.21.0
pip install "fastapi==0.111.0" "uvicorn[standard]==0.29.0" websockets==12.0
pip install kafka-python-ng==2.2.3 joblib==1.4.2 influxdb-client==1.43.0
pip install paho-mqtt==2.0.0 python-dotenv==1.0.1 pydantic==2.7.1 httpx==0.27.0 pandas==2.2.2
```

### 4. Train ML models
```bash
python ml/train_model.py
```

### 5. Start all services (open 3 terminals, activate venv in each)
```bash
# Terminal 1
python data_ingestion/iot_simulator.py

# Terminal 2
python ml/anomaly_detector.py

# Terminal 3
uvicorn api.main:app --reload --port 8000
```

### 6. Start frontend
```bash
cd ../frontend
npm install && npm start
```

### 7. Open dashboard
## 📁 Project Structure
## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stats/summary` | Events, anomaly count, detection rate |
| GET | `/api/anomalies/recent` | Latest anomaly events |
| GET | `/api/timeseries/traffic` | Traffic volume over time |
| GET | `/api/devices/health` | Per-device health scores |
| GET | `/api/anomalies/by-severity` | Count by severity level |
| WS | `/ws/live` | WebSocket live stream |

## 👤 Author

**Rishav Kant**
- GitHub: [@rishav1708](https://github.com/rishav1708)
- LinkedIn: [rishav-kant](https://www.linkedin.com/in/rishav-kant-a09bb7307)

## 📄 License

[MIT](LICENSE)
