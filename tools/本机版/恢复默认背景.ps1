$ErrorActionPreference='Stop'
try {
    & (Join-Path $PSScriptRoot '接入旧版记录.ps1')
    & (Join-Path (Split-Path $PSScriptRoot -Parent) '通用版\恢复原版.ps1') -ResourcesDir 'E:\ZCode\resources'
    exit $LASTEXITCODE
} catch { Write-Host ('未完成恢复：'+$_.Exception.Message) -ForegroundColor Yellow; exit 1 }
