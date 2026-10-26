"""把世界書（酒館的 world info JSON）內嵌進角色卡（chara_card_v3 JSON）的 data.character_book。

用法：
    python3 內嵌世界書.py 角色卡.json 世界書.json 世界書名稱 輸出.json

條目欄位照酒館匯出角色卡時的寫法（convertWorldInfoToCharacterBook）：
酒館與 RP Engine 匯入時都從 entry.extensions 讀回位置、深度、黏著、掃描深度等設定；
RP Engine 的 rp_brief、rp_conditions 也放在 extensions 裡，匯入時會帶回去。
"""
import json
import sys
from pathlib import Path


def to_book_entry(e):
    ext = dict(e.get("extensions") or {})
    ext.update({
        "position": e["position"],
        "exclude_recursion": e["excludeRecursion"],
        "prevent_recursion": e["preventRecursion"],
        "delay_until_recursion": e["delayUntilRecursion"],
        "display_index": e["displayIndex"],
        "probability": e["probability"],
        "useProbability": e["useProbability"],
        "depth": e["depth"],
        "selectiveLogic": e["selectiveLogic"],
        "outlet_name": e.get("outletName", ""),
        "group": e["group"],
        "group_override": e["groupOverride"],
        "group_weight": e["groupWeight"],
        "scan_depth": e["scanDepth"],
        "case_sensitive": e["caseSensitive"],
        "match_whole_words": e["matchWholeWords"],
        "use_group_scoring": e["useGroupScoring"],
        "automation_id": e["automationId"],
        "role": e["role"] if e["role"] is not None else 0,
        "vectorized": e["vectorized"],
        "sticky": e["sticky"],
        "cooldown": e["cooldown"],
        "delay": e["delay"],
        "triggers": e.get("triggers", []),
        "ignore_budget": e.get("ignoreBudget", False),
    })
    return {
        "id": e["uid"],
        "keys": e["key"],
        "secondary_keys": e["keysecondary"],
        "comment": e["comment"],
        "content": e["content"],
        "constant": e["constant"],
        "selective": e["selective"],
        "insertion_order": e["order"],
        "enabled": not e["disable"],
        "position": "before_char" if e["position"] == 0 else "after_char",
        "use_regex": True,
        "extensions": ext,
    }


def main(card_path, book_path, book_name, out_path):
    card = json.loads(Path(card_path).read_text(encoding="utf-8"))
    book = json.loads(Path(book_path).read_text(encoding="utf-8"))
    entries = sorted(book["entries"].values(), key=lambda e: e["displayIndex"])
    card["data"]["character_book"] = {"name": book_name, "entries": [to_book_entry(e) for e in entries]}
    card["data"].setdefault("extensions", {})["world"] = book_name
    Path(out_path).write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(entries)} 條內嵌 → {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
