# VoiceTyper

全域語音輸入工具，按住熱鍵說話，辨識結果進入待貼佇列，按 F9 貼到當下游標處（Discord、AI Agent 等）。

## 檔案

（此專案資料夾）

| 檔案 | 說明 |
|------|------|
| `voice_typer.py` | 設定檔，改熱鍵 / 模型 / 語言都在這 |
| `voice_typer_tray.py` | 主程式（系統匣） |
| `啟動語音輸入.vbs` | 啟動捷徑，雙擊即可，完全無視窗 |

## 啟動

雙擊 `啟動語音輸入.vbs`，或請 Claude 執行：
```
cd <此專案資料夾>; Start-Process pythonw -ArgumentList "voice_typer_tray.py"
```

## 設定（voice_typer.py 開頭）

```python
HOTKEY       = 'f7'      # 精準模式熱鍵（按住錄音）
HOTKEY_FAST  = 'f8'      # 快速模式熱鍵（small 模型）
MODEL_SIZE   = 'medium'  # tiny / base / small / medium（越大越準但越慢）
LANGUAGE     = None      # None=自動偵測中英文；'zh'=純中文
MIN_SECONDS  = 0.4       # 低於此秒數的錄音忽略
AUTO_PASTE   = False     # True = 辨識完自動切回原視窗貼上（舊行為）
HOTKEY_PASTE = 'f9'      # 貼上佇列中最早一筆
QUEUE_MAX    = 20        # 佇列上限
```

## 使用

- 右下角**綠色**圓圈 = 待機
- 按住 `F7`（精準）或 `F8`（快速） → 變紅，說話
- 放開 → 變藍（辨識中）→ 完成後進佇列、跳通知，圖示右下角顯示待貼筆數
- 按 `F9` → 把最早一筆貼到目前游標處（不切視窗）
- 右鍵圖示 → 挑某一筆（只複製到剪貼簿）／清除佇列／結束

## 套件

```
pip install faster-whisper sounddevice numpy keyboard pyperclip pystray Pillow
```

模型快取：`%USERPROFILE%\.cache\huggingface\hub\`（首次啟動自動下載 medium 約 769 MB）

## 上次做到哪
- 提示音拉長到 140-260ms（原本 70-80ms 在 Windows 上幾乎聽不見），五個事件各有音型，非阻塞播放，新增 SOUND 開關
- 改為佇列模式：辨識完不自動貼，存進佇列等 F9 貼到當下游標處；加上系統通知、圖示待貼筆數徽章、選單挑單筆／清除佇列（AUTO_PASTE=True 可回到舊行為）
- 熱鍵由 F4 / F3 改為 F7（精準 medium）/ F8（快速 small），避開 Claude 等程式的快捷鍵，README 與本檔同步更新
- 補寫完整 README.md（安裝、使用、設定、系統需求）
- 新增 MIT LICENSE
- 初始化 git repo，建立公開 GitHub repo 並推送
- GitHub：https://github.com/FengLingYu7563/VoiceTyper

## 待辦事項
- 確認 VBS 在目標電腦上可正常啟動

## 重點實作說明

### 語言限制
偵測到非中文／英文（日文等）自動強制用 `zh` 重辨識。
`initial_prompt` 引導模型優先處理中英文。

### 佇列模式（預設）
`AUTO_PASTE = False` 時辨識完不碰焦點，文字推進 `deque`，由 F9 取最早一筆
`pyperclip.copy` + ctypes Ctrl+V 貼到當下視窗。佇列變動就重畫圖示徽章與選單
（`_refresh_tray`），並用 `pystray.Icon.notify` 跳通知。

### 焦點還原（只有 AUTO_PASTE=True 用得到）
按下熱鍵時記住目標視窗 HWND，辨識完後：
1. 前景視窗已經是目標就直接 return（按 Alt 會打開該視窗選單，害 Ctrl+V 失效）
2. `AttachThreadInput` 取得切換權限 → `BringWindowToTop` + `SetForegroundWindow`
3. 都失敗才退回舊的 Alt trick，等 0.25s 再用 `keybd_event` 發送 Ctrl+V

### 無法鎖定同一程式內的分頁
Claude 桌面是 Electron 單一頂層視窗（class `Chrome_WidgetWin_1`），切換專案不改 HWND
也不改標題；UIA 只看得到外框按鈕，拿不到網頁內的輸入框。所以「回到原本那個專案」
在 Win32 層無解，這也是改用 F9 手動貼上佇列的原因。

### 提示音沒聲音時先看這裡
`winsound.Beep` 走的是**系統音效**通道，不是程式自己的那條。
音量混音器裡的「系統音效」若為 0，程式再怎麼叫都沒聲音；
混音器中灰色的 Python 條只是已結束 session 的殘留，與此無關。
另外低於 100ms 的 Beep 在 Windows 上幾乎聽不見，音長至少要 120ms。

### 速度優化
`beam_size=1` + `condition_on_previous_text=False`
