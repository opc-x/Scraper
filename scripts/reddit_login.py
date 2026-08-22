"""从本机日常 Chrome 抠 Reddit 登录态，供画像拉评论用。

用法：
    python -m scripts.reddit_login
"""
from __future__ import annotations

from app.core.job_comments import import_reddit_cookies_from_chrome


def main() -> None:
    if import_reddit_cookies_from_chrome():
        print("已从本机 Chrome 写入 Reddit 登录态。生成画像会带这份 Cookie。")
        return
    print("没读到 reddit_session。确认本机 Chrome 已登录 Reddit 后再跑一次。")


if __name__ == "__main__":
    main()
