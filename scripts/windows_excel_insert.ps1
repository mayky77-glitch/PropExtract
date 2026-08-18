[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$Request)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'WindowsExcelInsert.Contract.psm1') -Force
$data = $null
try {
    $data = Get-Content -Raw -LiteralPath $Request | ConvertFrom-Json
    $result = Invoke-ExcelRowContract -Data $data
    # Stdout is the adapter result channel; optional artifact files are
    # written atomically inside the contract module.
    [Console]::Out.WriteLine((ConvertTo-ContractJson $result))
}
catch {
    $envelope = $_.Exception.Data['contract_envelope']
    if ($null -eq $envelope) { $envelope = Get-ExceptionEnvelope -ErrorRecord $_ -Stage 'request' }
    if ($data -and $data.PSObject.Properties.Name -contains 'error_file' -and $data.error_file -and -not (Test-Path -LiteralPath $data.error_file)) {
        Write-AtomicContractJson -Path ([string]$data.error_file) -Value $envelope
    }
    [Console]::Error.WriteLine((ConvertTo-ContractJson $envelope))
    exit 1
}
