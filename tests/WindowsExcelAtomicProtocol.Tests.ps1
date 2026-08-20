$modulePath = Join-Path $PSScriptRoot '..' 'scripts' 'WindowsExcelAtomicProtocol.psm1'

if ($env:WINDOWS_EXCEL_ATOMIC_PROTOCOL_PESTER -ne '1') {
    if (-not (Get-Command Invoke-Pester -ErrorAction SilentlyContinue)) {
        throw 'Pester is required for WindowsExcelAtomicProtocol.Tests.ps1; this is a blocking validation prerequisite.'
    }
    $env:WINDOWS_EXCEL_ATOMIC_PROTOCOL_PESTER = '1'
    $run = Invoke-Pester -Path $PSCommandPath -PassThru
    if ($run.FailedCount -ne 0) { throw ("Pester failures: {0}" -f $run.FailedCount) }
    exit 0
}

Import-Module $modulePath -Force

Describe 'Windows Excel atomic protocol' {
    BeforeEach {
        $script:root = Join-Path ([System.IO.Path]::GetTempPath()) ('excel-atomic-' + [Guid]::NewGuid().ToString('N'))
        [System.IO.Directory]::CreateDirectory($script:root) | Out-Null
        $script:request = [pscustomobject]@{ operation_id = 'operation'; owner_nonce = 'owner'; pair_nonce = 'pair' }
        $script:lease = Join-Path $script:root 'lease.json'
        $script:result = Join-Path $script:root 'result.json'
        $script:error = Join-Path $script:root 'error.json'
        $script:events = [System.Collections.Generic.List[string]]::new()
    }
    AfterEach { if (Test-Path -LiteralPath $script:root) { Remove-Item -Recurse -Force -LiteralPath $script:root } }

    It 'durably writes BOM-free JSON and atomically replaces an existing artifact' {
        $path = Join-Path $script:root 'artifact.json'
        [System.IO.File]::WriteAllText($path, '{"old":true}', [System.Text.UTF8Encoding]::new($false))
        Write-AtomicProtocolJson -Path $path -Value ([ordered]@{ value = 'новое' })
        $bytes = [System.IO.File]::ReadAllBytes($path)
        (($bytes[0] -eq 0xEF) -and ($bytes[1] -eq 0xBB) -and ($bytes[2] -eq 0xBF)) | Should -BeFalse
        (Get-Content -Raw -LiteralPath $path | ConvertFrom-Json).value | Should -Be 'новое'
        @(Get-ChildItem -LiteralPath $script:root -Filter '*.tmp').Count | Should -Be 0
    }

    It 'flushes the stream to disk before disposal and replacement' {
        $source = Get-Content -Raw -LiteralPath $modulePath
        $flush = $source.IndexOf('$stream.Flush($true)', [System.StringComparison]::Ordinal)
        $dispose = $source.IndexOf('$stream.Dispose()', [System.StringComparison]::Ordinal)
        $replace = $source.IndexOf('[System.IO.File]::Replace', [System.StringComparison]::Ordinal)
        $flush | Should -BeGreaterThan -1
        $dispose | Should -BeGreaterThan $flush
        $replace | Should -BeGreaterThan $dispose
    }

    It 'writes a durable lease, validates exact ACK, then opens and publishes one result' {
        $callbacks = @{
            BuildLease = { param($r) $script:events.Add('lease') ; @{ operation_id = $r.operation_id; owner_nonce = $r.owner_nonce; pair_nonce = $r.pair_nonce; excel_pid = 42 } }
            ReadAck = { param($r) $script:events.Add('ack') ; @{ operation_id = $r.operation_id; owner_nonce = $r.owner_nonce; pair_nonce = $r.pair_nonce } }
            Open = { param($r) $script:events.Add('open') }
            Execute = { param($r) $script:events.Add('execute') ; @{ inserted = 1 } }
            Cleanup = @({ param($r) $script:events.Add('cleanup-one') }, { param($r) $script:events.Add('cleanup-two') })
        }
        $value = Invoke-WindowsExcelAtomicProtocol -Request $script:request -Callbacks $callbacks -LeaseFile $script:lease -ResultFile $script:result -ErrorFile $script:error
        $script:events | Should -Be @('lease', 'ack', 'open', 'execute', 'cleanup-one', 'cleanup-two')
        (Get-Content -Raw -LiteralPath $script:lease | ConvertFrom-Json).excel_pid | Should -Be 42
        (Get-Content -Raw -LiteralPath $script:result | ConvertFrom-Json).status | Should -Be 'ok'
        Test-Path -LiteralPath $script:error | Should -BeFalse
        $value.inserted | Should -Be 1
    }

    It 'does not open on an invalid ACK and records the exact primary failure' {
        $callbacks = @{
            BuildLease = { param($r) $script:events.Add('lease'); @{ operation_id = $r.operation_id; owner_nonce = $r.owner_nonce; pair_nonce = $r.pair_nonce } }
            ReadAck = { param($r) $script:events.Add('ack'); @{ operation_id = $r.operation_id; owner_nonce = 'wrong'; pair_nonce = $r.pair_nonce } }
            Open = { param($r) $script:events.Add('open') }
            Execute = { param($r) $script:events.Add('execute') }
        }
        { Invoke-WindowsExcelAtomicProtocol -Request $script:request -Callbacks $callbacks -LeaseFile $script:lease -ResultFile $script:result -ErrorFile $script:error } | Should -Throw 'excel_atomic_protocol_failed:ack'
        $script:events | Should -Be @('lease', 'ack')
        $failure = Get-Content -Raw -LiteralPath $script:error | ConvertFrom-Json
        $failure.primary.stage | Should -Be 'ack'
        $failure.primary.message | Should -Match 'excel_lease_ack_mismatch:owner_nonce'
        Test-Path -LiteralPath $script:result | Should -BeFalse
    }

    It 'runs all cleanup callbacks and keeps the execute failure primary' {
        $callbacks = @{
            BuildLease = { param($r) @{ operation_id = $r.operation_id; owner_nonce = $r.owner_nonce; pair_nonce = $r.pair_nonce } }
            ReadAck = { param($r) @{ operation_id = $r.operation_id; owner_nonce = $r.owner_nonce; pair_nonce = $r.pair_nonce } }
            Open = { param($r) $script:events.Add('open') }
            Execute = { param($r) throw [System.ComponentModel.Win32Exception]::new(5, 'save denied') }
            Cleanup = @({ param($r) $script:events.Add('cleanup-one'); throw 'first cleanup' }, { param($r) $script:events.Add('cleanup-two'); throw 'second cleanup' })
        }
        { Invoke-WindowsExcelAtomicProtocol -Request $script:request -Callbacks $callbacks -LeaseFile $script:lease -ResultFile $script:result -ErrorFile $script:error } | Should -Throw 'excel_atomic_protocol_failed:execute'
        $script:events | Should -Be @('open', 'cleanup-one', 'cleanup-two')
        $failure = Get-Content -Raw -LiteralPath $script:error | ConvertFrom-Json
        $failure.primary.stage | Should -Be 'execute'
        $failure.primary.winerror | Should -Be 5
        $failure.cleanup_failure.message | Should -Be 'first cleanup'
        Test-Path -LiteralPath $script:result | Should -BeFalse
    }
}
