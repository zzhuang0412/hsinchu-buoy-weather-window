# 新竹浮標 × 天候窗計算器：自動更新 repo

每週一清晨從中央氣象署開放資料抓新竹浮標（46757B）最近 30 天的逐時波浪觀測，
合併進一個長期 CSV，再把資料烤進天候窗計算器頁面，發布到 GitHub Pages。

```
.
├── .github/workflows/cwa-buoy.yml   每週一 06:40（台北）自動跑；也可手動 Run workflow
├── scripts/fetch_cwa_buoy.py        抓 O-B0075-002 → 合併 data/46757B_hourly.csv；--import 匯入歷史檔
├── scripts/build_page.py            CSV + 範本 → docs/index.html
├── template/weather_window_template.html   計算器範本（含 __HS_CM__ 等佔位符）
├── data/46757B_hourly.csv           長期逐時資料（已內含 2023 年 8,760 小時作起始）
└── docs/index.html                  GitHub Pages 發布的頁面（由 Actions 產生，不用手改）
```

只用 Python 標準函式庫，不需要安裝任何套件。

## 一次性設定

1. **API 授權碼**：到 https://opendata.cwa.gov.tw 註冊 → 會員中心 → 取得「API 授權碼」（免費）。
   在 repo 的 Settings → Secrets and variables → Actions 新增 `CWA_API_KEY`。
   本機測試可用 `set CWA_API_KEY=...`（Windows）或 `export CWA_API_KEY=...`。
2. **GitHub Pages**：Settings → Pages → Source「Deploy from a branch」→ Branch `main`、資料夾 `/docs`。
   網址會是 `https://<帳號>.github.io/<repo>/`。
3. **歷史資料（建議，一次就好）**：到 https://ocean.cwa.gov.tw 「海象觀測資料」查詢新竹浮標的波浪逐時資料，
   依站台允許的區間分批下載 CSV（一年一檔即可，2000 年起有資料），然後：

   ```
   python scripts/fetch_cwa_buoy.py --no-api --import 下載\新竹2000.csv 下載\新竹2001.csv ...
   python scripts/build_page.py
   git add data docs && git commit -m "data: 匯入 2000–2025 歷史觀測" && git push
   ```

   歷史檔週期欄若是 0.1 s 單位會自動換算成秒；波高本來就是 cm，不動。

## 每週自動做的事

`cwa-buoy.yml`：抓 API → 合併（同一小時以新資料為準，氣象署會回填修正）→ 重建頁面 → 有變更才 commit。
O-B0075-002 只保留最近 30 天，每週跑一次有四倍餘裕；Actions 連續失敗超過三週才會漏資料。

## 本機手動跑

```
python scripts/fetch_cwa_buoy.py --key <授權碼>          # 抓 30 天並合併
python scripts/build_page.py                             # 產生 docs/index.html
```

Windows 工作排程器備案（不想用 GitHub Actions 時）：
`每週一 07:00` 執行 `python C:\path\scripts\fetch_cwa_buoy.py --key <授權碼> --csv C:\path\data\46757B_hourly.csv`，
再把 CSV 載入計算器的「自己的 CSV」即可。

## CSV 格式

與氣象署「海象觀測資料查詢」匯出的逐時 CSV 相容，天候窗計算器的「自己的 CSV」直接可讀：

```
# 說明列（可有可無）
st,yyyymmddhhmi,H,T,D
46757B,202610022200,180,5.0,11
```

`yyyymmddhhmi` 台北時間；`H` 示性波高 cm；`T` 週期 s；`D` 波向（度）；缺值留空。

## 資料來源

- 中央氣象署開放資料 O-B0075-002「海象監測資料－30 天浮標站監測資料」（JSON；波高 m、週期 s）
- 中央氣象署海象觀測資料查詢 https://ocean.cwa.gov.tw （歷史逐時 CSV；波高 cm）
- 新竹浮標 46757B：離岸約 6.4 km、水深約 22 m
