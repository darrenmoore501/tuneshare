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
        theme = manager.theme
        self.root.configure(bg=theme.background)
        self.title = tk.Label(self.root, fg=theme.foreground, bg=theme.background, font=("Helvetica", 14))
        self.title.pack(pady=8)
        self.canvas = tk.Canvas(self.root, width=640, height=640, bg=theme.background, highlightthickness=0)
        self.canvas.pack()
        self.image_item = self.canvas.create_image(0, 0, anchor="nw")
        self.grid_items = []
        if manager.config.show_grid:
            for position in range(10, 640, 10):
                self.grid_items.append(self.canvas.create_line(position, 0, position, 640, fill=theme.inactive))
                self.grid_items.append(self.canvas.create_line(0, position, 640, position, fill=theme.inactive))
        self.controls = tk.Label(
            self.root, text="← / P  previous    → / N  next    SPACE  pause    T  theme    Q  quit",
            fg=theme.foreground, bg=theme.background,
        )
        self.controls.pack(pady=8)
        self.root.bind("<Key>", self.key)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.photo = None
        self.closed = False

    def key(self, event) -> None:
        key = event.keysym.lower()
        if key in ("n", "right"):
            self.manager.next()
        elif key in ("p", "left"):
            self.manager.previous()
        elif key == "space":
            self.manager.toggle_pause()
        elif key == "t":
            self.manager.next_theme()
        elif key == "q":
            self.close()
        elif key in ("1", "2", "3", "4") and int(key) <= len(self.manager.order):
            self.manager.select(int(key) - 1)

    def show(self, image: Image.Image) -> None:
        image = prepare_frame(image, self.manager.config.brightness)
        enlarged = image.resize((640, 640), Image.Resampling.NEAREST)
        self.photo = ImageTk.PhotoImage(enlarged, master=self.root)
        self.canvas.itemconfigure(self.image_item, image=self.photo)
        theme = self.manager.theme
        self.root.configure(bg=theme.background)
        self.canvas.configure(bg=theme.background)
        self.controls.configure(fg=theme.foreground, bg=theme.background)
        for item in self.grid_items:
            self.canvas.itemconfigure(item, fill=theme.inactive)
        suffix = "  •  paused" if self.manager.paused else ""
        self.title.configure(
            text=self.manager.name.replace("-", " ").title() + "  •  " + theme.name + suffix,
            fg=theme.foreground, bg=theme.background,
        )

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
