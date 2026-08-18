Set-StrictMode -Version Latest

function ConvertTo-ContractJson {
    param([Parameter(Mandatory = $true)]$Value)
    return ($Value | ConvertTo-Json -Compress -Depth 12)
}

function Write-AtomicContractJson {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)]$Value)
    $directory = Split-Path -Parent $Path
    if ($directory) { [System.IO.Directory]::CreateDirectory($directory) | Out-Null }
    $temporary = "$Path.tmp.$PID.$([guid]::NewGuid().ToString('N'))"
    $encoding = [System.Text.UTF8Encoding]::new($false)
    $stream = $null
    try {
        $stream = [System.IO.FileStream]::new($temporary, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        $writer = [System.IO.StreamWriter]::new($stream, $encoding, 4096, $true)
        try { $writer.Write((ConvertTo-ContractJson $Value)); $writer.Flush(); $stream.Flush($true) }
        finally { $writer.Dispose() }
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    }
    finally {
        if ($stream) { $stream.Dispose() }
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

function Write-ContractProgress {
    param($Data, [Parameter(Mandatory = $true)][string]$Stage, [hashtable]$Extra = @{}) 
    if ($Data.PSObject.Properties.Name -contains 'progress_file' -and $Data.progress_file) {
        $event = @{ contract_version = 'powershell-row-contract-v3'; kind = 'progress'; stage = $Stage; pid = $PID; hresult = $null; winerror = $null; primary = $null; cleanup = $null }
        foreach ($entry in $Extra.GetEnumerator()) { $event[$entry.Key] = $entry.Value }
        Write-AtomicContractJson -Path ([string]$Data.progress_file) -Value $event
    }
}

function Get-ExceptionEnvelope {
    param([Parameter(Mandatory = $true)]$ErrorRecord, [string]$Stage, $CleanupError = $null)
    $exception = $ErrorRecord.Exception
    $primaryWinError = if ($exception -is [ComponentModel.Win32Exception]) { [int]$exception.NativeErrorCode } else { $null }
    $primary = @{ stage = $Stage; code = [string]$exception.GetType().Name; message = [string]$exception.Message; hresult = [int64]$exception.HResult; winerror = $primaryWinError }
    $cleanup = $null
    if ($CleanupError) {
        $cleanupException = $CleanupError.Exception
        $cleanupWinError = if ($cleanupException -is [ComponentModel.Win32Exception]) { [int]$cleanupException.NativeErrorCode } else { $null }
        $cleanup = @{ stage = 'cleanup'; code = [string]$cleanupException.GetType().Name; message = [string]$cleanupException.Message; hresult = [int64]$cleanupException.HResult; winerror = $cleanupWinError }
    }
    return @{ contract_version = 'powershell-row-contract-v3'; kind = 'error'; stage = $Stage; hresult = $primary.hresult; winerror = $primary.winerror; primary = $primary; cleanup = $cleanup }
}

function Release-ComProxy {
    param($Value)
    if ($null -ne $Value -and [System.Runtime.InteropServices.Marshal]::IsComObject($Value)) {
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Value)
    }
}

function Get-HwndProcessId {
    param([Parameter(Mandatory = $true)][Int64]$Hwnd)
    if (-not ('NativeWindow' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NativeWindow {
  [DllImport("user32.dll", SetLastError=true)] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
'@
    }
    [uint32]$processId = 0
    if ([NativeWindow]::GetWindowThreadProcessId([IntPtr]$Hwnd, [ref]$processId) -eq 0 -or $processId -eq 0) {
        throw [ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error(), 'excel_hwnd_pid_missing')
    }
    return [int]$processId
}

function Get-ProcessIdentity {
    param([Parameter(Mandatory = $true)][int]$ProcessId)
    $process = Get-Process -Id $ProcessId -ErrorAction Stop
    try {
        return @{ pid = $ProcessId; image = [string]$process.Path; started_at = $process.StartTime.ToUniversalTime().ToString('o') }
    }
    finally { $process.Dispose() }
}

function Test-RowContractRequest {
    param([Parameter(Mandatory = $true)]$Data)
    $required = @('operation_id','owner_nonce','pair_nonce','control','candidate','sheet','insertion_row','group_start_row','group_end_row','expected_next_header_row','expected_next_header_value','source_row','template_row','fields','formula_y_r1c1','formula_z_r1c1','hyperlink','ordinal_map')
    foreach ($name in $required) {
        if (-not ($Data.PSObject.Properties.Name -contains $name) -or $null -eq $Data.$name -or "$($Data.$name)" -eq '') { throw "row_contract_missing_$name" }
    }
    foreach ($name in @('insertion_row','group_start_row','group_end_row','expected_next_header_row','source_row','template_row')) {
        if ([int]$Data.$name -lt 1) { throw "row_contract_invalid_$name" }
    }
    if ([int]$Data.group_start_row -gt [int]$Data.insertion_row -or [int]$Data.insertion_row -ge [int]$Data.expected_next_header_row -or [int]$Data.expected_next_header_row -gt [int]$Data.group_end_row + 1) { throw 'row_contract_group_bounds_invalid' }
    if ([int]$Data.source_row -lt [int]$Data.group_start_row -or [int]$Data.source_row -gt [int]$Data.group_end_row -or [int]$Data.template_row -lt [int]$Data.group_start_row -or [int]$Data.template_row -gt [int]$Data.group_end_row) { throw 'row_contract_source_template_invalid' }
    foreach ($property in $Data.fields.PSObject.Properties) {
        $column = [int]$property.Name
        if ((($column -lt 1) -or ($column -gt 24)) -and $column -ne 27) { throw 'row_contract_field_not_allowed' }
    }
    foreach ($entry in @($Data.ordinal_map)) {
        if ($null -eq $entry.row -or $null -eq $entry.ordinal -or [int]$entry.row -lt [int]$Data.group_start_row -or [int]$entry.row -gt [int]$Data.group_end_row + 1) { throw 'row_contract_ordinal_map_invalid' }
    }
}

function Wait-ExactLeaseAck {
    param([Parameter(Mandatory = $true)]$Data, [int]$TimeoutSeconds = 20)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-Path -LiteralPath $Data.ack_file) {
            $ack = Get-Content -Raw -LiteralPath $Data.ack_file | ConvertFrom-Json
            if ($ack.operation_id -eq $Data.operation_id -and $ack.owner_nonce -eq $Data.owner_nonce -and $ack.pair_nonce -eq $Data.pair_nonce) { return }
            throw 'excel_lease_ack_mismatch'
        }
        Start-Sleep -Milliseconds 50
    } until ((Get-Date) -gt $deadline)
    throw 'excel_lease_ack_missing'
}

function Copy-RowPresentation {
    param($Sheet, [int]$SourceRow, [int]$TemplateRow, [int]$TargetRow)
    $Sheet.Rows.Item($TargetRow).RowHeight = $Sheet.Rows.Item($SourceRow).RowHeight
    $Sheet.Rows.Item($TemplateRow).Copy()
    $Sheet.Rows.Item($TargetRow).PasteSpecial(-4122) # formats only
    $Sheet.Rows.Item($TargetRow).PasteSpecial(6)     # validation only
    $Sheet.Application.CutCopyMode = $false
}

function Get-PostInsertRow {
    param([int]$OriginalRow, [int]$InsertionRow)
    return $OriginalRow + $(if ($OriginalRow -ge $InsertionRow) { 1 } else { 0 })
}

function Invoke-ExcelRowContract {
    param([Parameter(Mandatory = $true)]$Data, [scriptblock]$ExcelFactory = { New-Object -ComObject Excel.Application })
    Test-RowContractRequest $Data
    $excel = $control = $candidate = $sheet = $null
    $ownedExcel = $false
    $stage = 'launch'
    $primary = $cleanup = $null
    try {
        Write-ContractProgress $Data 'launch'
        $excel = & $ExcelFactory
        $ownedExcel = $true
        $excel.Visible = $false; $excel.DisplayAlerts = $false; $excel.EnableEvents = $false; $excel.AskToUpdateLinks = $false
        $adapter = Get-ProcessIdentity -ProcessId $PID
        $excelProcessId = Get-HwndProcessId -Hwnd ([int64]$excel.Hwnd)
        $excelIdentity = Get-ProcessIdentity -ProcessId $excelProcessId
        if ((Split-Path -Leaf $excelIdentity.image).ToUpperInvariant() -ne 'EXCEL.EXE') { throw 'excel_lease_image_invalid' }
        $lease = @{ operation_id = $Data.operation_id; owner_nonce = $Data.owner_nonce; pair_nonce = $Data.pair_nonce; excel_adapter = 'powershell-com'; adapter_pid = $adapter.pid; adapter_image = $adapter.image; adapter_process_started_at = $adapter.started_at; excel_pid = $excelIdentity.pid; excel_hwnd = [int64]$excel.Hwnd; excel_image = $excelIdentity.image; excel_process_started_at = $excelIdentity.started_at; excel_build = [string]$excel.Build }
        Write-AtomicContractJson -Path ([string]$Data.lease_file) -Value $lease
        Write-ContractProgress $Data 'lease_written'
        $stage = 'ack'; Wait-ExactLeaseAck $Data
        Write-ContractProgress $Data 'acknowledged'
        # This is intentionally the first Workbooks.Open after the exact ACK.
        $stage = 'open_control'; $control = $excel.Workbooks.Open([string]$Data.control, 0, $false)
        $stage = 'calc_control'; $excel.CalculateFullRebuild(); $control.Save(); $control.Close($true); Release-ComProxy $control; $control = $null
        $stage = 'open_candidate'; $candidate = $excel.Workbooks.Open([string]$Data.candidate, 0, $false)
        $sheet = $candidate.Worksheets.Item([string]$Data.sheet)
        if ([int]$sheet.Rows.Count -lt [int]$Data.expected_next_header_row) { throw 'row_contract_sheet_bounds_invalid' }
        if ([string]$sheet.Cells.Item([int]$Data.expected_next_header_row, 1).Value2 -ne [string]$Data.expected_next_header_value) { throw 'row_contract_next_header_mismatch' }
        $stage = 'insert'; $sheet.Rows.Item([int]$Data.insertion_row).Insert(-4121, 0)
        Copy-RowPresentation -Sheet $sheet -SourceRow (Get-PostInsertRow ([int]$Data.source_row) ([int]$Data.insertion_row)) -TemplateRow (Get-PostInsertRow ([int]$Data.template_row) ([int]$Data.insertion_row)) -TargetRow ([int]$Data.insertion_row)
        foreach ($property in $Data.fields.PSObject.Properties) { $sheet.Cells.Item([int]$Data.insertion_row, [int]$property.Name).Value2 = $property.Value }
        $sheet.Cells.Item([int]$Data.insertion_row, 25).FormulaR1C1 = [string]$Data.formula_y_r1c1
        $sheet.Cells.Item([int]$Data.insertion_row, 26).FormulaR1C1 = [string]$Data.formula_z_r1c1
        $target = $sheet.Cells.Item([int]$Data.insertion_row, 23)
        $sheet.Hyperlinks.Add($target, [string]$Data.hyperlink, '', '', [string]$Data.hyperlink) | Out-Null
        foreach ($entry in @($Data.ordinal_map)) { $sheet.Cells.Item([int]$entry.row, 1).Value2 = [int]$entry.ordinal }
        $stage = 'calc'; $excel.CalculateFullRebuild()
        $stage = 'save'; $candidate.Save()
        $result = @{ contract_version = 'powershell-row-contract-v3'; kind = 'result'; status = 'ok'; stage = 'complete'; excel_build = [string]$excel.Build; lease = $lease }
        if ($Data.PSObject.Properties.Name -contains 'result_file' -and $Data.result_file) { Write-AtomicContractJson -Path ([string]$Data.result_file) -Value $result }
        return $result
    }
    catch { $primary = $_; throw }
    finally {
        try { if ($sheet) { Release-ComProxy $sheet }; if ($control) { $control.Close($false); Release-ComProxy $control }; if ($candidate) { $candidate.Close($false); Release-ComProxy $candidate }; if ($excel -and $ownedExcel) { $excel.Quit() }; if ($excel) { Release-ComProxy $excel } }
        catch { $cleanup = $_ }
        if ($cleanup -and -not $primary) { throw $cleanup }
        if ($primary -and $cleanup) {
            $envelope = Get-ExceptionEnvelope $primary $stage $cleanup
            Write-ContractProgress $Data 'cleanup_failed' @{ primary = $envelope.primary; cleanup = $envelope.cleanup }
            if ($Data.PSObject.Properties.Name -contains 'error_file' -and $Data.error_file) { Write-AtomicContractJson -Path ([string]$Data.error_file) -Value $envelope }
        }
    }
}

Export-ModuleMember -Function ConvertTo-ContractJson,Write-AtomicContractJson,Get-ExceptionEnvelope,Test-RowContractRequest,Wait-ExactLeaseAck,Invoke-ExcelRowContract
