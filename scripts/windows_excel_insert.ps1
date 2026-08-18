[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$Request)

$ErrorActionPreference = 'Stop'
$data = Get-Content -Raw -LiteralPath $Request | ConvertFrom-Json
$excel = $null
$control = $null
$candidate = $null
try {
    Add-Type @'
using System; using System.Runtime.InteropServices;
public static class NativeWindow { [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid); }
'@
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.EnableEvents = $false
    $excel.AskToUpdateLinks = $false
    # Lease precedes Workbooks.Open. The Python parent validates this exact
    # nonce/PID/HWND record and creates the ACK; no workbook is open yet.
    $hwnd = [IntPtr]$excel.Hwnd; [uint32]$excelPid = 0; [NativeWindow]::GetWindowThreadProcessId($hwnd, [ref]$excelPid) | Out-Null
    $excelProcess = Get-Process -Id $excelPid -ErrorAction Stop
    if ($excelProcess.ProcessName -ne 'EXCEL') { throw 'excel_lease_image_invalid' }
    $lease = @{ operation_id=$data.operation_id; owner_nonce=$data.owner_nonce; pair_nonce=$data.pair_nonce; excel_adapter='com'; adapter_pid=$PID; adapter_started_at=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o'); excel_pid=[int]$excelPid; excel_hwnd=[int64]$excel.Hwnd; excel_process_started_at=$excelProcess.StartTime.ToUniversalTime().ToString('o'); excel_image='EXCEL.EXE'; excel_build=[string]$excel.Build }
    $temporary = "$($data.lease_file).tmp.$PID"
    [System.IO.File]::WriteAllText($temporary, ($lease | ConvertTo-Json -Compress), (New-Object System.Text.UTF8Encoding($false)))
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
    $sheet.Rows.Item([int]$data.insertion_row).Insert(-4121, 0)
    foreach ($property in $data.fields.psobject.Properties) { $sheet.Cells.Item([int]$data.insertion_row, [int]$property.Name).Value2 = $property.Value }
    foreach ($property in $data.template_formula_r1c1.psobject.Properties) { $sheet.Cells.Item([int]$data.insertion_row, [int]$property.Name).FormulaR1C1 = $property.Value }
    # Rebase only visible numeric ordinals in A; semantic identity lives in RNS.
    $ordinal = 1
    for ($row = [int]$data.insertion_row; $row -le $sheet.UsedRange.Rows.Count; $row++) { if ($sheet.Cells.Item($row, 6).Value2) { $sheet.Cells.Item($row, 1).Value2 = $ordinal; $ordinal++ } }
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
