'use strict';
// The parse listener is hot even when it has no annotation work. Keep its
// ordinary path in C; JavaScript still owns translation and auxiliary data.
function createNativeParser(contexts,onError) {
    const state=Memory.alloc(65536);
    let generation=0,bridgeCalls=0;
    const finish=new NativeCallback((parser,serial)=>{
        try {
            bridgeCalls++;
            const key=String(parser),row=contexts.get(key);
            if(row?.generation===serial.toNumber())contexts.delete(key);
        }catch(error){onError(error);}
    },'void',['pointer','uint64']);
    const fallback=new NativeCallback(parser=>{
        try {
            bridgeCalls++;
            const row=contexts.get(String(parser));
            if(!row)return 0;
            parser.add(0x1a5).writeU8(row.placement?0:1);
            return row.generation;
        }catch(error){onError(error);return 0;}
    },'uint64',['pointer']);
    const module=new CModule(String.raw`
#include <stdint.h>
#include <glib.h>
#include <gum/guminterceptor.h>
#include <gum/gumspinlock.h>

#define CAPACITY 1024
typedef struct {
    void *key;
    uint64_t generation;
    uint32_t placement;
} Slot;
typedef struct {
    GumSpinlock lock;
    uint32_t active, fallback_all, overflows;
    uint64_t count, total_us, max_us, over8, all_calls;
    Slot slots[CAPACITY];
} State;
typedef struct {
    void *key;
    uint64_t generation;
    int64_t start;
    uint32_t outer;
} Invocation;
extern State parser_state;
extern void parser_finish(void *, uint64_t);
extern uint64_t parser_fallback(void *);
typedef char state_fits[(sizeof(State) <= 65536) ? 1 : -1];

void parser_init(void) { gum_spinlock_init(&parser_state.lock); }

void parser_register(void *key, uint64_t generation, uint32_t placement) {
    State *s=&parser_state;
    uint32_t i;
    Slot *free_slot=0;
    gum_spinlock_acquire(&s->lock);
    if (!s->fallback_all) {
        for (i=0; i<CAPACITY; i++) {
            Slot *p=&s->slots[i];
            if (p->key==key) { free_slot=p; break; }
            if (!p->key && !free_slot) free_slot=p;
        }
        if (free_slot) {
            if (!free_slot->key) s->active++;
            free_slot->key=key;
            free_slot->generation=generation;
            free_slot->placement=placement;
        } else {
            // Keep the complete JS Map authoritative on overflow. Do not
            // discard an annotation or interrupt the player's translation.
            s->fallback_all=1;
            s->overflows++;
        }
    }
    gum_spinlock_release(&s->lock);
}

void parser_on_enter(GumInvocationContext *ic) {
    State *s=&parser_state;
    Invocation *v=GUM_IC_GET_INVOCATION_DATA(ic,Invocation);
    unsigned char *label=gum_invocation_context_get_nth_argument(ic,0);
    unsigned char *parser=gum_invocation_context_get_nth_argument(ic,1);
    uint32_t i, fallback_all, placement=0;
    v->key=parser;
    v->generation=0;
    v->outer=(parser==label+0x400);
    v->start=v->outer ? g_get_monotonic_time() : 0;
    gum_spinlock_acquire(&s->lock);
    s->all_calls++;
    fallback_all=s->fallback_all;
    if (!fallback_all && s->active) {
        for (i=0; i<CAPACITY; i++) if (s->slots[i].key==parser) {
            v->generation=s->slots[i].generation;
            placement=s->slots[i].placement;
            break;
        }
    }
    gum_spinlock_release(&s->lock);
    // No JS callback may run while holding the registry lock.
    if (fallback_all) v->generation=parser_fallback(parser);
    else if (v->generation) parser[0x1a5]=placement ? 0 : 1;
}

void parser_on_leave(GumInvocationContext *ic) {
    State *s=&parser_state;
    Invocation *v=GUM_IC_GET_INVOCATION_DATA(ic,Invocation);
    uint32_t i;
    uint64_t elapsed=0;
    if (v->outer) {
        int64_t duration=g_get_monotonic_time()-v->start;
        elapsed=duration>0 ? (uint64_t)duration : 0;
    }
    gum_spinlock_acquire(&s->lock);
    if (v->generation && s->active) {
        for (i=0; i<CAPACITY; i++) {
            Slot *p=&s->slots[i];
            if (p->key==v->key && p->generation==v->generation) {
                p->key=0;
                s->active--;
                break;
            }
        }
    }
    if (v->outer) {
        s->count++;
        s->total_us+=elapsed;
        if (elapsed>s->max_us) s->max_us=elapsed;
        if (elapsed>=8000) s->over8++;
    }
    gum_spinlock_release(&s->lock);
    if (v->generation) parser_finish(v->key,v->generation);
}

void parser_snapshot(uint64_t *out) {
    State *s=&parser_state;
    gum_spinlock_acquire(&s->lock);
    out[0]=s->count; out[1]=s->total_us; out[2]=s->max_us;
    out[3]=s->over8; out[4]=s->all_calls; out[5]=s->active;
    out[6]=s->fallback_all; out[7]=s->overflows;
    gum_spinlock_release(&s->lock);
}
`,{parser_state:state,parser_finish:finish,parser_fallback:fallback});
    const options={scheduling:'exclusive'};
    const initialize=new NativeFunction(module.parser_init,'void',[],options);
    const register=new NativeFunction(module.parser_register,'void',['pointer','uint64','uint'],options);
    const readStats=new NativeFunction(module.parser_snapshot,'void',['pointer'],options);
    const snapshot=Memory.alloc(8*8);
    initialize();
    return {
        // All executable/data/bridge objects remain strongly owned for the
        // resident agent's lifetime. Never dispose while the game is running.
        module,state,finish,fallback,
        onEnter:module.parser_on_enter,onLeave:module.parser_on_leave,
        set(parser,value) {
            if(generation>=Number.MAX_SAFE_INTEGER)throw Error('Parser generation exhausted');
            const serial=++generation;
            contexts.set(String(parser),{...value,generation:serial});
            register(parser,serial,value.placement?1:0);
        },
        status() {
            readStats(snapshot);
            const values=Array.from({length:8},(_,i)=>snapshot.add(i*8).readU64().toNumber());
            return {count:values[0],totalMs:values[1]/1000,maxMs:values[2]/1000,over8Ms:values[3],
                allCalls:values[4],active:values[5],fallback:!!values[6],overflows:values[7],bridgeCalls};
        }
    };
}
