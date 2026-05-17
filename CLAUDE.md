# VoiceTyper

全域語音輸入工具，按住熱鍵說話，放開後自動轉文字貼到任何視窗（Discord、AI Agent 等）。

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
HOTKEY      = 'f4'      # 按住錄音的熱鍵
MODEL_SIZE  = 'medium'  # tiny / base / small / medium（越大越準但越慢）
LANGUAGE    = None      # None=自動偵測中英文；'zh'=純中文
MIN_SECONDS = 0.4       # 低於此秒數的錄音忽略
```

## 使用

- 右下角**綠色**圓圈 = 待機
- 按住 `F4` → 變紅，說話
- 放開 → 變藍（辨識中）→ 自動切回原視窗貼上
- 右鍵圖示 → 結束

## 套件

```
pip install faster-whisper sounddevice numpy keyboard pyperclip pystray Pillow
```

模型快取：`%USERPROFILE%\.cache\huggingface\hub\`（首次啟動自動下載 medium 約 769 MB）

## 上次做到哪
- 專案從 `D:\coding\test\` 搬移過來，完成接手初始化
- 修正 `啟動語音輸入.vbs` 路徑（改用 `WScript.ScriptFullName` 相對定位，跨電腦可用）
- 補建 `.gitignore`、`README.md`
- 新增 F3 快速模式熱鍵，使用 `small` 模型（F4 維持 `medium`）
- 移除所有絕對路徑，改為相對路徑或環境變數

## 待辦事項
- 確認 VBS 在目標電腦上可正常啟動

## 重點實作說明

### 語言限制
偵測到非中文／英文（日文等）自動強制用 `zh` 重辨識。
`initial_prompt` 引導模型優先處理中英文。

### 焦點還原
按下熱鍵時記住目標視窗 HWND，辨識完後：
1. `keybd_event(VK_MENU)` Alt trick 繞過 Windows 焦點鎖定
2. `BringWindowToTop` + `SetForegroundWindow` 切回目標視窗
3. 等 0.25s，再用 `keybd_event` 直接發送 Ctrl+V

### 速度優化
`beam_size=1` + `condition_on_previous_text=False`
