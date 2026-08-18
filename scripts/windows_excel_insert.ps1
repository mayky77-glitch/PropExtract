[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$Request)

$ErrorActionPreference = 'Stop'
$data = Get-Content -Raw -LiteralPath $Request | ConvertFrom-Json
$excel = $null
$control = $null
$candidate = $null
try {
    # A future launcher writes and verifies the nonce-matched lease ACK before
    # this helper can open either workbook.  Refuse rather than guessing.
    if (-not (Test-Path -LiteralPath $data.ack_file)) { throw 'excel_lease_ack_missing' }
    $ack = Get-Content -Raw -LiteralPath $data.ack_file | ConvertFrom-Json
    if ($ack.operation_id -ne $data.operation_id -or $ack.owner_nonce -ne $data.owner_nonce -or $ack.pair_nonce -ne $data.pair_nonce) {
        throw 'excel_lease_ack_mismatch'
    }
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.EnableEvents = $false
    $excel.AskToUpdateLinks = $false
    $control = $excel.Workbooks.Open($data.control, 0, $false)
    $excel.CalculateFullRebuild()
    $control.Save()
    $control.Close($true)
    $control = $null
    $candidate = $excel.Workbooks.Open($data.candidate, 0, $false)
    $candidate.Worksheets.Item(1).Rows.Item([int]$data.insertion_row).Insert(-4121, 0)
    $excel.CalculateFullRebuild()
    $candidate.Save()
    $candidate.Close($true)
    $candidate = $null
    @{ status = 'ok'; excel_build = [string]$excel.Build } | ConvertTo-Json -Compress
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
finally {
    if ($control) { $control.Close($false) }
    if ($candidate) { $candidate.Close($false) }
    if ($excel) { $excel.Quit() }
}
