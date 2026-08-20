Set-StrictMode -Version Latest

$script:ExcelMaximumRows = 1048576

function Throw-RequestSchemaError {
    param([Parameter(Mandatory = $true)][string]$Code)
    throw [System.ArgumentException]::new($Code)
}

function Read-JsonStringEnd {
    param([string]$Text, [int]$Index)
    if ($Text[$Index] -ne '"') { Throw-RequestSchemaError 'request_schema_json_string_expected' }
    $cursor = $Index + 1
    while ($cursor -lt $Text.Length) {
        if ($Text[$cursor] -eq '\\') {
            $cursor++
            if ($cursor -ge $Text.Length) { Throw-RequestSchemaError 'request_schema_json_escape_invalid' }
            if ($Text[$cursor] -eq 'u') {
                if (($cursor + 4) -ge $Text.Length -or $Text.Substring($cursor + 1, 4) -notmatch '^[0-9A-Fa-f]{4}$') {
                    Throw-RequestSchemaError 'request_schema_json_escape_invalid'
                }
                $cursor += 4
            }
        } elseif ($Text[$cursor] -eq '"') {
            return $cursor + 1
        } elseif ([int][char]$Text[$cursor] -lt 0x20) {
            Throw-RequestSchemaError 'request_schema_json_string_invalid'
        }
        $cursor++
    }
    Throw-RequestSchemaError 'request_schema_json_string_unterminated'
}

function Convert-JsonStringToken {
    param([Parameter(Mandatory = $true)][string]$Raw)
    try { return ($Raw | ConvertFrom-Json -ErrorAction Stop) } catch { Throw-RequestSchemaError 'request_schema_json_string_invalid' }
}

function Read-JsonSchemaNode {
    param([string]$Text, [ref]$Cursor, [string]$Path)
    while ($Cursor.Value -lt $Text.Length -and [char]::IsWhiteSpace($Text[$Cursor.Value])) { $Cursor.Value++ }
    if ($Cursor.Value -ge $Text.Length) { Throw-RequestSchemaError 'request_schema_json_unexpected_end' }
    $start = $Cursor.Value; $character = $Text[$Cursor.Value]
    if ($character -eq '"') {
        $Cursor.Value = Read-JsonStringEnd $Text $Cursor.Value
        return [pscustomobject]@{ Kind = 'string'; Raw = $Text.Substring($start, $Cursor.Value - $start) }
    }
    if ($character -eq '{') {
        $Cursor.Value++
        $properties = [ordered]@{}
        while ($true) {
            while ($Cursor.Value -lt $Text.Length -and [char]::IsWhiteSpace($Text[$Cursor.Value])) { $Cursor.Value++ }
            if ($Cursor.Value -ge $Text.Length) { Throw-RequestSchemaError 'request_schema_json_unexpected_end' }
            if ($Text[$Cursor.Value] -eq '}') { $Cursor.Value++; break }
            $keyStart = $Cursor.Value; $keyEnd = Read-JsonStringEnd $Text $Cursor.Value
            $key = Convert-JsonStringToken $Text.Substring($keyStart, $keyEnd - $keyStart)
            if ($properties.Contains($key)) { Throw-RequestSchemaError "request_schema_duplicate_key:$Path.$key" }
            $Cursor.Value = $keyEnd
            while ($Cursor.Value -lt $Text.Length -and [char]::IsWhiteSpace($Text[$Cursor.Value])) { $Cursor.Value++ }
            if ($Cursor.Value -ge $Text.Length -or $Text[$Cursor.Value] -ne ':') { Throw-RequestSchemaError 'request_schema_json_colon_expected' }
            $Cursor.Value++
            $childCursor = $Cursor.Value
            $properties[$key] = Read-JsonSchemaNode $Text ([ref]$childCursor) "$Path.$key"
            $Cursor.Value = $childCursor
            while ($Cursor.Value -lt $Text.Length -and [char]::IsWhiteSpace($Text[$Cursor.Value])) { $Cursor.Value++ }
            if ($Cursor.Value -lt $Text.Length -and $Text[$Cursor.Value] -eq ',') { $Cursor.Value++; continue }
            if ($Cursor.Value -lt $Text.Length -and $Text[$Cursor.Value] -eq '}') { $Cursor.Value++; break }
            Throw-RequestSchemaError 'request_schema_json_object_delimiter_expected'
        }
        return [pscustomobject]@{ Kind = 'object'; Properties = $properties }
    }
    if ($character -eq '[') {
        $Cursor.Value++; $items = [System.Collections.Generic.List[object]]::new(); $index = 0
        while ($true) {
            while ($Cursor.Value -lt $Text.Length -and [char]::IsWhiteSpace($Text[$Cursor.Value])) { $Cursor.Value++ }
            if ($Cursor.Value -ge $Text.Length) { Throw-RequestSchemaError 'request_schema_json_unexpected_end' }
            if ($Text[$Cursor.Value] -eq ']') { $Cursor.Value++; break }
            $childCursor = $Cursor.Value
            $items.Add((Read-JsonSchemaNode $Text ([ref]$childCursor) "$Path[$index]")); $index++
            $Cursor.Value = $childCursor
            while ($Cursor.Value -lt $Text.Length -and [char]::IsWhiteSpace($Text[$Cursor.Value])) { $Cursor.Value++ }
            if ($Cursor.Value -lt $Text.Length -and $Text[$Cursor.Value] -eq ',') { $Cursor.Value++; continue }
            if ($Cursor.Value -lt $Text.Length -and $Text[$Cursor.Value] -eq ']') { $Cursor.Value++; break }
            Throw-RequestSchemaError 'request_schema_json_array_delimiter_expected'
        }
        return [pscustomobject]@{ Kind = 'array'; Items = $items }
    }
    $rest = $Text.Substring($Cursor.Value)
    if ($rest -match '^(true|false|null)(?=\s|,|\]|\}|$)') {
        $raw = $matches[1]; $Cursor.Value += $raw.Length
        return [pscustomobject]@{ Kind = $raw; Raw = $raw }
    }
    if ($rest -match '^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?') {
        $raw = $matches[0]; $Cursor.Value += $raw.Length
        return [pscustomobject]@{ Kind = 'number'; Raw = $raw }
    }
    Throw-RequestSchemaError 'request_schema_json_value_invalid'
}

function Assert-ObjectKeys {
    param([object]$Node, [string]$Path, [string[]]$Required, [string[]]$Allowed)
    if ($Node.Kind -ne 'object') { Throw-RequestSchemaError "request_schema_object_required:$Path" }
    foreach ($name in $Node.Properties.Keys) {
        if ($name -notin $Allowed) { Throw-RequestSchemaError "request_schema_unknown_field:$Path.$name" }
    }
    foreach ($name in $Required) {
        if (-not $Node.Properties.Contains($name)) { Throw-RequestSchemaError "request_schema_required_field:$Path.$name" }
    }
}

function Get-RequiredString {
    param([object]$Node, [string]$Path)
    if ($Node.Kind -ne 'string') { Throw-RequestSchemaError "request_schema_string_required:$Path" }
    $value = Convert-JsonStringToken $Node.Raw
    if ([string]::IsNullOrWhiteSpace($value)) { Throw-RequestSchemaError "request_schema_string_empty:$Path" }
    return $value
}

function Get-ExcelInteger {
    param([object]$Node, [string]$Path, [int64]$Minimum = 1, [int64]$Maximum = $script:ExcelMaximumRows)
    if ($Node.Kind -ne 'number' -or $Node.Raw -notmatch '^(?:0|[1-9][0-9]*)$') { Throw-RequestSchemaError "request_schema_integral_number_required:$Path" }
    try { $number = [int64]::Parse($Node.Raw, [Globalization.CultureInfo]::InvariantCulture) } catch { Throw-RequestSchemaError "request_schema_integer_overflow:$Path" }
    if ($number -lt $Minimum -or $number -gt $Maximum) { Throw-RequestSchemaError "request_schema_excel_bounds:$Path" }
    return $number
}

function Test-WindowsExcelRequestSchema {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RequestJson,
        [scriptblock]$BeforeCom
    )
    $cursor = 0; $root = Read-JsonSchemaNode $RequestJson ([ref]$cursor) '$'
    while ($cursor -lt $RequestJson.Length -and [char]::IsWhiteSpace($RequestJson[$cursor])) { $cursor++ }
    if ($cursor -ne $RequestJson.Length) { Throw-RequestSchemaError 'request_schema_json_trailing_data' }
    Assert-ObjectKeys $root '$' @('operation_id','owner_nonce','pair_nonce','control','candidate','sheet','workbook_identity','sheet_identity','lease_file','ack_file','worksheet_last_row','group_start','group_end','next_header','insertion_row','source_row','template_row','ordinal_mapping','fields','formulas','hyperlink') @('operation_id','owner_nonce','pair_nonce','control','candidate','sheet','workbook_identity','sheet_identity','lease_file','ack_file','worksheet_last_row','group_start','group_end','next_header','insertion_row','source_row','template_row','ordinal_mapping','fields','formulas','hyperlink')
    foreach ($name in @('operation_id','owner_nonce','pair_nonce','control','candidate','sheet','workbook_identity','sheet_identity','lease_file','ack_file')) { [void](Get-RequiredString $root.Properties[$name] "`$.$name") }
    if ((Get-RequiredString $root.Properties.control '$.control') -eq (Get-RequiredString $root.Properties.candidate '$.candidate')) { Throw-RequestSchemaError 'request_schema_control_candidate_same' }
    $lastRow = Get-ExcelInteger $root.Properties.worksheet_last_row '$.worksheet_last_row'
    $groupStart = Get-ExcelInteger $root.Properties.group_start '$.group_start'
    $groupEnd = Get-ExcelInteger $root.Properties.group_end '$.group_end'
    $nextHeader = Get-ExcelInteger $root.Properties.next_header '$.next_header'
    $insertion = Get-ExcelInteger $root.Properties.insertion_row '$.insertion_row'
    $source = Get-ExcelInteger $root.Properties.source_row '$.source_row'
    $template = Get-ExcelInteger $root.Properties.template_row '$.template_row'
    if ($groupEnd -lt ($groupStart + 1) -or $nextHeader -ne ($groupEnd + 1) -or $insertion -ne $nextHeader) { Throw-RequestSchemaError 'request_schema_group_boundary_invalid' }
    if ($lastRow -lt $nextHeader -or $lastRow -ge $script:ExcelMaximumRows) { Throw-RequestSchemaError 'request_schema_worksheet_capacity_invalid' }
    foreach ($member in @(@{ Name='source_row'; Value=$source }, @{ Name='template_row'; Value=$template })) {
        if ($member.Value -le $groupStart -or $member.Value -gt $groupEnd) { Throw-RequestSchemaError "request_schema_group_membership_invalid:`$($member.Name)" }
    }
    $mapping = $root.Properties.ordinal_mapping
    if ($mapping.Kind -ne 'array' -or $mapping.Items.Count -eq 0) { Throw-RequestSchemaError 'request_schema_ordinal_mapping_required' }
    $mappedRows = [System.Collections.Generic.HashSet[int64]]::new(); $ordinals = [System.Collections.Generic.HashSet[int64]]::new(); $hasInsertion = $false
    for ($index = 0; $index -lt $mapping.Items.Count; $index++) {
        $item = $mapping.Items[$index]; Assert-ObjectKeys $item "`$.ordinal_mapping[$index]" @('row','ordinal') @('row','ordinal')
        $row = Get-ExcelInteger $item.Properties.row "`$.ordinal_mapping[$index].row"; $ordinal = Get-ExcelInteger $item.Properties.ordinal "`$.ordinal_mapping[$index].ordinal"
        if ($row -le $groupStart -or $row -gt $insertion) { Throw-RequestSchemaError 'request_schema_ordinal_mapping_group_invalid' }
        if (-not $mappedRows.Add($row) -or -not $ordinals.Add($ordinal)) { Throw-RequestSchemaError 'request_schema_ordinal_mapping_duplicate' }
        if ($row -eq $insertion) { $hasInsertion = $true }
    }
    if (-not $hasInsertion) { Throw-RequestSchemaError 'request_schema_ordinal_mapping_insertion_missing' }
    $fields = $root.Properties.fields; if ($fields.Kind -ne 'object') { Throw-RequestSchemaError 'request_schema_fields_object_required' }
    $allowedColumns = [System.Collections.Generic.HashSet[string]]::new([string[]](2..22 + 24 + 27 | ForEach-Object { [string]$_ }))
    foreach ($key in $fields.Properties.Keys) {
        if (-not $allowedColumns.Contains([string]$key)) { Throw-RequestSchemaError "request_schema_field_column_forbidden:$.fields.$key" }
    }
    $formulas = $root.Properties.formulas; Assert-ObjectKeys $formulas '$.formulas' @('y','z') @('y','z')
    foreach ($name in @('y','z')) { if (-not (Get-RequiredString $formulas.Properties[$name] "`$.formulas.$name").StartsWith('=')) { Throw-RequestSchemaError "request_schema_formula_r1c1_required:$name" } }
    $hyperlink = $root.Properties.hyperlink; Assert-ObjectKeys $hyperlink '$.hyperlink' @('address','display') @('address','display')
    [void](Get-RequiredString $hyperlink.Properties.address '$.hyperlink.address'); [void](Get-RequiredString $hyperlink.Properties.display '$.hyperlink.display')
    try { $data = $RequestJson | ConvertFrom-Json -ErrorAction Stop } catch { Throw-RequestSchemaError 'request_schema_json_invalid' }
    if ($BeforeCom) { & $BeforeCom $data }
    return $data
}

Set-Alias -Name Assert-WindowsExcelRequestSchema -Value Test-WindowsExcelRequestSchema
Export-ModuleMember -Function Test-WindowsExcelRequestSchema -Alias Assert-WindowsExcelRequestSchema
