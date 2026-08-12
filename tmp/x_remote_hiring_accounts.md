# X 远程办公招聘账号 —— 挖掘结果

规则见 [rules/x_remote_hiring_accounts.md](../rules/x_remote_hiring_accounts.md)。本批次抓取候选 20 个账号（发现关键词见脚本 `scripts/mine_x_remote_hiring.py`），置信度判断由人工/AI 阅读每个账号最近 15-20 条历史发帖后给出，**不是关键词硬匹配**。

抓取时间：2026-08-12（本机 Mac 环境，真实 X 登录态）

## 通过（置信度 > 70%）— 共 8 个

| screen_name | 置信度 | 判断依据 |
|---|---|---|
| [@RemoteOK](https://x.com/RemoteOK) | 90% | 知名远程招聘聚合账号，20 条历史发帖清一色远程岗位推送，格式统一，非个人账号 |
| [@remoteornothing](https://x.com/remoteornothing) | 92% | 远程岗位提醒 bot，覆盖 PagerDuty/Datadog/Gitlab/Anthropic 等真实公司真实岗位，格式高度一致，含 Telegram 提醒引流 |
| [@gonzalovega7](https://x.com/gonzalovega7) | 85% | 真实招聘方（DTC 宠物品牌），持续发布具体职位+薪资+Remote 标注，内容详实非模板灌水 |
| [@bigremotejob](https://x.com/bigremotejob) | 90% | 远程岗位聚合账号，"🔥Hiring🔥" 统一格式，公司名+薪资+Remote 地点一应俱全 |
| [@skillners](https://x.com/skillners) | 78% | 职业发展+远程岗位账号，条目详实（薪资区间、技能要求），偶有职业建议内容但招聘信息占比高 |
| [@RemoteCareerAfr](https://x.com/RemoteCareerAfr) | 85% | 持续发布"X is Hiring"格式远程岗位（Micro1/BruntWork/Mercor 等），全部标注 Remote |
| [@FarCoder](https://x.com/FarCoder) | 88% | 纯远程岗位推送 bot，"X is hiring a remote candidate for Y"统一格式，无杂质内容 |
| [@RemotejobWtessy](https://x.com/RemotejobWtessy) | 72% | 账号简介即"我每天发远程职位"，历史发帖以远程岗位为主，混有少量 VA 培训引流内容，勉强过线 |

## 未通过（<70%，附排除理由，供复核）

| screen_name | 大致置信度 | 排除理由 |
|---|---|---|
| @JobFound5 | ~55% | 混杂简历模板推广 + 疑似诈骗式"日结数据录入"帖子，质量不稳定 |
| @Presofthub | ~50% | 话题覆盖"海外工作+奖学金"泛类目，大量岗位是签证担保类现场岗，非远程为主 |
| @princessLeon7fk | ~35% | 高度重复的复制粘贴文案（同一段话改几个国家 hashtag 发几十遍），典型广告/诈骗号特征 |
| @gulfcareerhunt | ~55% | UAE 现场岗位与美国远程岗位混发，远程不是主线 |
| @EmanahGoodness | ~45% | 尼日利亚本地现场岗位（Lagos/Abuja）占比高，远程只是其中一类 |
| @JoblyGhana | ~25% | 绝大多数是加纳本地现场岗位（酒店、保安、前台） |
| @Scholarshiplug | ~55% | 奖学金内容占比接近一半，账号定位是"奖学金+工作+实习"综合类，非专注远程招聘 |
| @getaremotejobng | ~35% | 大量宗教/励志转发内容淹没了偶尔的远程岗位帖 |
| @MrCRemoteJobs | ~65% | 远程/现场岗位混发，大量 #viral #fyp #trending 泛流量 hashtag，疑似流量号而非正经招聘号 |
| @SushrutKM | ~30% | 个人账号，招聘只是偶发内容，历史发帖以个人生活/观点为主 |
| @careerdjobs | ~40% | 印度本地现场岗位（Chennai/Hyderabad/Bangalore）占多数，远程非主线 |
| @ChuksEmma947401 | ~35% | 大量励志语录/鸡汤内容，招聘信息穿插其中且现场/远程混杂 |

## 已知限制

- 候选发现只跑了 6 个关键词，扫到 75 个候选池，本批次只处理了前 20 个（脚本里 `MAX_CANDIDATES` 手动限量，避免一次性大批量请求触发账号风控，见 [issue #1](https://github.com/opc-x/Scraper/issues/1)）
- 置信度评估基于最近 15-20 条历史发帖，没有拉取账号 bio，规则文档里提到的"简介自我定位"这一项暂未纳入判断
- 没有凑够 100 个——20 个候选里只有 8 个真正达标，说明这类搜索关键词下"纯远程招聘号"的命中率大概 40% 左右，要凑到 100 个合格账号，预计需要处理 200-250 个候选，扩大批量前建议先确认账号没有因为这次测试被限流
