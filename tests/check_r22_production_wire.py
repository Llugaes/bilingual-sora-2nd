"""Check final-render-first behavior of the complete r22 wire in native V8."""

import check_r19_production_wire as harness

harness.PREFIX = "r22"
harness.NATIVE = r"""
rpc.exports={load(model){globalThis.model=model;return {runtime:Script.runtime,
 effect_units:model.details.detail_effect_units.length,
 parameter_units:model.details.detail_effect_units.filter(r=>r.parameter_kinds?.length).length};},
run(rows){const result=[];for(const row of rows){
 for(const mode of ['primary','secondary','annotation']){
  const tr=new RuntimeText(row.fixture_model||globalThis.model),plan=tr.render(row.source,mode,row.key||'',row.scope||'');
  if(JSON.stringify(plan)!==JSON.stringify(row.modes[mode]))throw Error('V8 fresh final render differs: '+row.name+'/'+mode);
  if(row.malformed_ruby&&(RuntimeText.rubyRanges(row.source)!==null||tr.translate(row.source,mode)!==row.source))throw Error('malformed R fallback admitted');
 }
 result.push({name:row.name,level:row.level,three_fresh_final_modes:true});
}
 const source=rows[0].source,plain=source.replace(/<\/?[Cc][0-9a-fA-F]*>|<[sS]\d+>/g,''),
 conflictModel={...globalThis.model,ambiguous_display:[...globalThis.model.ambiguous_display,source,plain]};
 for(const mode of ['primary','secondary','annotation']){
  const plan=new RuntimeText(conflictModel).render(source,mode);
  if(plan.text!==source||plan.layers.length)throw Error('whole conflict admitted');
 }
 for(const value of ['2147483648','-2147483649','9'.repeat(100)])for(const wrapped of [false,true]){
  const atom=(wrapped?'<c698>':'')+'Damage dealt to enemies with Seal +'+value+'%'+(wrapped?'</C>':''),
   original='[Support] HP Regen, Blind '+value+'%';
  for(const text of [atom,original])for(const order of [['primary','secondary','annotation'],['annotation','secondary','primary']]){
   const fresh=new RuntimeText(globalThis.model);
   for(const mode of order){const plan=fresh.render(text,mode);
    if(plan.text!==text||plan.layers.length||fresh.translate(text,mode)!==text)throw Error('native integer overflow admitted');}
  }
 }
 for(const text of ['[Support] HP Regen, <X999>Blind 30%</X>']){
  const p=new RuntimeText(globalThis.model).render(text);
  if(text.includes('<X')&&(p.text!==text||p.layers.length))throw Error('unknown control admitted');
 }
 const role=globalThis.model.details.detail_effect_units.find(r=>r.atomic&&r.source==='Recover %d%% HP/EP, Cure Status Ailments, Cure Stat Debuff');
 if(!role)throw Error('independent valid composite role missing');
 const compound='[Support] '+role.source.replace(/%d/g,'30').replace(/%%/g,'%');
 for(const kind of ['duplicate_valid_unit','compiler_style_blocked_template']){
  const details={...globalThis.model.details};
  if(kind==='duplicate_valid_unit')details.detail_effect_units=[...details.detail_effect_units,{...role,pair:['veto%d','conflict%d']}];
  else{details.detail_effect_units=details.detail_effect_units.filter(r=>r.source!==role.source);details.detail_effect_blocked_numeric=[...details.detail_effect_blocked_numeric,role.pattern];}
  for(const mode of ['primary','secondary','annotation']){
   const p=new RuntimeText({...globalThis.model,details}).render(compound,mode);
   if(p.text!==compound||p.layers.length)throw Error('matched compound refusal bypassed: '+kind+'/'+mode);
  }
 }
 return {passed:true,rows:result,whole_conflict_rejected:true,i32_overflow_rejected:true,
  type17_final_overflow_rejected:true,compound_conflict_and_compiler_veto_rejected:true,malformed_ruby_terminal_refusal:true,game_attached:false};
}};
"""

if __name__ == "__main__":
    harness.main()
