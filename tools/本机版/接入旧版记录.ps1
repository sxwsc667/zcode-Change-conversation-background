param([string]$ResourcesDir='E:\ZCode\resources')
$ErrorActionPreference='Stop'
. (Join-Path (Split-Path $PSScriptRoot -Parent) '通用版\公共函数.ps1')
$resources=Resolve-Resources $ResourcesDir
$lock=Open-OperationLock $resources
$temp=$null
try {
    Assert-Stopped $resources
    if (Test-Path -LiteralPath (Join-Path $resources 'app.asar.custom-bg-state.json')) {
        $state=Read-InstalledState $resources
        Assert-Current $resources $state
        return
    }
    $original='172d6f333e61642ce3882250949fafe8180f75b5b8e5552244ca2c59ca05d14e'
    # 接手时实际核验过的本机背景包；未知版本不自动认领。
    $known=@($original,'64b3344cfc05a93b302ab06d9482930c26185a398eba86e1fc2222595e2f99c1')
    $target=Join-Path $resources 'app.asar'
    $current=Get-PackageHash $target
    if ($known -notcontains $current) { throw '本机程序已变化，无法安全接入。请勿恢复旧程序包，请让助手重新核验。' }
    $legacy=Join-Path $resources 'app.asar.bak-20261008'
    if ((Get-PackageHash $legacy) -ne $original) { throw '旧版原始备份校验失败。' }
    $restore=Join-Path $resources 'app.asar.custom-bg-restore'
    if (!(Test-Path -LiteralPath $restore)) { Copy-Item -LiteralPath $legacy -Destination $restore }
    if ((Get-PackageHash $restore) -ne $original) { throw '恢复点校验失败。' }
    Assert-Stopped $resources
    if ((Get-PackageHash $target) -ne $current) { throw '检查期间程序发生变化，停止登记。' }
    $temp=New-Stage $resources 'state-stage'
    @{schemaVersion=1;originalHash=$original;currentHash=$current} | ConvertTo-Json | Set-Content -LiteralPath $temp -Encoding UTF8
    [IO.File]::Move($temp,(Join-Path $resources 'app.asar.custom-bg-state.json'))
    Write-Host '已接入现有背景的安全管理，不更换当前壁纸、不改动聊天记录。'
} finally {
    if ($temp -and (Test-Path -LiteralPath $temp)) { Remove-Item -LiteralPath $temp -ErrorAction SilentlyContinue }
    $lock.Dispose()
}
