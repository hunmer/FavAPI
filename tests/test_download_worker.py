"""下载分类目录模板渲染（download_worker._category_dir）测试。"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import download_worker  # noqa: E402


def _render(template, link=None, platform="douyin", content_id="7677", title="标题/测试"):
    with patch.object(download_worker, "load_settings", return_value={"download_category": template}):
        return download_worker._category_dir(platform, content_id, title, link)


def test_default_platform():
    assert str(_render("")) == "douyin"
    assert str(_render("{platform}")) == "douyin"


def test_author_variables_from_link():
    link = {"author_name": "张三", "author_id": "MS4wLjABAAA"}
    assert str(_render("{platform}/{authorName}", link)) == str(Path("douyin/张三"))
    assert str(_render("{authorId}/{platform}", link)) == str(Path("MS4wLjABAAA/douyin"))


def test_all_variables():
    link = {"ext": "mp4", "author_name": "李四", "author_id": "uid-1"}
    out = _render("{platform}/{title}.{id}.{ext}", link, title="你好")
    assert str(out) == str(Path("douyin/你好.7677.mp4"))


def test_unknown_and_empty_variables_dropped():
    # 未知变量置空、空段剔除、author 缺失时段整体消失
    assert str(_render("{foo}/{platform}")) == "douyin"
    assert str(_render("{platform}/{authorName}")) == "douyin"


def test_illegal_chars_and_traversal_sanitized():
    link = {"author_name": 'a/b:"c'}
    assert str(_render("{platform}/{authorName}", link)) == str(Path("douyin/a b c"))
    # .. 越界段被剔除
    assert str(_render("{platform}/../x")) == str(Path("douyin/x"))


def test_title_fallback_and_empty_result():
    # 空 title 回落 content_id；全空渲染回落 platform
    out = _render("{title}", title="   ")
    assert str(out) == "7677"
    assert str(_render("{authorName}")) == "douyin"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
