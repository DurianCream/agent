Set-StrictMode -Version Latest

function Test-P2Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-P2NativeDevice {
    param([string]$Drive)
    Initialize-P2Native
    return [MultiP2.ExclusiveDirectory]::Device($Drive)
}

function Get-P2NativeDriveType {
    param([string]$Root)
    Initialize-P2Native
    return [MultiP2.ExclusiveDirectory]::DriveType($Root)
}

function Assert-P2NativeDrive {
    param([string]$Path)
    $drive = $Path.Substring(0, 2).ToUpperInvariant()
    $device = Get-P2NativeDevice -Drive $drive
    if ($device -notmatch '^\\Device\\HarddiskVolume[0-9]+$') { throw 'P2 rejects mapped network, SUBST and non-native drive aliases before filesystem access.' }
    if ((Get-P2NativeDriveType -Root ($drive + '\')) -ne 3) { throw 'P2 requires a native fixed local drive.' }
    $psDrive = Get-PSDrive -Name $drive.Substring(0, 1) -PSProvider FileSystem -ErrorAction Stop
    if ($psDrive.Provider.Name -ne 'FileSystem' -or $psDrive.Root.TrimEnd('\', '/') -ne $drive) { throw 'P2 rejects PowerShell drive aliases.' }
}

function Assert-P2LocalPath {
    param([Parameter(Mandatory)][string]$Path, [switch]$MustExist)
    if ($Path -notmatch '^[A-Za-z]:[\\/]' -or $Path -match '[\x00-\x1f]' -or $Path.Substring(2).Contains(':')) {
        throw 'P2 requires a fully qualified local drive path without alternate streams.'
    }
    if (($Path -split '[\\/]') -contains '..' -or ($Path -split '[\\/]') -contains '.') {
        throw 'P2 paths cannot contain dot segments.'
    }
    Assert-P2NativeDrive -Path $Path
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    if ($full.Length -le 3) { throw 'A drive root is not a P2 resource path.' }
    if ($MustExist -and -not (Test-Path -LiteralPath $full)) { throw 'Required P2 path does not exist.' }
    $cursor = $full
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'P2 paths cannot traverse reparse points.' }
        }
        $parent = [IO.Directory]::GetParent($cursor)
        $cursor = if ($parent) { $parent.FullName } else { $null }
    }
    return $full
}

function Get-P2ExistingVM {
    param([Parameter(Mandatory)][string]$VmName)
    try { return Get-VM -Name $VmName -ErrorAction Stop }
    catch {
        if ($_.CategoryInfo.Category -eq [Management.Automation.ErrorCategory]::ObjectNotFound) { return $null }
        throw
    }
}

function Get-P2HostCapacity {
    $computer = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
    return [pscustomobject]@{LogicalProcessors=[int]$computer.NumberOfLogicalProcessors;PhysicalMemoryBytes=[uint64]$computer.TotalPhysicalMemory}
}

function Get-P2FreeMemory {
    return [uint64](Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop).FreePhysicalMemory * 1KB
}

function Get-P2DiskFacts {
    param([string]$Root)
    $device = $Root.Substring(0, 2)
    return Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='$device'" -ErrorAction Stop
}

function Assert-P2ProtectedAncestors {
    param([string]$Path)
    $trusted = @('S-1-5-32-544', 'S-1-5-18', 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')
    $forbidden = [Security.AccessControl.FileSystemRights]'WriteData, WriteAttributes, WriteExtendedAttributes, DeleteSubdirectoriesAndFiles, Delete, ChangePermissions, TakeOwnership'
    $cursor = if (Test-Path -LiteralPath $Path) { $Path } else { [IO.Directory]::GetParent($Path).FullName }
    while ($cursor) {
        $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Protected storage traverses a reparse point.' }
        $acl = Get-Acl -LiteralPath $cursor -ErrorAction Stop
        if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) { throw 'P2 storage ancestors must have a trusted administrator/System owner.' }
        foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
            if ($rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) { continue }
            if ($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -notin $trusted -and ($rule.FileSystemRights -band $forbidden)) {
                throw 'P2 storage ancestor permits untrusted replacement or modification.'
            }
        }
        $parent = [IO.Directory]::GetParent($cursor)
        $cursor = if ($parent) { $parent.FullName } else { $null }
    }
}

function New-P2Security {
    param([bool]$Directory, [string]$VmSid, [switch]$VmWrite)
    $acl = if ($Directory) { [Security.AccessControl.DirectorySecurity]::new() } else { [Security.AccessControl.FileSecurity]::new() }
    $acl.SetAccessRuleProtection($true, $false)
    $admin = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
    $system = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    $acl.SetOwner($admin)
    $inherit = if ($Directory) { [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit' } else { [Security.AccessControl.InheritanceFlags]::None }
    foreach ($sid in @($admin, $system)) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid, 'FullControl', $inherit, 'None', 'Allow'))
    }
    if ($VmSid) {
        $rights = if ($VmWrite) { 'Modify' } else { 'ReadAndExecute' }
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new($VmSid), $rights, 'None', 'None', 'Allow'))
    }
    return $acl
}

function Initialize-P2Native {
    if (-not ('MultiP2.ExclusiveDirectory' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
namespace MultiP2 {
    public static class ExclusiveDirectory {
        [StructLayout(LayoutKind.Sequential)]
        private struct SecurityAttributes {
            public int Length;
            public IntPtr Descriptor;
            public int Inherit;
        }
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool CreateDirectoryW(string path, ref SecurityAttributes attributes);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        private static extern uint QueryDosDeviceW(string drive, StringBuilder target, int capacity);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode)]
        private static extern uint GetDriveTypeW(string root);
        public static string Device(string drive) {
            var buffer = new StringBuilder(2048);
            if (QueryDosDeviceW(drive, buffer, buffer.Capacity) == 0)
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            return buffer.ToString().Split('\0')[0];
        }
        public static uint DriveType(string root) { return GetDriveTypeW(root); }
        public static int Create(string path, byte[] descriptor) {
            var pinned = GCHandle.Alloc(descriptor, GCHandleType.Pinned);
            try {
                var attributes = new SecurityAttributes {
                    Length = Marshal.SizeOf(typeof(SecurityAttributes)),
                    Descriptor = pinned.AddrOfPinnedObject(), Inherit = 0
                };
                return CreateDirectoryW(path, ref attributes) ? 0 : Marshal.GetLastWin32Error();
            } finally { pinned.Free(); }
        }
    }
}
'@ -ErrorAction Stop
    }
}

function Invoke-P2ExclusiveDirectory {
    param([string]$Path, [byte[]]$SecurityDescriptor)
    Initialize-P2Native
    return [MultiP2.ExclusiveDirectory]::Create($Path, $SecurityDescriptor)
}

function New-P2ProtectedDirectory {
    param([string]$Path)
    Assert-P2LocalPath -Path $Path | Out-Null
    Assert-P2ProtectedAncestors -Path $Path
    if (Test-Path -LiteralPath $Path) { throw 'The new protected directory already exists.' }
    $acl = New-P2Security -Directory $true
    $errorCode = Invoke-P2ExclusiveDirectory -Path $Path -SecurityDescriptor $acl.GetSecurityDescriptorBinaryForm()
    if ($errorCode -ne 0) { throw "Exclusive protected directory creation failed with Win32 error $errorCode; no existing directory is reused." }
    $actual = Get-Acl -LiteralPath $Path -ErrorAction Stop
    if (-not $actual.AreAccessRulesProtected -or $actual.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne 'S-1-5-32-544') { throw 'New storage was not atomically created with protected ownership.' }
    Assert-P2ProtectedAncestors -Path $Path
}

function Copy-P2ProtectedMedia {
    param([string]$Source, [string]$Destination, [string]$ExpectedSha256)
    Assert-P2LocalPath -Path $Source -MustExist | Out-Null
    Assert-P2LocalPath -Path $Destination | Out-Null
    Assert-P2ProtectedAncestors -Path $Destination
    $mediaInput = $null; $mediaOutput = $null; $hasher = $null
    try {
        $mediaInput = [IO.FileStream]::new($Source, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        $acl = New-P2Security -Directory $false
        if ($PSVersionTable.PSEdition -eq 'Core') {
            $mediaOutput = [IO.FileSystemAclExtensions]::Create([IO.FileInfo]::new($Destination), [IO.FileMode]::CreateNew, [Security.AccessControl.FileSystemRights]::ReadWrite, [IO.FileShare]::None, 65536, [IO.FileOptions]::SequentialScan, $acl)
        } else {
            $mediaOutput = [IO.FileStream]::new($Destination, [IO.FileMode]::CreateNew, [Security.AccessControl.FileSystemRights]::ReadWrite, [IO.FileShare]::None, 65536, [IO.FileOptions]::SequentialScan, $acl)
        }
        $mediaInput.CopyTo($mediaOutput); $mediaOutput.Flush($true); $mediaOutput.Position = 0
        $hasher = [Security.Cryptography.SHA256]::Create()
        $actual = ([BitConverter]::ToString($hasher.ComputeHash($mediaOutput))).Replace('-', '').ToLowerInvariant()
        if ($actual -ne $ExpectedSha256) { throw 'Copied ISO SHA256 mismatch.' }
    } finally {
        if ($hasher) { $hasher.Dispose() }; if ($mediaOutput) { $mediaOutput.Dispose() }; if ($mediaInput) { $mediaInput.Dispose() }
    }
}

function Protect-P2NewPath {
    param([string]$Path, [string]$VmSid, [switch]$VmWrite)
    # Initial storage/media creation already had a protected descriptor. This
    # only grants the newly created VM its exact read or disk-write permissions.
    Assert-P2LocalPath -Path $Path -MustExist | Out-Null
    Assert-P2ProtectedAncestors -Path ([IO.Directory]::GetParent($Path).FullName)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    $acl = New-P2Security -Directory ([bool]$item.PSIsContainer) -VmSid $VmSid -VmWrite:$VmWrite
    Set-Acl -LiteralPath $Path -AclObject $acl -ErrorAction Stop
}

function Get-P2VirtualMachineSid {
    param([Guid]$Id)
    return ([Security.Principal.NTAccount]::new('NT VIRTUAL MACHINE', $Id.ToString())).Translate([Security.Principal.SecurityIdentifier]).Value
}

function Assert-P2ProtectedMedia {
    param([string]$Path, [string]$VmSid)
    $acl = Get-Acl -LiteralPath $Path -ErrorAction Stop
    Assert-P2LocalPath -Path $Path -MustExist | Out-Null
    Assert-P2ProtectedAncestors -Path ([IO.Directory]::GetParent($Path).FullName)
    $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($owner -ne 'S-1-5-32-544' -or -not $acl.AreAccessRulesProtected) { throw 'P2 copied media is not administrator-controlled.' }
    $allowed = @('S-1-5-32-544', 'S-1-5-18', $VmSid)
    $vmRead = $false
    foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        if ($rule.AccessControlType -ne 'Allow' -or $rule.IdentityReference.Value -notin $allowed) { throw 'Unexpected P2 media access rule.' }
        if ($rule.IdentityReference.Value -eq $VmSid) {
            $forbidden = [Security.AccessControl.FileSystemRights]'Write, Delete, ChangePermissions, TakeOwnership'
            if ($rule.FileSystemRights -band $forbidden) { throw 'The VM can modify its installation media.' }
            $vmRead = ($rule.FileSystemRights -band [Security.AccessControl.FileSystemRights]::ReadAndExecute) -eq [Security.AccessControl.FileSystemRights]::ReadAndExecute
        }
    }
    if (-not $vmRead) { throw 'The VM cannot read its pinned installation media.' }
}

function Invoke-P2VMPreparation {
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact='Medium')]
    param(
        [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$VmName,
        [Parameter(Mandatory)][ValidateLength(1,80)][string]$OsName,
        [Parameter(Mandatory)][ValidateLength(1,80)][string]$OsVersion,
        [Parameter(Mandatory)][ValidateSet('amd64')][string]$Architecture,
        [Parameter(Mandatory)][ValidateSet('MicrosoftWindows','MicrosoftUEFICertificateAuthority')][string]$SecureBootTemplate,
        [Parameter(Mandatory)][ValidateRange(1,64)][int]$CpuCount,
        [Parameter(Mandatory)][ValidateRange(1,128)][int]$MemoryGiB,
        [Parameter(Mandatory)][ValidateRange(8,256)][int]$DiskGiB,
        [Parameter(Mandatory)][string]$IsoPath,
        [Parameter(Mandatory)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$IsoSha256,
        [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$SwitchName,
        [Parameter(Mandatory)][string]$VmPath,
        [switch]$Start
    )
    $ErrorActionPreference = 'Stop'
    if (-not (Test-P2Administrator)) { throw 'Run the reviewed provisioning script in an elevated administrator PowerShell.' }
    if (-not [regex]::IsMatch($VmName, '^multi-p2-[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$', [Text.RegularExpressions.RegexOptions]::CultureInvariant)) { throw 'Use a lowercase multi-p2- VM name with a 1..40 character safe alphanumeric/hyphen suffix.' }
    foreach ($label in @($OsName, $OsVersion)) {
        if ([string]::IsNullOrWhiteSpace($label) -or $label -ne $label.Trim() -or $label -match '[\p{C}\p{Zl}\p{Zp}*?]') { throw 'Provide explicit printable OS name and version labels without wildcard/control characters.' }
    }
    if ($OsVersion -in @('latest','current','any','unknown')) { throw 'Provide a concrete OS version or build, not a floating label.' }
    $memoryBytes = [uint64]$MemoryGiB * 1GB
    $diskBytes = [uint64]$DiskGiB * 1GB
    $requiredFreeMemory = $memoryBytes + 2GB
    $capacity = Get-P2HostCapacity
    if (-not $capacity -or $capacity.LogicalProcessors -lt 1 -or $CpuCount -gt $capacity.LogicalProcessors) { throw 'Requested CPU count exceeds verified host logical capacity.' }
    if ($capacity.PhysicalMemoryBytes -lt $requiredFreeMemory) { throw 'Requested memory plus 2 GiB headroom exceeds verified physical host RAM.' }
    if ($SwitchName.Length -gt 256 -or $SwitchName -match '[\x00-\x1f*?\[\]]') { throw 'Choose one exact existing switch name.' }
    $iso = Assert-P2LocalPath -Path $IsoPath -MustExist
    $target = Assert-P2LocalPath -Path $VmPath
    if ([IO.Path]::GetFileName($target) -ne $VmName) { throw 'The new VM directory leaf must match the exact requested VM name.' }
    if (Test-Path -LiteralPath $target) { throw 'The VM directory already exists; never reuse or delete it automatically.' }
    $parent = [IO.Directory]::GetParent($target).FullName
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) { throw 'Choose an existing local parent directory.' }
    Assert-P2ProtectedAncestors -Path $parent
    $image = Get-Item -LiteralPath $iso -Force
    if ($image.PSIsContainer -or $image.Extension -ne '.iso' -or $image.Length -le 0) { throw 'A nonempty ISO file is required.' }
    $expected = $IsoSha256.ToLowerInvariant()
    if ((Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Source ISO SHA256 mismatch.' }
    if (Get-P2ExistingVM -VmName $VmName) { throw 'The requested VM already exists; no existing VM will be changed.' }
    $switches = @(Get-VMSwitch -Name $SwitchName -ErrorAction Stop)
    if ($switches.Count -ne 1 -or $switches[0].Name -ne $SwitchName) { throw 'The exact selected switch was not found.' }
    $switchId = [Guid]$switches[0].Id
    $disk = Get-P2DiskFacts -Root $target
    $requiredDisk = [uint64]($diskBytes + 2GB + $image.Length)
    if (-not $disk -or $disk.DriveType -ne 3 -or [uint64]$disk.FreeSpace -lt $requiredDisk) { throw 'Insufficient fixed-disk capacity for VHD capacity, copied ISO and headroom.' }
    if ($Start -and (Get-P2FreeMemory) -lt $requiredFreeMemory) { throw "At least $($MemoryGiB + 2) GiB free host RAM is required before starting this VM." }
    $vhd = Join-Path $target 'disks\os.vhdx'
    $media = Join-Path $target 'media\installer.iso'
    $summary = [ordered]@{ preparation_api_version='0.2.0'; vm_name=$VmName; requested_guest=[ordered]@{os_name=$OsName;os_version=$OsVersion;architecture=$Architecture}; installed_guest='unverified'; guest_compatibility='unverified'; generation=2; secure_boot='On'; secure_boot_template=$SecureBootTemplate; unsupported_guest_requirements=@('vTPM','legacy_BIOS','non_amd64'); virtual_processors=$CpuCount; memory_gib=$MemoryGiB; vhd_capacity_gib=$DiskGiB; vhd_type='Dynamic'; vm_path=$target; switch_name=$SwitchName; switch_id=$switchId.ToString(); iso_sha256=$expected; guest_installation='not_run'; p2_isolation='not_configured' }
    if (-not $PSCmdlet.ShouldProcess($target, "Create only new VM $VmName and its new owned storage for the declared test request")) {
        $summary['status'] = 'planned_only'; return [pscustomobject]$summary
    }
    # Recheck targets immediately before effects. No deletion or fallback reuse.
    Assert-P2LocalPath -Path $target | Out-Null
    Assert-P2ProtectedAncestors -Path $parent
    if ((Test-Path -LiteralPath $target) -or (Get-P2ExistingVM -VmName $VmName)) { throw 'The new VM target appeared after preflight.' }
    $nowSwitch = @(Get-VMSwitch -Name $SwitchName -ErrorAction Stop)
    if ($nowSwitch.Count -ne 1 -or [Guid]$nowSwitch[0].Id -ne $switchId) { throw 'The selected switch changed after preflight.' }
    $created = $null
    try {
        New-P2ProtectedDirectory -Path $target
        foreach ($name in @('media', 'disks')) {
            $folder = Join-Path $target $name
            New-P2ProtectedDirectory -Path $folder
        }
        Copy-P2ProtectedMedia -Source $iso -Destination $media -ExpectedSha256 $expected
        if ((Get-FileHash -LiteralPath $media -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Copied ISO SHA256 mismatch.' }
        $created = New-VM -Name $VmName -Generation 2 -MemoryStartupBytes $memoryBytes -Path $target -NewVHDPath $vhd -NewVHDSizeBytes $diskBytes -SwitchName $SwitchName -ErrorAction Stop
        if (-not $created -or $created.Name -ne $VmName) { throw 'Unexpected new VM identity.' }
        $vmSid = Get-P2VirtualMachineSid -Id $created.Id
        Protect-P2NewPath -Path $target -VmSid $vmSid
        Protect-P2NewPath -Path (Join-Path $target 'media') -VmSid $vmSid
        Protect-P2NewPath -Path (Join-Path $target 'disks') -VmSid $vmSid
        Protect-P2NewPath -Path $media -VmSid $vmSid
        Protect-P2NewPath -Path $vhd -VmSid $vmSid -VmWrite
        Assert-P2ProtectedMedia -Path $media -VmSid $vmSid
        Set-VMProcessor -VM $created -Count $CpuCount -ErrorAction Stop
        Set-VMMemory -VM $created -DynamicMemoryEnabled $false -StartupBytes $memoryBytes -ErrorAction Stop
        Set-VM -VM $created -AutomaticStartAction Nothing -AutomaticStopAction ShutDown -AutomaticCheckpointsEnabled $false -ErrorAction Stop
        Set-VMFirmware -VM $created -EnableSecureBoot On -SecureBootTemplate $SecureBootTemplate -ErrorAction Stop
        $dvd = Add-VMDvdDrive -VM $created -Path $media -Passthru -ErrorAction Stop
        Set-VMFirmware -VM $created -FirstBootDevice $dvd -ErrorAction Stop
        $current = Get-VM -Id $created.Id -ErrorAction Stop
        $firmware = Get-VMFirmware -VM $created -ErrorAction Stop
        $virtualDisk = Get-VHD -Path $vhd -ErrorAction Stop
        $network = @(Get-VMNetworkAdapter -VM $created -ErrorAction Stop)
        if ($current.Name -ne $VmName -or $current.Generation -ne 2 -or $current.ProcessorCount -ne $CpuCount -or $current.MemoryStartup -ne $memoryBytes -or [string]$current.State -ne 'Off' -or $virtualDisk.Size -ne $diskBytes -or [string]$virtualDisk.VhdType -ne 'Dynamic' -or $network.Count -ne 1 -or [Guid]$network[0].SwitchId -ne $switchId) { throw 'New VM readback differs from the requested configuration.' }
        if ([string]$firmware.SecureBoot -ne 'On' -or $firmware.SecureBootTemplate -ne $SecureBootTemplate) { throw 'Secure Boot firmware readback differs from the explicit requested policy.' }
        $summary['vm_id'] = $created.Id.ToString()
        $summary['status'] = 'created_stopped'
        if ($Start) {
            if ((Get-P2FreeMemory) -lt $requiredFreeMemory) { throw "Free RAM fell below $($MemoryGiB + 2) GiB; the new VM remains stopped." }
            Assert-P2ProtectedMedia -Path $media -VmSid $vmSid
            if ((Get-FileHash -LiteralPath $media -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Copied ISO changed before start.' }
            $firmware = Get-VMFirmware -VM $created -ErrorAction Stop
            if ([string]$firmware.SecureBoot -ne 'On' -or $firmware.SecureBootTemplate -ne $SecureBootTemplate) { throw 'Secure Boot firmware changed before start.' }
            if ($PSCmdlet.ShouldProcess($created.Id.ToString(), 'Start the new VM installer; guest isolation is not yet configured')) {
                Start-VM -VM $created -ErrorAction Stop | Out-Null
                if ([string](Get-VM -Id $created.Id -ErrorAction Stop).State -ne 'Running') { throw 'New VM did not report Running.' }
                $summary['status'] = 'created_started_installer'
            }
        }
        return [pscustomobject]$summary
    } catch {
        $id = if ($created) { $created.Id.ToString() } else { "unverified_check_$VmName" }
        throw "P2 preparation failed (new VM ID: $id). A partial new VM and task-owned storage may remain at the approved path. No existing VM or file was deleted. Inspect the error and new resources before retrying. Cause: $($_.Exception.Message)"
    }
}

Export-ModuleMember -Function Invoke-P2VMPreparation
