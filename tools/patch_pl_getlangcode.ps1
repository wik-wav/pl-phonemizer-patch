<#
.SYNOPSIS
  Add a GetLangCode() override returning a language code (default "pl") to DIFF_PL_phonemiser.dll.

.DESCRIPTION
  The plugin (DiffSingerPolishPhonemizer : DiffSingerG2pPhonemizer) overrides GetDictionaryName /
  LoadBaseG2p / GetBaseG2pVowels / GetBaseG2pConsonants but NOT GetLangCode(), so DiffSingerG2pPhonemizer
  .LoadG2p never builds the "<lang>/<phone>" replacements and the plugin emits BARE phone names.
  Those bare names collide with English phonetic hints under ValidatePhoneme's bare-first resolution.

  This script adds a one-method override (ldstr "<lang>"; ret) with Mono.Cecil. The plugin's data
  (the g2p-pl manifest resource: dict.txt / phones.txt / g2p.onnx) is NEVER touched - the rename is
  done by G2pRemapper, driven by GetLangCode().

  A verify gate runs before anything is written: the candidate is re-read with Cecil (method body,
  override flags, original methods intact) and its g2p-pl resource is read back through
  ResourceReader. On any failure nothing is written.

.PARAMETER DllPath
  Path to the ORIGINAL DIFF_PL_phonemiser.dll (unpatched; a file whose DiffSingerPolishPhonemizer
  has no GetLangCode method).

.PARAMETER OutPath
  Where to write the patched DLL. Defaults to "<DllPath directory>\DIFF_PL_phonemiser.pl-prefix.dll".

.PARAMETER LangCode
  Language code the plugin should report. Default "pl".

.PARAMETER CecilDir
  Where Mono.Cecil lives / will be fetched to. Default: "<script dir>\..\.cecil".

.PARAMETER Install
  Also back up the original and replace it in place (for an OpenUtau Plugins folder).

.EXAMPLE
  .\patch_pl_getlangcode.ps1 -DllPath .\dll\DIFF_PL_phonemiser.original.dll

.EXAMPLE
  .\patch_pl_getlangcode.ps1 -DllPath "<OpenUtau>\Plugins\DIFF_PL_phonemiser.dll" -Install
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DllPath,
    [string]$OutPath,
    [string]$LangCode = "pl",
    [string]$CecilDir,
    [switch]$Install
)
$ErrorActionPreference = 'Stop'

# $PSScriptRoot is not reliably set inside param() defaults (Windows PowerShell 5.1) - resolve here.
if (-not $CecilDir) {
    $scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
    $CecilDir = Join-Path (Split-Path -Parent $scriptDir) ".cecil"
}

if (-not (Test-Path $DllPath)) { throw "DLL not found: $DllPath" }
if (-not $OutPath) { $OutPath = Join-Path (Split-Path -Parent (Resolve-Path $DllPath)) "DIFF_PL_phonemiser.pl-prefix.dll" }

# ---- Mono.Cecil: fetch if missing, then load from a byte array (a plain LoadFrom/Add-Type is
# ---- blocked with 0x80131515 on downloaded files; the byte load bypasses the zone check).
$cecil = Join-Path $CecilDir "Mono.Cecil.dll"
if (-not (Test-Path $cecil)) {
    Write-Host "fetching Mono.Cecil 0.11.5 -> $CecilDir"
    New-Item -ItemType Directory -Force -Path $CecilDir | Out-Null
    $nupkg = Join-Path $CecilDir "cecil.nupkg"
    Invoke-WebRequest -Uri "https://www.nuget.org/api/v2/package/Mono.Cecil/0.11.5" -OutFile $nupkg -UseBasicParsing
    $zip = Join-Path $CecilDir "cecil.zip"
    Copy-Item $nupkg $zip -Force
    Expand-Archive -Path $zip -DestinationPath (Join-Path $CecilDir "x") -Force
    Copy-Item (Join-Path $CecilDir "x\lib\netstandard2.0\Mono.Cecil*.dll") $CecilDir -Force
}
Get-ChildItem $CecilDir -Filter *.dll | ForEach-Object { Unblock-File $_.FullName -ErrorAction SilentlyContinue }
[void][System.Reflection.Assembly]::Load([System.IO.File]::ReadAllBytes($cecil))

$typeName = "OpenUtau.Core.DiffSinger.DiffSingerPolishPhonemizer"

# ---- build candidate
$asm  = [Mono.Cecil.AssemblyDefinition]::ReadAssembly((Resolve-Path $DllPath).Path)
$mod  = $asm.MainModule
$type = $mod.GetType($typeName)
if ($null -eq $type) { throw "type $typeName not found in $DllPath - is this DIFF_PL_phonemiser.dll?" }
foreach ($m in $type.Methods) {
    if ($m.Name -eq "GetLangCode") { throw "GetLangCode already present - already patched? (refusing to double-patch)" }
}
# NOTE: PowerShell -bor on a Cecil [Flags] enum throws InvalidCastException; set flags via properties.
$md = New-Object Mono.Cecil.MethodDefinition("GetLangCode", [Mono.Cecil.MethodAttributes]0, $mod.TypeSystem.String)
$md.IsPublic = $true; $md.IsVirtual = $true; $md.IsReuseSlot = $true; $md.IsHideBySig = $true
$il = $md.Body.GetILProcessor()
$il.Append($il.Create([Mono.Cecil.Cil.OpCodes]::Ldstr, $LangCode))
$il.Append($il.Create([Mono.Cecil.Cil.OpCodes]::Ret))
$type.Methods.Add($md)
$asm.Write($OutPath)
$cand = [System.IO.File]::ReadAllBytes($OutPath)
Write-Host "candidate written: $OutPath ($($cand.Length) bytes)"

# ---- VERIFY GATE
$problems = @()
if ($cand[0] -ne 0x4D -or $cand[1] -ne 0x5A) { $problems += "candidate is not MZ" }

$a2 = [Mono.Cecil.AssemblyDefinition]::ReadAssembly($OutPath)
$t2 = $a2.MainModule.GetType($typeName)
$found = $false
foreach ($m in $t2.Methods) {
    if ($m.Name -ne "GetLangCode") { continue }
    $found = $true
    if (-not ($m.IsVirtual -and $m.IsReuseSlot)) { $problems += "GetLangCode is not a reuseSlot virtual override" }
    if ($m.ReturnType.Name -ne "String")        { $problems += "GetLangCode return type is $($m.ReturnType.Name), expected String" }
    $ops = @($m.Body.Instructions | ForEach-Object { $_.OpCode.Name })
    if ($ops.Count -ne 2 -or $ops[0] -ne "ldstr" -or $ops[1] -ne "ret") {
        $problems += "GetLangCode body is [$($ops -join ',')], expected [ldstr, ret]"
    } else {
        $str = $m.Body.Instructions[0].Operand
        if ($str -ne $LangCode) { $problems += "GetLangCode returns '$str', expected '$LangCode'" }
    }
}
if (-not $found) { $problems += "GetLangCode missing after write" }
foreach ($n in "GetDictionaryName", "LoadBaseG2p", "GetBaseG2pVowels", "GetBaseG2pConsonants") {
    if (-not ($t2.Methods | Where-Object { $_.Name -eq $n })) { $problems += "original method $n missing" }
}

# g2p-pl resource must still be readable through the plugin's own read path
try {
    $la = [System.Reflection.Assembly]::Load($cand)
    $got = $false
    foreach ($rn in $la.GetManifestResourceNames()) {
        $s = $la.GetManifestResourceStream($rn); $ms = New-Object System.IO.MemoryStream; $s.CopyTo($ms); $ms.Seek(0, 'Begin') | Out-Null
        $rr = [System.Resources.ResourceReader]::new($ms); $en = $rr.GetEnumerator()
        while ($en.MoveNext()) {
            if ($en.Key -eq "g2p-pl") {
                $got = $true
                $b = $en.Value
                if ($b -isnot [byte[]]) { $problems += "g2p-pl is not a Byte[]" }
                elseif ($b[0] -ne 0x50 -or $b[1] -ne 0x4B) { $problems += "g2p-pl does not start with PK (not a zip)" }
                else { Write-Host "verify: g2p-pl OK ($($b.Length) bytes, zip magic present)" }
            }
        }
        $rr.Close(); $ms.Close(); $s.Close()
    }
    if (-not $got) { $problems += "g2p-pl resource not found after write" }
} catch {
    $problems += "resource read-back failed: $($_.Exception.Message)"
}

if ($problems.Count -gt 0) {
    Remove-Item $OutPath -Force
    Write-Host "VERIFY FAILED - nothing written:"
    $problems | ForEach-Object { Write-Host "  !! $_" }
    exit 1
}
Write-Host "VERIFY OK: GetLangCode()='$LangCode' override present, original methods intact, g2p-pl resource intact."

if ($Install) {
    $stamp = Get-Date -Format "yyyyMMdd"
    $bak = "$DllPath.bak-$stamp"
    Copy-Item (Resolve-Path $DllPath) $bak -Force
    Copy-Item $OutPath $DllPath -Force
    Write-Host "installed over $DllPath (original backed up at $bak)"
}
exit 0
