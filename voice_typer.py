#!/usr/bin/env python3
"""
VoiceTyper - 全域語音輸入工具
按住 Right Ctrl 說話，放開後自動貼上文字到任何視窗
"""

import threading
import time
import numpy as np
import sounddevice as sd
import keyboard
import pyperclip
import winsound
from faster_whisper import WhisperModel

# ── 設定 ──────────────────────────────────────────────
HOTKEY     = 'f4'  # 按住錄音的按鍵
SAMPLE_RATE = 16000
MODEL_SIZE  = 'medium'     # tiny / base / small / medium（越大越準但越慢）
LANGUAGE    = None         # None = 自動偵測（中英混打用這個）；純中文可改 'zh'
MIN_SECONDS = 0.4          # 低於這個秒數的錄音直接忽略
HOTKEY_FAST     = 'f3'    # 快速模式熱鍵（base 模型）
MODEL_SIZE_FAST = 'small'  # tiny / base / small / medium
# ─────────────────────────────────────────────────────


class VoiceTyper:
    def __init__(self):
        print("⏳ 載入 Whisper 模型（首次會下載，約 200-500 MB）...")
        self.model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        self.is_recording = False
        self.audio_frames = []
        self.stream = None
        self._lock = threading.Lock()

    # ── 音效回饋 ──────────────────────────────────────
    def _beep(self, freq: int, ms: int):
        try:
            winsound.Beep(freq, ms)
        except Exception:
            pass

    # ── 開始錄音 ──────────────────────────────────────
    def start_recording(self):
        with self._lock:
            if self.is_recording:
                return
            self.is_recording = True
            self.audio_frames = []

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32',
            callback=self._audio_callback,
        )
        self.stream.start()
        self._beep(880, 80)
        print("🎙  錄音中... 放開按鍵結束")

    def _audio_callback(self, indata, frames, time_info, status):
        if self.is_recording:
            self.audio_frames.append(indata.copy())

    # ── 停止錄音並轉文字 ──────────────────────────────
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

        if not self.audio_frames:
            return

        audio = np.concatenate(self.audio_frames).flatten()

        if len(audio) < SAMPLE_RATE * MIN_SECONDS:
            print("❌ 錄音太短，忽略")
            return

        print("⏳ 辨識中...")
        segments, _ = self.model.transcribe(
            audio,
            language=LANGUAGE,
            vad_filter=True,       # 自動去掉靜音段落
            beam_size=3,
        )
        text = "".join(seg.text for seg in segments).strip()

        if text:
            print(f"✅ {text}")
            pyperclip.copy(text)
            time.sleep(0.05)       # 給視窗一點反應時間
            keyboard.send('ctrl+v')
        else:
            print("❌ 沒有辨識到內容")

    # ── 主迴圈 ────────────────────────────────────────
    def run(self):
        print(f"\n✅ VoiceTyper 啟動！")
        print(f"   按住 [{HOTKEY.upper()}] 說話，放開後自動貼上")
        print(f"   語言：{'自動偵測' if LANGUAGE is None else '中文'}")
        print(f"   模型：{MODEL_SIZE}")
        print(f"   按 [ESC] 退出\n")

        keyboard.on_press_key(
            HOTKEY,
            lambda _: threading.Thread(
                target=self.start_recording, daemon=True
            ).start(),
        )
        keyboard.on_release_key(
            HOTKEY,
            lambda _: threading.Thread(
                target=self.stop_and_transcribe, daemon=True
            ).start(),
        )

        keyboard.wait('esc')
        print("\n👋 已退出")


if __name__ == '__main__':
    VoiceTyper().run()
