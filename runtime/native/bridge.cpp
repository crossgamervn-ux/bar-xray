#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <algorithm>
#include "minhook/include/MinHook.h"

// POD ABI for this verified Recoil build. No STL objects cross DLL boundaries.
struct Command {
    int32_t id, ai, timeout;
    uint32_t page, count, tag;
    uint8_t options, padding[3];
    float params[8];
};
static_assert(sizeof(Command)==60);
struct Vector { void *begin, *end, *capacity; };
struct Header {
    uint32_t magic, version, pid;
    volatile LONG ready;
    uint64_t heartbeat, updates, sends, rejects;
    uint32_t threadId;
    volatile LONG enabled;
    uint64_t maxDrainUs;
};
struct Slot {
    volatile LONG state; // 0 free, 1 pending, 2 executing, 3 completed
    uint32_t serial;
    volatile LONG cancelled;
    int32_t unit;
    uint64_t expectedUnit, deadline;
    float origin[3];
    uint32_t count, status, elapsedUs;
    uint64_t reserved;
    Command commands[31];
    uint8_t padding[124];
};
static_assert(sizeof(Header)==64 && sizeof(Slot)==2048);
struct Shared { Header header; Slot slots[64]; };
using UpdateFn=bool (*)(void*);
using SendFn=void (*)(void*,const Vector*,const Vector*,bool);
static UpdateFn originalUpdate=nullptr;
static SendFn sendCommands=nullptr;
static uintptr_t base=0;
static Shared* shared=nullptr;
static HANDLE mapping=nullptr, mutexHandle=nullptr;
static LARGE_INTEGER frequency{};
static uint32_t cursor=0;
static LONG initialized=0;
#ifdef OP_FIXTURE
using ValidateFn=uint32_t (*)(int,uint64_t,const float*);
static ValidateFn fixtureValidate=nullptr;
#endif

static uint64_t ticks() { LARGE_INTEGER q; QueryPerformanceCounter(&q);return q.QuadPart; }
static uint64_t micros(uint64_t begin) {return (ticks()-begin)*1000000/frequency.QuadPart;}
static uintptr_t ptr(uintptr_t a) {return *reinterpret_cast<uintptr_t*>(a);}

static uint32_t validate(const Slot& s) {
    if (s.cancelled) return 2;
    if (GetTickCount64()>s.deadline) return 1;
    if (!s.count || s.count>31) return 6;
    for (unsigned i=0;i<3;++i) if (!std::isfinite(s.origin[i])) return 6;
    for (unsigned i=0;i<s.count;++i) {
        const auto& c=s.commands[i];
        if (c.count>8 || c.page!=UINT32_MAX || c.id < -100000 || c.id > 100000) return 6;
        for (unsigned j=0;j<c.count;++j)
            if (!std::isfinite(c.params[j]) || std::abs(c.params[j])>=1e9f) return 6;
    }
#ifdef OP_FIXTURE
    return fixtureValidate(s.unit,s.expectedUnit,s.origin);
#else
    if (*reinterpret_cast<int*>(ptr(base+0x1698a40))!=0) return 5;
    const auto handler=ptr(base+0x169d8b0);
    if (!handler) return 3;
    const auto count=*reinterpret_cast<uint32_t*>(handler+0x1920);
    if (s.unit<0 || static_cast<uint32_t>(s.unit)>=count) return 3;
    const auto table=ptr(handler+0xa8);
    if (!table) return 3;
    const auto unit=ptr(table+8*s.unit);
    if (!unit || unit!=s.expectedUnit) return 3;
    const float health=*reinterpret_cast<float*>(unit+0x19c);
    if (!std::isfinite(health) || health<=0) return 3;
    const auto gu=ptr(ptr(base+0x169d440));
    if (!gu || *reinterpret_cast<uint8_t*>(gu+0x30)) return 4;
    if (*reinterpret_cast<int*>(gu+0x20)!=*reinterpret_cast<int*>(unit+0x1d8)) return 4;
    const auto pos=reinterpret_cast<float*>(unit+0xe0);
    if (!std::isfinite(pos[0]) || !std::isfinite(pos[2])) return 3;
    const float dx=pos[0]-s.origin[0], dz=pos[2]-s.origin[2];
    if (dx*dx+dz*dz>512.0f*512.0f) return 7;
    return 0;
#endif
}

static void drain() {
    if (!shared) return;
    auto& h=shared->header;
    const auto threadId=GetCurrentThreadId();
    if (!h.threadId) h.threadId=threadId;
    if (h.threadId!=threadId) return;
    h.heartbeat=GetTickCount64(); ++h.updates;
    const auto begin=ticks();
    // Never wait for the producer on the game thread; defer to the next update.
    for (unsigned work=0;work<8;++work) {
        const DWORD lock=WaitForSingleObject(mutexHandle,0);
        if (lock!=WAIT_OBJECT_0 && lock!=WAIT_ABANDONED) break;
        Slot* slot=nullptr;
        for (unsigned j=0;j<64;++j) {
            auto& candidate=shared->slots[(cursor+j)%64];
            if (candidate.state==1) {slot=&candidate;cursor=(cursor+j+1)%64;break;}
        }
        if (!slot) {ReleaseMutex(mutexHandle);break;}
        Slot local;
        std::memcpy(&local,slot,sizeof local);
        InterlockedExchange(&slot->state,2);
        ReleaseMutex(mutexHandle);
        const auto start=ticks();
        uint32_t status=h.enabled ? validate(local) : 8;
        if (slot->cancelled) status=2;
        if (!status) {
            int unit=local.unit;
            Vector units{&unit,&unit+1,&unit+1};
            Vector commands{local.commands,local.commands+local.count,local.commands+local.count};
#ifdef OP_FIXTURE
            void* selected=nullptr;
#else
            void* selected=reinterpret_cast<void*>(ptr(base+0x169d790));
#endif
            sendCommands(selected,&units,&commands,false);
            ++h.sends;
        } else ++h.rejects;
        slot->status=status;
        slot->elapsedUs=static_cast<uint32_t>(micros(start));
        InterlockedExchange(&slot->state,3); // publish only after all result fields
        if (micros(begin)>=1000) break;
    }
    h.maxDrainUs=std::max(h.maxDrainUs,micros(begin));
}

static bool hookedUpdate(void* game) {
    const bool result=originalUpdate(game);
    drain();
    return result;
}

extern "C" __declspec(dllexport) DWORD WINAPI OpStart(void*) {
    if (InterlockedCompareExchange(&initialized,1,0)!=0) return 0;
    base=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    void* target=nullptr;
#ifdef OP_FIXTURE
    target=reinterpret_cast<void*>(GetProcAddress((HMODULE)base,"OpFixtureUpdate"));
    sendCommands=reinterpret_cast<SendFn>(GetProcAddress((HMODULE)base,"OpFixtureSend"));
    fixtureValidate=reinterpret_cast<ValidateFn>(GetProcAddress((HMODULE)base,"OpFixtureValidate"));
    if (!target || !sendCommands || !fixtureValidate) return 11;
#else
    const uint8_t updatePrefix[]={0x41,0x57,0xb8,0x88,0x40,0,0,0x41,0x56,0x41,0x55,0x41,0x54,0x55,0x57,0x56};
    const uint8_t sendPrefix[]={0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x55,0x57,0x56,0x53,0x48,0x83,0xec,0x58};
    if (memcmp((void*)(base+0xd58c90),updatePrefix,sizeof updatePrefix) ||
        memcmp((void*)(base+0xda0fb0),sendPrefix,sizeof sendPrefix)) return 12;
    target=reinterpret_cast<void*>(base+0xd58c90);
    sendCommands=reinterpret_cast<SendFn>(base+0xda0fb0);
#endif
    wchar_t name[100];
    wsprintfW(name,L"Local\\AutoDodgeOP-%lu",GetCurrentProcessId());
    mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(Shared),name);
    if (!mapping) return 13;
    if (GetLastError()==ERROR_ALREADY_EXISTS) return 14;
    shared=(Shared*)MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(Shared));
    if (!shared) return 15;
    wsprintfW(name,L"Local\\AutoDodgeOP-Lock-%lu",GetCurrentProcessId());
    mutexHandle=CreateMutexW(nullptr,FALSE,name);
    if (!mutexHandle) return 16;
    QueryPerformanceFrequency(&frequency);
    shared->header.magic=0x4f504e31;shared->header.version=1;
    shared->header.pid=GetCurrentProcessId();shared->header.enabled=1;
    if (MH_Initialize()!=MH_OK) return 17;
    if (MH_CreateHook(target,(void*)&hookedUpdate,(void**)&originalUpdate)!=MH_OK) return 18;
    if (MH_EnableHook(target)!=MH_OK) return 19;
    InterlockedExchange(&shared->header.ready,1);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE,DWORD,LPVOID) {return TRUE;}
