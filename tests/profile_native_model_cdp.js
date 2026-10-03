const fs=require('node:fs');
const [port,path,seconds]=process.argv.slice(2);
(async()=>{
  const endpoints=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const ws=new WebSocket(endpoints[0].webSocketDebuggerUrl),pending=new Map();let id=0;
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result);}};
  const call=(method,params={})=>new Promise((resolve,reject)=>{const key=++id;pending.set(key,{resolve,reject});ws.send(JSON.stringify({id:key,method,params}));});
  await call('Profiler.enable');await call('Profiler.setSamplingInterval',{interval:1000});await call('Profiler.start');
  fs.writeFileSync(path+'.ready','ready');
  await new Promise(resolve=>setTimeout(resolve,Number(seconds)*1000));
  const result=await call('Profiler.stop');fs.writeFileSync(path,JSON.stringify(result.profile));ws.close();
})().catch(e=>{console.error(e);process.exitCode=1;});
