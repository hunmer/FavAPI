"""小红书 parser 单元测试。

运行：.venv/Scripts/python.exe tests/test_xiaohongshu_parser.py
（函数名 test_*，亦可用 pytest 收集）
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.platforms.xiaohongshu.parser import (  # noqa: E402
    extract_user_id,
    is_user_id,
    parse_collect_page,
    parse_note,
)


def _sample_note(note_id="6a769e4e00000000330302c3"):
    return {
        "note_id": note_id,
        "display_title": "用 CSS 做一张会反光的宝可梦闪卡",
        "type": "video",
        "cover": {
            "info_list": [
                {"image_scene": "WB_PRV", "url": "http://sns-webpic-qc.xhscdn.com/prv.webp"},
                {"image_scene": "WB_DFT", "url": "http://sns-webpic-qc.xhscdn.com/dft.webp"},
            ],
            "url_pre": "http://sns-webpic-qc.xhscdn.com/prv.webp",
            "url_default": "http://sns-webpic-qc.xhscdn.com/dft.webp",
            "height": 1011,
            "width": 1348,
        },
        "user": {"user_id": "67277035000000001c018cfc", "nickname": "林想的Web工坊"},
        "interact_info": {"liked": False, "liked_count": "198"},
        "xsec_token": "AB0_ad2Q=",
    }


def test_extract_user_id():
    url = "https://www.xiaohongshu.com/user/profile/5fdc0e36000000000100233a?tab=fav&subTab=note"
    assert extract_user_id(url) == "5fdc0e36000000000100233a"
    assert extract_user_id("https://www.xiaohongshu.com/explore/xxx") is None
    assert extract_user_id("") is None
    assert is_user_id("5fdc0e36000000000100233a")
    assert not is_user_id("123") and not is_user_id("")


def test_parse_note_fields():
    row = parse_note(_sample_note())
    assert row["content_id"] == "6a769e4e00000000330302c3"
    assert row["title"] == "用 CSS 做一张会反光的宝可梦闪卡"
    assert row["author_id"] == "67277035000000001c018cfc"
    assert row["author_name"] == "林想的Web工坊"
    assert row["cover_url"] == "http://sns-webpic-qc.xhscdn.com/dft.webp"
    assert row["duration"] is None and row["collected_at"] is None
    stats = json.loads(row["statistics"])
    assert stats["liked_count"] == 198
    assert json.loads(row["raw_data"])["note_id"] == "6a769e4e00000000330302c3"


def test_parse_note_cover_fallback_and_missing():
    # 无 url_default/url_pre → 回退 info_list 的 WB_DFT
    note = _sample_note()
    note["cover"] = {"info_list": [
        {"image_scene": "WB_PRV", "url": "http://x/prv.webp"},
        {"image_scene": "WB_DFT", "url": "http://x/dft.webp"},
    ]}
    assert parse_note(note)["cover_url"] == "http://x/dft.webp"
    # 空对象 → 各字段安全置空
    row = parse_note({"note_id": "n1"})
    assert row["content_id"] == "n1"
    assert row["title"] is None and row["author_name"] is None and row["cover_url"] is None
    assert json.loads(row["statistics"]) == {"liked_count": None}


def test_parse_collect_page_meta():
    data = {
        "msg": "成功",
        "data": {
            "cursor": "6a72f2880000000022012a87",
            "has_more": True,
            "notes": [_sample_note("n1"), _sample_note("n2"), {"no_id": 1}],
        },
        "code": 0,
        "success": True,
    }
    parsed = parse_collect_page(data)
    assert len(parsed["items"]) == 2  # 无 note_id 的条目丢弃
    assert parsed["cursor"] == "6a72f2880000000022012a87"
    assert parsed["has_more"] is True and parsed["total"] == 0


def test_parse_collect_page_empty():
    parsed = parse_collect_page({})
    assert parsed["items"] == [] and parsed["has_more"] is False
    assert parsed["cursor"] is None and parsed["total"] == 0


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
