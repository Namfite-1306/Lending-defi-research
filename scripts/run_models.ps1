param(
    [ValidateSet('check','all','rq1','rq2','rq3','rq4','rq5','rq6','rq7')][string]$Model = 'check',
    [string]$DataRun = 'data/runs/recovery_20261020',
    [string]$Config = 'configs/models.example.json',
    [string]$Out = '',
    [switch]$AllowExploratory,
    [switch]$Smoke
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Chay scripts/setup_models.ps1 truoc.' }
    $modelArgs = @('-m','defi_models',$Model,'--data-run',$DataRun,'--config',$Config)
    if ($Out) { $modelArgs += @('--out',$Out) }
    if ($AllowExploratory) { $modelArgs += '--allow-exploratory' }
    if ($Smoke) { $modelArgs += '--smoke' }
    & '.\.venv\Scripts\python.exe' @modelArgs
    if ($LASTEXITCODE -ne 0) { throw "Model run failed (exit $LASTEXITCODE); inspect manifest/error.txt." }
} finally { Pop-Location }
