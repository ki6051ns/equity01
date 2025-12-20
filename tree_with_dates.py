import os
import sys
from pathlib import Path
from datetime import datetime

# UTF-8出力を強制
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def tree_with_dates(path, prefix='', is_last=True, show_ext=True):
    path = Path(path)
    if not path.exists():
        print(f'エラー: パスが見つかりません: {path}')
        return
    
    items = sorted([p for p in path.iterdir() if p.name not in ['.git', '__pycache__', '.gitignore']], 
                   key=lambda x: (x.is_file(), x.name))
    
    for i, item in enumerate(items):
        is_last_item = i == len(items) - 1
        current_prefix = '└── ' if is_last_item else '├── '
        
        if item.is_file():
            mtime = datetime.fromtimestamp(item.stat().st_mtime)
            size = item.stat().st_size
            if size < 1024 * 1024:
                size_str = f'{size:,} bytes'
            else:
                size_str = f'{size/1024/1024:.2f} MB'
            
            # 拡張子を取得
            ext = item.suffix if item.suffix else '(拡張子なし)'
            if show_ext:
                print(f'{prefix}{current_prefix}{item.name} [{ext}] ({mtime.strftime("%Y-%m-%d %H:%M:%S")}, {size_str})')
            else:
                print(f'{prefix}{current_prefix}{item.name}  ({mtime.strftime("%Y-%m-%d %H:%M:%S")}, {size_str})')
        else:
            # ディレクトリの最終更新日時も表示
            mtime = datetime.fromtimestamp(item.stat().st_mtime)
            print(f'{prefix}{current_prefix}{item.name}/ ({mtime.strftime("%Y-%m-%d %H:%M:%S")})')
            next_prefix = prefix + ('    ' if is_last_item else '│   ')
            tree_with_dates(item, next_prefix, is_last_item, show_ext)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
    else:
        target_path = 'data'
    
    path = Path(target_path)
    if not path.exists():
        print(f'エラー: 指定されたパスが見つかりません: {target_path}')
        sys.exit(1)
    
    print(f'{path.name}/')
    tree_with_dates(target_path)

