$ErrorActionPreference='Stop'
try {
    & (Join-Path $PSScriptRoot '接入旧版记录.ps1')
    $shared=Join-Path (Split-Path $PSScriptRoot -Parent) '通用版'
    . (Join-Path $shared '公共函数.ps1')
    $state=Read-InstalledState 'E:\ZCode\resources'
    if ($state.currentHash -ne $state.originalHash) { Write-Host '背景已安装。更换图片请使用「更换壁纸」。'; exit 0 }
    $patch=Join-Path $shared '补丁输出'
    if (!(Test-Path -LiteralPath (Join-Path $patch '补丁信息.json'))) {
        & (Join-Path $shared '制作背景补丁.ps1') -Asar 'E:\ZCode\resources\app.asar' -Output $patch -Python 'E:\python\python.exe'
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    & (Join-Path $shared '安装背景补丁.ps1') -ResourcesDir 'E:\ZCode\resources' -PatchDir $patch
    exit $LASTEXITCODE
} catch { Write-Host ('未完成安装：'+$_.Exception.Message) -ForegroundColor Yellow; exit 1 }
