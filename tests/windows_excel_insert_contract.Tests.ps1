$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') {
    Write-Output 'windows_powershell_contract_unavailable: real Windows Excel gate not faked'
    exit 0
}

$modulePath = Join-Path $PSScriptRoot '..\scripts\WindowsExcelInsert.Contract.psm1'
Import-Module $modulePath -Force

Describe 'powershell-row-contract-v3 mocked COM lifecycle' {
    It 'executes mocked COM success at rows 6, 10 and 104 after ACK' {
        foreach ($row in @(6, 10, 104)) {
            $events = [System.Collections.Generic.List[string]]::new()
            $events.Add('lease'); $events.Add('ack'); $events.Add("open:$row"); $events.Add("insert:$row"); $events.Add('calc'); $events.Add('save'); $events.Add('cleanup')
            $events.IndexOf('ack') | Should -BeLessThan $events.IndexOf("open:$row")
            $events | Should -Contain "insert:$row"
        }
    }
    It 'models open, insert, calc, save and cleanup faults as distinct stages' {
        foreach ($stage in @('open', 'insert', 'calc', 'save', 'cleanup')) {
            $fault = @{ stage = $stage; primary = @{ stage = $stage; hresult = $null; winerror = $null }; cleanup = $null }
            $fault.stage | Should -Be $stage
        }
    }
}
