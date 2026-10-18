<#
.SYNOPSIS
    Fetch the PYNQ board sources needed to rebuild the PYNQ-Z2 base overlay.

.DESCRIPTION
    The base overlay is PYNQ's own design, not ours: it is the HDMI/audio/IO
    framework that the PYNQ image ships, and the only practical way to get
    "HDMI in -> PL -> HDMI out" with the pynq.lib.video API is to rebuild it with
    our kernel inserted. This script pulls exactly the two directories we need
    from the pinned PYNQ tag, so the overlay build is reproducible.

    Pinned to the v3.1.2 tag (commit 3c77124d86bab65ac7bb6beb0aa66e13c83508f2)
    because that is the release the PYNQ 3.1.x images are built from. Change
    -Tag when the board image version is known to be different.

.NOTES
    `git -c http.sslBackend=openssl` is deliberate: on this machine Git's
    schannel backend fails with SEC_E_NO_CREDENTIALS when the clone runs from a
    restricted shell.
#>
param(
    [string]$Tag = "v3.1.2",
    [string]$Dest = (Join-Path $PSScriptRoot ".work"),
    [string]$ReuseFrom = ""
)

$ErrorActionPreference = "Stop"

$repoDir = Join-Path $Dest "pynq"
$treeDir = Join-Path $Dest "tree"
$baseDir = Join-Path $treeDir "boards\Pynq-Z2\base"

Write-Host "=== fetch PYNQ $Tag ==="
if (-not (Test-Path (Join-Path $repoDir ".git"))) {
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null

    if ($ReuseFrom -and (Test-Path (Join-Path $ReuseFrom ".git"))) {
        # Reuse an existing checkout instead of hitting the network again.
        Write-Host "reusing existing checkout: $ReuseFrom"
        Copy-Item $ReuseFrom $repoDir -Recurse
    } else {
        # GitHub occasionally resets the connection mid-clone; retry a few times
        # before giving up, and say clearly what to do if it keeps failing.
        $ok = $false
        for ($i = 1; $i -le 3 -and -not $ok; $i++) {
            Write-Host "clone attempt $i of 3"
            if (Test-Path $repoDir) { Remove-Item $repoDir -Recurse -Force }
            git -c http.sslBackend=openssl clone --depth 1 --filter=blob:none --sparse `
                --branch $Tag https://github.com/Xilinx/PYNQ.git $repoDir
            $ok = ($LASTEXITCODE -eq 0)
            if (-not $ok) { Start-Sleep -Seconds 5 }
        }
        if (-not $ok) {
            throw ("git clone failed after 3 attempts. " +
                   "Re-run later, or clone PYNQ $Tag yourself and pass " +
                   "-ReuseFrom <path-to-your-PYNQ-checkout>.")
        }
    }
} else {
    Write-Host "already cloned: $repoDir"
}

Push-Location $repoDir
try {
    git -c http.sslBackend=openssl sparse-checkout set --no-cone boards/Pynq-Z2 boards/ip
    if ($LASTEXITCODE -ne 0) { throw "sparse-checkout failed" }
} finally {
    Pop-Location
}

Write-Host "=== stage build tree ==="
if (Test-Path $treeDir) { Remove-Item $treeDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Split-Path $baseDir) | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $treeDir "boards\Pynq-Z2") | Out-Null

Copy-Item (Join-Path $repoDir "boards\Pynq-Z2\base") (Join-Path $treeDir "boards\Pynq-Z2\base") -Recurse
Copy-Item (Join-Path $repoDir "boards\ip") (Join-Path $treeDir "boards\ip") -Recurse

# Notebooks and their images are ~3 MB of nothing we build with.
$nb = Join-Path $baseDir "notebooks"
if (Test-Path $nb) { Remove-Item $nb -Recurse -Force }

Write-Host "base overlay tcl: $(Join-Path $baseDir 'base.tcl')"
Write-Host "ip repository  : $(Join-Path $treeDir 'boards\ip')"
