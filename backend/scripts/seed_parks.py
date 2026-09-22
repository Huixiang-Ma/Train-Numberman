"""工单17 · 通用化种子数据（docs/09 G1：目的地 → 景区 → 景点 三层）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成

为什么需要它：
  原 seed_places.py 只灌了单一景区的 8 个景点，数据模型里没有「目的地 / 景区」概念，
  因此"通用文旅"在数据上根本立不住。本脚本补上三层归属，并把历史景点回填到景区。

幂等：全部按 name 去重，可反复执行；已存在的行不覆盖（避免冲掉线上人工修改）。

用法：python scripts/seed_parks.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select, text  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.base import SessionLocal, create_all, engine  # noqa: E402
from app.db.models import Attraction, Destination, Park  # noqa: E402

SCHEMA = get_settings().db_schema

# ---------------------------------------------------------------------------
# 目的地：刻意跨三省，用来验证"通用"而不是"换个名字的单景区"
# ---------------------------------------------------------------------------
DESTINATIONS = [
    {
        "name": "杭州",
        "region": "浙江·杭州",
        "summary": "三面云山一面城，湖山与人文叠印的江南都会。",
        "description": (
            "西湖的湖山格局自唐宋成型，历代疏浚与营建留下了堤、岛、塔、寺相间的景观序列。"
            "宋室南渡后，这里成为文人雅集与市井繁华并存的都会。"
        ),
        "tags": ["江南", "湖山", "宋韵", "世界遗产"],
        "lon": 120.1500,
        "lat": 30.2500,
    },
    {
        "name": "苏州",
        "region": "江苏·苏州",
        "summary": "园林之城，移步换景的东方造园艺术。",
        "description": (
            "明清两代，苏州士绅以宅园合一的方式把山水缩进方寸之间，"
            "叠石、理水、花木、题匾共同构成可游可居的文人空间。"
        ),
        "tags": ["园林", "江南", "昆曲", "世界遗产"],
        "lon": 120.6200,
        "lat": 31.3200,
    },
    {
        "name": "泉州",
        "region": "福建·泉州",
        "summary": "宋元中国的世界海洋商贸中心。",
        "description": (
            "作为海上丝绸之路的重要港口，佛教、道教、伊斯兰教、印度教、摩尼教的"
            "遗存在此并存，形成罕见的多元宗教景观。"
        ),
        "tags": ["海丝", "古城", "多元宗教", "世界遗产"],
        "lon": 118.5900,
        "lat": 24.9100,
    },
]

# ---------------------------------------------------------------------------
# 景区：挂在目的地之下；历史景点默认归属第一个景区
# ---------------------------------------------------------------------------
PARKS = [
    {
        "name": "西湖文化景观",
        "destination": "杭州",
        "level": "5A",
        "summary": "以一湖两塔三岛三堤构成的湖山人文景观群。",
        "description": "首批国家 5A 级景区，2011 年列入世界遗产名录，是「文化景观」类别中湖泊类景观的代表。",
        "open_hours": "全天开放（部分景点 08:00-17:30）",
        "status": "open",
        "daily_capacity": 80000,
        "ticket_notice": "景区免费开放；部分单点（如三潭印月）单独售票，需按所选时段入园。",
        "tags": ["世界遗产", "湖山", "古建筑", "免费开放"],
        "lon": 120.1466,
        "lat": 30.2475,
    },
    {
        "name": "灵隐飞来峰",
        "destination": "杭州",
        "level": "4A",
        "summary": "江南少见的石窟造像群与山林禅寺。",
        "description": "飞来峰崖壁上现存五代至元代造像三百余尊，与冷泉、古刹共同构成山林禅意空间。",
        "open_hours": "07:00-18:00（17:30 停止入园）",
        "status": "open",
        "daily_capacity": 20000,
        "ticket_notice": "需先购飞来峰景区票，再单独购买灵隐寺香花券；建议提前预约时段。",
        "tags": ["石刻", "禅意", "山林", "造像"],
        "lon": 120.1010,
        "lat": 30.2410,
    },
    {
        "name": "拙政园",
        "destination": "苏州",
        "level": "5A",
        "summary": "江南园林之首，以水为中心的全园布局。",
        "description": "明正德年间始建，全园以水景为核心，亭台楼榭依水而筑，是中国四大名园之一。",
        "open_hours": "07:30-17:30（16:30 停止入园）",
        "status": "open",
        "daily_capacity": 12000,
        "ticket_notice": "旺季需按预约时段入园，园内瞬时承载量有限，节假日建议提前一日预约。",
        "tags": ["世界遗产", "园林", "造园", "四大名园"],
        "lon": 120.6290,
        "lat": 31.3240,
    },
    {
        "name": "平江历史街区",
        "destination": "苏州",
        "level": "4A",
        "summary": "与宋《平江图》基本吻合的水巷街区。",
        "description": "街巷格局延续宋元，河街并行、水陆相邻，是苏州古城保存最完整的历史街区。",
        "open_hours": "全天开放",
        "status": "open",
        "daily_capacity": 60000,
        "ticket_notice": "街区免费开放；评弹、手作体验等项目单独收费。",
        "tags": ["古街", "市井", "水巷", "免费开放"],
        "lon": 120.6320,
        "lat": 31.3210,
    },
    {
        "name": "开元寺",
        "destination": "泉州",
        "level": "4A",
        "summary": "以东西塔与多元宗教构件闻名的千年古刹。",
        "description": "始建于唐，大雄宝殿的柱础与廊柱保留印度教石刻，是海丝多元文化交汇的实证。",
        "open_hours": "08:00-17:30",
        "status": "open",
        "daily_capacity": 15000,
        "ticket_notice": "免费开放，需现场登记；东西塔登塔单独限流。",
        "tags": ["海丝", "石塔", "多元宗教", "世界遗产"],
        "lon": 118.5890,
        "lat": 24.9130,
    },
]

# ---------------------------------------------------------------------------
# 新增景点：每个景区补 2~3 个，保证列表页有内容可看
# 坐标用 "景区基准点 + 偏移" 表示，避免手写一堆经纬度
# ---------------------------------------------------------------------------
ATTRACTIONS = [
    # 灵隐飞来峰
    {
        "park": "灵隐飞来峰",
        "name": "飞来峰造像",
        "summary": "五代至元代的崖壁石窟造像群，现存三百余尊。",
        "description": "造像沿溪崖分布，以元代梵式造像最具特色，是江南地区石窟艺术的重要遗存。",
        "open_hours": "07:00-18:00",
        "tags": ["石刻", "造像", "历史", "艺术"],
        "offset": [0.0012, 0.0008],
    },
    {
        "park": "灵隐飞来峰",
        "name": "冷泉亭",
        "summary": "溪畔古亭，历代题咏最集中的一处。",
        "description": "亭临冷泉溪，白居易、苏轼均有题咏，亭名与对联是飞来峰人文积淀的代表。",
        "open_hours": "07:00-18:00",
        "tags": ["亭台", "题咏", "人文"],
        "offset": [-0.0006, -0.0004],
    },
    {
        "park": "灵隐飞来峰",
        "name": "灵隐寺山门",
        "summary": "千年古刹的入口，殿宇沿中轴层层递进。",
        "description": "山门内天王殿、大雄宝殿、药师殿依次排布，是禅宗五山之一的核心空间。",
        "open_hours": "07:30-17:30",
        "tags": ["寺院", "禅意", "古建筑"],
        "offset": [0.0004, 0.0014],
    },
    # 拙政园
    {
        "park": "拙政园",
        "name": "远香堂",
        "summary": "全园主厅，四面通透、临荷而筑。",
        "description": "取周敦颐《爱莲说》「香远益清」之意，堂前荷池开阔，是赏荷的主要视点。",
        "open_hours": "07:30-17:30",
        "tags": ["厅堂", "荷池", "园林"],
        "offset": [0.0002, 0.0003],
    },
    {
        "park": "拙政园",
        "name": "小飞虹廊桥",
        "summary": "园内唯一的廊桥，借桥分水、因水成景。",
        "description": "朱红桥栏倒映水面如飞虹，是江南园林中廊桥的经典实例。",
        "open_hours": "07:30-17:30",
        "tags": ["廊桥", "水景", "园林"],
        "offset": [-0.0003, 0.0001],
    },
    {
        "park": "拙政园",
        "name": "香洲",
        "summary": "形如旱船的船厅，园林建筑中的「舫」式做法。",
        "description": "两艘舫式建筑一南一北，与水面相映，是园林建筑象征手法的代表。",
        "open_hours": "07:30-17:30",
        "tags": ["船厅", "建筑", "园林"],
        "offset": [0.0001, -0.0003],
    },
    # 平江历史街区
    {
        "park": "平江历史街区",
        "name": "平江路水巷",
        "summary": "河街并行的主街，石桥与驳岸保存完好。",
        "description": "沿街河埠、石桥、过街楼连续分布，是理解苏州水城格局最直观的一段。",
        "open_hours": "全天开放",
        "tags": ["水巷", "古街", "摄影"],
        "offset": [0.0002, 0.0002],
    },
    {
        "park": "平江历史街区",
        "name": "评弹小馆",
        "summary": "可听评弹、喝碧螺春的老式书场。",
        "description": "小型书场保留传统演出形式，适合作为街区游览中的休憩与体验节点。",
        "open_hours": "13:00-21:00",
        "tags": ["昆曲", "评弹", "非遗", "休憩"],
        "offset": [-0.0002, -0.0001],
    },
    # 开元寺
    {
        "park": "开元寺",
        "name": "东西塔",
        "summary": "镇国塔与仁寿塔，宋代石构双塔。",
        "description": "两塔为八角五层仿木构石塔，塔身浮雕保存完整，是泉州湾的地标。",
        "open_hours": "08:00-17:30",
        "tags": ["石塔", "宋代", "地标", "世界遗产"],
        "offset": [0.0005, 0.0003],
    },
    {
        "park": "开元寺",
        "name": "大雄宝殿",
        "summary": "百柱殿，柱础与廊柱存印度教石刻。",
        "description": "殿内立柱近百根，其中部分柱础为印度教寺院的旧构件，是海丝文化交汇的直接物证。",
        "open_hours": "08:00-17:30",
        "tags": ["殿宇", "海丝", "多元宗教"],
        "offset": [-0.0003, 0.0002],
    },
    {
        "park": "开元寺",
        "name": "古印度教石柱",
        "summary": "藏于廊下的印度教石刻构件。",
        "description": "石刻上的浮雕题材源自印度教神话，与佛教殿宇共存一处，为国内罕见。",
        "open_hours": "08:00-17:30",
        "tags": ["石刻", "海丝", "多元宗教", "罕见"],
        "offset": [0.0001, -0.0002],
    },
]

# 历史景点（原 seed_places.py 灌入的 8 个）默认归属的景区
DEFAULT_PARK = "西湖文化景观"


def _point(longitude: float, latitude: float):
    """构造 WGS84 点要素（PostGIS）。"""
    return func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)


def ensure_park_link_column() -> None:
    """确保 `attraction.park_id` 列存在。

    create_all 只建缺失的**表**，不会给已存在的 attraction 加**列**；而本脚本紧接着就要写
    park_id。所以在建表之后、写数据之前把这条列级变更一并做掉，让脚本自包含
    （不必先手工跑 sync_schema.py，也不会因顺序搞错而插入失败）。
    与 sync_schema.py 内容一致且幂等，两边重复执行无副作用。
    """
    statements = [
        f"ALTER TABLE {SCHEMA}.attraction ADD COLUMN IF NOT EXISTS park_id varchar(32)",
        f"CREATE INDEX IF NOT EXISTS ix_attraction_park_id ON {SCHEMA}.attraction (park_id)",
        # ADD CONSTRAINT 不支持 IF NOT EXISTS，用 DO 块判断
        (
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'attraction_park_id_fkey') THEN "
            f"ALTER TABLE {SCHEMA}.attraction ADD CONSTRAINT attraction_park_id_fkey "
            f"FOREIGN KEY (park_id) REFERENCES {SCHEMA}.park(id); "
            "END IF; END $$;"
        ),
    ]
    # 逐条独立事务：PostgreSQL 中一条 DDL 失败会中止整个事务块，后续语句会连带失败
    for statement in statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(statement))
        except Exception as exc:
            print(f"  ⚠️ 结构同步跳过：{statement[:60]} -> {type(exc).__name__}: {exc}")


def main() -> None:
    create_all()  # 建 destination / park 两张新表
    ensure_park_link_column()  # 给已有的 attraction 补 park_id 列

    created = {"destination": 0, "park": 0, "attraction": 0, "linked": 0}

    with SessionLocal() as db:
        # ---------------- 目的地 ----------------
        destination_ids: dict[str, str] = {}
        for item in DESTINATIONS:
            exists = db.scalars(select(Destination).where(Destination.name == item["name"])).first()
            if exists is not None:
                destination_ids[item["name"]] = exists.id
                continue
            row = Destination(
                name=item["name"],
                region=item["region"],
                summary=item["summary"],
                description=item["description"],
                tags=item["tags"],
                geom=_point(item["lon"], item["lat"]),
            )
            db.add(row)
            db.flush()
            destination_ids[item["name"]] = row.id
            created["destination"] += 1

        # ---------------- 景区 ----------------
        park_ids: dict[str, str] = {}
        park_geo: dict[str, tuple[float, float]] = {}
        for item in PARKS:
            park_geo[item["name"]] = (item["lon"], item["lat"])
            exists = db.scalars(select(Park).where(Park.name == item["name"])).first()
            if exists is not None:
                park_ids[item["name"]] = exists.id
                continue
            row = Park(
                destination_id=destination_ids.get(item["destination"]),
                name=item["name"],
                summary=item["summary"],
                description=item["description"],
                open_hours=item["open_hours"],
                status=item["status"],
                daily_capacity=item["daily_capacity"],
                level=item["level"],
                ticket_notice=item["ticket_notice"],
                tags=item["tags"],
                geom=_point(item["lon"], item["lat"]),
            )
            db.add(row)
            db.flush()
            park_ids[item["name"]] = row.id
            created["park"] += 1

        # ---------------- 新增景点 ----------------
        for item in ATTRACTIONS:
            if db.scalars(select(Attraction).where(Attraction.name == item["name"])).first() is not None:
                continue
            base_lon, base_lat = park_geo[item["park"]]
            dx, dy = item["offset"]
            db.add(
                Attraction(
                    park_id=park_ids[item["park"]],
                    name=item["name"],
                    summary=item["summary"],
                    description=item["description"],
                    open_hours=item["open_hours"],
                    tags=item["tags"],
                    geom=_point(base_lon + dx, base_lat + dy),
                )
            )
            created["attraction"] += 1

        # ---------------- 回填历史景点的归属 ----------------
        # 原 seed_places.py 灌入的景点没有 park_id；统一挂到默认景区，
        # 使"通用化"之后不存在无归属的孤儿景点。
        orphans = db.scalars(select(Attraction).where(Attraction.park_id.is_(None))).all()
        for row in orphans:
            row.park_id = park_ids[DEFAULT_PARK]
            created["linked"] += 1

        db.commit()

        total = {
            "destination": db.scalar(select(func.count()).select_from(Destination)),
            "park": db.scalar(select(func.count()).select_from(Park)),
            "attraction": db.scalar(select(func.count()).select_from(Attraction)),
            "orphan": db.scalar(
                select(func.count()).select_from(Attraction).where(Attraction.park_id.is_(None))
            ),
        }

    print(f"本次新增：{created}")
    print(f"当前总量：{total}")


if __name__ == "__main__":
    main()
