import asyncio, json, logging, os
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from influxdb_client import InfluxDBClient
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "iot-super-secret-token"
INFLUX_ORG = "iot_org"
INFLUX_BUCKET = "iot_metrics"

app = FastAPI(title="IoT Anomaly API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def query(flux):
    with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as c:
        tables = c.query_api().query(flux, org=INFLUX_ORG)
    return [r.values for t in tables for r in t.records]

@app.get("/health")
def health(): return {"status": "ok"}

@app.get("/api/stats/summary")
def summary():
    total = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-1h)|>filter(fn:(r)=>r._measurement=="iot_traffic")|>filter(fn:(r)=>r._field=="ensemble_score")|>group()|>count()')
    anom = query(f'from(bucket:"{INFLUX_BUCKET}")|>range(start:-1h)|>filter(fn:(r)=>r._measurement=="iot_traffic" and r.is_anomaly=="True")|>filter(fn:(r)=>r._field=="ensemble_score")|>group()|>count()')
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
