import time
import tkinter as tk

from PIL import Image, ImageTk

from siriusvision.app import ScreenManager
from siriusvision.displays.base import prepare_frame


class MacPreview:
    def __init__(self, manager: ScreenManager, now):
        self.manager = manager
        self.now = now
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            raise ValueError(f"Cannot open preview window: {exc}") from exc
        self.root.title("SiriusVision")
        self.root.configure(bg="#17191e")
        self.title = tk.Label(self.root, fg="#eee8dd", bg="#17191e", font=("Helvetica", 14))
        self.title.pack(pady=8)
        self.canvas = tk.Canvas(self.root, width=640, height=640, bg="black", highlightthickness=0)
        self.canvas.pack()
        self.image_item = self.canvas.create_image(0, 0, anchor="nw")
        if manager.config.show_grid:
            for position in range(10, 640, 10):
                self.canvas.create_line(position, 0, position, 640, fill="#252525")
                self.canvas.create_line(0, position, 640, position, fill="#252525")
        tk.Label(self.root, text="← / P  previous    → / N  next    SPACE  pause    Q  quit",
                 fg="#aaaeb6", bg="#17191e").pack(pady=8)
        self.root.bind("<Key>", self.key)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.photo = None
        self.last_frame = None
        self.previous_frame = None
        self.last_name = None
        self.transition_at = 0.0
        self.closed = False

    def key(self, event) -> None:
        key = event.keysym.lower()
        if key in ("n", "right"):
            self.manager.next()
        elif key in ("p", "left"):
            self.manager.previous()
        elif key == "space":
            self.manager.toggle_pause()
        elif key == "q":
            self.close()
        elif key in ("1", "2", "3", "4") and int(key) <= len(self.manager.order):
            self.manager.select(int(key) - 1)

    def show(self, image: Image.Image) -> None:
        image = prepare_frame(image, self.manager.config.brightness)
        if self.manager.name != self.last_name:
            self.previous_frame = self.last_frame
            self.transition_at = time.monotonic()
            self.last_name = self.manager.name
        self.last_frame = image
        if self.previous_frame is not None:
            alpha = min(1.0, (time.monotonic() - self.transition_at) / 0.3)
            image = Image.blend(self.previous_frame, image, alpha)
            if alpha == 1.0:
                self.previous_frame = None
        enlarged = image.resize((640, 640), Image.Resampling.NEAREST)
        self.photo = ImageTk.PhotoImage(enlarged, master=self.root)
        self.canvas.itemconfigure(self.image_item, image=self.photo)
        suffix = "  •  paused" if self.manager.paused else ""
        self.title.configure(text=self.manager.name.replace("-", " ").title() + suffix)

    def update(self) -> None:
        if self.closed:
            return
        self.manager.tick()
        self.show(self.manager.render(self.now()))
        self.root.after(100, self.update)

    def run(self) -> None:
        self.update()
        self.root.mainloop()

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.root.destroy()
