param(
    [Parameter(Mandatory)]
    [ValidateSet('stable', 'insiders')]
    [string]$Channel
)

$ErrorActionPreference = 'Stop'
$root = Join-Path $env:RUNNER_TEMP 'latest-msvc'
$logs = Join-Path $root 'logs'
New-Item $logs -ItemType Directory -Force | Out-Null
$channelUri = "https://aka.ms/vs/18/$Channel/channel"
$channelData = Invoke-RestMethod $channelUri
$manifest = $channelData.channelItems | Where-Object type -eq 'Manifest'
$catalog = Invoke-RestMethod $manifest.payloads[0].url
if ($catalog -is [string]) {
    $catalog = $catalog | ConvertFrom-Json -Depth 100
}
$default = $catalog.packages | Where-Object id -eq 'Microsoft.VisualCpp.Tools.HostARM64.TargetARM64'
$preview = $catalog.packages | Where-Object id -eq 'Microsoft.VC.Preview.Tools.HostARM64.TargetARM64'
if (@($default).Count -ne 1 -or @($preview).Count -ne 1) {
    throw 'Expected one default and one preview native ARM64 compiler package'
}
$metadata = @{
    channel = $channelUri
    catalogUrl = $manifest.payloads[0].url
    catalog = $catalog.info
    defaultPackage = $default
    previewPackage = $preview
    imageOS = $env:ImageOS
    imageVersion = $env:ImageVersion
}
$metadata | ConvertTo-Json -Depth 12 | Out-File "$logs\catalog-selection.json" -Encoding utf8
$metadata | ConvertTo-Json -Depth 4 | Write-Output

$installer = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer"
$imageVS = & "$installer\vswhere.exe" -latest -products '*' -property installationPath
$ninja = Join-Path $imageVS 'Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja'
$vs = Join-Path $root 'BuildTools'
$bootstrapper = Join-Path $root 'vs_BuildTools.exe'
Invoke-WebRequest "https://aka.ms/vs/18/$Channel/vs_buildtools.exe" -OutFile $bootstrapper
$signature = Get-AuthenticodeSignature $bootstrapper
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Microsoft Corporation*') {
    throw 'Invalid Microsoft bootstrapper signature'
}
$arguments = @(
    '--installPath', "`"$vs`"",
    '--channelUri', $channelUri,
    '--add', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
    '--add', 'Microsoft.VisualStudio.Component.VC.Tools.ARM64',
    '--add', 'Microsoft.VisualStudio.Component.VC.Preview.ARM64',
    '--quiet', '--wait', '--norestart', '--nocache'
)
$process = Start-Process $bootstrapper -ArgumentList $arguments -Wait -PassThru
Write-Output "Installer exit code: $($process.ExitCode)"
if ($process.ExitCode -notin 0, 3010) {
    throw "Fresh compiler installation failed: $($process.ExitCode)"
}
$instances = & "$installer\vswhere.exe" -all -prerelease -products '*' -format json | ConvertFrom-Json
$instance = $instances | Where-Object installationPath -eq $vs
$instance | ConvertTo-Json -Depth 8 | Out-File "$logs\installed-instance.json" -Encoding utf8
if ($instance.installationVersion -ne $catalog.info.buildVersion) {
    throw "Installed $($instance.installationVersion), catalog specified $($catalog.info.buildVersion)"
}
Get-ChildItem "$vs\VC\Tools\MSVC" -Directory | Select-Object -ExpandProperty Name
if (-not (Test-Path "$vs\Common7\Tools\vsdevcmd\ext\vcvars.bat")) {
    throw 'C++ developer-prompt extension was not installed'
}
Get-ChildItem "$vs\VC\Tools\MSVC" -Recurse -Filter cl.exe |
    Select-Object -ExpandProperty FullName |
    Tee-Object "$logs\installed-compilers.txt"
"LATEST_VS=$vs" | Out-File $env:GITHUB_ENV -Append -Encoding utf8
"LATEST_NINJA=$ninja" | Out-File $env:GITHUB_ENV -Append -Encoding utf8
"LATEST_DEFAULT=$($default.version -replace '^(\d+\.\d+).*', '$1')" | Out-File $env:GITHUB_ENV -Append -Encoding utf8
"LATEST_PREVIEW=$($preview.version -replace '^(\d+\.\d+).*', '$1')" | Out-File $env:GITHUB_ENV -Append -Encoding utf8
