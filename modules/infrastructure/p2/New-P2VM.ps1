#Requires -Version 5.1
#Requires -RunAsAdministrator
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
if (-not [Environment]::Is64BitProcess) { throw 'Use a fresh 64-bit administrator PowerShell with -NoProfile.' }
$systemHyperV = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::Windows)) 'System32\WindowsPowerShell\v1.0\Modules\Hyper-V'
$trustedModule = Get-Module -ListAvailable -Name $systemHyperV -ErrorAction Stop | Where-Object { $_.Path.StartsWith($systemHyperV + '\', [StringComparison]::OrdinalIgnoreCase) } | Sort-Object Version -Descending | Select-Object -First 1
if (-not $trustedModule) { throw 'The Windows system Hyper-V management module is unavailable.' }
Import-Module -Name $trustedModule.Path -ErrorAction Stop
Import-Module (Join-Path $PSScriptRoot 'P2VM.psm1') -Force -ErrorAction Stop
Invoke-P2VMPreparation @PSBoundParameters | ConvertTo-Json -Depth 4
