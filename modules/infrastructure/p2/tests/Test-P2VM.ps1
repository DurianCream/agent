[CmdletBinding()]
param([ValidateNotNullOrEmpty()][string]$EvidencePath)
$p2OriginalTemp = [Environment]::GetEnvironmentVariable('TEMP', 'Process')
$p2OriginalTmp = [Environment]::GetEnvironmentVariable('TMP', 'Process')
$p2OriginalErrorPreference = $ErrorActionPreference
$p2LoadedModule = $null
try {
$ErrorActionPreference = 'Stop'
if ($EvidencePath -and (Test-Path -LiteralPath $EvidencePath)) { throw 'Evidence output already exists; choose a new path.' }
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
$modulePath = Join-Path $PSScriptRoot '..\P2VM.psm1'
$wrapperPath = Join-Path $PSScriptRoot '..\New-P2VM.ps1'
$testRoot = Join-Path $root ('work\p2-host-isolation\host-tests-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($testRoot) | Out-Null
$env:TEMP = $testRoot; $env:TMP = $testRoot
$parseErrors = $null; $tokens = $null
$wrapperAst = [Management.Automation.Language.Parser]::ParseFile($wrapperPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Provisioning wrapper parse errors.' }
[Management.Automation.Language.Parser]::ParseFile($modulePath, [ref]$tokens, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count) { throw 'Provisioning module parse errors.' }
if (-not $wrapperAst.ScriptRequirements.IsElevationRequired) { throw 'Administrator requirement missing.' }
$p2LoadedModule = Import-Module $modulePath -Force -PassThru
$results = & $p2LoadedModule {
    param($TestRoot)
    $script:OriginalAncestor = (Get-Command Assert-P2ProtectedAncestors).ScriptBlock
    $script:OriginalSecurity = (Get-Command New-P2Security).ScriptBlock
    $script:OriginalNative = (Get-Command Invoke-P2ExclusiveDirectory).ScriptBlock
    $script:OriginalDriveGuard = (Get-Command Assert-P2NativeDrive).ScriptBlock
    $script:Results = [Collections.Generic.List[object]]::new()
    $script:Sequence = 0
    function script:Test-P2Administrator { return $script:Harness.Admin }
    function script:Assert-P2NativeDrive { param($Path); if($Path -match '^[ZS]:'){throw 'Mapped or SUBST drive rejected before IO.'} }
    function script:Get-P2NativeDevice { param($Drive); return $script:Harness.NativeDevice }
    function script:Get-P2NativeDriveType { param($Root); return 3 }
    function script:Get-PSDrive { [CmdletBinding()]param($Name,$PSProvider);return [pscustomobject]@{Root=$script:Harness.PsDriveRoot;Provider=[pscustomobject]@{Name='FileSystem'}} }
    function script:Assert-P2ProtectedAncestors { param($Path); if ($script:Harness.DenyAncestor) { throw 'Untrusted storage ancestor.' } }
    function script:Get-P2ExistingVM { param($VmName);$script:Harness.QueriedNames+=@($VmName);if ($script:Harness.ExistingVM) { return [pscustomobject]@{Name=$VmName} }; return $null }
    function script:Get-P2HostCapacity { return [pscustomobject]@{LogicalProcessors=$script:Harness.LogicalProcessors;PhysicalMemoryBytes=$script:Harness.PhysicalMemory} }
    function script:Get-P2FreeMemory {
        $index = [Math]::Min($script:Harness.MemoryReads, $script:Harness.Memory.Count - 1)
        $script:Harness.MemoryReads++; return $script:Harness.Memory[$index]
    }
    function script:Get-P2DiskFacts { param($Root); return [pscustomobject]@{DriveType=3;FreeSpace=$script:Harness.DiskFree} }
    function script:Get-VMSwitch { [CmdletBinding()]param($Name); return [pscustomobject]@{Name=$Name;Id=$script:Harness.SwitchId} }
    function script:New-P2ProtectedDirectory {
        param($Path)
        if ($script:Harness.CreateRace) { throw 'Exclusive protected directory creation failed with Win32 error 183.' }
        [IO.Directory]::CreateDirectory($Path) | Out-Null
    }
    function script:Copy-P2ProtectedMedia {
        param($Source,$Destination,$ExpectedSha256)
        [IO.File]::Copy($Source,$Destination,$false)
        if ($script:Harness.TamperCopy) { [IO.File]::WriteAllText($Destination,'altered fixture') }
    }
    function script:Protect-P2NewPath { param($Path,$VmSid,[switch]$VmWrite) }
    function script:Assert-P2ProtectedMedia { param($Path,$VmSid); if ($script:Harness.MediaDenied) { throw 'Unprotected media fixture.' } }
    function script:Get-P2VirtualMachineSid { param($Id); return 'S-1-5-83-0-1-2-3-4' }
    # These in-module functions shadow every Hyper-V management command. Tests
    # cannot fall through to a real VM operation, including on an admin host.
    function script:New-VM {
        [CmdletBinding()]param($Name,$Generation,$MemoryStartupBytes,$Path,$NewVHDPath,$NewVHDSizeBytes,$SwitchName)
        $script:Harness.Created++
        if ($script:Harness.ThrowNewVM) { throw 'Mock New-VM error after possible registration.' }
        $script:Harness.NewArgs = @($Name,$Generation,$MemoryStartupBytes,$NewVHDSizeBytes,$SwitchName)
        return [pscustomobject]@{Name=$Name;Id=[Guid]'11111111-1111-1111-1111-111111111111'}
    }
    function script:Set-VMProcessor { [CmdletBinding()]param($VM,$Count); if($script:Harness.FailConfigure){throw 'Mock configuration failure.'};$script:Harness.ConfiguredCpu=$Count }
    function script:Set-VMMemory { [CmdletBinding()]param($VM,$DynamicMemoryEnabled,$StartupBytes);$script:Harness.ConfiguredMemory=$StartupBytes }
    function script:Set-VM { [CmdletBinding()]param($VM,$AutomaticStartAction,$AutomaticStopAction,$AutomaticCheckpointsEnabled) }
    function script:Set-VMFirmware { [CmdletBinding()]param($VM,$EnableSecureBoot,$SecureBootTemplate,$FirstBootDevice);if($SecureBootTemplate){$script:Harness.ConfiguredTemplate=$SecureBootTemplate;$script:Harness.ConfiguredSecureBoot=$EnableSecureBoot} }
    function script:Add-VMDvdDrive { [CmdletBinding()]param($VM,$Path,[switch]$Passthru); return [pscustomobject]@{Path=$Path} }
    function script:Get-VM {
        [CmdletBinding()]param($Id)
        return [pscustomobject]@{Name=$script:Harness.NewArgs[0];Generation=2;ProcessorCount=$(if($script:Harness.BadReadback){$script:Harness.ConfiguredCpu+1}else{$script:Harness.ConfiguredCpu});MemoryStartup=$script:Harness.ConfiguredMemory;State=$script:Harness.State}
    }
    function script:Get-VMFirmware { [CmdletBinding()]param($VM);return [pscustomobject]@{SecureBoot=$(if($script:Harness.BadSecureBoot){'Off'}else{$script:Harness.ConfiguredSecureBoot});SecureBootTemplate=$(if($script:Harness.BadTemplate){'different_template'}else{$script:Harness.ConfiguredTemplate})} }
    function script:Get-VHD { [CmdletBinding()]param($Path); return [pscustomobject]@{Size=$script:Harness.NewArgs[3];VhdType='Dynamic'} }
    function script:Get-VMNetworkAdapter { [CmdletBinding()]param($VM); return [pscustomobject]@{SwitchId=$script:Harness.SwitchId} }
    function script:Start-VM { [CmdletBinding()]param($VM); $script:Harness.Started++;$script:Harness.State='Running' }
    function script:Get-Item {
        [CmdletBinding()]param($LiteralPath,[switch]$Force)
        if ($script:Harness.ReparsePath -eq $LiteralPath) { return [pscustomobject]@{Attributes=[IO.FileAttributes]::ReparsePoint} }
        return Microsoft.PowerShell.Management\Get-Item -LiteralPath $LiteralPath -Force:$Force
    }
    function script:Get-Acl {
        [CmdletBinding()]param($LiteralPath)
        if ($script:Harness.MockAcl) { return $script:Harness.MockAcl }
        return Microsoft.PowerShell.Security\Get-Acl -LiteralPath $LiteralPath
    }
    function script:Assert-P2Test { param([bool]$Condition,[string]$Message); if(-not $Condition){throw $Message} }
    function script:Expect-P2Failure {
        param([scriptblock]$Action,[string]$Text)
        $failed=$false
        try { & $Action | Out-Null } catch { $failed=$true; if($Text -and $_.Exception.Message -notlike ('*'+$Text+'*')){throw} }
        Assert-P2Test $failed 'Expected rejection did not occur.'
    }
    function script:Case-P2 {
        param([string]$Name,[scriptblock]$Action)
        $script:Sequence++
        $folder=Join-Path $TestRoot $script:Sequence
        [IO.Directory]::CreateDirectory($folder)|Out-Null
        $iso=Join-Path $folder 'fixture.iso';[IO.File]::WriteAllText($iso,'synthetic ISO bytes, never booted')
        $script:Harness=@{Admin=$true;ExistingVM=$false;QueriedNames=@();LogicalProcessors=10;PhysicalMemory=32GB;Memory=@(8GB);MemoryReads=0;DiskFree=100GB;SwitchId=[Guid]'22222222-2222-2222-2222-222222222222';Created=0;Started=0;NewArgs=$null;ConfiguredCpu=0;ConfiguredMemory=0;ConfiguredTemplate=$null;ConfiguredSecureBoot=$null;BadSecureBoot=$false;BadTemplate=$false;State='Off';FailConfigure=$false;ThrowNewVM=$false;TamperCopy=$false;DenyAncestor=$false;MediaDenied=$false;CreateRace=$false;BadReadback=$false;ReparsePath=$null;MockAcl=$null;NativeDevice='\Device\HarddiskVolume1';PsDriveRoot='C:\'}
        $script:P2Arguments=@{VmName='multi-p2-dev';OsName='FixtureOS';OsVersion='1.0.7';Architecture='amd64';SecureBootTemplate='MicrosoftUEFICertificateAuthority';CpuCount=2;MemoryGiB=4;DiskGiB=40;IsoPath=$iso;IsoSha256=(Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash;SwitchName='Chosen switch';VmPath=(Join-Path $folder 'multi-p2-dev');Confirm=$false}
        try { & $Action; $script:Results.Add([pscustomobject]@{name=$Name;outcome='passed'}) }
        catch { $script:Results.Add([pscustomobject]@{name=$Name;outcome='failed';detail=$_.Exception.Message}) }
    }
    Case-P2 'requires administrator before any effects' {
        $script:Harness.Admin=$false;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'elevated'
        Assert-P2Test ($script:Harness.Created -eq 0) 'VM created without admin.'
    }
    Case-P2 'WhatIf never creates storage or VM' {
        $result=Invoke-P2VMPreparation @script:P2Arguments -WhatIf
        Assert-P2Test ($result.status -eq 'planned_only' -and $script:Harness.Created -eq 0 -and -not(Test-Path -LiteralPath $script:P2Arguments.VmPath)) 'WhatIf had effects.'
    }
    Case-P2 'default creates only stopped exact VM' {
        $result=Invoke-P2VMPreparation @script:P2Arguments
        Assert-P2Test ($result.status -eq 'created_stopped' -and $script:Harness.Started -eq 0 -and $result.p2_isolation -eq 'not_configured') 'Unexpected deployment claim or start.'
        Assert-P2Test ($script:Harness.NewArgs[1] -eq 2 -and $script:Harness.NewArgs[2] -eq 4GB -and $script:Harness.NewArgs[3] -eq 40GB) 'Requested fixture resources were not preserved.'
    }
    Case-P2 'explicit Start checks resources and readback' {
        $result=Invoke-P2VMPreparation @script:P2Arguments -Start
        Assert-P2Test ($result.status -eq 'created_started_installer' -and $script:Harness.Started -eq 1 -and $result.guest_installation -eq 'not_run') 'Incorrect start or installation claim.'
    }
    Case-P2 'target metadata and hardware arguments are all mandatory' {
        $required=@('VmName','OsName','OsVersion','Architecture','SecureBootTemplate','CpuCount','MemoryGiB','DiskGiB')
        $command=Get-Command Invoke-P2VMPreparation
        foreach($name in $required){
            $attrs=@($command.Parameters[$name].Attributes|Where-Object{$_ -is [Management.Automation.ParameterAttribute] -and $_.Mandatory})
            Assert-P2Test ($attrs.Count -gt 0) "Required target parameter missing: $name"
        }
    }
    Case-P2 'declared OS and media do not certify installed guest' {
        $result=Invoke-P2VMPreparation @script:P2Arguments
        Assert-P2Test ($result.requested_guest.os_name -eq 'FixtureOS' -and $result.requested_guest.os_version -eq '1.0.7' -and $result.installed_guest -eq 'unverified' -and $result.guest_compatibility -eq 'unverified') 'Requested metadata was promoted to OS verification.'
        Assert-P2Test ($result.unsupported_guest_requirements -contains 'vTPM' -and $result.secure_boot -eq 'On') 'Unsupported requirements were hidden.'
    }
    Case-P2 'Windows template is selected only explicitly' {
        $script:P2Arguments.OsName='Windows Server';$script:P2Arguments.OsVersion='2022';$script:P2Arguments.SecureBootTemplate='MicrosoftWindows'
        $result=Invoke-P2VMPreparation @script:P2Arguments
        Assert-P2Test ($script:Harness.ConfiguredTemplate -eq 'MicrosoftWindows' -and $script:Harness.ConfiguredSecureBoot -eq 'On' -and $result.installed_guest -eq 'unverified') 'Explicit secure boot selection was not respected.'
    }
    Case-P2 'OS label does not guess a different boot template' {
        $script:P2Arguments.OsName='Windows Server';$script:P2Arguments.OsVersion='2022'
        $result=Invoke-P2VMPreparation @script:P2Arguments
        Assert-P2Test ($script:Harness.ConfiguredTemplate -eq 'MicrosoftUEFICertificateAuthority' -and $result.guest_compatibility -eq 'unverified') 'OS label implicitly changed boot policy.'
    }
    Case-P2 'explicit unique safe VM name drives exact query and path' {
        $script:P2Arguments.VmName='multi-p2-test-os-2';$script:P2Arguments.VmPath=Join-Path ([IO.Directory]::GetParent($script:P2Arguments.VmPath).FullName) $script:P2Arguments.VmName
        $result=Invoke-P2VMPreparation @script:P2Arguments
        Assert-P2Test ($result.vm_name -eq 'multi-p2-test-os-2' -and $script:Harness.NewArgs[0] -eq $result.vm_name -and @($script:Harness.QueriedNames|Where-Object{$_ -ne $result.vm_name}).Count -eq 0) 'A fixed VM name was reused.'
    }
    Case-P2 'unsafe or uppercase VM names rejected' {
        foreach($name in @('other-vm','multi-p2-UPPER','multi-p2-../escape',('multi-p2-'+('a'*41)))){
            $script:P2Arguments.VmName=$name;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'lowercase'
        }
        Assert-P2Test ($script:Harness.Created -eq 0) 'Unsafe VM name created.'
    }
    Case-P2 'floating OS version rejected' {$script:P2Arguments.OsVersion='latest';Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'concrete OS version'}
    Case-P2 'control characters in OS label rejected' {$script:P2Arguments.OsName="Fixture`nOS";Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'printable OS'}
    Case-P2 'unsupported architecture rejected without effects' {$script:P2Arguments.Architecture='arm64';Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments};Assert-P2Test ($script:Harness.Created -eq 0) 'Unsupported architecture used.'}
    Case-P2 'secure boot cannot be disabled by template' {$script:P2Arguments.SecureBootTemplate='Off';Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments};Assert-P2Test ($script:Harness.Created -eq 0) 'Secure boot downgrade allowed.'}
    Case-P2 'firmware disabled readback blocks start' {$script:Harness.BadSecureBoot=$true;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments -Start} 'firmware readback';Assert-P2Test ($script:Harness.Started -eq 0) 'Started with Secure Boot disabled.'}
    Case-P2 'firmware template readback mismatch blocks start' {$script:Harness.BadTemplate=$true;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments -Start} 'firmware readback';Assert-P2Test ($script:Harness.Started -eq 0) 'Started with wrong template.'}
    Case-P2 'selected resources replace prior fixed sizing' {
        $script:P2Arguments.CpuCount=4;$script:P2Arguments.MemoryGiB=8;$script:P2Arguments.DiskGiB=64
        $result=Invoke-P2VMPreparation @script:P2Arguments
        Assert-P2Test ($result.virtual_processors -eq 4 -and $result.memory_gib -eq 8 -and $result.vhd_capacity_gib -eq 64 -and $script:Harness.ConfiguredCpu -eq 4 -and $script:Harness.NewArgs[2] -eq 8GB -and $script:Harness.NewArgs[3] -eq 64GB) 'Requested sizing ignored.'
    }
    Case-P2 'CPU above host logical capacity rejected' {$script:P2Arguments.CpuCount=11;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'host logical capacity'}
    Case-P2 'RAM above physical capacity and reserve rejected' {$script:P2Arguments.MemoryGiB=32;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'physical host RAM'}
    Case-P2 'selected disk capacity includes ISO headroom' {$script:P2Arguments.DiskGiB=64;$script:Harness.DiskFree=64GB;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'disk capacity'}
    Case-P2 'selected RAM requires its own free-memory reserve' {$script:P2Arguments.MemoryGiB=8;$script:Harness.Memory=@(9GB);Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments -Start} '10 GiB';Assert-P2Test ($script:Harness.Created -eq 0) 'Wrong RAM reserve used.'}
    Case-P2 'existing VM is untouched' {
        $script:Harness.ExistingVM=$true;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'already exists'
        Assert-P2Test ($script:Harness.Created -eq 0) 'Existing VM was reused.'
    }
    Case-P2 'existing directory is untouched' {
        [IO.Directory]::CreateDirectory($script:P2Arguments.VmPath)|Out-Null
        $marker=Join-Path $script:P2Arguments.VmPath 'keep';[IO.File]::WriteAllText($marker,'unchanged')
        Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'already exists'
        Assert-P2Test ([IO.File]::ReadAllText($marker) -eq 'unchanged') 'Existing file changed.'
    }
    Case-P2 'relative destination rejected' {$script:P2Arguments.VmPath='work\multi-p2-dev';Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'fully qualified'}
    Case-P2 'mapped ISO rejected before source access' {$script:P2Arguments.IsoPath='Z:\image.iso';Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'before IO';Assert-P2Test ($script:Harness.Created -eq 0) 'Mapped ISO used.'}
    Case-P2 'SUBST storage rejected before target effects' {$script:P2Arguments.VmPath='S:\multi-p2-dev';Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'before IO';Assert-P2Test ($script:Harness.Created -eq 0) 'SUBST target used.'}
    Case-P2 'native mapping guard rejects SMB device' {$script:Harness.NativeDevice='\Device\LanmanRedirector\remote';Expect-P2Failure {& $script:OriginalDriveGuard -Path 'Z:\image.iso'} 'mapped network'}
    Case-P2 'native mapping guard rejects SUBST device' {$script:Harness.NativeDevice='\??\C:\user';Expect-P2Failure {& $script:OriginalDriveGuard -Path 'S:\multi-p2-dev'} 'SUBST'}
    Case-P2 'native mapping guard rejects PSDrive alias' {$script:Harness.PsDriveRoot='C:\other';Expect-P2Failure {& $script:OriginalDriveGuard -Path 'C:\multi-p2-dev'} 'PowerShell drive aliases'}
    Case-P2 'dot segments rejected' {$script:P2Arguments.VmPath='C:\something\..\multi-p2-dev';Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'dot segments'}
    Case-P2 'drive root rejected' {$script:P2Arguments.VmPath='C:\';Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'drive root'}
    Case-P2 'wrong directory leaf rejected' {$script:P2Arguments.VmPath=Join-Path ([IO.Directory]::GetParent($script:P2Arguments.VmPath).FullName) 'other';Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'leaf'}
    Case-P2 'wildcard switch rejected' {$script:P2Arguments.SwitchName='*';Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'exact existing'}
    Case-P2 'source ISO hash mismatch rejected' {$script:P2Arguments.IsoSha256='0'*64;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'SHA256 mismatch'}
    Case-P2 'copied ISO hash mismatch before VM creation' {
        $script:Harness.TamperCopy=$true;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'Copied ISO SHA256'
        Assert-P2Test ($script:Harness.Created -eq 0) 'Unverified media attached.'
    }
    Case-P2 'insufficient disk includes ISO and headroom' {$script:Harness.DiskFree=40GB;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'disk capacity'}
    Case-P2 'Start rejects initial low memory' {$script:Harness.Memory=@(2GB);Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments -Start} '6 GiB';Assert-P2Test ($script:Harness.Created -eq 0) 'Created before memory precheck.'}
    Case-P2 'memory decline preserves stopped new VM' {
        $script:Harness.Memory=@(8GB,2GB);Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments -Start} '6 GiB'
        Assert-P2Test ($script:Harness.Created -eq 1 -and $script:Harness.Started -eq 0 -and (Test-Path -LiteralPath $script:P2Arguments.VmPath)) 'Partial resource unexpectedly removed or started.'
    }
    Case-P2 'configuration failure never removes partial resources' {
        $script:Harness.FailConfigure=$true;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'configuration failure'
        Assert-P2Test ((Test-Path -LiteralPath $script:P2Arguments.VmPath) -and $script:Harness.Started -eq 0) 'Partial resource removed.'
    }
    Case-P2 'failed New-VM reports unknown instead of absent' {
        $script:Harness.ThrowNewVM=$true;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'unverified_check_multi-p2-dev'
        Assert-P2Test ($script:Harness.Created -eq 1 -and $script:Harness.Started -eq 0) 'Creation failure was mislabeled.'
    }
    Case-P2 'readback mismatch blocks start' {$script:Harness.BadReadback=$true;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments -Start} 'readback';Assert-P2Test ($script:Harness.Started -eq 0) 'Started bad VM.'}
    Case-P2 'unprotected media blocks start' {$script:Harness.MediaDenied=$true;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments -Start} 'Unprotected media';Assert-P2Test ($script:Harness.Started -eq 0) 'Started with writable media.'}
    Case-P2 'untrusted storage parent rejected' {$script:Harness.DenyAncestor=$true;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} 'Untrusted storage';Assert-P2Test ($script:Harness.Created -eq 0) 'Untrusted storage used.'}
    Case-P2 'reparse input rejected' {$script:Harness.ReparsePath=$script:P2Arguments.IsoPath;Expect-P2Failure {Assert-P2LocalPath -Path $script:P2Arguments.IsoPath -MustExist} 'reparse'}
    Case-P2 'exclusive create race rejects no reuse' {$script:Harness.CreateRace=$true;Expect-P2Failure {Invoke-P2VMPreparation @script:P2Arguments} '183';Assert-P2Test ($script:Harness.Created -eq 0) 'Raced path reused.'}
    Case-P2 'protected descriptors exist before creation' {
        $acl=& $script:OriginalSecurity -Directory $true
        Assert-P2Test ($acl.AreAccessRulesProtected -and $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -eq 'S-1-5-32-544') 'Descriptor ownership/protection wrong.'
        $rules=$acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])
        Assert-P2Test ($rules.Count -eq 2 -and @($rules | Where-Object {$_.IdentityReference.Value -notin @('S-1-5-32-544','S-1-5-18')}).Count -eq 0) 'Unexpected principal.'
    }
    Case-P2 'ancestor owner rejection uses real validator' {
        $acl=& $script:OriginalSecurity -Directory $true;$acl.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-21-1-2-3-1001'));$script:Harness.MockAcl=$acl
        Expect-P2Failure {& $script:OriginalAncestor -Path ([IO.Directory]::GetParent($script:P2Arguments.VmPath).FullName)} 'trusted administrator'
    }
    Case-P2 'ancestor delete-child grant rejected' {
        $acl=& $script:OriginalSecurity -Directory $true
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new('S-1-1-0'),'DeleteSubdirectoriesAndFiles','Allow'));$script:Harness.MockAcl=$acl
        Expect-P2Failure {& $script:OriginalAncestor -Path ([IO.Directory]::GetParent($script:P2Arguments.VmPath).FullName)} 'replacement'
    }
    Case-P2 'create-directory-only ancestor permission accepted' {
        $acl=& $script:OriginalSecurity -Directory $true
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new('S-1-1-0'),'CreateDirectories','Allow'));$script:Harness.MockAcl=$acl
        & $script:OriginalAncestor -Path ([IO.Directory]::GetParent($script:P2Arguments.VmPath).FullName)
    }
    Case-P2 'native exclusive create rejects existing directory unchanged' {
        $existing=[IO.Directory]::GetParent($script:P2Arguments.VmPath).FullName
        $before=(Microsoft.PowerShell.Security\Get-Acl -LiteralPath $existing).Sddl
        $acl=& $script:OriginalSecurity -Directory $true
        $errorCode=& $script:OriginalNative -Path $existing -SecurityDescriptor $acl.GetSecurityDescriptorBinaryForm()
        Assert-P2Test ($errorCode -eq 183) 'CreateDirectoryW did not reject the existing directory.'
        Assert-P2Test ((Microsoft.PowerShell.Security\Get-Acl -LiteralPath $existing).Sddl -eq $before) 'Existing ACL changed.'
    }
    return $script:Results.ToArray()
} $testRoot
$failed=@($results|Where-Object outcome -ne 'passed')
$evidence=[ordered]@{outcome=$(if($failed.Count){'failed'}else{'passed'});tests=$results.Count;passed=$results.Count-$failed.Count;checks=$results;parser='passed';administrator_requirement='present';actual_hyper_v_mutations='not_run';actual_vm_provisioning='not_run';method='In-process synthetic Hyper-V/security mocks; real parser and security-descriptor validation; real CreateDirectoryW existing-path rejection only. No actual VM, switch, host group, or existing ACL changes.'}
$json = $evidence | ConvertTo-Json -Depth 7
if ($EvidencePath) {
    # An explicit destination is create-new, including against a race after the
    # early check. Reusing this driver cannot overwrite a sealed prior result.
    $stream = [IO.FileStream]::new([IO.Path]::GetFullPath($EvidencePath), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json + "`n")
        $stream.Write($bytes, 0, $bytes.Length)
    } finally { $stream.Dispose() }
}
$json
if($failed.Count){throw "P2 mock suite failed: $($failed.Count) case(s)."}
} finally {
    try {
        if ($p2LoadedModule) { Remove-Module -ModuleInfo $p2LoadedModule -Force -ErrorAction Stop }
    } finally {
        [Environment]::SetEnvironmentVariable('TEMP', $p2OriginalTemp, 'Process')
        [Environment]::SetEnvironmentVariable('TMP', $p2OriginalTmp, 'Process')
        $ErrorActionPreference = $p2OriginalErrorPreference
    }
}
