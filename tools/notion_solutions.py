"""Add the R and Python solutions of each week to site/content/notion/week-N.json
(keys "solution_r" and "solution_py": [code, ...]).

The Notion solutions pages hold one code block per language; R and Python blocks are kept (MATLAB is not).
Run after tools/notion_weeks.py.

Usage: python tools/notion_solutions.py
"""
import json
from pathlib import Path

import notion_export as ne
import notion_weeks as nw

DIR = Path(__file__).resolve().parent.parent / "site" / "content" / "notion"


def code_blocks(i, acc):
    for j in ne.flat(i):
        b = ne.blocks[j]
        if b["type"] == "code":
            lang = (b.get("properties", {}).get("language") or [[""]])[0][0].strip().lower()
            if lang in acc:
                acc[lang].append(ne.rich(b["properties"].get("title")))
        elif b["type"] != "page":
            for k in nw.kids(j):
                code_blocks(k, acc)
    return acc


if __name__ == "__main__":
    for f in sorted(DIR.glob("week-*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        code = {"r": [], "python": []}
        for s in d.get("solutions", []):
            ne.fetch([s["id"]])
            for k in ne.blocks[s["id"]].get("content", []):
                code_blocks(k, code)
        d["solution_r"], d["solution_py"] = code["r"], code["python"]
        f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f.stem, "R:", len(code["r"]), "Python:", len(code["python"]))
