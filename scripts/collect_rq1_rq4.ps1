param([int]$WaitForPid = 0, [switch]$RunModels)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$jobRoot = Join-Path $projectRoot 'output\rq1_rq4_acquisition'
New-Item -ItemType Directory -Path $jobRoot -Force | Out-Null
$jobState = Join-Path $jobRoot 'collection_status.json'
$jobLock = $null
$phaseName = 'initializing'
$modelResultRoot = $null

function Save-CollectionState([string]$Status, [string]$Detail = '') {
    [ordered]@{
        status = $Status; phase = $phaseName; updated_utc = [DateTime]::UtcNow.ToString('o')
        pid = $PID; data_run = 'data/runs/recovery_20261020'; models = @(1,4)
        start_utc = '2023-01-27T00:00:00Z'; end_exclusive_utc = '2026-10-01T00:00:00Z'
        snapshot_block = 21762264; detail = $Detail
        model_result_root = $modelResultRoot
        run_models_requested = [bool]$RunModels
    } | ConvertTo-Json | Set-Content -LiteralPath $jobState -Encoding UTF8
}

Push-Location -LiteralPath $projectRoot
try {
    # File sharing lock releases automatically after a crash, without deleting data.
    $jobLock = [IO.File]::Open((Join-Path $jobRoot 'collection.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Missing .venv Python; run scripts/setup_models.ps1 -SkipDataCheck first.' }
    if ($WaitForPid -gt 0) {
        $phaseName = 'waiting_for_current_history'
        Save-CollectionState 'running' ('Waiting for history process ' + $WaitForPid)
        Wait-Process -Id $WaitForPid -ErrorAction SilentlyContinue
    }
    $phases = @(
        @{name='history'; args=@('-u','-m','defi_data.recovery','history','--workers','2','--chunk','10000','--protocols','aave_v3')},
        @{name='prices'; args=@('-u','-m','defi_data.recovery_prices','--feeds','ETH/USD','BTC/USD')},
        @{name='features'; args=@('-u','-m','defi_data.recovery_features')},
        @{name='snapshot'; args=@('-u','-m','defi_data.recovery_positions')},
        @{name='audit_1'; args=@('-u','-m','defi_data.recovery_audit','1','--models','1','4'); audit='audit_1_structure.json'},
        @{name='audit_2'; args=@('-u','-m','defi_data.recovery_audit','2','--models','1','4'); audit='audit_2_onchain.json'},
        @{name='audit_3'; args=@('-u','-m','defi_data.recovery_audit','3','--models','1','4'); audit='audit_3_research.json'},
        @{name='model_input_check'; args=@('-u','-m','defi_models','check','--check-models','1','4')}
    )
    if ($RunModels) {
        $modelResultRoot = 'results/rq14_full_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
        $phases += @(
            @{name='rq1_model'; args=@('-u','-m','defi_models','rq1','--config','configs/models.example.json','--out',($modelResultRoot + '/rq1_run'))},
            @{name='rq4_model'; args=@('-u','-m','defi_models','rq4','--config','configs/models.example.json','--out',($modelResultRoot + '/rq4_run'))},
            @{name='validate_rq1'; args=@('-u','scripts/validate_model_run.py',($modelResultRoot + '/rq1_run'))},
            @{name='validate_rq4'; args=@('-u','scripts/validate_model_run.py',($modelResultRoot + '/rq4_run'))}
        )
    }
    foreach ($phase in $phases) {
        $phaseName = $phase.name
        Save-CollectionState 'running'
        Write-Output ([DateTime]::UtcNow.ToString('o') + ' Starting ' + $phaseName)
        $stdout = Join-Path $jobRoot ($phaseName + '.stdout.log')
        $stderr = Join-Path $jobRoot ($phaseName + '.stderr.log')
        $phaseProcess = Start-Process -FilePath $pythonExe -ArgumentList $phase.args -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -Wait -PassThru
        if ($phaseProcess.ExitCode -ne 0) { throw ($phaseName + ' failed; inspect ' + $stdout + ' and ' + $stderr) }
        if ($phase.audit) {
            $auditPath = Join-Path $projectRoot ('data\runs\recovery_20261020\' + $phase.audit)
            $audit = Get-Content -LiteralPath $auditPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if (-not $audit.all_integrity_passed) { throw ($phaseName + ' integrity checks failed; inspect ' + $auditPath) }
        }
    }
    if ($RunModels) {
        @{rq1_results=($modelResultRoot + '/rq1_run'); rq4_results=($modelResultRoot + '/rq4_run'); historical_results=($modelResultRoot + '/rq4_run')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $jobRoot 'historical_results.json') -Encoding UTF8
    }
    $completionDetail = 'RQ1/RQ4 inputs passed scoped audits and model preflight. Other RQs are not certified.'
    if ($RunModels) { $completionDetail += ' Requested models passed output validation.' }
    $phaseName = 'completed'; Save-CollectionState 'completed' $completionDetail
} catch {
    if ($null -ne $jobLock) { Save-CollectionState 'failed' $_.Exception.Message }
    Write-Error $_
    exit 1
} finally {
    if ($null -ne $jobLock) { $jobLock.Dispose() }
    Pop-Location
}
