'use strict';
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const root=process.cwd(),directory=path.join(root,'tests');
const rows=JSON.parse(fs.readFileSync(path.join(directory,'fixtures/r26_p0_resource_bodies.json'),'utf8'));
const discovery=JSON.parse(fs.readFileSync('generated/r26-itemhelp-four-pe-capability-discovery.json','utf8'));
const routes=discovery.samples[0].copy_routes.map(r=>({name:'item_help_copy_'+(r.span[1]-r.span[0])+'_return',rva:r.return_rva}));
let code=fs.readFileSync(path.join(directory,'test_native_agent.js'),'utf8');code=code.slice(0,code.indexOf('\ntest('));
code=code.replace('    const context=vm.createContext(sandbox);',`
    let p0RangeQueries=0;
    for(const route of ${JSON.stringify(routes)})REPORT.native[route.name]={rva:route.rva,bytes:'0'.repeat(32)};
    sandbox.Process.findRangeByAddress=()=>{p0RangeQueries++;return null;};
    const context=vm.createContext(sandbox);`);
code=code.replace('        diagnosticStorage(){','        p0RangeQueries(){return p0RangeQueries;},\n        diagnosticStorage(){');
const core={exports:{}};new Function('require','__dirname','module',code+'\nmodule.exports={makeRuntime};')(require,directory,core);
const {RuntimeText}=require(path.join(root,'sora_bilingual/game/scripts/runtime_text.js'));
let checks=0;
for(const row of rows)for(const mode of ['primary','secondary','annotation']) {
 const model={pairs:{[row.source]:row.pair},plain_pairs:{[row.source]:row.pair}};
 const expected=new RuntimeText(model).render(row.source,mode).text;
 const baseline=core.exports.makeRuntime();baseline.api.load(model,mode,true,1);const ordinary=baseline.label(0xdf0000,'');
 const before={...baseline.memoryCost};baseline.externalSet(ordinary,row.source);
 const cost=Object.fromEntries(Object.entries(baseline.memoryCost).map(([k,v])=>[k,v-before[k]]));assert.equal(ordinary.text(),expected);
 for(const route of routes) {
  const r=core.exports.makeRuntime();r.api.load(model,mode,true,1);const label=r.label(0xdf0000,'');const prior={...r.memoryCost};
  r.externalSet(label,row.source,1,route.rva);
  assert.equal(label.text(),expected,row.id+'/'+mode+'/'+route.name);
  const delta=Object.fromEntries(Object.entries(r.memoryCost).map(([k,v])=>[k,v-prior[k]]));
  assert.deepEqual(delta,cost,'known complete translations must retain ordinary r25 callback cost');
  assert.equal(r.p0RangeQueries(),0,'no new item record/address proof on known complete translations');r.destroy(label);checks++;
 }
}
const result={created_utc:new Date().toISOString(),real_resource_cases:rows.length,four_return_route_mode_checks:checks,
    old_callback_cost_preserved:true,game_attached:false,actual_ui_setter_captured:false};
if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify(result,null,2));console.log(JSON.stringify(result));
