<#
start.ps1 - 创建虚拟环境、安装依赖并运行开发服务器（PowerShell）

用法：在项目根目录运行：
    .\start.ps1
可选参数：-Reinstall（重新安装依赖）
#>

param([switch]$Reinstall)

if (-not (Test-Path .venv)) {
    Write-Host "创建虚拟环境 .venv..."
    python -m venv .venv
}

Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force
. .\.venv\Scripts\Activate.ps1

Write-Host "升级 pip 并安装依赖（如果需要）..."
python -m pip install --upgrade pip
if ($Reinstall) {
    pip install --force-reinstall -r requirements.txt
} else {
    pip install -r requirements.txt
}

if (-not (Test-Path .env)) {
    Write-Warning ".env file not found. Please create a .env containing DATABASE_URL, REDIS_URL and SECRET_KEY."
} else {
    Write-Host ".env detected, starting service..."
}

uvicorn main:app --reload --host 0.0.0.0 --port 8000
