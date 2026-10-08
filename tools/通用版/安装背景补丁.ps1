param([string]$ResourcesDir,[string]$PatchDir)
$ErrorActionPreference='Stop'
$lock=$null; $stage=$null
try {
    . (Join-Path $PSScriptRoot '公共函数.ps1')
    $resources=Resolve-Resources $ResourcesDir
    $lock=Open-OperationLock $resources
    Assert-Stopped $resources
    if (!$PatchDir) { $PatchDir=Join-Path $PSScriptRoot '补丁输出' }
    $info=Read-PatchInfo $PatchDir
    $patch=Join-Path $PatchDir $info.patchedFile
    if ((Get-PackageHash $patch) -ne $info.patchedHash) { throw '补丁包校验失败，禁止安装。' }
    $target=Join-Path $resources 'app.asar'
    $before=Get-PackageHash $target
    if (Test-Path -LiteralPath (Join-Path $resources 'app.asar.custom-bg-state.json')) {
        $old=Read-InstalledState $resources
        Assert-Current $resources $old
        if ($old.originalHash -ne $info.originalHash) { throw '此恢复点属于另一版本，禁止混用。' }
        if ($before -ne $old.originalHash) { Write-Host '背景已经安装。换图请用「更换壁纸」。'; exit 0 }
    }
    if ($before -ne $info.originalHash) { throw '当前程序与制作补丁时的原版不一致，可能已经升级或安装旧版背景。已停止安装。' }
    $restore=Join-Path $resources 'app.asar.custom-bg-restore'
    if (!(Test-Path -LiteralPath $restore)) { Copy-Item -LiteralPath $target -Destination $restore }
    if ((Get-PackageHash $restore) -ne $info.originalHash) { throw '原版恢复点校验失败，停止安装。' }
    $stage=New-Stage $resources 'install-stage'
    Copy-Item -LiteralPath $patch -Destination $stage
    $state=@{schemaVersion=1;originalHash=$info.originalHash;currentHash=$info.patchedHash}
    Publish-Package $resources $stage $before $info.patchedHash $state
    Write-Host '背景安装成功！重新打开智码即可。' -ForegroundColor Green
} catch { Write-Host ('未完成安装：'+$_.Exception.Message) -ForegroundColor Yellow; exit 1 }
finally {
    if ($stage -and (Test-Path -LiteralPath $stage)) { Remove-Item -LiteralPath $stage -ErrorAction SilentlyContinue }
    if ($lock) { $lock.Dispose() }
}
