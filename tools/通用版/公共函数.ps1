$ErrorActionPreference = 'Stop'
function Get-PackageHash([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw "找不到文件：$Path" }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $sha.Dispose() }
}
function Read-Settings {
    $path = Join-Path $PSScriptRoot '工具设置.json'
    if (Test-Path -LiteralPath $path) { return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json }
    return $null
}
function Resolve-Resources([string]$Requested) {
    if (!$Requested) { $Requested = [string](Read-Settings).resourcesDir }
    if (!$Requested) {
        $candidates = @()
        foreach ($drive in Get-PSDrive -PSProvider FileSystem) { $candidates += Join-Path $drive.Root 'ZCode\resources' }
        if ($env:LOCALAPPDATA) { $candidates += Join-Path $env:LOCALAPPDATA 'Programs\ZCode\resources' }
        if ($env:ProgramFiles) { $candidates += Join-Path $env:ProgramFiles 'ZCode\resources' }
        if (${env:ProgramFiles(x86)}) { $candidates += Join-Path ${env:ProgramFiles(x86)} 'ZCode\resources' }
        $found = @($candidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'app.asar') } | Select-Object -Unique)
        if ($found.Count -eq 1) { $Requested = $found[0] }
        else {
            Add-Type -AssemblyName System.Windows.Forms
            $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
            $dialog.Description = '请选择智码安装位置中的 resources（资源）文件夹；不要选择聊天记录目录。'
            try {
                if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { throw '已取消选择，没有修改程序。' }
                $Requested = $dialog.SelectedPath
            } finally { $dialog.Dispose() }
        }
    }
    $resolved = (Resolve-Path -LiteralPath $Requested).ProviderPath
    if (!(Test-Path -LiteralPath (Join-Path $resolved 'app.asar') -PathType Leaf)) { throw '选择的文件夹里没有智码程序资源包。' }
    return $resolved
}
function Assert-Stopped([string]$Resources) {
    $exe = [IO.Path]::GetFullPath((Join-Path (Split-Path $Resources -Parent) 'ZCode.exe'))
    # 无法读取任一同名进程的路径时也拒绝修改，避免权限不足导致漏检。
    $processes = @(Get-CimInstance Win32_Process -Filter "Name = 'ZCode.exe'")
    if ($processes | Where-Object { !$_.ExecutablePath -or [IO.Path]::GetFullPath($_.ExecutablePath) -ieq $exe }) {
        throw '请先从系统托盘彻底退出智码，再重试。本工具不会强行关闭应用。'
    }
}
function Open-OperationLock([string]$Resources) {
    try { return [IO.File]::Open((Join-Path $Resources 'app.asar.custom-bg-operation.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
    catch { throw '另一个背景工具正在操作，或安装目录没有写入权限。请稍后重试。' }
}
function Find-Python([string]$Requested) {
    if (!$Requested) { $Requested = [string](Read-Settings).pythonPath }
    $candidates = @()
    if ($Requested) { $candidates += @{exe=$Requested; prefix=@()} }
    else {
        foreach ($name in @('py','python','python3')) {
            $cmd = Get-Command $name -ErrorAction SilentlyContinue
            if ($cmd -and $cmd.Source -notlike '*\WindowsApps\*') {
                $prefix=@(); if ($name -eq 'py') { $prefix=@('-3') }
                $candidates += @{exe=$cmd.Source; prefix=$prefix}
            }
        }
        foreach ($key in @('HKCU:\Software\Python\PythonCore\*\InstallPath','HKLM:\Software\Python\PythonCore\*\InstallPath','HKLM:\Software\WOW6432Node\Python\PythonCore\*\InstallPath')) {
            foreach ($entry in @(Get-ItemProperty -Path $key -ErrorAction SilentlyContinue)) {
                $exe = $entry.ExecutablePath
                if (!$exe -and $entry.'(default)') { $exe = Join-Path $entry.'(default)' 'python.exe' }
                if ($exe) { $candidates += @{exe=$exe; prefix=@()} }
            }
        }
    }
    foreach ($candidate in $candidates) {
        try {
            $exe=$candidate.exe; $prefix=$candidate.prefix
            $old=$ErrorActionPreference; $ErrorActionPreference='Continue'
            & $exe @prefix -c "import sys; from PIL import Image; assert sys.version_info >= (3,8); assert hasattr(Image, 'Resampling')" *> $null
            $ok=($LASTEXITCODE -eq 0)
        } catch { $ok=$false } finally { $ErrorActionPreference=$old }
        if ($ok) { return $candidate }
    }
    throw '未找到可用的 Python（派森编程语言）3.8 以上环境和 Pillow（枕头图像库）9.1 以上版本。请看《使用说明》，或在工具设置中填写运行程序位置。不会自动下载或安装。'
}
function Read-PatchInfo([string]$Directory) {
    if (!$Directory) { $Directory = Join-Path $PSScriptRoot '补丁输出' }
    $path = Join-Path $Directory '补丁信息.json'
    if (!(Test-Path -LiteralPath $path)) { throw '找不到补丁信息，请先制作背景补丁。' }
    $info = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($info.schemaVersion -ne 1 -or $info.originalHash -notmatch '^[a-fA-F0-9]{64}$' -or $info.patchedHash -notmatch '^[a-fA-F0-9]{64}$' -or $info.patchedFile -cne 'app.asar.custom-bg') {
        throw '补丁信息格式无效。请使用本版本工具重新制作，不要沿用旧版结果。'
    }
    return $info
}
function Read-InstalledState([string]$Resources) {
    $path = Join-Path $Resources 'app.asar.custom-bg-state.json'
    if (!(Test-Path -LiteralPath $path)) { throw '找不到本版工具的安装记录。旧版背景请使用原来的本机工具，不要混用。' }
    $state = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($state.schemaVersion -ne 1 -or $state.originalHash -notmatch '^[a-fA-F0-9]{64}$' -or $state.currentHash -notmatch '^[a-fA-F0-9]{64}$') { throw '安装记录损坏，已停止操作。' }
    return $state
}
function Assert-Current([string]$Resources, $State) {
    if ((Get-PackageHash (Join-Path $Resources 'app.asar')) -ne $State.currentHash) { throw '当前程序与安装记录不一致，可能已经升级或被其他工具修改。禁止用旧程序包覆盖。' }
    $restore = Join-Path $Resources 'app.asar.custom-bg-restore'
    if (!(Test-Path -LiteralPath $restore) -or (Get-PackageHash $restore) -ne $State.originalHash) { throw '原版恢复点缺失或校验失败，已停止操作。' }
}
function New-Stage([string]$Resources, [string]$Kind) {
    return Join-Path $Resources ('app.asar.'+$Kind+'-'+[Guid]::NewGuid().ToString('N'))
}
function Publish-Package([string]$Resources,[string]$Stage,[string]$Before,[string]$After,$State) {
    # 两次改名不是断电级原子事务；异常可回退，进程被终止时保留的旧包可用于人工恢复。
    $target=Join-Path $Resources 'app.asar'
    $statePath=Join-Path $Resources 'app.asar.custom-bg-state.json'
    $stateStage=New-Stage $Resources 'state-stage'
    $stateBackup=New-Stage $Resources 'state-previous'
    $saved=New-Stage $Resources 'previous'
    $failed=New-Stage $Resources 'failed'
    $moved=$false
    try {
        if ((Get-PackageHash $Stage) -ne $After) { throw '待替换文件校验失败，原程序未改动。' }
        $State | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $stateStage -Encoding UTF8
        Assert-Stopped $Resources
        if ((Get-PackageHash $target) -ne $Before) { throw '处理期间程序发生了变化，原程序未改动。' }
        Move-Item -LiteralPath $target -Destination $saved
        $moved=$true
        Move-Item -LiteralPath $Stage -Destination $target
        if ((Get-PackageHash $target) -ne $After) { throw '替换后校验失败。' }
        if (Test-Path -LiteralPath $statePath) { [IO.File]::Replace($stateStage,$statePath,$stateBackup) }
        else { [IO.File]::Move($stateStage,$statePath) }
    } catch {
        $reason=$_.Exception.Message
        if ($moved) {
            try {
                if (Test-Path -LiteralPath $target) { Move-Item -LiteralPath $target -Destination $failed }
                Move-Item -LiteralPath $saved -Destination $target
            } catch { throw ('自动回退未完成。请勿启动软件，原程序保留于：'+$saved+'。原因：'+$reason) }
            throw ('操作失败，已恢复操作前的程序。原因：'+$reason)
        }
        throw
    } finally {
        if (Test-Path -LiteralPath $stateStage) { Remove-Item -LiteralPath $stateStage -ErrorAction SilentlyContinue }
    }
    Write-Host '已保留操作前的程序包；原版恢复点保持不变。'
}
