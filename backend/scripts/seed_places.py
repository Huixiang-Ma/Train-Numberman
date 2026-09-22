"""工单19 · 灌入景区实体数据（景点 / 活动 / 文物 / 人物 / 故事）

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成

为什么需要这个脚本：
  阶段四的「个性化线路策划」与「活动推荐」都以**真实景点与活动**为事实依据
  （docs/05 §3.1 / §3.3）。原 seed_kb.py 只灌了知识分块，attraction / activity
  等关系表始终为空，导致行程分站与活动推荐无候选可用。
  本脚本补齐这部分实体数据，并带 PostGIS 坐标以支撑按距离推荐。

用法：python scripts/seed_places.py
幂等：按名称去重，可重复执行。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402

from app.db.base import SessionLocal, create_all  # noqa: E402
from app.db.models import Activity, Attraction, Person, Relic, Story  # noqa: E402

# 以一处山地古建园林景区为背景；坐标为经纬度（WGS84）
BASE_LON, BASE_LAT = 120.1466, 30.2475

ATTRACTIONS = [
    {
        "name": "主殿",
        "summary": "面阔五间、进深三间的抬梁式木构主殿，是全园形制最高、木构做法最完整的一处。",
        "description": "主殿为全园核心建筑，柱上架梁、梁上立瓜柱，层层叠置成屋架，节点以榫卯为主。"
        "屋面为歇山顶，正脊两端设吻兽，檐下斗拱层数体现建筑等级。殿内可近距离观察梁架与斗拱。",
        "open_hours": "08:30 - 17:00",
        "tags": ["古建筑", "历史", "木构", "斗拱"],
        "offset": (0.0, 0.0),
    },
    {
        "name": "东壁壁画廊",
        "summary": "连续叙事壁画长廊，矿物颜料绘制，可据服饰器物判断年代。",
        "description": "壁画以矿物颜料绘制，自出行场景起首，中段为主体仪仗，末端为宴饮，采用散点透视。"
        "人物衣纹线条流畅，局部有起甲与褪色，已做保护性修复，廊内设低照度展陈照明。",
        "open_hours": "09:00 - 16:30",
        "tags": ["壁画", "历史", "艺术", "叙事"],
        "offset": (0.0012, 0.0006),
    },
    {
        "name": "修葺碑亭",
        "summary": "存修葺碑记与后补题记，是研究地方营造组织与宗族参与的一手材料。",
        "description": "碑文楷书阴刻，记述修葺缘由、捐资名录与工匠分工，碑末有纪年可与地方志互证。"
        "碑侧另存小块题记记录后续补修。亭内设拓片对照展板，适合细读。",
        "open_hours": "08:30 - 17:00",
        "tags": ["碑刻", "历史", "书法", "石刻"],
        "offset": (-0.0009, 0.0008),
    },
    {
        "name": "先贤祠",
        "summary": "地方先贤纪念造像与基座题记，可与地方人物志互相印证。",
        "description": "造像面容端肃、手持书卷，基座题记交代立像时间与倡建者，反映后世对先贤功业的追念。"
        "祠内陈列地方人物志摘编，便于串起人物与建筑的故事线。",
        "open_hours": "09:00 - 16:30",
        "tags": ["人物", "历史", "造像", "人文"],
        "offset": (0.0006, -0.0007),
    },
    {
        "name": "水榭茶室",
        "summary": "临水休憩点，供应本地茶点与非遗小吃，是半日游的中场休息处。",
        "description": "水榭三面临水，设座约四十位，供应本地点茶、时令河鲜与传统面点。"
        "午后光线斜照水面，是园内最受欢迎的拍照与休憩点位之一。",
        "open_hours": "09:30 - 17:30",
        "tags": ["美食", "休憩", "茶", "亲子"],
        "offset": (-0.0007, -0.0004),
    },
    {
        "name": "登高台",
        "summary": "全园制高点，可俯瞰屋脊与山色，日落时段视野最佳。",
        "description": "经石阶上行约 120 级可达，平台可俯瞰整片屋面与远处山峦。"
        "建议在日落前 40 分钟登台，既能看屋脊光影，也便于拍摄全景。",
        "open_hours": "08:30 - 18:00",
        "tags": ["摄影", "自然", "观景"],
        "offset": (0.0016, 0.0011),
    },
    {
        "name": "非遗研学角",
        "summary": "碑拓、斗拱拼装等手作体验区，适合亲子参与，需提前预约。",
        "description": "研学角开设碑拓、斗拱拼装、壁画临摹等手作课程，单次约 40 分钟，"
        "由非遗传承人带教，成品可带走。周末场次紧张，建议提前一天预约。",
        "open_hours": "10:00 - 16:00（周一闭馆）",
        "tags": ["非遗", "亲子", "手作", "活动"],
        "offset": (0.0004, 0.0013),
    },
    {
        "name": "山门广场",
        "summary": "景区主入口与集散广场，设导览服务台、轮椅借用与寄存处。",
        "description": "山门广场为游客集散地，设导览服务台、电子讲解领取点、轮椅与婴儿车借用处。"
        "广场东侧为票务与安检通道，西侧接商业街。",
        "open_hours": "08:00 - 18:00",
        "tags": ["服务", "入口", "集散"],
        "offset": (-0.0014, -0.0016),
    },
]

ACTIVITIES = [
    {
        "name": "碑拓手作体验",
        "schedule": "每日 10:00 / 14:00 两场，每场 40 分钟",
        "description": "非遗传承人带教的碑拓手作，含上纸、捶打、上墨、揭取四个步骤，成品可带走。",
        "how_to_join": "在导览端或研学角现场预约，凭预约码入场；每场限 12 人，建议提前一天预约。",
        "tags": ["非遗", "亲子", "手作"],
        "offset": (0.0004, 0.0013),
    },
    {
        "name": "宋代点茶体验",
        "schedule": "每日 11:00 - 15:00 循环开放，单次约 30 分钟",
        "description": "在水榭茶室体验宋代点茶，含炙茶、碾茶、罗茶、候汤、击拂等环节。",
        "how_to_join": "水榭茶室现场排号，无需预约；每轮限 8 人，高峰期约需等位 20 分钟。",
        "tags": ["美食", "非遗", "茶", "体验"],
        "offset": (-0.0007, -0.0004),
    },
    {
        "name": "斗拱拼装课堂",
        "schedule": "每日 13:30 一场，约 50 分钟",
        "description": "用等比例斗拱模型讲解榫卯与受力，动手拼装一攒斗拱并了解其在屋架中的作用。",
        "how_to_join": "研学角现场报名，适合 8 岁以上；每场 16 人，建议提前 30 分钟到场。",
        "tags": ["古建筑", "亲子", "研学", "手作"],
        "offset": (0.0004, 0.0013),
    },
    {
        "name": "壁画临摹工坊",
        "schedule": "每周六 15:00 一场，约 60 分钟",
        "description": "在东壁壁画廊侧厅跟临壁画局部，讲解矿物颜料与线描技法。",
        "how_to_join": "需在导览端提前预约，每场 10 人；材料由工坊提供，成品可带走。",
        "tags": ["壁画", "艺术", "研学"],
        "offset": (0.0012, 0.0006),
    },
    {
        "name": "夜间灯彩游园",
        "schedule": "节令期间 18:30 - 21:00 开放",
        "description": "沿主殿至水榭一线布置传统灯彩，含灯谜与夜游讲解。",
        "how_to_join": "凭当日门票入园，无需另外预约；建议 19:00 前入园以走完全程。",
        "tags": ["夜游", "亲子", "灯彩"],
        "offset": (0.0, 0.0),
    },
    {
        "name": "实景演绎《山水间》",
        "schedule": "每日 16:00 一场，约 35 分钟",
        "description": "以水榭实景为舞台的地方题材实景演绎，讲本地营造与家族故事。",
        "how_to_join": "按场次入场，座位先到先得；雨天移至主殿前廊演出。",
        "tags": ["演艺", "人文", "历史"],
        "offset": (-0.0007, -0.0004),
    },
    {
        "name": "乡土植物物候观察",
        "schedule": "每日 09:30 - 11:00 自由参与",
        "description": "沿登高台步道观察乡土树种的叶形、树皮与花果，配物候记录卡。",
        "how_to_join": "在山门服务台领取记录卡即可参与，无人数限制，适合亲子。",
        "tags": ["自然", "生态", "科普", "亲子"],
        "offset": (0.0016, 0.0011),
    },
    {
        "name": "非遗小吃市集",
        "schedule": "每日 11:00 - 17:00",
        "description": "集中供应传统面点、时令河鲜与非遗手工小吃，可一次尝遍本地风味。",
        "how_to_join": "市集自由入场，扫码点单；建议避开 12:00 - 13:00 高峰时段。",
        "tags": ["美食", "非遗", "市集"],
        "offset": (-0.0007, -0.0004),
    },
]

RELICS = [
    {"name": "抬梁式梁架", "category": "木构", "era": "明清", "description": "柱上架梁、梁上立瓜柱的抬梁式屋架，节点以榫卯为主。"},
    {"name": "歇山顶屋面", "category": "屋面", "era": "明清", "description": "一条正脊、四条垂脊、四条戗脊，正脊两端设吻兽。"},
    {"name": "修葺碑记", "category": "碑刻", "era": "清代", "description": "楷书阴刻，记修葺缘由、捐资名录与工匠分工。"},
    {"name": "东壁叙事壁画", "category": "壁画", "era": "明代", "description": "矿物颜料绘制的连续叙事壁画，散点透视。"},
    {"name": "先贤造像", "category": "造像", "era": "清代", "description": "地方先贤纪念像，面容端肃、手持书卷，基座有题记。"},
]

PERSONS = [
    {"name": "倡建者·乡贤公", "lifespan": "约 1640 - 1705", "bio": "倡建并主持修葺本园的地方乡贤，碑记中列其名于捐资名录之首。"},
    {"name": "营造成匠师", "lifespan": "生卒不详", "bio": "主持本园木构营造的匠师，碑侧题记记其后续补修之事。"},
]

STORIES = [
    {
        "title": "榫卯为何不用铁钉",
        "content": "主殿屋架以榫卯相接、不用铁钉，并非只为节省材料。木构受温度湿度影响会伸缩，"
        "榫卯节点的微量活动恰好吸收了这种形变，反而比刚性连接更耐久。这也是本地木构能留存至今的原因之一。",
        "tags": ["古建筑", "木构", "榫卯"],
        "subject_type": "attraction",
        "subject_name": "主殿",
    },
    {
        "title": "壁画里的出行队伍",
        "content": "东壁壁画起首的出行场景中，人马排布由疏到密，衣纹线随行进方向倾斜，"
        "形成向前的动势。这类处理在同期壁画中并不少见，但本处保留了完整的仪仗序列，因此叙事价值较高。",
        "tags": ["壁画", "叙事", "艺术"],
        "subject_type": "attraction",
        "subject_name": "东壁壁画廊",
    },
    {
        "title": "碑记中的工匠分工",
        "content": "修葺碑记末尾列有工匠分工：木作、瓦作、石作、油作各有其人。"
        "这种分工记录说明当时的营造已相当组织化，也让后人得以还原一次完整修缮的协作结构。",
        "tags": ["碑刻", "营造", "工匠"],
        "subject_type": "attraction",
        "subject_name": "修葺碑亭",
    },
]


def _point(longitude: float, latitude: float):
    """构造 WGS84 点要素（PostGIS）。"""
    return func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)


def main() -> None:
    create_all()
    created = {"attraction": 0, "activity": 0, "relic": 0, "person": 0, "story": 0}

    with SessionLocal() as db:
        # ---- 景点 ----
        attraction_ids: dict[str, str] = {}
        for item in ATTRACTIONS:
            exists = db.scalars(select(Attraction).where(Attraction.name == item["name"])).first()
            if exists is not None:
                attraction_ids[item["name"]] = exists.id
                continue
            dx, dy = item["offset"]
            row = Attraction(
                name=item["name"],
                summary=item["summary"],
                description=item["description"],
                open_hours=item["open_hours"],
                tags=item["tags"],
                geom=_point(BASE_LON + dx, BASE_LAT + dy),
            )
            db.add(row)
            db.flush()
            attraction_ids[item["name"]] = row.id
            created["attraction"] += 1

        # ---- 活动（挂到就近景点）----
        for item in ACTIVITIES:
            if db.scalars(select(Activity).where(Activity.name == item["name"])).first() is not None:
                continue
            dx, dy = item["offset"]
            # 归属景点：取坐标完全一致的那一处
            owner = None
            for attraction in ATTRACTIONS:
                if attraction["offset"] == item["offset"]:
                    owner = attraction_ids.get(attraction["name"])
                    break
            db.add(
                Activity(
                    name=item["name"],
                    schedule=item["schedule"],
                    description=item["description"],
                    how_to_join=item["how_to_join"],
                    attraction_id=owner,
                    geom=_point(BASE_LON + dx, BASE_LAT + dy),
                )
            )
            created["activity"] += 1

        # ---- 文物 / 人物 ----
        for item in RELICS:
            if db.scalars(select(Relic).where(Relic.name == item["name"])).first() is None:
                db.add(Relic(**item))
                created["relic"] += 1
        for item in PERSONS:
            if db.scalars(select(Person).where(Person.name == item["name"])).first() is None:
                db.add(Person(**item))
                created["person"] += 1

        # ---- 故事（按名称关联到景点）----
        for item in STORIES:
            if db.scalars(select(Story).where(Story.title == item["title"])).first() is not None:
                continue
            payload = dict(item)
            subject_name = payload.pop("subject_name", "")
            db.add(Story(**payload, subject_id=attraction_ids.get(subject_name)))
            created["story"] += 1

        db.commit()

        # 活动未挂上景点时，按坐标就近补挂一次，保证推荐结果能显示所属景点
        for activity in db.scalars(select(Activity).where(Activity.attraction_id.is_(None))):
            if activity.geom is None:
                continue
            nearest = db.scalars(
                select(Attraction)
                .where(Attraction.geom.isnot(None))
                .order_by(func.ST_Distance(Attraction.geom, activity.geom))
                .limit(1)
            ).first()
            if nearest is not None:
                activity.attraction_id = nearest.id
        db.commit()

        total = {
            "attraction": db.scalar(select(func.count()).select_from(Attraction)),
            "activity": db.scalar(select(func.count()).select_from(Activity)),
            "relic": db.scalar(select(func.count()).select_from(Relic)),
            "person": db.scalar(select(func.count()).select_from(Person)),
            "story": db.scalar(select(func.count()).select_from(Story)),
        }

    print(f"本次新增：{created}")
    print(f"当前总量：{total}")


if __name__ == "__main__":
    main()
