param([string]$Asar,[string]$Image,[string]$Output,[string]$Python)
$ErrorActionPreference='Stop'
try {
    . (Join-Path $PSScriptRoot '公共函数.ps1')
    $runtime=Find-Python $Python; $exe=$runtime.exe; $prefix=$runtime.prefix
    if (!$Asar) { $Asar=Join-Path (Resolve-Resources '') 'app.asar' }
    $arguments=@((Join-Path $PSScriptRoot '制作背景补丁.py'),'--asar',$Asar)
    if ($Image) { $arguments += @('--image',$Image) }
    if ($Output) { $arguments += @('--output',$Output) }
    $env:PYTHONIOENCODING='utf-8'
    & $exe @prefix @arguments
    if ($LASTEXITCODE -eq 10) { exit 0 }
    exit $LASTEXITCODE
} catch { Write-Host ('未完成制作：'+$_.Exception.Message) -ForegroundColor Yellow; exit 1 }
