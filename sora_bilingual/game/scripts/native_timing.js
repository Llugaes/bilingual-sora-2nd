'use strict';
// Observe the complete synchronous hook boundary, including waiting to enter
// V8. No extra JS callback runs on a game thread. The middle listener remains
// the original Interceptor listener, with its original invocation semantics.
function createNativeLabelTiming(addresses) {
    const CAPACITY=32,THREADS=32,DEPTH=32,STAGES=2;
    const bytes=256*1024,state=Memory.alloc(bytes),snapshot=Memory.alloc(bytes);
    state.writeByteArray(new Uint8Array(bytes));
    const module=new CModule(String.raw`
#include <stdint.h>
#include <glib.h>
#include <gum/guminterceptor.h>
#include <gum/gumspinlock.h>
#define THREADS ${THREADS}
#define DEPTH ${DEPTH}
#define CAPACITY ${CAPACITY}
#define STAGES ${STAGES}
typedef struct { uint64_t start,entered,returned,label,stage; } Call;
typedef struct { uint64_t tid,depth; Call calls[DEPTH]; } Thread;
typedef struct { uint64_t count,total,max,over8,over50; } Metric;
typedef struct { uint64_t sequence,at,stage,tid,label,enter,body,leave; } Event;
typedef struct {
    GumSpinlock lock;
    uint64_t dropped,sequence;
    Metric metrics[STAGES][3];
    Event events[CAPACITY];
    Thread threads[THREADS];
} State;
extern State timing_state;
typedef char state_fits[(sizeof(State)<=${bytes})?1:-1];
static uint64_t now(void) { return (uint64_t)g_get_monotonic_time(); }
uint64_t timing_now(void) { return now(); }
void timing_init(void) { gum_spinlock_init(&timing_state.lock); }
static Thread *thread_for(uint64_t tid,int create) {
    Thread *empty=0; uint32_t i;
    for(i=0;i<THREADS;i++) {
        Thread *t=&timing_state.threads[i];
        if(t->tid==tid)return t;
        if(!t->tid&&!empty)empty=t;
    }
    if(create&&empty){empty->tid=tid;return empty;}
    return 0;
}
void before_enter(GumInvocationContext *ic) {
    uint64_t at=now(); Thread *t; Call *c;
    gum_spinlock_acquire(&timing_state.lock);
    t=thread_for(gum_invocation_context_get_thread_id(ic),1);
    if(!t){timing_state.dropped++;goto done;}
    if(t->depth++>=DEPTH){timing_state.dropped++;goto done;}
    c=&t->calls[t->depth-1]; c->start=at;c->entered=0;c->returned=0;
    c->label=(uint64_t)gum_invocation_context_get_nth_argument(ic,0);
    c->stage=(uint64_t)gum_invocation_context_get_listener_function_data(ic);
done: gum_spinlock_release(&timing_state.lock);
}
void after_enter(GumInvocationContext *ic) {
    uint64_t at=now();Thread *t;
    gum_spinlock_acquire(&timing_state.lock);
    t=thread_for(gum_invocation_context_get_thread_id(ic),0);
    if(t&&t->depth&&t->depth<=DEPTH)t->calls[t->depth-1].entered=at;
    gum_spinlock_release(&timing_state.lock);
}
void before_leave(GumInvocationContext *ic) {
    uint64_t at=now();Thread *t;
    gum_spinlock_acquire(&timing_state.lock);
    t=thread_for(gum_invocation_context_get_thread_id(ic),0);
    if(t&&t->depth&&t->depth<=DEPTH)t->calls[t->depth-1].returned=at;
    gum_spinlock_release(&timing_state.lock);
}
static void record(Metric *m,uint64_t us) {
    m->count++;m->total+=us;if(us>m->max)m->max=us;
    if(us>=8000)m->over8++;if(us>=50000)m->over50++;
}
void after_leave(GumInvocationContext *ic) {
    uint64_t at=now(),parts[3],tid=gum_invocation_context_get_thread_id(ic);
    Thread *t;Call *c;uint32_t i;Event *e;
    gum_spinlock_acquire(&timing_state.lock);
    t=thread_for(tid,0);if(!t||!t->depth)goto done;
    if(t->depth>DEPTH){t->depth--;goto done;}
    c=&t->calls[--t->depth];
    if(c->stage>=STAGES||c->entered<c->start||c->returned<c->entered||at<c->returned){timing_state.dropped++;goto release;}
    parts[0]=c->entered-c->start;parts[1]=c->returned-c->entered;parts[2]=at-c->returned;
    for(i=0;i<3;i++)record(&timing_state.metrics[c->stage][i],parts[i]);
    if(at-c->start>=8000) {
        uint64_t seq=++timing_state.sequence;e=&timing_state.events[(seq-1)%CAPACITY];
        e->sequence=seq;e->at=c->start;e->stage=c->stage;e->tid=tid;e->label=c->label;
        e->enter=parts[0];e->body=parts[1];e->leave=parts[2];
    }
release: if(!t->depth)t->tid=0;
done: gum_spinlock_release(&timing_state.lock);
}
void timing_snapshot(uint64_t *out) {
    uint32_t i,j,k;uint64_t *src;
    gum_spinlock_acquire(&timing_state.lock);
    *out++=timing_state.dropped;*out++=timing_state.sequence;
    for(i=0;i<STAGES;i++)for(j=0;j<3;j++) {
        Metric *m=&timing_state.metrics[i][j];
        *out++=m->count;*out++=m->total;*out++=m->max;*out++=m->over8;*out++=m->over50;
    }
    for(i=0;i<CAPACITY;i++) {
        src=(uint64_t*)&timing_state.events[i];for(k=0;k<8;k++)*out++=src[k];
    }
    gum_spinlock_release(&timing_state.lock);
}
`,{timing_state:state});
    const init=new NativeFunction(module.timing_init,'void',[],{scheduling:'exclusive'});
    const read=new NativeFunction(module.timing_snapshot,'void',['pointer'],{scheduling:'exclusive'});
    const clock=new NativeFunction(module.timing_now,'uint64',[],{scheduling:'exclusive'});
    init();
    const wallOffset=Date.now()-clock().toNumber()/1000;
    const names=['setter','update'],phases=['enter','body','leave'],listeners=[];
    return {
        attach(address,callbacks) {
            const stage=names.findIndex(name=>address.equals(addresses[name]));
            if(stage<0)throw Error('Unknown timed label hook');
            const before=Interceptor.attach(address,{onEnter:module.before_enter,onLeave:module.before_leave},ptr(stage));
            const middle=Interceptor.attach(address,callbacks);
            const after=Interceptor.attach(address,{onEnter:module.after_enter,onLeave:module.after_leave},ptr(stage));
            listeners.push(before,middle,after);return middle;
        },
        status() {
            read(snapshot);let at=0;
            const next=()=>snapshot.add((at++)*8).readU64().toNumber();
            const dropped=next(),sequence=next(),stages={};
            for(const name of names) {
                stages[name]={};
                for(const phase of phases)stages[name][phase]={count:next(),totalMs:next()/1000,maxMs:next()/1000,over8Ms:next(),over50Ms:next()};
            }
            const recent=[];
            for(let i=0;i<CAPACITY;i++) {
                const seq=next(),time=next(),stage=next(),thread=next();
                const label=snapshot.add(at++*8).readPointer().toString();
                const enterMs=next()/1000,bodyMs=next()/1000,leaveMs=next()/1000;
                if(seq)recent.push({sequence:seq,at:Math.round(wallOffset+time/1000),stage:names[stage],thread,label,enterMs,bodyMs,leaveMs});
            }
            recent.sort((a,b)=>a.sequence-b.sequence);
            return {dropped,sequence,stages,recent};
        },
        // Retain the native code and storage for the complete resident lifetime.
        module,state,listeners
    };
}
