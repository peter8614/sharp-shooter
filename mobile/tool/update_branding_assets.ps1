param(
    [string]$SourcePath = (Join-Path $PSScriptRoot '..\assets\app_logo_source.png')
)

# Reproduce platform icon sizes from the supplied artwork without redesigning it.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.Drawing
$mobileRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$resolvedSource = (Resolve-Path -LiteralPath $SourcePath).Path
$sourceImage = [System.Drawing.Image]::FromFile($resolvedSource)

function Export-Icon([string]$Destination, [int]$Size) {
    # iOS marketing icons must be opaque. Flatten every icon onto white.
    $bitmap = [System.Drawing.Bitmap]::new(
        $Size, $Size, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb
    )
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $attributes = [System.Drawing.Imaging.ImageAttributes]::new()
    try {
        $graphics.Clear([System.Drawing.Color]::White)
        $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $attributes.SetWrapMode([System.Drawing.Drawing2D.WrapMode]::TileFlipXY)
        $graphics.DrawImage(
            $sourceImage, [System.Drawing.Rectangle]::new(0, 0, $Size, $Size),
            0, 0, $sourceImage.Width, $sourceImage.Height,
            [System.Drawing.GraphicsUnit]::Pixel, $attributes
        )
        $bitmap.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $attributes.Dispose()
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

try {
    if ($sourceImage.Width -ne $sourceImage.Height) {
        throw 'Logo source must be square so icons preserve the entire artwork.'
    }
    foreach ($assetName in @('logo.png', 'SharpShooter.png')) {
        Copy-Item -LiteralPath $resolvedSource -Destination (Join-Path $mobileRoot "assets\$assetName") -Force
    }
    $iconRoot = Join-Path $mobileRoot 'ios\Runner\Assets.xcassets\AppIcon.appiconset'
    $catalog = Get-Content -LiteralPath (Join-Path $iconRoot 'Contents.json') -Raw | ConvertFrom-Json
    foreach ($icon in ($catalog.images | Sort-Object filename -Unique)) {
        $points = [double]::Parse($icon.size.Split('x')[0], [Globalization.CultureInfo]::InvariantCulture)
        $scale = [int]$icon.scale.TrimEnd('x')
        Export-Icon (Join-Path $iconRoot $icon.filename) ([int]($points * $scale))
    }
    $densities = @{ 'mdpi' = 48; 'hdpi' = 72; 'xhdpi' = 96; 'xxhdpi' = 144; 'xxxhdpi' = 192 }
    foreach ($density in $densities.Keys) {
        Export-Icon (Join-Path $mobileRoot "android\app\src\main\res\mipmap-$density\ic_launcher.png") $densities[$density]
    }
    Write-Output 'Updated App logos, iOS icon catalog (including 1024px), and Android launcher icons.'
} finally {
    $sourceImage.Dispose()
}
