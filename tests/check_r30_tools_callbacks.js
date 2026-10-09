'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=process.cwd(),directory=path.join(root,'tests');
const receipt=JSON.parse(fs.readFileSync(process.argv[2]||'generated/r26-p0-local-production-receipt.json','utf8'));
const currentModel=JSON.parse(fs.readFileSync(receipt.model_path,'utf8'));
const r25Receipt=JSON.parse(fs.readFileSync('generated/r25-production-receipt.json','utf8'));
const oldModel=JSON.parse(fs.readFileSync(r25Receipt.model_path,'utf8'));
function core(prior) {
 let code=fs.readFileSync(path.join(directory,'test_native_agent.js'),'utf8');code=code.slice(0,code.indexOf('\ntest('));
 if(prior)for(const [variable,file] of [['AGENT','native_agent.js'],['RESOLVER','runtime_text.js']])
  code=code.replace(new RegExp('const '+variable+' = [^\\n]+'),()=>`const ${variable} = ${JSON.stringify(fs.readFileSync('generated/r26-p0-validation-r25/'+file,'utf8'))};`);
 const module={exports:{}};new Function('require','__dirname','module',code+'\nmodule.exports={makeRuntime};')(require,directory,module);
 return module.exports.makeRuntime;
}
const makeCurrent=core(false),makeOld=core(true),modes=['primary','secondary','annotation'];
const routes=JSON.parse(fs.readFileSync('generated/r26-itemhelp-four-pe-capability-discovery.json','utf8')).samples[0].copy_routes;
const delta=(a,b)=>Object.fromEntries(Object.entries(a).map(([k,v])=>[k,v-b[k]]));
const {RuntimeText}=require(path.join(root,'sora_bilingual/game/scripts/runtime_text.js'));
const translator=new RuntimeText(currentModel);
const bodyRows=JSON.parse(fs.readFileSync('tests/fixtures/r26_p0_resource_bodies.json','utf8'));
let preserved=0,newChecks=0,switches=0;const costs=[];
const old=makeOld(),now=makeCurrent();old.api.load(oldModel,'primary',true,1);now.api.load(currentModel,'primary',true,1);
for(const row of bodyRows)for(const mode of modes)for(const route of routes) {
 old.api.select(mode,true);now.api.select(mode,true);
 const a=old.label(0xdf0000,''),b=now.label(0xdf0000,'');
 const ac={...old.memoryCost},bc={...now.memoryCost};
 old.externalSet(a,row.source,1,route.return_rva);now.externalSet(b,row.source,1,route.return_rva);
 assert.equal(b.text(),a.text());assert.equal(b.text(),translator.render(row.source,mode).text);
 const oldCost=delta(old.memoryCost,ac),newCost=delta(now.memoryCost,bc);
 assert.deepEqual(newCost,oldCost,'existing successful resource native callback read/write budget');
 costs.push({resource:row.id,mode,return_rva:route.return_rva,r25:oldCost,current:newCost});preserved++;
 old.destroy(a);now.destroy(b);
}
const inputs=JSON.parse(fs.readFileSync(process.argv[3]||'generated/r26-p0-producers-after.json','utf8')).cases.filter(r=>r.locale==='en');
for(const row of inputs) {
 const r=now;const label=r.label(0xde0000,'');
 for(const mode of modes) {
  r.api.select(mode,true);r.externalSet(label,row.source);
  assert.equal(label.text(),translator.render(row.source,mode).text,row.name+'/'+mode);newChecks++;
  r.externalSet(label,row.source);assert.equal(label.text(),translator.render(row.source,mode).text);switches++;
 }
 r.api.disable();r.update(label);assert.equal(label.text(),row.source,'disable restores original at native Update');switches++;
 r.api.select('secondary',true);r.update(label);assert.equal(label.text(),translator.render(row.source,'secondary').text);switches++;
 r.destroy(label);
}
const sealed=path.join(root,'dist/comprehensive-1.0.0-dev5-r29-tools-local1/DEV');
const sealedCache=JSON.parse(fs.readFileSync(path.join(sealed,'candidate-cache.json'),'utf8'));
const priorModel=JSON.parse(fs.readFileSync(path.join(sealed,'generated',sealedCache.model_name),'utf8'));
const actualInput=JSON.parse(fs.readFileSync('generated/r30-tools-real-failure-native-oracle.json','utf8')).cases[0];
let modelSwitchChecks=0;
for(const mode of modes){
 now.api.load(priorModel,mode,true,1);const label=now.label(0xdc0000,'');
 now.externalSet(label,actualInput.source);assert(label.text().startsWith(actualInput.source.split('\n')[0]),'sealed r29 must retain failed full header');modelSwitchChecks++;
 now.api.load(currentModel,mode,true,1);now.update(label);
 assert.equal(label.text(),translator.render(actualInput.source,mode).text,'same label after model load');modelSwitchChecks++;
 now.externalSet(label,actualInput.source);assert.equal(label.text(),translator.render(actualInput.source,mode).text,'same bytes after model reload');modelSwitchChecks++;
 now.api.disable();now.update(label);assert.equal(label.text(),actualInput.source);modelSwitchChecks++;
 now.destroy(label);
}
const output={model_only_reload_lifecycle_checks:modelSwitchChecks,r25_complete_body_route_mode_checks:preserved,existing_native_dependency_cost_equal:true,
 new_full_product_callback_modes:newChecks,same_text_switch_disable_reenable_checks:switches,costs,
 cost_scope:'production callback fixture native reads/writes, not actual Frida scan latency or gameplay FPS',game_attached:false};
fs.writeFileSync(process.argv[4]||'generated/r26-p0-local-callbacks.json',JSON.stringify(output,null,2));
console.log(JSON.stringify({...output,costs:undefined}));
