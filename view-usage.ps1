param(
    [string]$Url = "",
    [string]$Token = "",
    [switch]$Watch
)

# 1. Determine Target URL and Token
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $scriptDir ".env"

$targetHost = "100.97.230.23"
$targetPort = 4182
$authToken = "wyse-test-secret-2026"

if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $k = $parts[0].Trim()
            $v = $parts[1].Trim().Trim("'`"")
            if ($k -eq "PROXY_LISTEN_HOST" -and $v -and $v -ne "127.0.0.1" -and $v -ne "localhost") { $targetHost = $v }
            if ($k -eq "PROXY_PORT" -and $v) { $targetPort = $v }
            if ($k -eq "PROXY_AUTH_TOKEN" -and $v) { $authToken = $v }
        }
    }
}

if ($Url) {
    $baseUri = $Url.TrimEnd("/")
} else {
    $baseUri = "http://$($targetHost):$($targetPort)"
}

if ($Token) {
    $authToken = $Token
}

function Show-Dashboard {
    param(
        $data,
        $stats,
        [double]$liveSpeed = 0,
        [bool]$isWatch = $false
    )

    if ($isWatch) {
        Clear-Host
    }

    Write-Host "=================================================================" -ForegroundColor Cyan
    Write-Host "   AgentRouter-Proxy - Live Token & Speed Monitor" -ForegroundColor Cyan
    Write-Host "   Target: $baseUri (Wyse PC)" -ForegroundColor DarkGray
    Write-Host "=================================================================" -ForegroundColor Cyan

    if ($stats -and $stats.requests -ne $null) {
        Write-Host " Server Status: " -NoNewline
        Write-Host "ONLINE (HTTP 200)" -ForegroundColor Green -NoNewline
        Write-Host "  |  Active Session Req: " -NoNewline
        Write-Host "$($stats.requests)" -ForegroundColor Yellow
    }

    if ($isWatch) {
        Write-Host " Real-Time Speed: " -NoNewline
        if ($liveSpeed -gt 0) {
            Write-Host ("{0:N1} tok/s  [STREAMING]" -f $liveSpeed) -ForegroundColor Green
        } else {
            Write-Host "0.0 tok/s  [IDLE]" -ForegroundColor DarkGray
        }
    }

    Write-Host "-----------------------------------------------------------------" -ForegroundColor DarkGray

    $today = $data.today
    $todayTotal = if ($today.total_tokens) { [long]$today.total_tokens } else { 0 }
    $todayPrompt = if ($today.prompt_tokens) { [long]$today.prompt_tokens } else { 0 }
    $todayComp = if ($today.completion_tokens) { [long]$today.completion_tokens } else { 0 }
    $todayReqs = if ($today.requests) { [int]$today.requests } else { 0 }

    Write-Host " TODAY'S TOKEN USAGE:" -ForegroundColor Yellow
    Write-Host ("   Total Tokens:       {0,15:N0}" -f $todayTotal) -ForegroundColor White
    Write-Host ("   Prompt (Input):     {0,15:N0}" -f $todayPrompt) -ForegroundColor DarkGray
    Write-Host ("   Completion (Output):{0,15:N0}" -f $todayComp) -ForegroundColor Cyan
    Write-Host ("   Requests Completed: {0,15:N0}" -f $todayReqs) -ForegroundColor DarkYellow

    if ($today.models -and $today.models.PSObject.Properties.Count -gt 0) {
        Write-Host ""
        Write-Host " PER-MODEL BREAKDOWN (TODAY):" -ForegroundColor Yellow
        foreach ($prop in $today.models.PSObject.Properties) {
            $mName = $prop.Name
            $mTokens = [long]$prop.Value.total_tokens
            $mReqs = [int]$prop.Value.requests
            Write-Host ("   - {0,-20} : {1,12:N0} tokens  ({2} reqs)" -f $mName, $mTokens, $mReqs) -ForegroundColor White
        }
    }

    Write-Host "-----------------------------------------------------------------" -ForegroundColor DarkGray
    $thisMonth = if ($data.this_month.total_tokens) { [long]$data.this_month.total_tokens } else { 0 }
    $yesterday = if ($data.yesterday.total_tokens) { [long]$data.yesterday.total_tokens } else { 0 }
    $allTime = if ($data.all_time.total_tokens) { [long]$data.all_time.total_tokens } else { 0 }
    $allTimeReqs = if ($data.all_time.requests) { [int]$data.all_time.requests } else { 0 }

    Write-Host (" Yesterday:   {0,14:N0} tokens" -f $yesterday) -ForegroundColor DarkGray
    Write-Host (" This Month:  {0,14:N0} tokens" -f $thisMonth) -ForegroundColor DarkCyan
    Write-Host (" All-Time:    {0,14:N0} tokens  ({1} total reqs)" -f $allTime, $allTimeReqs) -ForegroundColor Green
    Write-Host "=================================================================" -ForegroundColor Cyan
}

$headers = @{}
if ($authToken) {
    $headers["Authorization"] = "Bearer $authToken"
}

if ($Watch) {
    $prevTokens = 0
    $prevTime = [DateTime]::UtcNow

    while ($true) {
        try {
            $data = Invoke-RestMethod -Uri "$baseUri/_usage" -Headers $headers -TimeoutSec 3 -ErrorAction Stop
            $stats = $null
            try { $stats = Invoke-RestMethod -Uri "$baseUri/_stats" -Headers $headers -TimeoutSec 2 -ErrorAction SilentlyContinue } catch {}

            $now = [DateTime]::UtcNow
            $elapsed = ($now - $prevTime).TotalSeconds
            $currentTokens = if ($data.today.completion_tokens) { [long]$data.today.completion_tokens } else { 0 }

            $liveSpeed = 0
            if ($prevTokens -gt 0 -and $currentTokens -ge $prevTokens -and $elapsed -gt 0.2) {
                $liveSpeed = ($currentTokens - $prevTokens) / $elapsed
            }

            Show-Dashboard -data $data -stats $stats -liveSpeed $liveSpeed -isWatch $true
            Write-Host " [Watching live updates every 2s. Press Ctrl+C to stop...]" -ForegroundColor DarkGray

            $prevTokens = $currentTokens
            $prevTime = $now
        } catch {
            Write-Host "[WARN] Could not reach proxy at $baseUri : $_" -ForegroundColor Red
        }

        Start-Sleep -Seconds 2
    }
} else {
    try {
        $data = Invoke-RestMethod -Uri "$baseUri/_usage" -Headers $headers -TimeoutSec 5 -ErrorAction Stop
        $stats = $null
        try { $stats = Invoke-RestMethod -Uri "$baseUri/_stats" -Headers $headers -TimeoutSec 3 -ErrorAction SilentlyContinue } catch {}
        Show-Dashboard -data $data -stats $stats -isWatch $false

        Write-Host ""
        $key = Read-Host "Press [W] to enter live watch mode (real-time tok/s), or Enter to exit"
        if ($key -match "^[wW]") {
            & $PSCommandPath -Url $Url -Token $Token -Watch
        }
    } catch {
        Write-Host "[ERROR] Could not connect to proxy at $baseUri : $_" -ForegroundColor Red
        Write-Host "Make sure the proxy is running and your Tailscale connection is active." -ForegroundColor Yellow
        Read-Host "Press Enter to exit"
    }
}
