$ErrorActionPreference = 'Stop'
$module = Join-Path $PSScriptRoot '..' 'scripts' 'WindowsExcelRequestSchema.psm1'
Import-Module $module -Force

function New-ValidRequestJson([int]$NextHeader = 6) {
    $request = [ordered]@{
        operation_id='operation-1'; owner_nonce='owner-1'; pair_nonce='pair-1'
        control='C:\\staged\\control.xlsx'; candidate='C:\\staged\\candidate.xlsx'; sheet='Реестр РНС'
        workbook_identity='workbook-sha256'; sheet_identity='sheet-identity'; lease_file='C:\\lease.json'; ack_file='C:\\ack.json'
        worksheet_last_row=($NextHeader + 4); group_start=4; group_end=($NextHeader - 1); next_header=$NextHeader; insertion_row=$NextHeader
        source_row=($NextHeader - 1); template_row=($NextHeader - 1); ordinal_mapping=@([ordered]@{ row=$NextHeader; ordinal=1 })
        fields=[ordered]@{'6'='38-1-1-2026'; '27'=''}; formulas=[ordered]@{y='=IF(RC[-24]<>"",ROW(),"")';z='=IF(RC[-20]<>"",ROW(),"")'}
        hyperlink=[ordered]@{address='file:///C:/document.pdf';display='document.pdf'}
    }
    return ($request | ConvertTo-Json -Depth 8 -Compress)
}

function Assert-Rejected([string]$Json, [string]$Expected) {
    $script:called = $false
    try { Test-WindowsExcelRequestSchema -RequestJson $Json -BeforeCom { $script:called = $true } | Out-Null; throw 'expected schema failure' }
    catch { $_.Exception.Message | Should -Match $Expected }
    $script:called | Should -BeFalse
}

Describe 'Windows Excel request schema v1' {
    It 'accepts the exact boundary cases 6, 10, and 104 before the COM callback' {
        foreach ($header in 6, 10, 104) {
            $script:called = $false
            $result = Test-WindowsExcelRequestSchema -RequestJson (New-ValidRequestJson $header) -BeforeCom { param($request) $script:called = $request.insertion_row -eq $header }
            $result.insertion_row | Should -Be $header
            $called | Should -BeTrue
        }
    }

    It 'rejects negative, fractional, string, and out-of-range row values before callbacks' {
        Assert-Rejected ((New-ValidRequestJson) -replace '"insertion_row":6','"insertion_row":-1') 'integral_number_required'
        Assert-Rejected ((New-ValidRequestJson) -replace '"insertion_row":6','"insertion_row":6.5') 'integral_number_required'
        Assert-Rejected ((New-ValidRequestJson) -replace '"insertion_row":6','"insertion_row":"6"') 'integral_number_required'
        Assert-Rejected ((New-ValidRequestJson) -replace '"worksheet_last_row":10','"worksheet_last_row":1048576') 'worksheet_capacity_invalid'
    }

    It 'rejects duplicate JSON keys and duplicate ordinal mapping values before callbacks' {
        $duplicateKey = (New-ValidRequestJson) -replace '"sheet":"Реестр РНС"','"sheet":"Реестр РНС","sheet":"duplicate"'
        Assert-Rejected $duplicateKey 'duplicate_key'
        $duplicateOrdinal = (New-ValidRequestJson) -replace '"ordinal_mapping":\[\{"row":6,"ordinal":1\}\]','"ordinal_mapping":[{"row":5,"ordinal":1},{"row":6,"ordinal":1}]'
        Assert-Rejected $duplicateOrdinal 'ordinal_mapping_duplicate'
    }

    It 'rejects unknown fields and protected A W Y Z writes before callbacks' {
        Assert-Rejected ((New-ValidRequestJson) -replace '"27":""','"27":"","25":"illegal"') 'field_column_forbidden'
        Assert-Rejected ((New-ValidRequestJson) -replace '"operation_id":"operation-1"','"operation_id":"operation-1","unknown":true') 'unknown_field'
        Assert-Rejected ((New-ValidRequestJson) -replace '"y":"=IF','"y":"IF') 'formula_r1c1_required'
    }

    It 'rejects group membership, header relation, and missing lease identity fields before callbacks' {
        Assert-Rejected ((New-ValidRequestJson) -replace '"next_header":6','"next_header":7') 'group_boundary_invalid'
        Assert-Rejected ((New-ValidRequestJson) -replace '"source_row":5','"source_row":4') 'group_membership_invalid'
        Assert-Rejected ((New-ValidRequestJson) -replace '"lease_file":"C:\\\\lease.json",','') 'required_field'
    }
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-Pester -Path $PSCommandPath -Output Detailed }
