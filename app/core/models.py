from pydantic import BaseModel


class SearchRequest(BaseModel):
    keyword: str
    city: str = ""
    salary_min: int | None = None
    salary_max: int | None = None
    channel: str = "boss"
    page: int = 1
    within_days: int = 90


class Job(BaseModel):
    channel: str
    external_id: str
    title: str
    company: str
    salary: str
    salary_cny: str = ""
    city: str
    experience: str = ""
    education: str = ""
    skills: list[str] = []
    description: str = ""
    url: str = ""
    raw: dict = {}


class SearchResponse(BaseModel):
    jobs: list[Job]
    total: int
    page: int
    channel: str
