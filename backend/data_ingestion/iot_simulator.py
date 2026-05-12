import json, time, random, logging
from datetime import datetime, timezone
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SIMULATOR] %(message)s")
logger = logging.getLogger(__name__)

DEVICES = [
    {"id": "thermostat_01",  "type": "thermostat",    "location": "living_room"},
    {"id": "camera_01",      "type": "ip_camera",     "location": "front_door"},
    {"id": "lock_01",        "type": "smart_lock",    "location": "main_entrance"},
    {"id": "sensor_01",      "type": "motion_sensor", "location": "bedroom"},
    {"id": "hub_01",         "type": "gateway",       "location": "network_hub"},
    {"id": "meter_01",       "type": "power_meter",   "location": "utility_room"},
]

KAFKA_TOPIC = "iot_traffic"
KAFKA_BOOTSTRAP = "localhost:9092"

def normal_traffic(device):
    base = {
        "thermostat":    {"packet_size": random.gauss(128,20),   "frequency": random.gauss(1,0.2),   "port": 1883},
        "ip_camera":     {"packet_size": random.gauss(1400,100), "frequency": random.gauss(30,5),    "port": 554},
        "smart_lock":    {"packet_size": random.gauss(64,10),    "frequency": random.gauss(0.1,0.05),"port": 8883},
        "motion_sensor": {"packet_size": random.gauss(32,5),     "frequency": random.gauss(0.5,0.1), "port": 1883},
        "gateway":       {"packet_size": random.gauss(512,80),   "frequency": random.gauss(10,2),    "port": 443},
        "power_meter":   {"packet_size": random.gauss(64,8),     "frequency": random.gauss(1,0.3),   "port": 502},
    }
    p = base.get(device["type"], base["gateway"])
    return {
        "device_id": device["id"], "device_type": device["type"],
        "location": device["location"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "packet_size": max(1, round(p["packet_size"], 2)),
        "frequency": max(0.01, round(p["frequency"], 4)),
        "src_ip": f"192.168.1.{random.randint(2,20)}",
        "dst_ip": f"52.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}",
        "protocol": random.choice(["MQTT","HTTPS","CoAP"]),
        "port": p["port"],
        "bytes_sent": random.randint(100,5000),
        "bytes_recv": random.randint(50,2000),
        "latency_ms": round(random.gauss(20,5), 2),
        "rssi_dbm": random.randint(-70,-40),
        "cpu_percent": round(random.gauss(15,5), 1),
        "memory_percent": round(random.gauss(40,10), 1),
        "label": "normal",
    }

def anomalous_traffic(device, attack_type):
    r = normal_traffic(device)
    r["label"] = attack_type
    if attack_type == "port_scan":
        r["port"] = random.randint(1,65535); r["frequency"] = random.uniform(50,200)
    elif attack_type == "data_exfiltration":
        r["bytes_sent"] = random.randint(500000,5000000); r["port"] = random.choice([21,22,3389])
    elif attack_type == "ddos":
        r["frequency"] = random.uniform(200,500); r["latency_ms"] = random.uniform(500,2000)
    elif attack_type == "device_malfunction":
        r["cpu_percent"] = random.uniform(90,100); r["latency_ms"] = random.uniform(300,1000)
    return r

def run_simulator():
    for attempt in range(10):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"))
            logger.info("✅ Kafka connected"); break
        except NoBrokersAvailable:
            logger.warning(f"Kafka not ready ({attempt+1}/10)..."); time.sleep(5)
    else:
        raise RuntimeError("Cannot connect to Kafka")

    attacks = ["port_scan","data_exfiltration","ddos","device_malfunction"]
    tick = 0
    logger.info(f"🚀 Simulating {len(DEVICES)} devices → '{KAFKA_TOPIC}'")
    try:
        while True:
            for device in DEVICES:
                if random.random() < 0.08:
                    rec = anomalous_traffic(device, random.choice(attacks))
                    logger.warning(f"🚨 ANOMALY [{rec['label']}] {device['id']}")
                else:
                    rec = normal_traffic(device)
                producer.send(KAFKA_TOPIC, value=rec)
            tick += 1
            if tick % 20 == 0: logger.info(f"📡 {tick * len(DEVICES)} records sent")
            producer.flush(); time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Stopped.")
    finally:
        producer.close()

if __name__ == "__main__":
    run_simulator()
