# ports/ — 建置組合 preset

這裡有**兩個正交的維度**，不要混在一起：

| 維度 | 檔案位置 | 描述什麼 | 切換成本 |
|---|---|---|---|
| **板子組合**（preset） | `ports/<名稱>/make_config.json` | BOARD / VARIANT / sdkconfig | **便宜**（只換編譯設定） |
| **來源版本**（stack） | `ports/_stacks/<名稱>.json` | MicroPython / ESP-IDF / lv_binding 的 ref | **貴**（會重新 checkout，IDF 跨版是數 GB） |

5 個 preset × 3 個 stack = 15 種組合 —— 但只需要 8 個檔案，因為它們是正交的。

---

## 用法

**從專案根目錄執行**（`--config` 是相對於當前工作目錄解析的）。

```bash
cd <mp_Make-Tools 根目錄>

python3 make.py --config ports/s3-quad/make_config.json
python3 make.py --config ports/s3-oct/make_config.json
python3 make.py --config ports/s31/make_config.json
python3 make.py --config ports/s31-psram250/make_config.json
python3 make.py --config ports/s31-psram200/make_config.json
```

產物落在 `build/<output.name>.bin`（同名檔已存在時會自動加時間戳，不會覆蓋）。

### 切換來源版本（stack）

```bash
cp ports/_stacks/stack-idf6-pr2.json git_config.json     # 目前唯一實測可用的
cp ports/_stacks/stack-idf6-pr1.json git_config.json     # 只有 IDF v6 相容層（S3 only）
cp ports/_stacks/stack-idf5-orig.json git_config.json    # 改造前的原始基準
```

> `_stacks/*.json` 是**範本**，平常不會被動到。工具跑完會把**根目錄那份**的
> `force_reset` 寫回 `false`（那是它的設計：一次性強制重置），範本保持原樣。

---

## 板子 preset 總表

| preset | BOARD | VARIANT | target | flash | PSRAM | CPU |
|---|---|---|---|---|---|---|
| `s3-quad` | `ESP32_GENERIC_S3` | — | `esp32s3` | 4 MB（自動） | quad 80 MHz | 240 MHz |
| `s3-oct` | `ESP32_GENERIC_S3` | `SPIRAM_OCT` | `esp32s3` | 4 MB（自動） | octal 80 MHz | 240 MHz |
| `s31` | `ESP32_GENERIC_S31` | — | `esp32s31` | 16 MB（自動） | **無** | 320 MHz |
| `s31-psram250` | `ESP32_GENERIC_S31` | — | `esp32s31` | 16 MB（自動） | octal **250 MHz** | 320 MHz |
| `s31-psram200` | `ESP32_GENERIC_S31` | — | `esp32s31` | 16 MB（自動） | octal 200 MHz | 320 MHz |

---

## ⚠️ 模組 → preset 對照（出貨前一定要核對）

**自動偵測讀的是 board 定義，不是你的模組。** 不確定時用這個確認：

```python
# 燒一版上去，在 REPL 執行
import esp
print(esp.flash_size())     # 16777216 = 16MB, 8388608 = 8MB, 4194304 = 4MB
```

| 模組 | 常用 flash | 該用哪個 preset |
|---|---|---|
| ESP32-S3-WROOM-1 **N4** | 4 MB | `s3-quad` |
| ESP32-S3-WROOM-1 **N8** | 8 MB | `s3-quad` + `--esp32-flash-mb 8` |
| ESP32-S3-WROOM-1 **N16** | 16 MB | `s3-quad` + `--esp32-flash-mb 16` |
| ESP32-S3-WROOM-1 **N8R8** | 8 MB | `s3-oct` + `--esp32-flash-mb 8` |
| ESP32-S3-WROOM-1 **N16R8** | 16 MB | `s3-oct` + `--esp32-flash-mb 16` |
| ESP32-S31（16MB 模組） | 16 MB | `s31` / `s31-psram*`（不需覆寫） |

**方向性很重要：**

- 宣告 **小於** 實際晶片 → ✅ 能開機，只是多出來的 flash 用不到
- 宣告 **大於** 實際晶片 → ❌ **開不了機**，bootloader 會報
  `Detected size smaller than the size in the binary image header. Probe failed.`

所以**不確定就挑小的**。要長期覆寫就在 preset 裡加 `"flash_mb": <N>`（`esp32.partition` 底下）。

---

## flash 大小會自動偵測

**preset 不需要寫 `flash_mb`。** 不指定時，工具會沿著 board 的 `SDKCONFIG_DEFAULTS`
鏈（含 `include()` 與 variant 檔）找 `CONFIG_ESPTOOLPY_FLASHSIZE_<N>MB=y`，
**後者覆蓋前者**，取最後一個：

```
ESP32_GENERIC_S3               →  4 MB   (sdkconfig.base)
ESP32_GENERIC_S31              → 16 MB   (sdkconfig.s31 排在 base 之後)
```

找不到時會印 `WARN: could not detect the flash size from the board; assuming 4MB.`。

要覆寫：`--esp32-flash-mb 8`，或在 preset 裡加 `esp32.partition.flash_mb`。

> ⚠️ 自動偵測很重要：以前不指定會**硬套 4MB**，那會連 `CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y`
> 一起寫進 sdkconfig，**蓋掉 S31 板子自己的 16MB**。

---

## 幾個容易踩的點

1. **`git_manage` 一定要寫。** 省略它不會「fallback 到根目錄的 `git_config.json`」——
   `cli.py` 的 `if cfg.git_manage and not args.no_git_manage:` 會讓 **git manager 整段不執行**，
   於是 ref 不會被 fetch / checkout / 驗證，**pin 直接失效**（樹在錯的 commit 也會照樣編）。
   附帶症狀：因為讀不到 git_config 的 ref，`esp_idf_version` 會落回硬編碼的猜測值，
   每次都印 `WARN: ESP-IDF version mismatch`。

2. **`esp32.sdkconfig` 只認晶片名，沒有 BOARD_VARIANT 這個軸**
   （`cli.py` 的 `_select_project_sdkconfig`）。同一份 config 裡，`esp32s3` 那塊會同時管
   base 與 OCT 變體。要針對變體給不同設定，就得**開另一個 preset 目錄** ——
   這正是 `s31` 與 `s31-psram250` 能並存的原因（各自有自己的 `esp32s31` 區塊）。

3. **`sdkconfig` 區塊裡不要放 `_comment` 之類的鍵。**
   `_write_esp32_sdkconfig_fragment` 會把所有字串值原樣寫成 `KEY=VALUE`，
   結果會生出 `_comment=...` 這種垃圾行。要寫說明請放在**最外層**的 `_notes`。

4. **stack 切換會撞到「工作區不乾淨」。**
   前一次建置會改到 `ports/esp32/lockfiles/dependencies.lock.*`，
   導致下一次 `git checkout <ref>` 失敗。`_stacks/*.json` 都帶
   `force_reset: true` 就是為了先清乾淨；工具跑完會把它寫回 `false`，
   所以**再切換一次時要重新 `cp`**（或手動清：
   `git -C lib/micropython checkout -- . && git -C lib/micropython clean -fd`）。

5. **`stack-idf5-orig` 要配 `exmod.list: []`。**
   上游 lv_binding + MicroPython >= 1.29 編不過（`mp_obj_int_to_bytes` 改名），
   那正是 PR #411 修的東西。而且要切到它會重新下載 IDF v5.5.5（數 GB）。

---

## 分區表

`esp32.partition.auto: true` 走兩趟：先寫一份 1 MB 的假分割表讓第一次建置失敗，
再讀 `micropython.bin` 的實際大小重算，尾端保留 `app_margin_kb`。

**會自帶 `vfs` 分割區**（`include_vfs=True`），所以燒錄後 `/` 一定掛得起來。
這是必要的：上游的 `partitions-*.csv` 都沒有 `vfs`，完全依賴 `main.c` 的
自動註冊，而那段在 IDF v6 上會靜默失敗（`esp_partition_register_external`
的回傳值被丟棄）→ `_boot.py` 跳過掛載 → 任何寫入 `/` 都得到
`OSError: [Errno 19] ENODEV`。

若 app 長大導致空間不足，工具會直接報
`RuntimeError: There is not enough flash to store the firmware.`（不會靜默生出壞固件）。
