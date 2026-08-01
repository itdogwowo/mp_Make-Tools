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

你也可以把 `target` 寫進設定檔（`build.target`），讓日常使用只剩「固定 python 版本」這個差異：

```bash
python3.12 /path/to/mp_Make-Tools/make.py
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
- `make_config.json`
- `make_config.example.json`
- `config.json`
- `config.example.json`

或用 `--config /path/to/config.json` 指定。

如果你的 firmware repo 沒有放設定檔，工具會退回讀取 `mp_Make-Tools` repo 內的預設設定（優先 `config.json`，其次 `config.example.json`）。

第一次執行時，如果完全找不到任何設定檔，工具會自動從 `make_config.example.json`（或 `config.example.json`）複製一份到 `project-dir/make_config.json` 讓你直接修改。

範例可參考：`mp_Make-Tools/make_config.example.json`

### git_manage

如果你希望把「repo 來源/版本（tag/ref）」集中管理在 git 設定檔，可以在 `make_config.json` 設定：

- `git_manage`: `"git_config.json"`

此時 `make.py` 每次執行都會先跑一次 git manager（依 git 設定檔下載/同步 repo、checkout 到指定 ref、更新 submodules、收集 tags/branch 資訊），再開始 build。

`make.py` 會優先從 git 設定檔取得：

- `micropython` 對應 repo 的 `dir/url/ref`
- `esp_idf` 對應 repo 的 `dir/url/ref`（會對應到 build 端的 `esp_idf.version`）

CLI 參數仍然具有最高優先權。

### Git 設定檔（git_config.json）

Git 相關操作（下載/同步 repo、列出 tag、把版本資訊寫回 config）已獨立成 `git.py`。
設定檔支援以下檔名（依序尋找）：

- `mp_make_tools.git_config.json`
- `mp_make_tools.git.json`
- `git_config.json`
- `git_config.example.json`

範例可參考：`mp_Make-Tools/git_config.example.json`

第一次執行時，如果完全找不到任何 git 設定檔，工具會自動從 `git_config.example.json` 複製一份到 `project-dir/git_config.json` 讓你直接修改。

建議使用 `repos` 清單格式（可同時管理多個 repo）：

```json
{
  "repos": [
    {
      "name": "mp_Make-Tools",
      "enabled": true,
      "force_reset": false,
      "dir": ".",
      "url": "https://github.com/itdogwowo/mp_Make-Tools.git",
      "ref": "main",
      "recursive": false
    }
  ],
  "tags_limit": 30,
  "list_wrap": 3,
  "write_detected_to": null,
  "update_detected_on_fetch": false,
  "require_clean": false,
  "strict_ref": false
}
```

欄位說明：

- `list_wrap`: 每行顯示幾個項目（例如 tags/branches；預設 3）
- `repos[].enabled`: 是否啟用此 repo（預設 true；可用來暫時關閉某些 repo）
- `repos[].force_reset`: true 時，會丟棄 repo 內所有未提交變更並刪除未追蹤檔案/資料夾（`git reset --hard` + `git clean -fd`）；完成後會自動把該 repo 的 `force_reset` 寫回 `false`（一次性）
- `repos[].recursive`: 是否同步 submodules（`true` 會做 `submodule update --init --recursive`）
- `require_clean`: true 時，若 repo 工作目錄有未提交變更會直接失敗（避免更新被 git 擋下卻沒注意）
- `strict_ref`: true 時，ref 找不到或 checkout/submodule 失敗會直接失敗（避免只顯示 WARN）
- `write_detected_to`: 寫回 `detected.*` 的目標檔案；設 `null` 代表不寫回
- `update_detected_on_fetch`: true 時，執行 `--fetch/--sync` 後會自動寫回 `detected.*`；注意這只負責「記錄目前狀態」，不代表一定會切到最新

「是否追最新」由各 repo 的 `ref` 決定：

- `ref: "main"`（或其他分支名）：**每次執行都會 fetch 遠端並硬 reset 到該分支最新**（本地未提交變更與未追蹤檔案會被剷除）
- `ref: "vX.Y.Z"` 或 commit hash：固定版本，每次執行 fetch 後 reset 到該固定點（等於鎖版本，可輸入 commit 唯一 ID 精確固定）
- `ref: null`：不強制 checkout 到特定 ref，只做既有 repo 的同步/偵測

> 有指定 `ref`（分支或 tag/commit）的 repo，每次執行都會硬 reset 到該 ref 的最新狀態，方便每次重新拉最新。要固定版本就選 tag 或直接填 commit hash。

`force_reset` 不是更新最新的必要條件；只有在本地有未提交修改、導致 checkout 被 git 拒絕時才需要啟用（一次性，用完自動寫回 false）。

執行順序：

- `repos` 中 `dir="."` 的項目會自動優先處理（即使不在陣列第一個）
- 其他 repo 依清單順序處理

### mp_Make-Tools 自我更新（跟到 main 最新）

`git.py` 可用 `repos` 清單同步任意 repo（包含 mp_Make-Tools 自己）。只要把目標 repo 設為 `dir="."` 與 `ref="main"`，就能把本 repo 同步到 `origin/main` 最新。

在 mp_Make-Tools repo 根目錄執行：

```bash
python3 git.py --sync
```

注意：如果工作目錄有未提交變更、或本地分支 checkout 需要覆蓋檔案，git 可能會拒絕切換/更新；這種情況需要你先 commit/stash/清乾淨再同步。

### 參數一致性檢查

工具每次執行都會將「config.json」與「CLI 參數」做一致性比對；若兩邊同一欄位都填了但值不同：

- 預設：輸出 WARN 並以 CLI 優先
- 嚴格模式：直接失敗（`--strict-config` 或 `build.strict=true`）

### 版本固定（MicroPython / ESP-IDF）

- MicroPython：可用 `repos` 裡 `name="micropython"` 的 `ref`（或 `--micropython-ref`）固定到 tag/branch/commit。若與現況不一致會 WARN；配合 `--sync` 或 `--fetch` 可自動 checkout。
- ESP-IDF：可用 `repos` 裡 `name="esp_idf"` 的 `ref`（或 `--esp-idf-version`）固定到 tag/branch/commit。ESP-IDF 通常需要 `recursive=true` 以同步 submodules。

### exmod（USER_C_MODULES）

如果你希望用「清單」決定要加入哪些 user C modules，可以在 config 放：

- `exmod.root`：例如 `ext_mod`
- `exmod.list`：例如 `\"/lcd_bus/micropython.cmake\"`、`\"/lcd_utils/micropython.cmake\"`

例如：

```json
{
  "exmod": {
    "root": "ext_mod",
    "list": [
      "/mp_jpeg/micropython.cmake",
      "/mp_heap_caps/micropython.cmake"
    ]
  }
}
```

執行時會把它們組成 `USER_C_MODULES`（多個時用 `;` 串接）。你也可以用 CLI 逐一加入：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware \
  --exmod-root ext_mod \
  --exmod /lcd_bus/micropython.cmake \
  --exmod /lcd_utils/micropython.cmake \
  esp32 BOARD=ESP32_GENERIC
```

### build.target（預設 target）

如果你希望日常只執行 `python3.12 make.py`，可以把 target 寫進設定檔：

- `build.target`：例如 `esp32s3`、`esp32p4`、`unix`

### esp32.make.vars（ESP32 make 變數）

ESP32 port 的一些選項通常是用 `make` 變數傳入（例如 `BOARD`、`BOARD_VARIANT`）。你可以集中寫在設定檔，避免每次重打：

- `esp32.make.vars`：例如 `{ "BOARD": "...", "BOARD_VARIANT": "..." }`
- 規則：如果命令列有同名 `KEY=VALUE`，命令列優先；否則才會從設定檔補上

#### ESP32_GENERIC_P4 的 Wi-Fi/BLE 變體

`ESP32_GENERIC_P4` 依板子是否帶外掛 Wi-Fi/BLE 協處理器（ESP32-C5/ESP32-C6）而有不同變體：

- 純 ESP32-P4（不使用協處理器）：不設定 `BOARD_VARIANT`
- 外掛 ESP32-C5（Wi-Fi/BLE）：`BOARD_VARIANT=C5_WIFI`
- 外掛 ESP32-C6（Wi-Fi/BLE）：`BOARD_VARIANT=C6_WIFI`

### esp32.idf_component.dependencies（ESP-IDF component 依賴）

若你的 user C module 需要額外的 ESP-IDF component（例如 `espressif/esp_new_jpeg`），可用設定檔自動補到 `ports/esp32/main/idf_component.yml`：

- `esp32.idf_component.dependencies`：例如 `{ "espressif/esp_new_jpeg": "^1.0.0" }`

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

### 將目前版本與 tag 寫回 config（方便複製）

你可以在下載/同步後，用獨立的 git 工具把「目前 checkout 的版本」與「近期 tags」寫回你的 config，讓你快速複製要鎖定的 tag/version：

```bash
python3 /path/to/mp_Make-Tools/git.py --project-dir /path/to/firmware \
  --fetch --write-detected
```

會寫入（或更新）`detected.*` 欄位，例如：

- `detected.micropython.head` / `detected.micropython.describe`
- `detected.micropython.tags_at_head` / `detected.micropython.recent_tags`
- `detected.esp_idf.*`

預設會更新 `project-dir/config.json`（若不存在則建立）。

如果你希望每次 `--fetch` 都自動更新，可以在 `git_config.json` 設定 `update_detected_on_fetch=true`。

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

- 預設檔名（由高到低）：`--name` → 設定檔 `output.name` → `BOARD[_BOARD_VARIANT]` → `target` → `firmware`
 - 若檔名重複：自動加上 `_YYYY_MM_DD_HH_MM_SS` 避免覆蓋（例如 `esp32s3_2026_04_01_12_30_45.bin`）

範例：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware --name my_firmware esp32s3 BOARD=ESP32_GENERIC_S3
```

## ESP32 分割表自動調整（factory-only）

如果你希望「永遠用兩段式建置」來最大化 `vfs` 分區（檔案系統空間），可以啟用分割表自動調整：

- 第一次建置：先取得 `micropython.bin` 的實際大小（即使封裝失敗也沒關係，只要 `micropython.bin` 已生成）
- 第二次建置：依據第一次的 `micropython.bin` 大小重寫 `partitions.csv`，讓 `factory` 分區剛好放得下 app，`vfs` 吃掉剩餘空間，最後封裝成功

設定檔（建議）：

```json
{
  "build": {
    "target": "esp32s3"
  },
  "esp32": {
    "partition": {
      "auto": true,
      "flash_mb": 4,
      "app_margin_kb": 0
    },
    "idf_component": {
      "dependencies": {
        "espressif/esp_new_jpeg": "^1.0.0"
      }
    },
    "make": {
      "vars": {
        "BOARD": "ESP32_GENERIC_S3",
        "BOARD_VARIANT": "SPIRAM_OCT"
      }
    }
  }
}
```

CLI 也可覆寫：

```bash
python3 /path/to/mp_Make-Tools/make.py --project-dir /path/to/firmware \
  --esp32-partition-auto --esp32-flash-mb 4 --esp32-app-margin-kb 0 \
  esp32 BOARD=ESP32_GENERIC
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

## 致謝 (Acknowledgements)

本工具的設計靈感與部分編譯流程參考自 [lvgl_micropython](https://github.com/lvgl/lvgl_micropython) 以及官方 [MicroPython](https://github.com/micropython/micropython) 的建置生態，特此致謝。
