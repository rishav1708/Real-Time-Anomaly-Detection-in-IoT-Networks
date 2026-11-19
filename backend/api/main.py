import asyncio, json, logging, os, io
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from influxdb_client import InfluxDBClient
import uvicorn
import pandas as pd
from collections import deque, Counter
from datetime import timedelta
from pathlib import Path
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INFLUX_URL    = os.getenv("INFLUX_URL",    "http://localhost:8086")
INFLUX_TOKEN  = os.getenv("INFLUX_TOKEN",  "iot-super-secret-token")
INFLUX_ORG    = os.getenv("INFLUX_ORG",    "iot_org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "iot_metrics")

# Demo mode: no InfluxDB configured -> simulate traffic in memory so the
# dashboard works as a single free container (e.g. Cloud Run, HF Spaces).
DEMO = not os.getenv("INFLUX_URL")
TICK = 2  # seconds between simulated readings per device
_events = deque(maxlen=6 * 3600 // TICK * 6)  # ~6h of history
_last = None

def _sync():
    """Generate readings up to now. Lazy catch-up instead of a background task,
    so it keeps working when the host pauses CPU between requests."""
    global _last
    from data_ingestion.cloud_simulator import DEVICES, generate_record
    now = datetime.now(timezone.utc)
    if _last is None or now - _last > timedelta(hours=6):
        _last = now - timedelta(hours=6)
    while _last + timedelta(seconds=TICK) <= now:
        _last += timedelta(seconds=TICK)
        for d in DEVICES:
            _events.append({**generate_record(d), "time": _last})

def _since(seconds, anomalies_only=False):
    _sync()
    cut = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return [e for e in _events if e["time"] >= cut and (e["is_anomaly"] or not anomalies_only)]

def _secs(span: str) -> int:
    return int(span[:-1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[span[-1]]

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
    if DEMO:
        ev = _since(3600); a = sum(e["is_anomaly"] for e in ev)
        return {"total_events": len(ev), "anomalies_1h": a, "detection_rate": round(a/max(len(ev),1)*100,2), "active_devices": 6}
    total = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-1h)|>filter(fn:(r)=>r._measurement=="iot_traffic")|>filter(fn:(r)=>r._field=="ensemble_score")|>group()|>count()')
    anom  = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-1h)|>filter(fn:(r)=>r._measurement=="iot_traffic" and r.is_anomaly=="True")|>filter(fn:(r)=>r._field=="ensemble_score")|>group()|>count()')
    t = total[0]["_value"] if total else 0
    a = anom[0]["_value"] if anom else 0
    return {"total_events": t, "anomalies_1h": a, "detection_rate": round(a/max(t,1)*100,2), "active_devices": 6}

@app.get("/api/anomalies/recent")
def recent(limit: int = Query(50, le=200)):
    if DEMO:
        rows = sorted(_since(6*3600, True), key=lambda e: e["time"], reverse=True)[:limit]
        return [{"timestamp": e["time"].isoformat(), "device_id": e["device_id"], "device_type": e["device_type"],
                 "severity": e["severity"], "ensemble_score": e["ensemble_score"]} for e in rows]
    rows = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-6h)|>filter(fn:(r)=>r._measurement=="iot_traffic" and r.is_anomaly=="True")|>filter(fn:(r)=>r._field=="ensemble_score")|>sort(columns:["_time"],desc:true)|>limit(n:{limit})')
    return [{"timestamp": r["_time"].isoformat(), "device_id": r.get("device_id"),
             "device_type": r.get("device_type"), "severity": r.get("severity"),
             "ensemble_score": r.get("_value")} for r in rows]

@app.get("/api/timeseries/traffic")
def timeseries(range_: str = Query("1h", alias="range"), window: str = "5m"):
    if DEMO:
        w = _secs(window)
        buckets = Counter(int(e["time"].timestamp()) // w * w + w for e in _since(_secs(range_)))
        return [{"time": datetime.fromtimestamp(t, timezone.utc).isoformat(), "count": n} for t, n in sorted(buckets.items())]
    rows = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-{range_})|>filter(fn:(r)=>r._measurement=="iot_traffic")|>filter(fn:(r)=>r._field=="ensemble_score")|>aggregateWindow(every:{window},fn:count,createEmpty:false)')
    return [{"time": r["_time"].isoformat(), "count": r["_value"]} for r in rows]

@app.get("/api/devices/health")
def devices():
    if DEMO:
        by = {}
        for e in _since(15*60): by.setdefault((e["device_id"], e["device_type"]), []).append(e["ensemble_score"])
        out = []
        for (d, t), v in by.items():
            m = sum(v)/len(v)
            out.append({"device_id": d, "device_type": t, "avg_score": round(m,4),
                        "health": "critical" if m>0.75 else "degraded" if m>0.25 else "healthy"})
        return out
    rows = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-15m)|>filter(fn:(r)=>r._measurement=="iot_traffic")|>filter(fn:(r)=>r._field=="ensemble_score")|>group(columns:["device_id","device_type"])|>mean()')
    return [{"device_id": r.get("device_id"), "device_type": r.get("device_type"),
             "avg_score": round(r.get("_value",0),4),
             "health": "critical" if r.get("_value",0)>0.75 else "degraded" if r.get("_value",0)>0.25 else "healthy"} for r in rows]

@app.get("/api/anomalies/by-severity")
def by_severity():
    if DEMO:
        c = Counter(e["severity"] for e in _since(3600, True))
        return {sev: c[sev] for sev in ["low","medium","high","critical"]}
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
            if DEMO:
                ev = _since(30, True)
                e = ev[-1] if ev else None
                await websocket.send_text(json.dumps({"type":"live_update","timestamp":datetime.now(timezone.utc).isoformat(),
                    "latest_anomaly":{"timestamp":e["time"].isoformat(),"device_id":e["device_id"],"severity":e["severity"],"score":e["ensemble_score"]} if e else None}))
                await asyncio.sleep(2)
                continue
            rows = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-30s)|>filter(fn:(r)=>r._measurement=="iot_traffic" and r.is_anomaly=="True")|>filter(fn:(r)=>r._field=="ensemble_score")|>sort(columns:["_time"],desc:true)|>limit(n:1)')
            payload = {"type":"live_update","timestamp":datetime.now(timezone.utc).isoformat(),
                       "latest_anomaly":{"timestamp":rows[0]["_time"].isoformat(),"device_id":rows[0].get("device_id"),"severity":rows[0].get("severity"),"score":rows[0].get("_value")} if rows else None}
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass

# Serve the built React dashboard from the same container (see root Dockerfile)
_static = Path(__file__).resolve().parent.parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
