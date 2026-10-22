param([int]$Port=8787,[int]$WalletLimit=10,[string]$WalletFile='')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Tao .venv va cai requirements-models.txt truoc.' }
    $liveArgs=@('-m','defi_live','--port',$Port,'--wallet-limit',$WalletLimit)
    if ($WalletFile) { $liveArgs+=@('--wallet-file',$WalletFile) }
    & '.\.venv\Scripts\python.exe' @liveArgs
} finally { Pop-Location }
