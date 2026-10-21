# End-to-end smoke test against a RUNNING controller (default: localhost:8000).
# Run:  powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1 -BaseUrl http://127.0.0.1:8000
param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$User = "smoke_" + (Get-Random -Maximum 99999),
    [string]$Password = "SmokeTest1"
)

$ErrorActionPreference = "Stop"
$failures = 0
function Check($name, $ok, $extra = "") {
    if ($ok) { Write-Host "  [PASS] $name" -ForegroundColor Green }
    else { Write-Host "  [FAIL] $name $extra" -ForegroundColor Red; $script:failures++ }
}

Write-Host "== 1. Health ==" -ForegroundColor Cyan
$r = Invoke-RestMethod "$BaseUrl/api/health"
Check "health responds" ($r.status -in @("ok","degraded","error"))
Write-Host "     status=$($r.status) storage=$($r.storage.adapter) db=$($r.database)"

Write-Host "== 2. Registration + login ==" -ForegroundColor Cyan
$reg = Invoke-RestMethod -Method Post "$BaseUrl/api/auth/register" `
    -ContentType "application/json" -Body (@{username=$User;password=$Password} | ConvertTo-Json)
Check "register" ($reg.access_token -and $reg.user.username -eq $User)
$login = Invoke-RestMethod -Method Post "$BaseUrl/api/auth/login" `
    -ContentType "application/json" -Body (@{username=$User;password=$Password} | ConvertTo-Json)
Check "login" ($null -ne $login.access_token)
$H = @{ Authorization = "Bearer $($login.access_token)" }
$me = Invoke-RestMethod "$BaseUrl/api/auth/me" -Headers $H
Check "me endpoint" ($me.username -eq $User)

# negative: wrong password must fail
$bad = $null
try { Invoke-RestMethod -Method Post "$BaseUrl/api/auth/login" `
    -ContentType "application/json" -Body (@{username=$User;password="Wrong999"} | ConvertTo-Json) }
catch { $bad = $_.Exception.Response.StatusCode.value__ }
Check "wrong password rejected (401)" ($bad -eq 401)

Write-Host "== 3. Upload ==" -ForegroundColor Cyan
Add-Type -AssemblyName System.Net.Http
$tmp = Join-Path $env:TEMP "smoke_upload.txt"
$content = "HDFS smoke test content - $(Get-Date -Format o)"
[System.IO.File]::WriteAllText($tmp, $content)
$bytes = [System.Text.Encoding]::UTF8.GetBytes($content)
$shaObjPre = [System.Security.Cryptography.SHA256]::Create()
$sha = [System.BitConverter]::ToString($shaObjPre.ComputeHash($bytes)).Replace("-","").ToLower()

function Send-MultipartFile {
    param([string]$Url, [hashtable]$Headers, [string]$FilePath, [string]$FieldName = "file")
    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromMinutes(5)
    foreach ($k in $Headers.Keys) {
        if ($k -ieq "Authorization") {
            $client.DefaultRequestHeaders.TryAddWithoutValidation($k, $Headers[$k]) | Out-Null
        }
    }
    $mp = New-Object System.Net.Http.MultipartFormDataContent
    $stream = [System.IO.File]::OpenRead($FilePath)
    $fileContent = New-Object System.Net.Http.StreamContent($stream)
    $fileContent.Headers.ContentType =
        [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("application/octet-stream")
    $mp.Add($fileContent, $FieldName, [System.IO.Path]::GetFileName($FilePath))
    $response = $client.PostAsync($Url, $mp).GetAwaiter().GetResult()
    $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    $status = [int]$response.StatusCode
    $stream.Dispose(); $mp.Dispose(); $client.Dispose()
    return @{ Status = $status; Body = $body }
}

$uploadResult = Send-MultipartFile -Url "$BaseUrl/api/files/upload" -Headers $H -FilePath $tmp
Check "upload status 201" ($uploadResult.Status -eq 201) "got $($uploadResult.Status) $($uploadResult.Body)"
$up = $uploadResult.Body | ConvertFrom-Json
Check "upload size recorded" ($up.file.size_bytes -eq $bytes.Length)
Check "sha256 recorded" ($up.file.sha256 -eq $sha)
Check "storage path not exposed" ($null -eq $up.file.hdfs_path)
$fileId = $up.file.id

Write-Host "== 4. List / stats ==" -ForegroundColor Cyan
$files = Invoke-RestMethod "$BaseUrl/api/files" -Headers $H
Check "file listed" (@($files.items | Where-Object { $_.id -eq $fileId }).Count -eq 1)
Check "storage_used_bytes matches" ($files.storage_used_bytes -ge $bytes.Length)
$stats = Invoke-RestMethod "$BaseUrl/api/dashboard/stats" -Headers $H
Check "dashboard stats" ($stats.total_files -ge 1)

Write-Host "== 5. Download + integrity ==" -ForegroundColor Cyan
function Get-Bytes {
    param([string]$Url, [hashtable]$Headers, [string]$OutFile)
    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromMinutes(5)
    foreach ($k in $Headers.Keys) {
        $client.DefaultRequestHeaders.TryAddWithoutValidation($k, $Headers[$k]) | Out-Null
    }
    $response = $client.GetAsync($Url).GetAwaiter().GetResult()
    $status = [int]$response.StatusCode
    if ($status -eq 200) {
        $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $out = [System.IO.File]::Create($OutFile)
        $stream.CopyTo($out)
        $out.Close(); $stream.Close()
    }
    $client.Dispose()
    return $status
}

$dlPath = Join-Path $env:TEMP "smoke_download.txt"
$dlStatus = Get-Bytes -Url "$BaseUrl/api/files/$fileId/download" -Headers $H -OutFile $dlPath
Check "download status 200" ($dlStatus -eq 200) "got $dlStatus"
$dlBytes = [System.IO.File]::ReadAllBytes($dlPath)
$got = [System.Text.Encoding]::UTF8.GetString($dlBytes)
Check "content identical" ($got -eq $content)
$shaObj = [System.Security.Cryptography.SHA256]::Create()
$dlSha = [System.BitConverter]::ToString($shaObj.ComputeHash($dlBytes)).Replace("-","").ToLower()
Check "downloaded sha256 matches" ($dlSha -eq $sha)
Remove-Item $dlPath -ErrorAction SilentlyContinue

Write-Host "== 6. Ownership isolation ==" -ForegroundColor Cyan
$reg2 = Invoke-RestMethod -Method Post "$BaseUrl/api/auth/register" `
    -ContentType "application/json" -Body (@{username="smoke_other_$([int](Get-Random -Maximum 9999))";password="OtherPass1"} | ConvertTo-Json)
$H2 = @{ Authorization = "Bearer $($reg2.access_token)" }
$code = 0
try { Invoke-WebRequest "$BaseUrl/api/files/$fileId/download" -Headers $H2 }
catch { $code = $_.Exception.Response.StatusCode.value__ }
Check "other user cannot download (404)" ($code -eq 404)
$code = 0
try { Invoke-WebRequest -Method Delete "$BaseUrl/api/files/$fileId" -Headers $H2 }
catch { $code = $_.Exception.Response.StatusCode.value__ }
Check "other user cannot delete (404)" ($code -eq 404)

Write-Host "== 7. Admin protection ==" -ForegroundColor Cyan
$code = 0
try { Invoke-WebRequest "$BaseUrl/api/admin/stats" -Headers $H }
catch { $code = $_.Exception.Response.StatusCode.value__ }
Check "regular user blocked from admin (403)" ($code -eq 403)
$code = 0
try { Invoke-WebRequest "$BaseUrl/api/admin/stats" }
catch { $code = $_.Exception.Response.StatusCode.value__ }
Check "anonymous blocked from admin (401)" ($code -eq 401)

Write-Host "== 8. Delete own file ==" -ForegroundColor Cyan
$del = Invoke-RestMethod -Method Delete "$BaseUrl/api/files/$fileId" -Headers $H
Check "delete own file" ($del.file_id -eq $fileId)
$after = Invoke-RestMethod "$BaseUrl/api/files" -Headers $H
Check "file no longer listed" (@($after.items | Where-Object { $_.id -eq $fileId }).Count -eq 0)

Write-Host "== 9. Validation / limits ==" -ForegroundColor Cyan
$big = Join-Path $env:TEMP "smoke_big.bin"
$fs = [System.IO.File]::Create($big)
$fs.SetLength(20MB)
$fs.Close()
$bigResult = Send-MultipartFile -Url "$BaseUrl/api/files/upload" -Headers $H -FilePath $big
Check "oversized upload rejected (413)" ($bigResult.Status -eq 413) "got $($bigResult.Status)"
Remove-Item $big -ErrorAction SilentlyContinue

# path traversal in the filename must not reach the storage layer
$sneaky = Join-Path $env:TEMP "sneaky.txt"
[System.IO.File]::WriteAllText($sneaky, "traversal attempt")
$sneakyResult = Send-MultipartFile -Url "$BaseUrl/api/files/upload" -Headers $H -FilePath $sneaky
$sneakyFile = $sneakyResult.Body | ConvertFrom-Json
Check "filename sanitised on upload" ($sneakyFile.file.original_name -eq "sneaky.txt")
Check "cleaned up" $true
if ($sneakyFile.file.id) { Invoke-RestMethod -Method Delete "$BaseUrl/api/files/$($sneakyFile.file.id)" -Headers $H | Out-Null }

Remove-Item $tmp -ErrorAction SilentlyContinue
Remove-Item $sneaky -ErrorAction SilentlyContinue
Write-Host ""
if ($failures -eq 0) { Write-Host "ALL SMOKE TESTS PASSED" -ForegroundColor Green }
else { Write-Host "$failures SMOKE TEST(S) FAILED" -ForegroundColor Red; exit 1 }
