from app.adapters.boss import BossAdapter
from app.api.routes.jobs import _job_payload
from app.core.models import SearchRequest
from app.db.schema import ScrapedJob


def test_job_payload_exposes_boss_list_fields():
    row = ScrapedJob(
        id=11067,
        channel="boss",
        external_id="job1",
        title="JAVA工程师",
        company="浙江春风动力股份...",
        salary="20-35K·14薪",
        city="杭州",
        experience="10年以上",
        education="本科",
        skills=["Java", "Python"],
        description="10年以上 · 本科 · Java",
        url="https://www.zhipin.com/job_detail/x.html",
        raw={
            "areaDistrict": "临平区",
            "businessDistrict": "东湖",
            "brandIndustry": "汽车研发/制造",
            "brandStageName": "已上市",
            "brandScaleName": "1000-9999人",
            "welfareList": ["年终奖", "五险一金"],
            "bossName": "邓娜",
            "bossTitle": "招聘经理",
        },
    )

    payload = _job_payload(row)

    assert payload["experience"] == "10年以上"
    assert payload["education"] == "本科"
    assert payload["district"] == "临平区 东湖"
    assert payload["industry"] == "汽车研发/制造"
    assert payload["stage"] == "已上市"
    assert payload["scale"] == "1000-9999人"
    assert payload["welfare"] == ["年终奖", "五险一金"]
    assert payload["recruiter"] == "邓娜 招聘经理"
    assert payload["is_remote"] is False
    assert payload["source_label"] == ""
    assert "match_score" in payload
    assert "sections" in payload
    assert isinstance(payload["sections"], list)


def test_job_payload_source_label_discord_server():
    row = ScrapedJob(
        id=1,
        channel="discord",
        external_id="dc_1",
        title="Software Engineer II, Growth",
        company="Amplitude",
        salary="$146K – $200K",
        city="远程",
        skills=["TypeScript"],
        description="",
        url="https://discord.com/channels/1488674851345531057/1",
        raw={"source_server": "CronJobs"},
    )
    assert _job_payload(row)["source_label"] == "CronJobs"


def test_boss_list_description_is_structured():
    jobs = BossAdapter._jobs_from_payload(
        {
            "zpData": {
                "jobList": [
                    {
                        "encryptJobId": "abc",
                        "jobName": "Java",
                        "brandName": "春风动力",
                        "salaryDesc": "20-35K",
                        "cityName": "杭州",
                        "areaDistrict": "临平区",
                        "businessDistrict": "东湖",
                        "jobExperience": "10年以上",
                        "jobDegree": "本科",
                        "brandIndustry": "汽车研发/制造",
                        "brandStageName": "已上市",
                        "brandScaleName": "1000-9999人",
                        "skills": ["Java", "Spring"],
                        "welfareList": ["年终奖"],
                        "bossName": "邓娜",
                        "bossTitle": "招聘经理",
                    }
                ]
            }
        },
        SearchRequest(keyword="Java", city="杭州", channel="boss"),
    )

    assert len(jobs) == 1
    assert "临平区" in jobs[0].description
    assert "技能：Java、Spring" in jobs[0].description
    assert "招聘：邓娜 招聘经理" in jobs[0].description
    assert jobs[0].experience == "10年以上"


def test_boss_parse_detail_extracts_jd():
    parsed = BossAdapter.parse_detail(
        {
            "code": 0,
            "zpData": {
                "jobInfo": {"postDescription": "岗位职责：\n1. 负责 Java 后端\n任职要求：\n1. 本科"},
                "brandComInfo": {
                    "brandName": "浙江春风动力股份有限公司",
                    "brandIntroduce": "做摩托车的。",
                },
            },
        }
    )
    assert "岗位职责" in parsed["post_description"]
    assert parsed["company"] == "浙江春风动力股份有限公司"
    assert parsed["company_intro"] == "做摩托车的。"
    assert BossAdapter.has_real_jd(parsed["post_description"])
    assert not BossAdapter.has_real_jd("10年以上 · 本科 · Java · Spring")
