"""角色總表 → 世界書（RP Engine 的「B 世界書版」，寫手自己演、多人共用一本）。

用法：
    python3 總表轉世界書.py 設定檔.json 輸出.json

設定檔：
    {
      "book": "世界書名稱",
      "characters": [
        { "sheet": "角色卡/角色總表_羽前京香.json",       # 角色總表（可省略：只用調整檔）
          "patch": "世界書/魔都精兵/第85話調整/羽前京香.json" }  # 時間點調整（可省略）
      ],
      "passersby": [ { "name": "路人全名", "keys": ["名字"], "content": "名片" } ]   # 路人：只有一條名片
    }

調整檔和總表做深度合併：物件逐欄合併，清單整個換掉，值為 null 的欄位刪掉。
調整檔另有 "lore" 區塊（只給導出用）：
    keys        這個人在場的判斷詞（全名、常用稱呼）；不要放「組長」這類通稱
    pronouns    在場判斷另外接受的代名詞，預設 ["妳", "她"]
    card        名片（一兩句）；沒寫就用 identity.summary
    card_constant  名片要不要常駐，預設 true（敵方、少出場的人設 false，提到名字才送）
    impression  旁人看得到的樣子（公開印象條目）；沒寫就不出這條
    guard       守則（角色備註，深度 2）的幾句；沒寫就取 rules 前 5 條
    targets     關係對象的判斷詞：{ "對象全名": ["稱呼", ...] }，沒寫就用 relationships[].aliases
    skip        不要導出的條目種類，例如 ["外觀"]

條目名稱照 docs/19 4.10：［全名・類型］、［全名×對象］；私密的名稱有「私密」。
觸發照 docs/19 4.5.1 第四版：進階條件（extensions.rp_conditions），
同時把條件編成一個正則主要關鍵字，酒館也讀得懂。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 正則：照 RP Engine core/lore/conditions-export 的寫法 ──────────────
_SPECIAL = set(r".*+?^${}()|[]\/")


def _term(word):
    """一般詞 → 正則片段（不分大小寫：英文字母展開成 [aA]，k 加上克耳文符號）。"""
    if len(word) > 2 and word.startswith("/") and word.rfind("/") > 0:
        body = word[1:word.rfind("/")]
        return body
    out = []
    for ch in word:
        if ch in _SPECIAL:
            out.append("\\" + ch)
        elif "a" <= ch.lower() <= "z" and ch.isascii():
            lo, up = ch.lower(), ch.upper()
            out.append(f"[{lo}{up}K]" if lo == "k" else f"[{lo}{up}]")
        else:
            out.append(ch)
    return "".join(out)


def _group(g):
    alts = "|".join(f"(?:{_term(k)})" for k in g["keys"])
    if g["mode"] == "none":
        return f"(?![\\s\\S]*?(?:{alts}))"
    if g["mode"] == "all":
        return "".join(f"(?=[\\s\\S]*?(?:{_term(k)}))" for k in g["keys"])
    return f"(?=[\\s\\S]*?(?:{alts}))"


def compile_conditions(cond):
    plans = ["".join(_group(g) for g in plan["all"]) for plan in cond["any"]]
    return "/^(?:" + "|".join(plans) + ")/"


def grp(keys, scope=None, mode="any"):
    g = {"mode": mode, "keys": list(dict.fromkeys(k for k in keys if k))}
    if scope == "latest":
        g["scope"] = {"kind": "latest"}
    elif isinstance(scope, int):
        g["scope"] = {"kind": "recent", "n": scope}
    return g


# ── 條目 ─────────────────────────────────────────────────────────────
BASE = {
    "constant": False, "vectorized": False, "selective": False, "selectiveLogic": 0,
    "addMemo": True, "order": 400, "position": 1, "disable": False, "ignoreBudget": False,
    "excludeRecursion": True, "preventRecursion": True, "delayUntilRecursion": 0,
    "probability": 100, "useProbability": True, "depth": 4, "outletName": "", "group": "",
    "groupOverride": False, "groupWeight": 100, "scanDepth": None, "caseSensitive": False,
    "matchWholeWords": False, "useGroupScoring": None, "automationId": "", "role": None,
    "sticky": None, "cooldown": None, "delay": None, "triggers": [],
    "characterFilter": {"isExclude": False, "names": [], "tags": []},
}


class Book:
    def __init__(self):
        self.entries = []

    def add(self, comment, content, *, keys=None, cond=None, brief=None, constant=False,
            sticky=None, position=1, depth=4, role=None, scan_depth=None, order=400):
        e = dict(BASE)
        e.update(comment=comment, content=content.strip(), constant=constant, sticky=sticky,
                 position=position, depth=depth, role=role, scanDepth=scan_depth, order=order)
        ext = {}
        if brief:
            ext["rp_brief"] = brief.strip()
        if cond:
            e["key"] = [compile_conditions(cond)]
            e["selective"] = True
            ext["rp_conditions"] = {"v": 1, **cond}
        else:
            e["key"] = list(dict.fromkeys(keys or []))
        e["keysecondary"] = []
        e["extensions"] = ext
        self.entries.append(e)
        return e

    def dump(self):
        out = {}
        for i, e in enumerate(self.entries):
            e = {"uid": i, **e, "displayIndex": i}
            out[str(i)] = e
        return {"entries": out}


# ── 合併 ─────────────────────────────────────────────────────────────
def merge(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            if v is None:
                out.pop(k, None)
            elif k in out:
                out[k] = merge(out[k], v)
            else:
                out[k] = v
        return out
    return b


def j(items, sep="；"):
    return sep.join(x.rstrip("。") if sep == "；" else x for x in items if x)


def sentence(s):
    s = (s or "").strip()
    return s if not s or s[-1] in "。！？」）』…" else s + "。"


# ── 導出一個角色 ───────────────────────────────────────────────────────
TITLE = {}


def tn(name):
    """條目名稱用的名字：名字裡有「・」時換成設定的短名，免得引擎把「・」當成類型的分隔。"""
    return TITLE.get(name, name.replace("・", ""))


def export_character(book, d):
    lore = d.get("lore", {})
    skip = set(lore.get("skip", []))
    ident = d["identity"]
    name = ident["name"]
    keys = lore.get("keys") or [name]
    pron = lore.get("pronouns", ["妳", "她"])
    present = grp(keys, 2)
    present_or_pron = grp(keys + pron, 2)
    card = lore.get("card") or f"{name}：{ident['summary']}"

    # 名片（常駐）
    book.add(f"［{tn(name)}・名片］", card, keys=keys, constant=lore.get("card_constant", True))

    # 核心
    p, t, v, m = d.get("personality", {}), d.get("thinking", {}), d.get("voice", {}), d.get("motivations", {})
    beh = d.get("behavior", {})
    aliases = [a for a in ident.get("aliases", []) if not re.search(r"[ぁ-んァ-ヶ]|^[A-Za-z ]+$", a)]
    lines = [f"名字：{name}。" + (f"別名、稱呼：{'、'.join(aliases)}。" if aliases else "")]
    pos = j([ident.get("role"), ident.get("position")])
    lines.append(f"定位：{sentence(pos)}")
    if ident.get("age"):
        lines.append(f"年齡：{sentence(ident['age'])}")
    lines.append(f"現況：{sentence(ident['summary'])}")
    if d.get("appearance", {}).get("summary"):
        lines.append(f"外觀：{sentence(d['appearance']['summary'])}")
    if p.get("core"):
        lines.append(f"本質：{sentence(p['core'])}")
    if p.get("surface"):
        lines.append(f"表面：{sentence(p['surface'])}")
    if p.get("inner"):
        lines.append(f"底層：{sentence(p['inner'])}")
    if p.get("contrasts"):
        lines.append(f"反差：{'；'.join(p['contrasts'][:3])}。")
    th = j([sentence(t.get("style")), sentence(t.get("decision")),
            ("拿不準時：" + sentence(t["when_unsure"])) if t.get("when_unsure") else ""], "")
    if th:
        lines.append(f"思考：{th}")
    vo = [sentence(v.get("summary")), sentence(v.get("style"))]
    if v.get("self_reference"):
        vo.append(f"自稱：{'、'.join(v['self_reference'])}。")
    if v.get("address_default"):
        vo.append(sentence(v["address_default"]))
    if v.get("rhythm"):
        vo.append(sentence(v["rhythm"]))
    if v.get("serious_mode"):
        vo.append("認真時：" + sentence(v["serious_mode"]))
    if v.get("catchphrases"):
        vo.append("口頭禪：" + "".join(v["catchphrases"][:4]))
    lines.append("聲線：" + "".join(vo))
    if p.get("emotional_style"):
        lines.append(f"情緒：{sentence(p['emotional_style'])}")
    dist = j([("面對陌生人：" + beh["with_strangers"]) if beh.get("with_strangers") else "",
              ("和朋友：" + beh["with_friends"]) if beh.get("with_friends") else "",
              ("對親近的人：" + beh["with_close"]) if beh.get("with_close") else ""])
    if dist:
        lines.append(f"距離：{sentence(dist)}")
    bl = m.get("bottom_lines", [])
    if bl:
        lines.append(f"底線（{pron[1]}的選擇，和理由）：" + "".join(f"{sentence(b['line'])[:-1]}——{sentence(b['because'])}" for b in bl))
    if p.get("big_five"):
        lines.append(f"五大人格（粗略）：{sentence(p['big_five'])}")
    book.add(f"［{tn(name)}・核心］", "\n".join(lines), keys=keys, sticky=4, brief=card)

    # 公開印象
    if lore.get("impression"):
        book.add(f"［{tn(name)}・公開印象］", lore["impression"], keys=keys, sticky=4)

    # 範例台詞
    exs = v.get("examples", [])[:5]
    if exs:
        txt = f"{name}說話的樣子（範例）：\n" + "\n".join(
            f"對方：{e['other']}\n{name}：{e['self']}" for e in exs)
        book.add(f"［{tn(name)}・範例台詞］", txt, keys=keys, sticky=4)

    # 守則（深度 2）
    guard = lore.get("guard") or [r["rule"] for r in d.get("rules", [])[:5]]
    cutoff = d.get("knowledge", {}).get("cutoff")
    if guard:
        gtxt = f"【{name}】" + "".join(sentence(g) for g in guard)
        if cutoff:
            gtxt += f"{pron[1]}的視野到{cutoff.rstrip('。')}為止。"
        book.add(f"［{tn(name)}・守則］", gtxt, keys=keys, sticky=4, position=4, depth=2, role=0)

    # 關係
    targets = lore.get("targets", {})
    private_bits = []
    for r in d.get("relationships", []):
        tname = r["name"]
        tkeys = targets.get(tname) or [tname] + [a for a in r.get("aliases", []) if a != tname]
        body = [f"{name}看{tname}：{sentence(r.get('view'))}",
                f"關係：{sentence(r.get('relation'))}"]
        if r.get("tone"):
            body.append(f"態度：{sentence(r['tone'])}")
        if r.get("typical"):
            body.append(f"相處：{sentence(r['typical'])}")
        if r.get("in_presence"):
            body.append(f"對方在場時：{sentence(r['in_presence'])}")
        if r.get("trust"):
            body.append(f"信任：{r['trust'].get('value')}／10，{sentence(r['trust'].get('note'))}")
        if r.get("conflicts"):
            body.append(f"摩擦：{sentence(r['conflicts'])}")
        if r.get("address"):
            body.append(f"稱呼：{sentence(r['address'])}")
        if r.get("unspoken"):
            if r.get("visibility") == "public":
                body.append(f"沒說出口的：{sentence(r['unspoken'])}")
            else:
                private_bits.append(f"對{tname}沒說出口的：{sentence(r['unspoken'])}")
        brief = f"{tname}：{r.get('relation', '')}".strip()
        cond = {"any": [{"all": [grp(tkeys, "latest"), present]}]}
        if r.get("trigger_recent"):
            cond = {"any": [{"all": [grp(tkeys, 2), present]}]}
        book.add(f"［{tn(name)}×{tn(tname)}］", "\n".join(body), cond=cond, brief=brief[:120])

    # 情境
    for pt in d.get("patterns", []):
        title = pt.get("title") or pt["situation"]
        txt = f"{pt['situation']}：{sentence(pt['response'])}"
        if pt.get("reading"):
            txt += f"（{pron[1]}心裡的第一個念頭：{sentence(pt['reading'])[:-1]}）"
        if pt.get("exception") and pt["exception"] not in ("沒有例外。", "沒有例外"):
            txt += f"\n例外：{sentence(pt['exception'])}"
        cond = {"any": [{"all": [grp(pt["keywords"], "latest"), present_or_pron]}]}
        book.add(f"［{tn(name)}・{title}］", txt, cond=cond, brief=sentence(pt["response"])[:100], scan_depth=1)

    # 經歷
    hist = d.get("history", [])
    pub = [h for h in hist if h.get("known_by", "public") != "private"]
    priv = [h for h in hist if h.get("known_by") == "private"]
    if pub and "經歷" not in skip:
        txt = "\n".join(f"・{h['when']}：{sentence(h['event'])}" + (f"影響：{sentence(h['impact'])}" if h.get("impact") else "")
                        + (f"（知道的人：{h['known_by']}）" if h.get("known_by") not in (None, "public") else "") for h in pub)
        cond = {"any": [{"all": [grp(["以前", "過去", "經歷", "當年", "那時候", "發生過", "怎麼會", "為什麼會", "後來", "之前"], "latest"), present_or_pron]}]}
        book.add(f"［{tn(name)}・經歷］", txt, cond=cond, brief=f"{name}的經歷：" + "、".join(h["when"] for h in pub), scan_depth=1)
    for h in priv:
        private_bits.append(f"{h['when']}：{sentence(h['event'])}")

    # 能力
    ab = d.get("abilities")
    if ab and "能力" not in skip:
        body = [sentence(ab.get("summary"))]
        for s in ab.get("skills", []):
            body.append(f"・{s['name']}：{sentence(s['detail'])}")
        if ab.get("strengths"):
            body.append("長處：" + "、".join(ab["strengths"]) + "。")
        if ab.get("weaknesses"):
            body.append("弱點：" + "、".join(ab["weaknesses"]) + "。")
        cb = ab.get("combat", {})
        if cb:
            body.append("戰鬥：" + j([cb.get("role"), cb.get("style"), cb.get("weapon") and "武器：" + cb["weapon"]]) + "。")
        if ab.get("limits"):
            body.append("限制：" + "".join(sentence(x) for x in ab["limits"]))
        cond = {"any": [{"all": [grp(["能力", "招式", "戰鬥", "力量", "桃", "必殺", "形態", "打得過", "多強", "變身", "迎戰", "醜鬼"], "latest"), present_or_pron]}]}
        book.add(f"［{tn(name)}・能力與戰鬥］", "\n".join(b for b in body if b), cond=cond, brief=sentence(ab.get("summary"))[:100], scan_depth=1)

    # 外觀
    ap = d.get("appearance")
    if ap and "外觀" not in skip:
        body = [sentence(ap.get("summary"))]
        size = []
        if ap.get("height_cm"):
            size.append(f"身高 {ap['height_cm']} 公分")
        mc = ap.get("measurements_cm")
        if mc and all(mc.get(k) for k in ("bust", "waist", "hips")):
            basis = ap.get("measurements_basis", "胸圍以外為依立繪推測")
            size.append(f"三圍 B{mc['bust']}／W{mc['waist']}／H{mc['hips']}（{basis}）")
        elif mc:
            size.append(f"三圍{mc.get('status', '官方未公開')}")
        if size:
            body.append("、".join(size) + "。")
        for k, label in (("body", "體型"), ("hair", "頭髮"), ("eyes", "眼睛"), ("expression", "表情"), ("posture", "姿態")):
            if ap.get(k):
                body.append(f"{label}：{sentence(ap[k])}")
        if ap.get("distinctive_features"):
            body.append("特徵：" + "；".join(ap["distinctive_features"]) + "。")
        for k, o in (ap.get("outfits") or {}).items():
            body.append(f"服裝（{'平常' if k == 'default' else k}）：{sentence(o)}")
        cond = {"any": [{"all": [grp(["外表", "外觀", "長相", "頭髮", "髮型", "眼睛", "身材", "衣服", "穿著", "打扮", "制服", "軍服", "身高", "樣子"], "latest"), present_or_pron]}]}
        book.add(f"［{tn(name)}・外觀］", "\n".join(body), cond=cond, brief=sentence(ap.get("summary")), scan_depth=1)

    # 喜好與習慣
    dl = d.get("daily_life", {})
    if (dl or beh) and "喜好" not in skip:
        body = []
        for k, label in (("likes", "喜歡"), ("dislikes", "討厭"), ("interests", "興趣"), ("habits", "習慣"), ("skills", "擅長"), ("treasures", "重要的東西")):
            if dl.get(k):
                body.append(f"{label}：{'、'.join(dl[k])}。")
        if dl.get("lifestyle"):
            body.append(f"生活：{sentence(dl['lifestyle'])}")
        if beh.get("daily"):
            body.append(f"平常的一天：{sentence(beh['daily'])}")
        if body:
            cond = {"any": [{"all": [grp(["喜歡", "討厭", "興趣", "習慣", "平常", "假日", "愛吃", "最愛", "嗜好", "休假", "空閒"], "latest"), present_or_pron]}]}
            book.add(f"［{tn(name)}・喜好與習慣］", "\n".join(body), cond=cond, brief=(body[0])[:100], scan_depth=1)

    # 視野
    kn = d.get("knowledge", {})
    if kn:
        body = []
        if kn.get("knows"):
            body.append(f"{pron[1]}親身知道的：" + "、".join(kn["knows"]) + "。")
        if kn.get("unknown"):
            body.append(f"{pron[1]}不知道的：" + "、".join(kn["unknown"]) + "——遇到時用自己的推測或直接說不知道。")
        if kn.get("misreads"):
            body.append(f"{pron[1]}可能誤會的：" + "".join(sentence(x) for x in kn["misreads"]))
        if kn.get("when_unsure"):
            body.append("拿不準時：" + sentence(kn["when_unsure"]))
        if cutoff:
            body.append(f"時間點：{sentence(cutoff)}")
        book.add(f"［{tn(name)}・視野］", "\n".join(body), keys=keys, sticky=4, brief=(body[0] if body else "")[:100])

    # 私密
    secret = []
    for h in kn.get("hides", []):
        secret.append(f"{pron[1]}知道但不說：{sentence(h['what'])}" + (f"（會說的時候：{sentence(h['tells_if'])[:-1]}）" if h.get("tells_if") else ""))
    for s in kn.get("suspects", []):
        secret.append(f"{pron[1]}懷疑：{sentence(s)}")
    for s in kn.get("secrets", []):
        secret.append(f"秘密：{sentence(s if isinstance(s, str) else s.get('what', ''))}")
    for c in p.get("insecurities", []):
        secret.append(f"{pron[1]}害怕的：{sentence(c)}")
    secret += private_bits
    if secret:
        book.add(f"［{tn(name)}・私密］", "\n".join(secret), keys=keys, sticky=4, brief=secret[0][:100])


def main(cfg_path, out_path):
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    TITLE.update(cfg.get("title_names", {}))
    book = Book()
    for extra in cfg.get("head", []):
        book.add(**extra)
    for c in cfg.get("characters", []):
        pass
    tail = cfg.get("passersby", [])
    for c in cfg["characters"]:
        d = {}
        if c.get("sheet"):
            d = json.loads((ROOT / c["sheet"]).read_text(encoding="utf-8"))
        if c.get("patch"):
            d = merge(d, json.loads((ROOT / c["patch"]).read_text(encoding="utf-8")))
        export_character(book, d)
    for p in tail:
        book.add(f"［{tn(p["name"])}・名片］", p["content"], keys=p["keys"])
    data = book.dump()
    Path(out_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(book.entries)} 條 → {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
