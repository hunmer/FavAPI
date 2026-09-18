"""CI：把双平台 bundle 加入 TUF 仓库并发布（由 release.yml 的 tufup-publish job 调用）。

用法：
  python scripts/tufup_publish.py --version 0.2.0 --repo-dir repository \
      --keys-dir keystore --bundles bundles

bundles 目录布局：bundles/<macos|windows>/FavAPI（解压后的便携目录）。
每个平台一个 app_name（FavAPI-macos-arm64 / FavAPI-windows-x64），共用同一 TUF 仓库。
"""
import argparse
import sys
from pathlib import Path

from tufup.repo import Repository

EXPIRATION_DAYS = {"root": 3650, "targets": 365, "snapshot": 365, "timestamp": 365}

# 平台子目录 → tufup app_name（与 app/services/updater.py 的 app_name() 保持一致）
PLATFORMS = {
    "macos": "FavAPI-macos-arm64",
    "windows": "FavAPI-windows-x64",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--repo-dir", type=Path, default=Path("repository"))
    parser.add_argument("--keys-dir", type=Path, default=Path("keystore"))
    parser.add_argument("--bundles", type=Path, default=Path("bundles"))
    args = parser.parse_args()

    # git 不跟踪空目录：基线/恢复后的仓库可能缺 targets/，tufup 写归档前须确保存在
    (args.repo_dir / "targets").mkdir(parents=True, exist_ok=True)

    for platform, app_name in PLATFORMS.items():
        bundle_dir = args.bundles / platform / "FavAPI"
        if not (bundle_dir / "FavAPI").exists() and not (bundle_dir / "FavAPI.exe").exists():
            print(f"跳过 {platform}：未找到 bundle {bundle_dir}", file=sys.stderr)
            continue
        archive_name = f"{app_name}-{args.version}.tar.gz"
        targets_json = (args.repo_dir / "metadata" / "targets.json")
        if archive_name in targets_json.read_text(encoding="utf-8"):
            print(f"{app_name} {args.version} 已发布，跳过（幂等重跑）")
            continue
        # chromium（pw-browsers 约 180MB）不参与增量更新：排除后全量归档约 60MB，
        # 低于 GitHub 单文件 100MB 上限；客户端安装时同样跳过 pw-browsers，
        # chromium 由 Release 全量包首次分发
        import shutil

        shutil.rmtree(bundle_dir / "pw-browsers", ignore_errors=True)
        # 清掉上次失败的未发布残留，避免 tufup 交互询问覆盖（CI 无 stdin）
        (args.repo_dir / "targets" / archive_name).unlink(missing_ok=True)
        # 双 app 共享 repo_dir：元数据全局累积，publish 各自 bump snapshot/timestamp
        repo = Repository(
            app_name=app_name,
            repo_dir=args.repo_dir,
            keys_dir=args.keys_dir,
            expiration_days=EXPIRATION_DAYS,
        )
        # 不用 initialize()：其对已存在的密钥会交互询问覆盖，CI 无法应答；
        # 密钥由 secrets 恢复（必已存在），只加载即可
        if not (args.repo_dir / "metadata" / "root.json").exists():
            sys.exit("TUF 仓库缺少 root.json 基线：请先本地运行 tufup_repo_init.py 并推送 gh-pages")
        repo._load_keys_and_roles(create_keys=False)
        repo.add_bundle(new_bundle_dir=bundle_dir, new_version=args.version)
        repo.publish_changes(private_key_dirs=[args.keys_dir])
        print(f"已发布 {app_name} {args.version}")


if __name__ == "__main__":
    main()
