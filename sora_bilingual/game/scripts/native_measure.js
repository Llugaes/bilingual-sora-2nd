'use strict';
// Native fast path for the two already-verified ruby measurement returns.
// Every condition that is not explicitly represented in the per-thread scope
// stays on the original JavaScript ruby_context_init listener.
function createNativeMeasure(callbacks, addresses, onError, scaleTracker=null) {
    const THREADS = 32, DEPTH = 16;
    // Includes alignment/padding before the 64-bit counters in State.
    const STATE_BYTES = 128 + THREADS * (16 + DEPTH * 32);
    const state = Memory.alloc(STATE_BYTES);
    state.writeByteArray(new Uint8Array(STATE_BYTES));
    const slowThis = new Map();
    const errorBridge = new NativeCallback(code => {
        onError(new Error(`native ruby measurement fast path disabled (${code})`));
    }, 'void', ['int']);
    const trackerSymbol=scaleTracker?.trackNative||null;
    const trackerExtern=trackerSymbol?'extern void measure_track_scale(void *, double);':'';
    const trackerCall=trackerSymbol?'measure_track_scale(v->args[0],(double)*(float *)((uint8_t *)v->args[0]+0x15c));':'';
    const slowEnter = new NativeCallback((invocation, a0, a1, a2, returnAddress, r15, rbx, rbp) => {
        const key = String(invocation);
        const self = {returnAddress, context: {r15, rbx, rbp}};
        const args = [a0, a1, a2];
        try {
            callbacks.onEnter.call(self, args);
        } catch (error) {
            onError(error);
        } finally {
            invocation.writePointer(args[0]);
            invocation.add(8).writePointer(args[1]);
            invocation.add(16).writePointer(args[2]);
            slowThis.set(key, self);
        }
    }, 'void', ['pointer', 'pointer', 'pointer', 'pointer', 'pointer', 'pointer', 'pointer', 'pointer']);
    const slowLeave = new NativeCallback(invocation => {
        const key = String(invocation), self = slowThis.get(key);
        if (!self) {
            onError(new Error('native ruby measurement slow scope missing'));
            return;
        }
        try {
            let current = invocation.add(24).readPointer();
            const value = {
                toInt32() { return current.toInt32(); },
                replace(next) { current = next; invocation.add(24).writePointer(next); }
            };
            callbacks.onLeave.call(self, value);
        } catch (error) {
            onError(error);
        } finally {
            slowThis.delete(key);
        }
    }, 'void', ['pointer']);
    const module = new CModule(String.raw`
#include <stdint.h>
#include <glib.h>
#include <gum/guminterceptor.h>
#include <gum/gumspinlock.h>

#define THREADS ${THREADS}
#define DEPTH ${DEPTH}
#define MEASURE 1
#define BASE 2

typedef struct { uint64_t token; void *label; void *owned; double factor; } Scope;
typedef struct { uint64_t tid; uint32_t depth; uint32_t pad; Scope scope[DEPTH]; } ThreadScope;
typedef struct {
    GumSpinlock lock;
    uint32_t disabled, pushes, pops, overflows, mismatches;
    uint64_t next_token, fast_measure, fast_base, slow, apply_failures;
    ThreadScope threads[THREADS];
} State;
typedef struct {
    void *args[3];
    void *return_value;
    void *return_address;
    void *r15, *rbx, *rbp;
    uint64_t tid, token;
    uint32_t fast, branch;
    double factor;
} Invocation;
extern State measure_state;
extern void measure_slow_enter(void *, void *, void *, void *, void *, void *, void *, void *);
extern void measure_slow_leave(void *);
extern void measure_error(int);
${trackerExtern}
typedef char state_fits[(sizeof(State) <= ${STATE_BYTES}) ? 1 : -1];
static int finite_double(double value) { return value==value && value<=1.7976931348623157e308 && value>=-1.7976931348623157e308; }
static int finite_float(float value) { return value==value && value<=3.402823466e38f && value>=-3.402823466e38f; }

static ThreadScope *thread_for(State *s, uint64_t tid, int create) {
    uint32_t i;
    ThreadScope *empty=0;
    for (i=0; i<THREADS; i++) {
        ThreadScope *t=&s->threads[i];
        if (t->tid==tid) return t;
        if (!t->tid && !empty) empty=t;
    }
    if (create && empty) { empty->tid=tid; return empty; }
    return 0;
}
static int evaluate(State *s, uint64_t tid, void *caller, void *r15, void *rbx, uint32_t measuring, double *factor) {
    Scope scope;
    ThreadScope *t;
    int branch=0;
    if (caller==(void *)${addresses.measurement}) branch=MEASURE;
    else if (caller==(void *)${addresses.baseMeasurement}) branch=BASE;
    else return 0;
    gum_spinlock_acquire(&s->lock);
    if (s->disabled) { gum_spinlock_release(&s->lock); return 0; }
    t=thread_for(s,tid,0);
    if (t && t->depth) scope=t->scope[t->depth-1]; else scope.token=0;
    gum_spinlock_release(&s->lock);
    if (!scope.token || scope.label!=r15 || !r15 || scope.owned==0 || !measuring)
        return 0;
    if (*(void **)((uint8_t *)r15+0x318)!=scope.owned || !rbx || *((uint8_t *)rbx+0x1ab)!=1)
        return 0;
    gum_spinlock_acquire(&s->lock);
    if (branch==MEASURE) s->fast_measure++; else s->fast_base++;
    gum_spinlock_release(&s->lock);
    *factor=scope.factor;
    return branch;
}
void measure_init(void) { gum_spinlock_init(&measure_state.lock); }
uint64_t measure_push(uint64_t tid, void *label, void *owned, double factor) {
    State *s=&measure_state; ThreadScope *t; Scope *item; uint64_t token;
    gum_spinlock_acquire(&s->lock);
    if (s->disabled || !finite_double(factor) || factor<=0.0 || factor>8.0) { s->disabled=1; gum_spinlock_release(&s->lock); return 0; }
    t=thread_for(s,tid,1);
    if (!t || t->depth>=DEPTH) { s->overflows++; s->disabled=1; gum_spinlock_release(&s->lock); return 0; }
    token=++s->next_token; if (!token) token=++s->next_token;
    item=&t->scope[t->depth++]; item->token=token; item->label=label; item->owned=owned; item->factor=factor; s->pushes++;
    gum_spinlock_release(&s->lock); return token;
}
int measure_pop(uint64_t tid, uint64_t token) {
    State *s=&measure_state; ThreadScope *t; int ok=0;
    gum_spinlock_acquire(&s->lock);
    t=thread_for(s,tid,0);
    if (t && t->depth && t->scope[t->depth-1].token==token) { t->depth--; if (!t->depth) t->tid=0; s->pops++; ok=1; }
    else { s->mismatches++; s->disabled=1; }
    gum_spinlock_release(&s->lock);
    return ok;
}
int measure_evaluate(uint64_t tid, void *caller, void *r15, void *rbx, uint32_t measuring) {
    double ignored=0; return evaluate(&measure_state,tid,caller,r15,rbx,measuring,&ignored);
}
int measure_apply_fast(void *target, double factor) {
    State *s=&measure_state; float x, sx, sy, nx, ny;
    if (!target || !finite_double(factor)) goto bad;
    x=*(float *)target; sx=*(float *)((uint8_t *)target+0x158); sy=*(float *)((uint8_t *)target+0x15c);
    if (!finite_float(x) || !finite_float(sx) || !finite_float(sy) || sx<=0.0f || sy<=0.0f || sx>8.0f || sy>8.0f) goto bad;
    nx=(float)((double)sx*factor); ny=(float)((double)sy*factor);
    if (!finite_float(nx) || !finite_float(ny)) goto bad;
    *(float *)((uint8_t *)target+0x158)=nx; *(float *)((uint8_t *)target+0x15c)=ny;
    return 1;
bad:
    gum_spinlock_acquire(&s->lock); s->disabled=1; s->apply_failures++; gum_spinlock_release(&s->lock); measure_error(4); return 0;
}
void measure_on_enter(GumInvocationContext *ic) {
    State *s=&measure_state; Invocation *v=GUM_IC_GET_INVOCATION_DATA(ic,Invocation); GumCpuContext *cpu=ic->cpu_context;
    v->args[0]=gum_invocation_context_get_nth_argument(ic,0); v->args[1]=gum_invocation_context_get_nth_argument(ic,1); v->args[2]=gum_invocation_context_get_nth_argument(ic,2);
    v->return_value=0; v->return_address=gum_invocation_context_get_return_address(ic); v->r15=(void *)cpu->r15; v->rbx=(void *)cpu->rbx; v->rbp=(void *)cpu->rbp; v->tid=gum_invocation_context_get_thread_id(ic); v->factor=0;
    v->branch=evaluate(s,v->tid,v->return_address,v->r15,v->rbx,1,&v->factor); v->fast=v->branch!=0;
    if (v->fast) return;
    gum_spinlock_acquire(&s->lock); s->slow++; gum_spinlock_release(&s->lock);
    measure_slow_enter(v,v->args[0],v->args[1],v->args[2],v->return_address,v->r15,v->rbx,v->rbp);
    gum_invocation_context_replace_nth_argument(ic,0,v->args[0]); gum_invocation_context_replace_nth_argument(ic,1,v->args[1]); gum_invocation_context_replace_nth_argument(ic,2,v->args[2]);
}
void measure_on_leave(GumInvocationContext *ic) {
    Invocation *v=GUM_IC_GET_INVOCATION_DATA(ic,Invocation);
    if (v->fast) { if (v->branch==MEASURE && measure_apply_fast(v->args[0],v->factor)) { ${trackerCall} } return; }
    v->return_value=gum_invocation_context_get_return_value(ic); measure_slow_leave(v); gum_invocation_context_replace_return_value(ic,v->return_value);
}
void measure_snapshot(uint64_t *out) {
    State *s=&measure_state; gum_spinlock_acquire(&s->lock);
    out[0]=s->disabled; out[1]=s->pushes; out[2]=s->pops; out[3]=s->overflows; out[4]=s->mismatches; out[5]=s->fast_measure; out[6]=s->fast_base; out[7]=s->slow; out[8]=s->apply_failures;
    gum_spinlock_release(&s->lock);
}
`, trackerSymbol ? {measure_state: state, measure_slow_enter: slowEnter, measure_slow_leave: slowLeave,
        measure_error: errorBridge, measure_track_scale: trackerSymbol} : {measure_state: state,
        measure_slow_enter: slowEnter, measure_slow_leave: slowLeave, measure_error: errorBridge});
    const options = {scheduling: 'exclusive'};
    const initialize = new NativeFunction(module.measure_init, 'void', [], options);
    const pushNative = new NativeFunction(module.measure_push, 'uint64', ['uint64', 'pointer', 'pointer', 'double'], options);
    const popNative = new NativeFunction(module.measure_pop, 'int', ['uint64', 'uint64'], options);
    const snapshotNative = new NativeFunction(module.measure_snapshot, 'void', ['pointer'], options);
    const evaluateNative = new NativeFunction(module.measure_evaluate, 'int', ['uint64', 'pointer', 'pointer', 'pointer', 'uint'], options);
    const applyNative = new NativeFunction(module.measure_apply_fast, 'int', ['pointer', 'double'], options);
    const snapshot = Memory.alloc(9 * 8);
    initialize();
    return {
        module, state, slowEnter, slowLeave, errorBridge,
        onEnter: module.measure_on_enter,
        onLeave: module.measure_on_leave,
        push(threadId, label, ownedText, rubyScale) { return pushNative(threadId, label, ownedText, rubyScale).toNumber(); },
        pop(threadId, token) { return !!popNative(threadId, token); },
        // Test-only controlled entry for the exact C predicate, not a game ABI adapter.
        evaluate(threadId, callerReturn, r15, rbx, measuring) {
            return evaluateNative(threadId, callerReturn, r15, rbx, measuring ? 1 : 0);
        },
        apply(target, rubyScale) { return !!applyNative(target, rubyScale); },
        status() {
            snapshotNative(snapshot);
            const value = index => snapshot.add(index * 8).readU64().toNumber();
            return {disabled: !!value(0), pushes: value(1), pops: value(2), overflows: value(3), mismatches: value(4), fastMeasure: value(5), fastBase: value(6), slow: value(7), applyFailures: value(8), bridgeScopes: slowThis.size};
        }
    };
}
