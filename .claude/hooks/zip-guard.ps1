# Blocks zip/Compress-Archive commands that would recursively archive and
# could accidentally include .env, *.key, *.pem, or similar secrets files.
#
# Fires when the command: uses -r/-R/-Recurse flag OR passes "." as a source.
# To bypass: explicitly exclude sensitive files, e.g.:
#   zip -r archive.zip . -x "*.env" -x "*.key" -x "*.pem"

$raw = $input | Out-String
if (-not $raw.Trim()) { exit 0 }

try { $j = $raw | ConvertFrom-Json } catch { exit 0 }

$cmd = $j.tool_input.command
if (-not $cmd) { exit 0 }

# Only care about archive commands
if ($cmd -notmatch '\bzip\b|Compress-Archive|7z\s+a\b|tar\s+.*-[czj]') { exit 0 }

# Only fire for recursive / directory-spanning invocations
$isRecursive = $cmd -match '\s-[rR]\b|\s-Recurse\b|\s/recurse\b'
$hasDotSource = $cmd -match '\s\.\s|\s\.$|\s\.\\'
if (-not ($isRecursive -or $hasDotSource)) { exit 0 }

# If the command already has explicit .env exclusion, pass through
if ($cmd -match '-x\s*["\x27]?\*?\.env|--exclude[= ]["\x27]?\*?\.env|Exclude.*\.env') { exit 0 }

# Scan project dir for sensitive files
$projectDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$sensitivePatterns = @(
    '^\.env',                                   # .env, .env.local, .env.production …
    '\.key$',                                   # private keys
    '\.pem$',                                   # certificates / private keys
    '\.p12$', '\.pfx$',                         # certificate stores
    '^credentials\.(json|ya?ml|env|cfg|ini)$',  # credential config files (not .py/.md)
    '^secrets\.(json|ya?ml|env|cfg|ini)$'       # secrets config files (not .py/.md)
)
$found = @()

try {
    Get-ChildItem -Path $projectDir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        foreach ($pat in $sensitivePatterns) {
            if ($_.Name -match $pat) { $found += $_.Name; break }
        }
    }
} catch { exit 0 }

if ($found.Count -eq 0) { exit 0 }

$fileList = ($found | Select-Object -Unique | Sort-Object) -join ', '
@{
    continue   = $false
    stopReason = "ZIP BLOCKED: Recursive archive would include sensitive files: $fileList`nExclude them explicitly, e.g.:`n  zip -r archive.zip . -x ""*.env"" -x ""*.key"" -x ""*.pem"""
} | ConvertTo-Json -Compress
