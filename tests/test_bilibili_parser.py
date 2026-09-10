"""Bilibili parser 单元测试。

运行：.venv/Scripts/python.exe tests/test_bilibili_parser.py
（函数名 test_*，亦可用 pytest 收集）
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.platforms.bilibili.parser import (  # noqa: E402
    extract_mid,
    parse_folder_list,
    parse_media,
    parse_resource_list,
)


def _sample_media(bvid="BV1bw9vBLEUY"):
    return {
        "id": 116493723638581,
        "type": 2,
        "title": "【插件更新】有手就行，一拖即用",
        "intro": "工具网址：https://frameronin.com/",
        "page": 1,
        "duration": 442,
        "upper": {"mid": 285760, "name": "bimelona", "face": "https://i1.hdslb.com/face/a.jpg"},
        "cnt_info": {"collect": 3745, "play": 47968, "danmaku": 5, "reply": 0, "thumb_up": 12},
        "cover": "http://i0.hdslb.com/bfs/archive/5da2b18e.jpg",
        "ctime": 1777553222,
        "fav_time": 1785590824,
        "bv_id": bvid,
        "bvid": bvid,
    }


_DEFAULT = object()


def _sample_resource_list(medias=_DEFAULT, has_more=True):
    return {
        "info": {
            "id": 290999545,
            "fid": 2909995,
            "mid": 388116545,
            "title": "默认收藏夹",
            "upper": {"mid": 388116545, "name": "无知少女の末路", "face": "https://i2.hdslb.com/face/b.jpg"},
            "media_count": 1693,
        },
        "medias": [_sample_media()] if medias is _DEFAULT else medias,
        "has_more": has_more,
        "ttl": 1789036083,
    }


def test_extract_mid():
    assert extract_mid("https://space.bilibili.com/388116545/favlist?spm_id_from=333.1387.0.0") == "388116545"
    assert extract_mid("https://space.bilibili.com/123") == "123"
    assert extract_mid("https://www.bilibili.com/video/BV1bw9vBLEUY") is None
    assert extract_mid("") is None


def test_parse_media_fields():
    row = parse_media(_sample_media())
    assert row["content_id"] == "BV1bw9vBLEUY"
    assert row["title"] == "【插件更新】有手就行，一拖即用"
    assert row["description"].startswith("工具网址")
    assert row["author_id"] == "285760" and row["author_name"] == "bimelona"
    assert row["cover_url"] == "http://i0.hdslb.com/bfs/archive/5da2b18e.jpg"
    assert row["duration"] == 442
    stats = json.loads(row["statistics"])
    assert stats["play"] == 47968 and stats["collect"] == 3745 and stats["danmaku"] == 5
    assert row["collected_at"] is not None  # fav_time → ISO
    assert json.loads(row["raw_data"])["bvid"] == "BV1bw9vBLEUY"


def test_parse_media_missing_fields():
    row = parse_media({"id": 123})
    assert row["content_id"] == "123"  # 无 bvid 时退回数字 id
    assert row["title"] is None and row["author_name"] is None
    assert row["duration"] is None and row["collected_at"] is None


def test_parse_resource_list():
    parsed = parse_resource_list(_sample_resource_list(medias=[_sample_media("BV1"), _sample_media("BV2")]))
    assert [it["content_id"] for it in parsed["items"]] == ["BV1", "BV2"]
    assert parsed["has_more"] is True
    assert parsed["total"] == 1693
    assert parsed["owner"] == {
        "mid": "388116545", "name": "无知少女の末路", "face": "https://i2.hdslb.com/face/b.jpg",
    }
    assert parsed["favorite"] == {"media_id": "290999545", "title": "默认收藏夹", "media_count": 1693}


def test_parse_resource_list_empty_medias():
    parsed = parse_resource_list(_sample_resource_list(medias=None, has_more=False))
    assert parsed["items"] == [] and parsed["has_more"] is False
    assert parsed["owner"]["mid"] == "388116545"


def test_parse_folder_list():
    data = {
        "count": 2,
        "list": [
            {"id": 290999545, "fid": 2909995, "mid": 388116545, "title": "默认收藏夹", "media_count": 1693},
            {"id": 290999600, "fid": 2909995, "mid": 388116545, "title": "教程", "media_count": 7},
        ],
    }
    parsed = parse_folder_list(data)
    assert parsed["owner"] == {"mid": "388116545", "name": None, "face": None}
    assert parsed["folders"] == [
        {"media_id": "290999545", "title": "默认收藏夹", "media_count": 1693},
        {"media_id": "290999600", "title": "教程", "media_count": 7},
    ]


def test_parse_folder_list_empty():
    parsed = parse_folder_list({})
    assert parsed["folders"] == [] and parsed["owner"]["mid"] == ""


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
