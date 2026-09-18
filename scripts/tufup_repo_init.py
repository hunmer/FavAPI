"""一次性初始化 TUF 仓库（tufup）：生成密钥与初始元数据。

用法：.venv/bin/python scripts/tufup_repo_init.py

产物（均在 tufup/ 下，已 gitignore）：
- keystore/        4 个角色的 ed25519 私钥 —— 绝不提交；备份后写入 GitHub Secret
                   TUFUP_KEYSTORE_BASE64（tar.gz 的 base64）
- repository/      TUF 仓库（metadata/ + targets/），CI 每次发版增量更新到 gh-pages

密钥生成方式为无密码 ed25519（私钥本身存放在本地与 GitHub Secrets，不加密，
避免 CI 需要额外密钥口令）。
"""
import base64
import io
import subprocess
import sys
import tarfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tufup.repo import Repository  # noqa: E402

TUFUP_DIR = PROJECT_ROOT / "tufup"
KEYSTORE_DIR = TUFUP_DIR / "keystore"
REPO_DIR = TUFUP_DIR / "repository"

# 双平台各一个 app（同一 TUF 仓库，target 名 = app_name-版本）
APP_NAMES = ["FavAPI-macos-arm64", "FavAPI-windows-x64"]

# 静态 Pages 托管无法自动滚动更新，元数据过期一律放宽（每次发版都会续期）
EXPIRATION_DAYS = {"root": 3650, "targets": 365, "snapshot": 365, "timestamp": 365}

# 客户端首次 refresh 的信任锚，提交进仓库供 PyInstaller 打包
ROOT_JSON_DST = PROJECT_ROOT / "app" / "resources" / "tuf-metadata" / "root.json"


def main() -> None:
    if KEYSTORE_DIR.exists():
        sys.exit(f"已存在 {KEYSTORE_DIR}，如需重新初始化请先手动删除（会使所有客户端失联）")
    # 初始化只需一个 app_name（元数据是全局的），后续 CI 以各自 app_name add_bundle
    repo = Repository(
        app_name=APP_NAMES[0],
        repo_dir=REPO_DIR,
        keys_dir=KEYSTORE_DIR,
        expiration_days=EXPIRATION_DAYS,
    )
    repo.initialize()
    print(f"密钥与初始元数据已生成：{TUFUP_DIR}")

    keystore_b64 = tar_dir_base64(KEYSTORE_DIR)
    print(f"\nGitHub Secret TUFUP_KEYSTORE_BASE64 的值（tar.gz 的 base64，已复制说明见下）：\n")
    print(keystore_b64)
    print("\n写入方式：gh secret set TUFUP_KEYSTORE_BASE64 < 密钥文件")
    print(f"（或执行：printf %s '{keystore_b64[:16]}...' —— 请把上面完整 base64 串存为文件后 gh secret set）")

    ROOT_JSON_DST.parent.mkdir(parents=True, exist_ok=True)
    ROOT_JSON_DST.write_bytes((REPO_DIR / "metadata" / "root.json").read_bytes())
    print(f"root.json 已复制到 {ROOT_JSON_DST}（将随 PyInstaller 打进包内作为信任锚）")

    print("\n请妥善备份 tufup/keystore/（丢失则无法再签发更新）。")
    print("下一步：git add app/resources/tufup-metadata && gh secret set TUFUP_KEYSTORE_BASE64")


def tar_dir_base64(path: Path) -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in sorted(path.iterdir()):
            tar.add(f, arcname=f.name)
    return base64.b64encode(buf.getvalue()).decode()


if __name__ == "__main__":
    main()
