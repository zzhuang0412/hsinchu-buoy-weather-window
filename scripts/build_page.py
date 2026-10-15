#!/usr/bin/env python3
"""
把長期合併 CSV 烤進天候窗計算器的頁面範本，產出可直接放 GitHub Pages 的單一 HTML。

    python build_page.py --csv data/46757B_hourly.csv --template template/weather_window_template.html --out docs/index.html

範本裡的佔位符：
    __HS_CM__        逐時示性波高 (cm)，逗號分隔，從 __START_YEAR__ 年 1 月 1 日 00:00（台北時間）起每小時一值，-1 = 缺測
    __START_YEAR__   第一年
    __LABEL__        資料集名稱（按鈕與圖例用）
    __FOOTER_NOTE__  頁尾的資料說明（期間、完整率、更新時間）
只用標準函式庫。
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_cwa_buoy import read_csv  # noqa: E402


def hourly_series(rows: dict[str, dict]) -> tuple[int, int, list[int]]:
    """從第一年 1/1 00:00 到最後一年 12/31 23:00，每小時一格；缺測 -1。"""
    years = sorted({int(ts[:4]) for ts in rows})
    y0, y1 = years[0], years[-1]
    start = datetime(y0, 1, 1)
    end = datetime(y1 + 1, 1, 1)
    n = int((end - start).total_seconds() // 3600)
    hs = [-1] * n
    for ts, r in rows.items():
        if r["H"] is None:
            continue
        t = datetime(int(ts[:4]), int(ts[4:6]), int(ts[6:8]), int(ts[8:10]))
        k = int((t - start).total_seconds() // 3600)
        if 0 <= k < n:
            hs[k] = int(r["H"])
    return y0, y1, hs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="data/46757B_hourly.csv")
    ap.add_argument("--template", default="template/weather_window_template.html")
    ap.add_argument("--out", default="docs/index.html")
    ap.add_argument("--name", default="新竹浮標", help="資料集名稱前綴")
    a = ap.parse_args()

    rows = read_csv(Path(a.csv))
    if not rows:
        raise SystemExit(f"{a.csv} 沒有資料")
    y0, y1, hs = hourly_series(rows)
    valid = sum(1 for v in hs if v >= 0)
    cov = valid / len(hs)
    last_ts = max(ts for ts, r in rows.items() if r["H"] is not None)
    last = f"{last_ts[:4]}-{last_ts[4:6]}-{last_ts[6:8]} {last_ts[8:10]}:00"
    label = f"{a.name} {y0}" if y0 == y1 else f"{a.name} {y0}–{y1}"
    span = f"{y0}" if y0 == y1 else f"{y0}–{y1}"
    footer = (
        f"內建資料：中央氣象署新竹浮標（46757B）{span} 年逐時示性波高，離岸約 6.4 km、水深約 22 m，"
        f"共 {len(hs):,} 小時、完整率 {cov:.0%}，最後一筆 {last}（台北時間）。"
        f"來源：氣象署開放資料 O-B0075-002 每週自動合併，加上一次性匯入的歷史觀測；"
        f"頁面由 GitHub Actions 於 {datetime.now():%Y-%m-%d %H:%M} UTC 重建。近岸測站的統計用於場址前仍需換算。"
    )

    tpl = Path(a.template).read_text(encoding="utf-8")
    for key in ("__HS_CM__", "__START_YEAR__", "__LABEL__", "__FOOTER_NOTE__"):
        if key not in tpl:
            raise SystemExit(f"範本缺少佔位符 {key}")
    html = (tpl.replace("__HS_CM__", ",".join(map(str, hs)))
               .replace("__START_YEAR__", str(y0))
               .replace("__LABEL__", label)
               .replace("__FOOTER_NOTE__", footer))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{out}：{len(html)/1e6:.2f} MB，{label}，{valid:,}/{len(hs):,} 小時有效（{cov:.1%}），最後一筆 {last}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
