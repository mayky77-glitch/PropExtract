[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$Request)

$ErrorActionPreference = 'Stop'
$data = Get-Content -Raw -LiteralPath $Request | ConvertFrom-Json
if ($data.mutation_mode -cnotin @('middle_insert', 'blank_fill')) {
    [Console]::Error.WriteLine('native_mutation_mode_invalid')
    exit 1
}

function Write-DurableUtf8NoBom([string]$Path, [string]$Content) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $stream = New-Object System.IO.FileStream($Path, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $bytes = $encoding.GetBytes($Content)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally { $stream.Dispose() }
}

$excel = $null
$control = $null
$candidate = $null
$success = $false
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.EnableEvents = $false
    $excel.AskToUpdateLinks = $false

    # Complete, exact-key, BOM-free and durable lease before any Workbooks.Open.
    $adapter = Get-Process -Id $PID -ErrorAction Stop
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class LeaseWindow { [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid); }' -ErrorAction Stop
    [uint32]$excelPid = 0
    [LeaseWindow]::GetWindowThreadProcessId([IntPtr]$excel.Hwnd, [ref]$excelPid) | Out-Null
    if ($excelPid -le 0) { throw 'excel_lease_hwnd_pid_missing' }
    $excelProcess = Get-Process -Id $excelPid -ErrorAction Stop
    $lease = [ordered]@{
        operation_id = [string]$data.operation_id
        owner_id = [string]$data.owner_nonce
        pair_nonce = [string]$data.pair_nonce
        adapter_type = 'com'
        adapter_image = ([string]$adapter.ProcessName + '.exe')
        adapter_pid = [int]$PID
        adapter_started_at = $adapter.StartTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        excel_image = 'EXCEL.EXE'
        excel_pid = [int]$excelPid
        excel_hwnd = [int64]$excel.Hwnd
        excel_process_started_at = $excelProcess.StartTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        excel_build = [string]$excel.Build
    }
    $temporary = "$($data.lease_file).tmp.$PID"
    Write-DurableUtf8NoBom $temporary ($lease | ConvertTo-Json -Compress)
    [System.IO.File]::Move($temporary, [string]$data.lease_file)

    # The only permission is one parent stdin message. ACK is audit-only and
    # intentionally never read or polled by this helper.
    $permission = [Console]::In.ReadLine()
    if ([string]::IsNullOrWhiteSpace($permission)) { throw 'excel_open_permission_missing' }
    $command = $permission | ConvertFrom-Json
    if ($command.command -cne 'open') { throw 'excel_open_not_granted' }

    $control = $excel.Workbooks.Open($data.control, 0, $false)
    $excel.CalculateFullRebuild()
    $control.Save()
    $control.Close($true)
    $control = $null
    $candidate = $excel.Workbooks.Open($data.candidate, 0, $false)
    $sheet = $candidate.Worksheets.Item([string]$data.sheet)
    if ($data.mutation_mode -ceq 'middle_insert') {
        $sheet.Rows.Item([int]$data.insertion_row).Insert(-4121, 0)
    }
    foreach ($property in $data.fields.psobject.Properties) { $sheet.Cells.Item([int]$data.insertion_row, [int]$property.Name).Value2 = $property.Value }
    if ($data.hyperlink) { $sheet.Hyperlinks.Add($sheet.Cells.Item([int]$data.insertion_row, 23), $data.hyperlink) | Out-Null }
    $excel.CalculateFullRebuild()
    $candidate.Save()
    $candidate.Close($true)
    $candidate = $null
    $success = $true
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
finally {
    if ($control) { $control.Close($false); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($control) }
    if ($candidate) { $candidate.Close($false); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($candidate) }
    if ($excel) { $excel.Quit(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
if ($success) { @{ status = 'ok' } | ConvertTo-Json -Compress }
