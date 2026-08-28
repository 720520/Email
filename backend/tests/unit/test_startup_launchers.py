from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_linux_launcher_does_not_silently_reuse_another_frontend() -> None:
    source = (PROJECT_ROOT / "scripts/start.sh").read_text(encoding="utf-8")

    assert "frontend_app_ready" in source
    assert "stop_stale_frontend" in source
    assert "另一份项目遗留的前端" in source
    assert "<title>基金运营工作台</title>" in source
    assert "port_in_use 5173 || return 0" in source
    assert 'warn "前端已在运行。"' not in source


def test_desktop_launcher_follows_its_own_project_directory() -> None:
    launcher = PROJECT_ROOT / "一键启动.desktop"
    source = launcher.read_text(encoding="utf-8")

    assert "%k" in source
    assert "$project_root/一键启动.sh" in source
    assert "Exec=/bin/bash -c " in source
    assert "/home/" not in source
    validator = shutil.which("desktop-file-validate")
    if validator:
        result = subprocess.run(
            [validator, str(launcher)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
