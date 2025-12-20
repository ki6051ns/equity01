# scripts/run_scoring.py
# 3.1 スコアリング一括実行用の簡易 CLI

from pathlib import Path
import argparse
import sys

# scripts ディレクトリをパスに追加
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from core.scoring_engine import run_from_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run equity01 scoring (3.1).")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/scoring.yml",
        help="Path to scoring config yaml (project rootからの相対パス or 絶対パス)",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    print("[run_scoring] config:", config_path)

    scores = run_from_config(config_path)

    # 追加保存: data/intermediate/scoring に保存（scoring_engine.pyで既に保存済みだが、latestも確実に作成）
    import yaml
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    
    asof = cfg.get("asof", "latest")
    outdir = PROJECT_ROOT / "data" / "intermediate" / "scoring"
    outdir.mkdir(parents=True, exist_ok=True)
    
    # latest シンボリック（Windowsで権限不可ならコピー）
    latest_path = outdir / "latest_scores.parquet"
    try:
        if latest_path.exists() or latest_path.is_symlink():
            latest_path.unlink()
        
        # 日付付きファイルが存在する場合はシンボリックリンク、なければ直接保存
        if asof != "latest":
            asof_date = asof.replace("-", "")
            date_path = outdir / f"{asof_date}_scores.parquet"
            if date_path.exists():
                latest_path.symlink_to(f"{asof_date}_scores.parquet")
            else:
                scores.to_parquet(latest_path)
        else:
            # latestの場合は直接保存
            scores.to_parquet(latest_path)
    except Exception as e:
        print(f"[run_scoring] symlink failed, fallback to copy: {e}")
        try:
            import shutil
            if asof != "latest":
                asof_date = asof.replace("-", "")
                date_path = outdir / f"{asof_date}_scores.parquet"
                if date_path.exists():
                    shutil.copy2(date_path, latest_path)
                else:
                    scores.to_parquet(latest_path)
            else:
                scores.to_parquet(latest_path)
        except Exception as e2:
            print(f"[run_scoring] copy latest failed: {e2}")

    print("\nTop 10 by penalized score:")
    print(
        scores[["score_penalized", "sigma", "weight"]]
        .head(10)
        .to_string(float_format=lambda x: f"{x: .4f}")
    )


if __name__ == "__main__":
    main()
