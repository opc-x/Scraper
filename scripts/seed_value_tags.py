"""价值观评分的内置起手标签（"价值观"维度）：加班 / 开会 / 内耗 / 对接 / 事逼。

五条全部是红色警示标签（polarity=-1），命中就扣分，在列表页/详情页职位卡片上
统一标红显示；没命中则视为确认干净，标绿。不是走「用户描述 -> AI 生成草稿」流程，
是重写时按用户明确给的五个维度直接手写的内置起点。
跑一次就够，已存在同名标签不会重复插入；改名或调权重直接在库里改，不用重跑这个脚本。

用法：python -m scripts.seed_value_tags
"""

from app.db.connection import SessionLocal
from app.db.schema import ValueTag

CATEGORY = "价值观"

SEED = [
    # (label, pattern, polarity, weight, rationale)
    ("加班", r"\b(996|997|10/9/6|mandatory\s?overtime|clock-?in)\b|大小周|强制打卡|经常加班|加班文化|单休|大礼拜",
     -1, 25, "996/大小周/强制打卡/经常加班，最直接的高强度信号，权重最高"),
    ("开会", r"\b(back-to-back\s?meetings|meeting-heavy|daily\s?standup\s?mandatory)\b|会议多|频繁开会|全天开会|会议繁多|高频对齐会",
     -1, 15, "会议密度高，挤占实际产出时间"),
    ("内耗", r"\b(office\s?politics|internal\s?friction|multiple\s?reporting\s?lines)\b|内耗|办公室政治|复杂汇报线|多头管理|部门壁垒",
     -1, 20, "汇报线复杂/办公室政治，实际产出被内部消耗掉"),
    ("对接", r"\b(cross-team\s?coordination|stakeholder\s?alignment|drive\s?alignment)\b|频繁对接|跨部门对接|多方对接|对接需求方|对接甲方",
     -1, 15, "岗位描述里反复强调对接工作，意味着大量协调而非技术产出"),
    ("事逼", r"\b(excessive\s?reporting|micromanagement|red\s?tape)\b|写周报|写日报|形式主义|过度流程|频繁汇报|层层审批",
     -1, 15, "高频写汇报材料/走流程，典型形式主义信号"),
]

LOW_ENGLISH_LABEL = "低英语要求"
LOW_ENGLISH_PATTERN = (
    r"[\u4e00-\u9fff]|mandarin|chinese[- ]speaking|no english required|"
    r"english not required|英语不限|不要求英语|中文办公|中文沟通|普通话"
)
LOW_ENGLISH_RATIONALE = "中文环境或不要求英语则命中（绿）；纯英文/高英语门槛未命中（红）。每条职位都露出。"
LOW_SALARY_LABEL = "低工资"
LOW_SALARY_THRESHOLD_USD = 60_000
LOW_SALARY_RATIONALE = "披露的年薪折算不到 6 万美元，跟薪资统计里最低那档口径一致"

# 旧命名（改名前用过），迁移时把这些行原地改名+挪维度，而不是删了重插，保留 id 和历史数据
RENAME_FROM = {"反加班": "加班", "反开会": "开会", "反内耗": "内耗", "反对接": "对接", "反事逼": "事逼"}


def main() -> None:
    db = SessionLocal()
    try:
        # 迁移旧的"反 XX"命名 -> 新命名 + 新维度
        renamed = 0
        for old_label, new_label in RENAME_FROM.items():
            row = db.query(ValueTag).filter_by(label=old_label).first()
            if row:
                row.label = new_label
                row.category = CATEGORY
                renamed += 1
        db.commit()

        keep_labels = {label for label, *_ in SEED} | {LOW_SALARY_LABEL, LOW_ENGLISH_LABEL}
        removed = db.query(ValueTag).filter(
            ValueTag.description.like("[种子标签]%"), ~ValueTag.label.in_(keep_labels)
        ).delete(synchronize_session=False)

        existing = {t.label for t in db.query(ValueTag).all()}
        added = 0
        for label, pattern, polarity, weight, rationale in SEED:
            if label in existing:
                continue
            db.add(ValueTag(
                description=f"[种子标签] {rationale}",
                label=label, category=CATEGORY, pattern=pattern, polarity=polarity, weight=weight,
                rationale=rationale, status="approved",
            ))
            added += 1

        if LOW_SALARY_LABEL not in existing:
            db.add(ValueTag(
                description=f"[种子标签] {LOW_SALARY_RATIONALE}",
                label=LOW_SALARY_LABEL, category=CATEGORY, pattern="(salary-threshold, no pattern)",
                polarity=-1, weight=20, rationale=LOW_SALARY_RATIONALE, status="approved",
                salary_below_usd=LOW_SALARY_THRESHOLD_USD,
            ))
            added += 1

        row = db.query(ValueTag).filter_by(label=LOW_ENGLISH_LABEL).first()
        if not row:
            db.add(ValueTag(
                description=f"[种子标签] {LOW_ENGLISH_RATIONALE}",
                label=LOW_ENGLISH_LABEL, category=CATEGORY, pattern=LOW_ENGLISH_PATTERN,
                polarity=1, weight=20, rationale=LOW_ENGLISH_RATIONALE, status="approved",
                pinned=True,
            ))
            added += 1
        else:
            row.pattern = LOW_ENGLISH_PATTERN
            row.polarity = 1
            row.pinned = True
            row.status = "approved"
            row.weight = 20
            row.rationale = LOW_ENGLISH_RATIONALE
            row.description = f"[种子标签] {LOW_ENGLISH_RATIONALE}"

        db.commit()
        print(f"renamed {renamed}, added {added} value tags, removed {removed} superseded seed tags ({len(SEED) - added - renamed} already existed)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
