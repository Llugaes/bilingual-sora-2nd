'use strict';
const fs=require('fs'),assert=require('node:assert/strict'),path=require('path'),crypto=require('crypto');
const runtimePath=require.resolve('../sora_bilingual/game/scripts/runtime_text.js');
assert.equal(fs.realpathSync(runtimePath),fs.realpathSync(path.resolve(__dirname,'../sora_bilingual/game/scripts/runtime_text.js')));
const {RuntimeText}=require('../sora_bilingual/game/scripts/runtime_text.js');
const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
for(const row of fixture.rows)for(const order of [['primary','secondary','annotation'],['annotation','secondary','primary']]) {
 const warm=new RuntimeText(fixture.model);
 for(const mode of order) {
  const fresh=new RuntimeText(fixture.model);
  assert.deepEqual(fresh.render(row.source,mode),row.modes[mode],row.name+'/'+mode);
  assert.deepEqual(warm.render(row.source,mode),row.modes[mode],row.name+'/warm/'+mode);
 }
}
console.log(JSON.stringify({whole_constructors:fixture.rows.length,three_final_modes:true,positive_owner_injected:false,game_attached:false,runtime_path:runtimePath,runtime_sha256:crypto.createHash('sha256').update(fs.readFileSync(runtimePath)).digest('hex')}));
