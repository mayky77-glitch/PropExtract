[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$Uri = "http://127.0.0.1:8775/api/shutdown"
$Headers = @{ "X-PropExtract-Action" = "shutdown" }

try {
    $null = Invoke-RestMethod -Method Post -Uri $Uri -Headers $Headers -ContentType "application/json" -Body "{}" -TimeoutSec 8
    Write-Host "PropExtract stopped. You can close the browser tab." -ForegroundColor Green
    exit 0
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
    Write-Host "PropExtract is already stopped." -ForegroundColor Yellow
    exit 0
}
