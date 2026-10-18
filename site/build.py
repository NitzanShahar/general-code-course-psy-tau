"""Build the course site (GitHub Pages, served from the repo root).

Sources (edit these): site/site.json, site/site.css, site/img/, site/content/weeks/week-N.json,
  site/content/book.json (units imported from Notion) and site/content/book_extra_*.json (units written for this course).
  The book has three inner books — R, Python and code management ("code"); site.json "book_layout" lists their chapters in order.
Output (do not edit by hand):
  index.html                  public site: a general announcement while "published" is empty, otherwise the published weeks
  <staff_dir>/index.html …    staff ("מתרגלים") site: every week that has content + the book of units + the admin page
                              (admin.html, from site/content/admin.json; on the public site too once weeks are published)
  assets/                     css and images, shared by both

Usage: python site/build.py
"""
import hashlib
import html
import json
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlencode, urlsplit

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "site"
CFG = json.loads((SRC / "site.json").read_text(encoding="utf-8"))
FONTS = ("https://fonts.googleapis.com/css2?family=Assistant:wght@400;500;600;700"
         "&family=Frank+Ruhl+Libre:wght@500;700;900&family=JetBrains+Mono:wght@400;600&display=swap")

ICON = {
    "deck": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>',
    "play": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9.5v5l4.5-2.5z" fill="currentColor"/></svg>',
    "book": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/></svg>',
    "chat": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4z"/></svg>',
    "link": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>',
    "copy": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>',
    "clock": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    "spark": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/></svg>',
}

esc = html.escape


# ---------- content ----------

def fix(s, book=None):
    for rule in CFG.get("book_replace", []):
        a, b = rule[0], rule[1]
        if len(rule) < 3 or rule[2] == book:
            s = s.replace(a, b)
    return s


BOOKS = [("r", "R", "ספר R"), ("py", "Python", "ספר פייתון"), ("code", "ניהול קוד", "ספר ניהול קוד")]
BOOK_NAME = {k: name for k, _, name in BOOKS}
BOOK_TAG = {k: tag for k, tag, _ in BOOKS}


def load_book():
    """All chapters, by inner book: {"r": [chapter, ...], "py": [...], "code": [...]}; chapter n counts within its book."""
    content = SRC / "content"
    pool = {c["id"]: c for c in json.loads((content / "book.json").read_text(encoding="utf-8"))}
    for f in sorted(content.glob("book_extra_*.json")):
        for c in json.loads(f.read_text(encoding="utf-8")):
            pool[c["key"]] = c
    drop = set(CFG.get("book_drop_sections", []))
    names = CFG.get("book_chapter_titles", {})
    book = {}
    for b, _, _ in BOOKS:
        book[b] = []
        for n, ref in enumerate(CFG["book_layout"][b], 1):
            if ref not in pool:
                print(f"  ! book {b}: chapter {ref} not found")
                c = {"title": "(פרק בהכנה)", "secs": []}
            else:
                c = pool[ref]
            secs = [s for s in c["secs"] if s["h"] and s["h"] not in drop]
            book[b].append({"n": n, "idx": n, "book": b, "title": names.get(c["title"], c["title"]), "secs": secs})
    return book


def prune_book(book, weeks):
    """Keep only the units that some week uses (and chapters that still have units); renumber what is left.
    Week files refer to chapters by their place in book_layout ("idx"); "n" is the number shown on the site."""
    used = {(u["book"], u["ch"], s) for c in weeks.values() for u in c.get("units", []) for s in u["secs"]}
    out = {}
    for b, chs in book.items():
        out[b] = []
        for ch in chs:
            secs = [s for s in ch["secs"] if (b, ch["idx"], s["h"]) in used]
            if secs:
                out[b].append(dict(ch, n=len(out[b]) + 1, secs=secs))
    return out


def chapter(book, b, idx):
    return next((c for c in book[b] if c["idx"] == idx), None)


def load_files():
    f = SRC / "content" / "files.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


FILES = load_files()
DEPTH = [0]  # depth of the page being built (for links to files/)


def short_date(d):
    """'18.10.2026' -> '18.10'"""
    return ".".join(d.split(".")[:2]) if d else ""


def load_weeks():
    out = {}
    for w in CFG["weeks"]:
        f = SRC / "content" / "weeks" / f"week-{w['n']}.json"
        if f.exists():
            out[w["n"]] = json.loads(f.read_text(encoding="utf-8"))
    return out


# ---------- text helpers ----------

LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)|(https?://(?:[^\s<>()\]]|\([^\s<>()]*\))+(?:[^\s<>()\].,;:!?'\"]|\([^\s<>()]*\)))")  # bare URLs may hold (…), as Wikipedia's do


LATIN_RUN = re.compile(r"(?<![&#A-Za-z0-9_])[A-Za-z0-9](?:[A-Za-z0-9_+#/-]|[.:](?=[A-Za-z0-9]))*(?: [A-Za-z0-9](?:[A-Za-z0-9_+#/-]|[.:](?=[A-Za-z0-9]))*)*")  # 12:00 and file.py are one run; a final "." is not


def hx(s):
    """A heading in Hebrew with English terms: each English run is isolated (<bdi>), so the punctuation between runs
    follows the Hebrew order ("ו-interpreters: R" stays in place instead of jumping)."""
    return LATIN_RUN.sub(lambda m: f"<bdi>{m.group(0)}</bdi>", esc(s))


def url_label(url):
    """A readable name for a bare URL: "ויקיפדיה: Bash" for Wikipedia, otherwise the site and the decoded path."""
    p = urlsplit(url)
    host, path = p.netloc.removeprefix("www."), unquote(p.path).rstrip("/")
    m = re.match(r"([a-z]+)\.wikipedia\.org$", host)
    if m and path.startswith("/wiki/"):
        return ("ויקיפדיה: " if m.group(1) == "he" else "Wikipedia: ") + path[6:].replace("_", " ")
    label = host + re.sub(r"\.html?$", "", path)
    return label if len(label) <= 70 else label[:67] + "…"


def inline(s):
    """Escape text and turn markdown links, bare URLs, `code` and **bold** into HTML."""
    out, pos = [], 0
    for m in LINK.finditer(s):
        out.append(_marks(esc(s[pos:m.start()])))
        if m.group(2):
            label, url = m.group(1).strip() or m.group(2), m.group(2)
        else:
            label = url = m.group(3)
        if label == url:
            label = url_label(url)
        cls = "" if re.search(r"[֐-׿]", label) else ' class="ltr"'
        out.append(f'<a href="{esc(url)}" target="_blank" rel="noopener"{cls}>{esc(label)}</a>')
        pos = m.end()
    out.append(_marks(esc(s[pos:])))
    return iso("".join(out))


def _marks(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return re.sub(r"`([^`\n]+)`", r'<code class="ltr">\1</code>', s)


ISO_SKIP = re.compile(r"(<code\b.*?</code>|<[^>]+>|&[#\w]+;)", re.S)


def iso(h):
    """In Hebrew text, isolate each English run (<bdi>) so the punctuation between runs keeps the Hebrew order.
    Text with no Hebrew letter is left as it is."""
    if not re.search(r"[֐-׿]", h):
        return h
    return "".join(p if ISO_SKIP.fullmatch(p or "x") else LATIN_RUN.sub(lambda m: f"<bdi>{m.group(0)}</bdi>", p)
                   for p in ISO_SKIP.split(h))


CODE_LINE = re.compile(r"^[\x20-\x7E—–“”]+$")


def lines_html(s, steps=False):
    """One block per line; ASCII lines that look like code (assignment, call, comment) read left-to-right in mono.
    steps: a prompt — space before each numbered step and before the closing instruction, so the steps read apart."""
    out = []
    lines = s.split("\n")
    last = max((i for i, l in enumerate(lines) if l.strip()), default=-1)
    for i, line in enumerate(lines):
        t = line.strip()
        if t and CODE_LINE.match(t) and re.search(r"[=(#<\[]|\w\.\w|^\w+$", t) and "http" not in t:
            out.append(f'<div class="cl">{esc(line)}</div>')
        else:
            st = ' class="st"' if steps and i and (re.match(r"\d+\.\s", t) or i == last) else ""
            out.append(f"<div{st}>{inline(line) if t else '&nbsp;'}</div>")
    return "".join(out)


def renumber(s):
    """Notion writes every numbered step as "1." (and some prompts skip or repeat numbers); number a prompt's steps 1, 2, 3, …"""
    out, k = [], 0
    for line in s.split("\n"):
        m = re.match(r"^(\d+)\.(\s|$)", line)
        if m:
            k += 1
            line = f"{k}." + line[m.end(1) + 1:]
        out.append(line)
    return "\n".join(out)


def plain(s):
    """Text for the clipboard: links as their label (and URL), no markdown marks."""
    s = re.sub(r"\[([^\]]*)\]\(([^)\s]+)\)", lambda m: m.group(1) if m.group(1).strip() in ("", m.group(2)) else f"{m.group(1)} ({m.group(2)})", s)
    return s.replace("**", "")


def link_lines(s):
    """Split a video/reference callout into list items."""
    items = []
    for line in s.split("\n"):
        line = line.strip().lstrip("-").strip()
        if not line:
            continue
        m = re.match(r"\[\[FILE (.*?)(?:\|([0-9a-f-]+))?\]\]$", line)
        if m:
            name, fid = m.group(1).strip(), m.group(2)
            path = FILES.get(fid or "", {}).get("path")
            label = FILES.get(fid or "", {}).get("label") or re.sub(r"\.(mp4|mov|pdf)$", "", name) or "סרטון"
            if path:
                items.append(f'<a href="{"../" * DEPTH[0]}{esc(path)}" target="_blank" rel="noopener">{esc(label)}</a>')
            elif name:
                items.append(f'<span class="pend">{esc(name)} — יועלה בהמשך</span>')
        else:
            items.append(inline(line))
    return items


def md_lines(lines):
    """Notion-style lines -> HTML: "1. " numbered, "- " bulleted, two spaces of indent per level, else a paragraph."""
    out, stack = [], []  # open lists: (indent, tag)

    def close():
        out.append(f"</li></{stack.pop()[1]}>")

    for raw in lines:
        for line in raw.split("\n"):
            if not line.strip():
                continue
            ind = (len(line) - len(line.lstrip(" "))) // 2
            t = line.strip()
            m = re.match(r"^(\d+\.|[-•])\s*(.*)$", t)
            if not m:
                if stack and ind > 0:  # an indented line inside a list item
                    out.append(f"<br>{inline(t)}")
                    continue
                while stack:
                    close()
                cls = ' class="hp"' if re.match(r"^(חלק|בונוס)", t) else ""
                out.append(f"<p{cls}>{inline(t)}</p>")
                continue
            tag = "ol" if m.group(1)[0].isdigit() else "ul"
            while stack and stack[-1][0] > ind:
                close()
            if stack and stack[-1][0] == ind:
                if stack[-1][1] == tag:
                    out.append(f"</li><li>{inline(m.group(2))}")
                    continue
                close()
            out.append(f"<{tag}><li>{inline(m.group(2))}")
            stack.append((ind, tag))
    while stack:
        close()
    return "".join(out)


def week_label(w):
    return f"שבוע {w['n']}"


# ---------- page shell ----------

def page(title, body, depth, staff, script=""):
    up = "../" * depth
    robots = '<meta name="robots" content="noindex,nofollow">' if staff else ""
    return f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{robots}<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}" rel="stylesheet">
<link rel="stylesheet" href="{up}assets/site.css?v={CSS_VER}">
<link rel="icon" href="{up}assets/tau-logo.png">
</head>
<body>
<div class="wrap">
{body}
</div>
<script>
{script}
</script>
</body>
</html>
"""


# a version stamp on the stylesheet link, so browsers load a changed site.css at once instead of a cached copy
CSS_VER = hashlib.md5((SRC / "site.css").read_bytes()).hexdigest()[:8]


def header(depth, staff, on):
    up = "../" * depth
    nav = ""
    if on is not None:
        # first = rightmost in RTL; the syllabus is in the admin page's "מסמכים" section
        links = [("index.html", "תוכן הקורס", "weeks"), ("book.html", "ספר היחידות", "book"), ("admin.html", "מנהלות הקורס", "admin")]
        nav = '<nav class="gen">' + "".join(
            f'<a href="{h}" class="{"on" if k == on else ""}">{t}</a>' for h, t, k in links) + "</nav>"
    badge = '<span class="staffbadge">גרסת מתרגלים</span>' if staff else ""
    return f"""<header class="hdr">
<img class="logo" src="{up}assets/tau-logo.png" alt="אוניברסיטת תל אביב">
<span class="sep"></span>
<a class="home" href="index.html"><span class="t1">{esc(CFG['title'])}</span><span class="t2">{esc(CFG['subtitle'])}</span></a>
{badge}{nav}
</header>"""


def footer(depth, staff):
    up = "../" * depth
    if staff:
        gate = f'<a class="ln" href="{up}index.html">לאתר הסטודנטים</a>'
    else:
        gate = ('<details class="tlog"><summary>כניסת מתרגלים</summary><form class="tlogf">'
                '<input type="password" autocomplete="off" aria-label="סיסמה" placeholder="סיסמה">'
                '<button type="submit">כניסה</button><span class="terr" hidden>סיסמה שגויה</span></form></details>')
    return (f'<footer class="foot"><img class="flogo" src="{up}assets/tau-logo.png" alt="">'
            f'<b>{esc(CFG["title"])}</b><span>{esc(CFG["subtitle"])}</span>{gate}</footer>')


GATE_JS = """// TA sign-in: the password is the name of the staff site's folder.
document.querySelectorAll('.tlogf').forEach(function(f){
  f.addEventListener('submit',function(e){ e.preventDefault();
    var v=f.querySelector('input').value.trim().toLowerCase().replace(/[^a-z0-9_-]/g,''), er=f.querySelector('.terr');
    if(!v) return;
    if(location.protocol==='file:'){ location.href=v+'/index.html'; return; }
    fetch(v+'/index.html',{method:'HEAD',cache:'no-store'}).then(function(r){ if(r.ok) location.href=v+'/'; else er.hidden=false; }).catch(function(){er.hidden=false});
  });
});"""


# ---------- week pages ----------

def rail_weeks(avail, sel):
    items = []
    for w in CFG["weeks"]:
        cls = "wk"
        if w["n"] == sel:
            cls += " sel"
        if w["n"] == CFG.get("current"):
            cls += " cur"
        now = '<span class="now">השבוע</span>' if w["n"] == CFG.get("current") else ""
        name = hx(w["title"]) if w["title"] else '<span class="empty">—</span>'
        inner = f'<span class="c">{w["n"]}</span><span>{name}<small class="wd">{short_date(w.get("date", ""))}</small>{now}</span>'
        if w["n"] in avail:
            items.append(f'<a href="week-{w["n"]}.html" class="{cls}">{inner}</a>')
        else:
            items.append(f'<div class="{cls} fut" title="בהכנה">{inner}</div>')
        for b in CFG.get("breaks", []):
            if b["after"] == w["n"]:
                items.append(f'<div class="wk brk"><span class="c">✦</span><span>{esc(b["label"])}<small class="wd">{short_date(b["date"])}</small></span></div>')
    items.append(f'<div class="wk fut exam"><span class="c">✱</span><span>{esc(CFG["exam"])}</span></div>')
    return "".join(items)


def player(url, title):
    """Local videos open in the site's own player page (no download button), as on the R course site."""
    return "play.html?" + urlencode({"v": url, "t": title})


def href(url, depth, title=""):
    """External links open in a new tab; local videos open in the player; other repo files (e.g. decks/W1.html) are relative to the repo root."""
    if re.match(r"https?://", url):
        return f'href="{esc(url)}" target="_blank" rel="noopener"'
    if url.lower().endswith(".mp4"):
        return f'href="{esc(player(url, title))}"'
    return f'href="{"../" * depth}{esc(url)}"'


def file_link(ref, depth):
    """A data file of an assignment: a Notion file id (files.json) or a path in the repo (files/data/...)."""
    path = FILES[ref]["path"] if ref in FILES else ref
    if not (ROOT / path).exists():
        print(f"  ! missing file: {path}")
        return ""
    name = Path(path).name
    if ref in FILES and re.match(r"^[0-9a-f]{8}-", name):
        name = name.split("-", 1)[1]
    return f'<a class="dfile" href="{"../" * depth}{esc(path)}" download>{ICON["link"]}{esc(name)}</a>'


# order of the inner books on a week page: general code management first, then the two languages
WEEK_ORDER = ("code", "r", "py")


def week_page(w, c, avail, book, depth, staff):
    n = w["n"]
    DEPTH[0] = depth
    weeks = rail_weeks(avail, n)
    rail = f'<aside class="rail card"><h3>שבועות הקורס</h3>{weeks}</aside>'
    mob = (f'<details class="mweeks card"><summary><span class="c" style="background:var(--ink);color:#fff;border-color:var(--ink)">{n}</span>'
           f'<span><b>שבוע {n}</b> · {hx(w["title"])}</span><span class="more">כל השבועות ▾</span></summary><div class="list">{weeks}</div></details>')

    deck, videos = [], []
    if c.get("deck"):
        d = c["deck"]
        deck.append(f'<a {href(d["url"], depth)} class="deck"><small>מצגת</small>'
                    f'<b>{esc(d["title"])}</b><small>{esc(d.get("note", ""))}</small><code>## WEEK {n} · R + Python</code></a>')
        r = d.get("recording")  # a recorded walk-through of the deck, in the site's player
        if r:
            deck.append(f'<a {href(r["url"], depth, r["title"])} class="vid"><span class="ic">{ICON["play"]}</span>'
                        f'<span class="vt">{esc(r["title"])}<span class="vs">{esc(r.get("note", ""))}</span></span></a>')
    for v in c.get("videos", []):
        tag = f'<span class="vtag b-{v["book"]}">{BOOK_TAG[v["book"]]}</span>' if v.get("book") else ""
        videos.append(f'<a {href(v["url"], depth, v["title"])} class="vid"><span class="ic">{ICON["play"]}</span>'
                      f'<span class="vt">{esc(v["title"])}{tag}<span class="vs">{esc(v.get("note", ""))}</span></span></a>')

    # the week's units, by inner book and chapter: the same unit component as the book, opening in place
    units = []
    for bk in WEEK_ORDER:
        mine = [u for u in c.get("units", []) if u["book"] == bk]
        if not mine:
            continue
        units.append(f'<div class="wbook b-{bk}" data-book="{bk}"><p class="wbh"><span class="btag">{BOOK_TAG[bk]}</span>{BOOK_NAME[bk]}</p>')
        for u in mine:
            ch = chapter(book, bk, u["ch"])
            if ch is None:
                print(f"  ! week {n}: no units of {bk} chapter {u['ch']} in the book")
                continue
            index = {s["h"]: k for k, s in enumerate(ch["secs"], 1)}
            for s in u["secs"]:
                if s not in index:
                    print(f"  ! week {n}: section not in {bk} chapter {u['ch']}: {s}")
            secs = "".join(book_section(ch, index[s], ch["secs"][index[s] - 1], [], in_week=True) for s in u["secs"] if s in index)
            units.append(f'<div class="wch"><span class="num">{ch["n"]}</span><b>{hx(ch["title"])}</b>'
                         f'<a class="tobook" href="book.html?w={n}#{bk}{ch["n"]}">הפרק המלא בספר ↗</a></div><div class="wunits">{secs}</div>')
        units.append("</div>")
    langs = {u["book"] for u in c.get("units", [])}
    chooser = ""
    if c.get("os_choice"):  # a week written per operating system (week 1): Windows or Mac
        chooser = OS_CHOOSER
    elif {"r", "py"} <= langs:
        chooser = ('<div class="langs" data-kind="lang" role="group" aria-label="איזו שפה להציג"><span>להציג:</span>'
                   '<button type="button" data-lang="all" class="on">הכול</button><button type="button" data-lang="r">R</button>'
                   '<button type="button" data-lang="py">Python</button></div>')
    reading = "".join(f'<a href="{esc(r["url"])}" target="_blank" rel="noopener" class="row"><span class="ic">{ICON["book"]}</span>'
                      f'<span><span class="rt ltr" style="display:block;text-align:right">{esc(r["title"])}</span><span class="rs">{esc(r.get("note", ""))}</span></span></a>'
                      for r in c.get("reading", []))

    hw = c.get("hw") or {}
    if not hw.get("title"):
        hw_html = f'<div class="hw"><p class="none">{inline(hw.get("none", "אין מטלה להגשה השבוע."))}</p></div>'
    else:
        due = (f'<p class="due">{ICON["clock"]}להגשה עד {esc(hw["due"])}</p>' if hw.get("due")
               else f'<p class="due tbd">{ICON["clock"]}תאריך ההגשה יפורסם בהמשך</p>')
        body = md_lines(hw["lines"]) if "lines" in hw else f'<ol>{"".join(f"<li>{esc(s)}</li>" for s in hw["steps"])}</ol>'
        ctx = f'<div class="ctx">{md_lines(hw["context"])}</div>' if hw.get("context") else ""
        dl = "".join(file_link(f, depth) for f in hw.get("files", []))
        dl = f'<p class="dfiles">קובצי נתונים: {dl}</p>' if dl else ""
        hw_html = (f'<div class="hw"><b class="ht">{esc(hw["title"])}</b>{ctx}{dl}<div class="hwb">{body}</div>'
                   + "".join(f'<p class="sm">{inline(p)}</p>' for p in hw.get("submit", [])) + due
                   + (f'<a class="hwsubmit" href="{esc(hw["submit_url"])}" target="_blank" rel="noopener">{ICON["spark"]}<span>להגשת המטלה<small>טופס ההגשה נפתח בלשונית חדשה</small></span></a>'
                      if hw.get("submit_url") else "") + "</div>")

    prev_n = next((m for m in sorted(avail, reverse=True) if m < n), None)
    next_n = next((m for m in sorted(avail) if m > n), None)
    title_of = {x["n"]: x["title"] for x in CFG["weeks"]}
    prev = (f'<a href="week-{prev_n}.html"><span>→ שבוע {prev_n}: {hx(title_of[prev_n])}</span></a>' if prev_n else "<span>→ אין שבוע קודם</span>")
    nxt = (f'<a href="week-{next_n}.html"><span>שבוע {next_n}: {hx(title_of[next_n])} ←</span></a>' if next_n else "<span>השבוע הבא בהכנה ←</span>")
    when = f"שבוע {n} · יום ראשון {w.get('date', '')}" + (f" · {w['note']}" if w.get("note") else "")

    main = f"""<main class="card">
<section class="hero"><p class="eyebrow">{esc(when)}</p><h1>{hx(w['title'])}</h1>{''.join(f'<p class="intro">{inline(p)}</p>' for p in c['intro'].split(chr(10) + chr(10)) if p.strip())}</section>
<section class="sec"><div class="ch"><h2>מצגת</h2></div><div class="media">{''.join(deck)}</div></section>
<section class="sec units"><div class="ch"><h2>מה לומדים השבוע</h2><span>יחידות מספר היחידות · לחצו על יחידה כדי לפתוח אותה</span></div>{chooser}{''.join(units) or '<p class="nounits">השבוע אין יחידות חדשות: חוזרים על החומר של הקורס לקראת הבחינה.</p>'}
{('<p class="sub">קריאה מומלצת</p>' + reading) if reading else ''}</section>
{f'<section class="sec"><div class="ch"><h2>סרטוני עזר</h2></div><div class="media">{"".join(videos)}</div></section>' if videos else ''}
<section class="sec"><div class="ch"><h2>המטלה השבועית</h2></div>{hw_html}{solution_html(c, staff)}</section>
<nav class="nav">{prev}{nxt}</nav>
</main>"""
    return f'{mob}<div class="layout">{rail}{main}</div>'


def solution_html(c, staff):
    """Staff site only: the solutions (model answers to open questions; terminal, R and Python code), after the assignment."""
    sol = c.get("solution")
    if not staff or not sol:
        return ""
    out = []
    for lang, label in (("answers", "· תשובות לדוגמה"), ("sh", "· הטרמינל"), ("r", "ב-R"), ("py", "בפייתון")):
        parts = []
        for blk in sol.get(lang, []):
            if blk.get("code") is not None:
                parts.append(f'<pre class="solcode ltr"><code>{esc(blk["code"])}</code></pre>')
            else:
                parts.append(f'<p>{inline(blk["text"])}</p>')
        if parts:
            out.append(f'<details class="sol"><summary>{ICON["spark"]}פתרון {label} <span>(באתר המתרגלים בלבד · ישוחרר לסטודנטים אחרי מועד ההגשה)</span></summary>'
                       f'<div class="solb">{"".join(parts)}</div></details>')
    return "".join(out)


# ---------- book of units ----------

def book_page(book, weeks, only_used=False):
    """only_used (public site): just the units of the published weeks, keeping their numbers in the book."""
    # which weeks use each section (to open them from a week's link: book.html?w=N)
    used = {}
    for n, c in weeks.items():
        for u in c.get("units", []):
            for s in u["secs"]:
                used.setdefault((u["book"], u["ch"], s), []).append(n)

    nav, body, chips = [], [], []
    for bk, tag, name in BOOKS:
        chs = [c for c in book[bk] if not only_used or any((bk, c["idx"], s["h"]) in used for s in c["secs"])]
        if not chs:
            continue
        chips.append(f'<a class="bchip b-{bk}" href="#book-{bk}"><span class="btag">{tag}</span><span>{name}<small>{len(chs)} פרקים</small></span></a>')
        nav.append(f'<h3 class="b-{bk}">{name}</h3>')
        body.append(f'<p class="grp b-{bk}" id="book-{bk}"><span class="btag">{tag}</span>{name}</p>')
        if any(it.get("mac") is not None for ch in chs for x in ch["secs"] for it in x["items"]):
            body.append(OS_CHOOSER)  # some units of this book are written per operating system
        for ch in chs:
            nav.append(f'<a href="#{bk}{ch["n"]}" class="b-{bk}"><span class="num">{ch["n"]}</span><span>{hx(ch["title"])}</span></a>')
            secs = [book_section(ch, k, s, used.get((bk, ch["idx"], s["h"]), [])) for k, s in enumerate(ch["secs"], 1)
                    if not only_used or (bk, ch["idx"], s["h"]) in used]
            body.append(f'<section class="chap b-{bk}" id="{bk}{ch["n"]}"><div class="ch"><span class="num">{ch["n"]}</span>'
                        f'<h2>{hx(ch["title"])}</h2><span>{len(secs)} יחידות</span></div>{"".join(secs)}</section>')

    rail = f'<aside class="rail card"><h3>שלושת הספרים</h3><nav class="bnav">{"".join(nav)}</nav></aside>'
    mob = (f'<details class="mweeks card"><summary><span class="ic">{ICON["book"]}</span><span><b>ספר היחידות</b></span>'
           f'<span class="more">כל הפרקים ▾</span></summary><div class="list bnav">{"".join(nav)}</div></details>')
    main = f"""<main class="card">
<section class="bhero"><p class="eyebrow">ספר היחידות</p><h1>ספר היחידות של הקורס</h1>
<p class="intro">הספר בנוי משלושה ספרים פנימיים: R, פייתון, וניהול קוד (המחשב והטרמינל, סביבות עבודה, כתיבת קוד נכונה, Git ועבודה עם AI). כל יחידה היא שיחה קצרה עם מתרגל AI: מעתיקים את ההנחיה, מדביקים אותה בצ׳אט, ומתקדמים איתו שלב אחר שלב. ליד חלק מהיחידות יש גם סרטונים וקישורים להעמקה.</p>
<div class="bchips">{"".join(chips)}</div>
<div class="howto">{ICON["spark"]}<span>לחצו על „העתקה״, הדביקו בצ׳אט של מתרגל ה-AI, וענו לו כשהוא עוצר ושואל. אם נתקעים — אפשר לבקש ממנו רמז, ורק בסוף את הפתרון.</span></div>
{books_html()}</section>
{''.join(body)}
</main>"""
    return f'{mob}<div class="layout">{rail}{main}</div>'


def books_html():
    books = CFG.get("books", [])
    if not books:
        return ""
    items = "".join(f'<li><a href="{esc(u)}" target="_blank" rel="noopener" class="ltr">{esc(t)}</a></li>' for t, u in books)
    return f'<div class="books"><p class="lbl">{ICON["book"]}ספרים מומלצים</p><ul class="links">{items}</ul></div>'


def book_section(ch, k, s, wks, in_week=False):
    bk = ch["book"]
    blocks = []

    def render(kind, t):
        t = fix(t, bk)
        if kind == "prompt":
            lines = t.split("\n")
            first = lines[0].replace("**", "").strip()
            if first in (s["h"], ch["title"]) or (len(lines) > 1 and len(first) < 30 and not re.match(r"^\d", first)):
                t = "\n".join(lines[1:]).strip()
            t = renumber(t)
            return (f'<p class="lbl">{ICON["chat"]}הנחיה למתרגל AI</p><div class="prompt">'
                    f'<button class="copy" type="button">{ICON["copy"]}<span>העתקה</span></button>'
                    f'<div class="pt">{lines_html(t, steps=True)}</div><textarea hidden>{esc(plain(t))}</textarea></div>')
        if kind in ("video", "ref"):
            items = link_lines(t)
            if not items:
                return ""
            label = (ICON["play"] + "סרטונים") if kind == "video" else (ICON["link"] + "להעמקה")
            return f'<p class="lbl">{label}</p><ul class="links">{"".join(f"<li>{i}</li>" for i in items)}</ul>'
        if kind == "code":
            return f'<div class="prompt ltr" style="padding:14px 16px;font-family:JetBrains Mono,monospace;font-size:13.5px;text-align:left">{esc(t.strip("`").strip())}</div>'
        return f'<div class="prompt" style="padding:14px 16px">{lines_html(t)}</div>'

    for it in s["items"]:
        if it.get("mac") is not None:  # written per operating system: the chooser (OS_JS) shows one of the two
            blocks.append(f'<div class="osv" data-os="win">{render(it["kind"], it["text"])}</div>'
                          f'<div class="osv" data-os="mac">{render(it["kind"], it["mac"])}</div>')
        else:
            blocks.append(render(it["kind"], it["text"]))
    uid = f'{bk}{ch["n"]}-{k}'
    if in_week:
        blocks.append(f'<p class="bsfoot">יחידה {ch["n"]}.{k} ב{BOOK_NAME[bk]} · <a href="book.html#{uid}">לראות אותה בתוך הפרק ↗</a></p>')
    data = f' data-w="{" ".join(map(str, wks))}"' if wks else ""
    return (f'<details class="bs b-{bk}" id="{uid}"{data}><summary><span class="un">{BOOK_TAG[bk] if bk != "code" else "קוד"} {ch["n"]}.{k}</span><span>{hx(fix(s["h"], bk))}</span></summary>'
            f'<div class="bsb">{"".join(blocks)}</div></details>')


COPY_JS = """// copy an AI-tutor prompt
document.querySelectorAll('.copy').forEach(function(b){
  b.addEventListener('click',function(){
    var t=b.parentNode.querySelector('textarea').value, s=b.querySelector('span');
    function ok(){ b.classList.add('ok'); s.textContent='הועתק'; setTimeout(function(){b.classList.remove('ok'); s.textContent='העתקה';},1600); }
    if(navigator.clipboard) navigator.clipboard.writeText(t).then(ok,function(){});
    else { var a=document.createElement('textarea'); a.value=t; document.body.appendChild(a); a.select(); try{document.execCommand('copy'); ok();}catch(e){} a.remove(); }
  });
});"""

LANG_JS = """// week page: show both languages, or only R / only Python (remembered in this browser)
(function(){
  var box=document.querySelector('.langs[data-kind=lang]'); if(!box) return;
  function set(l){
    box.querySelectorAll('button').forEach(function(b){ b.classList.toggle('on', b.dataset.lang===l); });
    document.querySelectorAll('.wbook[data-book=r],.wbook[data-book=py]').forEach(function(d){ d.hidden = (l!=='all' && d.dataset.book!==l); });
    try{ localStorage.setItem('yesodot-lang', l); }catch(e){}
  }
  box.addEventListener('click',function(e){ var b=e.target.closest('button'); if(b) set(b.dataset.lang); });
  var saved=null; try{ saved=localStorage.getItem('yesodot-lang'); }catch(e){}
  if(saved==='r'||saved==='py') set(saved);
})();"""

OS_CHOOSER = ('<div class="oschoice" role="group" aria-label="מערכת הפעלה"><span>על איזה מחשב אתם עובדים?</span><div>'
              '<button type="button" data-os="win" class="on" aria-pressed="true">Windows</button>'
              '<button type="button" data-os="mac" aria-pressed="false">Mac</button></div></div>')

OS_JS = """// units written per operating system: show the Windows or the Mac version (remembered in this browser)
(function(){
  if(!document.querySelector('.oschoice')) return;
  function set(o){
    document.documentElement.setAttribute('data-os', o);
    document.querySelectorAll('.oschoice button').forEach(function(b){ var on=b.dataset.os===o; b.classList.toggle('on',on); b.setAttribute('aria-pressed',on); });
    try{ localStorage.setItem('yesodot-os', o); }catch(e){}
  }
  document.addEventListener('click',function(e){ var b=e.target.closest('.oschoice button'); if(b) set(b.dataset.os); });
  var saved=null; try{ saved=localStorage.getItem('yesodot-os'); }catch(e){}
  set(saved==='mac' ? 'mac' : 'win');
})();"""

BOOK_JS = COPY_JS + """
// book.html?w=N opens (and marks) the sections that week N uses; #r3-2 opens one section
(function(){
  var w=(location.search.match(/[?&]w=(\\d+)/)||[])[1];
  if(w) document.querySelectorAll('.bs[data-w]').forEach(function(d){ if((' '+d.dataset.w+' ').indexOf(' '+w+' ')>=0){ d.open=true; d.classList.add('hl'); } });
  var h=location.hash.slice(1), el=h&&document.getElementById(h);
  if(el&&el.tagName==='DETAILS') el.open=true;
})();"""


# ---------- course admin ----------

def admin_page(prefix, avail, depth):
    """The admin page (content/admin.json): staff, meetings, submission, grading, documents — as on the R course site."""
    a = json.loads((SRC / "content" / "admin.json").read_text(encoding="utf-8"))
    # the guide to the site and any recorded meeting, side by side, in the site's player
    v = a.get("video")
    vids = ([f'<a {href(v["url"], depth, v["title"])} class="vid guide"><span class="ic">{ICON["play"]}</span>'
             f'<span class="vt">{esc(v["title"])}<span class="vs">{esc(v.get("note", ""))}</span></span></a>'] if v else [])
    vids += [f'<a {href(r["url"], depth, r["title"])} class="vid"><span class="ic">{ICON["play"]}</span>'
             f'<span class="vt">{esc(r["title"])}<span class="vs">{esc(r.get("note", ""))}</span></span></a>'
             for r in a.get("recordings", [])]
    video = (f'<section class="sec"><div class="ch"><h2>איך עובדים עם האתר</h2></div><div class="media">{"".join(vids)}</div></section>'
             if vids else "")
    people ="".join(f'<div class="person"><b>{esc(p["role"])}</b><span>{esc(p["name"])}</span>'
                     + (f'<a class="ltr" href="mailto:{esc(p["email"])}">{esc(p["email"])}</a>' if p.get("email") else "")
                     + "</div>" for p in a["staff"])
    secs = "".join(f'<section class="sec"><div class="ch"><h2>{esc(x["h"])}</h2></div><div class="adm">{md_lines(x["lines"])}</div></section>'
                   for x in a["sections"])
    # external links always; a local file (relative to the site's folder) only if it is there: syllabus.pdf is in the staff folder only
    links = "".join(f'<a href="{esc(l["url"])}" class="row" target="_blank" rel="noopener"><span class="ic">{ICON["book"]}</span>'
                    f'<span><span class="rt">{esc(l["title"])}</span><span class="rs">{esc(l.get("note", ""))}</span></span></a>'
                    for l in a.get("links", []) if re.match(r"https?://", l["url"]) or (ROOT / prefix / l["url"]).exists())
    weeks = rail_weeks(avail, None)
    rail = f'<aside class="rail card"><h3>שבועות הקורס</h3>{weeks}</aside>'
    mob = (f'<details class="mweeks card"><summary><span class="ic">{ICON["book"]}</span><span><b>מנהלות הקורס</b></span>'
           f'<span class="more">כל השבועות ▾</span></summary><div class="list">{weeks}</div></details>')
    docs = f'<section class="sec"><div class="ch"><h2>מסמכים</h2></div>{links}</section>' if links else ""
    main = (f'<main class="card"><section class="hero"><p class="eyebrow">מנהלות הקורס</p><h1>מנהלות הקורס</h1>'
            f'<p class="intro">{esc(a["intro"])}</p></section>'
            f'<section class="sec"><div class="ch"><h2>צוות הקורס</h2></div><div class="people">{people}</div></section>'
            f'{video}{secs}{docs}</main>')
    return f'{mob}<div class="layout">{rail}{main}</div>'


PLAYER_JS = """// the site's player: a local video, no download button, no right-click menu (makes saving harder, not impossible)
(function(){
  var q=new URLSearchParams(location.search), v=q.get('v')||'', t=q.get('t')||'';
  var vid=document.getElementById('vid');
  if(/^files\\/[^?#]+\\.mp4$/i.test(v) && v.indexOf('..')<0){ vid.src='__UP__'+v; }
  document.getElementById('ptitle').textContent=t;
  if(t) document.title=t+' · '+document.title;
  vid.addEventListener('contextmenu',function(e){e.preventDefault();});
  var b=document.getElementById('back');
  if(document.referrer && document.referrer.indexOf(location.host)>=0){ b.href=document.referrer; }
})();"""


def player_page(depth, staff):
    body = (header(depth, staff, None) + '<main class="card player"><a class="back" href="index.html" id="back">→ חזרה</a>'
            '<h1 class="ptitle" id="ptitle"></h1>'
            '<video id="vid" controls controlsList="nodownload" disablePictureInPicture playsinline preload="metadata"></video>'
            '</main>' + footer(depth, staff))
    return page(CFG["title"], body, depth, staff, PLAYER_JS.replace("__UP__", "../" * depth) + "\n" + GATE_JS)


# ---------- build ----------

def write(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    print("  ", rel)


def build_site(prefix, staff, avail, weeks, book):
    depth = 1 if prefix else 0
    title_of = {w["n"]: w for w in CFG["weeks"]}
    for n in avail:
        body = header(depth, staff, "weeks") + week_page(title_of[n], weeks[n], avail, book, depth, staff) + footer(depth, staff)
        html_ = page(f"שבוע {n} · {CFG['title']}", body, depth, staff, COPY_JS + "\n" + LANG_JS + "\n" + OS_JS + "\n" + GATE_JS)
        write(f"{prefix}week-{n}.html", html_)
    home = CFG.get("current") if CFG.get("current") in avail else min(avail)
    body = header(depth, staff, "weeks") + week_page(title_of[home], weeks[home], avail, book, depth, staff) + footer(depth, staff)
    write(f"{prefix}index.html", page(CFG["title"], body, depth, staff, COPY_JS + "\n" + LANG_JS + "\n" + OS_JS + "\n" + GATE_JS))
    DEPTH[0] = depth
    body = header(depth, staff, "book") + book_page(book, {n: weeks[n] for n in avail}, only_used=not staff) + footer(depth, staff)
    write(f"{prefix}book.html", page(f"ספר היחידות · {CFG['title']}", body, depth, staff, BOOK_JS + "\n" + OS_JS + "\n" + GATE_JS))
    body = header(depth, staff, "admin") + admin_page(prefix, avail, depth) + footer(depth, staff)
    write(f"{prefix}admin.html", page(f"מנהלות הקורס · {CFG['title']}", body, depth, staff, GATE_JS))
    write(f"{prefix}play.html", player_page(depth, staff))


def build_solo():
    """The public site before any week is published: the course title and a general announcement."""
    ann = CFG.get("announcement", {})
    paras = "".join(f"<p>{inline(p)}</p>" for p in ann.get("text", []))
    note = (f'<div class="ann card"><p class="eyebrow">{esc(ann.get("title", "הודעה"))}</p>{paras}</div>' if paras else "")
    body = (f'<main class="solo"><img src="assets/tau-logo.png" alt="אוניברסיטת תל אביב">'
            f'<h1>{esc(CFG["title"])}</h1><p class="st">{esc(CFG["subtitle"])}</p>{note}</main>' + footer(0, False))
    write("index.html", page(CFG["title"], body, 0, False, GATE_JS))


def main():
    weeks = load_weeks()
    book = prune_book(load_book(), weeks)
    staff = CFG["staff_dir"].strip("/")
    (ROOT / "assets").mkdir(exist_ok=True)
    shutil.copy2(SRC / "site.css", ROOT / "assets" / "site.css")
    for f in (SRC / "img").iterdir():
        shutil.copy2(f, ROOT / "assets" / f.name)

    # clear generated pages from previous builds
    for d in (ROOT, ROOT / staff):
        for f in list(d.glob("week-*.html")) + [d / "book.html", d / "admin.html", d / "play.html"]:
            if f.exists():
                f.unlink()

    print("staff site:")
    build_site(f"{staff}/", True, sorted(weeks), weeks, book)
    print("public site:")
    pub = sorted(n for n in CFG.get("published", []) if n in weeks)
    if pub:
        syl = ROOT / staff / "syllabus.pdf"  # the detailed syllabus (tools/build_syllabus.py) is public once the course is
        if syl.exists():
            shutil.copyfile(syl, ROOT / "syllabus.pdf")
        build_site("", False, pub, weeks, book)
    else:
        build_solo()
    (ROOT / ".nojekyll").touch()


if __name__ == "__main__":
    main()
