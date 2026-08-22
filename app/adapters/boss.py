import asyncio
import json
import os
import re
import time
from datetime import datetime
from urllib.parse import quote

from DrissionPage import ChromiumPage

from app.adapters.base import BaseAdapter
from app.core.channel_config import get_channel_config
from app.core.models import Job, SearchRequest
from app.infra import chrome

BOSS_CITY_MAP = {
    "全国": "100010000",
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "成都": "101270100",
    "南京": "101190100",
    "武汉": "101200100",
    "西安": "101110100",
    "苏州": "101190400",
    "长沙": "101250100",
    "郑州": "101180100",
    "重庆": "101040100",
    "天津": "101030100",
    "厦门": "101230200",
    "合肥": "101220100",
    "东莞": "101281600",
    "佛山": "101280800",
    "昆明": "101290100",
}

API_PATTERN = "wapi/zpgeek/search/joblist"


class BossAdapter(BaseAdapter):
    name = "boss"

    def __init__(self):
        self._page: ChromiumPage | None = None
        self.last_code = None

    async def reload(self):
        await self.close()

    def _ensure_page(self) -> ChromiumPage:
        if self._page is None:
            headless = os.environ.get("SCRAPER_CHROME_HEADLESS", "0") != "0"
            self._page = chrome.new_page("boss", headless=headless)
        cfg = get_channel_config("boss")
        chrome.sync_cookies(self._page, "boss", "https://www.zhipin.com", ".zhipin.com", cfg.get("cookie", ""))
        return self._page

    async def search(self, req: SearchRequest) -> list[Job]:
        return await asyncio.to_thread(self._search_sync, req)

    def _search_sync(self, req: SearchRequest) -> list[Job]:
        page = self._ensure_page()

        city_code = BOSS_CITY_MAP.get(req.city, "100010000")
        url = (
            f"https://www.zhipin.com/web/geek/jobs?query={quote(req.keyword)}"
            f"&city={city_code}&page={req.page}"
        )

        page.get(url)
        self.wait_if_verify()
        page.listen.start(API_PATTERN)
        page.get(url)
        self.wait_if_verify()

        try:
            packet = page.listen.wait(timeout=20)
        except Exception:
            page.listen.stop()
            return []

        page.listen.stop()

        if not packet or not packet.response:
            return []

        try:
            body = packet.response.body
            if isinstance(body, bytes):
                body = body.decode("utf-8", errors="replace")
            data = json.loads(body) if isinstance(body, str) else body
        except (json.JSONDecodeError, AttributeError, TypeError):
            return []

        if not isinstance(data, dict):
            return []
        if data.get("code") not in (0, None, "0"):
            return []
        return self._jobs_from_payload(data, req)

    def fetch_joblist(self, keyword: str, city: str, page_no: int, page_size: int = 30) -> list[Job]:
        """在已打开的浏览器里发 joblist 请求，用当前页的登录态和校验参数。"""
        page = self._ensure_page()
        self.wait_if_verify()
        city_code = BOSS_CITY_MAP.get(city, "100010000")
        api = (
            "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
            f"?scene=1&query={quote(keyword)}&city={city_code}&page={page_no}&pageSize={page_size}"
        )
        self.last_code = None
        req = SearchRequest(keyword=keyword, city=city, channel="boss", page=page_no)
        page.listen.start(API_PATTERN)
        page.run_js(
            f'fetch("{api}", {{credentials:"include", headers:{{"Accept":"application/json"}}}})'
            '.then(r=>r.json()).then(j=>window.__boss_joblist=j)'
        )
        try:
            packet = page.listen.wait(timeout=12)
        except Exception:
            packet = None
        page.listen.stop()
        data = None
        if packet and packet.response:
            try:
                body = packet.response.body
                if isinstance(body, bytes):
                    body = body.decode("utf-8", errors="replace")
                data = json.loads(body) if isinstance(body, str) else body
            except (json.JSONDecodeError, AttributeError, TypeError):
                data = None
        if not isinstance(data, dict):
            time.sleep(1.2)
            data = page.run_js("return window.__boss_joblist")
        if not isinstance(data, dict) or data.get("code") not in (0, None, "0"):
            if isinstance(data, dict):
                print(f"[boss] api code={data.get('code')} {data.get('message')}", flush=True)
                self.last_code = data.get("code")
            return []
        return self._jobs_from_payload(data, req)

    def wait_if_verify(self, timeout: int = 300) -> bool:
        """停在安全验证页等人工点击，过了再继续。"""
        page = self._page
        if page is None:
            return False
        deadline = time.time() + timeout
        waited = False
        while "verify.html" in (page.url or "") or "安全验证" in (page.title or ""):
            if not waited:
                print("[boss] 安全验证窗口在，按页面要求点完，我在这等", flush=True)
                waited = True
            if time.time() > deadline:
                print("[boss] 验证等待超时", flush=True)
                return False
            time.sleep(2)
        if waited:
            print("[boss] 验证过了，继续", flush=True)
            time.sleep(3)
        return True

    def recover_from_block(self, timeout: int = 300) -> bool:
        """接口风控时打开搜索页（会跳验证），等人点完再继续。"""
        page = self._ensure_page()
        print("[boss] 需要人工验证：窗口已顶到前面，按页面点完就行", flush=True)
        try:
            page.set.window.max()
        except Exception:
            pass
        page.get("https://www.zhipin.com/web/geek/jobs?query=Java&city=100010000")
        if "verify.html" in (page.url or "") or "安全验证" in (page.title or ""):
            ok = self.wait_if_verify(timeout)
        else:
            print("[boss] 搜索页已打开，有滑块/验证就点，我等你 90 秒", flush=True)
            deadline = time.time() + 90
            ok = True
            while time.time() < deadline:
                if "verify.html" in (page.url or "") or "安全验证" in (page.title or ""):
                    ok = self.wait_if_verify(timeout)
                    break
                time.sleep(2)
        if ok:
            self.last_code = None
            time.sleep(6)
        return ok

    @classmethod
    def _jobs_from_payload(cls, data: dict, req: SearchRequest) -> list[Job]:
        job_list = data.get("zpData", {}).get("jobList", [])
        jobs = []

        for item in job_list:
            salary = item.get("salaryDesc", "")
            if req.salary_min and salary:
                low = cls._parse_salary_low(salary)
                if low and low < req.salary_min:
                    continue

            labels = item.get("jobLabels") or []
            skills = item.get("skills") or []
            welfare = item.get("welfareList") or []
            desc_parts = [str(x) for x in labels + skills + welfare if x]
            raw = dict(item)
            raw["captured_at"] = datetime.utcnow().isoformat()
            jobs.append(
                Job(
                    channel="boss",
                    external_id=str(item.get("encryptJobId", "")),
                    title=item.get("jobName", ""),
                    company=item.get("brandName", ""),
                    salary=salary,
                    city=item.get("cityName", req.city),
                    experience=item.get("jobExperience", ""),
                    education=item.get("jobDegree", ""),
                    skills=skills if isinstance(skills, list) else [],
                    description=" · ".join(desc_parts),
                    url=f"https://www.zhipin.com/job_detail/{item.get('encryptJobId', '')}.html",
                    raw=raw,
                )
            )

        return jobs

    @staticmethod
    def _parse_salary_low(salary_desc: str) -> int | None:
        m = re.match(r"(\d+)-", salary_desc)
        if m:
            num = int(m.group(1))
            if "K" in salary_desc.upper():
                return num * 1000
            return num
        return None

    async def close(self):
        if self._page:
            try:
                self._page.quit()
            except Exception:
                pass
            self._page = None
            try:
                chrome.persist_profile("boss")
            except Exception as e:
                print(f"[boss] profile 回传跳过: {e}", flush=True)
