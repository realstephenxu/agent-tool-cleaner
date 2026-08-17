# Agent 工具清理助手

你是不是也装过很多 AI 编程/Agent 工具，后来不用了，却很难卸载干净？

这个工具可以帮你：

- **自动扫描**电脑上已安装的常见 AI Agent 工具
- **一键卸载**不需要的工具
- 卸载后由你决定：**保留配置残留**，还是**彻底清除残留**
- 支持 Windows、macOS、Linux

它适合普通用户，不需要懂命令行，也不需要安装第三方依赖。

---

## ✨ 功能特点

- 自动识别常见 Agent 工具，包括：
  - 命令行工具：Claude Code、Codex CLI、Gemini CLI、GitHub Copilot CLI、Aider、Open Interpreter、AutoGPT、OpenHands、Goose、Amp、OpenCode、Crush、Amazon Q、OpenClaw、ClawHub 等
  - 桌面软件：Cursor、Windsurf、Trae 等
  - VS Code 插件：Cline、Roo Code、Continue、Codex VS Code Extension 等
- 卸载时优先调用工具自己的官方卸载方式
- 卸载后可以只保留配置，也可以把配置、缓存、登录信息等残留一起清掉
- 所有危险操作都会先让你确认
- 支持 `--dry-run` 预览，不会误删

---

## 🚀 快速开始

### Windows 用户（最简单）

1. 下载本项目并解压
2. 双击 **`一键运行.bat`**
3. 在弹出的菜单中选择要执行的操作

> 前提：电脑上已经安装 Python 3.8 或更高版本。  
> 如果没有 Python，可以到 [python.org](https://www.python.org/downloads/) 下载安装。

### macOS / Linux 用户

打开终端，进入项目目录后运行：

```bash
python3 agent_tool_cleaner.py
```

同样会进入中文菜单。

---

## 📖 使用说明

运行后会出现菜单：

```text
1. 扫描已安装的 Agent 工具
2. 卸载 Agent 工具（可选择保留/清除残留）
3. 仅清理残留
0. 退出
```

### 1. 扫描

先扫描，看看电脑上发现了哪些 Agent 工具和残留文件。

### 2. 卸载

选择要卸载的工具，工具会先执行官方卸载，然后询问你是否清除残留：

- 选“否”：保留配置文件、登录状态、缓存等
- 选“是”：把这些残留一起删除

### 3. 仅清理残留

如果某个工具已经卸载了，但还剩下配置文件，可以用这个功能单独清理。

---

## 🖥️ 命令行高级用法

如果你习惯使用命令行，也可以这样用：

```bash
# 扫描
python agent_tool_cleaner.py scan

# 交互式卸载
python agent_tool_cleaner.py uninstall

# 只清理残留
python agent_tool_cleaner.py clean

# 先预览会执行哪些操作，不实际删除
python agent_tool_cleaner.py uninstall --dry-run

# 输出 JSON 格式的扫描结果
python agent_tool_cleaner.py scan --json
```

---

## 🔒 安全提示

- 请先运行“扫描”，确认工具识别结果后再卸载。
- “清除残留”会永久删除相关配置文件、登录状态、缓存和历史记录。
- 如果你不确定，建议先使用 `--dry-run` 预览。
- 重要数据请提前备份。

---

## 📦 支持平台

- Windows 10 / 11
- macOS
- Linux

## 📄 开源协议

MIT License
