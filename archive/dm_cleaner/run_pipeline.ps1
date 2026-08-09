<#
.SYNOPSIS
  Run the Jester cleaning pipeline with maximum observability.

.DESCRIPTION
  - Processes PDFs, TXT, HTML, JSON, JSONL from input folder (recursive, multi-glob).
  - Writes one JSONL (default) per source into the output folder + manifest files.
  - Emits per-file quality reports and optional debug artifacts.
  - Uses a safe argument array (no backticks) and tees logs to a timestamped file.
  - Optionally activates a virtual environment automatically.
#>

param(
  [string]$InDir      = "D:\dnd5E\Rules",
  [string]$OutDir     = "F:\Jester\out",
  [string]$ReportsDir = "F:\Jester\reports",
  [string]$DebugDir   = "F:\Jester\debug",
  [string]$VenvPath   = "F:\Jester\venv",
  [string]$Globs      = "**/*.pdf,**/*.txt,**/*.html,**/*.json,**/*.jsonl",
  [int]$MinWords      = 120,
  [int]$MaxWords      = 600,
  [ValidateSet("auto","json")]
  [string]$Format     = "auto",
  [switch]$PrettyJson,
  [switch]$QuietPyPDF2,
  [switch]$DownloadNLTK
)

$ErrorActionPreference = "Stop"

# --- Resolve and create directories
$null = New-Item -ItemType Directory -Force -Path $OutDir, $ReportsDir, $DebugDir | Out-Null
$logDir = "F:\Jester\logs"
$null = New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ("pipeline-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

Write-Host "Log file: $logFile"

# --- Activate venv if present (no-op if not found)
$activate = Join-Path $VenvPath "Scripts\Activate.ps1"
if (Test-Path $activate) {
  Write-Host "Activating venv: $VenvPath"
  . $activate
} else {
  Write-Warning "Venv not found at $VenvPath (continuing with current Python)."
}

# --- Environment for quality + observability
$env:PYTHONUTF8              = "1"
$env:PYTHONHASHSEED          = "0"
$env:PYTHONWARNINGS          = "default"
$env:DM_REPORT_DIR           = $ReportsDir
$env:DM_DEBUG_DIR            = $DebugDir
$env:DM_DOC_ID_POLICY        = "hash_stem"
$env:DM_SEM_DEDUP_ENABLED    = "1"
$env:DM_SEM_DEDUP_MODEL      = "sentence-transformers/all-MiniLM-L6-v2"
$env:DM_SEM_DEDUP_THRESH     = "0.92"
$env:TOKENIZERS_PARALLELISM  = "false"

# Ensure our project root (if using local modules) is in PYTHONPATH
$projRoot = Split-Path $VenvPath -Parent
if (-not [string]::IsNullOrWhiteSpace($projRoot)) {
  $env:PYTHONPATH = "$projRoot;$env:PYTHONPATH"
}

# --- Optional: suppress PyPDF2 deprecation warnings
$warningArgs = @()
if ($QuietPyPDF2) {
  $warningArgs += @("-W", "ignore:.*:DeprecationWarning:PyPDF2")
}

# --- Optional: NLTK data download
if ($DownloadNLTK) {
  Write-Host "Downloading NLTK resources (punkt, stopwords)..."
  & python - << 'PYCODE'
import nltk, sys
for pkg in ("punkt","stopwords"):
    try:
        nltk.download(pkg, quiet=True, raise_on_error=True)
        print(f"Downloaded: {pkg}")
    except Exception as e:
        print(f"Failed to download {pkg}: {e}", file=sys.stderr)
        sys.exit(1)
PYCODE
}

# --- Build argument list safely (no backticks)
$argsList = @()
$argsList += $warningArgs
$argsList += @(
  "-X", "faulthandler",
  "-X", "tracemalloc",
  "pipeline.py",
  "--input-dir",  $InDir,
  "--input-glob", $Globs,
  "--output-dir", $OutDir,
  "--min-words",  "$MinWords",
  "--max-words",  "$MaxWords",
  "--format",     $Format
)
if ($PrettyJson) { $argsList += "--pretty-json" }

# --- Run and tee logs
Write-Host "Running pipeline..."
$elapsed = Measure-Command {
  & python @argsList | Tee-Object -FilePath $logFile
}

"Total elapsed: {0:c}" -f $elapsed.TotalDuration | Tee-Object -FilePath $logFile -Append
Write-Host "Done."
Write-Host "Logs   : $logFile"
Write-Host "Reports: $ReportsDir"
Write-Host "Debug  : $DebugDir"
Write-Host "Output : $OutDir"
