from app.channels.youtube import YouTubeAdapter

# 结构取自真实调用（2026-08-12 实测 YouTube Data API v3 search.list）
SAMPLE_SEARCH_RESPONSE = {
    "kind": "youtube#searchListResponse",
    "items": [
        {
            "kind": "youtube#searchResult",
            "id": {"kind": "youtube#video", "videoId": "GtPyXqFbCus"},
            "snippet": {
                "title": "How to Get a Remote or International Tech Job (Complete Guide)",
                "description": "The most common question I get is how do I land a remote tech job...",
                "channelTitle": "Beyond Coding",
            },
        },
        {
            # 频道类结果混在搜索结果里（type=video 参数下理论不该出现，但防御性处理）
            "kind": "youtube#searchResult",
            "id": {"kind": "youtube#channel", "channelId": "UCabc123"},
            "snippet": {"title": "Some Channel", "description": "", "channelTitle": ""},
        },
    ],
}


def test_extract_videos_reads_snippet_fields():
    videos = YouTubeAdapter.extract_videos(SAMPLE_SEARCH_RESPONSE)

    assert len(videos) == 1
    assert videos[0]["video_id"] == "GtPyXqFbCus"
    assert "Remote" in videos[0]["title"]
    assert videos[0]["channel"] == "Beyond Coding"
    assert "remote tech job" in videos[0]["description"]


def test_extract_videos_skips_non_video_results():
    payload = {"items": [{"kind": "youtube#searchResult", "id": {"kind": "youtube#channel"}, "snippet": {}}]}
    assert YouTubeAdapter.extract_videos(payload) == []


def test_extract_videos_empty_payload_returns_empty_list():
    assert YouTubeAdapter.extract_videos({}) == []
    assert YouTubeAdapter.extract_videos(None) == []
