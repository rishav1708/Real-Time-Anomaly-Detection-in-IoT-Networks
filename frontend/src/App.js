import React, { useState, useEffect, useCallback, useRef } from 'react';
import { AreaChart, Area, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts';
import axios from 'axios';

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const WS  = process.env.REACT_APP_WS_URL  || 'ws://localhost:8000/ws/live';
const C = { blue:'#00d4ff', green:'#00ff88', red:'#ff3860', orange:'#ff8c00', yellow:'#ffd700' };
const PIE_COLORS = [C.green, C.yellow, C.orange, C.red];
const SEV = {
  critical:{bg:'#ff386022',b:'#ff3860',t:'#ff3860'},
  high:{bg:'#ff8c0022',b:'#ff8c00',t:'#ff8c00'},
  medium:{bg:'#ffd70022',b:'#ffd700',t:'#ffd700'},
  low:{bg:'#00ff8822',b:'#00ff88',t:'#00ff88'}
};

function usePolling(url, ms=5000) {
  const [data,setData]=useState(null);
  const fetch_=useCallback(async()=>{try{const r=await axios.get(`${API}${url}`);setData(r.data)}catch(e){}},[url]);
  useEffect(()=>{fetch_();const id=setInterval(fetch_,ms);return()=>clearInterval(id)},[fetch_,ms]);
  return data;
}

function useLive(max=30) {
  const [events,setEvents]=useState([]);
  const [conn,setConn]=useState(false);
  useEffect(()=>{
    let ws;
    function connect(){
      ws=new WebSocket(WS);
      ws.onopen=()=>setConn(true);
      ws.onclose=()=>{setConn(false);setTimeout(connect,3000)};
      ws.onmessage=(e)=>{const m=JSON.parse(e.data);if(m.latest_anomaly)setEvents(p=>[m.latest_anomaly,...p].slice(0,max))};
    }
    connect();
    return()=>ws&&ws.close();
  },[max]);
  return {events,conn};
}

function Badge({s}){const c=SEV[s]||SEV.low;return <span style={{background:c.bg,border:`1px solid ${c.b}`,color:c.t,padding:'2px 8px',borderRadius:4,fontSize:11,fontWeight:700,textTransform:'uppercase'}}>{s}</span>}
function Card({title,value,color=C.blue,sub}){return <div style={{background:'#0f1629',border:'1px solid #1e2d4a',borderRadius:12,padding:'20px 24px',position:'relative',overflow:'hidden'}}><div style={{position:'absolute',top:0,left:0,right:0,height:2,background:color}}/><div style={{color:'#64748b',fontSize:12,textTransform:'uppercase',letterSpacing:1}}>{title}</div><div style={{color,fontSize:32,fontWeight:800,marginTop:8,fontFamily:'monospace'}}>{value??'—'}</div>{sub&&<div style={{color:'#64748b',fontSize:12,marginTop:4}}>{sub}</div>}</div>}
function Tip({active,payload,label}){if(!active||!payload?.length)return null;return <div style={{background:'#0f1629',border:'1px solid #1e2d4a',padding:'8px 14px',borderRadius:8}}><div style={{fontSize:11,color:'#64748b',marginBottom:4}}>{label}</div>{payload.map(p=><div key={p.name} style={{fontSize:13,color:p.color}}>{p.name}: {p.value}</div>)}</div>}

// ── CSV Analyzer Component ────────────────────────────────────────────────────
function CSVAnalyzer() {
  const [dragging, setDragging]   = useState(false);
  const [loading,  setLoading]    = useState(false);
  const [results,  setResults]    = useState(null);
  const [error,    setError]      = useState(null);
  const fileRef = useRef();

  const analyze = async (file) => {
    if (!file) return;
    setLoading(true); setError(null); setResults(null);
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await axios.post(`${API}/api/analyze-csv`, form, {
        headers: {'Content-Type': 'multipart/form-data'}
      });
      if (res.data.error) setError(res.data.error);
      else setResults(res.data);
    } catch(e) {
      setError('Failed to analyze file. Make sure it is a valid CSV.');
    }
    setLoading(false);
  };

  const onDrop = (e) => {
    e.preventDefault(); setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file?.name.endsWith('.csv')) analyze(file);
    else setError('Please upload a .csv file');
  };

  const downloadSample = () => {
    window.open(`${API}/api/sample-csv`, '_blank');
  };

  const downloadResults = () => {
    if (!results) return;
    const cols = ['device_id','device_type','packet_size','frequency','bytes_sent',
                  'latency_ms','cpu_percent','memory_percent','port','ensemble_score','severity','is_anomaly','flags'];
    const header = cols.join(',');
    const rows = results.results.map(r => cols.map(c => r[c]??'').join(','));
    const blob = new Blob([header+'\n'+rows.join('\n')], {type:'text/csv'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href=url; a.download='anomaly_results.csv'; a.click();
  };

  return (
    <div style={{background:'#0f1629',border:'1px solid #1e2d4a',borderRadius:12,padding:'24px',marginTop:28}}>
      {/* Header */}
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:20}}>
        <div>
          <h2 style={{fontSize:18,fontWeight:800,marginBottom:4}}>
            🔍 Analyze Your IoT Data
          </h2>
          <p style={{color:'#64748b',fontSize:13}}>
            Upload your own IoT network log CSV and get instant anomaly detection results
          </p>
        </div>
        <button onClick={downloadSample} style={{
          padding:'8px 16px',borderRadius:8,border:'1px solid #00d4ff',
          background:'#00d4ff22',color:C.blue,fontSize:12,cursor:'pointer',fontWeight:600
        }}>
          ⬇ Download Sample CSV
        </button>
      </div>

      {/* Drop Zone */}
      <div
        onDragOver={(e)=>{e.preventDefault();setDragging(true)}}
        onDragLeave={()=>setDragging(false)}
        onDrop={onDrop}
        onClick={()=>fileRef.current.click()}
        style={{
          border:`2px dashed ${dragging?C.blue:'#1e2d4a'}`,
          borderRadius:12, padding:'40px 20px', textAlign:'center',
          cursor:'pointer', transition:'all 0.2s',
          background: dragging?'#00d4ff08':'transparent',
          marginBottom:20,
        }}
      >
        <div style={{fontSize:40,marginBottom:12}}>📂</div>
        <div style={{color:'#e2e8f0',fontSize:15,fontWeight:600,marginBottom:6}}>
          {loading ? '⏳ Analyzing...' : 'Drop your CSV file here or click to browse'}
        </div>
        <div style={{color:'#64748b',fontSize:12}}>
          Supports: packet_size, frequency, bytes_sent, latency_ms, cpu_percent, memory_percent, port
        </div>
        <input ref={fileRef} type="file" accept=".csv"
          style={{display:'none'}}
          onChange={e=>analyze(e.target.files[0])}
        />
      </div>

      {/* Error */}
      {error && (
        <div style={{background:'#ff386022',border:'1px solid #ff3860',borderRadius:8,padding:'12px 16px',marginBottom:16,color:C.red,fontSize:13}}>
          ⚠️ {error}
        </div>
      )}

      {/* Results */}
      {results && (
        <div>
          {/* Summary cards */}
          <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:12,marginBottom:20}}>
            {[
              {label:'Total Rows',    value:results.total_rows,        color:C.blue},
              {label:'Anomalies',     value:results.anomalies,         color:C.red},
              {label:'Clean',         value:results.clean,             color:C.green},
              {label:'Detection Rate',value:`${results.detection_rate}%`,color:C.orange},
            ].map(c=>(
              <div key={c.label} style={{background:'#141d35',border:'1px solid #1e2d4a',borderRadius:10,padding:'16px'}}>
                <div style={{color:'#64748b',fontSize:11,textTransform:'uppercase',letterSpacing:1}}>{c.label}</div>
                <div style={{color:c.color,fontSize:28,fontWeight:800,fontFamily:'monospace',marginTop:6}}>{c.value}</div>
              </div>
            ))}
          </div>

          {/* Severity breakdown */}
          <div style={{display:'flex',gap:10,marginBottom:20,flexWrap:'wrap'}}>
            {['low','medium','high','critical'].map((s,i)=>(
              <div key={s} style={{background:SEV[s].bg,border:`1px solid ${SEV[s].b}`,borderRadius:8,padding:'8px 16px',display:'flex',gap:10,alignItems:'center'}}>
                <span style={{color:SEV[s].t,fontWeight:700,textTransform:'capitalize'}}>{s}</span>
                <span style={{color:'#e2e8f0',fontFamily:'monospace',fontWeight:800}}>{results.by_severity[s]}</span>
              </div>
            ))}
          </div>

          {/* Results table */}
          <div style={{borderRadius:10,overflow:'hidden',border:'1px solid #1e2d4a',marginBottom:16}}>
            <div style={{display:'grid',gridTemplateColumns:'1.5fr 1fr 80px 80px 80px 90px 100px 1.5fr',gap:8,padding:'10px 14px',background:'#141d35',fontSize:11,color:'#64748b',textTransform:'uppercase',letterSpacing:1}}>
              {['Device','Type','Pkt Size','Freq','CPU%','Score','Severity','Flags'].map(h=><div key={h}>{h}</div>)}
            </div>
            <div style={{maxHeight:380,overflowY:'auto'}}>
              {results.results.map((r,i)=>(
                <div key={i} style={{
                  display:'grid',gridTemplateColumns:'1.5fr 1fr 80px 80px 80px 90px 100px 1.5fr',
                  gap:8,padding:'10px 14px',alignItems:'center',
                  borderBottom:'1px solid #1e2d4a',
                  background: r.is_anomaly ? (i%2===0?'#ff386010':'#ff386018') : (i%2===0?'transparent':'#ffffff05'),
                }}>
                  <div style={{fontSize:12,fontFamily:'monospace',fontWeight:r.is_anomaly?700:400}}>{r.device_id||'—'}</div>
                  <div style={{fontSize:11,color:'#64748b'}}>{r.device_type||'—'}</div>
                  <div style={{fontSize:12,fontFamily:'monospace'}}>{Number(r.packet_size||0).toFixed(0)}</div>
                  <div style={{fontSize:12,fontFamily:'monospace'}}>{Number(r.frequency||0).toFixed(1)}</div>
                  <div style={{fontSize:12,fontFamily:'monospace'}}>{Number(r.cpu_percent||0).toFixed(1)}</div>
                  <div style={{fontSize:13,fontFamily:'monospace',color:r.ensemble_score>0.75?C.red:r.ensemble_score>0.5?C.orange:r.ensemble_score>0.25?C.yellow:C.green,fontWeight:700}}>
                    {Number(r.ensemble_score||0).toFixed(3)}
                  </div>
                  <Badge s={r.severity}/>
                  <div style={{fontSize:10,color:'#64748b',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{r.flags||'none'}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Download results */}
          <button onClick={downloadResults} style={{
            padding:'10px 20px',borderRadius:8,border:'1px solid #00ff88',
            background:'#00ff8822',color:C.green,fontSize:13,cursor:'pointer',fontWeight:600
          }}>
            ⬇ Download Results CSV
          </button>
        </div>
      )}
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [range,setRange]=useState('1h');
  const [tab,setTab]=useState('dashboard');
  const summary=usePolling('/api/stats/summary',5000);
  const ts=usePolling(`/api/timeseries/traffic?range=${range}`,10000);
  const devices=usePolling('/api/devices/health',8000);
  const sev=usePolling('/api/anomalies/by-severity',10000);
  const recent=usePolling('/api/anomalies/recent?limit=50',5000);
  const {events,conn}=useLive(30);

  const pieData=sev?['low','medium','high','critical'].map(k=>({name:k,value:sev[k]??0})):[];
  const chartData=(ts||[]).map(d=>({time:new Date(d.time).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}),count:d.count}));
  const alerts=[...events,...(recent||[])].filter((v,i,a)=>a.findIndex(x=>x.timestamp===v.timestamp)===i).slice(0,50);

  return (
    <div style={{minHeight:'100vh',background:'#0a0e1a'}}>
      {/* Header */}
      <header style={{background:'#0f1629',borderBottom:'1px solid #1e2d4a',padding:'16px 32px',display:'flex',alignItems:'center',justifyContent:'space-between'}}>
        <div style={{display:'flex',alignItems:'center',gap:14}}>
          <span style={{fontSize:24}}>🛡️</span>
          <div>
            <div style={{fontSize:18,fontWeight:800}}>IoT <span style={{color:C.blue}}>Anomaly</span> Detector</div>
            <div style={{fontSize:11,color:'#64748b'}}>AI-Powered Network Security Monitor</div>
          </div>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:16}}>
          {/* Nav tabs */}
          <div style={{display:'flex',gap:4,background:'#141d35',borderRadius:8,padding:4}}>
            {[['dashboard','📊 Dashboard'],['analyze','🔍 Analyze CSV']].map(([id,label])=>(
              <button key={id} onClick={()=>setTab(id)} style={{
                padding:'6px 14px',borderRadius:6,border:'none',cursor:'pointer',fontSize:12,fontWeight:600,
                background:tab===id?'#1e2d4a':'transparent',
                color:tab===id?'#e2e8f0':'#64748b',
              }}>{label}</button>
            ))}
          </div>
          <div style={{display:'flex',alignItems:'center',gap:8,fontSize:12}}>
            <span style={{width:8,height:8,borderRadius:'50%',background:conn?C.green:C.red,display:'inline-block'}}/>
            <span style={{color:conn?C.green:C.red}}>{conn?'Live':'Disconnected'}</span>
          </div>
        </div>
      </header>

      <main style={{padding:'24px 32px',maxWidth:1600,margin:'0 auto'}}>
        {tab === 'dashboard' && (
          <>
            <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:16,marginBottom:28}}>
              <Card title="Total Events (1h)" value={summary?.total_events?.toLocaleString()} />
              <Card title="Anomalies (1h)" value={summary?.anomalies_1h} color={C.red} />
              <Card title="Detection Rate" value={summary?`${summary.detection_rate}%`:null} color={C.orange} />
              <Card title="Active Devices" value={summary?.active_devices} color={C.green} sub="Monitored IoT devices" />
            </div>

            <div style={{display:'grid',gridTemplateColumns:'2fr 1fr',gap:20,marginBottom:28}}>
              <div style={{background:'#0f1629',border:'1px solid #1e2d4a',borderRadius:12,padding:'20px 24px'}}>
                <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:16}}>
                  <h2 style={{fontSize:16,fontWeight:700}}>Network Traffic Volume</h2>
                  <div style={{display:'flex',gap:8}}>
                    {['30m','1h','6h'].map(r=>(
                      <button key={r} onClick={()=>setRange(r)} style={{padding:'4px 12px',borderRadius:6,border:'1px solid',borderColor:range===r?C.blue:'#1e2d4a',background:range===r?'#00d4ff22':'transparent',color:range===r?C.blue:'#64748b',fontSize:12,cursor:'pointer'}}>{r}</button>
                    ))}
                  </div>
                </div>
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={chartData}>
                    <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={C.blue} stopOpacity={0.3}/><stop offset="95%" stopColor={C.blue} stopOpacity={0}/></linearGradient></defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e2d4a"/>
                    <XAxis dataKey="time" tick={{fill:'#64748b',fontSize:11}} axisLine={false}/>
                    <YAxis tick={{fill:'#64748b',fontSize:11}} axisLine={false}/>
                    <Tooltip content={<Tip/>}/>
                    <Area type="monotone" dataKey="count" stroke={C.blue} fill="url(#g)" strokeWidth={2} name="Events"/>
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <div style={{background:'#0f1629',border:'1px solid #1e2d4a',borderRadius:12,padding:'20px 24px'}}>
                <h2 style={{fontSize:16,fontWeight:700,marginBottom:16}}>Anomalies by Severity</h2>
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart><Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" paddingAngle={3}>{pieData.map((_,i)=><Cell key={i} fill={PIE_COLORS[i]}/>)}</Pie><Tooltip content={<Tip/>}/><Legend iconType="circle" iconSize={8} formatter={v=><span style={{color:'#e2e8f0',fontSize:12}}>{v}</span>}/></PieChart>
                </ResponsiveContainer>
                <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,marginTop:8}}>
                  {['low','medium','high','critical'].map((k,i)=>(
                    <div key={k} style={{display:'flex',justifyContent:'space-between',fontSize:12}}>
                      <span style={{color:PIE_COLORS[i],textTransform:'capitalize'}}>{k}</span>
                      <span style={{color:'#e2e8f0',fontFamily:'monospace'}}>{sev?.[k]??0}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div style={{display:'grid',gridTemplateColumns:'280px 1fr',gap:20}}>
              <div style={{background:'#0f1629',border:'1px solid #1e2d4a',borderRadius:12,padding:'20px 16px'}}>
                <h2 style={{fontSize:16,fontWeight:700,marginBottom:16}}>Device Health</h2>
                {devices?.length
                  ? devices.map(d=>(
                    <div key={d.device_id} style={{border:'1px solid #1e2d4a',borderRadius:10,padding:'14px',display:'flex',alignItems:'center',gap:12,marginBottom:8}}>
                      <div style={{width:10,height:10,borderRadius:'50%',flexShrink:0,background:{healthy:C.green,degraded:C.yellow,critical:C.red}[d.health]||'#64748b'}}/>
                      <div style={{flex:1,minWidth:0}}>
                        <div style={{fontSize:13,fontWeight:600,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{d.device_id}</div>
                        <div style={{fontSize:11,color:'#64748b'}}>{d.device_type}</div>
                      </div>
                      <Badge s={d.health}/>
                    </div>
                  ))
                  : <div style={{color:'#64748b',fontSize:13}}>Waiting for data...</div>
                }
              </div>
              <div style={{background:'#0f1629',border:'1px solid #1e2d4a',borderRadius:12,overflow:'hidden'}}>
                <div style={{padding:'20px 24px 8px',display:'flex',alignItems:'center',gap:10}}>
                  <h2 style={{fontSize:16,fontWeight:700}}>Alert Feed</h2>
                  {conn&&<span style={{display:'flex',alignItems:'center',gap:5,fontSize:11,color:C.green}}><span style={{width:7,height:7,background:C.green,borderRadius:'50%'}}/>LIVE</span>}
                </div>
                <div style={{display:'grid',gridTemplateColumns:'1fr 130px 100px 80px',gap:12,padding:'8px 16px',borderBottom:'1px solid #1e2d4a',background:'#141d35'}}>
                  {['Device','Time','Severity','Score'].map(h=><div key={h} style={{fontSize:11,color:'#64748b',textTransform:'uppercase',letterSpacing:1}}>{h}</div>)}
                </div>
                <div style={{maxHeight:420,overflowY:'auto'}}>
                  {alerts.length
                    ? alerts.map((e,i)=>(
                      <div key={e.timestamp+i} style={{display:'grid',gridTemplateColumns:'1fr 130px 100px 80px',gap:12,padding:'10px 16px',alignItems:'center',borderBottom:'1px solid #1e2d4a',background:i===0?'#ff386008':'transparent'}}>
                        <div style={{fontSize:13,fontFamily:'monospace'}}>{e.device_id}</div>
                        <div style={{fontSize:11,color:'#64748b'}}>{new Date(e.timestamp).toLocaleTimeString()}</div>
                        <Badge s={e.severity}/>
                        <div style={{fontSize:12,fontFamily:'monospace',color:C.yellow,textAlign:'right'}}>{(e.score??e.ensemble_score??0).toFixed(3)}</div>
                      </div>
                    ))
                    : <div style={{padding:32,textAlign:'center',color:'#64748b',fontSize:13}}>No anomalies yet. Simulator is running...</div>
                  }
                </div>
              </div>
            </div>
          </>
        )}

        {tab === 'analyze' && <CSVAnalyzer />}

        <div style={{marginTop:28,textAlign:'center',color:'#64748b',fontSize:11}}>
          IoT Anomaly Detection · Isolation Forest + LSTM Autoencoder · React + FastAPI
        </div>
      </main>
    </div>
  );
}
