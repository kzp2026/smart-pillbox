# ==============================================================
# 智能药盒 Streamlit 应用 — GitHub 部署脚本
# 用法：在安装 Git 后运行此脚本
# ==============================================================

param(
    [string]$GitHubRepoUrl = ""  # 例如: https://github.com/你的用户名/智能药盒.git
)

$ErrorActionPreference = "Stop"
Set-Location "D:\智能药盒"

# 1. 检查 Git 是否安装
Write-Host ">>> [1/4] 检查 Git..." -ForegroundColor Cyan
try {
    git --version 2>&1 | Out-Null
    Write-Host "Git 已安装: $(git --version)" -ForegroundColor Green
} catch {
    Write-Host "错误: 未找到 Git，请先安装: https://git-scm.com/download/win" -ForegroundColor Red
    exit 1
}

# 2. 初始化 Git 仓库
Write-Host ">>> [2/4] 初始化 Git 仓库..." -ForegroundColor Cyan
if (-not (Test-Path ".git")) {
    git init
    Write-Host "Git 仓库已初始化" -ForegroundColor Green
} else {
    Write-Host "Git 仓库已存在" -ForegroundColor Yellow
}

# 3. 添加所有文件并提交
Write-Host ">>> [3/4] 添加文件并提交..." -ForegroundColor Cyan
git add -A
git status --short

$commitMsg = "初始部署: 智能药盒用户评论分析与产品设计生成系统"
git commit -m $commitMsg
Write-Host "已提交: $commitMsg" -ForegroundColor Green

# 4. 推送到 GitHub
if ($GitHubRepoUrl) {
    Write-Host ">>> [4/4] 推送到 GitHub..." -ForegroundColor Cyan
    git remote remove origin 2>$null
    git remote add origin $GitHubRepoUrl
    git branch -M main
    git push -u origin main
    Write-Host "推送完成！" -ForegroundColor Green
} else {
    Write-Host ">>> [4/4] 请手动设置远程仓库并推送:" -ForegroundColor Yellow
    Write-Host "  1. 在 https://github.com/new 创建新仓库" -ForegroundColor White
    Write-Host "  2. 运行: git remote add origin <你的仓库URL>" -ForegroundColor White
    Write-Host "  3. 运行: git push -u origin main" -ForegroundColor White
}

Write-Host "`n=== 部署完成！下一步: Streamlit Cloud ===" -ForegroundColor Green
Write-Host "  打开 https://share.streamlit.io/ -> 用 GitHub 登录 -> New app" -ForegroundColor White
Write-Host "  选择仓库 -> Main file path: app.py -> Deploy!" -ForegroundColor White
