import os
import sys
from pathlib import Path
from datetime import datetime

# UTF-8出力を強制
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def tree_with_dates(path, prefix='', is_last=True, show_ext=True, output=sys.stdout):
    path = Path(path)
    if not path.exists():
        print(f'エラー: パスが見つかりません: {path}', file=output)
        return
    
    items = sorted([p for p in path.iterdir() if p.name not in ['.git', '__pycache__', '.gitignore', '.venv', 'venv']], 
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
                print(f'{prefix}{current_prefix}{item.name} [{ext}] ({mtime.strftime("%Y-%m-%d %H:%M:%S")}, {size_str})', file=output)
            else:
                print(f'{prefix}{current_prefix}{item.name}  ({mtime.strftime("%Y-%m-%d %H:%M:%S")}, {size_str})', file=output)
        else:
            # ディレクトリの最終更新日時も表示
            mtime = datetime.fromtimestamp(item.stat().st_mtime)
            print(f'{prefix}{current_prefix}{item.name}/ ({mtime.strftime("%Y-%m-%d %H:%M:%S")})', file=output)
            next_prefix = prefix + ('    ' if is_last_item else '│   ')
            tree_with_dates(item, next_prefix, is_last_item, show_ext, output)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='ディレクトリツリーを拡張子と最終更新日時込みで表示')
    parser.add_argument('path', nargs='?', default='.', help='対象ディレクトリパス（デフォルト: カレントディレクトリ）')
    parser.add_argument('-o', '--output', help='出力先ファイルパス（指定しない場合は標準出力）')
    args = parser.parse_args()
    
    path = Path(args.path)
    if not path.exists():
        print(f'エラー: 指定されたパスが見つかりません: {args.path}', file=sys.stderr)
        sys.exit(1)
    
    # 出力先を決定
    if args.output:
        output_file = open(args.output, 'w', encoding='utf-8')
        output = output_file
    else:
        output = sys.stdout
    
    try:
        print(f'{path.name}/', file=output)
        tree_with_dates(path, output=output)
    finally:
        if args.output:
            output_file.close()
            print(f'\n出力完了: {args.output}', file=sys.stderr)

