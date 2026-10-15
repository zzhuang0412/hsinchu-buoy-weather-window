# 天候窗計算器 × 新竹浮標自動更新：評估與交接

## 結論

**要自動用新竹浮標資料，資料抓取這一段交給 Claude Code（跑在 GitHub Actions 上），計算器本身不用改。**
但先講清楚一件事：自動化只能補「最近 30 天」的滾動資料；月窗口統計真正需要的 10–20 年歷史，
得一次性從氣象署海象網站用瀏覽器下載再匯入。所以是「一次手動 + 之後全自動」。

### 為什麼不留在這裡（Claude 雲端排程）做

1. 這裡的 shell 連不到 `opendata.cwa.gov.tw`（出站只放行套件庫），已實測回 403。
2. 這裡能用的網頁讀取工具回來的是摘要，不是原始 JSON；30 天 × 24 小時 = 720 筆逐時數值沒辦法原樣帶回，也存不成檔。
3. 計算器 artifact 的安全政策不允許頁面自己去外部抓資料，所以就算抓到，也得重新發布整個頁面。

### 為什麼放 GitHub Actions，而不是你的電腦

- 不用電腦開著；每週跑十幾秒，免費額度綽綽有餘。
- 資料進 repo 有版本紀錄；GitHub Pages 自動更新頁面，網址固定。
- 備案：Windows 工作排程器每週跑同一支腳本，再把 CSV 載入計算器（README 有指令）。

### 自動化給得了、給不了的

| | 來源 | 怎麼取得 | 用途 |
|---|---|---|---|
| 近 30 天逐時 | 開放資料 O-B0075-002（JSON，需免費授權碼） | 每週一 06:40 Actions 自動抓、合併 | 把紀錄從現在起接成連續序列；go/no-go 分頁看近況 |
| 2000 年起歷史逐時 | ocean.cwa.gov.tw 海象觀測資料查詢（CSV） | 一次性瀏覽器下載（下載連結有簽章，不好自動化） | 月窗口統計的主體 |

單位差異腳本已處理：API 波高 m → cm；歷史檔週期 0.1 s → s；缺值（`None`、`-`、0、離譜值）→ 空。

## 交接包內容

```
cwa-buoy-handoff/
├── HANDOFF.md                        本文件
├── README.md                         repo 說明（設定步驟、格式）
├── .github/workflows/cwa-buoy.yml    每週一 06:40 台北自動跑（週日 22:40 UTC）
├── scripts/fetch_cwa_buoy.py         抓 API、合併、--import 歷史檔；純標準函式庫
├── scripts/build_page.py             CSV + 範本 → docs/index.html
├── template/weather_window_template.html   由現有計算器改成的範本（只換了資料與說明文字，計算邏輯原封不動）
├── data/46757B_hourly.csv            起始資料：2023 年 8,760 小時（就是 artifact 內建那份）
└── docs/index.html                   已用 2023 資料預先建好一版，可直接看
```

已在這裡驗證過：解析器對實測的 API 結構（`Result.Records.SeaSurfaceObs.Location[].StationObsTimes.StationObsTime[]`）
正確；歷史格式匯入、合併、建頁都跑過，建出的頁面與現有計算器一模一樣。
唯一沒在這裡跑到的是真正呼叫 API（網路被擋），所以交接指令第 4 步要 Code 先在本機跑一次。

## 給 Claude Code 的指令（整段貼上）

```
我把「cwa-buoy-handoff」資料夾放在這個目錄。請照 HANDOFF.md 和 README.md 把它變成一個會自動更新的 GitHub repo：

1. 先讀 HANDOFF.md、README.md、scripts/ 兩支腳本，不要改 template/ 裡的計算邏輯。
2. 在這個資料夾 git init，用 gh 建私有 repo「hsinchu-buoy-weather-window」，推上 main。
3. 我等一下會貼氣象署 API 授權碼給你；用 `gh secret set CWA_API_KEY` 設定，不要寫進任何檔案或 commit。
4. 本機先跑一次：
   python scripts/fetch_cwa_buoy.py --csv data/46757B_hourly.csv
   python scripts/build_page.py
   確認 API 真的回傳新竹浮標（46757B）最近 30 天資料並合併，docs/index.html 的資料按鈕顯示「新竹浮標 2023–2026」。
   如果 API 的 JSON 結構和腳本註解寫的不同，修 _parse_record / fetch_api，其他不動。
5. commit、push，然後 `gh workflow run cwa-buoy.yml` 手動觸發一次，確認 Actions 成功並有 commit。
6. 開 GitHub Pages：Settings → Pages，Source 選 Deploy from a branch、main、/docs（用 gh api 設也行），回報網址。
7. 之後我會給你從 ocean.cwa.gov.tw 下載的歷史 CSV（一年一檔）；用
   python scripts/fetch_cwa_buoy.py --no-api --import <檔案...>
   匯入後重建頁面並 commit。
全程用繁體中文回報；每步做完告訴我結果再往下。
```

## 你要親自做的三件事

1. **申請授權碼**：https://opendata.cwa.gov.tw 註冊 → 會員中心 → API 授權碼（免費），貼給 Code 設 secret。
2. **下載歷史資料**：https://ocean.cwa.gov.tw 海象觀測資料查詢 → 新竹浮標 → 波浪逐時 → 依允許區間分批下載 CSV（2000 年起），交給 Code 匯入。
3. **Pages 網址**出來後，貼到課程網站或講義；artifact 版的計算器（示範 2023）照舊留在課堂用。

## 之後

- 每週一早上 Pages 頁面就是最新的；「自己的 CSV」功能仍在，臨時分析別的測站也可以。
- 如果希望 artifact 版也換成多年資料，把 `data/46757B_hourly.csv` 丟給我，我重新發布一版即可。
- 想加其他測站（例如七美、龍洞或新竹外海的離岸風場浮標）只要改 `--station`，再複製一份工作流程。
