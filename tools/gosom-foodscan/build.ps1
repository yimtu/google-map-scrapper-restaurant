$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$work = Join-Path $env:TEMP ("foodscan-gosom-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $work | Out-Null
try {
    $gosomArchive = Join-Path $work "gosom-v1.18.1.zip"
    $scrapemateArchive = Join-Path $work "scrapemate-v1.4.0.zip"
    Invoke-WebRequest "https://github.com/gosom/google-maps-scraper/archive/refs/tags/v1.18.1.zip" -OutFile $gosomArchive
    Invoke-WebRequest "https://github.com/gosom/scrapemate/archive/refs/tags/v1.4.0.zip" -OutFile $scrapemateArchive
    if ((Get-FileHash $gosomArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne "e44b4b66bf578c8d7dd17fac97d84ee3d59a46c0ef478b089aa59eaf126821a6") {
        throw "Gosom source archive SHA-256 mismatch"
    }
    if ((Get-FileHash $scrapemateArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne "e0057db4ee576858d526279c63220f796a3dbccde41893006c997981c7fa4fdc") {
        throw "Scrapemate source archive SHA-256 mismatch"
    }
    Expand-Archive $gosomArchive $work
    Expand-Archive $scrapemateArchive $work
    Push-Location (Join-Path $work "scrapemate-1.4.0")
    git apply (Join-Path $here "patch\scrapemate-foodscan.patch")
    go test ./adapters/fetchers/jshttp
    Pop-Location
    $gosom = Join-Path $work "google-maps-scraper-1.18.1"
    $gomod = Join-Path $gosom "go.mod"
    $content = Get-Content $gomod -Raw
    Set-Content $gomod ($content + "`nreplace github.com/gosom/scrapemate => ../scrapemate-1.4.0`n") -NoNewline
    Push-Location $gosom
    go build -trimpath -o (Join-Path $here "gosom-foodscan.exe") .
    Pop-Location
    Get-FileHash (Join-Path $here "gosom-foodscan.exe") -Algorithm SHA256
} finally {
    Pop-Location -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $work -Recurse -Force
}
