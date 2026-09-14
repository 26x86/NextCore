#Requires -Version 5.1
<#
.SYNOPSIS
  Write an OpenCore + NextCore EFI tree to a USB stick (Windows).

.DESCRIPTION
  Two modes:

  * -DiskNumber <N> -Force   Erase the USB disk, create GPT with a FAT32 EFI System
                             Partition (default 512 MiB) plus an exFAT data partition
                             on the remaining space, then copy the EFI tree.
  * -EspRoot <X:\>           Copy the EFI tree onto an already mounted FAT32 volume
                             without repartitioning (repair / refresh).

  The EFI tree comes from tools\make_efi.py output (-EfiDir). When -EfiDir is not
  given, the script runs make_efi.py with -Profile into .\out\<profile>.

  Every copied file is re-hashed on the target and compared to MANIFEST.sha256.
  Booting to the picker is not a macOS boot; nothing here sets macos_boot_verified.

.PARAMETER List
  List removable USB disks and exit.

.PARAMETER DiskNumber
  Windows disk number (see -List or Get-Disk). Destructive; requires -Force.

.PARAMETER EspRoot
  Mounted FAT32 volume root (e.g. D:\) to receive the EFI tree. Non-destructive.

.PARAMETER EfiDir
  Directory containing EFI\ and MANIFEST.sha256 (make_efi.py output). Default: .\out\<Profile>.

.PARAMETER Profile
  make_efi.py profile used when -EfiDir does not exist yet. Default: generic-x64.

.PARAMETER EspSizeMB
  EFI System Partition size in MiB (default 512).

.PARAMETER Force
  Acknowledge that -DiskNumber erases the whole disk.

.EXAMPLE
  .\tools\make-usb.ps1 -List

.EXAMPLE
  .\tools\make-usb.ps1 -Profile 15igl7 -DiskNumber 2 -Force

.EXAMPLE
  .\tools\make-usb.ps1 -EfiDir .\out\15igl7 -EspRoot D:\
#>
[CmdletBinding(DefaultParameterSetName = 'List')]
param(
    [Parameter(ParameterSetName = 'List')]
    [switch]$List,

    [Parameter(ParameterSetName = 'Disk', Mandatory = $true)]
    [int]$DiskNumber,

    [Parameter(ParameterSetName = 'Esp', Mandatory = $true)]
    [string]$EspRoot,

    [string]$EfiDir,
    [string]$Profile = 'generic-x64',
    [int]$EspSizeMB = 512,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$MakeEfi = Join-Path $PSScriptRoot 'make_efi.py'

$GptEspType = '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}'
$GptBasicDataType = '{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}'

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-RemovableUsbDisks {
    Get-Disk | Where-Object {
        $removable = $false
        if ($_.PSObject.Properties.Match('MediaType').Count -gt 0) {
            $removable = ($_.MediaType -eq 'Removable Media')
        }
        ($_.BusType -eq 'USB') -or $removable
    }
}

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Resolve-EfiDir {
    if ($EfiDir) {
        $dir = (Resolve-Path -LiteralPath $EfiDir).Path
    } else {
        $dir = Join-Path $RepoRoot "out\$Profile"
        if (-not (Test-Path -LiteralPath (Join-Path $dir 'MANIFEST.sha256'))) {
            $python = Get-Command python -ErrorAction SilentlyContinue
            if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
            if (-not $python) { throw 'python not found; run tools\make_efi.py manually and pass -EfiDir.' }
            Write-Host "Generating EFI tree with profile '$Profile'..."
            & $python.Source $MakeEfi --profile $Profile --out $dir --force 2>&1 | Out-Host
            if ($LASTEXITCODE -ne 0) { throw "make_efi.py failed (exit $LASTEXITCODE)" }
        }
    }
    foreach ($required in @('EFI\BOOT\BOOTX64.EFI', 'EFI\OC\OpenCore.efi', 'EFI\OC\config.plist', 'EFI\NEXTCORE\BOOTX64.EFI', 'MANIFEST.sha256')) {
        if (-not (Test-Path -LiteralPath (Join-Path $dir $required))) {
            throw "EFI tree incomplete: missing $required under $dir"
        }
    }
    return $dir
}

function Read-Manifest([string]$Path) {
    $entries = [ordered]@{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $hash, $rel = $line -split '\s{2}', 2
        $entries[$rel.Trim().Replace('/', '\')] = $hash.Trim().ToLowerInvariant()
    }
    return $entries
}

function Copy-EfiTree([string]$SourceDir, [string]$TargetRoot) {
    $manifest = Read-Manifest (Join-Path $SourceDir 'MANIFEST.sha256')
    $targetEfi = Join-Path $TargetRoot 'EFI'
    if (Test-Path -LiteralPath $targetEfi) {
        Write-Host "Replacing existing $targetEfi"
        Remove-Item -LiteralPath $targetEfi -Recurse -Force
    }
    Copy-Item -LiteralPath (Join-Path $SourceDir 'EFI') -Destination $targetEfi -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $SourceDir 'MANIFEST.sha256') -Destination (Join-Path $TargetRoot 'MANIFEST.sha256') -Force

    $verified = [ordered]@{}
    foreach ($rel in $manifest.Keys) {
        $path = Join-Path $TargetRoot $rel
        $actual = Get-Sha256 $path
        if ($actual -ne $manifest[$rel]) {
            throw "Hash mismatch after copy: $rel (expected $($manifest[$rel]), got $actual)"
        }
        $verified[$rel] = $actual
    }
    return $verified
}

function Get-UsedDriveLetters {
    $letters = New-Object 'System.Collections.Generic.HashSet[char]'
    Get-Volume -ErrorAction SilentlyContinue | Where-Object DriveLetter | ForEach-Object { [void]$letters.Add([char]$_.DriveLetter) }
    Get-Partition -ErrorAction SilentlyContinue | Where-Object DriveLetter | ForEach-Object { [void]$letters.Add([char]$_.DriveLetter) }
    return $letters
}

function Get-NextDriveLetter([System.Collections.Generic.HashSet[char]]$Reserved) {
    $used = Get-UsedDriveLetters
    if ($Reserved) { foreach ($c in $Reserved) { [void]$used.Add($c) } }
    foreach ($c in ([char[]]([char]'D'..[char]'Z'))) {
        if (-not $used.Contains($c)) { return $c }
    }
    throw 'No free drive letters in D-Z.'
}

function Set-DriveLetter($Partition, [char]$Letter) {
    if ($Partition.DriveLetter -and ([char]$Partition.DriveLetter -ne $Letter)) {
        Remove-PartitionAccessPath -DiskNumber $Partition.DiskNumber -PartitionNumber $Partition.PartitionNumber `
            -AccessPath "$($Partition.DriveLetter):\" -ErrorAction SilentlyContinue
    }
    Set-Partition -DiskNumber $Partition.DiskNumber -PartitionNumber $Partition.PartitionNumber -NewDriveLetter $Letter | Out-Null
    return $Letter
}

function Initialize-GptDisk([int]$Number) {
    Clear-Disk -Number $Number -RemoveData -RemoveOEM -Confirm:$false
    $disk = Get-Disk -Number $Number
    switch ($disk.PartitionStyle) {
        'RAW' { Initialize-Disk -Number $Number -PartitionStyle GPT }
        'GPT' { }
        default {
            @("select disk $Number", 'clean', 'convert gpt', 'exit') -join "`n" | diskpart | Out-Null
            if ((Get-Disk -Number $Number).PartitionStyle -ne 'GPT') {
                throw "Could not convert disk $Number to GPT."
            }
        }
    }
}

function Write-Receipt([string]$SourceDir, [string]$Mode, [hashtable]$Result) {
    $receipt = [ordered]@{
        schema              = 'nextcore.usb-receipt/1'
        created_utc         = (Get-Date).ToUniversalTime().ToString('o')
        efi_dir             = $SourceDir
        mode                = $Mode
        macos_boot_verified = $false
        result              = $Result
    }
    $path = Join-Path $SourceDir 'usb-receipt.json'
    $receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $path -Encoding UTF8
    Write-Host "Receipt: $path"
}

# ----------------------------------------------------------------------------- modes

if ($PSCmdlet.ParameterSetName -eq 'List') {
    $disks = @(Get-RemovableUsbDisks)
    if ($disks.Count -eq 0) {
        Write-Host 'No removable USB disks detected.'
        return
    }
    $disks | Select-Object Number, FriendlyName, BusType, PartitionStyle,
        @{ Name = 'SizeGiB'; Expression = { [math]::Round($_.Size / 1GB, 2) } } | Format-Table -AutoSize
    return
}

$sourceDir = Resolve-EfiDir

if ($PSCmdlet.ParameterSetName -eq 'Esp') {
    $root = $EspRoot.TrimEnd('\') + '\'
    if (-not (Test-Path -LiteralPath $root)) { throw "ESP root not found: $root" }
    $volume = Get-Volume -FilePath $root -ErrorAction SilentlyContinue
    if ($volume -and $volume.FileSystem -notin @('FAT32', 'FAT')) {
        Write-Warning "Volume at $root is $($volume.FileSystem); firmware only boots an EFI tree from FAT32."
    }
    $verified = Copy-EfiTree -SourceDir $sourceDir -TargetRoot $root
    Write-Host "EFI tree applied to $root"
    $verified.GetEnumerator() | ForEach-Object { Write-Host ("  {0}  {1}" -f $_.Value.Substring(0, 16), $_.Key) }
    Write-Receipt -SourceDir $sourceDir -Mode 'esp' -Result @{ esp_root = $root; files = $verified }
    return
}

# Disk mode (destructive)
if (-not $Force) { throw 'Writing a disk is destructive. Re-run with -Force after backing up the USB stick.' }
if (-not (Test-Administrator)) { throw 'Partitioning requires an elevated (Administrator) PowerShell.' }

$disk = Get-Disk -Number $DiskNumber
if ($disk.IsBoot -or $disk.IsSystem) { throw "Refusing disk ${DiskNumber}: it is the boot/system disk." }
$mediaType = if ($disk.PSObject.Properties.Match('MediaType').Count -gt 0) { $disk.MediaType } else { 'unknown' }
if (($disk.BusType -ne 'USB') -and ($mediaType -ne 'Removable Media')) {
    throw "Disk $DiskNumber is not a removable USB disk (BusType=$($disk.BusType), MediaType=$mediaType)."
}
if ($disk.Size -lt (($EspSizeMB + 64) * 1MB)) { throw "Disk $DiskNumber is too small for a $EspSizeMB MiB ESP." }

Write-Warning ("About to ERASE disk {0}: {1} ({2} GiB). All data will be lost." -f $DiskNumber, $disk.FriendlyName, [math]::Round($disk.Size / 1GB, 2))
Start-Sleep -Seconds 3

Initialize-GptDisk -Number $DiskNumber
$espPart = New-Partition -DiskNumber $DiskNumber -Size ($EspSizeMB * 1MB) -GptType $GptEspType
$espLetter = Set-DriveLetter $espPart (Get-NextDriveLetter $null)
Format-Volume -DriveLetter $espLetter -FileSystem FAT32 -NewFileSystemLabel 'NEXTCORE' -Confirm:$false | Out-Null

$dataLetter = $null
$remaining = (Get-Disk -Number $DiskNumber).LargestFreeExtent
if ($remaining -gt 64MB) {
    $dataPart = New-Partition -DiskNumber $DiskNumber -UseMaximumSize -GptType $GptBasicDataType
    $reserved = [System.Collections.Generic.HashSet[char]]::new()
    [void]$reserved.Add([char]$espLetter)
    $dataLetter = Set-DriveLetter $dataPart (Get-NextDriveLetter $reserved)
    Format-Volume -DriveLetter $dataLetter -FileSystem exFAT -NewFileSystemLabel 'NEXTCORE_DATA' -Confirm:$false | Out-Null
}

$espRoot = "${espLetter}:\"
$verified = Copy-EfiTree -SourceDir $sourceDir -TargetRoot $espRoot

$summary = "USB ready. ESP: $espRoot"
if ($dataLetter) { $summary += "  Data: ${dataLetter}:\" }
Write-Host $summary
$verified.GetEnumerator() | ForEach-Object { Write-Host ("  {0}  {1}" -f $_.Value.Substring(0, 16), $_.Key) }
Write-Host 'Firmware: disable Secure Boot, boot the USB in UEFI mode, pick "NextCore Picker" in OpenCore.'

Write-Receipt -SourceDir $sourceDir -Mode 'disk' -Result @{
    disk_number = $DiskNumber
    disk_name   = $disk.FriendlyName
    esp_root    = $espRoot
    data_root   = $(if ($dataLetter) { "${dataLetter}:\" } else { $null })
    files       = $verified
}
