"""從《蔚藍檔案・奇普托斯》世界書產生「角色卡」世界書與角色卡總表。

用法：
    python3 build_cards.py <原世界書.json> <輸出資料夾>

角色卡只收角色本人的資訊（身分、外觀、衣裝、性格、思考、動機、
言行、說話方式、日常、能力、演出守則），劇情相關內容一律排除：
- 整段排除：history、knowledge 欄位，以及「經歷與關係」條目。
- 人際關係：relationships 只取「對象」與「基本關係」一句，互動細節、看法與衝突不收；
  關係句中帶劇情的部分依 basic_relationship_edits.json 改寫或刪除。
- 欄位排除：identity 中的時間線欄位、behavior 中針對特定人物的互動欄位。
- 逐句處理：其餘欄位中描述特定劇情事件經過、結果或真相的句子，
  依 plot_sentence_edits.json 刪除或改寫成不含劇情的特質描述。
"""
import json
import re
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

CORE_SECTIONS = [
    "identity", "appearance", "personality", "thinking", "motivations",
    "behavior", "speech", "daily_life", "abilities", "portrayal_guardrails",
]
EXCLUDED_SECTIONS = ["history", "relationships", "knowledge"]
META_KEYS = {"name", "entry_role", "usage_scope"}

# identity 中屬於劇情時間線的欄位
IDENTITY_TIMELINE_KEYS = {"timeline_scope", "period_note", "period"}

# 針對特定人物的互動模式，屬於人際關係而非角色本人資訊
RELATION_KEYS = {
    "behavior": {
        "with_ibuki", "with_aru", "with_makoto", "with_haruka", "with_mutsuki",
        "with_fuuka", "with_juri", "with_hina", "with_kasumi", "with_kirara",
        "with_yuuka", "with_koyuki", "with_kanna", "with_fubuki", "with_miyako",
        "with_hanako", "with_hasumi", "with_shun", "with_sakurako", "with_saori",
        "with_mirai", "with_rin", "partner", "sister", "sisters", "friend_care",
    },
    "thinking": {"relationships", "senior"},
}

SENTENCE = re.compile(r"[^。！？；]+[。！？；]?|[。！？；]")
INDEX = re.compile(r"\[\d+\]")

SCHOOL_ALIASES = {
    "三一": "三一綜合學園",
    "千年": "千年科學學園",
    "奧利斯": "奧利斯分校",
    "赤冬": "赤冬聯邦學園",
    "山海經": "山海經高級中學",
}
YEAR_ALIASES = {"1": "一年級", "2": "二年級", "3": "三年級", 1: "一年級", 2: "二年級", 3: "三年級"}

# 學籍、所屬寫成敘述句或缺漏者，總表改用人工整理的欄位：(分組, 年級, 所屬, 職位, 備註)
ROSTER_OVERRIDES = {
    "白子＊TERROR": ("其他世界", "", "（原世界）阿拜多斯對策委員會", "", "來自另一個世界的白子"),
    "小空": ("其他人物", "", "天使24夏萊分店", "店員", ""),
    "彩奈": ("夏萊", "", "希迪姆的箱子", "", "系統中的存在"),
    "星奈": ("夏萊", "", "希迪姆的箱子", "", "系統中的存在"),
    "木乃香": ("女武神警察學園", "", "公安局", "", ""),
    "愛麗絲": ("千年科學學園", "一年級", "遊戲開發部", "", ""),
    "小春": ("三一綜合學園", "一年級", "補課部", "", "原屬實現正義部"),
    "翼": ("千年科學學園", "", "原偽科學部", "", "以個人研究與實況活動延續興趣"),
    "若藻": ("百鬼夜行聯合學園", "", "", "", "停學中；七囚人之一"),
    "陽葵": ("千年科學學園", "三年級", "特異現象搜查部", "", ""),
    "雛罌粟": ("百鬼夜行相關勢力", "", "花鳥風月部", "部長", ""),
    "棕櫚": ("百鬼夜行相關勢力", "", "花鳥風月部", "", "正式學籍不明"),
    "薊": ("百鬼夜行相關勢力", "", "花鳥風月部", "", "正式學籍、年級不明"),
    "Kei": ("千年科學學園", "", "與遊戲開發部共同活動", "", ""),
    "良舞": ("無學籍・其他", "", "嘩啦嘩啦頭盔團", "", "原三一學生，已退學"),
    "昴": ("奧利斯分校", "三年級", "尼科米底亞部隊", "", ""),
    "彌香": ("三一綜合學園", "三年級", "茶會・聖父派", "名義上的暫任代表", ""),
    "誡": ("無學籍・其他", "", "原煉丹部部長", "", "原山海經學生，已退學；七囚人之一"),
    "晶": ("狂獵藝術學院", "", "舍監隊", "幹部", "另以怪盜身分行動"),
    "葛葉": ("百鬼夜行相關勢力", "", "百花繚亂紛爭調停委員會", "初代委員長", "無已知現役學籍"),
    "瑪爾庫特": ("十字神名", "", "十字神名", "第十位預言者", "未確認現役學籍"),
    "艾茵": ("十字神名", "", "十字神名", "技師", "沒有確認的學籍"),
    "奧爾": ("十字神名", "", "十字神名", "技師", "沒有確認的學籍"),
    "索芙": ("十字神名", "", "十字神名", "技師", "沒有確認的學籍"),
    "聯邦學生會會長": ("聯邦學生會", "", "聯邦學生會", "會長", "失蹤中"),
    "明美": ("無學籍・其他", "", "", "混混學生首領", "七囚人之一；原學籍不明"),
    "莉央": ("千年科學學園", "三年級", "研討會", "前會長", ""),
    "小雪": ("千年科學學園", "一年級", "研討會", "成員", ""),
    "白芭蕾": ("其他勢力", "", "優斯緹娜聖徒會", "", ""),
    "頭盔團一般成員": ("其他勢力", "", "頭盔團", "一般成員", ""),
    "安普羅西斯": ("其他勢力", "", "", "", "異常造物"),
    "普雷納帕特斯": ("其他世界", "", "", "", "另一個世界的老師"),
    "沙織": ("奧利斯分校", "二年級", "奧利斯小隊", "前隊長", "目前離開小隊生活"),
    "未來": ("千年科學學園", "", "原偽科學部", "前部長", ""),
    "廣美": ("狂獵藝術學院", "", "舍監隊", "副隊長", "文學系"),
    "伊吹": ("格黑娜學園", "一年級", "萬魔殿", "成員", "跳級生"),
    "泉": ("格黑娜學園", "二年級", "美食研究會", "社員", ""),
    "繪里香": ("格黑娜學園", "二年級", "閃亮亮部", "創社成員", ""),
    "綺羅羅": ("格黑娜學園", "二年級", "閃亮亮部", "部長", ""),
    "黑服": ("數秘術", "", "數秘術", "研究者", ""),
    "貝雅特里榭": ("數秘術", "", "數秘術", "成員", "自稱夫人"),
    "戈爾孔特與轉印": ("數秘術", "", "數秘術", "成員", "雙人組外觀"),
    "法蘭西斯": ("數秘術", "", "數秘術", "", "與戈爾孔特相關的新人格"),
    "瑪艾斯托洛": ("數秘術", "", "數秘術", "成員", "自居藝術家"),
    "地下生活者": ("數秘術", "", "數秘術", "前成員", "遭驅逐"),
}
FALLBACK_GROUP = "其他人物"
GROUP_ORDER = [
    "阿拜多斯高中", "格黑娜學園", "千年科學學園", "三一綜合學園", "百鬼夜行聯合學園",
    "百鬼夜行相關勢力", "山海經高級中學", "赤冬聯邦學園", "狂獵藝術學院", "女武神警察學園",
    "SRT特殊學園", "奧利斯分校", "高地人鐵道學園", "克洛諾斯學園", "聯邦學生會", "夏萊",
    "十字神名", "數秘術", "無學籍・其他", "凱薩集團", "其他勢力", "其他世界", FALLBACK_GROUP,
]


def body_of(entry):
    c = entry["content"]
    return json.loads(c[c.index("{"):c.rindex("}") + 1], object_pairs_hook=OrderedDict)


def wrap(name, obj):
    return f"［{name}］\n{json.dumps(obj, ensure_ascii=False, separators=(',', ':'))}\n［/{name}］"


class SentenceEditor:
    def __init__(self, path):
        self.edits = {}
        # path 不含清單索引（例如 thinking.blind_spots），避免前面項目刪除後索引位移
        for e in json.load(open(path, encoding="utf-8")):
            self.edits[(e["scope"], e["name"], e["path"], e["original"])] = e["replacement"]
        self.used = set()
        self.count = defaultdict(lambda: {"deleted": 0, "rewritten": 0})

    def text(self, scope, name, path, s):
        parts = SENTENCE.findall(s)
        if "".join(parts) != s:
            return s
        out = []
        for part in parts:
            key = (scope, name, INDEX.sub("", path), part.strip())
            if key in self.edits:
                self.used.add(key)
                new = self.edits[key]
                self.count[name]["rewritten" if new else "deleted"] += 1
                if new:
                    out.append(new)
            else:
                out.append(part)
        t = "".join(out).strip()
        if t.endswith("；"):
            t = t[:-1] + "。"
        return t

    def walk(self, scope, name, x, path):
        """回傳處理後的值；若整個值被清空則回傳 None。"""
        if isinstance(x, dict):
            res = OrderedDict()
            for k, v in x.items():
                nv = self.walk(scope, name, v, f"{path}.{k}")
                if nv is not None:
                    res[k] = nv
            return res or None
        if isinstance(x, list):
            res = []
            for i, v in enumerate(x):
                nv = self.walk(scope, name, v, f"{path}[{i}]")
                if nv is not None:
                    res.append(nv)
            return res or None
        if isinstance(x, str):
            return self.text(scope, name, path, x) or None
        return x


class RelationshipEditor:
    """把原本的 relationships 收斂成「對象＋一句基本關係」。"""

    def __init__(self, path):
        self.edits = {}
        for e in json.load(open(path, encoding="utf-8")):
            self.edits[(e["name"], e["character"])] = (e["original"], e["replacement"])
        self.used = set()

    def basic(self, name, rels):
        out = []
        for r in rels or []:
            who, text = r.get("character"), (r.get("relationship") or "").strip()
            if not who or not text:
                continue
            key = (name, who)
            if key in self.edits:
                original, new = self.edits[key]
                if original != text:
                    raise SystemExit(f"關係原文已變動，請重新確認：{name}→{who}")
                self.used.add(key)
                text = new
            else:
                # 只取第一句，後面多半是互動細節或劇情脈絡
                text = re.match(r"[^。]*。?", text).group(0)
            if text:
                out.append(OrderedDict([("character", who), ("relationship", text)]))
        return out


def build_core(name, core, editor, rel_editor):
    card = OrderedDict()
    card["name"] = name
    card["entry_role"] = "character_card"
    card["usage_scope"] = (
        f"{name}本人的身分、外觀、性格、思考、動機、言行、說話方式、日常與能力。"
        "另附基本人物關係（對象與身分關係）。不含劇情經歷、互動細節與情報知識；劇情請由劇情條目另行提供。"
    )
    for sec in CORE_SECTIONS:
        val = core.get(sec)
        if val is None:
            continue
        if sec == "identity" and isinstance(val, dict):
            val = OrderedDict((k, v) for k, v in val.items() if k not in IDENTITY_TIMELINE_KEYS)
        if sec in RELATION_KEYS and isinstance(val, dict):
            val = OrderedDict((k, v) for k, v in val.items() if k not in RELATION_KEYS[sec])
        val = editor.walk("人物", name, val, sec)
        if val is not None:
            card[sec] = val
    rels = rel_editor.basic(name, core.get("relationships"))
    if rels:
        card["basic_relationships"] = rels
    return card


SUB_SCOPES = {
    "外觀與衣裝": "{name}的外觀與衣裝細節；換裝或需要外觀連貫描寫時使用。",
    "專長與行動": "{name}的專長、行動方式與能力限制；需要具體行動或能力描寫時使用。",
}


def build_sub(name, sub, scope, role, editor):
    card = OrderedDict()
    card["name"] = name
    card["entry_role"] = role
    # 原條目的 usage_scope 常寫明適用的劇情時期，改用不含劇情的通用說明
    card["usage_scope"] = SUB_SCOPES[scope].format(name=name)
    for k, v in sub.items():
        if k in META_KEYS:
            continue
        nv = editor.walk(scope, name, v, k)
        if nv is not None:
            card[k] = nv
    return card


def short(s):
    if not s:
        return ""
    s = str(s).strip().rstrip("。")
    return re.split(r"[，。；]", s)[0]


def roster_row(name, identity):
    if name in ROSTER_OVERRIDES:
        return ROSTER_OVERRIDES[name]
    school = identity.get("school") or ""
    school = SCHOOL_ALIASES.get(school, school)
    org = identity.get("organization") or identity.get("affiliation") or identity.get("association") or ""
    if school and school in GROUP_ORDER:
        group = school
    elif org.startswith("凱薩"):
        group = "凱薩集團"
    elif org == "聯邦學生會" or school == "聯邦學生會":
        group = "聯邦學生會"
    else:
        group = FALLBACK_GROUP
    year = identity.get("year") or ""
    year = YEAR_ALIASES.get(year, year)
    return (group, year, short(org), short(identity.get("position")), "")


def main(src, out_dir):
    src_entries = json.load(open(src, encoding="utf-8"))["entries"]
    editor = SentenceEditor(HERE / "plot_sentence_edits.json")
    rel_editor = RelationshipEditor(HERE / "basic_relationship_edits.json")

    per = defaultdict(dict)
    order = []
    for e in sorted(src_entries.values(), key=lambda e: e["uid"]):
        owner, _, cat = e["comment"].rpartition("・")
        if cat in ("人物", "外觀與衣裝", "專長與行動", "經歷與關係"):
            if owner not in per:
                order.append(owner)
            per[owner][cat] = e

    def entry_from(src_entry, uid, comment, content):
        e = json.loads(json.dumps(src_entry))
        e.update(uid=uid, comment=comment, content=content, displayIndex=uid)
        return e

    entries = OrderedDict()
    roster = []
    report = []
    uid = 1
    for name in order:
        parts = per[name]
        if "人物" not in parts:
            continue
        core = body_of(parts["人物"])
        cname = core["name"]
        card = build_core(cname, core, editor, rel_editor)
        entries[str(uid)] = entry_from(parts["人物"], uid, f"{cname}・角色卡", wrap(cname, card))
        made = ["人物"]
        uid += 1
        for cat, role in (("外觀與衣裝", "character_card_appearance"), ("專長與行動", "character_card_capabilities")):
            if cat in parts:
                sub = build_sub(cname, body_of(parts[cat]), cat, role, editor)
                entries[str(uid)] = entry_from(parts[cat], uid, f"{cname}・角色卡・{cat}", wrap(cname, sub))
                made.append(cat)
                uid += 1
        group, year, org, pos, note = roster_row(cname, core.get("identity") or {})
        roster.append(dict(name=cname, group=group, year=year, org=org, position=pos, note=note))
        report.append(dict(
            name=cname, made=made, excluded_history_entry="經歷與關係" in parts,
            relationships=len(card.get("basic_relationships", [])),
            **editor.count[cname],
        ))

    groups = OrderedDict((g, []) for g in GROUP_ORDER)
    for r in roster:
        groups.setdefault(r["group"], []).append(r)
    lines = OrderedDict()
    for g, rows in groups.items():
        if rows:
            lines[g] = ["｜".join(x or "—" for x in (r["name"], r["year"], r["org"], r["position"])) + (f"（{r['note']}）" if r["note"] else "") for r in rows]
    roster_obj = OrderedDict([
        ("name", "角色卡總表"),
        ("entry_role", "roster"),
        ("usage_scope", "列出本世界書收錄角色卡的人物與基本所屬，只供辨識人物；不含劇情，也不代表人物都在場。"),
        ("format", "名稱｜年級｜所屬｜職位（備註）；— 表示未定或不明"),
        ("groups", lines),
    ])
    template = next(iter(entries.values()))
    roster_entry = json.loads(json.dumps(template))
    roster_entry.update(
        uid=0, displayIndex=0, comment="角色卡總表", key=["角色卡總表", "角色總表", "人物一覽"],
        keysecondary=[], selective=False, constant=False, order=1000,
        content=wrap("角色卡總表", roster_obj),
    )
    final = OrderedDict([("0", roster_entry)])
    final.update(entries)

    unused = [k for k in editor.edits if k not in editor.used]
    unused += [k for k in rel_editor.edits if k not in rel_editor.used]
    if unused:
        raise SystemExit(f"有 {len(unused)} 筆刪改規則沒有套用到，請檢查：{unused[:3]}")

    out = Path(out_dir)
    (out / "tools").mkdir(parents=True, exist_ok=True)
    with open(out / "blue_archive_character_cards_zhTW.json", "w", encoding="utf-8") as f:
        json.dump({"entries": final}, f, ensure_ascii=False, indent=4)
    with open(out / "tools" / "build_report.json", "w", encoding="utf-8") as f:
        json.dump(dict(roster=roster, cards=report), f, ensure_ascii=False, indent=1)
    with open(out / "角色卡總表.md", "w", encoding="utf-8") as f:
        f.write(render_markdown(groups, report, len(final), len(editor.edits), len(rel_editor.edits)))
    print(f"角色 {len(roster)} 位，條目 {len(final)} 筆（含總表）")


MD_HEADER = """# 角色卡總表

本資料夾的 `blue_archive_character_cards_zhTW.json` 是由《蔚藍檔案・奇普托斯》世界書整理出的**角色卡世界書**。
角色卡只放「角色本人的資訊」與**基本人物關係**，**不放劇情**；劇情、經歷與詳細的互動關係仍留在原本的世界書。

## 角色卡收錄原則

| 類別 | 角色卡處理方式 | 說明 |
| --- | --- | --- |
| 身分（identity） | 保留 | 學園、年級、所屬、職位、年齡、生日，以及停學、退學、七囚人、前任職位等**現在的身分狀態**。移除 `timeline_scope` 等劇情時間線欄位。 |
| 外觀、衣裝 | 保留 | 外觀與各套衣裝的細節、換裝連貫規則。條目說明改為不指定劇情時期的通用說明。 |
| 性格、思考、動機、言行、說話方式、日常 | 保留，逐句過濾 | 由過去經驗形成、但以**特質**寫成的內容保留（例如「容易把責任攬到自己身上」）；描述**特定事件經過、結果或真相**的句子刪除，或改寫成不含劇情的特質。 |
| 能力、專長與行動 | 保留，逐句過濾 | 保留能力與限制；刪除「曾在某次作戰中……」這類戰績與事件敘述。 |
| 演出守則（portrayal_guardrails） | 保留，逐句過濾 | 刪除指定劇情時期、劇情快照的守則。 |
| 經歷（history）、「經歷與關係」條目 | **整段排除** | 屬於劇情。 |
| 基本人物關係（basic_relationships） | 保留，精簡 | 只留「對象」與一句「基本關係」（例如陽奈→亞子：行政與指揮上的重要輔佐）。原本的互動方式、看法、衝突等細節不收；關係句中帶劇情的部分改寫或刪除。 |
| 針對特定人物的互動欄位 | **整段排除** | 例如 `behavior.with_aru`、`behavior.partner`；這類互動細節由上面的基本關係取代。對「老師」「陌生人」「朋友」等一般對象的互動方式保留。 |
| 情報（knowledge） | **整段排除** | 知道、不知道、隱瞞的劇情情報。 |

逐句刪改共 {edits} 筆，記錄在 `tools/plot_sentence_edits.json`；基本關係的改寫或刪除共 {rel_edits} 筆，記錄在 `tools/basic_relationship_edits.json`。兩者的 `replacement` 為空字串都代表刪除。沒有列在關係紀錄中的關係，取原文第一句。

## 世界書結構

- 共 {entries} 筆條目：第 0 筆為「角色卡總表」，其後每位角色依序為 `名稱・角色卡`、`名稱・角色卡・外觀與衣裝`、`名稱・角色卡・專長與行動`（後兩者僅在原世界書有對應條目時產生）。
- 觸發關鍵字、次要關鍵字、順序、深度等設定沿用原世界書對應條目。
- 「角色卡總表」條目預設不常駐（`constant: false`），以「角色卡總表／角色總表／人物一覽」觸發；若希望模型隨時知道所有角色的所屬，可在 SillyTavern 改為常駐（約 4,000 字）。
- 角色卡與原世界書的「人物」條目使用相同關鍵字。兩本同時啟用時會同時觸發，建議擇一使用，或只把原世界書當作劇情來源。

## 重新產生

```bash
python3 tools/build_cards.py ../blue_archive_kivotos_worldbook_zhTW.json .
```

新增或調整刪改規則時編輯 `tools/plot_sentence_edits.json` 或 `tools/basic_relationship_edits.json`；若有規則沒有套用到任何內容，或關係原文已和紀錄不同，產生器會報錯停止。

## 角色總表

「關係」為角色卡收錄的基本人物關係數；「刪／改」為該角色在角色卡中被刪除、改寫的劇情句數（不含關係）。「—」表示原資料未定或不明。
"""


def render_markdown(groups, report, n_entries, n_edits, n_rel_edits):
    rep = {r["name"]: r for r in report}
    out = [MD_HEADER.format(entries=n_entries, edits=n_edits, rel_edits=n_rel_edits)]
    total = 0
    for g, rows in groups.items():
        if not rows:
            continue
        out.append(f"\n### {g}（{len(rows)}）\n")
        out.append("| 名稱 | 年級 | 所屬 | 職位 | 備註 | 角色卡條目 | 關係 | 刪／改 |")
        out.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in rows:
            p = rep[r["name"]]
            made = "、".join({"人物": "本體", "外觀與衣裝": "外觀", "專長與行動": "專長"}[m] for m in p["made"])
            out.append("| " + " | ".join([
                r["name"], r["year"] or "—", r["org"] or "—", r["position"] or "—", r["note"] or "",
                made, str(p["relationships"]), f"{p['deleted']}／{p['rewritten']}",
            ]) + " |")
            total += 1
    out.append(f"\n共 {total} 位角色。\n")
    return "\n".join(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
