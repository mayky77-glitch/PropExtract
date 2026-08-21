[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$Request)

$ErrorActionPreference = 'Stop'
$data = Get-Content -Raw -LiteralPath $Request | ConvertFrom-Json
if ($data.mutation_mode -notin @('middle_insert', 'blank_fill')) {
    [Console]::Error.WriteLine('native_mutation_mode_invalid')
    exit 1
}
$excel = $null
$control = $null
$candidate = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.EnableEvents = $false
    $excel.AskToUpdateLinks = $false
    # Lease precedes Workbooks.Open. The Python parent validates this exact
    # nonce/PID/HWND record and creates the ACK; no workbook is open yet.
    $lease = @{ operation_id=$data.operation_id; owner_nonce=$data.owner_nonce; pair_nonce=$data.pair_nonce; excel_adapter='com'; excel_pid=$PID; excel_hwnd=[int64]$excel.Hwnd; excel_process_started_at=(Get-Date).ToUniversalTime().ToString('o'); excel_build=[string]$excel.Build }
    $temporary = "$($data.lease_file).tmp.$PID"
    $lease | ConvertTo-Json -Compress | Set-Content -NoNewline -Encoding utf8 -LiteralPath $temporary
    Move-Item -Force -LiteralPath $temporary -Destination $data.lease_file
    $deadline = (Get-Date).AddSeconds(20)
    do { Start-Sleep -Milliseconds 50 } until ((Test-Path -LiteralPath $data.ack_file) -or (Get-Date) -gt $deadline)
    if (-not (Test-Path -LiteralPath $data.ack_file)) { throw 'excel_lease_ack_missing' }
    $ack = Get-Content -Raw -LiteralPath $data.ack_file | ConvertFrom-Json
    if ($ack.operation_id -ne $data.operation_id -or $ack.owner_nonce -ne $data.owner_nonce -or $ack.pair_nonce -ne $data.pair_nonce) { throw 'excel_lease_ack_mismatch' }
    $control = $excel.Workbooks.Open($data.control, 0, $false)
    $excel.CalculateFullRebuild()
    $control.Save()
    $control.Close($true)
    $control = $null
    $candidate = $excel.Workbooks.Open($data.candidate, 0, $false)
    $sheet = $candidate.Worksheets.Item([string]$data.sheet)
    if ($data.mutation_mode -eq 'middle_insert') {
        $sheet.Rows.Item([int]$data.insertion_row).Insert(-4121, 0)
    }
    foreach ($property in $data.fields.psobject.Properties) { $sheet.Cells.Item([int]$data.insertion_row, [int]$property.Name).Value2 = $property.Value }
    if ($data.hyperlink) { $sheet.Hyperlinks.Add($sheet.Cells.Item([int]$data.insertion_row, 23), $data.hyperlink) | Out-Null }
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
