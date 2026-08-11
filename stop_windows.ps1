[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$Url = "http://127.0.0.1:8775"
$Uri = "http://127.0.0.1:8775/api/shutdown"
$Headers = @{ "X-PropExtract-Action" = "shutdown" }
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LockPath = Join-Path $Root "windows-runtime.lock.json"

function Get-PropExtractMessage([string]$Key) {
    switch ($Key) {
        "identity" { return [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String("HQQ1BCAAQwQ0BDAEOwQ+BEEETAQgAD4EPwRABDUENAQ1BDsEOARCBEwEIAA4BDQENQQ9BEIEOAREBDgEOgQwBEIEPgRABCAATQQ6BDcENQQ8BD8EOwRPBEAEMAQgAFAAcgBvAHAARQB4AHQAcgBhAGMAdAAuACAAHwRABD4EMgQ1BEAETARCBDUEIABDBEEEQgQwBD0EPgQyBDoEQwQgAD8EQAQ+BDUEOgRCBDAELgA=")) }
        "missing" { return [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String("HQQ1BCAAQwQ0BDAEOwQ+BEEETAQgAD8EQAQ+BDIENQRABDgEQgRMBCAATQQ6BDcENQQ8BD8EOwRPBEAEIABQAHIAbwBwAEUAeAB0AHIAYQBjAHQAOgAgAD0ENQQgAD0EMAQ5BDQENQQ9BCAAPwQ1BEAENQQ9BD4EQQQ4BDwESwQ5BCAAUAB5AHQAaABvAG4ALgAgABcEMAQ/BEMEQQRCBDgEQgQ1BCAAUAByAG8AcABFAHgAdAByAGEAYwB0ACAARwQ1BEAENQQ3BCAAcwB0AGEAcgB0AF8AdwBpAG4AZABvAHcAcwAuAGMAbQBkAC4A")) }
        "occupied" { return [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String("HwQ+BEAEQgQgADgANwA3ADUAIAA3BDAEPQRPBEIEIAA0BEAEQwQzBD4EOQQgAEEEOwRDBDYEMQQ+BDkEIAA4BDsEOAQgADQEQARDBDMEPgQ5BCAAOgQ+BD8EOAQ1BDkEIABQAHIAbwBwAEUAeAB0AHIAYQBjAHQALgAgAB4EQQRCBDAEPQQ+BDIEOgQwBCAAPgRCBDwENQQ9BDUEPQQwBC4A")) }
        "wrong" { return [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String("FwQwBD8EQwRJBDUEPQQwBCAANARABEMEMwQwBE8EIAA6BD4EPwQ4BE8EIABQAHIAbwBwAEUAeAB0AHIAYQBjAHQAIAA4BDsEOAQgADQEQARDBDMEMARPBCAAQQQ7BEMENgQxBDAELgAgAB4EQQRCBDAEPQQ+BDIEOgQwBCAAPgRCBDwENQQ9BDUEPQQwBDsAIABCBDUEOgRDBEkEOAQ5BCAATQQ6BDcENQQ8BD8EOwRPBEAEIAA9BDUEIAAxBEMENAQ1BEIEIAA4BDcEPAQ1BD0EUQQ9BC4A")) }
        "stopped" { return [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String("GARBBEUEPgQ0BD0ESwQ5BCAATQQ6BDcENQQ8BD8EOwRPBEAEIABQAHIAbwBwAEUAeAB0AHIAYQBjAHQAIAA+BEEEQgQwBD0EPgQyBDsENQQ9BC4AIAAUBEAEQwQzBD4EOQQgAE0EOgQ3BDUEPAQ/BDsETwRABCAAPQQ1BCAAOAQ3BDwENQQ9BFEEPQQuAA==")) }
        "timeout" { return [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String("HQQ1BCAAQwQ0BDAEOwQ+BEEETAQgADQEPgQ2BDQEMARCBEwEQQRPBCAAPgRBBEIEMAQ9BD4EMgQ6BDgEIABQAHIAbwBwAEUAeAB0AHIAYQBjAHQAIAA3BDAEIAAxADIAIABBBDUEOgRDBD0ENAQuACAAHwQ+BEEEOwQ1BDQEPQRPBE8EIAA/BEAEPgQyBDUEQAQ6BDAEIAAvAGgAZQBhAGwAdABoACAAPQQ1BCAAPwQ+BDQEQgQyBDUEQAQ0BDgEOwQwBCAANwQwBDIENQRABEgENQQ9BDgENQQgADgEQQRFBD4ENAQ9BD4EMwQ+BCAATQQ6BDcENQQ8BD8EOwRPBEAEMAQuAA==")) }
        "command" { return [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String("HQQ1BCAAQwQ0BDAEOwQ+BEEETAQgAD4EQgQ/BEAEMAQyBDgEQgRMBCAAOgQ+BDwEMAQ9BDQEQwQgAD4EQQRCBDAEPQQ+BDIEOgQ4BCAAUAByAG8AcABFAHgAdAByAGEAYwB0ADoAIAA=")) }
        default { return "PropExtract lifecycle error" }
    }
}

function Get-PropExtractHealth {
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri "$Url/health" -TimeoutSec 2
        $Health = $Response.Content | ConvertFrom-Json
        $Health | Add-Member -NotePropertyName "instance_id" -NotePropertyValue ([string]$Response.Headers["X-PropExtract-Instance"]) -Force
        return $Health
    } catch {
        return $null
    }
}

function Test-LoopbackPortOpen {
    $Client = New-Object System.Net.Sockets.TcpClient
    try {
        $Client.Connect("127.0.0.1", 8775)
        return $true
    } catch {
        return $false
    } finally {
        $Client.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $LockPath -PathType Leaf)) {
    throw (Get-PropExtractMessage "missing")
}
$RuntimeLock = Get-Content -LiteralPath $LockPath -Raw -Encoding UTF8 | ConvertFrom-Json
$RuntimeRoot = Join-Path $Root ".runtime\windows"
$PythonRoot = Join-Path $RuntimeRoot ("python-" + [string]$RuntimeLock.artifacts.python.version)
$RuntimePython = Join-Path $PythonRoot ([string]$RuntimeLock.pythonTree.executablePath)
if (-not (Test-Path -LiteralPath $RuntimePython -PathType Leaf)) {
    throw (Get-PropExtractMessage "missing")
}
$InstanceId = (& $RuntimePython -B -S -c "from rns_import_server.server import project_instance_id; print(project_instance_id())" | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $InstanceId -notmatch '^[0-9a-f]{64}$') {
    throw (Get-PropExtractMessage "identity")
}
$Health = Get-PropExtractHealth
if ($null -eq $Health) {
    if (Test-LoopbackPortOpen) {
        throw (Get-PropExtractMessage "occupied")
    }
    Write-Host "PropExtract is already stopped." -ForegroundColor Yellow
    exit 0
}
if ($Health.status -ne "ok" -or $Health.service -ne "rns-import" -or $Health.instance_id -ne $InstanceId) {
    throw (Get-PropExtractMessage "wrong")
}

try {
    $null = Invoke-RestMethod -Method Post -Uri $Uri -Headers $Headers -ContentType "application/json" -Body "{}" -TimeoutSec 8
} catch [System.Net.WebException] {
    $Response = $_.Exception.Response
    if ($Response) {
        try {
            $Reader = New-Object System.IO.StreamReader($Response.GetResponseStream())
            $Payload = $Reader.ReadToEnd() | ConvertFrom-Json
            $Reader.Dispose()
            Write-Host ([string]$Payload.error) -ForegroundColor Red
        } catch {
            Write-Host "PropExtract could not stop: $($_.Exception.Message)" -ForegroundColor Red
        }
        exit 1
    }
    throw "$(Get-PropExtractMessage "command")$($_.Exception.Message)"
}

$Deadline = [DateTime]::UtcNow.AddSeconds(12)
while ([DateTime]::UtcNow -lt $Deadline) {
    $Health = Get-PropExtractHealth
    if ($null -eq $Health -and -not (Test-LoopbackPortOpen)) {
        Write-Host "PropExtract stopped. You can close the browser tab." -ForegroundColor Green
        exit 0
    }
    if ($null -ne $Health -and ($Health.status -ne "ok" -or $Health.service -ne "rns-import" -or $Health.instance_id -ne $InstanceId)) {
        Write-Host (Get-PropExtractMessage "stopped") -ForegroundColor Green
        exit 0
    }
    Start-Sleep -Milliseconds 200
}
throw (Get-PropExtractMessage "timeout")
