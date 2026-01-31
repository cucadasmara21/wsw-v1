#!/usr/bin/env pwsh
param(
  [int]$Target = 200000,
  [string]$ApiBase = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path ".\\scripts\\audit_v8.ps1") {
  powershell -ExecutionPolicy Bypass -File ".\\scripts\\audit_v8.ps1" -Target $Target -ApiBase $ApiBase
  exit $LASTEXITCODE
}

Write-Error "scripts\\audit_v8.ps1 not found."
exit 1

