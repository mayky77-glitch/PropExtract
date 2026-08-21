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

Add-Type -ReferencedAssemblies 'System.Runtime.Serialization.dll' -TypeDefinition @'
using System;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

[DataContract]
public sealed class NativeCancelCommand {
    [DataMember(Name = "command")]
    public string Command { get; set; }
}

public sealed class NativeCancelListener : IDisposable {
    private readonly ManualResetEvent permission = new ManualResetEvent(false);
    private Task<string> pending;
    private volatile bool cancelled;
    private volatile bool failed;
    private volatile bool opened;

    public NativeCancelListener() { }

    public bool IsCancellationRequested { get { return cancelled; } }
    public bool Failed { get { return failed; } }
    public void Start() { pending = Console.In.ReadLineAsync(); }
    public bool WaitForOpen(int milliseconds) {
        int deadline = Environment.TickCount + milliseconds;
        do {
            Poll();
            if (opened || cancelled || failed) break;
            Thread.Sleep(10);
        } while (unchecked(Environment.TickCount - deadline) < 0);
        return opened && !cancelled && !failed;
    }
    public void Dispose() { }

    public void Poll() {
        try {
            if (pending == null || !pending.IsCompleted) return;
            string line = pending.Result;
            if (line == null) { failed = true; permission.Set(); return; }
            var serializer = new DataContractJsonSerializer(typeof(NativeCancelCommand));
            NativeCancelCommand message;
            using (var bytes = new System.IO.MemoryStream(Encoding.UTF8.GetBytes(line))) {
                message = serializer.ReadObject(bytes) as NativeCancelCommand;
            }
            if (message != null && String.Equals(message.Command, "open", StringComparison.Ordinal)) {
                opened = true;
                permission.Set();
            } else if (message != null && String.Equals(message.Command, "cancel", StringComparison.Ordinal)) {
                cancelled = true;
                permission.Set();
            }
            pending = Console.In.ReadLineAsync();
        } catch { failed = true; }
    }
}
'@

function Test-NativeCancel($Listener) {
    # ReadLineAsync is started once per line; checkpoints only poll completed
    # state and therefore never block on an open parent stdin pipe.
    $Listener.Poll()
    if ($Listener.Failed) { throw 'excel_cancel_listener_failed' }
    if ($Listener.IsCancellationRequested) { throw 'excel_operation_cancelled' }
}

$excel = $null
$control = $null
$candidate = $null
$cancelListener = $null
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
    $cancelListener = New-Object NativeCancelListener
    $cancelListener.Start()
    if (-not $cancelListener.WaitForOpen(20000)) {
        Test-NativeCancel $cancelListener
        throw 'excel_open_permission_missing'
    }

    $control = $excel.Workbooks.Open($data.control, 0, $false)
    Test-NativeCancel $cancelListener
    $excel.CalculateFullRebuild()
    Test-NativeCancel $cancelListener
    $control.Save()
    Test-NativeCancel $cancelListener
    $control.Close($true)
    $control = $null
    $candidate = $excel.Workbooks.Open($data.candidate, 0, $false)
    Test-NativeCancel $cancelListener
    $sheet = $candidate.Worksheets.Item([string]$data.sheet)
    if ($data.mutation_mode -ceq 'middle_insert') {
        $sheet.Rows.Item([int]$data.insertion_row).Insert(-4121, 0)
    }
    foreach ($property in $data.fields.psobject.Properties) { $sheet.Cells.Item([int]$data.insertion_row, [int]$property.Name).Value2 = $property.Value }
    if ($data.hyperlink) { $sheet.Hyperlinks.Add($sheet.Cells.Item([int]$data.insertion_row, 23), $data.hyperlink) | Out-Null }
    Test-NativeCancel $cancelListener
    $excel.CalculateFullRebuild()
    Test-NativeCancel $cancelListener
    $candidate.Save()
    Test-NativeCancel $cancelListener
    $candidate.Close($true)
    $candidate = $null
    $success = $true
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
finally {
    if ($cancelListener) { $cancelListener.Dispose() }
    if ($control) { $control.Close($false); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($control) }
    if ($candidate) { $candidate.Close($false); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($candidate) }
    if ($excel) { $excel.Quit(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel) }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
if ($success) { @{ status = 'ok' } | ConvertTo-Json -Compress }
