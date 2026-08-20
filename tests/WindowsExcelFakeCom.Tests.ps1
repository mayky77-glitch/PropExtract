$ErrorActionPreference = 'Stop'

if ($env:WINDOWS_EXCEL_FAKE_COM_PESTER_DISCOVERY -ne '1') {
    Import-Module Pester -ErrorAction Stop
    $env:WINDOWS_EXCEL_FAKE_COM_PESTER_DISCOVERY = '1'
    try { $result = Invoke-Pester -Path $PSCommandPath -PassThru -Output Detailed }
    finally { Remove-Item Env:WINDOWS_EXCEL_FAKE_COM_PESTER_DISCOVERY -ErrorAction SilentlyContinue }
    if ($result.FailedCount -gt 0) { exit 1 }
    exit 0
}

function New-ExpectedFakeComCall {
    param([int]$Sequence, [string]$Event, [string]$Stage = '', [string]$Kind = '', [int]$ProxyId = 0, [hashtable]$Arguments = @{})
    [pscustomobject]@{ sequence = $Sequence; event = $Event; stage = $Stage; kind = $Kind; proxy_id = $ProxyId; arguments = $Arguments }
}

function Get-ExpectedFakeComTrace {
    param([Parameter(Mandatory)][ValidateSet(6, 10, 104)][int]$InsertionRow)
    $address = "https://example.invalid/$InsertionRow"
    @(
        (New-ExpectedFakeComCall 1 'proxy.acquire' '' 'Application' 1),
        (New-ExpectedFakeComCall 2 'proxy.acquire.property' '' 'Application' 1 @{ property = 'Workbooks' }),
        (New-ExpectedFakeComCall 3 'proxy.acquire' '' 'Workbooks' 2),
        (New-ExpectedFakeComCall 4 'workbooks.open' 'open' 'Workbooks' 2 @{ path = 'control.xlsx'; update_links = 0; read_only = $false }),
        (New-ExpectedFakeComCall 5 'proxy.acquire' '' 'Workbook' 3),
        (New-ExpectedFakeComCall 6 'application.calculate' 'calc' 'Application' 1),
        (New-ExpectedFakeComCall 7 'workbook.save' 'save' 'Workbook' 3),
        (New-ExpectedFakeComCall 8 'workbook.close' 'cleanup' 'Workbook' 3 @{ save_changes = $true }),
        (New-ExpectedFakeComCall 9 'workbooks.open' 'open' 'Workbooks' 2 @{ path = 'candidate.xlsx'; update_links = 0; read_only = $false }),
        (New-ExpectedFakeComCall 10 'proxy.acquire' '' 'Workbook' 4),
        (New-ExpectedFakeComCall 11 'proxy.acquire.property' '' 'Workbook' 4 @{ property = 'Worksheets' }),
        (New-ExpectedFakeComCall 12 'proxy.acquire' '' 'Worksheets' 5),
        (New-ExpectedFakeComCall 13 'worksheets.item' '' 'Worksheets' 5 @{ name = 'Объекты' }),
        (New-ExpectedFakeComCall 14 'proxy.acquire' '' 'Sheet' 6),
        (New-ExpectedFakeComCall 15 'proxy.acquire.property' '' 'Sheet' 6 @{ property = 'Rows' }),
        (New-ExpectedFakeComCall 16 'proxy.acquire' '' 'Rows' 7),
        (New-ExpectedFakeComCall 17 'rows.item' '' 'Rows' 7 @{ row = $InsertionRow }),
        (New-ExpectedFakeComCall 18 'proxy.acquire' '' 'Row' 8),
        (New-ExpectedFakeComCall 19 'row.insert' 'insert' 'Row' 8 @{ row = $InsertionRow; shift = -4121; copy_origin = 0 }),
        (New-ExpectedFakeComCall 20 'proxy.acquire.property' '' 'Sheet' 6 @{ property = 'Cells' }),
        (New-ExpectedFakeComCall 21 'proxy.acquire' '' 'Cells' 9),
        (New-ExpectedFakeComCall 22 'cells.item' '' 'Cells' 9 @{ row = $InsertionRow; column = 1 }),
        (New-ExpectedFakeComCall 23 'proxy.acquire' '' 'Cell' 10),
        (New-ExpectedFakeComCall 24 'cell.mutate.value2' 'mutation' 'Cell' 10 @{ row = $InsertionRow; column = 1; value = "row-$InsertionRow-col-1" }),
        (New-ExpectedFakeComCall 25 'cells.item' '' 'Cells' 9 @{ row = $InsertionRow; column = 2 }),
        (New-ExpectedFakeComCall 26 'proxy.acquire' '' 'Cell' 11),
        (New-ExpectedFakeComCall 27 'cell.mutate.value2' 'mutation' 'Cell' 11 @{ row = $InsertionRow; column = 2; value = "row-$InsertionRow-col-2" }),
        (New-ExpectedFakeComCall 28 'cells.item' '' 'Cells' 9 @{ row = $InsertionRow; column = 23 }),
        (New-ExpectedFakeComCall 29 'proxy.acquire' '' 'Cell' 12),
        (New-ExpectedFakeComCall 30 'cell.mutate.value2' 'mutation' 'Cell' 12 @{ row = $InsertionRow; column = 23; value = "row-$InsertionRow-col-23" }),
        (New-ExpectedFakeComCall 31 'proxy.acquire.property' '' 'Sheet' 6 @{ property = 'Hyperlinks' }),
        (New-ExpectedFakeComCall 32 'proxy.acquire' '' 'Hyperlinks' 13),
        (New-ExpectedFakeComCall 33 'cells.item' '' 'Cells' 9 @{ row = $InsertionRow; column = 23 }),
        (New-ExpectedFakeComCall 34 'proxy.acquire' '' 'Cell' 14),
        (New-ExpectedFakeComCall 35 'hyperlinks.add' 'mutation' 'Hyperlinks' 13 @{ anchor_id = 14; row = $InsertionRow; column = 23; address = $address }),
        (New-ExpectedFakeComCall 36 'proxy.acquire' '' 'Hyperlink' 15),
        (New-ExpectedFakeComCall 37 'application.calculate' 'calc' 'Application' 1),
        (New-ExpectedFakeComCall 38 'workbook.save' 'save' 'Workbook' 4),
        (New-ExpectedFakeComCall 39 'workbook.close' 'cleanup' 'Workbook' 4 @{ save_changes = $true }),
        (New-ExpectedFakeComCall 40 'application.quit' 'cleanup' 'Application' 1),
        (New-ExpectedFakeComCall 41 'proxy.release' 'release' 'Hyperlink' 15),
        (New-ExpectedFakeComCall 42 'proxy.release' 'release' 'Cell' 14),
        (New-ExpectedFakeComCall 43 'proxy.release' 'release' 'Hyperlinks' 13),
        (New-ExpectedFakeComCall 44 'proxy.release' 'release' 'Cell' 12),
        (New-ExpectedFakeComCall 45 'proxy.release' 'release' 'Cell' 11),
        (New-ExpectedFakeComCall 46 'proxy.release' 'release' 'Cell' 10),
        (New-ExpectedFakeComCall 47 'proxy.release' 'release' 'Cells' 9),
        (New-ExpectedFakeComCall 48 'proxy.release' 'release' 'Row' 8),
        (New-ExpectedFakeComCall 49 'proxy.release' 'release' 'Rows' 7),
        (New-ExpectedFakeComCall 50 'proxy.release' 'release' 'Sheet' 6),
        (New-ExpectedFakeComCall 51 'proxy.release' 'release' 'Worksheets' 5),
        (New-ExpectedFakeComCall 52 'proxy.release' 'release' 'Workbook' 4),
        (New-ExpectedFakeComCall 53 'proxy.release' 'release' 'Workbook' 3),
        (New-ExpectedFakeComCall 54 'proxy.release' 'release' 'Workbooks' 2),
        (New-ExpectedFakeComCall 55 'proxy.release' 'release' 'Application' 1)
    )
}

function Assert-ExactFakeComTrace {
    param([Parameter(Mandatory)]$Actual, [Parameter(Mandatory)]$Expected)
    @($Actual).Count | Should -Be @($Expected).Count
    for ($index = 0; $index -lt @($Expected).Count; $index++) {
        $actualCall = @($Actual)[$index]; $expectedCall = @($Expected)[$index]
        $actualCall.sequence | Should -Be $expectedCall.sequence
        $actualCall.event | Should -Be $expectedCall.event
        $actualCall.stage | Should -Be $expectedCall.stage
        $actualCall.kind | Should -Be $expectedCall.kind
        $actualCall.proxy_id | Should -Be $expectedCall.proxy_id
        @($actualCall.arguments.PSObject.Properties).Count | Should -Be $expectedCall.arguments.Count
        foreach ($name in $expectedCall.arguments.Keys) {
            $actualCall.arguments.PSObject.Properties.Name | Should -Contain $name
            $actualCall.arguments.$name | Should -Be $expectedCall.arguments[$name]
        }
    }
}

function Assert-ExactFailureEnvelope {
    param([Parameter(Mandatory)]$Actual, [string]$Stage, [int]$Occurrence, [string]$Message, [int]$HResult, [int]$WinError)
    $Actual.stage | Should -Be $Stage; $Actual.occurrence | Should -Be $Occurrence
    $Actual.message | Should -Be $Message; $Actual.hresult | Should -Be $HResult; $Actual.winerror | Should -Be $WinError
}

Describe 'Windows Excel fake COM fault corpus' {
    BeforeAll { Import-Module (Join-Path $PSScriptRoot 'support/WindowsExcelFakeCom.psm1') -Force }

    It 'matches the exact ordered fake-COM trace for row <row>' -ForEach @(6, 10, 104) {
        param($row)
        $scenario = Invoke-WindowsExcelFakeComScenario -InsertionRow $row
        Assert-ExactFakeComTrace -Actual $scenario.Trace -Expected (Get-ExpectedFakeComTrace -InsertionRow $row)
        $scenario.Error | Should -BeNullOrEmpty; $scenario.CleanupErrors.Count | Should -Be 0
        $scenario.Final.classification | Should -Be 'success'; $scenario.Final.success | Should -BeTrue
        $scenario.Final.cleanup_failure_count | Should -Be 0
        (@($scenario.Proxies | Where-Object { $_.Kind -eq 'Hyperlink' }) | Select-Object -ExpandProperty Id) | Should -Be 15
        (Test-WindowsExcelFakeComTrace -Scenario $scenario -InsertionRow $row).is_success | Should -BeTrue
    }

    It 'keeps open and insert failures as explicit primary failures' -ForEach @('open', 'insert') {
        param($stage)
        $scenario = Invoke-WindowsExcelFakeComScenario -InsertionRow 10 -Faults @{ $stage = @{ message = "forced-$stage"; hresult = -41; winerror = 122 } }
        Assert-ExactFailureEnvelope -Actual $scenario.Error -Stage $stage -Occurrence 1 -Message "forced-$stage" -HResult -41 -WinError 122
        $scenario.CleanupErrors.Count | Should -Be 0; $scenario.Final.classification | Should -Be 'primary_failure'; $scenario.Final.success | Should -BeFalse
    }

    It 'targets the candidate post-insert <stage> occurrence and preserves the primary envelope' -ForEach @('calc', 'save') {
        param($stage)
        $scenario = Invoke-WindowsExcelFakeComScenario -InsertionRow 10 -Faults @{ $stage = @{ occurrence = 2; message = "candidate-$stage"; hresult = -42; winerror = 123 } }
        Assert-ExactFailureEnvelope -Actual $scenario.Error -Stage $stage -Occurrence 2 -Message "candidate-$stage" -HResult -42 -WinError 123
        $scenario.CleanupErrors.Count | Should -Be 0; $scenario.Final.classification | Should -Be 'primary_failure'; $scenario.Final.success | Should -BeFalse
        @($scenario.Trace | Where-Object { $_.event -eq 'row.insert' -and $_.arguments.row -eq 10 }).Count | Should -Be 1
        @($scenario.Trace | Where-Object { $_.event -eq 'hyperlinks.add' -and $_.arguments.anchor_id -eq 14 -and $_.arguments.address -eq 'https://example.invalid/10' }).Count | Should -Be 1
        @($scenario.Trace | Where-Object event -eq 'application.calculate').Count | Should -Be 2
        @($scenario.Trace | Where-Object event -eq 'workbook.save').Count | Should -Be $(if ($stage -eq 'save') { 2 } else { 1 })
        (@($scenario.Trace | Where-Object event -eq 'proxy.release' | Select-Object -ExpandProperty proxy_id) -join ',') | Should -Be '15,14,13,12,11,10,9,8,7,6,5,4,3,2,1'
    }

    It 'orders an occurrence-targeted primary cleanup fault before its release cleanup envelope' {
        $scenario = Invoke-WindowsExcelFakeComScenario -InsertionRow 10 -Faults @{
            cleanup = @{ occurrence = 2; message = 'candidate-close'; hresult = -701; winerror = 1701 }
            release = @{ occurrences = @(1, 2); message = 'release-cleanup'; hresult = -702; winerror = 1702 }
        }
        Assert-ExactFailureEnvelope -Actual $scenario.Error -Stage 'cleanup' -Occurrence 2 -Message 'candidate-close' -HResult -701 -WinError 1701
        $scenario.CleanupErrors.Count | Should -Be 2
        Assert-ExactFailureEnvelope -Actual $scenario.CleanupErrors[0] -Stage 'release' -Occurrence 1 -Message 'release-cleanup' -HResult -702 -WinError 1702
        Assert-ExactFailureEnvelope -Actual $scenario.CleanupErrors[1] -Stage 'release' -Occurrence 2 -Message 'release-cleanup' -HResult -702 -WinError 1702
        $scenario.Final.classification | Should -Be 'primary_and_cleanup_failure'; $scenario.Final.success | Should -BeFalse; $scenario.Final.cleanup_failure_count | Should -Be 2
        @($scenario.Trace | Where-Object event -eq 'application.quit').Count | Should -Be 0
        (@($scenario.Trace | Where-Object event -eq 'proxy.release' | Select-Object -ExpandProperty proxy_id) -join ',') | Should -Be '15,14,13,12,11,10,9,8,7,6,5,4,3,2,1'
    }

    It 'classifies a targeted release-only fault as a failure, never a success' {
        $scenario = Invoke-WindowsExcelFakeComScenario -InsertionRow 10 -Faults @{ release = @{ occurrence = 2; message = 'anchor-release'; hresult = -703; winerror = 1703 } }
        $scenario.Error | Should -BeNullOrEmpty; $scenario.CleanupErrors.Count | Should -Be 1
        Assert-ExactFailureEnvelope -Actual $scenario.CleanupErrors[0] -Stage 'release' -Occurrence 2 -Message 'anchor-release' -HResult -703 -WinError 1703
        $scenario.Final.classification | Should -Be 'cleanup_failure'; $scenario.Final.success | Should -BeFalse; $scenario.Final.cleanup_failure_count | Should -Be 1
        (@($scenario.Trace | Where-Object event -eq 'proxy.release' | Select-Object -ExpandProperty proxy_id) -join ',') | Should -Be '15,14,13,12,11,10,9,8,7,6,5,4,3,2,1'
    }
}
