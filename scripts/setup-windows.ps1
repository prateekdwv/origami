# One-time Windows user tools plus this repository's isolated Python environment.
# Run with: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent

function Add-UserPath([string] $directory) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @($userPath -split ';' | Where-Object { $_ })
    if ($entries.TrimEnd('\') -notcontains $directory.TrimEnd('\')) {
        [Environment]::SetEnvironmentVariable('Path', (($entries + $directory) -join ';'), 'User')
    }
    if (($env:Path -split ';').TrimEnd('\') -notcontains $directory.TrimEnd('\')) {
        $env:Path = "$directory;$env:Path"
    }
}

Push-Location $repoRoot
try {
    $uvDirectory = Join-Path $env:LOCALAPPDATA 'Programs/uv'
    $uvExe = Join-Path $uvDirectory 'uv.exe'
    if (Test-Path $uvExe) { Add-UserPath $uvDirectory }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        $previousInstall = $env:UV_INSTALL_DIR
        $previousModify = $env:UV_NO_MODIFY_PATH
        try {
            $env:UV_INSTALL_DIR = $uvDirectory
            $env:UV_NO_MODIFY_PATH = '1'
            Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
            if (-not (Test-Path $uvExe)) { throw 'uv installation failed.' }
        } finally {
            $env:UV_INSTALL_DIR = $previousInstall
            $env:UV_NO_MODIFY_PATH = $previousModify
        }
        Add-UserPath $uvDirectory
    }

    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or
        -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
        $ffmpegDirectory = Join-Path $env:LOCALAPPDATA 'Programs/ffmpeg'
        $ffmpegExe = Get-ChildItem $ffmpegDirectory -Filter ffmpeg.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $ffmpegExe) {
            $archive = Join-Path ([IO.Path]::GetTempPath()) ([IO.Path]::GetRandomFileName() + '.zip')
            try {
                Invoke-WebRequest -UseBasicParsing https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip -OutFile $archive
                Expand-Archive -LiteralPath $archive -DestinationPath $ffmpegDirectory -Force
            } finally {
                if (Test-Path $archive) { Remove-Item -LiteralPath $archive }
            }
            $ffmpegExe = Get-ChildItem $ffmpegDirectory -Filter ffmpeg.exe -Recurse | Select-Object -First 1
        }
        if (-not $ffmpegExe) { throw 'FFmpeg installation failed.' }
        Add-UserPath $ffmpegExe.DirectoryName
    }
    foreach ($command in @('uv', 'ffmpeg', 'ffprobe')) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { throw "$command is unavailable." }
    }

    # Pure-Python srt needs packaging; native dependencies must use wheels.
    $nativePackages = @('av', 'glcontext', 'manimpango', 'mapbox-earcut', 'moderngl',
        'numpy', 'pillow', 'pycairo', 'pyglm', 'pyproj', 'pywin32', 'scipy', 'skia-pathops')
    $syncArguments = @('sync', '--locked', '--no-compile-bytecode')
    foreach ($package in $nativePackages) { $syncArguments += @('--no-build-package', $package) }
    & uv @syncArguments
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    Write-Host 'Setup complete. Open a new terminal, then use uv sync --locked and the project README commands.'
} finally { Pop-Location }
