#!/usr/bin/env python3
"""
抓中央氣象署開放資料「海象監測資料－30 天浮標站監測資料」(O-B0075-002)，
把新竹浮標 (46757B) 的逐時波浪資料合併進一個長期 CSV。

CSV 格式刻意與氣象署「海象觀測資料查詢」匯出的逐時 CSV 相容，
天候窗計算器的 parseCWA() 直接吃得下：
    以 st, 開頭的表頭，必含 yyyymmddhhmi（台北時間）與 H（示性波高，cm）。
我們多留 T（週期，秒，一位小數）與 D（波向，度）兩欄備用。

用法：
    python fetch_cwa_buoy.py --key <CWA_API_KEY> [--station 46757B] [--csv data/46757B_hourly.csv]
    python fetch_cwa_buoy.py --import 歷史下載.csv --csv data/46757B_hourly.csv   # 匯入一次性下載的歷史檔
環境變數 CWA_API_KEY 也可以代替 --key。

只用標準函式庫，沒有第三方依賴。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-B0075-002"
HEADER = ["st", "yyyymmddhhmi", "H", "T", "D"]
COMMENT = (
    "# 新竹浮標 46757B 逐時波浪資料。來源：中央氣象署開放資料 O-B0075-002（30 天滾動）及一次性匯入的歷史檔。"
    " H=示性波高(cm) T=週期(s) D=波向(度，自北順時針)。缺值留空。本檔由 fetch_cwa_buoy.py 自動合併。"
)


# ----------------------------------------------------------------------------- API
def fetch_api(key: str, station: str) -> list[dict]:
    """回傳 [{'ts': 'yyyymmddhhmi', 'H': cm or None, 'T': s or None, 'D': deg or None}, ...]"""
    q = urllib.parse.urlencode({"Authorization": key, "StationID": station})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "cwa-buoy-fetch/1.0", "Accept": "application/json"})
    # 氣象署憑證缺 Subject Key Identifier，Python 3.13 起預設的 VERIFY_X509_STRICT 會拒絕連線。
    # 只關掉嚴格模式，憑證鏈與主機名稱照常驗證。
    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        payload = json.loads(r.read().decode("utf-8"))

    # 結構（2026-10-15 實測）：Records.SeaSurfaceObs.Location[].StationObsTimes.StationObsTime[]（與 Result.Fields 並列）
    #   每筆：{"DateTime": "2026-10-02T22:00:00+08:00", "WeatherElements": {"WaveHeight": "1.8", "WavePeriod": "5.0", "WaveDirection": "11.0", ...}}
    #   約 721 筆、順序不固定；缺測為字串 "None"。
    # 氣象署偶爾改大小寫或多包一層，所以用遞迴搜尋 StationObsTime 清單，不寫死路徑。
    records = []
    for loc in _find_lists(payload, "Location"):
        for st in loc:
            sid = _deep_get(st, ["Station", "StationID"]) or _deep_get(st, ["StationID"])
            if sid and station and str(sid).strip().upper() != station.upper():
                continue
            for obs in _find_lists(st, "StationObsTime"):
                for rec in obs:
                    row = _parse_record(rec, station)
                    if row:
                        records.append(row)
    if not records:
        msg = json.dumps(payload, ensure_ascii=False)[:400]
        raise SystemExit(f"API 沒有回傳 {station} 的觀測列；回應開頭：{msg}")
    return records


def _parse_record(rec: dict, station: str) -> dict | None:
    dt = rec.get("DateTime") or rec.get("ObsTime") or rec.get("Time")
    if not dt:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})", str(dt))
    if not m:
        return None
    ts = "".join(m.groups())  # 台北時間，與氣象署歷史 CSV 一致
    we = rec.get("WeatherElements") or rec.get("weatherElements") or rec
    h = _num(we.get("WaveHeight"))
    t = _num(we.get("WavePeriod"))
    d = _num(we.get("WaveDirection"))
    # 明顯不合理的值視為缺測（儀器或通訊故障會出現 0、負值或極大值）
    if h is not None and (h <= 0 or h > 25):
        h = None
    if t is not None and (t <= 0 or t > 30):
        t = None
    if d is not None and not (0 <= d <= 360):
        d = None
    return {"st": station, "ts": ts, "H": None if h is None else round(h * 100), "T": t, "D": d}


def _num(v):
    try:
        if v is None:
            return None
        s = str(v).strip()
        if s in ("", "-", "None", "null", "NA", "X", "x"):
            return None
        return float(s)
    except ValueError:
        return None


def _deep_get(d, path):
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _find_lists(node, key):
    """遞迴找出所有名為 key、值為 list 的欄位（大小寫不敏感）。"""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower() == key.lower() and isinstance(v, list):
                out.append(v)
            else:
                out.extend(_find_lists(v, key))
    elif isinstance(node, list):
        for v in node:
            out.extend(_find_lists(v, key))
    return out


# ----------------------------------------------------------------------------- CSV
def read_csv(path: Path) -> dict[str, dict]:
    """讀既有合併檔或氣象署匯出檔，回傳 {ts: row}。自動跳過說明列、找 st, 表頭。"""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    hi = next((i for i, l in enumerate(lines) if l.strip().startswith("st,")), None)
    if hi is None:
        raise SystemExit(f"{path}：找不到以 st, 開頭的表頭")
    head = [c.strip() for c in lines[hi].split(",")]
    it, ih = head.index("yyyymmddhhmi"), head.index("H")
    itp = head.index("T") if "T" in head else None
    idd = head.index("D") if "D" in head else None
    ist = head.index("st") if "st" in head else None
    rows = {}
    tvals = []
    for l in lines[hi + 1:]:
        c = l.split(",")
        if len(c) <= max(it, ih):
            continue
        ts = c[it].strip()
        if not re.fullmatch(r"\d{12}", ts):
            continue
        h = _num(c[ih])
        t = _num(c[itp]) if itp is not None and itp < len(c) else None
        d = _num(c[idd]) if idd is not None and idd < len(c) else None
        if t is not None:
            tvals.append(t)
        rows[ts] = {"st": c[ist].strip() if ist is not None else "", "ts": ts,
                    "H": None if h is None or h < 0 else round(h), "T": t, "D": d}
    # 氣象署歷史匯出檔的週期常以 0.1 s 為單位（例如 55 代表 5.5 s）；若中位數 > 30 就換算回秒。
    if tvals:
        tv = sorted(tvals)
        if tv[len(tv) // 2] > 30:
            for r in rows.values():
                if r["T"] is not None:
                    r["T"] = r["T"] / 10
    return rows


def write_csv(path: Path, rows: dict[str, dict], station: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        f.write(COMMENT + "\n")
        w = csv.writer(f)
        w.writerow(HEADER)
        for ts in sorted(rows):
            r = rows[ts]
            w.writerow([
                r.get("st") or station, ts,
                "" if r["H"] is None else int(r["H"]),
                "" if r["T"] is None else f"{r['T']:.1f}",
                "" if r["D"] is None else f"{r['D']:.0f}",
            ])
    tmp.replace(path)


def merge(base: dict[str, dict], new: dict[str, dict]) -> tuple[dict[str, dict], int, int]:
    """新資料覆蓋同時間的舊資料（氣象署會回填／修正），回傳 (合併結果, 新增筆數, 更新筆數)。"""
    added = updated = 0
    for ts, r in new.items():
        if ts not in base:
            added += 1
        elif base[ts] != r and r["H"] is not None:
            updated += 1
        else:
            continue
        base[ts] = r
    return base, added, updated


# ----------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", default=os.environ.get("CWA_API_KEY"), help="氣象署開放資料 API 授權碼（或設環境變數 CWA_API_KEY）")
    ap.add_argument("--station", default="46757B", help="測站代碼，預設新竹浮標 46757B")
    ap.add_argument("--csv", default="data/46757B_hourly.csv", help="長期合併檔路徑")
    ap.add_argument("--import", dest="import_files", nargs="*", default=[], help="一次性匯入的氣象署歷史 CSV（可多個）")
    ap.add_argument("--no-api", action="store_true", help="只匯入、不呼叫 API")
    a = ap.parse_args()

    out = Path(a.csv)
    rows = read_csv(out)
    n0 = len(rows)
    print(f"既有資料 {n0:,} 筆" + (f"（{min(rows)}–{max(rows)}）" if rows else ""))

    for p in a.import_files:
        imp = read_csv(Path(p))
        rows, add, upd = merge(rows, imp)
        print(f"匯入 {p}：{len(imp):,} 筆，新增 {add:,}，更新 {upd:,}")

    if not a.no_api:
        if not a.key:
            print("沒有 API 授權碼：請用 --key 或環境變數 CWA_API_KEY（opendata.cwa.gov.tw 免費註冊）", file=sys.stderr)
            return 2
        recs = fetch_api(a.key, a.station)
        new = {r["ts"]: r for r in recs}
        rows, add, upd = merge(rows, new)
        valid = sum(1 for r in recs if r["H"] is not None)
        print(f"API 回傳 {len(recs):,} 筆（{min(new)}–{max(new)}，有效波高 {valid:,}），新增 {add:,}，更新 {upd:,}")

    if a.no_api and not a.import_files:
        print("沒有指定 --import 又加了 --no-api，沒事可做")
        return 0
    write_csv(out, rows, a.station)
    print(f"已寫入 {out}：共 {len(rows):,} 筆，{datetime.now():%Y-%m-%d %H:%M}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
