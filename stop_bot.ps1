# Скрипт остановки бота Avito Analytics
Write-Host "Остановка бота Avito Analytics..." -ForegroundColor Yellow
Write-Host ""

# Находим все процессы Python
$pythonProcesses = Get-Process python -ErrorAction SilentlyContinue

if (-not $pythonProcesses) {
    Write-Host "Процессы Python не найдены. Бот, вероятно, уже остановлен." -ForegroundColor Green
    exit
}

$botFound = $false

foreach ($proc in $pythonProcesses) {
    try {
        # Получаем командную строку процесса
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
        
        if ($cmdLine -and $cmdLine -match "main\.py") {
            Write-Host "Найден процесс бота с PID: $($proc.Id)" -ForegroundColor Cyan
            Stop-Process -Id $proc.Id -Force
            Write-Host "Бот успешно остановлен (PID: $($proc.Id))" -ForegroundColor Green
            $botFound = $true
        }
    } catch {
        # Игнорируем ошибки доступа к процессу
        continue
    }
}

if (-not $botFound) {
    Write-Host "Процесс бота (main.py) не найден. Возможно, бот уже остановлен." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Нажмите любую клавишу для выхода..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
