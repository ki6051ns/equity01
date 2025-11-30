import os
import sys
from pathlib import Path
from datetime import datetime

# UTF-8出力を強制
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def tree_with_dates(path, prefix='', is_last=True):
    path = Path(path)
    if not path.exists():
        return
    
    items = sorted([p for p in path.iterdir() if p.name != '.git'], 
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
            print(f'{prefix}{current_prefix}{item.name}  ({mtime.strftime("%Y-%m-%d %H:%M:%S")}, {size_str})')
        else:
            print(f'{prefix}{current_prefix}{item.name}/')
            next_prefix = prefix + ('    ' if is_last_item else '│   ')
            tree_with_dates(item, next_prefix, is_last_item)

if __name__ == '__main__':
    print('data/')
    tree_with_dates('data')

