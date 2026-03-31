`mp_Make-Tools` 是一個獨立的「MicroPython 韌體建置工具庫」。

你的專案（firmware repo）負責放：

- `lib/micropython`（MicroPython 原始碼，通常是 git submodule）
- （可選）你的 `USER_C_MODULES`、要 freeze 的 Python 檔案/資料夾、板子設定等

而 `mp_Make-Tools` 只負責：

- 產生 `build/manifest.py`
- 統一呼叫 `make -C lib/micropython/ports/<target> ...`

這樣就能把你喜歡的 `python3 make.py` 使用體驗從 `lvgl_micropython` 解綁出來，放進你自己的專案流程中。

## 基本用法

在你的 firmware repo 內（repo 根目錄要有 `lib/micropython`）：

```bash
python3 /path/to/mp_Make-Tools/make.py unix
```

指定專案路徑（從任何位置執行都可）：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware unix
```

如果不指定 `--project-dir`，預設會使用「目前工作目錄（cwd）」當作專案根目錄。

指定 port 參數（全部原樣透傳給 MicroPython 的 make）：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware esp32 BOARD=ESP32_GENERIC
```

ESP32 也可以直接用 chip 當 target（會自動等同 `esp32` 並設定 `--esp-idf-chips`）：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware esp32s3 BOARD=ESP32_GENERIC_S3
```

## 只生成 manifest（不編譯）

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware --manifest-only unix
```

會輸出 `build/manifest.py` 的完整路徑。

## 設定檔（config.json）

你可以在 firmware repo 根目錄放一個設定檔（支援以下檔名，會自動依序尋找）：

- `mp_make_tools.config.json`
- `mp_make_tools.json`
- `config.json`

或用 `--config /path/to/config.json` 指定。

範例可參考：[config.example.json](file:///c:/Users/bl91920/Documents/code/git/lvgl_micropython/mp_Make-Tools/config.example.json)

### 參數一致性檢查

工具每次執行都會將「config.json」與「CLI 參數」做一致性比對；若兩邊同一欄位都填了但值不同：

- 預設：輸出 WARN 並以 CLI 優先
- 嚴格模式：直接失敗（`--strict-config` 或 `build.strict=true`）

### 版本固定（MicroPython / ESP-IDF）

- MicroPython：可用 `micropython.ref`（或 `--micropython-ref`）固定到 tag/branch/commit。\n  若與現況不一致會 WARN；配合 `--sync` 或 `--fetch` 可自動 checkout。
- ESP-IDF：可用 `esp_idf.version`（或 `--esp-idf-version`）固定到 tag/branch/commit。\n  ESP-IDF 需要遞迴 submodule，本工具在 `--fetch/--sync` 時會自動 `--recursive`。

### exmod（USER_C_MODULES）

如果你希望用「清單」決定要加入哪些 user C modules，可以在 config 放：

- `exmod.root`：例如 `ext_mod`
- `exmod.list`：例如 `\"/lcd_bus/micropython.cmake\"`、`\"/lcd_utils/micropython.cmake\"`

執行時會把它們組成 `USER_C_MODULES`（多個時用 `;` 串接）。你也可以用 CLI 逐一加入：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware \
  --exmod-root ext_mod \
  --exmod /lcd_bus/micropython.cmake \
  --exmod /lcd_utils/micropython.cmake \
  esp32 BOARD=ESP32_GENERIC
```

## 自動下載（fetch）

如果你的 firmware repo 還沒有把 source 拉下來，工具可以幫你：

- 下載 MicroPython（預設放在 `lib/micropython`）
- 針對 `esp32` 下載 ESP-IDF（預設放在 `lib/esp-idf`，並在編譯時自動帶入 `IDF_PATH`）

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware --fetch esp32 BOARD=ESP32_GENERIC
```

自訂下載來源或路徑：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware \
  --fetch \
  --micropython-url https://github.com/micropython/micropython \
  --esp-idf-url https://github.com/espressif/esp-idf \
  --esp-idf-dir /path/to/firmware/lib/esp-idf \
  esp32 BOARD=ESP32_GENERIC
```

如果你的 repo 已經用 git submodule 定義了 `lib/micropython`/`lib/esp-idf`，`--fetch` 會優先用 submodule 更新；沒有 submodule 才會用 `git clone --depth=1`。

ESP-IDF 版本建議（MicroPython 推薦）：`v5.5.1`（也支援 `v5.3`、`v5.4`、`v5.4.1`、`v5.4.2`）。可用：

- `--esp-idf-version v5.5.1`
- 或寫在 `config.json` 的 `esp_idf.version`

## ESP-IDF 環境（install/export）

ESP32 建置通常需要先跑一次（只需一次）：`./install.sh esp32`，並在每個新 shell session 做：`source export.sh`。

工具提供幾個選項：

- `--idf-install`：在 `lib/esp-idf` 存在時，嘗試執行 `./install.sh <chips>`（chips 來源：`--esp-idf-chips` 或 `config.json` 的 `esp_idf.chips`）
- （預設）ESP32 編譯時會自動 `source $IDF_PATH/export.sh` 再執行 `make ...`（避免 `idf.py: command not found`）
- `--no-idf-export`：關閉上述行為（不建議，除非你已自行處理好 ESP-IDF 環境）
- `--idf-export`：強制啟用上述行為（兼容舊用法）

範例：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware \
  --fetch --idf-install --idf-export \
  esp32 BOARD=ESP32_GENERIC
```

## 建置前自動 clean

為了確保建置乾淨，工具預設每次建置都會先執行一次 `make clean` 再開始編譯。

- `--no-clean`：關閉自動 clean（不建議，除非你很確定需要加速增量編譯）

## 自動檢查/安裝提示（doctor）

只檢查並輸出缺少的指令與安裝建議：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware --doctor esp32
```

在 Linux/macOS 嘗試自動安裝（能做的就做，不能做就提示指令）：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware --doctor --install esp32
```

在真正建置時也可以加上 `--install`，若偵測到缺少必要指令會嘗試自動安裝（需要特殊權限時會提示你該用什麼指令安裝）：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware --install esp32 BOARD=ESP32_GENERIC
```

預設在真正編譯前會自動跑一次 doctor；若你想跳過：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware --no-doctor esp32 BOARD=ESP32_GENERIC
```

## 輸出韌體檔案（ESP32）

ESP32 建置成功後，工具會自動把 `firmware.bin` 改名複製到你的專案 `build/` 目錄下：

- 預設檔名：等同 `target` 參數（例如 `esp32s3` 會輸出 `build/esp32s3.bin`）
- `--name <name>`：指定輸出檔名（優先於其他）
 - 若檔名重複：自動加上 `_YYYY_MM_DD_HH_MM_SS` 避免覆蓋（例如 `esp32s3_2026_04_01_12_30_45.bin`）

範例：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware --name my_firmware esp32s3 BOARD=ESP32_GENERIC_S3
```

## Freeze 與額外 manifest

額外 include 其他 manifest：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware \
  --include-manifest /abs/path/to/extra_manifest.py \
  unix
```

Freeze 單一檔案：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware \
  --freeze-file /abs/path/to/main.py \
  unix
```

Freeze 整個資料夾：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware \
  --freeze-dir /abs/path/to/frozen_pkg \
  unix
```

遞迴 freeze 資料夾：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware \
  --freeze-dir-recursive /abs/path/to/frozen_pkg \
  unix
```

## USER_C_MODULES

把你的 C 擴充模組（usermod）掛進來：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware \
  --user-c-modules /abs/path/to/usermod \
  esp32 BOARD=ESP32_GENERIC
```

## 備註

- `build/manifest.py` 一律由工具產生，並以 `FROZEN_MANIFEST=...` 傳給 MicroPython build。
- Windows：目前工具只保證 `--manifest-only` 可用；實際編譯仍建議在 Linux/macOS 環境進行。
