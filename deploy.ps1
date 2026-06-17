# ==============================================================
# 产品设计生成系统 — GitHub 部署脚本
# ==============================================================

param(
    [string]$GitHubRepoUrl = ""
)

$ErrorActionPreference = "Stop"
Set-Location "D:\智能药盒"

Write-Host ">>> [1/4] 检查 Git..." -ForegroundColor Cyan
try { git --version 2>&1 | Out-Null; Write-Host "Git 已安装" -ForegroundColor Green }
catch { Write-Host "错误: 未找到 Git，请先安装 https://git-scm.com/download/win" -ForegroundColor Red; exit 1 }

Write-Host ">>> [2/4] 初始化 Git 仓库..." -ForegroundColor Cyan
if (-not (Test-Path ".git")) { git init; Write-Host "Git 仓库已初始化" -ForegroundColor Green }
else { Write-Host "Git 仓库已存在" -ForegroundColor Yellow }

Write-Host ">>> [3/4] 添加文件并提交..." -ForegroundColor Cyan
git add -A
git status --short
git commit -m "产品设计生成系统 - 初始部署"
Write-Host "已提交" -ForegroundColor Green

if ($GitHubRepoUrl) {
    Write-Host ">>> [4/4] 推送到 GitHub..." -ForegroundColor Cyan
    git remote remove origin 2>$null
    git remote add origin $GitHubRepoUrl
    git branch -M main
    git push -u origin main
    Write-Host "推送完成！" -ForegroundColor Green
} else {
    Write-Host ">>> [4/4] 手动推送:" -ForegroundColor Yellow
    Write-Host "  1. https://github.com/new 创建新仓库"
    Write-Host "  2. git remote add origin <仓库URL>"
    Write-Host "  3. git push -u origin main"
}

Write-Host "`n=== 下一步: Streamlit Cloud ===" -ForegroundColor Green
Write-Host "  https://share.streamlit.io/ -> GitHub 登录 -> New app"
Write-Host "  选择仓库 -> Main file path: app.py -> Deploy!"
