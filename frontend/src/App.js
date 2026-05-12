import React, { useState, useEffect, useCallback } from 'react';
import { AreaChart, Area, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts';
import axios from 'axios';

const API = 'http://localhost:8000';
const WS  = 'ws://localhost:8000/ws/live';
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

function Card({title,value,color=C.blue,sub}){
  return <div style={{background:'#0f1629',border:'1px solid #1e2d4a',borderRadius:12,padding:'20px 24px',position:'relative',overflow:'hidden'}}>
    <div style={{position:'absolute',top:0,left:0,right:0,height:2,background:color}}/>
    <div style={{color:'#64748b',fontSize:12,textTransform:'uppercase',letterSpacing:1}}>{title}</div>
    <div style={{color,fontSize:32,fontWeight:800,marginTop:8,fontFamily:'monospace'}}>{value??'—'}</div>
    {sub&&<div style={{color:'#64748b',fontSize:12,marginTop:4}}>{sub}</div>}
  </div>
}

function Tip({active,payload,label}){
  if(!active||!payload?.length)return null;
  return <div style={{background:'#0f1629',border:'1px solid #1e2d4a',padding:'8px 14px',borderRadius:8}}>
    <div style={{fontSize:11,color:'#64748b',marginBottom:4}}>{label}</div>
    {payload.map(p=><div key={p.name} style={{fontSize:13,color:p.color}}>{p.name}: {p.value}</div>)}
  </div>
}

export default function App() {
  const [range,setRange]=useState('1h');
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
      <header style={{background:'#0f1629',borderBottom:'1px solid #1e2d4a',padding:'16px 32px',display:'flex',alignItems:'center',justifyContent:'space-between'}}>
        <div style={{display:'flex',alignItems:'center',gap:14}}>
          <span style={{fontSize:24}}>🛡️</span>
          <div>
            <div style={{fontSize:18,fontWeight:800}}>IoT <span style={{color:C.blue}}>Anomaly</span> Detector</div>
            <div style={{fontSize:11,color:'#64748b'}}>AI-Powered Network Security Monitor</div>
          </div>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:8,fontSize:12}}>
          <span style={{width:8,height:8,borderRadius:'50%',background:conn?C.green:C.red,display:'inline-block'}}/>
          <span style={{color:conn?C.green:C.red}}>{conn?'Live':'Disconnected'}</span>
        </div>
      </header>

      <main style={{padding:'24px 32px',maxWidth:1600,margin:'0 auto'}}>
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
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" paddingAngle={3}>
                  {pieData.map((_,i)=><Cell key={i} fill={PIE_COLORS[i]}/>)}
                </Pie>
                <Tooltip content={<Tip/>}/>
                <Legend iconType="circle" iconSize={8} formatter={v=><span style={{color:'#e2e8f0',fontSize:12}}>{v}</span>}/>
              </PieChart>
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
              {conn&&<span style={{display:'flex',alignItems:'center',gap:5,fontSize:11,color:C.green}}>
                <span style={{width:7,height:7,background:C.green,borderRadius:'50%'}}/>LIVE
              </span>}
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

        <div style={{marginTop:28,textAlign:'center',color:'#64748b',fontSize:11}}>
          IoT Anomaly Detection · Isolation Forest + LSTM Autoencoder · React + FastAPI
        </div>
      </main>
    </div>
  );
}
