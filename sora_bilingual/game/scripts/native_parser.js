'use strict';
// The parse listener is hot even when it has no annotation work. Keep its
// ordinary path in C; JavaScript still owns translation and auxiliary data.
function createNativeParser(contexts,onError) {
    const state=Memory.alloc(65536);
    const scaleFallbacks=new Map();
    let generation=0,bridgeCalls=0;
    const finish=new NativeCallback((parser,serial)=>{
        try {
            bridgeCalls++;
            const key=String(parser),row=contexts.get(key),scale=scaleFallbacks.get(key);
            if(row?.generation===serial.toNumber())contexts.delete(key);
            if(scale?.generation===serial.toNumber())scaleFallbacks.delete(key);
        }catch(error){onError(error);}
    },'void',['pointer','uint64']);
    const fallback=new NativeCallback(parser=>{
        try {
            bridgeCalls++;
            const key=String(parser),row=contexts.get(key);
            if(row) {
                parser.add(0x1a5).writeU8(row.placement?0:1);
                return row.generation;
            }
            return scaleFallbacks.get(key)?.generation||0;
        }catch(error){onError(error);return 0;}
    },'uint64',['pointer']);
    const scaleLookup=new NativeCallback(parser=>{
        try {
            bridgeCalls++;
            const key=String(parser),value=contexts.get(key)?.factor??scaleFallbacks.get(key)?.factor;
            return Number.isFinite(value)&&value>0&&value<=8?value:0;
        }catch(error){onError(error);return 0;}
    },'double',['pointer']);
    const scaleRegister=new NativeCallback((parser,factor)=>{
        try {
            factor=Number(factor);
            if(!Number.isFinite(factor)||factor<=0||factor>8||generation>=Number.MAX_SAFE_INTEGER)return 0;
            const serial=++generation;
            scaleFallbacks.set(String(parser),{generation:serial,factor});
            return serial;
        }catch(error){onError(error);return 0;}
    },'uint64',['pointer','double']);
    const module=new CModule(String.raw`
#include <stdint.h>
#include <glib.h>
#include <gum/guminterceptor.h>
#include <gum/gumspinlock.h>

#define CAPACITY 1024
typedef struct {
    void *key;
    uint64_t generation;
    double factor;
    uint32_t placement, has_context, has_scale, parsing;
} Slot;
typedef struct {
    GumSpinlock lock;
    uint32_t active, fallback_all, overflows;
    uint64_t count, total_us, max_us, over8, all_calls;
    uint64_t size_tracks, size_applied, size_rejected;
    Slot slots[CAPACITY];
} State;
typedef struct {
    void *key;
    uint64_t generation, slot_generation;
    int64_t start;
    uint32_t outer, tracked;
} Invocation;
extern State parser_state;
extern void parser_finish(void *, uint64_t);
extern uint64_t parser_fallback(void *);
extern double parser_scale_lookup(void *);
extern uint64_t parser_scale_register(void *, double);
typedef char state_fits[(sizeof(State) <= 65536) ? 1 : -1];
static int finite_double(double value) { return value==value && value<=1.7976931348623157e308 && value>=-1.7976931348623157e308; }
static int finite_float(float value) { return value==value && value<=3.402823466e38f && value>=-3.402823466e38f; }

static Slot *find_slot(State *s, void *key, Slot **free_slot) {
    uint32_t i;
    Slot *free_value=0;
    for (i=0; i<CAPACITY; i++) {
        Slot *p=&s->slots[i];
        if (p->key==key) { if (free_slot) *free_slot=p; return p; }
        if (!p->key && !free_value) free_value=p;
    }
    if (free_slot) *free_slot=free_value;
    return 0;
}

void parser_init(void) { gum_spinlock_init(&parser_state.lock); }

void parser_register(void *key, uint64_t generation, uint32_t placement, double factor) {
    State *s=&parser_state;
    Slot *free_slot=0;
    if (!key || !finite_double(factor) || factor<=0.0 || factor>8.0) return;
    gum_spinlock_acquire(&s->lock);
    if (!s->fallback_all) {
        find_slot(s,key,&free_slot);
        if (free_slot) {
            if (!free_slot->key) s->active++;
            free_slot->key=key;
            free_slot->generation=generation;
            free_slot->placement=placement;
            free_slot->factor=factor;
            free_slot->has_context=1;
            free_slot->has_scale=1;
        } else {
            // Keep the complete JS Map authoritative on overflow. Do not
            // discard an annotation or interrupt the player's translation.
            s->fallback_all=1;
            s->overflows++;
        }
    }
    gum_spinlock_release(&s->lock);
}

void parser_track_scale(void *key, double factor) {
    State *s=&parser_state;
    Slot *p, *free_slot=0;
    uint32_t fallback_all;
    if (!key || !finite_double(factor) || factor<=0.0 || factor>8.0) return;
    gum_spinlock_acquire(&s->lock);
    fallback_all=s->fallback_all;
    if (!fallback_all) {
        p=find_slot(s,key,&free_slot);
        if (!p) p=free_slot;
        if (p) {
            if (!p->key) { p->key=key; s->active++; }
            p->factor=factor;
            p->has_scale=1;
            s->size_tracks++;
        } else { s->fallback_all=1; s->overflows++; fallback_all=1; }
    }
    gum_spinlock_release(&s->lock);
    // Only an overflowed registry needs a C-to-JS scale record. The normal
    // measurement path remains wholly native.
    if (fallback_all) parser_scale_register(key,factor);
}

void parser_on_enter(GumInvocationContext *ic) {
    State *s=&parser_state;
    Invocation *v=GUM_IC_GET_INVOCATION_DATA(ic,Invocation);
    unsigned char *label=gum_invocation_context_get_nth_argument(ic,0);
    unsigned char *parser=gum_invocation_context_get_nth_argument(ic,1);
    uint32_t i, fallback_all, placement=0;
    v->key=parser;
    v->generation=0;
    v->slot_generation=0;
    v->tracked=0;
    v->outer=(parser==label+0x400);
    v->start=v->outer ? g_get_monotonic_time() : 0;
    gum_spinlock_acquire(&s->lock);
    s->all_calls++;
    fallback_all=s->fallback_all;
    // Existing C slots remain reference-counted after an overflow so their
    // eventual parser leave can retire them. New keys still use JS below.
    if (s->active) {
        for (i=0; i<CAPACITY; i++) if (s->slots[i].key==parser) {
            Slot *p=&s->slots[i];
            v->slot_generation=p->generation;
            v->tracked=1;
            p->parsing++;
            if (p->has_context) placement=p->placement;
            break;
        }
    }
    gum_spinlock_release(&s->lock);
    // No JS callback may run while holding the registry lock.
    if (fallback_all) v->generation=parser_fallback(parser);
    else if (v->tracked) {
        v->generation=v->slot_generation;
        if (v->generation) parser[0x1a5]=placement ? 0 : 1;
    }
}

void parser_on_leave(GumInvocationContext *ic) {
    State *s=&parser_state;
    Invocation *v=GUM_IC_GET_INVOCATION_DATA(ic,Invocation);
    uint32_t i;
    uint64_t finish=0;
    uint64_t elapsed=0;
    if (v->outer) {
        int64_t duration=g_get_monotonic_time()-v->start;
        elapsed=duration>0 ? (uint64_t)duration : 0;
    }
    gum_spinlock_acquire(&s->lock);
    if (v->tracked && s->active) {
        for (i=0; i<CAPACITY; i++) {
            Slot *p=&s->slots[i];
            if (p->key==v->key) {
                if (p->parsing) p->parsing--;
                if (!p->parsing && p->generation==v->slot_generation) {
                    if (p->has_context) finish=v->generation ? v->generation : p->generation;
                    p->key=0;
                    p->generation=0;
                    p->has_context=0;
                    p->has_scale=0;
                    s->active--;
                }
                break;
            }
        }
    }
    if (!v->tracked && v->generation && s->active) {
        // After registry overflow the JS map owns the active invocation, but
        // an older native slot with the same serial still needs retiring.
        for (i=0; i<CAPACITY; i++) {
            Slot *p=&s->slots[i];
            if (p->key==v->key && p->generation==v->generation) {
                p->key=0;
                p->generation=0;
                p->has_context=0;
                p->has_scale=0;
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
    // Registry overflow delegates the complete context lifecycle to JS.
    // Its serial still needs the same completion bridge as the former path.
    if (!v->tracked && v->generation) finish=v->generation;
    if (finish) parser_finish(v->key,finish);
}

static int parser_apply_size_for(State *s, void *key) {
    uint32_t i;
    uint32_t fallback_all;
    double factor=0;
    float sx, sy, nx, ny;
    if (!key) return 0;
    gum_spinlock_acquire(&s->lock);
    fallback_all=s->fallback_all;
    for (i=0; i<CAPACITY; i++) if (s->slots[i].key==key && s->slots[i].has_scale) {
        factor=s->slots[i].factor;
        break;
    }
    gum_spinlock_release(&s->lock);
    if ((!finite_double(factor) || factor<=0.0 || factor>8.0) && fallback_all)
        factor=parser_scale_lookup(key);
    if (!finite_double(factor) || factor<=0.0 || factor>8.0) return 0;
    sx=*(float *)((uint8_t *)key+0x158); sy=*(float *)((uint8_t *)key+0x15c);
    nx=(float)((double)sx*factor); ny=(float)((double)sy*factor);
    if (!finite_float(sx) || !finite_float(sy) || sx<=0.0f || sy<=0.0f || sx>8.0f || sy>8.0f ||
            !finite_float(nx) || !finite_float(ny) || nx<=0.0f || ny<=0.0f || nx>8.0f || ny>8.0f) {
        gum_spinlock_acquire(&s->lock); s->size_rejected++; gum_spinlock_release(&s->lock);
        return 0;
    }
    *(float *)((uint8_t *)key+0x158)=nx;
    *(float *)((uint8_t *)key+0x15c)=ny;
    gum_spinlock_acquire(&s->lock); s->size_applied++; gum_spinlock_release(&s->lock);
    return 1;
}
int parser_apply_size(void *key) { return parser_apply_size_for(&parser_state,key); }
void parser_size_on_enter(GumInvocationContext *ic) {
    GumCpuContext *cpu=ic->cpu_context;
    parser_apply_size_for(&parser_state,(void *)cpu->rbx);
}

void parser_snapshot(uint64_t *out) {
    State *s=&parser_state;
    gum_spinlock_acquire(&s->lock);
    out[0]=s->count; out[1]=s->total_us; out[2]=s->max_us;
    out[3]=s->over8; out[4]=s->all_calls; out[5]=s->active;
    out[6]=s->fallback_all; out[7]=s->overflows;
    out[8]=s->size_tracks; out[9]=s->size_applied; out[10]=s->size_rejected;
    gum_spinlock_release(&s->lock);
}
`,{parser_state:state,parser_finish:finish,parser_fallback:fallback,
        parser_scale_lookup:scaleLookup,parser_scale_register:scaleRegister});
    const options={scheduling:'exclusive'};
    const initialize=new NativeFunction(module.parser_init,'void',[],options);
    const register=new NativeFunction(module.parser_register,'void',['pointer','uint64','uint','double'],options);
    const trackNative=new NativeFunction(module.parser_track_scale,'void',['pointer','double'],options);
    const applySize=new NativeFunction(module.parser_apply_size,'int',['pointer'],options);
    const readStats=new NativeFunction(module.parser_snapshot,'void',['pointer'],options);
    const snapshot=Memory.alloc(11*8);
    initialize();
    return {
        // All executable/data/bridge objects remain strongly owned for the
        // resident agent's lifetime. Never dispose while the game is running.
        module,state,finish,fallback,scaleLookup,scaleRegister,trackNative:module.parser_track_scale,
        onEnter:module.parser_on_enter,onLeave:module.parser_on_leave,sizeOnEnter:module.parser_size_on_enter,
        set(parser,value) {
            if(generation>=Number.MAX_SAFE_INTEGER)throw Error('Parser generation exhausted');
            const serial=++generation;
            contexts.set(String(parser),{...value,generation:serial});
            const factor=Number(value.factor);
            if(!Number.isFinite(factor)||factor<=0||factor>8)throw Error('Invalid auxiliary scale');
            register(parser,serial,value.placement?1:0,factor);
        },
        trackScale(parser,factor) {
            factor=Number(factor);
            if(!Number.isFinite(factor)||factor<=0||factor>8)throw Error('Invalid parser scale');
            trackNative(parser,factor);
        },
        // Test-only direct entry to the same C body used by sizeOnEnter.
        applySize(parser) { return !!applySize(parser); },
        status() {
            readStats(snapshot);
            const values=Array.from({length:11},(_,i)=>snapshot.add(i*8).readU64().toNumber());
            return {count:values[0],totalMs:values[1]/1000,maxMs:values[2]/1000,over8Ms:values[3],
                allCalls:values[4],active:values[5],fallback:!!values[6],overflows:values[7],
                sizeTracks:values[8],sizeApplied:values[9],sizeRejected:values[10],bridgeCalls};
        }
    };
}
