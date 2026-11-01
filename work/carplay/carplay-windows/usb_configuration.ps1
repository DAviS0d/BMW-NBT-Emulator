param([ValidateSet('Prepare','SelectCarPlay','StartService','Restore')][string]$Mode = 'Prepare')
$ErrorActionPreference = 'Stop'
$state = Join-Path $PSScriptRoot '..\playport\state'
New-Item -ItemType Directory -Force -Path $state | Out-Null
$backup = Join-Path $state 'windows-usb-backup.json'
$log = Join-Path $state 'windows-usb-configuration.log'
function Enable-CdcEnumerator($snapshot) {
    $driverKey = (Get-PnpDeviceProperty -InstanceId $snapshot.deviceId -KeyName DEVPKEY_Device_Driver).Data
    $software = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\' + $driverKey
    if (-not ($snapshot.PSObject.Properties.Name -contains 'cdcEnumerator')) {
        $properties = Get-ItemProperty -LiteralPath $software
        $saved = [ordered]@{ registry=$software; present=($properties.PSObject.Properties.Name -contains 'EnumeratorClass'); value=$properties.EnumeratorClass }
        $snapshot | Add-Member -NotePropertyName cdcEnumerator -NotePropertyValue $saved
        $snapshot | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $backup -Encoding UTF8
    }
    # Microsoft-documented WMCDC enumeration combines each NCM control/data pair.
    New-ItemProperty -LiteralPath $software -Name EnumeratorClass -PropertyType Binary -Value ([byte[]]@(2,0,0)) -Force | Out-Null
}
Start-Transcript -Path $log -Force | Out-Null
try {
    if (-not [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Administrator approval is required to select the iPhone USB configuration.'
    }
    if ($Mode -eq 'Prepare') {
        if (Test-Path -LiteralPath $backup) { throw 'An earlier USB configuration backup exists. Restore it before preparing again.' }
        $phones = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match '^USB\\VID_05AC&PID_12[A-Fa-f0-9]{2}\\' })
        if ($phones.Count -ne 1) { throw 'Connect exactly one iPhone before preparing wired CarPlay.' }
        $deviceId = $phones[0].InstanceId
        $registry = 'HKLM:\SYSTEM\CurrentControlSet\Enum\' + $deviceId + '\Device Parameters'
        $properties = Get-ItemProperty -LiteralPath $registry
        $service = Get-CimInstance Win32_Service -Filter "Name='Apple Mobile Device Service'"
        if (-not $service) { throw 'Apple Mobile Device Support is required.' }
        $snapshot = [pscustomobject][ordered]@{ deviceId=$deviceId; registry=$registry; values=@{}; serviceMode=$service.StartMode; serviceState=$service.State }
        foreach($name in @('OriginalConfigurationValue','AltConfigurationValue')) {
            if ($properties.PSObject.Properties.Name -contains $name) { $snapshot.values[$name] = $properties.$name }
        }
        $snapshot | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $backup -Encoding UTF8
        Enable-CdcEnumerator $snapshot
        New-ItemProperty -LiteralPath $registry -Name OriginalConfigurationValue -PropertyType DWord -Value 6 -Force | Out-Null
        New-ItemProperty -LiteralPath $registry -Name AltConfigurationValue -PropertyType DWord -Value 3 -Force | Out-Null
        if ($service.StartMode -eq 'Disabled') { Set-Service -Name 'Apple Mobile Device Service' -StartupType Manual }
        if ((Get-Service 'Apple Mobile Device Service').Status -eq 'Running') { Stop-Service -Name 'Apple Mobile Device Service' }
        try {
            & pnputil.exe /restart-device $deviceId
            $restartCode = $LASTEXITCODE
        } finally { Start-Service -Name 'Apple Mobile Device Service' }
        if ($restartCode -eq 3010) { Write-Output 'Windows requests a fresh connection. Unplug and reconnect the cable once.' }
        elseif ($restartCode -ne 0) { throw 'iPhone restart failed; use Restore to revert the saved settings.' }
        Write-Output 'Wired USB configuration prepared. Original settings saved for Restore.'
    } elseif ($Mode -eq 'StartService') {
        if (-not (Test-Path -LiteralPath $backup)) { throw 'Prepare must save the original service settings first.' }
        if ((Get-CimInstance Win32_Service -Filter "Name='Apple Mobile Device Service'").StartMode -eq 'Disabled') {
            Set-Service -Name 'Apple Mobile Device Service' -StartupType Manual
        }
        Start-Service -Name 'Apple Mobile Device Service'
        Write-Output 'Apple USB multiplexing service started.'
    } elseif ($Mode -eq 'SelectCarPlay') {
        if (-not (Test-Path -LiteralPath $backup)) { throw 'Prepare must save the original configuration first.' }
        $snapshot = Get-Content -LiteralPath $backup -Raw | ConvertFrom-Json
        Enable-CdcEnumerator $snapshot
        New-ItemProperty -LiteralPath $snapshot.registry -Name OriginalConfigurationValue -PropertyType DWord -Value 6 -Force | Out-Null
        Stop-Service -Name 'Apple Mobile Device Service'
        try {
            & pnputil.exe /restart-device $snapshot.deviceId
            $restartCode = $LASTEXITCODE
        } finally { Start-Service -Name 'Apple Mobile Device Service' }
        if ($restartCode -ne 0) { throw "iPhone restart returned $restartCode; reconnect the cable manually." }
        Write-Output 'CarPlay USB configuration value 6 selected.'
    } else {
        if (-not (Test-Path -LiteralPath $backup)) { throw 'No saved USB configuration to restore.' }
        $snapshot = Get-Content -LiteralPath $backup -Raw | ConvertFrom-Json
        if ($snapshot.PSObject.Properties.Name -contains 'cdcEnumerator') {
            if ($snapshot.cdcEnumerator.present) {
                New-ItemProperty -LiteralPath $snapshot.cdcEnumerator.registry -Name EnumeratorClass -PropertyType Binary -Value ([byte[]]$snapshot.cdcEnumerator.value) -Force | Out-Null
            } else {
                Remove-ItemProperty -LiteralPath $snapshot.cdcEnumerator.registry -Name EnumeratorClass -ErrorAction SilentlyContinue
            }
        }
        foreach($name in @('OriginalConfigurationValue','AltConfigurationValue')) {
            if ($snapshot.values.PSObject.Properties.Name -contains $name) {
                New-ItemProperty -LiteralPath $snapshot.registry -Name $name -PropertyType DWord -Value $snapshot.values.$name -Force | Out-Null
            } else {
                Remove-ItemProperty -LiteralPath $snapshot.registry -Name $name -ErrorAction SilentlyContinue
            }
        }
        if ($snapshot.serviceState -ne 'Running') { Stop-Service -Name 'Apple Mobile Device Service' -ErrorAction Stop }
        $startup = switch($snapshot.serviceMode) { 'Auto' { 'Automatic' }; 'Disabled' { 'Disabled' }; default { 'Manual' } }
        Set-Service -Name 'Apple Mobile Device Service' -StartupType $startup
        & pnputil.exe /restart-device $snapshot.deviceId
        if ($LASTEXITCODE -ne 0) { throw 'Original settings restored, but reconnect the iPhone manually. Backup retained.' }
        Remove-Item -LiteralPath $backup
        Write-Output 'Original Apple USB configuration and service settings restored.'
    }
} finally { Stop-Transcript | Out-Null }
