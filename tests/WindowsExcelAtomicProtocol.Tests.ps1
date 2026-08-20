if ($env:WINDOWS_EXCEL_ATOMIC_PROTOCOL_PESTER -ne '1') {
    if (-not (Get-Command Invoke-Pester -ErrorAction SilentlyContinue)) {
        throw 'Pester is required for WindowsExcelAtomicProtocol.Tests.ps1; this is a blocking validation prerequisite.'
    }
    $env:WINDOWS_EXCEL_ATOMIC_PROTOCOL_PESTER = '1'
    $run = Invoke-Pester -Path $PSCommandPath -PassThru
    if ($run.FailedCount -ne 0) { throw ("Pester failures: {0}" -f $run.FailedCount) }
    exit 0
}

Describe 'Windows Excel atomic protocol' {
    BeforeAll {
        $script:modulePath = Join-Path $PSScriptRoot '..' 'scripts' 'WindowsExcelAtomicProtocol.psm1'
        Import-Module $script:modulePath -Force
    }
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
        @(Get-ChildItem -LiteralPath $script:root -Filter '*.bak').Count | Should -Be 0
    }

    It 'flushes the stream to disk before disposal and replacement' {
        $source = Get-Content -Raw -LiteralPath $script:modulePath
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

    It 'removes a preseeded error before publishing the sole successful result' {
        [System.IO.File]::WriteAllText($script:error, '{"status":"error"}', [System.Text.UTF8Encoding]::new($false))
        $callbacks = @{
            BuildLease = { param($r) @{ operation_id = $r.operation_id; owner_nonce = $r.owner_nonce; pair_nonce = $r.pair_nonce } }
            ReadAck = { param($r) @{ operation_id = $r.operation_id; owner_nonce = $r.owner_nonce; pair_nonce = $r.pair_nonce } }
            Open = { param($r) $script:events.Add('open') }
            Execute = { param($r) @{ inserted = 1 } }
        }
        Invoke-WindowsExcelAtomicProtocol -Request $script:request -Callbacks $callbacks -LeaseFile $script:lease -ResultFile $script:result -ErrorFile $script:error | Out-Null
        Test-Path -LiteralPath $script:result | Should -BeTrue
        Test-Path -LiteralPath $script:error | Should -BeFalse
    }

    It 'removes a preseeded result before publishing the sole failed outcome' {
        [System.IO.File]::WriteAllText($script:result, '{"status":"ok"}', [System.Text.UTF8Encoding]::new($false))
        $callbacks = @{
            BuildLease = { param($r) @{ operation_id = $r.operation_id; owner_nonce = $r.owner_nonce; pair_nonce = $r.pair_nonce } }
            ReadAck = { param($r) @{ operation_id = $r.operation_id; owner_nonce = $r.owner_nonce; pair_nonce = $r.pair_nonce } }
            Open = { param($r) $script:events.Add('open') }
            Execute = { param($r) throw [System.ComponentModel.Win32Exception]::new(5, 'save denied') }
        }
        { Invoke-WindowsExcelAtomicProtocol -Request $script:request -Callbacks $callbacks -LeaseFile $script:lease -ResultFile $script:result -ErrorFile $script:error } | Should -Throw 'excel_atomic_protocol_failed:execute'
        Test-Path -LiteralPath $script:result | Should -BeFalse
        Test-Path -LiteralPath $script:error | Should -BeTrue
    }

    It 'rejects a locked stale final artifact before entering any operation callback' {
        [System.IO.File]::WriteAllText($script:result, '{"status":"ok","operation":"old"}', [System.Text.UTF8Encoding]::new($false))
        [System.IO.File]::WriteAllText($script:error, '{"status":"error","operation":"old"}', [System.Text.UTF8Encoding]::new($false))
        $callbacks = @{
            BuildLease = { param($r) $script:events.Add('lease'); @{ operation_id = $r.operation_id; owner_nonce = $r.owner_nonce; pair_nonce = $r.pair_nonce } }
            ReadAck = { param($r) $script:events.Add('ack'); @{ operation_id = $r.operation_id; owner_nonce = $r.owner_nonce; pair_nonce = $r.pair_nonce } }
            Open = { param($r) $script:events.Add('open') }
            Execute = { param($r) $script:events.Add('execute') }
        }
        $lock = $null
        try {
            $lock = New-Object System.IO.FileStream($script:error, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::None)
            { Invoke-WindowsExcelAtomicProtocol -Request $script:request -Callbacks $callbacks -LeaseFile $script:lease -ResultFile $script:result -ErrorFile $script:error } | Should -Throw 'excel_atomic_protocol_final_artifact_invalidation_failed:error:*'
            $script:events.Count | Should -Be 0
            Test-Path -LiteralPath $script:lease | Should -BeFalse
            Test-Path -LiteralPath $script:result | Should -BeFalse
        }
        finally {
            if ($null -ne $lock) { $lock.Dispose() }
        }
        (Get-Content -Raw -LiteralPath $script:error | ConvertFrom-Json).operation | Should -Be 'old'
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

    $faultCases = @(
        @{ name = 'lease'; events = @('lease', 'cleanup-first', 'cleanup-later') },
        @{ name = 'open'; events = @('lease', 'ack', 'open', 'cleanup-first', 'cleanup-later') },
        @{ name = 'execute'; events = @('lease', 'ack', 'open', 'execute', 'cleanup-first', 'cleanup-later') },
        @{ name = 'cleanup'; events = @('lease', 'ack', 'open', 'execute', 'cleanup-first', 'cleanup-later') }
    )
    It 'keeps exact <name> failure diagnostics and excludes downstream callbacks' -TestCases $faultCases {
        param($name, $events)
            $script:faultStage = $name
            $script:primaryFault = [System.ComponentModel.Win32Exception]::new(5, ($name + ' denied'))
            $script:cleanupFault = [System.ComponentModel.Win32Exception]::new(32, 'cleanup locked')
            $callbacks = @{
                BuildLease = {
                    param($r)
                    $script:events.Add('lease')
                    if ($script:faultStage -eq 'lease') { throw $script:primaryFault }
                    @{ operation_id = $r.operation_id; owner_nonce = $r.owner_nonce; pair_nonce = $r.pair_nonce }
                }
                ReadAck = {
                    param($r)
                    $script:events.Add('ack')
                    @{ operation_id = $r.operation_id; owner_nonce = $r.owner_nonce; pair_nonce = $r.pair_nonce }
                }
                Open = {
                    param($r)
                    $script:events.Add('open')
                    if ($script:faultStage -eq 'open') { throw $script:primaryFault }
                }
                Execute = {
                    param($r)
                    $script:events.Add('execute')
                    if ($script:faultStage -eq 'execute') { throw $script:primaryFault }
                    @{ inserted = 1 }
                }
                Cleanup = @(
                    {
                        param($r)
                        $script:events.Add('cleanup-first')
                        throw $script:cleanupFault
                    },
                    { param($r) $script:events.Add('cleanup-later') }
                )
            }
            { Invoke-WindowsExcelAtomicProtocol -Request $script:request -Callbacks $callbacks -LeaseFile $script:lease -ResultFile $script:result -ErrorFile $script:error } | Should -Throw ('excel_atomic_protocol_failed:' + $name)
            $script:events | Should -Be $events
            $failure = Get-Content -Raw -LiteralPath $script:error | ConvertFrom-Json
            $failure.primary.stage | Should -Be $name
            if ($name -eq 'cleanup') {
                $failure.primary.hresult | Should -Be $script:cleanupFault.HResult
                $failure.primary.winerror | Should -Be 32
            } else {
                $failure.primary.hresult | Should -Be $script:primaryFault.HResult
                $failure.primary.winerror | Should -Be 5
            }
            $failure.cleanup_failure.stage | Should -Be 'cleanup'
            $failure.cleanup_failure.hresult | Should -Be $script:cleanupFault.HResult
            $failure.cleanup_failure.winerror | Should -Be 32
            Test-Path -LiteralPath $script:result | Should -BeFalse
    }

    It 'makes final publication failures explicit and cannot report success' {
        $source = Get-Content -Raw -LiteralPath $script:modulePath
        $remove = $source.IndexOf('[System.IO.File]::Delete($StaleOpposite)', [System.StringComparison]::Ordinal)
        $write = $source.IndexOf('Write-AtomicProtocolJson -Path $Destination', [System.StringComparison]::Ordinal)
        $failure = $source.IndexOf('excel_atomic_protocol_final_publication_failed:', [System.StringComparison]::Ordinal)
        $invalidation = $source.IndexOf('Invalidate-AtomicProtocolFinalArtifacts -ResultFile $ResultFile -ErrorFile $ErrorFile', [System.StringComparison]::Ordinal)
        $leaseCallback = $source.IndexOf('$Callbacks.BuildLease', [System.StringComparison]::Ordinal)
        $remove | Should -BeGreaterThan -1
        $write | Should -BeGreaterThan $remove
        $failure | Should -BeGreaterThan -1
        $invalidation | Should -BeGreaterThan -1
        $leaseCallback | Should -BeGreaterThan $invalidation
    }
}
