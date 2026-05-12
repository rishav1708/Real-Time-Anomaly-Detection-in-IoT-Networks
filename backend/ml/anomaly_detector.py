import os, json, time, logging
import numpy as np
import joblib
import tensorflow as tf
from collections import deque
from kafka import KafkaConsumer
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [DETECTOR] %(message)s")
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = "localhost:9092"
KAFKA_TOPIC = "iot_traffic"
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "iot-super-secret-token"
INFLUX_ORG = "iot_org"
INFLUX_BUCKET = "iot_metrics"
MODEL_DIR = os.path.join(os.path.dirname(__file__), "saved_models")
FEATURES = ["packet_size","frequency","bytes_sent","bytes_recv",
            "latency_ms","rssi_dbm","cpu_percent","memory_percent","port"]
SEQUENCE_LEN = 10

class Models:
    def __init__(self):
        self.scaler = joblib.load(os.path.join(MODEL_DIR,"scaler.joblib"))
        self.iso = joblib.load(os.path.join(MODEL_DIR,"isolation_forest.joblib"))
        self.lstm = tf.keras.models.load_model(os.path.join(MODEL_DIR,"lstm_autoencoder.keras"))
        with open(os.path.join(MODEL_DIR,"lstm_meta.json")) as f:
            meta = json.load(f)
        self.thresh = meta["threshold"]
        self.windows = {}
        logger.info("✅ Models loaded")

    def predict(self, rec):
        raw = np.array([[rec.get(f,0) for f in FEATURES]], dtype=np.float32)
        sc = self.scaler.transform(raw)
        iso_score = float(-self.iso.score_samples(sc)[0])
        iso_flag = self.iso.predict(sc)[0] == -1
        if rec["device_id"] not in self.windows:
            self.windows[rec["device_id"]] = deque(maxlen=SEQUENCE_LEN)
        self.windows[rec["device_id"]].append(sc[0])
        lstm_score, lstm_flag = 0.0, False
        if len(self.windows[rec["device_id"]]) == SEQUENCE_LEN:
            seq = np.array(self.windows[rec["device_id"]])[np.newaxis]
            recon = self.lstm.predict(seq, verbose=0)
            lstm_score = float(np.mean(np.power(seq-recon,2)))
            lstm_flag = lstm_score > self.thresh
        score = round(min(iso_score/0.8,1)*0.6 + min(lstm_score/max(self.thresh*3,1e-9),1)*0.4, 4)
        sev = "critical" if score>=0.75 else "high" if score>=0.5 else "medium" if score>=0.25 else "low"
        return {**rec, "iso_score": round(iso_score,4), "lstm_score": round(lstm_score,6),
                "ensemble_score": score, "is_anomaly": iso_flag or lstm_flag, "severity": sev}

def run():
    models = Models()
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    writer = client.write_api(write_options=SYNCHRONOUS)
    consumer = KafkaConsumer(KAFKA_TOPIC, bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset="latest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")))
    logger.info(f"👂 Listening on '{KAFKA_TOPIC}'...")
    count = 0
    for msg in consumer:
        try:
            e = models.predict(msg.value)
            p = (Point("iot_traffic")
                 .tag("device_id", e["device_id"]).tag("device_type", e["device_type"])
                 .tag("severity", e["severity"]).tag("is_anomaly", str(e["is_anomaly"]))
                 .field("ensemble_score", e["ensemble_score"])
                 .field("cpu_percent", e["cpu_percent"])
                 .field("latency_ms", e["latency_ms"]))
            writer.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=p)
            count += 1
            if e["is_anomaly"]:
                logger.warning(f"🚨 {e['device_id']} | {e['severity']} | {e['ensemble_score']}")
            elif count % 50 == 0:
                logger.info(f"✅ {count} records processed")
        except Exception as ex:
            logger.error(f"Error: {ex}")

if __name__ == "__main__":
    run()
