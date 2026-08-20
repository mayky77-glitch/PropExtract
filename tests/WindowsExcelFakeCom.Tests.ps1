$ErrorActionPreference = 'Stop'

if ($env:WINDOWS_EXCEL_FAKE_COM_PESTER_DISCOVERY -ne '1') {
    Import-Module Pester -ErrorAction Stop
    $env:WINDOWS_EXCEL_FAKE_COM_PESTER_DISCOVERY = '1'
    try { $result = Invoke-Pester -Path $PSCommandPath -PassThru -Output Detailed }
    finally { Remove-Item Env:WINDOWS_EXCEL_FAKE_COM_PESTER_DISCOVERY -ErrorAction SilentlyContinue }
    if ($result.FailedCount -gt 0) { exit 1 }
    exit 0
}

Describe 'Windows Excel fake COM fault corpus' {
    BeforeAll {
        Import-Module (Join-Path $PSScriptRoot 'support/WindowsExcelFakeCom.psm1') -Force
    }

    It 'self-validates expected calls and envelopes for rows 6, 10, and 104' -ForEach @(6, 10, 104) {
        param($row)
        $scenario = Invoke-WindowsExcelFakeComScenario -InsertionRow $row
        $validation = Test-WindowsExcelFakeComTrace -Scenario $scenario -InsertionRow $row
        $scenario.Error | Should -BeNullOrEmpty
        $validation.has_insert | Should -BeTrue
        $validation.has_mutations | Should -BeTrue
        $validation.call_envelope.hyperlink.Count | Should -Be 1
        $validation.has_hyperlink_result | Should -BeTrue
        $validation.reverse_release | Should -BeTrue
        @($scenario.Trace | Where-Object event -eq 'application.calculate').Count | Should -Be 2
        @($scenario.Trace | Where-Object event -eq 'workbook.save').Count | Should -Be 2
    }

    It 'preserves the stage and native envelope for injected faults' -ForEach @('open', 'insert', 'calc', 'save', 'cleanup', 'release') {
        param($stage)
        $scenario = Invoke-WindowsExcelFakeComScenario -InsertionRow 10 -Faults @{ $stage = @{ message = "forced-$stage"; hresult = -42; winerror = 123 } }
        if ($stage -eq 'release') {
            $scenario.CleanupErrors.Count | Should -BeGreaterThan 0
            $scenario.CleanupErrors[0].stage | Should -Be 'release'
        } else {
            $scenario.Error.stage | Should -Be $stage
            $scenario.Error.hresult | Should -Be -42
            $scenario.Error.winerror | Should -Be 123
        }
    }

    It 'makes every chained return, including Hyperlinks.Add, observable' {
        $fake = New-WindowsExcelFakeCom
        $app = $fake.Application; $books = $app.Workbooks; $book = $books.Open('candidate.xlsx', 0, $false)
        $sheet = $book.Worksheets.Item('Объекты'); $cell = $sheet.Cells.Item(104, 23)
        $link = $sheet.Hyperlinks.Add($cell, 'https://example.invalid/104')
        $link.Kind | Should -Be 'Hyperlink'
        @($fake.State.Calls | Where-Object { $_.event -eq 'proxy.acquire' -and $_.kind -eq 'Hyperlink' }).Count | Should -Be 1
    }
}
