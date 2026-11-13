# VoiceTyper

Windows 全域語音輸入工具。按住熱鍵說話，辨識完成的文字進入待貼佇列，之後在任何視窗（Discord、瀏覽器、編輯器等）按 F9 就貼到游標處。

## 功能

- 按住熱鍵錄音，放開後在背景辨識，不搶焦點、不會打斷你手上的事
- 待貼佇列：可以連錄好幾筆，之後到各自要貼的地方一筆一筆按 F9 貼出去
- 完成時跳系統通知，系統匣圖示顯示還有幾筆待貼，右鍵可挑某一筆或清空
- 雙模型：F7 精準模式（medium）、F8 快速模式（small）
- 自動偵測中英文，遇到日韓文自動強制切換中文重辨識
- 系統匣常駐，右鍵結束

## 安裝

**1. 安裝套件**

```
pip install faster-whisper sounddevice numpy keyboard pyperclip pystray Pillow
```

**2. 首次啟動會自動下載模型**（需要網路）

| 模型 | 大小 | 速度 | 準確度 |
|------|------|------|--------|
| small | ~466 MB | 快 | 一般 |
| medium | ~769 MB | 慢 | 高 |

模型會快取在 `%USERPROFILE%\.cache\huggingface\hub\`，之後離線也能用。

## 啟動

雙擊 `啟動語音輸入.vbs`（背景執行，不會有視窗跳出）

## 使用

| 動作 | 說明 |
|------|------|
| 按住 `F7` | 精準模式錄音（medium 模型） |
| 按住 `F8` | 快速模式錄音（small 模型） |
| 放開 | 背景辨識，完成後進入待貼佇列並跳通知 |
| 按 `F9` | 把佇列中**最早**一筆貼到目前游標處 |
| 系統匣右鍵 → 某一筆 | 只複製該筆到剪貼簿（自己 Ctrl+V），並移出佇列 |
| 系統匣右鍵 → 清除佇列 | 丟掉所有待貼項目 |
| 系統匣右鍵 → 結束 | 關閉程式 |

典型用法：在 A 視窗錄第一筆、跑去 B 視窗錄第二筆，回到 A 按 F9 貼第一筆，再回 B 按 F9 貼第二筆。

系統匣圖示顏色：
- 綠色：待機
- 紅色：錄音中
- 藍色：辨識中
- 右下角紅色數字：待貼筆數（滑鼠移上去也會顯示）

## 設定

編輯 `voice_typer.py` 開頭：

```python
HOTKEY          = 'f7'      # 精準模式熱鍵
HOTKEY_FAST     = 'f8'      # 快速模式熱鍵
MODEL_SIZE      = 'medium'  # tiny / base / small / medium
MODEL_SIZE_FAST = 'small'   # tiny / base / small / medium
LANGUAGE        = None      # None=自動偵測；'zh'=純中文
MIN_SECONDS     = 0.4       # 低於此秒數的錄音忽略

AUTO_PASTE      = False     # True = 辨識完自動切回原視窗貼上（舊行為，不進佇列）
HOTKEY_PASTE    = 'f9'      # 貼上佇列中最早一筆
QUEUE_MAX       = 20        # 佇列上限，超過自動丟掉最舊一筆
```

## 系統需求

- Windows 10 / 11
- Python 3.10+
- 麥克風

## License

MIT
