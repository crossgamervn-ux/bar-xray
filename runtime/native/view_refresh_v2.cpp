#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>
#include <cstring>
#include "minhook/include/MinHook.h"

struct Shared {
    uint32_t magic,version,pid,ready;
    volatile LONG state;
    uint32_t value,status,thread;
    uint64_t deadline;
    uint32_t before,after,count,oldValue;
    uint64_t calls;
};
static_assert(sizeof(Shared)==64);
static Shared* s=nullptr;
static const unsigned char* bridge=nullptr;
static uintptr_t base=0;
static LONG started=0;
using Fn=int(*)(void*);
static Fn original=nullptr;
static uintptr_t ptr(uintptr_t a){return *reinterpret_cast<uintptr_t*>(a);}

static int callback(void* lua) {
    ++s->calls;
    // Execute on the same engine thread already measured by the resident bridge.
    if(s->state==1 && GetCurrentThreadId()==*reinterpret_cast<const uint32_t*>(bridge+48)
       && InterlockedCompareExchange(&s->state,2,1)==1) {
        s->thread=GetCurrentThreadId();s->status=0;s->before=0;s->after=0;s->count=0;
        const auto gu=ptr(ptr(base+0x169d440));
        const auto d=ptr(base+0x150dac0);
        const auto ui=ptr(base+0x18d2660);
        if(GetTickCount64()>s->deadline) s->status=1;
        else if(s->value>1 || !gu || !d || !ui) s->status=2;
        else if(*reinterpret_cast<int*>(ptr(base+0x1698a40))!=0) s->status=3;
        else {
            const auto begin=ptr(d+0xb4d8),end=ptr(d+0xb4e0);
            if(end<begin || (end-begin)%8 || (end-begin)/8>1000000) s->status=4;
            else {
                s->oldValue=*reinterpret_cast<uint8_t*>(gu+0x31);
                s->count=static_cast<uint32_t>((end-begin)/8);
                for(auto i=begin;i<end;i+=8) if(ptr(ptr(i)+0x10d0)==UINTPTR_MAX) ++s->before;
                *reinterpret_cast<uint8_t*>(gu+0x31)=static_cast<uint8_t>(s->value);
                // CLuaUI::UpdateTeams() copies full-view into the LuaUI read context.
                reinterpret_cast<void(*)()>(base+0x113570)();
                // CUnitDrawerData::PlayerChanged(this, playerID), verified RVA/ABI.
                reinterpret_cast<void(*)(void*,int)>(base+0x3c2950)(reinterpret_cast<void*>(d),*reinterpret_cast<int*>(gu+0x1c));
                for(auto i=begin;i<end;i+=8) if(ptr(ptr(i)+0x10d0)==UINTPTR_MAX) ++s->after;
            }
        }
        InterlockedExchange(&s->state,3);
    }
    return original(lua);
}

extern "C" __declspec(dllexport) DWORD WINAPI OpStart(void*) {
    if(InterlockedCompareExchange(&started,1,0))return 0;
    base=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));
    const unsigned char a[]={0x41,0x57,0x41,0x56,0x41,0x55,0x41,0x54,0x55,0x57,0x56,0x53,0x48,0x81,0xec,0x88,0,0,0};
    const unsigned char b[]={0x56,0x53,0x48,0x83,0xec,0x28,0x48,0x8b,0x99,0xd8,0xb4,0,0,0x48,0x8b,0xb1,0xe0,0xb4,0,0};
    if(memcmp((void*)(base+0x14a0e0),a,sizeof(a))||memcmp((void*)(base+0x3c2950),b,sizeof(b)))return 12;
    const unsigned char c[]={0x57,0x56,0x53,0x48,0x83,0xec,0x20,0x48,0x8b,0x1d,0xe2,0xf0,0x7b,0x01};
    if(memcmp((void*)(base+0x113570),c,sizeof(c)))return 20;
    wchar_t name[100];wsprintfW(name,L"Local\\AutoDodgeOP-%lu",GetCurrentProcessId());
    HANDLE h=OpenFileMappingW(FILE_MAP_READ,FALSE,name);
    if(!h)return 13;
    bridge=static_cast<const unsigned char*>(MapViewOfFile(h,FILE_MAP_READ,0,0,64));
    if(!bridge || *reinterpret_cast<const uint32_t*>(bridge)!=0x4f504e31)return 14;
    wsprintfW(name,L"Local\\ViewRefresh2-%lu",GetCurrentProcessId());
    h=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(Shared),name);
    if(!h || GetLastError()==ERROR_ALREADY_EXISTS)return 15;
    s=static_cast<Shared*>(MapViewOfFile(h,FILE_MAP_ALL_ACCESS,0,0,sizeof(Shared)));
    if(!s)return 16;
    s->magic=0x56523131;s->version=2;s->pid=GetCurrentProcessId();
    if(MH_Initialize()!=MH_OK)return 17;
    if(MH_CreateHook((void*)(base+0x14a0e0),(void*)callback,(void**)&original)!=MH_OK)return 18;
    if(MH_EnableHook((void*)(base+0x14a0e0))!=MH_OK)return 19;
    s->ready=1;return 0;
}
BOOL WINAPI DllMain(HINSTANCE,DWORD,LPVOID){return TRUE;}
