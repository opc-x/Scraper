"""
一次性交互登录：打开真实浏览器窗口，人工手动登录 X，登录态落到持久化 profile 里
（跟 infra/chrome.py 里 headless 抓取用的是同一份 profile），完成后自动回传 R2。

用法：
    python scripts/x_login.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.infra import chrome  # noqa: E402

TIMEOUT_SECONDS = 600
POLL_INTERVAL = 3


def _has_auth_cookie(page) -> bool:
    try:
        for c in page.cookies():
            name = c.get("name") if isinstance(c, dict) else getattr(c, "name", None)
            if name == "auth_token":
                return True
    except Exception:
        pass
    return False


def main():
    page = chrome.new_page("x", headless=False)
    page.get("https://x.com/i/flow/login")
    print("浏览器窗口已打开，请在窗口里手动登录 X（含验证码/双重验证）。")
    print(f"最长等待 {TIMEOUT_SECONDS} 秒，检测到登录成功会自动保存并退出。")

    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        if _has_auth_cookie(page):
            print("检测到登录态，保存 profile 并回传 R2 ...")
            chrome.persist_profile("x")
            page.quit()
            print("完成。登录态已持久化，之后 headless 抓取会复用这份 profile。")
            return
        time.sleep(POLL_INTERVAL)

    print(f"超过 {TIMEOUT_SECONDS} 秒没检测到登录，退出（浏览器窗口保持打开，可以继续手动操作后重新运行本脚本）。")


if __name__ == "__main__":
    main()
