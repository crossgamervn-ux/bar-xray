param([string]$Toolchain='C:\msys64\mingw64\bin')
$ErrorActionPreference='Stop'
$cc=Join-Path $Toolchain 'gcc.exe'
$cpp=Join-Path $Toolchain 'g++.exe'
if(-not(Test-Path -LiteralPath $cc) -or -not(Test-Path -LiteralPath $cpp)){throw 'Install an x64 MinGW-w64 toolchain or specify -Toolchain'}
Push-Location $PSScriptRoot
try {
 foreach($file in @('buffer','hook','trampoline')) {
  & $cc -O2 -c "minhook/src/$file.c" -o "$file.o"
  if($LASTEXITCODE){throw 'MinHook compilation failed'}
 }
 & $cc -O2 -c minhook/src/hde/hde64.c -o hde64.o
 if($LASTEXITCODE){throw 'HDE compilation failed'}
 & $cpp -std=c++17 -O2 -shared -static -static-libgcc -static-libstdc++ bridge.cpp buffer.o hook.o trampoline.o hde64.o -o autododge_native.dll
 if($LASTEXITCODE){throw 'Bridge compilation failed'}
 & $cpp -std=c++17 -O2 -shared -static -static-libgcc -static-libstdc++ view_refresh_v2.cpp buffer.o hook.o trampoline.o hde64.o -o view_refresh_v2.dll
 if($LASTEXITCODE){throw 'View DLL compilation failed'}
 Write-Output 'Built both AX runtime dependencies'
} finally {Pop-Location}
