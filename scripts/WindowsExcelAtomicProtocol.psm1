Set-StrictMode -Version Latest

function Get-AtomicProtocolFailure {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][System.Exception]$Exception
    )

    $hresult = $null
    $winerror = $null
    if ($null -ne $Exception.HResult) { $hresult = [int]$Exception.HResult }
    if ($Exception.PSObject.Properties.Name -contains 'NativeErrorCode') {
        $winerror = [int]$Exception.NativeErrorCode
    }
    elseif ($Exception.InnerException -and ($Exception.InnerException.PSObject.Properties.Name -contains 'NativeErrorCode')) {
        $winerror = [int]$Exception.InnerException.NativeErrorCode
    }
    [ordered]@{
        stage = $Stage
        message = [string]$Exception.Message
        hresult = $hresult
        winerror = $winerror
    }
}

function Write-AtomicProtocolJson {
    <#
    A completed write is not published until the UTF-8 stream has flushed its
    buffers to disk and has been disposed.  File.Replace is the durable,
    atomic replacement path for an existing NTFS destination.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value
    )

    $destination = [System.IO.Path]::GetFullPath($Path)
    $directory = [System.IO.Path]::GetDirectoryName($destination)
    if ([string]::IsNullOrWhiteSpace($directory)) { throw 'atomic_json_path_requires_parent' }
    [System.IO.Directory]::CreateDirectory($directory) | Out-Null
    $temporary = Join-Path $directory ('.{0}.{1}.tmp' -f [System.IO.Path]::GetFileName($destination), [Guid]::NewGuid().ToString('N'))
    $stream = $null
    try {
        $json = $Value | ConvertTo-Json -Compress -Depth 16
        $bytes = New-Object System.Text.UTF8Encoding($false)
        $payload = $bytes.GetBytes($json)
        $stream = New-Object System.IO.FileStream($temporary, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        $stream.Write($payload, 0, $payload.Length)
        $stream.Flush($true)
        $stream.Dispose()
        $stream = $null
        if ([System.IO.File]::Exists($destination)) {
            [System.IO.File]::Replace($temporary, $destination, $null)
        }
        else {
            [System.IO.File]::Move($temporary, $destination)
        }
    }
    finally {
        if ($null -ne $stream) { $stream.Dispose() }
        if ([System.IO.File]::Exists($temporary)) { [System.IO.File]::Delete($temporary) }
    }
}

function Assert-ExactAtomicAck {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]$Request,
        [Parameter(Mandatory = $true)]$Ack
    )

    foreach ($name in @('operation_id', 'owner_nonce', 'pair_nonce')) {
        if ($null -eq $Ack -or $Ack.$name -cne $Request.$name) {
            throw ('excel_lease_ack_mismatch:{0}' -f $name)
        }
    }
}

function Assert-ExactAtomicLease {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]$Request,
        [Parameter(Mandatory = $true)]$Lease
    )

    foreach ($name in @('operation_id', 'owner_nonce', 'pair_nonce')) {
        if ($Lease.$name -cne $Request.$name) {
            throw ('excel_lease_identity_mismatch:{0}' -f $name)
        }
    }
}

function Invoke-WindowsExcelAtomicProtocol {
    <#
    Callbacks are intentionally injected so this protocol can be tested without
    Excel. BuildLease must return the truthful identity obtained by its owner;
    this wrapper durably publishes it before it calls ReadAck. Open is never
    called until the nonce-bound ACK has passed exact comparison.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]$Request,
        [Parameter(Mandatory = $true)][hashtable]$Callbacks,
        [Parameter(Mandatory = $true)][string]$LeaseFile,
        [Parameter(Mandatory = $true)][string]$ResultFile,
        [Parameter(Mandatory = $true)][string]$ErrorFile
    )

    if ([System.IO.Path]::GetFullPath($ResultFile) -ceq [System.IO.Path]::GetFullPath($ErrorFile)) {
        throw 'final_artifact_paths_must_differ'
    }
    foreach ($required in @('BuildLease', 'ReadAck', 'Open', 'Execute')) {
        if (-not $Callbacks.ContainsKey($required) -or $null -eq $Callbacks[$required]) {
            throw ('missing_atomic_protocol_callback:{0}' -f $required)
        }
    }

    $primary = $null
    $cleanupFailure = $null
    $result = $null
    try {
        try {
            $lease = & $Callbacks.BuildLease $Request
            if ($null -eq $lease) { throw 'truthful_lease_missing' }
            Assert-ExactAtomicLease -Request $Request -Lease $lease
            Write-AtomicProtocolJson -Path $LeaseFile -Value $lease
        }
        catch { $primary = Get-AtomicProtocolFailure -Stage 'lease' -Exception $_.Exception }

        if ($null -eq $primary) {
            try {
                $ack = & $Callbacks.ReadAck $Request
                Assert-ExactAtomicAck -Request $Request -Ack $ack
            }
            catch { $primary = Get-AtomicProtocolFailure -Stage 'ack' -Exception $_.Exception }
        }
        if ($null -eq $primary) {
            try { & $Callbacks.Open $Request }
            catch { $primary = Get-AtomicProtocolFailure -Stage 'open' -Exception $_.Exception }
        }
        if ($null -eq $primary) {
            try { $result = & $Callbacks.Execute $Request }
            catch { $primary = Get-AtomicProtocolFailure -Stage 'execute' -Exception $_.Exception }
        }
    }
    finally {
        if ($Callbacks.ContainsKey('Cleanup') -and $null -ne $Callbacks.Cleanup) {
            foreach ($cleanup in @($Callbacks.Cleanup)) {
                try { & $cleanup $Request }
                catch {
                    if ($null -eq $cleanupFailure) {
                        $cleanupFailure = Get-AtomicProtocolFailure -Stage 'cleanup' -Exception $_.Exception
                    }
                }
            }
        }
    }

    if ($null -eq $primary -and $null -ne $cleanupFailure) { $primary = $cleanupFailure }
    if ($null -ne $primary) {
        $failure = [ordered]@{ status = 'error'; primary = $primary; cleanup_failure = $cleanupFailure }
        Write-AtomicProtocolJson -Path $ErrorFile -Value $failure
        throw ([System.InvalidOperationException]::new(('excel_atomic_protocol_failed:{0}' -f $primary.stage)))
    }

    Write-AtomicProtocolJson -Path $ResultFile -Value ([ordered]@{ status = 'ok'; result = $result; cleanup_failure = $null })
    return $result
}

Export-ModuleMember -Function Write-AtomicProtocolJson, Assert-ExactAtomicAck, Invoke-WindowsExcelAtomicProtocol
