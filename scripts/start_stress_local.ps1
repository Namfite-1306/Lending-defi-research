param(
  [string]$Python = 'C:\Users\HAI NAM\Finance1\defi-research\.venv\Scripts\python.exe',
  [int]$Port = 8790,
  [int]$UniverseBatch = 200,
  [int]$SnapshotWallets = 40
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$env:TEMP=Join-Path $projectRoot 'tmp'
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
$historyPath=Join-Path $projectRoot 'results\merged_7rq_20261023_final'
if (-not (Test-Path -LiteralPath $historyPath)) { $historyPath=Join-Path $projectRoot 'results\full_7rq_20261022_final' }
$manifest=Get-Content -LiteralPath (Join-Path $historyPath 'manifest.json') -Raw | ConvertFrom-Json
$datasetPath=$manifest.data_run
$seedPath=Join-Path $datasetPath 'processed\borrower_universe.csv'
$dataRoot=Split-Path (Split-Path $datasetPath -Parent) -Parent
$backtestPath=Join-Path $dataRoot 'stress_backtests_20261024'
$canonicalRoot=Split-Path $dataRoot -Parent
$researchData=Join-Path $dataRoot 'research_h124_20261024'
$researchResults=Join-Path $canonicalRoot 'results\research_h124_20261024'
& $Python -m defi_live --port $Port --state-dir data/live/stress_local_20261024 --lookback-blocks 30 --wallet-limit $SnapshotWallets --universe-seed $seedPath --universe-batch $UniverseBatch --universe-seconds 30 --snapshot-seconds 300 --historical-results $historyPath --evidence-dir results/stress_validation_20261024 --backtest-dir $backtestPath --research-data $researchData --research-results $researchResults
exit $LASTEXITCODE
