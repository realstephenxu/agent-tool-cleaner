#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent-tool-cleaner: scan and uninstall AI agent tools, with optional residue cleanup.

This is a safety-first CLI:
  * It only reads installation evidence during scan.
  * Destructive actions always ask for confirmation (unless --yes is given).
  * Use --dry-run to preview without changing anything.

Supported sources:
  * executables in PATH
  * npm / pip / pipx / brew global packages
  * Windows GUI install locations + registry uninstall entries
  * macOS /Applications and ~/Applications
  * Linux desktop entries
  * VS Code extensions
  * known per-tool config/data/cache directories
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

HOME = Path.home()
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# Make Chinese output display correctly in modern Windows terminals / double-click runs.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# --------------------------------------------------------------------------- #
# Tool registry
# --------------------------------------------------------------------------- #
# Fields:
#   detect.dirs              : paths under $HOME that indicate the tool (config/data/cache)
#   detect.windows_dirs      : paths under %APPDATA% / %LOCALAPPDATA% / %PROGRAMFILES%
#   detect.mac_apps          : app bundle names under /Applications or ~/Applications
#   detect.linux_desktop     : .desktop file names under /usr/share/applications or ~/.local/share/applications
#   uninstall.dirs           : installation directories to remove when uninstalling (fallback for GUI apps)
#   remnants.dirs / files    : residue locations to remove during cleanup
TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "id": "claude-code",
        "name": "Claude Code",
        "kind": "CLI",
        "description": "Anthropic's CLI coding agent",
        "detect": {
            "commands": ["claude"],
            "npm": ["@anthropic-ai/claude-code"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/Claude", "AppData/Local/Programs/claude"],
            "mac_apps": ["Claude.app"],
            "linux_desktop": ["claude.desktop"],
            "dirs": [".claude", ".config/claude", ".local/share/claude", ".cache/claude"],
            "vscode_extensions": ["anthropic.claude-code"],
        },
        "uninstall": {
            "npm": ["@anthropic-ai/claude-code"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": ["Claude Code"],
            "dirs": ["AppData/Local/Programs/claude"],
        },
        "remnants": {
            "dirs": [".claude", ".config/claude", ".local/share/claude", ".cache/claude"],
            "files": [".claude.json", ".claude.json.backup", ".claude/.credentials.json"],
            "windows_dirs": ["AppData/Roaming/Claude", "AppData/Local/Programs/claude"],
            "mac_apps": ["Claude.app"],
            "linux_desktop": ["claude.desktop"],
        },
    },
    {
        "id": "codex",
        "name": "Codex CLI",
        "kind": "CLI",
        "description": "OpenAI's terminal coding agent",
        "detect": {
            "commands": ["codex"],
            "npm": ["@openai/codex"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/Codex", "AppData/Local/Codex"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".codex", ".config/codex", ".local/share/codex", ".cache/codex"],
            "vscode_extensions": ["openai.chatgpt"],
        },
        "uninstall": {
            "npm": ["@openai/codex"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": ["Codex"],
            "dirs": ["AppData/Local/Codex"],
        },
        "remnants": {
            "dirs": [".codex", ".config/codex", ".local/share/codex", ".cache/codex"],
            "files": [".codex.json", ".codex/auth.json", ".codex/config.toml"],
            "windows_dirs": ["AppData/Roaming/Codex", "AppData/Local/Codex"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },
    {
        "id": "gemini-cli",
        "name": "Gemini CLI",
        "kind": "CLI",
        "description": "Google's Gemini command-line agent",
        "detect": {
            "commands": ["gemini"],
            "npm": ["@google/gemini-cli"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/Gemini", "AppData/Local/Gemini"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".gemini", ".config/gemini", ".local/share/gemini", ".cache/gemini"],
            "vscode_extensions": [],
        },
        "uninstall": {
            "npm": ["@google/gemini-cli"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": ["Gemini CLI"],
            "dirs": ["AppData/Local/Gemini"],
        },
        "remnants": {
            "dirs": [".gemini", ".config/gemini", ".local/share/gemini", ".cache/gemini"],
            "files": [".gemini/settings.json"],
            "windows_dirs": ["AppData/Roaming/Gemini", "AppData/Local/Gemini"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },
    {
        "id": "github-copilot-cli",
        "name": "GitHub Copilot CLI",
        "kind": "CLI",
        "description": "GitHub Copilot in the terminal",
        "detect": {
            "commands": ["github-copilot-cli", "copilot"],
            "npm": ["@github/copilot", "@github/copilot-cli"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/GitHub Copilot", "AppData/Local/GitHub Copilot"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".copilot", ".config/github-copilot", ".config/github-copilot-cli"],
            "vscode_extensions": ["github.copilot", "github.copilot-chat"],
        },
        "uninstall": {
            "npm": ["@github/copilot", "@github/copilot-cli"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": ["GitHub Copilot CLI"],
            "dirs": [],
        },
        "remnants": {
            "dirs": [".copilot", ".config/github-copilot", ".config/github-copilot-cli"],
            "files": [".copilot.json"],
            "windows_dirs": ["AppData/Roaming/GitHub Copilot", "AppData/Local/GitHub Copilot"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },

    {
        "id": "aider",
        "name": "Aider",
        "kind": "CLI",
        "description": "AI pair programming in your terminal",
        "detect": {
            "commands": ["aider"],
            "npm": [],
            "pip": ["aider-chat", "aider"],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/aider", "AppData/Local/aider"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".aider", ".config/aider", ".local/share/aider", ".cache/aider"],
            "vscode_extensions": ["aider.aider"],
        },
        "uninstall": {
            "npm": [],
            "pip": ["aider-chat", "aider"],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": [],
            "dirs": [],
        },
        "remnants": {
            "dirs": [".aider", ".config/aider", ".local/share/aider", ".cache/aider"],
            "files": [".aider.model.settings.yml", ".aider.history"],
            "windows_dirs": ["AppData/Roaming/aider", "AppData/Local/aider"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },
    {
        "id": "open-interpreter",
        "name": "Open Interpreter",
        "kind": "CLI",
        "description": "Natural language interface for your computer",
        "detect": {
            "commands": ["interpreter", "open-interpreter"],
            "npm": [],
            "pip": ["open-interpreter"],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/open-interpreter", "AppData/Local/open-interpreter"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".local/share/interpreter", ".config/interpreter", ".cache/interpreter"],
            "vscode_extensions": [],
        },
        "uninstall": {
            "npm": [],
            "pip": ["open-interpreter"],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": [],
            "dirs": [],
        },
        "remnants": {
            "dirs": [".local/share/interpreter", ".config/interpreter", ".cache/interpreter"],
            "files": [],
            "windows_dirs": ["AppData/Roaming/open-interpreter", "AppData/Local/open-interpreter"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },
    {
        "id": "autogpt",
        "name": "AutoGPT",
        "kind": "CLI",
        "description": "Autonomous GPT agent platform",
        "detect": {
            "commands": ["autogpt", "auto-gpt"],
            "npm": [],
            "pip": ["auto-gpt", "agpt"],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/AutoGPT", "AppData/Local/AutoGPT"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".autogpt", ".config/autogpt", ".local/share/autogpt", ".cache/autogpt"],
            "vscode_extensions": [],
        },
        "uninstall": {
            "npm": [],
            "pip": ["auto-gpt", "agpt"],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": [],
            "dirs": [],
        },
        "remnants": {
            "dirs": [".autogpt", ".config/autogpt", ".local/share/autogpt", ".cache/autogpt"],
            "files": [".autogpt", "autogpt.json"],
            "windows_dirs": ["AppData/Roaming/AutoGPT", "AppData/Local/AutoGPT"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },
    {
        "id": "openhands",
        "name": "OpenHands",
        "kind": "CLI",
        "description": "AI software development agent platform",
        "detect": {
            "commands": ["openhands", "codeact"],
            "npm": [],
            "pip": ["openhands", "openhands-ai"],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/OpenHands", "AppData/Local/OpenHands"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".openhands", ".config/openhands", ".local/share/openhands", ".cache/openhands"],
            "vscode_extensions": ["OpenHands.openhands"],
        },
        "uninstall": {
            "npm": [],
            "pip": ["openhands", "openhands-ai"],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": [],
            "dirs": [],
        },
        "remnants": {
            "dirs": [".openhands", ".config/openhands", ".local/share/openhands", ".cache/openhands"],
            "files": [],
            "windows_dirs": ["AppData/Roaming/OpenHands", "AppData/Local/OpenHands"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },
    {
        "id": "goose",
        "name": "Goose",
        "kind": "CLI",
        "description": "Open-source AI agent by Block",
        "detect": {
            "commands": ["goose"],
            "npm": ["goose"],
            "pip": [],
            "brew": ["goose"],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/goose", "AppData/Local/goose"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".config/goose", ".local/share/goose", ".cache/goose"],
            "vscode_extensions": ["block.goose"],
        },
        "uninstall": {
            "npm": ["goose"],
            "pip": [],
            "brew": ["goose"],
            "cask": [],
            "windows_uninstall_names": ["Goose"],
            "dirs": [],
        },
        "remnants": {
            "dirs": [".config/goose", ".local/share/goose", ".cache/goose"],
            "files": [],
            "windows_dirs": ["AppData/Roaming/goose", "AppData/Local/goose"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },

    {
        "id": "amp",
        "name": "Amp",
        "kind": "CLI",
        "description": "Sourcegraph's terminal AI coding agent",
        "detect": {
            "commands": ["amp"],
            "npm": ["@sourcegraph/amp"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/amp", "AppData/Local/amp"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".amp", ".config/amp", ".local/share/amp", ".cache/amp"],
            "vscode_extensions": ["sourcegraph.amp"],
        },
        "uninstall": {
            "npm": ["@sourcegraph/amp"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": [],
            "dirs": [],
        },
        "remnants": {
            "dirs": [".amp", ".config/amp", ".local/share/amp", ".cache/amp"],
            "files": [],
            "windows_dirs": ["AppData/Roaming/amp", "AppData/Local/amp"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },
    {
        "id": "opencode",
        "name": "OpenCode",
        "kind": "CLI",
        "description": "Open-source AI coding agent for the terminal",
        "detect": {
            "commands": ["opencode"],
            "npm": ["opencode-ai"],
            "pip": [],
            "brew": ["opencode"],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/opencode", "AppData/Local/opencode"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".opencode", ".config/opencode", ".local/share/opencode", ".cache/opencode"],
            "vscode_extensions": ["sst.opencode"],
        },
        "uninstall": {
            "npm": ["opencode-ai"],
            "pip": [],
            "brew": ["opencode"],
            "cask": [],
            "windows_uninstall_names": ["OpenCode"],
            "dirs": [],
        },
        "remnants": {
            "dirs": [".opencode", ".config/opencode", ".local/share/opencode", ".cache/opencode"],
            "files": [".opencode.json"],
            "windows_dirs": ["AppData/Roaming/opencode", "AppData/Local/opencode"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },
    {
        "id": "crush",
        "name": "Crush",
        "kind": "CLI",
        "description": "Charm's terminal AI agent",
        "detect": {
            "commands": ["crush"],
            "npm": ["@charmverse/crush"],
            "pip": [],
            "brew": ["crush"],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/crush", "AppData/Local/crush"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".crush", ".config/crush", ".local/share/crush", ".cache/crush"],
            "vscode_extensions": [],
        },
        "uninstall": {
            "npm": ["@charmverse/crush"],
            "pip": [],
            "brew": ["crush"],
            "cask": [],
            "windows_uninstall_names": [],
            "dirs": [],
        },
        "remnants": {
            "dirs": [".crush", ".config/crush", ".local/share/crush", ".cache/crush"],
            "files": [],
            "windows_dirs": ["AppData/Roaming/crush", "AppData/Local/crush"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },
    {
        "id": "cline",
        "name": "Cline",
        "kind": "Plugin",
        "description": "VS Code autonomous coding assistant",
        "detect": {
            "commands": [],
            "npm": [],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev", "AppData/Roaming/Cline"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".cline", ".config/cline"],
            "vscode_extensions": ["saoudrizwan.claude-dev"],
        },
        "uninstall": {
            "npm": [],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": [],
            "dirs": [],
        },
        "remnants": {
            "dirs": [".cline", ".config/cline"],
            "files": [],
            "windows_dirs": ["AppData/Roaming/Code/User/globalStorage/saoudrizwan.claude-dev", "AppData/Roaming/Cline"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },

    {
        "id": "roo-code",
        "name": "Roo Code",
        "kind": "Plugin",
        "description": "VS Code AI coding agent (formerly Roo Cline)",
        "detect": {
            "commands": [],
            "npm": [],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/Code/User/globalStorage/rooveterinaryinc.roo-cline", "AppData/Roaming/Roo Code"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".roo", ".config/roo"],
            "vscode_extensions": ["rooveterinaryinc.roo-cline"],
        },
        "uninstall": {
            "npm": [],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": [],
            "dirs": [],
        },
        "remnants": {
            "dirs": [".roo", ".config/roo"],
            "files": [],
            "windows_dirs": ["AppData/Roaming/Code/User/globalStorage/rooveterinaryinc.roo-cline", "AppData/Roaming/Roo Code"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },
    {
        "id": "continue",
        "name": "Continue",
        "kind": "Plugin",
        "description": "Open-source AI code assistant in VS Code/JetBrains",
        "detect": {
            "commands": ["continue"],
            "npm": [],
            "pip": ["continuedev"],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/Code/User/globalStorage/continue.continue", "AppData/Roaming/Continue"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [".continue", ".config/continue"],
            "vscode_extensions": ["continue.continue"],
        },
        "uninstall": {
            "npm": [],
            "pip": ["continuedev"],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": [],
            "dirs": [],
        },
        "remnants": {
            "dirs": [".continue", ".config/continue"],
            "files": [],
            "windows_dirs": ["AppData/Roaming/Code/User/globalStorage/continue.continue", "AppData/Roaming/Continue"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },
    {
        "id": "cursor",
        "name": "Cursor",
        "kind": "GUI",
        "description": "AI-powered code editor",
        "detect": {
            "commands": ["cursor"],
            "npm": [],
            "pip": [],
            "brew": ["cursor"],
            "cask": ["cursor"],
            "windows_dirs": ["AppData/Local/Programs/cursor", "AppData/Local/Programs/Cursor", "AppData/Roaming/Cursor"],
            "mac_apps": ["Cursor.app"],
            "linux_desktop": ["cursor.desktop"],
            "dirs": [".cursor", ".config/Cursor", ".config/cursor"],
            "vscode_extensions": [],
        },
        "uninstall": {
            "npm": [],
            "pip": [],
            "brew": [],
            "cask": ["cursor"],
            "windows_uninstall_names": ["Cursor"],
            "dirs": ["AppData/Local/Programs/cursor", "AppData/Local/Programs/Cursor"],
        },
        "remnants": {
            "dirs": [".cursor", ".config/Cursor", ".config/cursor"],
            "files": [".cursor/.lastRun", ".cursor-tutor"],
            "windows_dirs": ["AppData/Roaming/Cursor", "AppData/Local/Cursor"],
            "mac_apps": ["Cursor.app"],
            "linux_desktop": ["cursor.desktop"],
        },
    },

    {
        "id": "windsurf",
        "name": "Windsurf",
        "kind": "GUI",
        "description": "Agentic AI IDE by Codeium",
        "detect": {
            "commands": ["windsurf"],
            "npm": [],
            "pip": [],
            "brew": [],
            "cask": ["windsurf"],
            "windows_dirs": ["AppData/Local/Programs/Windsurf", "AppData/Roaming/Windsurf", "AppData/Local/Windsurf"],
            "mac_apps": ["Windsurf.app"],
            "linux_desktop": ["windsurf.desktop"],
            "dirs": [".codeium", ".config/Windsurf", ".config/windsurf"],
            "vscode_extensions": ["codeium.windsurf"],
        },
        "uninstall": {
            "npm": [],
            "pip": [],
            "brew": [],
            "cask": ["windsurf"],
            "windows_uninstall_names": ["Windsurf"],
            "dirs": ["AppData/Local/Programs/Windsurf"],
        },
        "remnants": {
            "dirs": [".codeium", ".config/Windsurf", ".config/windsurf"],
            "files": [".codeium"],
            "windows_dirs": ["AppData/Roaming/Windsurf", "AppData/Local/Windsurf"],
            "mac_apps": ["Windsurf.app"],
            "linux_desktop": ["windsurf.desktop"],
        },
    },
    {
        "id": "trae",
        "name": "Trae",
        "kind": "GUI",
        "description": "ByteDance's AI-native IDE",
        "detect": {
            "commands": ["trae"],
            "npm": [],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Local/Programs/Trae", "AppData/Roaming/Trae", "AppData/Local/Trae"],
            "mac_apps": ["Trae.app"],
            "linux_desktop": ["trae.desktop"],
            "dirs": [".trae", ".config/Trae", ".config/trae"],
            "vscode_extensions": [],
        },
        "uninstall": {
            "npm": [],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": ["Trae"],
            "dirs": ["AppData/Local/Programs/Trae"],
        },
        "remnants": {
            "dirs": [".trae", ".config/Trae", ".config/trae"],
            "files": [],
            "windows_dirs": ["AppData/Roaming/Trae", "AppData/Local/Trae"],
            "mac_apps": ["Trae.app"],
            "linux_desktop": ["trae.desktop"],
        },
    },
    {
        "id": "amazon-q",
        "name": "Amazon Q",
        "kind": "CLI",
        "description": "AWS's AI assistant / coding agent",
        "detect": {
            "commands": ["q", "amazon-q"],
            "npm": ["@aws/amazon-q"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/Amazon Q", "AppData/Local/Amazon Q"],
            "mac_apps": ["Amazon Q.app"],
            "linux_desktop": ["amazon-q.desktop"],
            "dirs": [".aws/amazonq", ".config/amazonq", ".local/share/amazon-q"],
            "vscode_extensions": ["amazonwebservices.amazon-q-vscode"],
        },
        "uninstall": {
            "npm": ["@aws/amazon-q"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": ["Amazon Q"],
            "dirs": [],
        },
        "remnants": {
            "dirs": [".aws/amazonq", ".config/amazonq", ".local/share/amazon-q"],
            "files": [],
            "windows_dirs": ["AppData/Roaming/Amazon Q", "AppData/Local/Amazon Q"],
            "mac_apps": ["Amazon Q.app"],
            "linux_desktop": ["amazon-q.desktop"],
        },
    },
    {
        "id": "openai-codex-vscode",
        "name": "Codex VS Code Extension",
        "kind": "Plugin",
        "description": "OpenAI Codex extension for VS Code",
        "detect": {
            "commands": [],
            "npm": [],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/Code/User/globalStorage/openai.chatgpt"],
            "mac_apps": [],
            "linux_desktop": [],
            "dirs": [],
            "vscode_extensions": ["openai.chatgpt"],
        },
        "uninstall": {
            "npm": [],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": [],
            "dirs": [],
        },
        "remnants": {
            "dirs": [],
            "files": [],
            "windows_dirs": ["AppData/Roaming/Code/User/globalStorage/openai.chatgpt"],
            "mac_apps": [],
            "linux_desktop": [],
        },
    },
    {
        "id": "openclaw",
        "name": "OpenClaw",
        "kind": "CLI",
        "description": "Open-source personal AI assistant (Claw family)",
        "detect": {
            "commands": ["openclaw", "oc"],
            "npm": ["openclaw", "@openclaw/openclaw"],
            "pip": [],
            "brew": ["openclaw"],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/OpenClaw", "AppData/Local/OpenClaw", "AppData/Roaming/.openclaw"],
            "mac_apps": [],
            "linux_desktop": ["openclaw.desktop"],
            "dirs": [".openclaw", ".config/openclaw", ".local/share/openclaw", ".cache/openclaw"],
            "vscode_extensions": [],
        },
        "uninstall": {
            "npm": ["openclaw", "@openclaw/openclaw"],
            "pip": [],
            "brew": ["openclaw"],
            "cask": [],
            "windows_uninstall_names": ["OpenClaw"],
            "dirs": ["AppData/Local/OpenClaw"],
        },
        "remnants": {
            "dirs": [".openclaw", ".config/openclaw", ".local/share/openclaw", ".cache/openclaw"],
            "files": [".openclaw.json", ".openclaw/.credentials.json"],
            "windows_dirs": ["AppData/Roaming/OpenClaw", "AppData/Local/OpenClaw", "AppData/Roaming/.openclaw"],
            "mac_apps": [],
            "linux_desktop": ["openclaw.desktop"],
        },
    },
    {
        "id": "clawhub",
        "name": "ClawHub",
        "kind": "CLI",
        "description": "Plugin/extension hub for the Claw family",
        "detect": {
            "commands": ["clawhub"],
            "npm": ["clawhub", "@openclaw/clawhub"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_dirs": ["AppData/Roaming/ClawHub", "AppData/Local/ClawHub", "AppData/Roaming/.clawhub"],
            "mac_apps": [],
            "linux_desktop": ["clawhub.desktop"],
            "dirs": [".clawhub", ".config/clawhub", ".local/share/clawhub", ".cache/clawhub"],
            "vscode_extensions": [],
        },
        "uninstall": {
            "npm": ["clawhub", "@openclaw/clawhub"],
            "pip": [],
            "brew": [],
            "cask": [],
            "windows_uninstall_names": ["ClawHub"],
            "dirs": ["AppData/Local/ClawHub"],
        },
        "remnants": {
            "dirs": [".clawhub", ".config/clawhub", ".local/share/clawhub", ".cache/clawhub"],
            "files": [".clawhub.json"],
            "windows_dirs": ["AppData/Roaming/ClawHub", "AppData/Local/ClawHub", "AppData/Roaming/.clawhub"],
            "mac_apps": [],
            "linux_desktop": ["clawhub.desktop"],
        },
    },
]


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def eprint(*args: Any, **kwargs: Any) -> None:
    print(*args, file=sys.stderr, **kwargs)


def path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def is_within_home(path: Path) -> bool:
    """Safety check: refuse to delete paths that resolve outside the user home."""
    try:
        resolved = path.resolve()
        home = HOME.resolve()
        return str(resolved).lower().startswith(str(home).lower())
    except OSError:
        return False


def safe_remove(path: Path) -> bool:
    """Remove a file or directory. Returns True if something was removed."""
    if not path_exists(path):
        return False
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True
    except (OSError, PermissionError) as exc:
        eprint(f"  ! failed to remove {path}: {exc}")
        return False


# --------------------------------------------------------------------------- #
# Package / environment scanners (cached)
# --------------------------------------------------------------------------- #

_cache: Dict[str, Any] = {}


def run_cmd(cmd: Sequence[str], timeout: int = 30) -> Optional[str]:
    """Run a command, return stdout or None on failure. Suppresses errors."""
    try:
        proc = subprocess.run(
            list(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.stdout if proc.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def get_npm_global_packages() -> Dict[str, str]:
    if "npm" in _cache:
        return _cache["npm"]
    packages: Dict[str, str] = {}
    out = run_cmd(["npm", "ls", "-g", "--depth=0", "--json"], timeout=60)
    if out:
        try:
            data = json.loads(out)
            deps = data.get("dependencies", {}) or {}
            for name, info in deps.items():
                packages[name.lower()] = info.get("version", "")
        except (json.JSONDecodeError, AttributeError):
            pass
    _cache["npm"] = packages
    return packages


def get_pip_packages() -> Dict[str, str]:
    if "pip" in _cache:
        return _cache["pip"]
    packages: Dict[str, str] = {}
    py = sys.executable or "python"
    out = run_cmd([py, "-m", "pip", "list", "--format=json", "--disable-pip-version-check"], timeout=60)
    if out:
        try:
            for item in json.loads(out):
                packages[item.get("name", "").lower()] = item.get("version", "")
        except (json.JSONDecodeError, AttributeError):
            pass
    _cache["pip"] = packages
    return packages


def get_pipx_packages() -> Dict[str, str]:
    if "pipx" in _cache:
        return _cache["pipx"]
    packages: Dict[str, str] = {}
    out = run_cmd(["pipx", "list", "--json"], timeout=60)
    if out:
        try:
            data = json.loads(out)
            venvs = data.get("venvs", {}) or {}
            for name, info in venvs.items():
                packages[name.lower()] = info.get("metadata", {}).get("main_package", {}).get("package_version", "")
        except (json.JSONDecodeError, AttributeError):
            pass
    _cache["pipx"] = packages
    return packages


def get_uv_tool_packages() -> Dict[str, str]:
    if "uv" in _cache:
        return _cache["uv"]
    packages: Dict[str, str] = {}
    out = run_cmd(["uv", "tool", "list"], timeout=60)
    if out:
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("-"):
                continue
            # Typical line: "toolname v0.1.0" or "toolname"
            parts = line.split()
            if parts:
                packages[parts[0].lower()] = parts[1] if len(parts) > 1 else ""
    _cache["uv"] = packages
    return packages


def get_brew_packages() -> Dict[str, Dict[str, bool]]:
    if "brew" in _cache:
        return _cache["brew"]
    result: Dict[str, Dict[str, bool]] = {"formula": set(), "cask": set()}
    formulas = run_cmd(["brew", "list", "--formula"], timeout=60)
    if formulas:
        for line in formulas.splitlines():
            name = line.strip()
            if name:
                result["formula"].add(name.lower())
    casks = run_cmd(["brew", "list", "--cask"], timeout=60)
    if casks:
        for line in casks.splitlines():
            name = line.strip()
            if name:
                result["cask"].add(name.lower())
    _cache["brew"] = result
    return result


def get_vscode_extensions() -> set:
    if "vscode" in _cache:
        return _cache["vscode"]
    exts: set = set()
    out = run_cmd(["code", "--list-extensions"], timeout=30)
    if out:
        for line in out.splitlines():
            ext = line.strip().lower()
            if ext:
                exts.add(ext)
    # Also scan the standard local extension folders without requiring `code` on PATH.
    candidates = [
        HOME / ".vscode" / "extensions",
        HOME / ".vscode-server" / "extensions",
    ]
    if IS_WINDOWS:
        candidates.append(Path(os.environ.get("USERPROFILE", "")) / ".vscode" / "extensions")
    for base in candidates:
        if path_exists(base):
            try:
                for child in base.iterdir():
                    if child.is_dir():
                        # VS Code extension dirs look like "publisher.name-version"
                        parts = child.name.split("-")
                        if len(parts) >= 2:
                            exts.add((parts[0] + "." + parts[1]).lower())
            except OSError:
                pass
    _cache["vscode"] = exts
    return exts


# --------------------------------------------------------------------------- #
# Windows registry uninstall scanner
# --------------------------------------------------------------------------- #

def get_windows_uninstall_entries() -> List[Dict[str, str]]:
    """Return a list of installed program entries from the Windows registry."""
    if not IS_WINDOWS or "winreg_entries" in _cache:
        return _cache.get("winreg_entries", [])
    entries: List[Dict[str, str]] = []
    try:
        import winreg
    except ImportError:
        _cache["winreg_entries"] = entries
        return entries

    root_paths = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]
    for root_path in root_paths:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root_path)
        except OSError:
            continue
        try:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, subkey_name) as subkey:
                        entry: Dict[str, str] = {}
                        for value_name in ("DisplayName", "DisplayVersion", "UninstallString", "QuietUninstallString", "InstallLocation"):
                            try:
                                entry[value_name] = str(winreg.QueryValueEx(subkey, value_name)[0])
                            except OSError:
                                entry[value_name] = ""
                        if entry.get("DisplayName"):
                            entries.append(entry)
                except OSError:
                    continue
        finally:
            winreg.CloseKey(key)

    # HKCU uninstall entries (per-user apps)
    try:
        import winreg
        for root_path in root_paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, root_path)
            except OSError:
                continue
            try:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            entry: Dict[str, str] = {}
                            for value_name in ("DisplayName", "DisplayVersion", "UninstallString", "QuietUninstallString", "InstallLocation"):
                                try:
                                    entry[value_name] = str(winreg.QueryValueEx(subkey, value_name)[0])
                                except OSError:
                                    entry[value_name] = ""
                            if entry.get("DisplayName"):
                                entries.append(entry)
                    except OSError:
                        continue
            finally:
                winreg.CloseKey(key)
    except OSError:
        pass

    _cache["winreg_entries"] = entries
    return entries


def find_windows_uninstaller(names: Sequence[str]) -> Optional[Dict[str, str]]:
    if not IS_WINDOWS:
        return None
    entries = get_windows_uninstall_entries()
    lowered_names = [n.lower() for n in names if n]
    for entry in entries:
        display = (entry.get("DisplayName") or "").lower()
        if any(n and n in display for n in lowered_names):
            return entry
    return None


# --------------------------------------------------------------------------- #
# Path resolution helpers
# --------------------------------------------------------------------------- #

def resolve_windows_path(rel: str) -> List[Path]:
    """Resolve a path like 'AppData/Local/Programs/cursor' to concrete absolute paths."""
    if not IS_WINDOWS:
        return []
    rel = rel.replace("\\", "/")
    bases = []
    appdata = os.environ.get("APPDATA")
    localappdata = os.environ.get("LOCALAPPDATA")
    programfiles = os.environ.get("PROGRAMFILES")
    programfiles_x86 = os.environ.get("PROGRAMFILES(X86)")
    userprofile = os.environ.get("USERPROFILE")
    if appdata:
        bases.append(Path(appdata))
    if localappdata:
        bases.append(Path(localappdata))
    if programfiles:
        bases.append(Path(programfiles))
    if programfiles_x86:
        bases.append(Path(programfiles_x86))
    if userprofile:
        bases.append(Path(userprofile))
    results = []
    for base in bases:
        p = base / rel
        if path_exists(p):
            results.append(p)
    return results


def resolve_home_dirs(rel_list: Sequence[str]) -> List[Path]:
    results = []
    for rel in rel_list:
        if not rel:
            continue
        p = HOME / rel.replace("\\", "/")
        if path_exists(p):
            results.append(p)
    return results


def resolve_mac_apps(apps: Sequence[str]) -> List[Path]:
    if not IS_MAC:
        return []
    results = []
    for app in apps:
        for base in [Path("/Applications"), HOME / "Applications"]:
            p = base / app
            if path_exists(p):
                results.append(p)
    return results


def resolve_linux_desktops(desktops: Sequence[str]) -> List[Path]:
    if not IS_LINUX:
        return []
    results = []
    for name in desktops:
        for base in [Path("/usr/share/applications"), HOME / ".local/share/applications"]:
            p = base / name
            if path_exists(p):
                results.append(p)
    return results


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #

@dataclass
class Detection:
    definition: Dict[str, Any]
    detected: bool = False
    status: str = "not-detected"  # installed | residue-only | not-detected
    evidence: List[Dict[str, str]] = field(default_factory=list)
    remnant_paths: List[Path] = field(default_factory=list)
    install_paths: List[Path] = field(default_factory=list)
    windows_uninstaller: Optional[Dict[str, str]] = None

    @property
    def id(self) -> str:
        return self.definition["id"]

    @property
    def name(self) -> str:
        return self.definition["name"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.definition.get("kind", ""),
            "description": self.definition.get("description", ""),
            "status": self.status,
            "detected": self.detected,
            "evidence": self.evidence,
            "remnant_paths": [str(p) for p in self.remnant_paths],
            "install_paths": [str(p) for p in self.install_paths],
            "windows_uninstaller": self.windows_uninstaller,
        }


def _add_evidence(det: Detection, etype: str, value: str) -> None:
    det.evidence.append({"type": etype, "value": value})


def detect_tool(defn: Dict[str, Any]) -> Detection:
    det = Detection(definition=defn)
    detect = defn.get("detect", {})
    remnants = defn.get("remnants", {})

    # Commands on PATH
    for cmd in detect.get("commands", []):
        found = shutil.which(cmd)
        if found:
            det.detected = True
            det.status = "installed"
            _add_evidence(det, "command", f"{cmd} -> {found}")

    # npm global packages
    npm_pkgs = get_npm_global_packages()
    for pkg in detect.get("npm", []):
        if pkg.lower() in npm_pkgs:
            det.detected = True
            det.status = "installed"
            _add_evidence(det, "npm", f"{pkg}@{npm_pkgs[pkg.lower()]}")

    # pip packages
    pip_pkgs = get_pip_packages()
    for pkg in detect.get("pip", []):
        if pkg.lower() in pip_pkgs:
            det.detected = True
            det.status = "installed"
            _add_evidence(det, "pip", f"{pkg}@{pip_pkgs[pkg.lower()]}")

    # pipx packages
    pipx_pkgs = get_pipx_packages()
    for pkg in detect.get("pip", []):
        if pkg.lower() in pipx_pkgs:
            det.detected = True
            det.status = "installed"
            _add_evidence(det, "pipx", f"{pkg}@{pipx_pkgs[pkg.lower()]}")

    # uv tools
    uv_pkgs = get_uv_tool_packages()
    for pkg in detect.get("pip", []):
        if pkg.lower() in uv_pkgs:
            det.detected = True
            det.status = "installed"
            _add_evidence(det, "uv", f"{pkg}@{uv_pkgs[pkg.lower()]}")

    # brew
    brew = get_brew_packages()
    for pkg in detect.get("brew", []):
        if pkg.lower() in brew["formula"]:
            det.detected = True
            det.status = "installed"
            _add_evidence(det, "brew", f"{pkg}")
    for pkg in detect.get("cask", []):
        if pkg.lower() in brew["cask"]:
            det.detected = True
            det.status = "installed"
            _add_evidence(det, "brew-cask", f"{pkg}")

    # Windows paths. We only treat program install directories as proof of
    # installation; AppData/Roaming style paths are config/residue and are
    # collected later in the remnant scan.
    for rel in detect.get("windows_dirs", []):
        for p in resolve_windows_path(rel):
            det.install_paths.append(p)
            lower = str(p).lower()
            if "programs" in lower or "program files" in lower:
                det.detected = True
                det.status = "installed"
                _add_evidence(det, "windows-path", str(p))

    # macOS apps
    for app in detect.get("mac_apps", []):
        for p in resolve_mac_apps([app]):
            det.detected = True
            det.status = "installed"
            det.install_paths.append(p)
            _add_evidence(det, "mac-app", str(p))

    # Linux desktop files
    for desktop in detect.get("linux_desktop", []):
        for p in resolve_linux_desktops([desktop]):
            det.detected = True
            det.status = "installed"
            det.install_paths.append(p)
            _add_evidence(det, "linux-desktop", str(p))

    # Home dirs / config dirs are treated as residue, not as proof of installation.
    # They are picked up again in the remnant scan below.

    # VS Code extensions
    vscode_exts = get_vscode_extensions()
    for ext in detect.get("vscode_extensions", []):
        if ext.lower() in vscode_exts:
            det.detected = True
            det.status = "installed"
            _add_evidence(det, "vscode-extension", ext)

    # Windows uninstaller evidence
    uninstall_names = defn.get("uninstall", {}).get("windows_uninstall_names", [])
    if uninstall_names:
        entry = find_windows_uninstaller(uninstall_names)
        if entry:
            det.detected = True
            det.status = "installed"
            det.windows_uninstaller = entry
            _add_evidence(det, "windows-uninstall", entry.get("DisplayName", "Unknown"))

    # Remnant paths (even if main installation is gone)
    remnant_paths: List[Path] = []
    for rel in remnants.get("dirs", []):
        for p in resolve_home_dirs([rel]):
            if p not in remnant_paths:
                remnant_paths.append(p)
    for rel in remnants.get("files", []):
        for p in resolve_home_dirs([rel]):
            if p not in remnant_paths:
                remnant_paths.append(p)
    for rel in remnants.get("windows_dirs", []):
        for p in resolve_windows_path(rel):
            if p not in remnant_paths:
                remnant_paths.append(p)
    for app in remnants.get("mac_apps", []):
        for p in resolve_mac_apps([app]):
            if p not in remnant_paths:
                remnant_paths.append(p)
    for desktop in remnants.get("linux_desktop", []):
        for p in resolve_linux_desktops([desktop]):
            if p not in remnant_paths:
                remnant_paths.append(p)
    det.remnant_paths = remnant_paths

    if remnant_paths and not det.detected:
        det.detected = True
        det.status = "residue-only"
        _add_evidence(det, "residue", f"{len(remnant_paths)} path(s) found")

    return det


def scan_all() -> List[Detection]:
    return [detect_tool(d) for d in TOOL_DEFINITIONS]


# --------------------------------------------------------------------------- #
# Uninstall action builders
# --------------------------------------------------------------------------- #

def _build_remove_path_actions(paths: Iterable[Path]) -> List[Dict[str, Any]]:
    actions = []
    for p in paths:
        if path_exists(p):
            actions.append({
                "description": f"Delete {p}",
                "kind": "remove_path",
                "path": str(p),
            })
    return actions


def build_uninstall_actions(det: Detection) -> List[Dict[str, Any]]:
    """Build actions that remove the main installation (not remnants)."""
    actions: List[Dict[str, Any]] = []
    un = det.definition.get("uninstall", {})

    for pkg in un.get("npm", []):
        actions.append({
            "description": f"npm uninstall -g {pkg}",
            "kind": "npm",
            "package": pkg,
        })
    for pkg in un.get("pip", []):
        actions.append({
            "description": f"python -m pip uninstall -y {pkg}",
            "kind": "pip",
            "package": pkg,
        })
    pipx_pkgs = get_pipx_packages()
    for pkg in un.get("pip", []):
        if pkg.lower() in pipx_pkgs:
            actions.append({
                "description": f"pipx uninstall {pkg}",
                "kind": "pipx",
                "package": pkg,
            })
    uv_pkgs = get_uv_tool_packages()
    for pkg in un.get("pip", []):
        if pkg.lower() in uv_pkgs:
            actions.append({
                "description": f"uv tool uninstall {pkg}",
                "kind": "uv",
                "package": pkg,
            })
    for pkg in un.get("brew", []):
        actions.append({
            "description": f"brew uninstall {pkg}",
            "kind": "brew",
            "package": pkg,
            "type": "formula",
        })
    for pkg in un.get("cask", []):
        actions.append({
            "description": f"brew uninstall --cask {pkg}",
            "kind": "brew",
            "package": pkg,
            "type": "cask",
        })

    # Official Windows uninstaller if present
    if det.windows_uninstaller:
        uninstall_str = det.windows_uninstaller.get("QuietUninstallString") or det.windows_uninstaller.get("UninstallString")
        if uninstall_str:
            actions.append({
                "description": f"Run official uninstaller: {uninstall_str}",
                "kind": "run",
                "command": uninstall_str,
            })

    # Install directory fallback for GUI apps / manually installed tools.
    # We intentionally do NOT delete AppData/Roaming or other config dirs here;
    # those are part of the optional residue cleanup step.
    for rel in un.get("dirs", []):
        for p in resolve_windows_path(rel):
            if path_exists(p):
                actions.append({
                    "description": f"Delete install directory {p}",
                    "kind": "remove_path",
                    "path": str(p),
                })
    # macOS .app bundles are the main installation, so remove them during uninstall.
    for p in det.install_paths:
        if p.name.lower().endswith(".app") and path_exists(p):
            actions.append({
                "description": f"Delete app bundle {p}",
                "kind": "remove_path",
                "path": str(p),
            })

    # Deduplicate
    seen = set()
    unique = []
    for a in actions:
        key = (a["kind"], a.get("package", ""), a.get("path", ""), a.get("command", ""))
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


def build_cleanup_actions(det: Detection) -> List[Dict[str, Any]]:
    """Build actions that remove the tool's remaining data/config/cache."""
    return _build_remove_path_actions(det.remnant_paths)


# --------------------------------------------------------------------------- #
# Action execution
# --------------------------------------------------------------------------- #

def execute_action(action: Dict[str, Any], dry_run: bool = False, yes: bool = False) -> bool:
    kind = action["kind"]
    desc = action["description"]
    print(f"  > {desc}")

    if dry_run:
        print("    [dry-run] skipped")
        return True

    if kind == "npm":
        ok = run_cmd(["npm", "uninstall", "-g", action["package"]]) is not None
        if not ok:
            eprint("  ! npm uninstall failed")
        return ok
    if kind == "pip":
        py = sys.executable or "python"
        ok = run_cmd([py, "-m", "pip", "uninstall", "-y", action["package"]]) is not None
        if not ok:
            eprint("  ! pip uninstall failed")
        return ok
    if kind == "pipx":
        ok = run_cmd(["pipx", "uninstall", action["package"]]) is not None
        if not ok:
            eprint("  ! pipx uninstall failed")
        return ok
    if kind == "uv":
        ok = run_cmd(["uv", "tool", "uninstall", action["package"]]) is not None
        if not ok:
            eprint("  ! uv tool uninstall failed")
        return ok
    if kind == "brew":
        if action.get("type") == "cask":
            ok = run_cmd(["brew", "uninstall", "--cask", action["package"]]) is not None
        else:
            ok = run_cmd(["brew", "uninstall", action["package"]]) is not None
        if not ok:
            eprint("  ! brew uninstall failed")
        return ok
    if kind == "run":
        # Registry uninstall strings can contain quoted paths + arguments.
        return subprocess.run(action["command"], shell=True, check=False).returncode == 0
    if kind == "remove_path":
        p = Path(action["path"])
        # Do not allow deleting filesystem roots or outside-home unless it's a known app dir.
        return safe_remove(p)
    eprint(f"  ! unknown action kind: {kind}")
    return False


def confirm(prompt: str, default: bool = False, yes: bool = False) -> bool:
    if yes:
        return True
    suffix = " [Y/n] " if default else " [y/N] "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes", "是", "确认", "确定")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def print_scan_table(detections: Sequence[Detection], show_all: bool = False) -> None:
    selected = detections if show_all else [d for d in detections if d.detected]
    if not selected:
        print("没有检测到已安装的 agent 工具（或残留）。")
        return

    print(f"\n检测到 {len(selected)} 个 agent 工具/残留：\n")
    for i, det in enumerate(selected, 1):
        status = "已安装" if det.status == "installed" else "仅残留"
        print(f"[{i:02d}] {det.name} ({det.definition.get('kind', '')}) - {status}")
        for ev in det.evidence[:8]:
            print(f"      - {ev['type']}: {ev['value']}")
        if len(det.evidence) > 8:
            print(f"      ... 还有 {len(det.evidence) - 8} 条证据")
        if det.remnant_paths:
            print(f"      残留路径: {len(det.remnant_paths)} 个")
    print()


def select_detections(detections: Sequence[Detection], yes: bool = False) -> List[Detection]:
    detected = [d for d in detections if d.detected]
    if not detected:
        print("没有可操作的目标。")
        return []
    print_scan_table(detected)
    print("请输入要处理的编号（逗号分隔），或输入 all 选择全部，直接回车退出：")
    raw = input("> ").strip().lower()
    if not raw:
        return []
    if raw == "all":
        return detected
    selected = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            idx = int(part) - 1
            if 0 <= idx < len(detected):
                selected.append(detected[idx])
            else:
                eprint(f"无效编号: {part}")
        except ValueError:
            eprint(f"无效输入: {part}")
    # Deduplicate preserving order
    seen = set()
    result = []
    for d in selected:
        if d.id not in seen:
            seen.add(d.id)
            result.append(d)
    return result


def cmd_scan(args: argparse.Namespace) -> int:
    detections = scan_all()
    if args.json:
        data = [d.to_dict() for d in detections if d.detected or args.all]
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print_scan_table(detections, show_all=args.all)
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    detections = scan_all()
    if args.all:
        selected = [d for d in detections if d.detected]
        if not selected:
            print("没有可操作的目标。")
            return 0
        print_scan_table(selected)
    else:
        selected = select_detections(detections, yes=args.yes)
        if not selected:
            return 0

    for det in selected:
        print(f"\n===== {det.name} =====")
        actions = build_uninstall_actions(det)
        if not actions:
            print("  (没有找到可执行的主卸载动作，可能是手动安装；将只处理残留清理。)")
        else:
            print("  计划执行以下主卸载动作：")
            for a in actions:
                print(f"    - {a['description']}")
            if not confirm("  确认卸载该工具？", default=False, yes=args.yes):
                print("  已跳过。")
                continue
            for a in actions:
                execute_action(a, dry_run=args.dry_run, yes=args.yes)

        # Ask about remnants
        cleanup = build_cleanup_actions(det)
        if cleanup:
            print(f"  发现 {len(cleanup)} 个残留位置：")
            for a in cleanup:
                print(f"    - {a['path']}")
            if confirm("  是否清除这些残留？（选否=保留）", default=False, yes=args.yes):
                for a in cleanup:
                    execute_action(a, dry_run=args.dry_run, yes=args.yes)
            else:
                print("  已选择保留残留。")
        else:
            print("  没有发现需要清理的残留。")
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    """Clean residue only, without uninstalling the main tool."""
    detections = scan_all()
    # Only show residue-only or all detected with residue
    candidates = [d for d in detections if d.remnant_paths]
    if not candidates:
        print("没有发现任何残留。")
        return 0
    if args.all:
        selected = candidates
        print_scan_table(selected)
    else:
        selected = select_detections(candidates, yes=args.yes)
        if not selected:
            return 0
    for det in selected:
        cleanup = build_cleanup_actions(det)
        print(f"\n===== {det.name} =====")
        for a in cleanup:
            print(f"  - {a['path']}")
        if confirm("  确认清除以上残留？", default=False, yes=args.yes):
            for a in cleanup:
                execute_action(a, dry_run=args.dry_run, yes=args.yes)
        else:
            print("  已取消。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-tool-cleaner",
        description="扫描并卸载电脑上的 AI agent 工具，可选择保留或清除残留。",
    )
    parser.add_argument("--version", action="version", version="agent-tool-cleaner 0.1.0")
    parser.set_defaults(all=False, json=False, dry_run=False, yes=False)
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="扫描已安装的 agent 工具和残留")
    scan.add_argument("--all", action="store_true", help="同时显示未检测到的工具（调试用）")
    scan.add_argument("--json", action="store_true", help="以 JSON 输出")
    scan.set_defaults(func=cmd_scan)

    uninstall = sub.add_parser("uninstall", help="交互式卸载 agent 工具")
    uninstall.add_argument("--all", action="store_true", help="不询问，处理所有检测到的工具")
    uninstall.add_argument("--dry-run", action="store_true", help="只预览不执行")
    uninstall.add_argument("--yes", "-y", action="store_true", help="自动确认（慎用）")
    uninstall.set_defaults(func=cmd_uninstall)

    clean = sub.add_parser("clean", help="仅清理残留，不卸载主程序")
    clean.add_argument("--all", action="store_true", help="不询问，处理所有检测到残留的工具")
    clean.add_argument("--dry-run", action="store_true", help="只预览不执行")
    clean.add_argument("--yes", "-y", action="store_true", help="自动确认（慎用）")
    clean.set_defaults(func=cmd_clean)

    return parser


def cmd_menu(args: argparse.Namespace) -> int:
    """傻瓜式交互菜单：适合直接双击运行，不需要记命令。"""
    while True:
        print()
        print("=" * 50)
        print("  Agent 工具清理助手")
        print("=" * 50)
        print("  1. 扫描已安装的 Agent 工具")
        print("  2. 卸载 Agent 工具（可选择保留/清除残留）")
        print("  3. 仅清理残留")
        print("  0. 退出")
        print("-" * 50)
        choice = input("请输入数字选择: ").strip().lower()
        if choice == "1":
            cmd_scan(args)
            input("\n按回车返回菜单...")
        elif choice == "2":
            cmd_uninstall(args)
            input("\n按回车返回菜单...")
        elif choice == "3":
            cmd_clean(args)
            input("\n按回车返回菜单...")
        elif choice in ("0", "q", "quit", "exit", "退出"):
            print("已退出。")
            break
        else:
            print("无效输入，请重新选择。")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        return cmd_menu(args)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
