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
    $state = $State
    $addCallCommand = Get-Command Add-WindowsExcelFakeComCall -CommandType Function
    $faultCommand = Get-Command Invoke-WindowsExcelFakeComFault -CommandType Function
    $newProxyCommand = Get-Command New-WindowsExcelFakeComProxy -CommandType Function
    Add-WindowsExcelFakeComCall -State $State -Event 'proxy.acquire' -Proxy $proxy
    $proxy | Add-Member -MemberType ScriptMethod -Name Release -Value {
        if (-not $proxy.Released) {
            & $addCallCommand -State $state -Event 'proxy.release' -Stage 'release' -Proxy $proxy
            try { & $faultCommand -State $state -Stage 'release' }
            finally { $proxy.Released = $true }
        }
    }.GetNewClosure()

    switch ($Kind) {
        'Application' {
            $proxy | Add-Member ScriptProperty Workbooks ({
                & $addCallCommand -State $state -Event 'proxy.acquire.property' -Proxy $proxy -Arguments @{ property = 'Workbooks' }
                & $newProxyCommand -State $state -Kind 'Workbooks'
            }.GetNewClosure())
            $proxy | Add-Member ScriptMethod CalculateFullRebuild ({
                & $addCallCommand -State $state -Event 'application.calculate' -Stage 'calc' -Proxy $proxy
                & $faultCommand -State $state -Stage 'calc'
            }.GetNewClosure())
            $proxy | Add-Member ScriptMethod Quit ({
                & $addCallCommand -State $state -Event 'application.quit' -Stage 'cleanup' -Proxy $proxy
                & $faultCommand -State $state -Stage 'cleanup'
            }.GetNewClosure())
        }
        'Workbooks' {
            $proxy | Add-Member ScriptMethod Open ({ param([string]$Path, [int]$UpdateLinks, [bool]$ReadOnly)
                & $addCallCommand -State $state -Event 'workbooks.open' -Stage 'open' -Proxy $proxy -Arguments @{ path = $Path; update_links = $UpdateLinks; read_only = $ReadOnly }
                & $faultCommand -State $state -Stage 'open'
                & $newProxyCommand -State $state -Kind 'Workbook' -Metadata @{ Path = $Path }
            }.GetNewClosure())
        }
        'Workbook' {
            $proxy | Add-Member ScriptProperty Worksheets ({
                & $addCallCommand -State $state -Event 'proxy.acquire.property' -Proxy $proxy -Arguments @{ property = 'Worksheets' }
                & $newProxyCommand -State $state -Kind 'Worksheets'
            }.GetNewClosure())
            $proxy | Add-Member ScriptMethod Save ({
                & $addCallCommand -State $state -Event 'workbook.save' -Stage 'save' -Proxy $proxy
                & $faultCommand -State $state -Stage 'save'
            }.GetNewClosure())
            $proxy | Add-Member ScriptMethod Close ({ param([bool]$SaveChanges)
                & $addCallCommand -State $state -Event 'workbook.close' -Stage 'cleanup' -Proxy $proxy -Arguments @{ save_changes = $SaveChanges }
                & $faultCommand -State $state -Stage 'cleanup'
            }.GetNewClosure())
        }
        'Worksheets' {
            $proxy | Add-Member ScriptMethod Item ({ param([string]$Name)
                & $addCallCommand -State $state -Event 'worksheets.item' -Proxy $proxy -Arguments @{ name = $Name }
                & $newProxyCommand -State $state -Kind 'Sheet' -Metadata @{ Name = $Name }
            }.GetNewClosure())
        }
        'Sheet' {
            foreach ($property in @('Rows', 'Cells', 'Hyperlinks')) {
                $propertyName = $property
                $getter = {
                    & $addCallCommand -State $state -Event 'proxy.acquire.property' -Proxy $proxy -Arguments @{ property = $propertyName }
                    & $newProxyCommand -State $state -Kind $propertyName
                }.GetNewClosure()
                $proxy | Add-Member ScriptProperty $propertyName $getter
            }
        }
        'Rows' {
            $proxy | Add-Member ScriptMethod Item ({ param([int]$Row)
                & $addCallCommand -State $state -Event 'rows.item' -Proxy $proxy -Arguments @{ row = $Row }
                & $newProxyCommand -State $state -Kind 'Row' -Metadata @{ Row = $Row }
            }.GetNewClosure())
        }
        'Row' {
            $proxy | Add-Member ScriptMethod Insert ({ param([int]$Shift, [int]$CopyOrigin)
                & $addCallCommand -State $state -Event 'row.insert' -Stage 'insert' -Proxy $proxy -Arguments @{ row = $proxy.Row; shift = $Shift; copy_origin = $CopyOrigin }
                & $faultCommand -State $state -Stage 'insert'
            }.GetNewClosure())
        }
        'Cells' {
            $proxy | Add-Member ScriptMethod Item ({ param([int]$Row, [int]$Column)
                & $addCallCommand -State $state -Event 'cells.item' -Proxy $proxy -Arguments @{ row = $Row; column = $Column }
                & $newProxyCommand -State $state -Kind 'Cell' -Metadata @{ Row = $Row; Column = $Column }
            }.GetNewClosure())
        }
        'Cell' {
            $proxy | Add-Member ScriptProperty Value2 ({ $proxy._Value2 }.GetNewClosure()) ({ param($Value)
                & $addCallCommand -State $state -Event 'cell.mutate.value2' -Stage 'mutation' -Proxy $proxy -Arguments @{ row = $proxy.Row; column = $proxy.Column; value = $Value }
                $proxy._Value2 = $Value
            }.GetNewClosure())
            $proxy | Add-Member -MemberType NoteProperty -Name _Value2 -Value $null
        }
        'Hyperlinks' {
            $proxy | Add-Member ScriptMethod Add ({ param($Anchor, [string]$Address)
                & $addCallCommand -State $state -Event 'hyperlinks.add' -Stage 'mutation' -Proxy $proxy -Arguments @{ anchor_id = $Anchor.Id; row = $Anchor.Row; column = $Anchor.Column; address = $Address }
                & $newProxyCommand -State $state -Kind 'Hyperlink' -Metadata @{ Address = $Address; AnchorId = $Anchor.Id }
            }.GetNewClosure())
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

function Find-WindowsExcelFakeComControlledException {
    param([Parameter(Mandatory)]$Exception)
    $seen = [System.Collections.Generic.HashSet[System.Exception]]::new()
    $current = $Exception
    for ($depth = 0; $depth -lt 4 -and $null -ne $current; $depth++) {
        if (-not $seen.Add($current)) { break }
        if ($null -ne $current.Data -and $current.Data.Contains('stage')) { return $current }
        $current = $current.InnerException
    }
    return $null
}

function Write-WindowsExcelFakeComUnexpectedException {
    param([Parameter(Mandatory)]$Exception, [string]$ScriptStackTrace = '')
    try {
        Write-Warning ("fake_com_unexpected_exception type={0}; message={1}; stack={2}" -f $Exception.GetType().FullName, $Exception.Message, $ScriptStackTrace) -WarningAction Continue
    } catch {}
}

function Get-WindowsExcelFakeComErrorEnvelope {
    param($Exception, [string]$ScriptStackTrace = '')
    if ($null -eq $Exception) { return $null }
    $controlledException = Find-WindowsExcelFakeComControlledException -Exception $Exception
    if ($null -eq $controlledException) {
        Write-WindowsExcelFakeComUnexpectedException -Exception $Exception -ScriptStackTrace $ScriptStackTrace
        $controlledException = $Exception
    }
    [pscustomobject]@{
        message = $controlledException.Message
        stage = [string]$controlledException.Data['stage']
        occurrence = if ($controlledException.Data.Contains('occurrence')) { [int]$controlledException.Data['occurrence'] } else { 0 }
        hresult = [int]$controlledException.Data['hresult']
        winerror = [int]$controlledException.Data['winerror']
    }
}

function Invoke-WindowsExcelFakeComScenario {
    [CmdletBinding()]
    param([Parameter(Mandatory)][ValidateSet(6, 10, 104)][int]$InsertionRow, [hashtable]$Faults = @{})
    $fake = New-WindowsExcelFakeCom -Faults $Faults
    $proxies = [System.Collections.Generic.List[object]]::new()
    $app = $fake.Application; [void]$proxies.Add($app)
    $error = $null; $primaryErrorRecord = $null; $cleanupErrors = [System.Collections.Generic.List[object]]::new()
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
    } catch { $error = $_.Exception; $primaryErrorRecord = $_ }
    finally {
        for ($index = $proxies.Count - 1; $index -ge 0; $index--) {
            try { $proxies[$index].Release() } catch { [void]$cleanupErrors.Add((Get-WindowsExcelFakeComErrorEnvelope $_.Exception $_.ScriptStackTrace)) }
        }
    }
    $primaryStackTrace = if ($null -eq $primaryErrorRecord) { '' } else { $primaryErrorRecord.ScriptStackTrace }
    $primaryError = Get-WindowsExcelFakeComErrorEnvelope $error $primaryStackTrace
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
