"""抖音 parser 单元测试。

运行：.venv/Scripts/python.exe tests/test_parser.py
（函数名 test_*，亦可用 pytest 收集）
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.platforms.douyin.parser import parse_aweme, parse_listcollection  # noqa: E402


def _sample_aweme(aweme_id="7412345678901234567"):
    return {
        "aweme_id": aweme_id,
        "desc": "标题第一行\n正文描述第二行",
        "author": {"uid": "888888", "sec_uid": "sec_xxx", "nickname": "测试作者"},
        "video": {
            "duration": 15300,
            "cover": {"url_list": ["https://p3.douyinpic.com/cover.jpg"]},
        },
        "statistics": {
            "digg_count": "1200", "comment_count": 34,
            "share_count": 5, "collect_count": "678", "play_count": 99999,
        },
        "collect_time": 1757460000,
    }


def test_parse_aweme_fields():
    row = parse_aweme(_sample_aweme())
    assert row["content_id"] == "7412345678901234567"
    assert row["title"] == "标题第一行"
    assert row["description"].startswith("标题第一行")
    assert row["author_id"] == "888888"
    assert row["author_name"] == "测试作者"
    assert row["cover_url"] == "https://p3.douyinpic.com/cover.jpg"
    assert row["duration"] == 15300
    stats = json.loads(row["statistics"])
    assert stats["digg_count"] == 1200 and stats["collect_count"] == 678
    assert row["collected_at"] is not None
    assert json.loads(row["raw_data"])["aweme_id"] == "7412345678901234567"


def test_parse_aweme_missing_fields():
    row = parse_aweme({"aweme_id": "1"})
    assert row["content_id"] == "1"
    assert row["title"] is None and row["author_name"] is None
    assert row["duration"] is None and row["cover_url"] is None


def test_parse_sample_collected_at_fallback():
    sample_path = Path(__file__).resolve().parent.parent / "samples" / "douyin_favorites.json"
    data = json.loads(sample_path.read_text(encoding="utf-8"))
    row = parse_listcollection(data)["items"][0]
    expected = datetime.fromtimestamp(data["aweme_list"][0]["create_time"]).astimezone().isoformat(timespec="seconds")
    assert row["collected_at"] == expected


def test_parse_listcollection_dedup_and_meta():
    data = {
        "aweme_list": [_sample_aweme("a1"), _sample_aweme("a2"), _sample_aweme("a1")],
        "cursor": 20,
        "has_more": True,
        "total": 87,
    }
    parsed = parse_listcollection(data)
    assert len(parsed["items"]) == 3  # 去重在 adapter 的 merge 完成，parser 保留原始条数
    assert parsed["cursor"] == 20 and parsed["has_more"] is True and parsed["total"] == 87


def test_parse_listcollection_empty():
    parsed = parse_listcollection({})
    assert parsed["items"] == [] and parsed["has_more"] is False and parsed["total"] == 0


def _detail(aweme_id="7665364150679587323"):
    return {
        "status_code": 0,
        "aweme_detail": {
            "aweme_id": aweme_id,
            "video": {
                "play_addr": {
                    "url_list": [
                        "https://www.douyin.com/aweme/v1/playwm/?video_id=v0d00fg10000",
                        "https://v26-web.douyinvod.com/video/tos/playwm/cn/tos/video.mp4",
                    ],
                    "width": 1080, "height": 1920, "data_size": 10485760,
                },
                "bit_rate": [
                    {
                        "gear_name": "adapt_1080_0",
                        "data_size": 8388608,
                        "play_addr": {
                            "url_list": ["https://v26-web.douyinvod.com/video/tos/playwm/cn/tos/video.mp4"],
                            "width": 1080, "height": 1920,
                        },
                    },
                    {
                        "gear_name": "normal_720_0",
                        "play_addr": {
                            "url_list": ["https://v26-web.douyinvod.com/video/tos/720.mp4"],
                            "width": 720, "height": 1280,
                        },
                    },
                ],
            },
        },
    }


def test_parse_download_links():
    from app.platforms.douyin.parser import parse_download_links

    links = parse_download_links(_detail())
    # playwm 统一替换为 play；默认画质 + bit_rate 各档；重复 URL 去重
    assert [l["url"] for l in links] == [
        "https://www.douyin.com/aweme/v1/play/?video_id=v0d00fg10000",
        "https://v26-web.douyinvod.com/video/tos/play/cn/tos/video.mp4",
        "https://v26-web.douyinvod.com/video/tos/720.mp4",
    ]
    assert links[0]["label"] == "默认画质 1920p"
    assert links[0]["size"] == 10485760 and links[0]["ext"] == "mp4"
    assert links[0]["height"] == 1920


def test_parse_download_links_empty():
    from app.platforms.douyin.parser import parse_download_links

    assert parse_download_links({}) == []
    assert parse_download_links({"aweme_detail": {}}) == []


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
