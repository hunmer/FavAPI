import asyncio
import unittest
from datetime import datetime
from unittest.mock import patch

from app.platforms.douyin import api_client


def _cursor(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1_000_000)


class CancelCollectWindowTest(unittest.TestCase):
    def test_retries_status_code_5(self):
        attempts = []

        def fake_cancel(_cookie, _ids):
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("取消收藏失败：status_code=5 fatal_ids=[] message=操作频繁")
            return {"status_code": 0}

        with (
            patch.object(api_client, "cancel_collect_page", fake_cancel),
            patch.object(api_client.constants, "CANCEL_COLLECT_INTERVAL_SEC", 0),
        ):
            asyncio.run(api_client._cancel_collect_batch_with_retry("cookie", [f"id-{i}" for i in range(20)]))
        self.assertEqual(len(attempts), 3)

    def test_splits_invalid_batch_and_skips_invalid_single_id(self):
        calls = []

        def fake_cancel(_cookie, ids):
            calls.append(list(ids))
            if len(ids) > 1:
                raise RuntimeError("取消收藏失败：status_code=5 fatal_ids=[] message=参数不合法")
            if ids[0] == "bad":
                raise RuntimeError("取消收藏失败：status_code=5 fatal_ids=[] message=参数不合法")
            return {"status_code": 0}

        with (
            patch.object(api_client, "cancel_collect_page", fake_cancel),
            patch.object(api_client, "cancel_collect_single", lambda c, i: fake_cancel(c, [i])),
            patch.object(api_client.constants, "CANCEL_COLLECT_BATCH", 4),
        ):
            canceled = asyncio.run(api_client._cancel_collect_batch_with_retry(
                "cookie", ["good-1", "bad", "good-2", "good-3"],
            ))

        self.assertEqual(canceled, 3)
        self.assertEqual(calls, [
            ["good-1", "bad", "good-2", "good-3"],
            ["good-1"], ["bad"], ["good-2"], ["good-3"],
        ])

    def test_small_batch_is_sent_one_id_at_a_time(self):
        calls = []

        def fake_cancel(_cookie, ids):
            calls.append(list(ids))
            return {"status_code": 0}

        with (
            patch.object(api_client, "cancel_collect_page", fake_cancel),
            patch.object(api_client, "cancel_collect_single", lambda _cookie, item_id: (calls.append([item_id]) or {"status_code": 0, "collects_flag": False})),
        ):
            canceled = asyncio.run(api_client._cancel_collect_batch_with_retry(
                "cookie", ["id-1", "id-2"],
            ))

        self.assertEqual(canceled, 2)
        self.assertEqual(calls, [["id-1"], ["id-2"]])

    def test_collects_all_matches_before_canceling(self):
        cursor_1 = _cursor("2026-08-01T00:00:00+08:00")
        responses = iter([
            {"items": [{"content_id": "target-1", "collected_at": "2025-06-01T00:00:00+08:00"}], "cursor": cursor_1, "has_more": True},
            {"items": [{"content_id": "target-2", "collected_at": "2025-05-01T00:00:00+08:00"}], "cursor": cursor_1 - 1, "has_more": False},
        ])
        calls = []

        def fake_fetch(cookie_header, cursor=0, count=20):
            return next(responses)

        def fake_cancel(cookie_header, ids):
            calls.append(list(ids))
            return {"status_code": 0}

        with (
            patch.object(api_client, "fetch_listcollection_page", fake_fetch),
            patch.object(api_client, "cancel_collect_page", fake_cancel),
            patch.object(api_client.constants, "API_PAGE_INTERVAL_SEC", 0),
        ):
            result = asyncio.run(api_client.cancel_collect_by_window(
                "cookie", datetime.fromisoformat("2021-01-01T00:00:00+08:00"),
                datetime.fromisoformat("2026-01-01T00:00:00+08:00"),
            ))

        self.assertEqual(calls, [["target-1"], ["target-2"]])
        self.assertEqual(result["matched"], 2)
        self.assertEqual(result["canceled"], 2)

    def test_scans_past_cursor_date_until_api_end(self):
        cursor_new = _cursor("2026-08-01T00:00:00+08:00")
        cursor_old = _cursor("2022-04-03T00:00:00+08:00")
        calls = []
        responses = iter([
            {"items": [{"content_id": "outside", "collected_at": "2026-08-01T00:00:00+08:00"}], "cursor": cursor_new, "has_more": True},
            {"items": [{"content_id": "target", "collected_at": "2021-06-01T00:00:00+08:00"}], "cursor": cursor_old, "has_more": False},
        ])

        def fake_fetch(cookie_header, cursor=0, count=20):
            calls.append((cursor, count))
            return next(responses)

        canceled = []
        with (
            patch.object(api_client, "fetch_listcollection_page", fake_fetch),
            patch.object(api_client, "cancel_collect_page", lambda _cookie, ids: canceled.extend(ids)),
            patch.object(api_client.constants, "API_PAGE_INTERVAL_SEC", 0),
        ):
            result = asyncio.run(api_client.cancel_collect_by_window(
                "cookie",
                datetime.fromisoformat("2021-01-01T00:00:00+08:00"),
                datetime.fromisoformat("2026-01-01T23:59:59+08:00"),
                time_mode="collected",
            ))

        self.assertEqual(calls, [(0, 20), (cursor_new, 20)])
        self.assertEqual(canceled, ["target"])
        self.assertEqual(result["matched"], 1)
        self.assertFalse(result["stopped_early"])

    def test_scans_empty_pages_with_valid_cursor(self):
        responses = iter([
            {"items": [], "cursor": _cursor("2024-01-01T00:00:00+08:00"), "has_more": True},
            {"items": [], "cursor": _cursor("2023-01-01T00:00:00+08:00"), "has_more": False},
        ])
        with (
            patch.object(api_client, "fetch_listcollection_page", lambda *args, **kwargs: next(responses)),
            patch.object(api_client.constants, "API_PAGE_INTERVAL_SEC", 0),
        ):
            result = asyncio.run(api_client.cancel_collect_by_window("cookie", None, None))
        self.assertEqual(result["pages"], 2)
        self.assertEqual(result["matched"], 0)


if __name__ == "__main__":
    unittest.main()
