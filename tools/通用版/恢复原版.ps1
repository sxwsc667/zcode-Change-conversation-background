param([string]$ResourcesDir)
$ErrorActionPreference='Stop'
$lock=$null; $stage=$null
try {
    . (Join-Path $PSScriptRoot '公共函数.ps1')
    $resources=Resolve-Resources $ResourcesDir
    $lock=Open-OperationLock $resources
    Assert-Stopped $resources
    $state=Read-InstalledState $resources
    Assert-Current $resources $state
    if ($state.currentHash -eq $state.originalHash) { Write-Host '当前已经是原版，不需要重复恢复。'; exit 0 }
    $before=$state.currentHash
    $stage=New-Stage $resources 'restore-stage'
    Copy-Item -LiteralPath (Join-Path $resources 'app.asar.custom-bg-restore') -Destination $stage
    $state.currentHash=$state.originalHash
    Publish-Package $resources $stage $before $state.originalHash $state
    Write-Host '已恢复原版界面，重新打开智码即可。' -ForegroundColor Green
} catch { Write-Host ('未完成恢复：'+$_.Exception.Message) -ForegroundColor Yellow; exit 1 }
finally {
    if ($stage -and (Test-Path -LiteralPath $stage)) { Remove-Item -LiteralPath $stage -ErrorAction SilentlyContinue }
    if ($lock) { $lock.Dispose() }
}
