"""世界觀總表 → 世界書（照 世界觀/世界觀總表_寫作說明.md §3、§4）。

用法：
    python3 世界觀總表轉世界書.py 世界觀總表.json 輸出.json [--no-truth]

產出（同一本書）：
    總覽｜［世界名］           常駐：overview.basic＋absent
    總覽｜［世界名］世界的規則  常駐：overview.truths
    索引｜［世界名］           常駐：每個實體一行
    類型｜［名字］             每個實體一條公開條目（觸發）
    類型｜［名字］真相         有 secret 的實體各一條（觸發條件同公開條目）；--no-truth 時不產生
關鍵字：keys.primary 單獨成立；keys.secondary（通稱）要和 keys.context 一起出現（context 看最近 N 則）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from 總表轉世界書 import Book, grp, sentence  # noqa: E402

TYPE = {"place": "地點", "faction": "勢力", "system": "制度", "concept": "前提", "culture": "文化",
        "species": "種族", "event": "事件", "item": "物品"}
ORDER = {"concept": 700, "system": 700, "place": 600, "faction": 600, "species": 500, "event": 500, "item": 500, "culture": 500}


def line(label, items, sep="；"):
    items = [x for x in (items or []) if x]
    return f"{label}：{sep.join(x.rstrip('。') for x in items)}。" if items else ""


def body(e):
    t = e["type"]
    out = list(e.get("common", [])[:1])
    rest = e.get("common", [])[1:]
    if t == "place":
        out += [line("樣子", e.get("features")), line("出入", e.get("access")), line("能做的事", e.get("can_do")),
                line("規矩", e.get("rules"))]
        r = e.get("rulers", {})
        if r.get("apparent"):
            out.append(f"誰管事：{r['apparent']}" + (f"（實際上：{r['real']}）" if r.get("real") and r["real"] != r["apparent"] else "") + "。")
        out += [line("常見的人", e.get("people")), line("危險", e.get("dangers"))]
    elif t == "faction":
        if e.get("impulse"):
            out.append(f"想要：{sentence(e['impulse'])}")
        if e.get("tier"):
            out.append(f"規模：{e['tier']}；穩固度：{e.get('hold', '')}。")
        out += [line("地盤", [e.get("turf")]), line("資產", e.get("assets"))]
        if e.get("leaders"):
            out.append("領袖：" + "；".join(f"{l['name']}（{l['role']}，{l['trait']}）" for l in e["leaders"]) + "。")
        out += [line("盟友", e.get("allies")), line("敵人", e.get("enemies"))]
        if e.get("public_face"):
            out.append(f"外人看到的：{sentence(e['public_face'])}")
        out.append(line("成員才知道", e.get("inside"), "\n・") if not e.get("inside") else "成員才知道：\n・" + "\n・".join(e["inside"]))
        if e.get("membership"):
            out.append(f"加入：{sentence(e['membership'])}")
    elif t == "system":
        out += [line("能做", e.get("can")), line("做不到", e.get("limits")), line("會被什麼反制", e.get("weaknesses")),
                line("代價", e.get("costs"))]
        if e.get("access"):
            out.append(f"誰用得到：{sentence(e['access'])}")
        out.append(line("對世界的影響", e.get("consequences")))
        if e.get("perceived"):
            out.append(f"一般人看到的：{sentence(e['perceived'])}")
    elif t == "concept":
        out += [line("日常怎麼顯現", e.get("daily"))]
    elif t == "species":
        if e.get("habitat"):
            out.append(f"棲息：{sentence(e['habitat'])}")
        out += [line("能力", e.get("abilities")), line("限制", e.get("limits"))]
        if e.get("rarity"):
            out.append(f"稀有度：{sentence(e['rarity'])}")
        out.append(line("和其他存在的關係", e.get("relations")))
    elif t == "event":
        if e.get("when"):
            out.append(f"時間：{sentence(e['when'])}")
        if e.get("cause"):
            out.append(f"起因：{sentence(e['cause'])}")
        out += [line("現在", e.get("consequences_now")), line("物證", e.get("evidence"))]
        if e.get("accounts"):
            out.append("各方的說法：" + "；".join(f"{a['who']}：{a['believes'].rstrip('。')}" for a in e["accounts"]) + "。")
    out += rest
    out.append(line("當地的說法", e.get("lexicon")))
    loc = e.get("local")
    if loc and loc.get("facts"):
        out.append(f"{loc['known_by']}才知道：" + "".join(sentence(f) for f in loc["facts"]))
    if e.get("absent"):
        out.append("；".join(a.rstrip("。") for a in e["absent"]) + "。")
    return "\n".join(x for x in out if x)


def cond(e):
    k = e.get("keys", {})
    plans = []
    if k.get("primary"):
        plans.append({"all": [grp(k["primary"])]})
    if k.get("secondary") and k.get("context"):
        n = 4 if e["type"] == "place" else 2
        plans.append({"all": [grp(k["secondary"], "latest"), grp(k["context"], n)]})
    return {"any": plans}


def main(src, out, *flags):
    w = json.loads(Path(src).read_text(encoding="utf-8"))
    name = w["meta"]["world"]
    ov = w["overview"]
    book = Book()
    basic = ov["basic"] + ("\n" + line("這個世界沒有", ov.get("absent")) if ov.get("absent") else "")
    book.add(f"總覽｜［{name}］", basic, keys=[name], constant=True, position=0, order=900)
    book.add(f"總覽｜［{name}］世界的規則", "\n".join(ov["truths"]), keys=[name], constant=True, position=0, order=890)
    idx = "這個世界有：\n" + "\n".join(f"・{e['brief']}" for e in w["entities"])
    book.add(f"索引｜［{name}］", idx, keys=[name], constant=True, position=0, order=880)
    for e in w["entities"]:
        label = TYPE[e["type"]]
        c = cond(e)
        book.add(f"{label}｜［{e['name']}］", body(e), cond=c, brief=e["brief"], position=0, order=ORDER[e["type"]])
        sec = e.get("secret")
        if sec and sec.get("facts") and "--no-truth" not in flags:
            txt = f"{e['name']}的真相（旁白知道，角色不一定知道）：\n" + "\n".join(sec["facts"])
            if sec.get("known_by"):
                txt += f"\n誰知道：{sentence(sec['known_by'])}"
            if sec.get("clues"):
                txt += f"\n線索：" + "；".join(sec["clues"]) + "。"
            book.add(f"{label}｜［{e['name']}］真相", txt, cond=c, position=0, order=ORDER[e["type"]] - 1)
    data = book.dump()
    Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(book.entries)} 條 → {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
