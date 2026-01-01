"""
Parquetファイルの中身をプレビューするスクリプト

使用方法:
    python scripts/ops/preview_parquet.py <parquet_file_path> [--rows N] [--columns COL1,COL2,...]
    
例:
    python scripts/ops/preview_parquet.py data/processed/index_tpx_daily.parquet
    python scripts/ops/preview_parquet.py data/processed/paper_trade_with_alpha_beta.parquet --rows 20
    python scripts/ops/preview_parquet.py data/processed/paper_trade_with_alpha_beta.parquet --columns trade_date,port_ret_cc,alpha_ret_cc
"""
import argparse
import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd


def preview_parquet(
    file_path: Path,
    n_rows: int = 10,
    columns: Optional[List[str]] = None,
    show_info: bool = True,
) -> None:
    """Parquetファイルを読み込んで表示"""
    if not file_path.exists():
        print(f"❌ ファイルが見つかりません: {file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        df = pd.read_parquet(file_path)
    except Exception as e:
        print(f"❌ ファイルの読み込みに失敗しました: {e}", file=sys.stderr)
        sys.exit(1)

    if df.empty:
        print("⚠️  ファイルは空です")
        return

    # 基本情報
    if show_info:
        print("=" * 80)
        print(f"📁 ファイル: {file_path}")
        print(f"📊 行数: {len(df):,}")
        print(f"📋 列数: {len(df.columns)}")
        print(f"📅 日付範囲: ", end="")
        
        # 日付カラムを探す
        date_cols = [c for c in df.columns if "date" in c.lower() or "time" in c.lower()]
        if date_cols:
            date_col = date_cols[0]
            if pd.api.types.is_datetime64_any_dtype(df[date_col]):
                print(f"{df[date_col].min()} ～ {df[date_col].max()}")
            else:
                print("(日付カラムが見つかりません)")
        else:
            print("(日付カラムが見つかりません)")
        
        print(f"💾 メモリ使用量: {df.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB")
        print("=" * 80)
        print()

    # カラム情報
    if show_info:
        print("📋 カラム一覧:")
        for i, col in enumerate(df.columns, 1):
            dtype = df[col].dtype
            null_count = df[col].isna().sum()
            null_pct = (null_count / len(df)) * 100
            print(f"  {i:2d}. {col:30s} ({dtype}) - NaN: {null_count:,} ({null_pct:.1f}%)")
        print()

    # データプレビュー
    print("📊 データプレビュー:")
    print("-" * 80)
    
    # 表示するカラムを選択
    display_df = df.copy()
    if columns:
        # 指定されたカラムのみ表示
        missing_cols = [c for c in columns if c not in df.columns]
        if missing_cols:
            print(f"⚠️  指定されたカラムが見つかりません: {missing_cols}", file=sys.stderr)
        display_cols = [c for c in columns if c in df.columns]
        if display_cols:
            display_df = display_df[display_cols]
        else:
            print("⚠️  表示可能なカラムがありません。全カラムを表示します。", file=sys.stderr)
            display_cols = None
    else:
        display_cols = None

    # 先頭
    print(f"\n【先頭 {min(n_rows, len(df))} 行】")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    pd.set_option("display.max_colwidth", 50)
    print(display_df.head(n_rows).to_string())
    
    # 末尾（行数が多い場合）
    if len(df) > n_rows * 2:
        print(f"\n【末尾 {min(n_rows, len(df))} 行】")
        print(display_df.tail(n_rows).to_string())
    
    # 統計情報（数値カラムのみ）
    numeric_cols = display_df.select_dtypes(include=["number"]).columns.tolist()
    if numeric_cols and show_info:
        print(f"\n📈 統計情報（数値カラム）:")
        print("-" * 80)
        stats = display_df[numeric_cols].describe()
        print(stats.to_string())

    print()
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Parquetファイルの中身をプレビュー",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  %(prog)s data/processed/index_tpx_daily.parquet
  %(prog)s data/processed/paper_trade_with_alpha_beta.parquet --rows 20
  %(prog)s data/processed/paper_trade_with_alpha_beta.parquet --columns trade_date,port_ret_cc,alpha_ret_cc
        """,
    )
    parser.add_argument(
        "file_path",
        type=str,
        help="プレビューするparquetファイルのパス",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=10,
        help="表示する行数（デフォルト: 10）",
    )
    parser.add_argument(
        "--columns",
        type=str,
        default=None,
        help="表示するカラム（カンマ区切り、例: col1,col2,col3）",
    )
    parser.add_argument(
        "--no-info",
        action="store_true",
        help="基本情報を表示しない",
    )

    args = parser.parse_args()

    file_path = Path(args.file_path)
    columns = args.columns.split(",") if args.columns else None
    if columns:
        columns = [c.strip() for c in columns]

    preview_parquet(
        file_path=file_path,
        n_rows=args.rows,
        columns=columns,
        show_info=not args.no_info,
    )


if __name__ == "__main__":
    main()

