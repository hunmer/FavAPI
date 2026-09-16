import asyncio
import unittest
from datetime import datetime
from unittest.mock import patch

from app.platforms.douyin import api_client


def _cursor(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1_000_000)


class CancelCollectWindowTest(unittest.TestCase):
    def test_continues_after_empty_refine_page(self):
        page_lo_1 = _cursor("2026-02-06T23:03:44+08:00")
        empty_page_cursor = _cursor("2026-02-05T12:33:21+08:00")
        target_cursor = _cursor("2025-11-01T11:25:30+08:00")
        before_window_cursor = _cursor("2024-12-18T12:28:36+08:00")
        calls = []

        responses = iter([
            {"items": [{"content_id": "newer"}], "cursor": page_lo_1, "has_more": True},
            {"items": [{"content_id": "target-main"}], "cursor": target_cursor, "has_more": True},
            {"items": [], "cursor": empty_page_cursor, "has_more": True},
            {"items": [{"content_id": "target"}], "cursor": target_cursor, "has_more": True},
            {"items": [{"content_id": "older"}], "cursor": before_window_cursor, "has_more": True},
        ])

        def fake_fetch(cookie_header, cursor=0, count=20):
            calls.append((cursor, count))
            return next(responses)

        canceled = []

        def fake_cancel(cookie_header, aweme_ids):
            canceled.extend(aweme_ids)
            return {"status_code": 0}

        events = []

        async def on_progress(event):
            events.append(event)

        with (
            patch.object(api_client, "fetch_listcollection_page", fake_fetch),
            patch.object(api_client, "cancel_collect_page", fake_cancel),
            patch.object(api_client.constants, "API_PAGE_INTERVAL_SEC", 0),
            patch.object(api_client.constants, "CANCEL_COLLECT_INTERVAL_SEC", 0),
        ):
            result = asyncio.run(api_client.cancel_collect_by_window(
                "cookie",
                datetime.fromisoformat("2025-01-01T00:00:00+08:00"),
                datetime.fromisoformat("2026-01-01T23:59:59+08:00"),
                on_progress=on_progress,
                time_mode="collected",
            ))

        self.assertEqual(calls, [
            (0, 20),
            (page_lo_1, 20),
            (page_lo_1, 1),
            (empty_page_cursor, 1),
            (target_cursor, 1),
        ])
        self.assertEqual(canceled, ["target"])
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["canceled"], 1)
        self.assertTrue(result["stopped_early"])
        self.assertEqual(events[-1]["matched_this_page"], 1)
        self.assertEqual(events[-1]["canceled"], 1)
