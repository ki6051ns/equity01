"""
check_no_bin_import.py

scripts.tools.bin を import している箇所がないかチェックする。
bin は単独実行専用（import禁止）のため、参照があればエラー。
"""
import sys
from pathlib import Path
import subprocess

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def check_bin_imports():
    """scripts.tools.bin の import を検出"""
    # ripgrepで検索（Windowsではfindstrでも可だが、ripgrep推奨）
    try:
        result = subprocess.run(
            ["rg", "-n", r"(?:from|import).*tools\.bin"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode == 0 and result.stdout.strip():
            # マッチが見つかった
            print("ERROR: scripts.tools.bin を import している箇所が見つかりました:")
            print(result.stdout)
            return False
        elif result.returncode == 1:
            # マッチなし（正常）
            print("OK: scripts.tools.bin の import は見つかりませんでした")
            return True
        else:
            # ripgrepエラー
            print(f"WARN: ripgrep実行エラー: {result.stderr}")
            return False
            
    except FileNotFoundError:
        # ripgrepがインストールされていない場合はPythonで検索
        print("WARN: ripgrepが見つかりません。Pythonで検索します...")
        return check_bin_imports_python()


def check_bin_imports_python():
    """Pythonで直接検索（ripgrep代替）"""
    import re
    
    patterns = [
        r"(?:from|import).*tools\.bin",
    ]
    
    violations = []
    
    for py_file in PROJECT_ROOT.rglob("*.py"):
        # 除外パス（check_no_bin_import.py自体も除外）
        if any(exclude in str(py_file) for exclude in ["__pycache__", ".git", "deprecated", "check_no_bin_import.py"]):
            continue
        
        try:
            content = py_file.read_text(encoding="utf-8")
            for i, line in enumerate(content.split("\n"), 1):
                for pattern in patterns:
                    if re.search(pattern, line):
                        violations.append(f"{py_file.relative_to(PROJECT_ROOT)}:{i}: {line.strip()}")
        except Exception:
            pass
    
    if violations:
        print("ERROR: scripts.tools.bin を import している箇所が見つかりました:")
        for v in violations:
            print(f"  {v}")
        return False
    else:
        print("OK: scripts.tools.bin の import は見つかりませんでした")
        return True


if __name__ == "__main__":
    success = check_bin_imports()
    sys.exit(0 if success else 1)

