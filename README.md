# VoiceTyper

Windows 全域語音輸入工具。按住熱鍵說話，放開後自動辨識並貼到任何視窗（Discord、瀏覽器、編輯器等）。

## 功能

- 按住熱鍵錄音，放開即自動貼上，不需切換視窗
- 雙模型：F4 精準模式（medium）、F3 快速模式（small）
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
| 按住 `F4` | 精準模式錄音（medium 模型） |
| 按住 `F3` | 快速模式錄音（small 模型） |
| 放開 | 自動辨識並貼到原本的視窗 |
| 系統匣右鍵 → 結束 | 關閉程式 |

系統匣圖示顏色：
- 🟢 綠色：待機
- 🔴 紅色：錄音中
- 🔵 藍色：辨識中

## 設定

編輯 `voice_typer.py` 開頭：

```python
HOTKEY          = 'f4'      # 精準模式熱鍵
HOTKEY_FAST     = 'f3'      # 快速模式熱鍵
MODEL_SIZE      = 'medium'  # tiny / base / small / medium
MODEL_SIZE_FAST = 'small'   # tiny / base / small / medium
LANGUAGE        = None      # None=自動偵測；'zh'=純中文
MIN_SECONDS     = 0.4       # 低於此秒數的錄音忽略
```

## 系統需求

- Windows 10 / 11
- Python 3.10+
- 麥克風

## License

MIT
