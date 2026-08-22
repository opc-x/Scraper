import hashlib
import os

from DrissionPage import ChromiumOptions, ChromiumPage

from app.infra import r2

_default_profile_root = (
    "/data/chrome_profiles"
    if os.path.isdir("/data") and os.access("/data", os.W_OK)
    else os.path.expanduser("~/.scraper/chrome_profiles")
)
PROFILE_ROOT = os.environ.get("CHROME_PROFILE_ROOT", _default_profile_root)


def _profile_dir(channel: str) -> str:
    path = os.path.join(PROFILE_ROOT, channel)
    os.makedirs(path, exist_ok=True)
    return path


def _r2_key(channel: str) -> str:
    return f"chrome-profiles/{channel}.tar.gz"


def new_page(channel: str, headless: bool = True) -> ChromiumPage:
    """持久化 profile 的 page，登录态落盘；本地没有 profile 时先从 R2 拉一份。

    headless=False 用于人工交互登录（真实浏览器窗口，行为上就是个正常用户在操作）。
    """
    profile_dir = _profile_dir(channel)
    if not os.listdir(profile_dir):
        r2.download_dir(_r2_key(channel), profile_dir)

    opts = ChromiumOptions()
    if headless:
        opts.headless()
    opts.set_argument("--no-sandbox")
    opts.set_argument("--disable-gpu")
    opts.set_user_data_path(profile_dir)
    return ChromiumPage(opts)


def persist_profile(channel: str) -> None:
    """把当前 profile 回传 R2，容器重启/重新部署后能在 new_page() 里拉回来。"""
    r2.upload_dir(_r2_key(channel), _profile_dir(channel))


def sync_cookies(
    page: ChromiumPage, channel: str, domain_url: str, cookie_domain: str, cookie: str
) -> None:
    """仅在 cookie 变化时注入，避免旧字符串覆盖持久化 session。"""
    if not cookie:
        return

    cookie_hash = hashlib.sha256(cookie.encode()).hexdigest()
    marker = os.path.join(_profile_dir(channel), ".cookie_hash")

    if os.path.exists(marker):
        with open(marker) as f:
            if f.read().strip() == cookie_hash:
                return

    page.get(domain_url)
    for pair in cookie.split(";"):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            page.set.cookies(
                {
                    "name": k.strip(),
                    "value": v.strip(),
                    "domain": cookie_domain,
                    "path": "/",
                }
            )

    with open(marker, "w") as f:
        f.write(cookie_hash)
