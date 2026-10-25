param([string]$PdfDirectory = (Join-Path $PSScriptRoot '../backend/data/bank_pdfs'))
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]
$taskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
$actionMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' } | Select-Object -First 1
function Await-Result($Operation, [Type]$ResultType) {
    $task = $taskMethod.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.GetAwaiter().GetResult()
}
function Await-Action($Operation) {
    $task = $actionMethod.Invoke($null, @($Operation))
    $null = $task.GetAwaiter().GetResult()
}
$language = New-Object Windows.Globalization.Language('ru')
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
if (-not $engine) { throw 'Russian Windows OCR language pack is required.' }
foreach ($pdf in Get-ChildItem -LiteralPath $PdfDirectory -Filter '*.pdf') {
    $hash = (Get-FileHash -LiteralPath $pdf.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $output = $pdf.FullName + '.ocr.json'
    if (Test-Path -LiteralPath $output) {
        $saved = Get-Content -LiteralPath $output -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($saved.source_sha256 -eq $hash) { Write-Output ('Cached: ' + $pdf.Name); continue }
    }
    $file = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($pdf.FullName)) ([Windows.Storage.StorageFile])
    $document = Await-Result ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
    $pages = @()
    for ($index = 0; $index -lt $document.PageCount; $index++) {
        $page = $document.GetPage($index)
        $stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
        $options = New-Object Windows.Data.Pdf.PdfPageRenderOptions
        $options.DestinationWidth = 2400
        Await-Action ($page.RenderToStreamAsync($stream, $options))
        $decoder = Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await-Result ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Await-Result ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $pageText = ($result.Lines | ForEach-Object { $_.Text }) -join "`n"
        $pages += @{ page = $index + 1; text = $pageText }
        $bitmap.Dispose(); $stream.Dispose(); $page.Dispose()
        Write-Output ($pdf.Name + ': ' + ($index + 1) + '/' + $document.PageCount)
    }
    @{ source_sha256 = $hash; engine = 'Windows.Media.Ocr/ru'; pages = $pages } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $output -Encoding UTF8
}
