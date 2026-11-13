#!/usr/bin/env python3
"""
VoiceTyper Tray - 系統匣版本
設定（熱鍵、模型、語言）請修改 voice_typer.py

預設為「佇列模式」：
  F7 / F8 錄音 → 辨識完成的文字存進佇列（不自動貼上，也不搶焦點）
  F9         → 把佇列中最早一筆貼到目前游標所在的地方
  系統匣圖示會顯示待貼筆數，右鍵可挑某一筆複製、或清空佇列
把 voice_typer.py 的 AUTO_PASTE 改成 True 可回到舊的自動貼上行為。
"""

import os
import sys
import ctypes
import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd
import keyboard
import pyperclip
import winsound
from PIL import Image, ImageDraw, ImageFont
import pystray
from faster_whisper import WhisperModel

# 從 voice_typer.py 讀取設定
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from voice_typer import (
    HOTKEY, SAMPLE_RATE, MODEL_SIZE, LANGUAGE, MIN_SECONDS,
    HOTKEY_FAST, MODEL_SIZE_FAST,
    AUTO_PASTE, HOTKEY_PASTE, QUEUE_MAX, SOUND,
)

# ── 圖示 ─────────────────────────────────────────────

def _font(size: int):
    for name in ('arialbd.ttf', 'arial.ttf', 'segoeui.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _make_icon(fill: tuple, count: int = 0) -> Image.Image:
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, 62, 62], fill=fill)
    # 麥克風外形
    d.rounded_rectangle([24, 12, 40, 36], radius=8, fill='white')
    d.ellipse([18, 28, 46, 46], outline='white', width=3)
    d.line([32, 46, 32, 54], fill='white', width=3)
    d.line([22, 54, 42, 54], fill='white', width=3)

    if count:
        # 右下角待貼筆數徽章
        d.ellipse([32, 32, 63, 63], fill=(220, 40, 40), outline='white', width=2)
        txt = str(count) if count < 10 else '9+'
        f = _font(20)
        box = d.textbbox((0, 0), txt, font=f)
        w, h = box[2] - box[0], box[3] - box[1]
        d.text((47.5 - w / 2 - box[0], 47.5 - h / 2 - box[1]), txt, font=f, fill='white')
    return img


COLOR_IDLE      = (55, 155, 80)    # 綠：待機
COLOR_RECORDING = (200, 55, 55)    # 紅：錄音
COLOR_THINKING  = (55, 120, 200)   # 藍：辨識中

# ── 主類別 ───────────────────────────────────────────

class VoiceTyperTray:
    def __init__(self):
        self.is_recording = False
        self.audio_frames: list = []
        self.stream = None
        self._lock = threading.Lock()
        self._qlock = threading.Lock()
        self.queue: deque[str] = deque()
        self._state = COLOR_IDLE
        self._target_hwnd: int = 0
        self._current_model = None
        self.tray: pystray.Icon | None = None

        print("⏳ 載入 Whisper 模型...")
        self.model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        self.model_fast = WhisperModel(MODEL_SIZE_FAST, device="cpu", compute_type="int8")
        print(f"✅ 模型載入完成（{MODEL_SIZE} / {MODEL_SIZE_FAST}）")

    # ── 工具 ─────────────────────────────────────────

    def _beep(self, *tones):
        """播放提示音；tones 為 (頻率, 毫秒) 的序列。

        注意：低於 100ms 的 Beep 在 Windows 上幾乎聽不見，
        所以這裡的音長都至少 120ms。
        """
        if not SOUND:
            return

        def play():
            for freq, ms in tones:
                try:
                    winsound.Beep(freq, ms)
                except Exception:
                    return

        threading.Thread(target=play, daemon=True).start()

    # 各事件的提示音
    SND_START = ((880, 140),)                 # 開始錄音
    SND_STOP  = ((660, 140),)                 # 放開，開始辨識
    SND_DONE  = ((1047, 130), (1319, 190))    # 辨識完成，已進佇列（上行兩聲）
    SND_PASTE = ((1319, 120),)                # 貼出一筆
    SND_EMPTY = ((300, 260),)                 # 佇列是空的

    def _set_state(self, color: tuple):
        self._state = color
        self._refresh_tray()

    def _refresh_tray(self):
        """重畫圖示（含待貼徽章）、更新提示文字與選單"""
        if not self.tray:
            return
        with self._qlock:
            n = len(self.queue)
        try:
            self.tray.icon = _make_icon(self._state, n)
            self.tray.title = f'VoiceTyper - 待貼 {n} 筆' if n else 'VoiceTyper'
            self.tray.menu = pystray.Menu(*self._menu_items())
            self.tray.update_menu()
        except Exception:
            pass

    def _notify(self, title: str, message: str):
        if not self.tray:
            return
        try:
            self.tray.notify(message, title)
        except Exception:
            pass

    def _restore_focus(self):
        """還原焦點到錄音前的視窗（只有 AUTO_PASTE=True 才會用到）

        1. 焦點根本沒跑掉 → 直接 return。千萬不要按 Alt，
           那會打開目標視窗的選單列，害 Ctrl+V 貼不進去。
        2. 需要切回時用 AttachThreadInput 取得切換權限（不需按鍵）。
        3. 真的切不回去才退回舊的 Alt trick。
        """
        if not self._target_hwnd:
            return
        try:
            user32   = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            if user32.GetForegroundWindow() == self._target_hwnd:
                return  # 使用者沒切走，不要碰焦點

            # 把自己的輸入佇列接到目標視窗的執行緒，才有資格 SetForegroundWindow
            target_tid = user32.GetWindowThreadProcessId(self._target_hwnd, None)
            cur_tid    = kernel32.GetCurrentThreadId()
            attached   = False
            if target_tid and target_tid != cur_tid:
                attached = bool(user32.AttachThreadInput(cur_tid, target_tid, True))

            user32.BringWindowToTop(self._target_hwnd)
            ok = user32.SetForegroundWindow(self._target_hwnd)

            if attached:
                user32.AttachThreadInput(cur_tid, target_tid, False)

            if not ok and user32.GetForegroundWindow() != self._target_hwnd:
                # Fallback：舊的 Alt trick（可能觸發選單，只在上面失敗時用）
                VK_MENU = 0x12
                KUP     = 0x0002
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

    # ── 佇列 ─────────────────────────────────────────

    def _enqueue(self, text: str):
        with self._qlock:
            dropped = len(self.queue) >= QUEUE_MAX
            if dropped:
                self.queue.popleft()
            self.queue.append(text)
            n = len(self.queue)
        self._refresh_tray()
        preview = text if len(text) <= 60 else text[:60] + '…'
        suffix  = '（已滿，丟掉最舊一筆）' if dropped else ''
        self._notify(f'語音已就緒，待貼 {n} 筆{suffix}',
                     f'{preview}\n按 {HOTKEY_PASTE.upper()} 貼到游標處')
        self._beep(*self.SND_DONE)

    def paste_next(self):
        """把最早一筆貼到目前游標處；佇列空就低頻嗶一聲"""
        with self._qlock:
            if not self.queue:
                self._beep(*self.SND_EMPTY)
                return
            text = self.queue.popleft()
        pyperclip.copy(text)
        self._refresh_tray()
        self._beep(*self.SND_PASTE)
        time.sleep(0.05)
        self._send_ctrl_v()

    def _pick(self, index: int):
        """系統匣選單挑某一筆：複製到剪貼簿並移出佇列（自己 Ctrl+V 貼）"""
        def handler(icon=None, item=None):
            with self._qlock:
                if index >= len(self.queue):
                    return
                text = self.queue[index]
                del self.queue[index]
            pyperclip.copy(text)
            self._refresh_tray()
            self._notify('已複製到剪貼簿', text if len(text) <= 60 else text[:60] + '…')
        return handler

    def _clear_queue(self, icon=None, item=None):
        with self._qlock:
            self.queue.clear()
        self._refresh_tray()
        self._notify('佇列已清空', '待貼項目全部移除')

    # ── 錄音 ─────────────────────────────────────────

    def start_recording(self, model=None):
        with self._lock:
            if self.is_recording:
                return
            self.is_recording = True
            self.audio_frames = []
            self._current_model = model or self.model
            # 記住目前焦點視窗（AUTO_PASTE 模式要貼回這裡）
            self._target_hwnd = ctypes.windll.user32.GetForegroundWindow()

        self._set_state(COLOR_RECORDING)
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32',
            callback=self._audio_callback,
        )
        self.stream.start()
        self._beep(*self.SND_START)

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

        self._beep(*self.SND_STOP)
        self._set_state(COLOR_THINKING)

        if not self.audio_frames:
            self._set_state(COLOR_IDLE)
            return

        audio = np.concatenate(self.audio_frames).flatten()
        if len(audio) < SAMPLE_RATE * MIN_SECONDS:
            self._set_state(COLOR_IDLE)
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
        self._set_state(COLOR_IDLE)

        if not text:
            return

        if AUTO_PASTE:
            pyperclip.copy(text)
            self._restore_focus()  # 切回原本的視窗
            self._send_ctrl_v()    # 直接用 ctypes 貼上
        else:
            self._enqueue(text)    # 進佇列，等 F9

    # ── 系統匣 ───────────────────────────────────────

    def _menu_items(self):
        items = [
            pystray.MenuItem(f'{HOTKEY.upper()} 精準（{MODEL_SIZE}）', None, enabled=False),
            pystray.MenuItem(f'{HOTKEY_FAST.upper()} 快速（{MODEL_SIZE_FAST}）', None, enabled=False),
        ]
        if not AUTO_PASTE:
            items.append(
                pystray.MenuItem(f'{HOTKEY_PASTE.upper()} 貼上最早一筆', None, enabled=False)
            )
            items.append(pystray.Menu.SEPARATOR)
            with self._qlock:
                snapshot = list(self.queue)
            if snapshot:
                for i, t in enumerate(snapshot):
                    label = t if len(t) <= 24 else t[:24] + '…'
                    items.append(pystray.MenuItem(f'{i + 1}. {label}', self._pick(i)))
                items.append(pystray.Menu.SEPARATOR)
                items.append(pystray.MenuItem('清除佇列', self._clear_queue))
            else:
                items.append(pystray.MenuItem('（佇列是空的）', None, enabled=False))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem('結束', self._exit))
        return items

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
        if not AUTO_PASTE:
            keyboard.on_release_key(
                HOTKEY_PASTE,
                lambda _: threading.Thread(target=self.paste_next, daemon=True).start(),
            )

        self.tray = pystray.Icon(
            'VoiceTyper',
            _make_icon(COLOR_IDLE),
            'VoiceTyper',
            pystray.Menu(*self._menu_items()),
        )
        self.tray.run()

    def _exit(self, icon, item):
        icon.stop()
        keyboard.unhook_all()
        os._exit(0)


if __name__ == '__main__':
    VoiceTyperTray().run()
