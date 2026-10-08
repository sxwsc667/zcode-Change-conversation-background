param([string]$ResourcesDir,[string]$ImagePath,[string]$Python)
$ErrorActionPreference='Stop'
$lock=$null; $stage=$null
try {
    . (Join-Path $PSScriptRoot '公共函数.ps1')
    $resources=Resolve-Resources $ResourcesDir
    $lock=Open-OperationLock $resources
    Assert-Stopped $resources
    $state=Read-InstalledState $resources
    Assert-Current $resources $state
    if ($state.currentHash -eq $state.originalHash) { throw '尚未安装背景，请先运行「安装背景补丁」。' }
    $runtime=Find-Python $Python; $exe=$runtime.exe; $prefix=$runtime.prefix
    $stage=New-Stage $resources 'wallpaper-stage'
    $target=Join-Path $resources 'app.asar'
    $helper=Join-Path $PSScriptRoot '更换壁纸.py'
    $arguments=@($helper,$target,$stage)
    if ($ImagePath) { $arguments += $ImagePath }
    $env:PYTHONIOENCODING='utf-8'
    & $exe @prefix @arguments
    if ($LASTEXITCODE -eq 10) { exit 0 }
    if ($LASTEXITCODE -ne 0) { throw '图片处理没有通过，当前程序未改动。' }
    $before=$state.currentHash
    $after=Get-PackageHash $stage
    $state.currentHash=$after
    Publish-Package $resources $stage $before $after $state
    Write-Host '壁纸更换成功！重新打开智码即可。' -ForegroundColor Green
} catch { Write-Host ('未完成更换：'+$_.Exception.Message) -ForegroundColor Yellow; exit 1 }
finally {
    if ($stage -and (Test-Path -LiteralPath $stage)) { Remove-Item -LiteralPath $stage -ErrorAction SilentlyContinue }
    if ($lock) { $lock.Dispose() }
}
