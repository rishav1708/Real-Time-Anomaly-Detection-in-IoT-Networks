"""
Cloud IoT Simulator — writes directly to InfluxDB Cloud (no Kafka needed)
"""
import time, random, logging
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SIMULATOR] %(message)s")
logger = logging.getLogger(__name__)

INFLUX_URL    = os.getenv("INFLUX_URL",    "http://localhost:8086")
INFLUX_TOKEN  = os.getenv("INFLUX_TOKEN",  "iot-super-secret-token")
INFLUX_ORG    = os.getenv("INFLUX_ORG",    "iot_org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "iot_metrics")

DEVICES = [
    {"id": "thermostat_01",  "type": "thermostat",    "location": "living_room"},
    {"id": "camera_01",      "type": "ip_camera",     "location": "front_door"},
    {"id": "lock_01",        "type": "smart_lock",    "location": "main_entrance"},
    {"id": "sensor_01",      "type": "motion_sensor", "location": "bedroom"},
    {"id": "hub_01",         "type": "gateway",       "location": "network_hub"},
    {"id": "meter_01",       "type": "power_meter",   "location": "utility_room"},
]

# Simple Isolation Forest scoring (rule-based for cloud, no model needed)
def compute_score(rec, is_anomaly):
    if not is_anomaly:
        return round(random.uniform(0.05, 0.20), 4)
    attack = rec.get("attack_type", "")
    if attack == "ddos":           return round(random.uniform(0.80, 0.99), 4)
    if attack == "data_exfil":     return round(random.uniform(0.75, 0.95), 4)
    if attack == "port_scan":      return round(random.uniform(0.60, 0.85), 4)
    if attack == "malfunction":    return round(random.uniform(0.55, 0.80), 4)
    return round(random.uniform(0.50, 0.90), 4)

def severity(score):
    if score >= 0.75: return "critical"
    if score >= 0.50: return "high"
    if score >= 0.25: return "medium"
    return "low"

def generate_record(device):
    is_anomaly = random.random() < 0.08
    attack_type = random.choice(["ddos","data_exfil","port_scan","malfunction"]) if is_anomaly else ""
    base = {
        "packet_size":    random.gauss(1400,50)   if attack_type=="ddos"       else random.gauss(300,150),
        "frequency":      random.uniform(200,500) if attack_type=="ddos"       else random.gauss(5,3),
        "bytes_sent":     random.randint(500000,5000000) if attack_type=="data_exfil" else random.randint(100,5000),
        "latency_ms":     random.uniform(500,2000) if attack_type=="ddos"      else random.gauss(20,5),
        "cpu_percent":    random.uniform(90,100)  if attack_type=="malfunction" else random.gauss(15,5),
        "memory_percent": random.uniform(95,100)  if attack_type=="malfunction" else random.gauss(40,10),
    }
    score = compute_score({"attack_type": attack_type}, is_anomaly)
    return {**base, "device_id": device["id"], "device_type": device["type"],
            "location": device["location"], "is_anomaly": is_anomaly,
            "attack_type": attack_type, "ensemble_score": score, "severity": severity(score)}

def run():
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    writer = client.write_api(write_options=SYNCHRONOUS)
    logger.info("🚀 Cloud simulator started → InfluxDB")
    tick = 0
    try:
        while True:
            for device in DEVICES:
                rec = generate_record(device)
                point = (Point("iot_traffic")
                    .tag("device_id",   rec["device_id"])
                    .tag("device_type", rec["device_type"])
                    .tag("location",    rec["location"])
                    .tag("severity",    rec["severity"])
                    .tag("is_anomaly",  str(rec["is_anomaly"]))
                    .field("ensemble_score",  rec["ensemble_score"])
                    .field("packet_size",     max(1.0, rec["packet_size"]))
                    .field("frequency",       max(0.01, rec["frequency"]))
                    .field("bytes_sent",      float(rec["bytes_sent"]))
                    .field("latency_ms",      max(1.0, rec["latency_ms"]))
                    .field("cpu_percent",     max(0.0, rec["cpu_percent"]))
                    .field("memory_percent",  max(0.0, rec["memory_percent"])))
                writer.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                if rec["is_anomaly"]:
                    logger.warning(f"🚨 {rec['device_id']} | {rec['severity']} | {rec['ensemble_score']}")
            tick += 1
            if tick % 20 == 0: logger.info(f"✅ {tick * len(DEVICES)} records written")
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Stopped.")
    finally:
        client.close()

if __name__ == "__main__":
    run()
