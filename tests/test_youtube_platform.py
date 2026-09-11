import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.platforms.declarative import _walk, DeclarativeAdapter  # noqa: E402


def _sample_response():
    playlist = {
        "playlistId": "PL123",
        "title": {"simpleText": "我的播放列表"},
        "shortBylineText": {"runs": [{"text": "示例频道"}]},
        "thumbnail": {"thumbnails": [{"url": "https://i.ytimg.com/vi/x/hqdefault.jpg"}]},
    }
    return {"contents": {"twoColumnBrowseResultsRenderer": {"tabs": [
        {"tabRenderer": {"content": {"sectionListRenderer": {"contents": [
            {"itemSectionRenderer": {"contents": [
                {"gridRenderer": {"items": [{"gridPlaylistRenderer": playlist}]}}
            ]}}
        ]}}}}
    ]}}}


def test_youtube_declarative_mapping():
    spec = json.loads((Path(__file__).resolve().parents[1] / "platforms/youtube/platform.json").read_text(encoding="utf-8"))
    adapter = DeclarativeAdapter(spec)
    rows = _walk(_sample_response(), spec["capture"]["items_path"])
    assert len(rows) == 1
    row = rows[0]
    assert row["playlistId"] == "PL123"
    assert adapter._value(row, "title.simpleText") == "我的播放列表"
    assert adapter._value(row, "shortBylineText.runs[].text") == "示例频道"
    assert adapter._value(row, "thumbnail.thumbnails[].url").startswith("https://i.ytimg.com")
