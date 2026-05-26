# 7-11 工單圖檔自動改名

[English README](README.md)

把每天從 7-11 拍回來的紙本工單照片，用 Claude 視覺 API 自動辨識手寫欄位、
依規則改檔名歸檔。原本每天要花 30 分鐘人工整理的事，現在雙擊就跑完。

## 解決的痛點

技術員一整天在外面拍紙本工單，回家要把照片依下面這個固定格式歸檔，
之後才能依日期、門市、維修號碼搜尋：

```
{mmdd} 7-11{門市}({故障叫修} {修護內容詳細}){維修號碼}.jpg
```

範例：

```
0407 7-11同華(單杯)91430773.jpg
0403 7-11水龍吟(中WB不熱 32mm1 電磁閥1)91431308.jpg
```

這五個欄位散落在工單上五個不同位置，又是手寫中文+英文料件代碼混雜，
日期還用民國年。**一張一張手動改名是真實的瓶頸。**

## 怎麼運作

1. **掃描**指定資料夾下的 `.jpg / .jpeg / .png`。
2. **送圖** 給 Claude（`claude-haiku-4-5`），附上結構化 JSON 提示詞，
   要它回傳五個欄位：店章日期、門市名稱、故障叫修、修護內容（料件+數量）、維修號碼。
3. **解析 + 驗證** 回傳的 JSON，民國年轉成 MMDD，去掉空白與檔案系統禁用字元。
4. **組檔名** → 搬到 `done/`。重複檔名加 `-2`、`-3` 後綴。任何步驟失敗的原檔搬到 `error/`，等人工檢查。
5. **追加 log**（`rename_log.txt`），可回查模型每張圖的辨識結果。

整支工具是**單檔 Python 腳本、零第三方套件**，只用標準函式庫
（`urllib`、`tkinter` ...）。

## 為什麼適合放作品集

- **真實上線情境**：每天有非技術背景的使用者在用，不是 demo。
- **視覺 LLM 當 OCR + 分類器**：模型不只是抄文字，還要在表單上「定位欄位」、
  分辨同一張表單上兩串紅色八位數哪一個才是「維修號碼」、選擇手寫的中文料件名而不是同一列的印刷 SKU 代碼。
- **防呆輸出處理**：嚴格解析 JSON、驗證民國年格式、檢查必要欄位、失敗一律隔離不要硬猜。
- **跨平台、無相依**：Windows / macOS / Linux 都跑得起來，Python 3.7+ 內建即可，無需 `pip install`。
  有 Tkinter 資料夾選擇器給不開終端機的人。
- **使用者端打包**：附上 macOS `.command` 雙擊啟動器，操作者連終端機都不用碰。

## 快速開始

### 1. 裝 Python

Python 3.7 以上。
Windows 10/11 可在 Microsoft Store 搜尋 Python 安裝；macOS 內建 `/usr/bin/python3`。

### 2. 申請 Anthropic API key

到 <https://console.anthropic.com/settings/keys> 申請，會以 `sk-ant-` 開頭。

### 3. 設定 key

```bash
# macOS / Linux（永久）
echo 'ANTHROPIC_API_KEY=sk-ant-你的key' > ~/.workorder_rename.conf
chmod 600 ~/.workorder_rename.conf
```

```cmd
:: Windows（cmd，跑一次後要重開新的 cmd 才生效）
setx ANTHROPIC_API_KEY "sk-ant-你的key"
```

### 4. 執行

```bash
# 跳資料夾選擇視窗
python rename_workorder.py

# 指定資料夾
python rename_workorder.py --folder "/path/to/workorders"

# 試跑（不實際搬檔）
python rename_workorder.py --folder "/path/to/workorders" --dry-run
```

macOS 也可以雙擊 `run_rename.command` 直接跑，不用開終端機。

## 跑完之後的資料夾結構

```
workorders/
├── (新拍的工單圖丟這裡)
├── done/                    ← 改名成功的歸檔
├── error/                   ← 辨識失敗或必要欄位缺失
└── rename_log.txt           ← append-only 紀錄檔
```

## 完整命名規則

```
{mmdd} 7-11{門市}({故障叫修} {料件1}{數量1} {料件2}{數量2}...){維修號碼}.jpg
```

| 變數         | 來源欄位                                          | 範例 |
| ------------ | ------------------------------------------------- | ---- |
| `mmdd`       | 右下角門市店章（民國年.月.日 → MMDD）             | 115.4.07 → `0407` |
| `門市`       | 「門市名稱」手寫欄位                              | `同華` |
| `故障叫修`   | 「故障叫修」手寫欄位                              | `單杯` |
| `料件{數量}` | 「修護內容」表格每列，多列用空格串接              | `32mm1 電磁閥1` |
| `維修號碼`   | 右上角紅字八位數「維修號碼」                      | `91430773` |

細節：

- `{mmdd}` 後接**半形空格**（不是 hyphen）；`7-11` 內部還是 hyphen。
- 修護內容空白時，括號內只放故障叫修。
- 多列修護內容用空格分隔。
- 料件名取手寫中文，不要取印刷的 SKU 代碼（例如取 `銅插頭` 而不是 `EVER-103743-LC`）。

## 成本估算

用 Claude Haiku 4.5、工單照片約 1500×1000 像素估：

- 每張約 1,500 input tokens + 200 output tokens ≈ **US$0.006**
- 一天 30 張 ≈ **US$0.18**（約 NT$6）
- 一個月 ≈ **US$5.40**（約 NT$180）

辨識失敗也不會多燒 API，因為大多數失敗是在 API 回應後的 JSON 解析或欄位驗證階段被擋下。

## 已知容易誤判

手寫辨識會錯。下列詞遇到時要人工確認：

| 正確 | 曾被誤讀為 |
| --- | --- |
| 單杯 | 不出菜 |
| 不出水 | 不出立 |
| 電磁閥 | 電池閥 |
| 長業 | 義美 / 葉美 |

另外：

- **維修號碼**是右上角**紅色**的八位數，不要跟「叫修編號」「序號」「故障代碼」搞混。
- **日期**一律用右下角**門市店章**，不是叫修時間、不是完成時間。

## 專案結構

```
workorder-image-renamer/
├── README.md                ← 英文版
├── README.zh-TW.md          ← 本檔
├── LICENSE                  ← MIT
├── .gitignore
├── rename_workorder.py      ← 主程式
└── run_rename.command       ← macOS 雙擊啟動器
```

## 授權

MIT — 詳見 [LICENSE](LICENSE)。
