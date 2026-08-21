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

Add-Type -ReferencedAssemblies 'System.Web.Extensions.dll' -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

public sealed class NativeControlReader : IDisposable {
    private volatile bool opened;
    private volatile bool cancelled;
    private volatile bool failed;
    private Thread reader;

    public bool IsOpen { get { return opened; } }
    public bool IsCancellationRequested { get { return cancelled; } }
    public bool Failed { get { return failed; } }

    public void Start() {
        reader = new Thread(ReadLoop);
        reader.IsBackground = true;
        reader.Name = "excel-native-control-reader";
        reader.Start();
    }

    public bool WaitForOpen(int milliseconds) {
        int deadline = Environment.TickCount + milliseconds;
        do {
            if (opened || cancelled || failed) break;
            Thread.Sleep(10);
        } while (unchecked(Environment.TickCount - deadline) < 0);
        return opened && !cancelled && !failed;
    }

    private static bool ExactCommand(string line, out string command) {
        command = null;
        try {
            object raw = new JavaScriptSerializer().DeserializeObject(line);
            var message = raw as Dictionary<string, object>;
            if (message == null || message.Count != 1 || !message.ContainsKey("command") || !(message["command"] is string)) return false;
            command = (string)message["command"];
            return command == "open" || command == "cancel";
        } catch { return false; }
    }

    private void ReadLoop() {
        try {
            using (var input = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false), false, 1024, false)) {
                string line;
                while ((line = input.ReadLine()) != null) {
                    string command;
                    if (!ExactCommand(line, out command)) { failed = true; return; }
                    if (!opened) {
                        if (command == "cancel") { cancelled = true; return; }
                        opened = true;
                        continue;
                    }
                    if (command == "cancel") { cancelled = true; return; }
                    failed = true;
                    return;
                }
                if (!opened) failed = true;
            }
        } catch { failed = true; }
    }

    public void Dispose() { }
}
'@

function Test-NativeCancel($Reader) {
    if ($Reader.Failed) { throw 'excel_cancel_listener_failed' }
    if ($Reader.IsCancellationRequested) { throw 'excel_operation_cancelled' }
}

$excel = $null
$control = $null
$candidate = $null
$controlReader = $null
$success = $false
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.EnableEvents = $false
    $excel.AskToUpdateLinks = $false

    # Complete exact-key durable lease before every Workbooks.Open.
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

    # ACK is audit only. One reader owns stdin and only parent ``open`` permits COM work.
    $controlReader = New-Object NativeControlReader
    $controlReader.Start()
    if (-not $controlReader.WaitForOpen(20000)) {
        Test-NativeCancel $controlReader
        throw 'excel_open_permission_missing'
    }

    $control = $excel.Workbooks.Open($data.control, 0, $false)
    Test-NativeCancel $controlReader
    $excel.CalculateFullRebuild()
    Test-NativeCancel $controlReader
    $control.Save()
    Test-NativeCancel $controlReader
    $control.Close($true)
    $control = $null
    $candidate = $excel.Workbooks.Open($data.candidate, 0, $false)
    Test-NativeCancel $controlReader
    $sheet = $candidate.Worksheets.Item([string]$data.sheet)
    if ($data.mutation_mode -ceq 'middle_insert') {
        $sheet.Rows.Item([int]$data.insertion_row).Insert(-4121, 0)
    }
    foreach ($property in $data.fields.psobject.Properties) { $sheet.Cells.Item([int]$data.insertion_row, [int]$property.Name).Value2 = $property.Value }
    if ($data.hyperlink) { $sheet.Hyperlinks.Add($sheet.Cells.Item([int]$data.insertion_row, 23), $data.hyperlink) | Out-Null }
    Test-NativeCancel $controlReader
    $excel.CalculateFullRebuild()
    Test-NativeCancel $controlReader
    $candidate.Save()
    Test-NativeCancel $controlReader
    $candidate.Close($true)
    $candidate = $null
    Test-NativeCancel $controlReader
    $success = $true
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
finally {
    if ($controlReader) { $controlReader.Dispose() }
    if ($control) { $control.Close($false); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($control) }
    if ($candidate) { $candidate.Close($false); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($candidate) }
    if ($excel) { $excel.Quit(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
if ($success) { @{ status = 'ok' } | ConvertTo-Json -Compress }
