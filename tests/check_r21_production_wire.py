"""r21 complete indexed wire and targeted final plans in owned Frida V8."""

import json
import check_r19_production_wire as harness

harness.PREFIX = "r21"
harness.NATIVE = r"""
rpc.exports={load(model){globalThis.model=model;
 return {runtime:Script.runtime,effect_units:model.details.detail_effect_units.length,
         compact_headers:model.skill_help_headers.compact_formats.length,
         complete_npc_facilities:Object.keys(model.npc_facilities).length};},
run(rows){const result=[];for(const row of rows){
 const tr=new RuntimeText(globalThis.model),source=row.source,
       primary=tr.translate(source,'primary'),secondary=tr.translate(source,'secondary'),plan=tr.render(source);
 if(primary!==row.primary||secondary!==row.secondary||JSON.stringify(plan)!==JSON.stringify(row.plan))
   throw Error('V8 final render differs: '+row.name);
 if(row.modes)for(const mode of ['annotation','primary','secondary']){
   const fresh=new RuntimeText(globalThis.model).render(source,mode),
         words=(fresh.text+' '+fresh.layers.map(l=>l.text).join(' ')).replace(/<[^<>]*>/g,'').match(/[A-Za-z]+/g)||[];
   if(JSON.stringify(fresh)!==JSON.stringify(row.modes[mode])||words.some(w=>!row.baselineEnglish[mode].includes(w)))
     throw Error('Captured r20 success regressed in final V8 mode: '+row.name+' / '+mode);
   if(source.includes('Delay')&&(fresh.text.includes('Delay')||
       (mode!=='secondary'&&!fresh.text.includes('遅延'))||
       (mode!=='primary'&&!(fresh.text+fresh.layers.map(l=>l.text).join('')).includes('延迟'))))
     throw Error('Captured Arts Delay role was swallowed: '+mode);
 }
 result.push({name:row.name,level:row.level,roles:plan.layers.filter(l=>l.semantic_ids?.length).length});
}
 for(const value of ['2147483648','-2147483649','9'.repeat(100)]){
   for(const suffix of ['Blind '+value+'%','STR↑ ('+value+' turns)','Damage dealt to enemies with Seal +'+value+'%']){
     for(const prefix of ['', '[Physical] '])for(const wrapped of [false,true]){
       const original=prefix+(wrapped?'<c698>':'')+suffix+(wrapped?'</C>':'');
       for(const order of [['primary','secondary','annotation'],['annotation','secondary','primary']]){
         const fresh=new RuntimeText(globalThis.model);
         for(const mode of order){const plan=fresh.render(original,mode);
           if(fresh.translate(original,mode)!==original||plan.text!==original||plan.layers.length)
             throw Error('typed overflow revived: '+original+' / '+mode);
         }
       }
     }
   }
 }
 const source=rows[0].source,conflict=new RuntimeText({...globalThis.model,
   ambiguous_display:[...globalThis.model.ambiguous_display,source]});
 if(conflict.render(source).text!==source||conflict.render(source).layers.length)throw Error('whole conflict admitted');
 const facility='<c990>Arseille - Factory</c>',facilityConflict=new RuntimeText({...globalThis.model,
   ambiguous_display:[...globalThis.model.ambiguous_display,facility]});
 if(facilityConflict.render(facility).text!==facility)throw Error('facility conflict admitted');
 const visible=s=>s.replace(/<[^<>]*>/g,'').trim(),oracle=new RuntimeText(globalThis.model),families={};
 for(const row of globalThis.statusOracleInputs){
   const primary=oracle.translate(row.source,'primary'),secondary=oracle.translate(row.source,'secondary'),plan=oracle.render(row.source),
         payload=plan.layers.map(l=>l.text).join('')+[...plan.text.matchAll(/<R>[\s\S]*?<\/R([^<>]*)>/g)].map(m=>m[1]==='_'?'':m[1]).join('');
   if(visible(primary)!==visible(row.expected_primary)||visible(secondary)!==visible(row.expected_secondary)||
       (visible(row.expected_primary)!==visible(row.expected_secondary)&&visible(payload)!==visible(row.expected_secondary)))
     throw Error('Raw status oracle differs in final V8 render: '+row.family+' / '+row.source);
   families[row.family]=(families[row.family]||0)+1;
 }
 return {passed:true,rows:result,whole_conflict_rejected:true,typed_overflows_rejected:true,
   facility_conflict_rejected:true,status_raw_oracle:{rows:globalThis.statusOracleInputs.length,families,failures:0},game_attached:false};
}};
"""
oracle_inputs = json.loads(
    (harness.ROOT / "generated/r21-status-oracle-inputs.json").read_text("utf-8")
)
if oracle_inputs["missing"]:
    raise RuntimeError("Raw status oracle has incomplete peers")
harness.NATIVE += (
    "\nglobalThis.statusOracleInputs="
    + json.dumps(oracle_inputs["cases"], ensure_ascii=False)
    + ";\n"
)

if __name__ == "__main__":
    harness.main()
