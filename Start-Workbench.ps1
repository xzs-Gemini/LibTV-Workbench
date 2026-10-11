param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
try {
    $null = Invoke-RestMethod 'http://127.0.0.1:5212/api/state' -TimeoutSec 2
    if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:5212' }
    return
} catch { }
$runtimePython = $env:LIBTV_PYTHON
if (-not $runtimePython) {
    $localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localPython) { $runtimePython = $localPython }
    else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCommand) { $runtimePython = $pythonCommand.Source }
    }
}
if (-not $runtimePython) { throw '请安装 Python 3.12，或用 LIBTV_PYTHON 指定 python.exe 的完整路径。' }
$logDir = Join-Path $PSScriptRoot 'data'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
Start-Process -FilePath $runtimePython -ArgumentList '-m','workbench.server' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir 'server.log') -RedirectStandardError (Join-Path $logDir 'server-error.log')
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:5212' }
