import asyncio, json, logging, os, io
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from influxdb_client import InfluxDBClient
import uvicorn
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INFLUX_URL    = os.getenv("INFLUX_URL",    "http://localhost:8086")
INFLUX_TOKEN  = os.getenv("INFLUX_TOKEN",  "iot-super-secret-token")
INFLUX_ORG    = os.getenv("INFLUX_ORG",    "iot_org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "iot_metrics")

app = FastAPI(title="IoT Anomaly API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def query(flux):
    try:
        with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as c:
            tables = c.query_api().query(flux, org=INFLUX_ORG)
        return [r.values for t in tables for r in t.records]
    except Exception as e:
        logger.error(f"Query error: {e}")
        return []

# ── Rule-based anomaly scoring (works without ML models) ─────────────────────
def score_row(row: dict) -> dict:
    score = 0.0
    flags = []

    packet_size    = float(row.get("packet_size",    row.get("packet_size_bytes", 0)) or 0)
    frequency      = float(row.get("frequency",      row.get("packets_per_sec",   0)) or 0)
    bytes_sent     = float(row.get("bytes_sent",     row.get("bytes_out",         0)) or 0)
    latency_ms     = float(row.get("latency_ms",     row.get("latency",           0)) or 0)
    cpu_percent    = float(row.get("cpu_percent",    row.get("cpu",               0)) or 0)
    memory_percent = float(row.get("memory_percent", row.get("memory",            0)) or 0)
    port           = int(float(row.get("port", 443) or 443))

    if frequency > 100:    score += 0.35; flags.append("high_frequency")
    if bytes_sent > 100000:score += 0.30; flags.append("data_exfiltration")
    if latency_ms > 300:   score += 0.20; flags.append("high_latency")
    if cpu_percent > 85:   score += 0.25; flags.append("high_cpu")
    if memory_percent > 90:score += 0.20; flags.append("high_memory")
    if packet_size > 1400: score += 0.15; flags.append("large_packets")
    if port in range(1, 1024) and port not in [80,443,22,21,25,53,1883,8883,554,502]:
        score += 0.15; flags.append("unusual_port")

    score = min(round(score, 4), 1.0)
    sev   = "critical" if score>=0.75 else "high" if score>=0.50 else "medium" if score>=0.25 else "low"
    return {
        **row,
        "ensemble_score": score,
        "is_anomaly":     score >= 0.25,
        "severity":       sev,
        "flags":          ", ".join(flags) if flags else "none",
    }

@app.get("/health")
def health(): return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/api/sample-csv")
def sample_csv():
    """Returns sample CSV structure for users to download."""
    from fastapi.responses import Response
    csv = """device_id,device_type,packet_size,frequency,bytes_sent,bytes_recv,latency_ms,cpu_percent,memory_percent,port
thermostat_01,thermostat,128,1.2,450,200,18.5,12.3,38.1,1883
camera_01,ip_camera,1400,28.5,12000,800,22.1,45.2,52.3,554
lock_01,smart_lock,64,0.1,120,80,19.8,8.1,35.2,8883
attacker_01,unknown,50,180,5000000,100,4.2,22.1,41.2,4444
sensor_01,motion_sensor,32,0.5,90,50,21.3,6.2,28.4,1883
gateway_01,gateway,512,9.8,4500,2100,25.6,18.4,42.1,443"""
    return Response(content=csv, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=sample_iot_data.csv"})

@app.post("/api/analyze-csv")
async def analyze_csv(file: UploadFile = File(...)):
    """Analyze uploaded CSV file for anomalies."""
    try:
        contents = await file.read()
        df = pd.read_csv(io.StringIO(contents.decode("utf-8")))
        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

        results = []
        for _, row in df.iterrows():
            scored = score_row(row.to_dict())
            results.append(scored)

        total     = len(results)
        anomalies = sum(1 for r in results if r["is_anomaly"])
        by_sev    = {"low":0,"medium":0,"high":0,"critical":0}
        for r in results:
            by_sev[r["severity"]] += 1

        return {
            "total_rows":   total,
            "anomalies":    anomalies,
            "clean":        total - anomalies,
            "detection_rate": round(anomalies/max(total,1)*100, 2),
            "by_severity":  by_sev,
            "results":      results,
        }
    except Exception as e:
        logger.error(f"CSV analysis error: {e}")
        return {"error": str(e)}

@app.get("/api/stats/summary")
def summary():
    total = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-1h)|>filter(fn:(r)=>r._measurement=="iot_traffic")|>filter(fn:(r)=>r._field=="ensemble_score")|>group()|>count()')
    anom  = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-1h)|>filter(fn:(r)=>r._measurement=="iot_traffic" and r.is_anomaly=="True")|>filter(fn:(r)=>r._field=="ensemble_score")|>group()|>count()')
    t = total[0]["_value"] if total else 0
    a = anom[0]["_value"] if anom else 0
    return {"total_events": t, "anomalies_1h": a, "detection_rate": round(a/max(t,1)*100,2), "active_devices": 6}

@app.get("/api/anomalies/recent")
def recent(limit: int = Query(50, le=200)):
    rows = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-6h)|>filter(fn:(r)=>r._measurement=="iot_traffic" and r.is_anomaly=="True")|>filter(fn:(r)=>r._field=="ensemble_score")|>sort(columns:["_time"],desc:true)|>limit(n:{limit})')
    return [{"timestamp": r["_time"].isoformat(), "device_id": r.get("device_id"),
             "device_type": r.get("device_type"), "severity": r.get("severity"),
             "ensemble_score": r.get("_value")} for r in rows]

@app.get("/api/timeseries/traffic")
def timeseries(range_: str = Query("1h", alias="range"), window: str = "5m"):
    rows = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-{range_})|>filter(fn:(r)=>r._measurement=="iot_traffic")|>filter(fn:(r)=>r._field=="ensemble_score")|>aggregateWindow(every:{window},fn:count,createEmpty:false)')
    return [{"time": r["_time"].isoformat(), "count": r["_value"]} for r in rows]

@app.get("/api/devices/health")
def devices():
    rows = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-15m)|>filter(fn:(r)=>r._measurement=="iot_traffic")|>filter(fn:(r)=>r._field=="ensemble_score")|>group(columns:["device_id","device_type"])|>mean()')
    return [{"device_id": r.get("device_id"), "device_type": r.get("device_type"),
             "avg_score": round(r.get("_value",0),4),
             "health": "critical" if r.get("_value",0)>0.75 else "degraded" if r.get("_value",0)>0.25 else "healthy"} for r in rows]

@app.get("/api/anomalies/by-severity")
def by_severity():
    out = {}
    for sev in ["low","medium","high","critical"]:
        rows = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-1h)|>filter(fn:(r)=>r._measurement=="iot_traffic" and r.is_anomaly=="True" and r.severity=="{sev}")|>filter(fn:(r)=>r._field=="ensemble_score")|>group()|>count()')
        out[sev] = rows[0]["_value"] if rows else 0
    return out

@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            rows = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-30s)|>filter(fn:(r)=>r._measurement=="iot_traffic" and r.is_anomaly=="True")|>filter(fn:(r)=>r._field=="ensemble_score")|>sort(columns:["_time"],desc:true)|>limit(n:1)')
            payload = {"type":"live_update","timestamp":datetime.now(timezone.utc).isoformat(),
                       "latest_anomaly":{"timestamp":rows[0]["_time"].isoformat(),"device_id":rows[0].get("device_id"),"severity":rows[0].get("severity"),"score":rows[0].get("_value")} if rows else None}
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
