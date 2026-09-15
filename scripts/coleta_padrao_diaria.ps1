$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).ProviderPath
$zone = [TimeZoneInfo]::FindSystemTimeZoneById('E. South America Standard Time')
$day = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $zone).ToString('yyyy-MM-dd')
$reportDir = Join-Path $projectRoot 'reports'
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
$reportPath = Join-Path $reportDir "coleta_padrao_$day.json"
$logPath = Join-Path $reportDir 'coleta_padrao_diaria.log'
$program = Join-Path $projectRoot '.venv\Scripts\futebol-analytics.exe'
if (-not (Test-Path -LiteralPath $program)) { throw 'Executável do projeto não encontrado.' }
Push-Location -LiteralPath $projectRoot
try {
    "$(Get-Date -Format o) início: $day" | Out-File -LiteralPath $logPath -Append -Encoding utf8
    $startedAt = Get-Date
    $output = & $program coletar-padrao --data $day --saida $reportPath 2>&1
    $result = $LASTEXITCODE
    if ((Test-Path -LiteralPath $reportPath) -and
        (Get-Item -LiteralPath $reportPath).LastWriteTime -ge $startedAt) {
        $report = Get-Content -LiteralPath $reportPath -Raw -Encoding utf8 | ConvertFrom-Json
        $summary = ($report.resumo.PSObject.Properties | ForEach-Object {
            "$($_.Name)=$($_.Value.status):$($_.Value.jogos)"
        }) -join ', '
        "Relatório: $reportPath; $summary" | Out-File -LiteralPath $logPath -Append -Encoding utf8
    } else {
        "Sem relatório; código $result" | Out-File -LiteralPath $logPath -Append -Encoding utf8
    }
    "$(Get-Date -Format o) fim: código $result" | Out-File -LiteralPath $logPath -Append -Encoding utf8
    exit $result
} finally {
    Pop-Location
}
