import {useCallback, useEffect, useRef, useState} from 'react';
type RecordData = Record<string, any>;
export function SimulationLab({token, navigate}:{token:string,navigate:(page:string,sessionId?:string,inspectionJob?:string)=>void}) {
 const [catalog,setCatalog]=useState<RecordData>({scenarios:[],enabled:false,can_control:false});
 const [config,setConfig]=useState({scenario:'healthy',fidelity:'L1',speed:2,inspections:true,seed:21000});
 const [history,setHistory]=useState<RecordData[]>([]),[session,setSession]=useState<RecordData|null>(null);
 const [selected,setSelected]=useState(sessionStorage.getItem('tg-demo-session')||''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{if(selected)sessionStorage.setItem('tg-demo-session',selected)},[selected]);
 const selectedRef=useRef(selected);selectedRef.current=selected;const refreshing=useRef(false);
 const createKey=useRef(crypto.randomUUID()); const commandKeys=useRef<Record<string,string>>({});
 const api=useCallback(async(path:string,method='GET',body?:unknown,key?:string)=>{
  const response=await fetch('/api/v1/demo/'+path,{method,headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json',...(key?{'Idempotency-Key':key}:{})},body:body===undefined?undefined:JSON.stringify(body)});
  if(!response.ok)throw Error(`${response.status}: ${await response.text()}`);return response.json();
 },[token]);
 const refresh=useCallback(async()=>{
  if(refreshing.current)return;refreshing.current=true;
  try{const rows=await api('sessions');setHistory(rows);
  const id=selectedRef.current||rows[0]?.id;
  if(id){const data=await api(`sessions/${id}/status`);if(!selectedRef.current||selectedRef.current===id)setSession(data)}}finally{refreshing.current=false}
 },[api,selected]);
 useEffect(()=>{let active=true;api('scenarios').then(x=>{if(active)setCatalog(x)}).catch(e=>setError(String(e)));return()=>{active=false}},[api]);
 useEffect(()=>{let active=true;const load=()=>refresh().catch(e=>{if(active)setError(String(e))});load();const timer=setInterval(load,1500);return()=>{active=false;clearInterval(timer)}},[refresh]);
 function configure(change:RecordData){setConfig(c=>({...c,...change}));createKey.current=crypto.randomUUID()}
 async function control(action:string,id=session?.id){
  if(!id)return;setBusy(true);setError('');const label=id+':'+action;const key=commandKeys.current[label]||crypto.randomUUID();commandKeys.current[label]=key;
  try{await api(`sessions/${id}/${action}`,'POST',undefined,key);delete commandKeys.current[label];await refresh()}catch(e){setError(String(e))}finally{setBusy(false)}
 }
 async function start(){
  setBusy(true);setError('');try{const row=await api('sessions','POST',config,createKey.current);selectedRef.current=row.id;setSelected(row.id);const key=commandKeys.current[row.id+':start']||crypto.randomUUID();commandKeys.current[row.id+':start']=key;await api(`sessions/${row.id}/start`,'POST',undefined,key);createKey.current=crypto.randomUUID();setSession(await api(`sessions/${row.id}/status`));await refresh()}catch(e){setError(String(e))}finally{setBusy(false)}
 }
 const active=history.some(s=>['preparing','ready','running','paused','stopping'].includes(s.state));
 const allowed=catalog.enabled&&catalog.can_control;
 const state=session?.state||'idle'; const scenario=catalog.scenarios.find((s:RecordData)=>s.id===config.scenario);
 const duration=session?.started_at?Math.max(0,((session.ended_at?Date.parse(session.ended_at):Date.now())-Date.parse(session.started_at))/1000):0;
 const inspectionAllowed=!['critical','interruption'].includes(config.scenario);
 return <div className="simulation-lab">
  <div className="simulation-notice"><strong>Software Simulation — No Physical Plant Control</strong><p>Commands operate synthetic observation playback. Stopping a publisher preserves measurements and does not resolve an advisory.</p></div>
  {catalog.scenarios.length===0?<p role="status">Loading simulation catalog…</p>:!allowed&&<p className="notice">{!catalog.enabled?'Simulation execution is disabled in this deployment.':'Viewer access: session status is visible; execution requires an operator.'}</p>}
  {error&&<p role="alert" className="warning">{error}</p>}
  <div className="simulation-grid"><section className="panel"><div className="section-number">01 · Select a scenario</div><h2>What would you like to investigate?</h2>
   <div className="scenario-list">{catalog.scenarios.map((item:RecordData)=><button key={item.id} type="button" aria-pressed={config.scenario===item.id} className={config.scenario===item.id?'scenario selected':'scenario'} disabled={busy||active} onClick={()=>configure({scenario:item.id,fidelity:item.id==='degraded'?'L2':config.fidelity,inspections:item.inspections})}><strong>{item.name}</strong><span>{item.description}</span></button>)}</div>
  </section><div><section className="panel"><div className="section-number">02 · Configure playback</div><h2>{scenario?.name||'Preparing catalog'}</h2><div className="form-grid">{active&&<p className="helper">The current session configuration is fixed. Stop playback before choosing a new configuration.</p>}
   <label>Sensor fidelity<select aria-label="Sensor fidelity" value={config.scenario==='degraded'?'L2':config.fidelity} disabled={busy||active||config.scenario==='degraded'} onChange={e=>configure({fidelity:e.target.value})}><option value="L1">L1 · Nominal virtual sensing</option><option value="L2">L2 · Degraded virtual sensing</option></select></label>
   <label>Playback speed<select aria-label="Playback speed" value={config.speed} disabled={busy||active} onChange={e=>configure({speed:Number(e.target.value)})}>{[1,2,5,10].map(s=><option key={s} value={s}>{s}×</option>)}</select></label>
   <label className="checkbox-label"><input type="checkbox" checked={inspectionAllowed&&config.inspections} disabled={!inspectionAllowed||busy||active} onChange={e=>configure({inspections:e.target.checked})}/>Include measured LiDAR / thermal inspections</label>
   <p className="helper">Seed {config.seed} · immutable session dataset identity is assigned at creation. Fault detection depends on measurement qualification.</p>
  </div><button className="primary" disabled={!allowed||busy||active} onClick={start}>{session&&['completed','stopped','failed'].includes(state)?'Restart scenario as new session':'Start scenario'}</button>{active&&<p className="helper">One session owns this demo namespace. Stop it before starting another.</p>}</section>
  <section className="panel" aria-live="polite"><div className="section-number">03 · Observe execution</div><div className="panel-head"><h2>Session progress</h2><span className={'state state-'+state} data-testid="demo-state">{state}</span></div>
   {session?<><p className="session-identity">{session.id}</p><p>{catalog.scenarios.find((s:RecordData)=>s.id===session.configuration.scenario)?.name||session.configuration.scenario} · {session.configuration.fidelity} · {session.configuration.speed}× · seed {session.configuration.seed}</p>
    {session.desired_state!==state&&<p role="status">Requested: {session.desired_state}. Waiting for controller acknowledgment.</p>}
    <p><strong>Publisher:</strong> {session.publisher_active?'Emitting observations':session.controller_recent?'Not emitting':'Controller heartbeat unavailable / publisher inactive'}</p>
    <p>Stage: {session.phase||'Awaiting controller'}</p><p className="helper">Latest edge receipt: {session.last_accepted_observation?.received||'No accepted observation yet'}</p>{state==='completed'&&<p className="helper">Publisher completed. Analytics and inspection jobs may still be processing.</p>}
    {session.total_observations==null?<p>Preparation is indeterminate until the dataset is ready.</p>:<><progress aria-label="Published deliveries" value={session.published_observations} max={session.total_observations}/><p>{session.published_observations} / {session.total_observations} deliveries acknowledged by MQTT</p></>}
    <dl className="session-metrics"><div><dt>Accepted sensor observations</dt><dd data-testid="demo-accepted">{session.accepted_observations??'Unavailable'}</dd></div><div><dt>Processing backlog</dt><dd>{session.processing_backlog??'Unavailable'}</dd></div><div><dt>Completed inspections</dt><dd>{session.completed_inspections??0}</dd></div><div><dt>Wall-clock elapsed</dt><dd>{duration.toFixed(1)} s</dd></div><div><dt>Source playback position</dt><dd>{session.playback_position_s.toFixed(1)} s</dd></div></dl>
    <div className="playback-controls"><button disabled={!allowed||busy||state!=='running'} onClick={()=>control('pause')}>Pause</button><button disabled={!allowed||busy||state!=='paused'} onClick={()=>control('resume')}>Resume</button><button className="stop" disabled={!allowed||busy||!['preparing','ready','running','paused'].includes(state)} onClick={()=>control('stop')}>Stop</button></div>
    {session.error&&<p role="alert" className="warning">{session.error}</p>}
    <details><summary>Delivery and session provenance</summary><pre>{JSON.stringify({provenance:session.provenance,last_published:session.last_published_observation,last_accepted:session.last_accepted_observation,inspection_jobs:session.inspection_jobs,replay_wall_begin:session.replay_wall_begin,source_begin:session.source_begin,history:session.history},null,2)}</pre></details>
   </>:<p>No simulation session yet. Select a scenario and start a new run.</p>}
   <div className="outcome-links">{['Measurements','Inspections','Advisories','Monitoring'].map(page=><button key={page} onClick={()=>navigate(page,session?.id,session?.inspection_message_id)}>Open {page}</button>)}</div><small>Source recency and platform connection are shown separately in the header. Existing advisories may outlive a session.</small>
  </section></div></div>
  <section className="panel"><h2>Session history</h2><div className="table-wrap"><table><thead><tr><th>Session / created</th><th>Scenario</th><th>Configuration</th><th>State</th><th>Published</th></tr></thead><tbody>{history.map(row=><tr key={row.id}><td><button className="text-button" onClick={()=>setSelected(row.id)}>{row.id}</button><small>{new Date(row.created_at).toLocaleString()}</small></td><td>{catalog.scenarios.find((s:RecordData)=>s.id===row.configuration.scenario)?.name||row.configuration.scenario}</td><td>{row.configuration.fidelity} · {row.configuration.speed}× · seed {row.configuration.seed}</td><td>{row.state}</td><td>{row.published_observations}</td></tr>)}</tbody></table></div></section>
 </div>
}
