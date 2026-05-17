#!/usr/bin/env python3
"""
VoiceTyper Tray - 系統匣版本
設定（熱鍵、模型、語言）請修改 voice_typer.py
"""

import os
import sys
import ctypes
import threading
import time
import numpy as np
import sounddevice as sd
import keyboard
import pyperclip
import winsound
from PIL import Image, ImageDraw
import pystray
from faster_whisper import WhisperModel

# 從 voice_typer.py 讀取設定
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from voice_typer import HOTKEY, SAMPLE_RATE, MODEL_SIZE, LANGUAGE, MIN_SECONDS, HOTKEY_FAST, MODEL_SIZE_FAST

# ── 圖示 ─────────────────────────────────────────────

def _make_icon(fill: tuple) -> Image.Image:
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, 62, 62], fill=fill)
    # 麥克風外形
    d.rounded_rectangle([24, 12, 40, 36], radius=8, fill='white')
    d.ellipse([18, 28, 46, 46], outline='white', width=3)
    d.line([32, 46, 32, 54], fill='white', width=3)
    d.line([22, 54, 42, 54], fill='white', width=3)
    return img

ICON_IDLE      = _make_icon((55, 155, 80))   # 綠：待機
ICON_RECORDING = _make_icon((200, 55, 55))   # 紅：錄音
ICON_THINKING  = _make_icon((55, 120, 200))  # 藍：辨識中

# ── 主類別 ───────────────────────────────────────────

class VoiceTyperTray:
    def __init__(self):
        self.is_recording = False
        self.audio_frames: list = []
        self.stream = None
        self._lock = threading.Lock()
        self._target_hwnd: int = 0
        self._current_model = None
        self.tray: pystray.Icon | None = None

        print("⏳ 載入 Whisper 模型...")
        self.model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        self.model_fast = WhisperModel(MODEL_SIZE_FAST, device="cpu", compute_type="int8")
        print(f"✅ 模型載入完成（{MODEL_SIZE} / {MODEL_SIZE_FAST}）")

    # ── 工具 ─────────────────────────────────────────

    def _beep(self, freq: int, ms: int):
        try:
            winsound.Beep(freq, ms)
        except Exception:
            pass

    def _set_icon(self, icon: Image.Image):
        if self.tray:
            self.tray.icon = icon

    def _restore_focus(self):
        """還原焦點到錄音前的視窗（Alt trick 繞過 Windows 焦點鎖定）"""
        if not self._target_hwnd:
            return
        try:
            user32    = ctypes.windll.user32
            VK_MENU   = 0x12          # Alt 鍵
            KUP       = 0x0002        # KEYEVENTF_KEYUP
            # 短暫按下 Alt → Windows 允許後續 SetForegroundWindow
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.BringWindowToTop(self._target_hwnd)
            user32.SetForegroundWindow(self._target_hwnd)
            user32.keybd_event(VK_MENU, 0, KUP, 0)
            time.sleep(0.25)          # 等 OS 完成焦點切換
        except Exception:
            pass

    def _send_ctrl_v(self):
        """用 ctypes 直接發送 Ctrl+V（比 keyboard.send 更可靠）"""
        u   = ctypes.windll.user32
        KUP = 0x0002
        u.keybd_event(0x11, 0, 0,   0)   # Ctrl down
        u.keybd_event(0x56, 0, 0,   0)   # V    down
        u.keybd_event(0x56, 0, KUP, 0)   # V    up
        u.keybd_event(0x11, 0, KUP, 0)   # Ctrl up

    # ── 錄音 ─────────────────────────────────────────

    def start_recording(self, model=None):
        with self._lock:
            if self.is_recording:
                return
            self.is_recording = True
            self.audio_frames = []
            self._current_model = model or self.model
            # 記住目前焦點視窗（這才是要貼上的地方）
            self._target_hwnd = ctypes.windll.user32.GetForegroundWindow()

        self._set_icon(ICON_RECORDING)
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32',
            callback=self._audio_callback,
        )
        self.stream.start()
        self._beep(880, 80)

    def _audio_callback(self, indata, frames, time_info, status):
        if self.is_recording:
            self.audio_frames.append(indata.copy())

    # ── 辨識 ─────────────────────────────────────────

    def stop_and_transcribe(self):
        with self._lock:
            if not self.is_recording:
                return
            self.is_recording = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        self._beep(660, 80)
        self._set_icon(ICON_THINKING)

        if not self.audio_frames:
            self._set_icon(ICON_IDLE)
            return

        audio = np.concatenate(self.audio_frames).flatten()
        if len(audio) < SAMPLE_RATE * MIN_SECONDS:
            self._set_icon(ICON_IDLE)
            return

        # 允許的語言：中文 + 英文
        ALLOWED = {'zh', 'en'}
        PROMPT  = "繁體中文與英文混合對話。Traditional Chinese and English."

        segments_gen, info = self._current_model.transcribe(
            audio,
            language=LANGUAGE,      # None = 自動偵測
            initial_prompt=PROMPT,  # 引導模型優先辨識中英文
            vad_filter=True,
            beam_size=1,
            condition_on_previous_text=False,
        )
        parts = [seg.text for seg in segments_gen]   # 先把 generator 消耗掉

        if info.language not in ALLOWED:
            # 偵測到日文/韓文等 → 強制用中文重跑
            print(f"⚠️  偵測到 {info.language}，強制切換為中文重辨識")
            segments_gen2, _ = self._current_model.transcribe(
                audio,
                language='zh',
                vad_filter=True,
                beam_size=1,
                condition_on_previous_text=False,
            )
            parts = [seg.text for seg in segments_gen2]

        text = "".join(parts).strip()
        self._set_icon(ICON_IDLE)

        if text:
            pyperclip.copy(text)
            self._restore_focus()  # 切回原本的視窗
            self._send_ctrl_v()    # 直接用 ctypes 貼上

    # ── 系統匣 ───────────────────────────────────────

    def run(self):
        keyboard.on_press_key(
            HOTKEY,
            lambda _: threading.Thread(target=self.start_recording, daemon=True).start(),
        )
        keyboard.on_release_key(
            HOTKEY,
            lambda _: threading.Thread(target=self.stop_and_transcribe, daemon=True).start(),
        )
        keyboard.on_press_key(
            HOTKEY_FAST,
            lambda _: threading.Thread(target=lambda: self.start_recording(self.model_fast), daemon=True).start(),
        )
        keyboard.on_release_key(
            HOTKEY_FAST,
            lambda _: threading.Thread(target=self.stop_and_transcribe, daemon=True).start(),
        )

        menu = pystray.Menu(
            pystray.MenuItem(f'{HOTKEY.upper()} 精準（{MODEL_SIZE}）', None, enabled=False),
            pystray.MenuItem(f'{HOTKEY_FAST.upper()} 快速（{MODEL_SIZE_FAST}）', None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('結束', self._exit),
        )
        self.tray = pystray.Icon('VoiceTyper', ICON_IDLE, 'VoiceTyper', menu)
        self.tray.run()

    def _exit(self, icon, item):
        icon.stop()
        keyboard.unhook_all()
        os._exit(0)


if __name__ == '__main__':
    VoiceTyperTray().run()
