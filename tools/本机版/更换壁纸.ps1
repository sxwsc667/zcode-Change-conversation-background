param([string]$ImagePath)
$ErrorActionPreference='Stop'
try {
    & (Join-Path $PSScriptRoot '接入旧版记录.ps1')
    & (Join-Path (Split-Path $PSScriptRoot -Parent) '通用版\更换壁纸.ps1') -ResourcesDir 'E:\ZCode\resources' -Python 'E:\python\python.exe' -ImagePath $ImagePath
    exit $LASTEXITCODE
} catch { Write-Host ('未完成更换：'+$_.Exception.Message) -ForegroundColor Yellow; exit 1 }
