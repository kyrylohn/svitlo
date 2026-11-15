#!/usr/bin/env python3
"""svitlo_export.py — експортер стану світла для сторінки «Світло».

Працює вдома на пристрої, який завжди ввімкнений і стоїть на ДБЖ
(Raspberry Pi, NAS, старий ноутбук, Mac). Що робить:
  1. Раз на `interval` секунд перевіряє, чи є мережева напруга
     (ping / http / команда / Home Assistant).
  2. Веде журнал відключень з типом «за графіком» / «екстрене» (усе поза графіком, як рахує ДТЕК).
  3. Підтягує графік відключень з outage-data-ua (Baskerville42).
  4. Пише data.json у локальний клон гілки `data` і пушить його (один
     коміт, що перезаписується, тож історія не росте).

Запуск:
  python3 svitlo_export.py --config config.json            # цикл
  python3 svitlo_export.py --check                         # лише перевірка джерела
  python3 svitlo_export.py --dry                           # вивести data.json, без git
  python3 svitlo_export.py --once [--force]                # одна ітерація

Лише стандартна бібліотека, Python 3.9+.
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")
SCHEDULE_URL = "https://raw.githubusercontent.com/Baskerville42/outage-data-ua/main/data/%s.json"
SCHEDULE_TTL = 300
KEEP_JOURNAL = 400
GIT_TIMEOUT = 120
COMMIT_MSG = "Дані сторінки (оновлюються автоматично)"

DEFAULTS = {
    "repo_dir": "~/svitlo-data", "branch": "data", "interval": 60,
    "heartbeat_min": 15, "off_after": 3, "on_after": 2, "min_outage_sec": 60,
    "region": "dnipro", "group_key": "GPV5.1",
    "source": {"type": "ping", "host": "192.168.1.50"},
}


def log(msg):
    print("%s %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


def die(msg):
    print("Помилка: " + msg, file=sys.stderr, flush=True)
    sys.exit(2)


# ---------- джерела світла: True = є, False = немає, None = невідомо ----------

def check_ping(src):
    host, count, timeout = str(src["host"]), int(src.get("count", 2)), int(src.get("timeout", 2))
    if host.startswith("-"):
        die("некоректний host для ping")
    system = platform.system()
    if system == "Windows":
        cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), host]
    elif system == "Darwin":
        cmd = ["ping", "-c", str(count), "-t", str(timeout * count), host]
    else:
        cmd = ["ping", "-c", str(count), "-W", str(timeout), host]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=count * timeout + 10)
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def check_http(src):
    try:
        req = urllib.request.Request(src["url"], headers={"User-Agent": "svitlo-export"})
        with urllib.request.urlopen(req, timeout=float(src.get("timeout", 5))) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def check_command(src):
    try:
        r = subprocess.run(src["cmd"], shell=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=float(src.get("timeout", 30)))
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def check_ha(src):
    token = os.environ.get(src.get("token_env", "HA_TOKEN"))
    if not token:
        die("не задано змінну середовища %s з токеном Home Assistant" % src.get("token_env", "HA_TOKEN"))
    url = src["url"].rstrip("/") + "/api/states/" + src["entity"]
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=float(src.get("timeout", 10))) as r:
            state = str(json.loads(r.read().decode("utf-8")).get("state", "")).lower()
    except Exception:
        return None  # HA недоступний / 401 — це не «немає світла»
    return {"on": True, "off": False}.get(state)


SOURCES = {"ping": check_ping, "http": check_http, "command": check_command, "ha": check_ha}


def check_source(src):
    fn = SOURCES.get(src.get("type"))
    if not fn:
        die("невідомий тип джерела: %r (є: %s)" % (src.get("type"), ", ".join(SOURCES)))
    return fn(src)


# ---------- графік outage-data-ua ----------

HOUR_SPANS = {  # значення -> (зсув початку, зсув кінця у хвилинах, тип)
    "no": (0, 60, "p"), "first": (0, 30, "p"), "second": (30, 60, "p"),
    "maybe": (0, 60, "i"), "mfirst": (0, 30, "i"), "msecond": (30, 60, "i"),
}


def parse_day(hours):
    """{"1": "yes", ...} -> [{"s","e","t"}], суміжні проміжки одного типу зливаються."""
    spans = []
    for i in range(1, 25):
        rule = HOUR_SPANS.get(hours.get(str(i)))
        if not rule:
            continue
        s, e, t = (i - 1) * 60 + rule[0], (i - 1) * 60 + rule[1], rule[2]
        if spans and spans[-1]["t"] == t and spans[-1]["e"] == s:
            spans[-1]["e"] = e
        else:
            spans.append({"s": s, "e": e, "t": t})
    return spans


class Schedule:
    def __init__(self, region):
        self.url = SCHEDULE_URL % region
        self.raw = None
        self.fetched = 0

    def refresh(self):
        if time.time() - self.fetched < SCHEDULE_TTL:
            return
        self.fetched = time.time()  # не довбати сервер при збої
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": "svitlo-export"})
            with urllib.request.urlopen(req, timeout=20) as r:
                fact = json.loads(r.read().decode("utf-8"))["fact"]
            if isinstance(fact.get("data"), dict):
                self.raw = fact
        except Exception as e:
            log("графік: помилка завантаження (%s), лишаю попередній" % e)

    def days(self, group_key, today):
        """Повертає (today_spans|None, tomorrow_spans|None) для дат Києва."""
        out = []
        for d in (today, today + timedelta(days=1)):
            key = str(int(datetime(d.year, d.month, d.day, tzinfo=KYIV).timestamp()))
            group = self.raw["data"].get(key, {}).get(group_key)
            out.append(parse_day(group) if isinstance(group, dict) else None)
        return out[0], out[1]


# ---------- стан ----------

def load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    base = {"svitlo": "unknown", "base": None, "pochatok": 0, "typ": "", "zhurnal": [],
            "last_push": 0, "last_body": ""}
    base.update(st)
    return base


def save_state(path, st):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, path)


class Tracker:
    """Дебаунс і журнал. st["base"] — останній певний стан (on/off/None)."""

    def __init__(self, cfg, st):
        self.cfg, self.st = cfg, st
        self.fails = self.oks = 0
        self.first_fail = self.first_ok = 0

    def update(self, ok, now, spans_today):
        st, cfg = self.st, self.cfg
        if ok is None:
            st["svitlo"] = "unknown"
            return
        if ok:
            self.fails = 0
            self.oks += 1
            if self.oks == 1:
                self.first_ok = now
            if st["base"] is None or (st["base"] == "off" and self.oks >= cfg["on_after"]):
                if st["base"] == "off" and st["pochatok"]:
                    if self.first_ok - st["pochatok"] >= cfg["min_outage_sec"]:
                        st["zhurnal"].append({"s": st["pochatok"], "e": self.first_ok,
                                              "t": st["typ"] or "u"})
                        st["zhurnal"] = st["zhurnal"][-KEEP_JOURNAL:]
                st["base"], st["pochatok"], st["typ"] = "on", 0, ""
        else:
            self.oks = 0
            self.fails += 1
            if self.fails == 1:
                self.first_fail = now
            if st["base"] is None or (st["base"] == "on" and self.fails >= cfg["off_after"]):
                st["base"], st["pochatok"] = "off", self.first_fail
                st["typ"] = classify(spans_today, self.first_fail)
        st["svitlo"] = st["base"]


def classify(spans_today, ts):
    """'p' — за графіком, 'e' — екстрене (усе поза графіком, як у ДТЕК), '' — графіка немає."""
    if spans_today is None:
        return ""
    dt = datetime.fromtimestamp(ts, KYIV)
    m = dt.hour * 60 + dt.minute
    return "p" if any(sp["t"] == "p" and sp["s"] <= m + 20 and sp["e"] >= m - 5
                      for sp in spans_today) else "e"


# ---------- data.json ----------

def build_grafik(sched, cfg, now_dt):
    today = now_dt.date()
    t_spans, tm_spans = sched.days(cfg["group_key"], today)
    grafik = {"date": today.isoformat(), "today": t_spans, "tomorrow": tm_spans,
              "tomorrow_status": "waiting_for_schedule" if tm_spans is None else "schedule_applies",
              "dzherelo": "outage-data-ua", "onovleno": sched.raw.get("update"),
              "ok": t_spans is not None}
    # планові проміжки на сьогодні+завтра, зшиті через північ
    planned = [dict(sp) for sp in (t_spans or []) if sp["t"] == "p"]
    for sp in (tm_spans or []):
        if sp["t"] == "p":
            planned.append({"s": sp["s"] + 1440, "e": sp["e"] + 1440, "t": "p"})
    merged = []
    for sp in planned:
        if merged and merged[-1]["e"] == sp["s"]:
            merged[-1]["e"] = sp["e"]
        else:
            merged.append(sp)
    midnight = datetime(today.year, today.month, today.day, tzinfo=KYIV)
    iso = lambda m: (midnight + timedelta(minutes=m)).isoformat()
    nowm = now_dt.hour * 60 + now_dt.minute + now_dt.second / 60.0
    current = next((sp for sp in merged if sp["s"] <= nowm < sp["e"]), None)
    nxt = next((sp for sp in merged if sp["s"] > nowm), None)
    nastupne = iso(nxt["s"]) if nxt else None
    end = current or nxt
    return grafik, nastupne, (iso(end["e"]) if end else None)


def build_data(cfg, st, sched, now):
    now_dt = datetime.fromtimestamp(now, KYIV)
    data = {"v": 1, "group": cfg["group_key"].replace("GPV", ""), "svitlo": st["svitlo"],
            "pochatok": st["pochatok"] if st["base"] == "off" else 0, "typ": st["typ"],
            "zhurnal": st["zhurnal"]}
    if sched.raw is not None:
        data["grafik"], data["nastupne"], data["vkliuchennia"] = build_grafik(sched, cfg, now_dt)
    return data


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ---------- git ----------

def git(repo, *args):
    env = dict(os.environ)
    ident = subprocess.run(["git", "-C", repo, "config", "user.email"],
                           capture_output=True, text=True).stdout.strip()
    if not ident:
        env.update(GIT_AUTHOR_NAME="svitlo", GIT_AUTHOR_EMAIL="svitlo@localhost",
                   GIT_COMMITTER_NAME="svitlo", GIT_COMMITTER_EMAIL="svitlo@localhost")
    return subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True,
                          timeout=GIT_TIMEOUT, env=env)


def publish(cfg, repo, text):
    with open(os.path.join(repo, "data.json"), "w", encoding="utf-8") as f:
        f.write(text)
    r = git(repo, "add", "data.json")
    if r.returncode:
        raise RuntimeError("git add: " + r.stderr.strip())
    has_head = git(repo, "rev-parse", "--verify", "-q", "HEAD").returncode == 0
    if has_head:
        r = git(repo, "commit", "-q", "--amend", "--no-edit", "--allow-empty", "--date=now")
    else:
        r = git(repo, "commit", "-q", "--allow-empty", "-m", COMMIT_MSG)
    if r.returncode:
        raise RuntimeError("git commit: " + r.stderr.strip())
    err = ""
    for attempt in range(4):
        r = git(repo, "push", "-q", "-f", "origin", "HEAD:refs/heads/" + cfg["branch"])
        if r.returncode == 0:
            return
        err = r.stderr.strip()
        if attempt < 3:
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("git push: " + err)


# ---------- основний цикл ----------

def iteration(cfg, st, tracker, sched, args, state_path, repo):
    now = int(time.time())
    sched.refresh()
    spans_today = None
    if sched.raw is not None:
        spans_today = sched.days(cfg["group_key"], datetime.fromtimestamp(now, KYIV).date())[0]
    tracker.update(check_source(cfg["source"]), now, spans_today)
    data = build_data(cfg, st, sched, now)
    body = dump(data)
    if args.dry:
        print(json.dumps(dict(data, generated=now), ensure_ascii=False, indent=2))
        return
    due = now - st["last_push"] >= cfg["heartbeat_min"] * 60
    if args.force or due or body != st["last_body"]:
        data["generated"] = now
        try:
            publish(cfg, repo, dump(data))
            st["last_push"], st["last_body"] = now, body
            log("pushed svitlo=%s zapysiv=%d" % (st["svitlo"], len(st["zhurnal"])))
        except Exception as e:
            log("помилка публікації: %s" % e)
    save_state(state_path, st)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Експортер стану світла для сторінки «Світло»")
    ap.add_argument("--config", default=os.path.join(here, "config.json"))
    ap.add_argument("--once", action="store_true", help="одна ітерація і вихід")
    ap.add_argument("--force", action="store_true", help="пушити навіть без змін")
    ap.add_argument("--dry", action="store_true", help="одна перевірка, друк data.json, без git")
    ap.add_argument("--check", action="store_true", help="перевірити джерело і вийти")
    args = ap.parse_args()

    try:
        with open(args.config, encoding="utf-8") as f:
            cfg = dict(DEFAULTS, **json.load(f))
    except (OSError, ValueError) as e:
        die("не вдалося прочитати конфіг %s: %s" % (args.config, e))

    if args.check:
        print({True: "світло є", False: "світла немає", None: "невідомо"}[check_source(cfg["source"])])
        return

    repo = os.path.expanduser(cfg["repo_dir"])
    if not args.dry and not os.path.isdir(os.path.join(repo, ".git")):
        die("%s не є git-репозиторієм (склонуйте репо і виконайте checkout гілки %s)" % (repo, cfg["branch"]))
    state_path = os.path.join(repo, ".git", "svitlo_state.json")
    st = load_state(state_path)
    tracker = Tracker(cfg, st)
    sched = Schedule(cfg["region"])
    one = args.once or args.dry
    try:
        while True:
            try:
                iteration(cfg, st, tracker, sched, args, state_path, repo)
            except SystemExit:
                raise
            except Exception as e:
                log("помилка ітерації: %s" % e)
            if one:
                break
            time.sleep(cfg["interval"])
    except KeyboardInterrupt:
        print("\nЗупинено.", flush=True)


if __name__ == "__main__":
    main()
