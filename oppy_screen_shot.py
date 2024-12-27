import tkinter as tk
from PIL import Image
from mss import mss
import pyautogui
import time
import threading


class ScreenSelector:
    def __init__(self):
        self.start_x = None
        self.start_y = None
        self.rect_id = None
        self.current_monitor = None
        self.is_running = True

        # Tkinterウィンドウの作成
        self.root = tk.Tk()
        self.root.withdraw()  # メインウィンドウを非表示

        # オーバーレイウィンドウの作成
        self.overlay = tk.Toplevel()
        self.overlay.attributes('-alpha', 0.3)  # 透明度設定
        self.overlay.attributes('-topmost', True)  # 最前面に表示

        # ウィンドウの装飾を削除
        self.overlay.overrideredirect(True)

        # キャンバスの設定
        self.canvas = tk.Canvas(
            self.overlay,
            highlightthickness=0,
            bg='black'
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # マウスイベントのバインド
        self.canvas.bind('<Button-1>', self.on_mouse_down)
        self.canvas.bind('<B1-Motion>', self.on_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_mouse_up)

        # Escキーでキャンセル
        self.overlay.bind('<Escape>', self.on_escape)
        self.overlay.protocol("WM_DELETE_WINDOW", self.on_close)

        # マウス位置監視スレッドの開始
        self.monitor_thread = threading.Thread(target=self.monitor_mouse_position)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

        # 初期位置の設定
        self.update_overlay_position()

        # 標準入力監視スレッドの開始
        self.input_thread = threading.Thread(target=self.monitor_input)
        self.input_thread.daemon = True
        self.input_thread.start()

    def monitor_input(self):
        """標準入力を監視し、'exit'が入力されたら終了"""
        while self.is_running:
            try:
                line = input().strip()
                if line.lower() == 'exit':
                    print("[OPPY-SCREEN-SHOT] Exit command received.", flush=True)
                    # メインスレッドでウィンドウを閉じる
                    self.root.after(0, self.on_close)
            except EOFError:
                break
            except Exception as e:
                print(f"[OPPY-SCREEN-SHOT] Input error: {e}", flush=True)

    def get_monitor_at_cursor(self):
        """カーソル位置にあるモニターの情報を取得"""
        cursor_x, cursor_y = pyautogui.position()
        with mss() as sct:
            for monitor in sct.monitors[1:]:  # 最初のモニター（全画面を表す）をスキップ
                if (monitor["left"] <= cursor_x < monitor["left"] + monitor["width"] and
                        monitor["top"] <= cursor_y < monitor["top"] + monitor["height"]):
                    # モニターデータにモニターの索引を追加
                    monitor['index'] = sct.monitors.index(monitor)
                    return monitor

            # カーソルがモニター上にない場合はデフォルトのモニターを返す
            monitor = sct.monitors[1]  # デフォルトはプライマリモニター

            # モニターデータにモニターの索引を追加
            monitor['index'] = sct.monitors.index(monitor)

            return sct.monitors[1]  # デフォルトはプライマリモニター

    def update_overlay_position(self):
        """オーバーレイウィンドウの位置を更新"""
        new_monitor = self.get_monitor_at_cursor()

        # モニターが変更された場合のみウィンドウを移動
        if (not self.current_monitor or
                new_monitor['left'] != self.current_monitor['left'] or
                new_monitor['top'] != self.current_monitor['top']):
            print("[OPPY-SCREEN-SHOT] Moved to monitor:", new_monitor['index'], flush=True)

            self.current_monitor = new_monitor

            # キャンバスのサイズを更新
            self.canvas.config(
                width=self.current_monitor['width'],
                height=self.current_monitor['height']
            )

            # オーバーレイウィンドウの位置とサイズを更新
            self.overlay.geometry(
                f"{self.current_monitor['width']}x{self.current_monitor['height']}+"
                f"{self.current_monitor['left']}+{self.current_monitor['top']}"
            )

            # 既存の選択矩形があれば削除
            if self.rect_id:
                self.canvas.delete(self.rect_id)
                self.rect_id = None

    def monitor_mouse_position(self):
        """マウス位置を監視し、必要に応じてオーバーレイの位置を更新"""
        while self.is_running:
            self.update_overlay_position()
            time.sleep(0.1)  # 監視間隔

    def on_mouse_down(self, event):
        """マウスボタン押下時の処理"""
        self.start_x = event.x
        self.start_y = event.y

        # 既存の選択矩形があれば削除
        if self.rect_id:
            self.canvas.delete(self.rect_id)

        # 新しい選択矩形を作成
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline='red', width=2
        )

    def on_mouse_drag(self, event):
        """マウスドラッグ時の処理"""
        if self.rect_id:
            # 選択矩形を更新
            self.canvas.coords(
                self.rect_id,
                self.start_x, self.start_y,
                event.x, event.y
            )

    def on_mouse_up(self, event):
        """マウスボタンリリース時の処理"""
        if self.rect_id:
            # 選択範囲の座標を取得
            coords = self.canvas.coords(self.rect_id)

            # 選択範囲のサイズを計算
            width = abs(coords[2] - coords[0])
            height = abs(coords[3] - coords[1])

            # 最小サイズ（10x10ピクセル）未満の場合は再選択
            if width < 10 or height < 10:
                print("[OPPY-SCREEN-SHOT] Selected area is too small (minimum: 10x10 pixels). Please try again.",
                      flush=True)
                self.reset_selection()
                return

            try:
                # 座標をモニターの相対座標に変換
                x1 = min(coords[0], coords[2]) + self.current_monitor['left']
                y1 = min(coords[1], coords[3]) + self.current_monitor['top']
                x2 = max(coords[0], coords[2]) + self.current_monitor['left']
                y2 = max(coords[1], coords[3]) + self.current_monitor['top']

                # スクリーンショットを撮影
                self.capture_screenshot(int(x1), int(y1), int(x2), int(y2))

                # 成功したら終了
                self.on_close()

            except Exception as e:
                print(f"[OPPY-SCREEN-SHOT] Error capturing screenshot: {e}. Please try again.", flush=True)
                self.reset_selection()

    def reset_selection(self):
        """選択をリセットして再選択モードに移行"""
        # 既存の選択矩形をクリア
        if self.rect_id:
            self.canvas.delete(self.rect_id)
            self.rect_id = None

        # 選択状態をリセット
        self.start_x = None
        self.start_y = None

    def capture_screenshot(self, x1, y1, x2, y2):
        """指定された範囲のスクリーンショットを撮影"""
        try:
            with mss() as sct:
                # 撮影範囲の設定
                monitor = {
                    "left": x1,
                    "top": y1,
                    "width": max(x2 - x1, 1),  # 幅が0以下にならないように
                    "height": max(y2 - y1, 1)  # 高さが0以下にならないように
                }

                # スクリーンショットの撮影
                screenshot = sct.grab(monitor)

                # 一旦ファイル名はoppy_screen_shot.pngに固定
                file_name = 'oppy_screen_shot.png'

                # PIL Imageに変換して保存
                img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
                img.save(file_name)
                print("[OPPY-SCREEN-SHOT] Captured:", file_name, flush=True)

        except Exception as e:
            print(f"[OPPY-SCREEN-SHOT] Error saving screenshot: {e}", flush=True)
            raise  # エラーを上位に伝播させて再選択を促す

    def on_escape(self, event):
        """ESCキー押下時の処理"""
        print("[OPPY-SCREEN-SHOT] Canceled.", flush=True)
        self.on_close()

    def on_close(self):
        """アプリケーション終了時の処理"""
        if not self.is_running:  # 既に終了処理が実行されている場合は無視
            return

        print("[OPPY-SCREEN-SHOT] Closed.", flush=True)
        self.is_running = False
        self.overlay.destroy()
        self.root.quit()

    def run(self):
        """アプリケーションの実行"""
        self.root.mainloop()


if __name__ == "__main__":
    print("[OPPY-SCREEN-SHOT] Started.", flush=True)
    selector = ScreenSelector()
    selector.run()
