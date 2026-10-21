#!/usr/bin/env python3
"""Zugriff auf lernen.h-da.de über die Moodle-Mobile-Web-Service-API.

Befehle:
  login               Token mit h-da-Zugangsdaten holen und im macOS-Schlüsselbund ablegen
                      (einmalig; das Passwort wird nur für diesen Aufruf benutzt, nie gespeichert).
  whoami              Token prüfen, zeigt Name und Site.
  courses             Alle eingeschriebenen Kurse (auch verborgene) auflisten.
  sync [kurs ...]     Kursstruktur und Ankündigungen abrufen, als Manifest speichern und
                      Änderungen seit dem letzten Sync ausgeben. Lädt keine Dateien.
  sections <kurs>     Abschnitte und Module eines Kurses aus dem Manifest zeigen (mit IDs).
  fetch <kurs> ...    Dateien laden: --section N (ganzer Abschnitt), --module ID, oder --all.
                      Lädt nur, was lokal fehlt oder sich auf Moodle geändert hat.
  news [kurs ...]     Ankündigungen aus dem Manifest zeigen.
  deadlines           Anstehende Moodle-Termine (Abgaben, Tests) aus dem Moodle-Kalender.

Kurs-Kürzel und Zielordner stehen in <projekt>/tools/moodle/courses.json (Projekt = $HDA_ROOT oder cwd). Manifest und
Dateien liegen unter <kursordner>/moodle/. Token widerrufen: Moodle → Profil →
Sicherheitsschlüssel; lokal löschen: security delete-generic-password -s hda-moodle-token
"""
import argparse
import datetime as dt
import getpass
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

MOODLE_URL = "https://lernen.h-da.de"
SERVICE = "moodle_mobile_app"
KEYCHAIN_SERVICE = "hda-moodle-token"
# Projektordner: Umgebungsvariable HDA_ROOT oder das aktuelle Arbeitsverzeichnis.
# Dort liegen tools/moodle/courses.json und die Kursordner.
ROOT = Path(os.environ.get("HDA_ROOT", os.getcwd())).resolve()
CONF = ROOT / "tools" / "moodle" / "courses.json"
COURSES = json.loads(CONF.read_text()) if CONF.exists() else {}


# --- Schlüsselbund -----------------------------------------------------------

def keychain_get():
    r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def keychain_set(account, token):
    subprocess.run(["security", "add-generic-password", "-a", account, "-s", KEYCHAIN_SERVICE,
                    "-w", token, "-U"], check=True, capture_output=True)


def require_token():
    token = keychain_get()
    if not token:
        sys.exit("Kein Token im Schlüsselbund. Zuerst `moodle.py login` ausführen.")
    return token


# --- HTTP / Web Services -----------------------------------------------------

def post(path, data):
    req = urllib.request.Request(MOODLE_URL + path, data=urllib.parse.urlencode(data).encode())
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def flatten(params, prefix=""):
    """Moodle erwartet Arrays als key[0]=... und Objekte als key[feld]=..."""
    out = {}
    for key, value in params.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, dict):
            out.update(flatten(value, name))
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                if isinstance(item, (dict, list, tuple)):
                    out.update(flatten({i: item}, name))
                else:
                    out[f"{name}[{i}]"] = item
        else:
            out[name] = value
    return out


def ws(token, function, **params):
    data = {"wstoken": token, "wsfunction": function, "moodlewsrestformat": "json"}
    data.update(flatten(params))
    result = post("/webservice/rest/server.php", data)
    if isinstance(result, dict) and "exception" in result:
        sys.exit(f"Moodle-Fehler bei {function}: {result.get('errorcode')} – {result.get('message')}")
    return result


def text(h):
    t = re.sub(r"<br\s*/?>|</p>|</li>|</tr>", "\n", h or "")
    t = re.sub(r"</t[dh]>", " | ", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def when(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M") if ts else "?"


# --- Kurse / Manifest ----------------------------------------------------------

def course(key):
    if key not in COURSES:
        sys.exit(f"Unbekannter Kurs „{key}“. Bekannt: {', '.join(COURSES)}")
    c = dict(COURSES[key]); c["key"] = key
    c["path"] = ROOT / c["dir"] / "moodle"
    return c


def manifest_path(c):
    return c["path"] / "manifest.json"


def load_manifest(c):
    p = manifest_path(c)
    return json.loads(p.read_text()) if p.exists() else None


def build_manifest(token, c):
    secs = ws(token, "core_course_get_contents", courseid=c["id"])
    sections = []
    for s in secs:
        mods = []
        for md in s.get("modules", []):
            mods.append({
                "id": md["id"], "modname": md["modname"], "name": html.unescape(md["name"]),
                "visible": md.get("visible", 1), "url": md.get("url"),
                "description": text(md.get("description")),
                "contents": [{"filename": f.get("filename"), "filepath": f.get("filepath") or "/",
                              "fileurl": f.get("fileurl"), "filesize": f.get("filesize"),
                              "timemodified": f.get("timemodified"), "type": f.get("type")}
                             for f in (md.get("contents") or []) if f.get("fileurl") and f.get("type") == "file"],
            })
        sections.append({"section": s["section"], "name": html.unescape(s["name"]),
                         "visible": s.get("visible", 1), "summary": text(s.get("summary")),
                         "modules": mods})
    news = []
    for f in ws(token, "mod_forum_get_forums_by_courses", courseids=[c["id"]]):
        if f["type"] != "news":
            continue
        d = ws(token, "mod_forum_get_forum_discussions", forumid=f["id"], sortorder=1, perpage=20)
        for x in d.get("discussions", []):
            news.append({"id": x["discussion"], "time": x["timemodified"], "subject": x["subject"],
                         "author": x["userfullname"], "message": text(x["message"])})
    return {"synced": dt.datetime.now().isoformat(timespec="seconds"), "course": {k: c[k] for k in ("key", "id", "title")},
            "sections": sections, "news": news}


def diff_manifest(old, new):
    """Liefert Textzeilen mit Änderungen zwischen zwei Manifesten."""
    lines = []
    if old is None:
        return ["Erster Sync, kein Vergleich möglich."]
    def index(m):
        mods, files = {}, {}
        for s in m["sections"]:
            for md in s["modules"]:
                mods[md["id"]] = (s, md)
                for f in md["contents"]:
                    files[f["fileurl"]] = (s, md, f)
        return mods, files
    om, of = index(old); nm, nf = index(new)
    for mid, (s, md) in nm.items():
        if mid not in om:
            lines.append(f"NEU     [{s['section']}] {s['name']} → {md['modname']} „{md['name']}“ (Modul {mid})")
        elif om[mid][1]["description"] != md["description"]:
            lines.append(f"TEXT    [{s['section']}] „{md['name']}“ Beschreibung geändert")
    for mid, (s, md) in om.items():
        if mid not in nm:
            lines.append(f"WEG     [{s['section']}] „{md['name']}“ entfernt")
    for url, (s, md, f) in nf.items():
        if url not in of:
            if md["id"] in om:
                lines.append(f"DATEI+  [{s['section']}] „{md['name']}“: {f['filename']} ({when(f['timemodified'])})")
        elif of[url][2]["timemodified"] != f["timemodified"] or of[url][2]["filesize"] != f["filesize"]:
            lines.append(f"GEÄNDERT[{s['section']}] „{md['name']}“: {f['filename']} ({when(f['timemodified'])})")
    for s in new["sections"]:
        o = next((x for x in old["sections"] if x["section"] == s["section"]), None)
        if o is None:
            lines.append(f"ABSCHN+ [{s['section']}] {s['name']}")
        elif o["summary"] != s["summary"] or o["name"] != s["name"]:
            lines.append(f"ABSCHN~ [{s['section']}] {s['name']} (Text/Name geändert)")
    oldnews = {n["id"] for n in old["news"]}
    for n in new["news"]:
        if n["id"] not in oldnews:
            lines.append(f"NEWS    {when(n['time'])} {n['author']}: „{n['subject']}“")
    return lines or ["Keine Änderungen."]


# --- Befehle -----------------------------------------------------------------

def cmd_login(args):
    if not sys.stdin.isatty():
        sys.exit("`login` braucht ein Terminal mit TTY. Bitte in einem normalen Terminalfenster ausführen.")
    user = args.user or input("h-da Benutzername: ").strip()
    password = getpass.getpass("h-da Passwort (wird nicht gespeichert): ")
    res = post("/login/token.php", {"username": user, "password": password, "service": SERVICE})
    del password
    if "token" not in res:
        sys.exit(f"Login fehlgeschlagen: {res.get('error') or res}")
    keychain_set(user, res["token"])
    info = ws(res["token"], "core_webservice_get_site_info")
    print(f"Angemeldet als {info['fullname']} auf „{info['sitename']}“. Token im Schlüsselbund „{KEYCHAIN_SERVICE}“.")


def cmd_whoami(args):
    info = ws(require_token(), "core_webservice_get_site_info")
    print(f"{info['fullname']} ({info['username']}) auf „{info['sitename']}“, Moodle {info.get('release', '?')}")


def cmd_courses(args):
    token = require_token()
    info = ws(token, "core_webservice_get_site_info")
    courses = ws(token, "core_enrol_get_users_courses", userid=info["userid"])
    courses.sort(key=lambda c: (bool(c.get("hidden")), c.get("fullname", "")))
    known = {v["id"]: k for k, v in COURSES.items()}
    for c in courses:
        flag = " (verborgen)" if c.get("hidden") else ""
        key = known.get(c["id"], "")
        print(f"{c['id']:>6}  {key:<5} {c.get('shortname', ''):<32} {c['fullname']}{flag}")


def cmd_sync(args):
    token = require_token()
    keys = args.kurs or list(COURSES)
    for key in keys:
        c = course(key)
        old = load_manifest(c)
        new = build_manifest(token, c)
        c["path"].mkdir(parents=True, exist_ok=True)
        lines = diff_manifest(old, new)
        manifest_path(c).write_text(json.dumps(new, ensure_ascii=False, indent=1))
        print(f"== {key}: {c['title']} ({len(new['sections'])} Abschnitte, {len(new['news'])} Ankündigungen)")
        for ln in lines:
            print("   " + ln)
        if old is not None and lines != ["Keine Änderungen."]:
            with open(c["path"] / "changes.log", "a") as fh:
                fh.write(f"\n# {new['synced']}\n" + "\n".join(lines) + "\n")


def local_file(c, s, f):
    sec = f"{s['section']:02d}-{re.sub(r'[^\w.-]+', '_', s['name'])[:40]}"
    return c["path"] / "files" / sec / f["filepath"].strip("/") / f["filename"]


def cmd_sections(args):
    c = course(args.kurs)
    m = load_manifest(c) or sys.exit("Noch kein Manifest, zuerst `sync`.")
    print(f"{c['title']} – Stand {m['synced']}")
    for s in m["sections"]:
        if not s["visible"] and not args.all:
            continue
        print(f"\n[{s['section']}] {s['name']}")
        if s["summary"] and args.verbose:
            print("    " + s["summary"].replace("\n", "\n    ")[:800])
        for md in s["modules"]:
            mark = ""
            if md["contents"]:
                have = sum(local_file(c, s, f).exists() for f in md["contents"])
                mark = f" [{have}/{len(md['contents'])} lokal]"
            print(f"    {md['id']:>7} {md['modname']:<10} {md['name'][:80]}{mark}")
            if args.verbose and md["description"]:
                print("            " + md["description"].replace("\n", "\n            ")[:600])
            for f in md["contents"] if args.verbose else []:
                print(f"            · {f['filename']} ({(f['filesize'] or 0)//1024} KB, {when(f['timemodified'])})")


def cmd_fetch(args):
    token = require_token()
    c = course(args.kurs)
    m = load_manifest(c) or sys.exit("Noch kein Manifest, zuerst `sync`.")
    todo = []
    for s in m["sections"]:
        for md in s["modules"]:
            if args.all or (args.section is not None and s["section"] == args.section) \
                    or (args.module and md["id"] in args.module):
                todo += [(s, md, f) for f in md["contents"]]
    if not todo:
        sys.exit("Nichts ausgewählt (--section N, --module ID oder --all).")
    for s, md, f in todo:
        dest = local_file(c, s, f)
        if dest.exists() and f["timemodified"] and int(dest.stat().st_mtime) == f["timemodified"]:
            print(f"ok      {dest.relative_to(ROOT)}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = f["fileurl"] + ("&" if "?" in f["fileurl"] else "?") + "token=" + token
        with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as out:
            while chunk := r.read(1 << 16):
                out.write(chunk)
        if f["timemodified"]:
            os.utime(dest, (f["timemodified"], f["timemodified"]))
        print(f"geladen {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KB)")


def cmd_news(args):
    for key in args.kurs or list(COURSES):
        c = course(key)
        m = load_manifest(c)
        if not m:
            continue
        print(f"== {c['title']}")
        for n in sorted(m["news"], key=lambda n: -n["time"]):
            print(f"-- {when(n['time'])} {n['author']}: {n['subject']}\n{n['message']}\n")


def cmd_deadlines(args):
    token = require_token()
    now = int(dt.datetime.now().timestamp())
    ev = ws(token, "core_calendar_get_action_events_by_timesort", timesortfrom=now, limitnum=50)
    events = ev.get("events", [])
    if not events:
        print("Keine anstehenden Moodle-Termine.")
    for e in events:
        cs = e["course"]["shortname"] if e.get("course") else "-"
        print(f"{when(e['timesort'])}  {cs:<20} {e['modulename']:<8} {e['name']}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("login"); s.add_argument("--user"); s.set_defaults(fn=cmd_login)
    s = sub.add_parser("whoami"); s.set_defaults(fn=cmd_whoami)
    s = sub.add_parser("courses"); s.set_defaults(fn=cmd_courses)
    s = sub.add_parser("sync"); s.add_argument("kurs", nargs="*"); s.set_defaults(fn=cmd_sync)
    s = sub.add_parser("sections"); s.add_argument("kurs"); s.add_argument("-v", "--verbose", action="store_true")
    s.add_argument("--all", action="store_true", help="auch unsichtbare Abschnitte"); s.set_defaults(fn=cmd_sections)
    s = sub.add_parser("fetch"); s.add_argument("kurs"); s.add_argument("--section", type=int)
    s.add_argument("--module", type=int, action="append"); s.add_argument("--all", action="store_true"); s.set_defaults(fn=cmd_fetch)
    s = sub.add_parser("news"); s.add_argument("kurs", nargs="*"); s.set_defaults(fn=cmd_news)
    s = sub.add_parser("deadlines"); s.set_defaults(fn=cmd_deadlines)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
