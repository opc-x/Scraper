import asyncio
import json
import re

from DrissionPage import ChromiumPage, ChromiumOptions

from app.adapters.base import BaseAdapter
from app.core.config import settings
from app.core.models import Job, SearchRequest

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

API_PATTERN = re.compile(r"wapi/zpgeek/search/joblist")


class BossAdapter(BaseAdapter):
    name = "boss"

    def __init__(self):
        self._page: ChromiumPage | None = None

    def _ensure_page(self) -> ChromiumPage:
        if self._page is None:
            opts = ChromiumOptions()
            opts.headless()
            opts.set_argument("--no-sandbox")
            opts.set_argument("--disable-gpu")
            if settings.boss_cookie:
                opts.set_argument(f"--cookie={settings.boss_cookie}")
            self._page = ChromiumPage(opts)
        return self._page

    async def search(self, req: SearchRequest) -> list[Job]:
        return await asyncio.to_thread(self._search_sync, req)

    def _search_sync(self, req: SearchRequest) -> list[Job]:
        page = self._ensure_page()

        city_code = BOSS_CITY_MAP.get(req.city, "100010000")
        url = f"https://www.zhipin.com/web/geek/job?query={req.keyword}&city={city_code}&page={req.page}"

        page.listen.start(API_PATTERN)
        page.get(url)

        try:
            packet = page.listen.wait(timeout=15)
        except Exception:
            page.listen.stop()
            return []

        page.listen.stop()

        if not packet or not packet.response:
            return []

        try:
            data = json.loads(packet.response.body) if isinstance(packet.response.body, str) else packet.response.body
        except (json.JSONDecodeError, AttributeError):
            return []

        job_list = data.get("zpData", {}).get("jobList", [])
        jobs = []

        for item in job_list:
            salary = item.get("salaryDesc", "")
            if req.salary_min and salary:
                low = self._parse_salary_low(salary)
                if low and low < req.salary_min:
                    continue

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
                    skills=item.get("skills", []),
                    description=item.get("jobLabels", []),
                    url=f"https://www.zhipin.com/job_detail/{item.get('encryptJobId', '')}.html",
                    raw=item,
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
            self._page.quit()
            self._page = None
