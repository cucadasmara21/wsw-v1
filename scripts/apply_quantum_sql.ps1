param(
  [string]$Container = "wsw-postgres",
  [string]$Db = "wsw_db",
  [string]$User = "postgres",
  [string]$SqlPath = ""
)

# Use script directory to find SQL file relative to repo root
if ([string]::IsNullOrEmpty($SqlPath)) {
    $SqlPath = Join-Path $PSScriptRoot "..\quantum_materialization.sql"
    $SqlPath = [System.IO.Path]::GetFullPath($SqlPath)
}

if (-not (Test-Path $SqlPath)) {
    Write-Error "SQL file not found: $SqlPath"
    exit 1
}

Write-Host "Applying SQL from: $SqlPath"
Get-Content -Raw $SqlPath | docker exec -i $Container psql -U $User -d $Db

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] SQL applied successfully"
} else {
    Write-Error "SQL application failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}
