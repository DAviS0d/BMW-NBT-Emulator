$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
}
$source = Join-Path $PSScriptRoot 'Program.cs'
$output = Join-Path $PSScriptRoot 'bt-bridge.exe'
& $compiler /nologo /optimize+ /platform:x64 "/out:$output" $source
if ($LASTEXITCODE -ne 0) { throw 'Bluetooth bridge compilation failed' }
