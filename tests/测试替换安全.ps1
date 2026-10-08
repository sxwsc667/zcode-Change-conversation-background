param([string]$WorkDir)
$ErrorActionPreference='Stop'
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'tools\通用版\公共函数.ps1')
if (!$WorkDir) { throw '必须提供测试临时目录。' }
$base=[IO.Path]::GetFullPath($WorkDir)
New-Item -ItemType Directory -Path $base -Force | Out-Null
function Assert($Condition,[string]$Message) { if (!$Condition) { throw $Message } }
function Expect-Failure([scriptblock]$Action,[string]$Message) {
    $failed=$false
    try { & $Action } catch { $failed=$true }
    Assert $failed $Message
}
function New-Fixture([string]$Name) {
    $r=Join-Path $base $Name
    New-Item -ItemType Directory -Path $r | Out-Null
    [IO.File]::WriteAllText((Join-Path $r 'app.asar'),'old')
    [IO.File]::WriteAllText((Join-Path $r 'stage'),'new')
    return $r
}
$realHash=${function:Get-PackageHash}
function Assert-Stopped([string]$Resources) { }
$r=New-Fixture 'success'
$before=Get-PackageHash (Join-Path $r 'app.asar');$after=Get-PackageHash (Join-Path $r 'stage')
$state=@{schemaVersion=1;originalHash=$before;currentHash=$after}
Publish-Package $r (Join-Path $r 'stage') $before $after $state
Assert ((Get-PackageHash (Join-Path $r 'app.asar')) -eq $after) '发布失败'
Assert ((Read-InstalledState $r).currentHash -eq $after) '安装记录未提交'
Write-Output '通过：正常替换与安装记录'
$r=New-Fixture 'bad-stage'
Expect-Failure { Publish-Package $r (Join-Path $r 'stage') $before ('0'*64) $state } '应拒绝坏副本'
Assert ((Get-PackageHash (Join-Path $r 'app.asar')) -eq $before) '坏副本修改了原文件'
Write-Output '通过：坏副本拒绝替换'
$r=New-Fixture 'changed-target'
Expect-Failure { Publish-Package $r (Join-Path $r 'stage') ('0'*64) $after $state } '应拒绝发生变化的原文件'
Assert ((Get-PackageHash (Join-Path $r 'app.asar')) -eq $before) '竞态检查失效'
Write-Output '通过：处理期间变化被拒绝'
$r=New-Fixture 'post-check-failure'
$script:failTarget=Join-Path $r 'app.asar'
function Get-PackageHash([string]$Path) {
    $actual=& $realHash $Path
    if ($Path -eq $script:failTarget -and $actual -eq $after) { return ('0'*64) }
    return $actual
}
Expect-Failure { Publish-Package $r (Join-Path $r 'stage') $before $after $state } '应出现替换后校验失败'
Set-Item -LiteralPath Function:\Get-PackageHash -Value $realHash
Assert ((Get-PackageHash (Join-Path $r 'app.asar')) -eq $before) '替换后校验失败未回退'
Assert (!(Test-Path -LiteralPath (Join-Path $r 'app.asar.custom-bg-state.json'))) '失败不应记录成功状态'
Write-Output '通过：替换后校验失败自动回退'
$r=New-Fixture 'state-write-failure'
$statePath=Join-Path $r 'app.asar.custom-bg-state.json'
[IO.File]::WriteAllText($statePath,'old-state')
$held=[IO.File]::Open($statePath,'Open','Read','None')
try { Expect-Failure { Publish-Package $r (Join-Path $r 'stage') $before $after $state } '应出现状态提交失败' }
finally { $held.Dispose() }
Assert ((Get-PackageHash (Join-Path $r 'app.asar')) -eq $before) '状态提交失败未回退'
Assert ([IO.File]::ReadAllText($statePath) -eq 'old-state') '旧状态被破坏'
Write-Output '通过：安装记录写入失败自动回退'
$r=New-Fixture 'lock-test';$lock=Open-OperationLock $r
try { Expect-Failure { $another=Open-OperationLock $r; $another.Dispose() } '应拒绝并发操作' }
finally { $lock.Dispose() }
Write-Output '通过：并发操作拒绝'
$r=New-Fixture 'no-state'
Expect-Failure { Read-InstalledState $r } '应拒绝缺少安装记录'
Write-Output '通过：缺少安装记录拒绝'
$r=New-Fixture 'bad-manifest'
@{schemaVersion=1;originalHash=$before;patchedHash=$after;patchedFile='..\outside'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $r '补丁信息.json') -Encoding UTF8
Expect-Failure { Read-PatchInfo $r } '应拒绝补丁路径越界'
Write-Output '通过：补丁信息路径越界拒绝'
Write-Output '公共安全函数：8 项测试全部通过。'
