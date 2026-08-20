Set-StrictMode -Version Latest

function Add-WindowsExcelFakeComCall {
    param(
        [Parameter(Mandatory)]$State,
        [Parameter(Mandatory)][string]$Event,
        [string]$Stage = '',
        $Proxy = $null,
        [hashtable]$Arguments = @{}
    )

    $State.Sequence++
    [void]$State.Calls.Add([pscustomobject]@{
        sequence = $State.Sequence
        event = $Event
        stage = $Stage
        kind = if ($null -eq $Proxy) { '' } else { $Proxy.Kind }
        proxy_id = if ($null -eq $Proxy) { 0 } else { $Proxy.Id }
        arguments = [pscustomobject]$Arguments
    })
}

function Invoke-WindowsExcelFakeComFault {
    param([Parameter(Mandatory)]$State, [Parameter(Mandatory)][string]$Stage)

    if (-not $State.FaultCounts.ContainsKey($Stage)) { $State.FaultCounts[$Stage] = 0 }
    $State.FaultCounts[$Stage] = [int]$State.FaultCounts[$Stage] + 1
    $occurrence = [int]$State.FaultCounts[$Stage]
    if (-not $State.Faults.ContainsKey($Stage)) { return }
    $fault = $State.Faults[$Stage]
    if ($fault -isnot [hashtable]) { $fault = @{} }
    if ($fault.ContainsKey('occurrence') -and $occurrence -ne [int]$fault.occurrence) { return }
    if ($fault.ContainsKey('occurrences') -and $occurrence -notin @($fault.occurrences | ForEach-Object { [int]$_ })) { return }
    $message = if ($fault.message) { [string]$fault.message } else { "fake_excel_$Stage`_fault" }
    $exception = [System.InvalidOperationException]::new($message)
    $exception.Data['stage'] = $Stage
    $exception.Data['occurrence'] = $occurrence
    $exception.Data['hresult'] = if ($fault.ContainsKey('hresult')) { [int]$fault.hresult } else { -2147352567 }
    $exception.Data['winerror'] = if ($fault.ContainsKey('winerror')) { [int]$fault.winerror } else { 5 }
    throw $exception
}

function New-WindowsExcelFakeComProxy {
    param([Parameter(Mandatory)]$State, [Parameter(Mandatory)][string]$Kind, [hashtable]$Metadata = @{})

    $State.NextId++
    $proxy = [pscustomobject](@{ Kind = $Kind; Id = $State.NextId; Released = $false; _State = $State } + $Metadata)
    Add-WindowsExcelFakeComCall -State $State -Event 'proxy.acquire' -Proxy $proxy
    $proxy | Add-Member -MemberType ScriptMethod -Name Release -Value {
        if (-not $this.Released) {
            Add-WindowsExcelFakeComCall -State $this._State -Event 'proxy.release' -Stage 'release' -Proxy $this
            try { Invoke-WindowsExcelFakeComFault -State $this._State -Stage 'release' }
            finally { $this.Released = $true }
        }
    }

    switch ($Kind) {
        'Application' {
            $proxy | Add-Member ScriptProperty Workbooks ({
                Add-WindowsExcelFakeComCall -State $this._State -Event 'proxy.acquire.property' -Proxy $this -Arguments @{ property = 'Workbooks' }
                New-WindowsExcelFakeComProxy -State $this._State -Kind 'Workbooks'
            })
            $proxy | Add-Member ScriptMethod CalculateFullRebuild ({
                Add-WindowsExcelFakeComCall -State $this._State -Event 'application.calculate' -Stage 'calc' -Proxy $this
                Invoke-WindowsExcelFakeComFault -State $this._State -Stage 'calc'
            })
            $proxy | Add-Member ScriptMethod Quit ({
                Add-WindowsExcelFakeComCall -State $this._State -Event 'application.quit' -Stage 'cleanup' -Proxy $this
                Invoke-WindowsExcelFakeComFault -State $this._State -Stage 'cleanup'
            })
        }
        'Workbooks' {
            $proxy | Add-Member ScriptMethod Open ({ param([string]$Path, [int]$UpdateLinks, [bool]$ReadOnly)
                Add-WindowsExcelFakeComCall -State $this._State -Event 'workbooks.open' -Stage 'open' -Proxy $this -Arguments @{ path = $Path; update_links = $UpdateLinks; read_only = $ReadOnly }
                Invoke-WindowsExcelFakeComFault -State $this._State -Stage 'open'
                New-WindowsExcelFakeComProxy -State $this._State -Kind 'Workbook' -Metadata @{ Path = $Path }
            })
        }
        'Workbook' {
            $proxy | Add-Member ScriptProperty Worksheets ({
                Add-WindowsExcelFakeComCall -State $this._State -Event 'proxy.acquire.property' -Proxy $this -Arguments @{ property = 'Worksheets' }
                New-WindowsExcelFakeComProxy -State $this._State -Kind 'Worksheets'
            })
            $proxy | Add-Member ScriptMethod Save ({
                Add-WindowsExcelFakeComCall -State $this._State -Event 'workbook.save' -Stage 'save' -Proxy $this
                Invoke-WindowsExcelFakeComFault -State $this._State -Stage 'save'
            })
            $proxy | Add-Member ScriptMethod Close ({ param([bool]$SaveChanges)
                Add-WindowsExcelFakeComCall -State $this._State -Event 'workbook.close' -Stage 'cleanup' -Proxy $this -Arguments @{ save_changes = $SaveChanges }
                Invoke-WindowsExcelFakeComFault -State $this._State -Stage 'cleanup'
            })
        }
        'Worksheets' {
            $proxy | Add-Member ScriptMethod Item ({ param([string]$Name)
                Add-WindowsExcelFakeComCall -State $this._State -Event 'worksheets.item' -Proxy $this -Arguments @{ name = $Name }
                New-WindowsExcelFakeComProxy -State $this._State -Kind 'Sheet' -Metadata @{ Name = $Name }
            })
        }
        'Sheet' {
            foreach ($property in @('Rows', 'Cells', 'Hyperlinks')) {
                $propertyName = $property
                $getter = {
                    Add-WindowsExcelFakeComCall -State $this._State -Event 'proxy.acquire.property' -Proxy $this -Arguments @{ property = $propertyName }
                    New-WindowsExcelFakeComProxy -State $this._State -Kind $propertyName
                }.GetNewClosure()
                $proxy | Add-Member ScriptProperty $propertyName $getter
            }
        }
        'Rows' {
            $proxy | Add-Member ScriptMethod Item ({ param([int]$Row)
                Add-WindowsExcelFakeComCall -State $this._State -Event 'rows.item' -Proxy $this -Arguments @{ row = $Row }
                New-WindowsExcelFakeComProxy -State $this._State -Kind 'Row' -Metadata @{ Row = $Row }
            })
        }
        'Row' {
            $proxy | Add-Member ScriptMethod Insert ({ param([int]$Shift, [int]$CopyOrigin)
                Add-WindowsExcelFakeComCall -State $this._State -Event 'row.insert' -Stage 'insert' -Proxy $this -Arguments @{ row = $this.Row; shift = $Shift; copy_origin = $CopyOrigin }
                Invoke-WindowsExcelFakeComFault -State $this._State -Stage 'insert'
            })
        }
        'Cells' {
            $proxy | Add-Member ScriptMethod Item ({ param([int]$Row, [int]$Column)
                Add-WindowsExcelFakeComCall -State $this._State -Event 'cells.item' -Proxy $this -Arguments @{ row = $Row; column = $Column }
                New-WindowsExcelFakeComProxy -State $this._State -Kind 'Cell' -Metadata @{ Row = $Row; Column = $Column }
            })
        }
        'Cell' {
            $proxy | Add-Member ScriptProperty Value2 ({ $this._Value2 }) ({ param($Value)
                Add-WindowsExcelFakeComCall -State $this._State -Event 'cell.mutate.value2' -Stage 'mutation' -Proxy $this -Arguments @{ row = $this.Row; column = $this.Column; value = $Value }
                $this._Value2 = $Value
            })
            $proxy | Add-Member -MemberType NoteProperty -Name _Value2 -Value $null
        }
        'Hyperlinks' {
            $proxy | Add-Member ScriptMethod Add ({ param($Anchor, [string]$Address)
                Add-WindowsExcelFakeComCall -State $this._State -Event 'hyperlinks.add' -Stage 'mutation' -Proxy $this -Arguments @{ anchor_id = $Anchor.Id; row = $Anchor.Row; column = $Anchor.Column; address = $Address }
                New-WindowsExcelFakeComProxy -State $this._State -Kind 'Hyperlink' -Metadata @{ Address = $Address; AnchorId = $Anchor.Id }
            })
        }
    }
    return $proxy
}

function New-WindowsExcelFakeCom {
    [CmdletBinding()]
    param([hashtable]$Faults = @{})
    $state = [pscustomobject]@{ Calls = [System.Collections.Generic.List[object]]::new(); Faults = $Faults; FaultCounts = @{}; NextId = 0; Sequence = 0 }
    [pscustomobject]@{ Application = (New-WindowsExcelFakeComProxy -State $state -Kind 'Application'); State = $state }
}

function Get-WindowsExcelFakeComErrorEnvelope {
    param($Exception)
    if ($null -eq $Exception) { return $null }
    [pscustomobject]@{
        message = $Exception.Message
        stage = [string]$Exception.Data['stage']
        occurrence = if ($Exception.Data.Contains('occurrence')) { [int]$Exception.Data['occurrence'] } else { 0 }
        hresult = [int]$Exception.Data['hresult']
        winerror = [int]$Exception.Data['winerror']
    }
}

function Invoke-WindowsExcelFakeComScenario {
    [CmdletBinding()]
    param([Parameter(Mandatory)][ValidateSet(6, 10, 104)][int]$InsertionRow, [hashtable]$Faults = @{})
    $fake = New-WindowsExcelFakeCom -Faults $Faults
    $proxies = [System.Collections.Generic.List[object]]::new()
    $app = $fake.Application; [void]$proxies.Add($app)
    $error = $null; $cleanupErrors = [System.Collections.Generic.List[object]]::new()
    try {
        $workbooks = $app.Workbooks; [void]$proxies.Add($workbooks)
        $control = $workbooks.Open('control.xlsx', 0, $false); [void]$proxies.Add($control)
        $app.CalculateFullRebuild(); $control.Save(); $control.Close($true)
        $candidate = $workbooks.Open('candidate.xlsx', 0, $false); [void]$proxies.Add($candidate)
        $worksheets = $candidate.Worksheets; [void]$proxies.Add($worksheets)
        $sheet = $worksheets.Item('Объекты'); [void]$proxies.Add($sheet)
        $rows = $sheet.Rows; [void]$proxies.Add($rows)
        $row = $rows.Item($InsertionRow); [void]$proxies.Add($row); $row.Insert(-4121, 0)
        $cells = $sheet.Cells; [void]$proxies.Add($cells)
        foreach ($column in @(1, 2, 23)) { $cell = $cells.Item($InsertionRow, $column); [void]$proxies.Add($cell); $cell.Value2 = "row-$InsertionRow-col-$column" }
        $hyperlinks = $sheet.Hyperlinks; [void]$proxies.Add($hyperlinks)
        $linkAnchor = $cells.Item($InsertionRow, 23); [void]$proxies.Add($linkAnchor)
        $link = $hyperlinks.Add($linkAnchor, "https://example.invalid/$InsertionRow"); [void]$proxies.Add($link)
        $app.CalculateFullRebuild(); $candidate.Save(); $candidate.Close($true); $app.Quit()
    } catch { $error = $_.Exception }
    finally {
        for ($index = $proxies.Count - 1; $index -ge 0; $index--) {
            try { $proxies[$index].Release() } catch { [void]$cleanupErrors.Add((Get-WindowsExcelFakeComErrorEnvelope $_.Exception)) }
        }
    }
    $primaryError = Get-WindowsExcelFakeComErrorEnvelope $error
    $cleanup = @($cleanupErrors)
    $classification = if ($null -ne $primaryError) {
        if ($cleanup.Count -gt 0) { 'primary_and_cleanup_failure' } else { 'primary_failure' }
    } elseif ($cleanup.Count -gt 0) {
        'cleanup_failure'
    } else {
        'success'
    }
    [pscustomobject]@{
        Trace = @($fake.State.Calls)
        Error = $primaryError
        CleanupErrors = $cleanup
        Proxies = @($proxies)
        Final = [pscustomobject]@{
            classification = $classification
            success = $classification -eq 'success'
            primary_failure = $primaryError
            cleanup_failures = $cleanup
            cleanup_failure_count = $cleanup.Count
        }
    }
}

function Test-WindowsExcelFakeComTrace {
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Scenario, [Parameter(Mandatory)][ValidateSet(6, 10, 104)][int]$InsertionRow)
    $trace = @($Scenario.Trace)
    $insert = @($trace | Where-Object { $_.event -eq 'row.insert' -and $_.arguments.row -eq $InsertionRow })
    $writes = @($trace | Where-Object { $_.event -eq 'cell.mutate.value2' -and $_.arguments.row -eq $InsertionRow })
    $link = @($trace | Where-Object { $_.event -eq 'hyperlinks.add' -and $_.arguments.row -eq $InsertionRow -and $_.arguments.column -eq 23 })
    $acquired = @($trace | Where-Object event -eq 'proxy.acquire')
    $released = @($trace | Where-Object event -eq 'proxy.release')
    $expectedRelease = [object[]]@($acquired.proxy_id)
    [array]::Reverse($expectedRelease)
    [pscustomobject]@{
        row = $InsertionRow
        has_insert = $insert.Count -eq 1
        has_mutations = $writes.Count -eq 3
        has_hyperlink_result = @($acquired | Where-Object kind -eq 'Hyperlink').Count -eq 1
        reverse_release = (@($released.proxy_id) -join ',') -eq ($expectedRelease -join ',')
        is_success = $Scenario.Final.success
        call_envelope = [pscustomobject]@{ insert = $insert; mutations = $writes; hyperlink = $link }
    }
}

Export-ModuleMember -Function New-WindowsExcelFakeCom, Invoke-WindowsExcelFakeComScenario, Get-WindowsExcelFakeComErrorEnvelope, Test-WindowsExcelFakeComTrace
