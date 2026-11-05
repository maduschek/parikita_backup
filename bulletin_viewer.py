#!/usr/bin/env python3
"""
Bulletin Viewer for PariKita backup data.
Displays entries from bulletin_all.json in a desktop GUI, showing linked images in a gallery,
and allows clicking on thumbnails to view full-resolution images.
"""

import sys
import os
import json
import re
import html
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

try:
    from PIL import Image, ImageTk, ExifTags
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def get_image_description(path: Path | str | None) -> str:
    """Extract EXIF ImageDescription tag from an image file if present."""
    if not path or not HAS_PIL:
        return ""
    try:
        p = Path(path)
        if not p.is_file():
            return ""
        im = Image.open(p)
        exif = im.getexif()
        if not exif:
            return ""
        # EXIF tag 270 corresponds to ImageDescription
        val = exif.get(270)
        if val is None and hasattr(ExifTags, "Base") and hasattr(ExifTags.Base, "ImageDescription"):
            val = exif.get(ExifTags.Base.ImageDescription)
        if val is not None:
            if isinstance(val, bytes):
                for enc in ("utf-8", "utf-16le", "latin-1"):
                    try:
                        return val.decode(enc).rstrip("\x00").strip()
                    except UnicodeDecodeError:
                        continue
                return str(val).strip()
            return str(val).strip()
    except Exception:
        pass
    return ""


def clean_html(text: str | None) -> str:
    """Convert HTML-formatted text from bulletin posts into readable plain text."""
    if not text:
        return ""
    text = html.unescape(text)
    # Replace common break/paragraph tags
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)<p\s*>", "", text)
    text = re.sub(r"(?i)</li>", "\n", text)
    text = re.sub(r"(?i)<li>", "• ", text)
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse 3+ consecutive newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_datetime(dt_str: str | None) -> str:
    """Format ISO datetime string nicely."""
    if not dt_str:
        return ""
    try:
        # Handle "2026-09-09T13:14:06" or with timezone
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(dt_str)[:19]


def format_time_range(start_str: str | None, end_str: str | None) -> str:
    """Format a start and end ISO datetime into a clean time range like '(08:00 – 12:00)'."""
    def get_time(s: str | None) -> str:
        if not s:
            return ""
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            t = dt.strftime("%H:%M")
            return "" if t in ("00:00", "00:00:00", "00:00:01") else t
        except Exception:
            return ""

    t1 = get_time(start_str)
    t2 = get_time(end_str)
    if t1 and t2:
        return f" ({t1} – {t2})"
    if t1:
        return f" ({t1})"
    return ""


def format_calendar_item(item: dict) -> str:
    """Format a single CalendarItem dictionary into readable text."""
    itype = item.get("ItemType") or "Calendar Item"
    time_str = format_time_range(item.get("StartDate"), item.get("EndDate"))
    lines = []

    if itype == "MealPlan":
        title = item.get("Title") or "Meal Plan"
        lines.append(f"[Meal Plan] {title}")
        if item.get("Breakfast"):
            lines.append(f"  • Breakfast: {item['Breakfast']}")
        if item.get("Lunch"):
            lines.append(f"  • Lunch: {item['Lunch']}")
        if item.get("Afternoon"):
            lines.append(f"  • Afternoon Snack: {item['Afternoon']}")
        if item.get("Dinner"):
            lines.append(f"  • Dinner: {item['Dinner']}")

    elif itype == "InstitutionHoliday":
        info = item.get("AdditionalInformation") or "Holiday"
        lines.append(f"[Holiday] {info}")

    elif itype == "Activity":
        title = item.get("Title") or "Activity"
        lines.append(f"[Activity] {title}{time_str}")
        content = clean_html(item.get("ContentHtml"))
        if content:
            lines.append(f"  {content}")

    elif itype == "Invitation":
        title = item.get("Title") or "Invitation"
        lines.append(f"[Invitation] {title}{time_str}")
        content = clean_html(item.get("ContentHtml"))
        if content:
            lines.append(f"  {content}")

    elif itype == "Absence":
        atype = item.get("AbsenceType") or "Absence"
        lines.append(f"[Absence] {atype}{time_str}")

    elif itype == "CheckinStatus":
        status = item.get("Status") or "Check-in"
        bus = f" (Bus: {item.get('BusName')})" if item.get("BusName") else ""
        lines.append(f"[Check-in] {status}{bus}{time_str}")

    elif itype == "SleepRegistration":
        status = item.get("SleepStatus") or "Sleep"
        lines.append(f"[Sleep] {status}{time_str}")

    elif itype == "HealthStatus":
        stype = item.get("StatusType") or ""
        tspec = item.get("TypeSpecificInformation") or ""
        qual = item.get("Quality") or ""
        tstatus = item.get("TimeOfStatus") or ""
        comm = item.get("Comment") or ""
        parts = [p for p in [stype, tspec, qual] if p]
        desc = " - ".join(parts) if parts else "Health Status"
        if tstatus:
            desc += f" at {tstatus[:5]}"
        if comm:
            desc += f" ({comm})"
        lines.append(f"[Health Status] {desc}")

    elif itype == "Playdate":
        host = item.get("HostChildName") or ""
        invitees = ", ".join(item.get("InviteeChildrenNames") or [])
        details = []
        if host:
            details.append(f"Host: {host}")
        if invitees:
            details.append(f"Invitees: {invitees}")
        desc = " | ".join(details) if details else "Playdate"
        lines.append(f"[Playdate] {desc}{time_str}")

    elif itype == "Diary":
        title = item.get("Title") or "Diary"
        lines.append(f"[Diary] {title}")

    else:
        title = item.get("Title") or item.get("AdditionalInformation") or itype
        lines.append(f"[{itype}] {title}{time_str}")

    return "\n".join(lines)


def format_calendar_items(items: list[dict]) -> str:
    """Format a list of CalendarItems for a day into a formatted section string."""
    if not items:
        return ""
    formatted_items = [format_calendar_item(it) for it in items]
    return "— Calendar Items —\n" + "\n\n".join(formatted_items)


def get_calendar_title(items: list[dict]) -> str:
    """Derive a succinct, meaningful title from a list of CalendarItems for table display."""
    titles = []
    for it in items:
        t = it.get("Title") or it.get("AdditionalInformation") or it.get("AbsenceType")
        if not t and it.get("ItemType") == "CheckinStatus":
            t = f"Check-in: {it.get('Status', '')}"
        elif not t and it.get("ItemType") == "SleepRegistration":
            t = f"Sleep: {it.get('SleepStatus', '')}"
        elif not t and it.get("ItemType") == "HealthStatus":
            t = f"Health: {it.get('TypeSpecificInformation') or it.get('StatusType', '')}"
        elif not t:
            t = it.get("ItemType")
        if t and t.strip() not in titles:
            titles.append(t.strip())
    if not titles:
        return "Calendar"
    if len(titles) == 1:
        return titles[0]
    return " | ".join(titles[:2]) + (f" (+{len(titles)-2})" if len(titles) > 2 else "")


def open_file_with_default_app(file_path: Path | str) -> bool:
    """Open a file with the system default application across OS platforms."""
    path = Path(file_path).resolve()
    if not path.exists():
        messagebox.showwarning("File Not Found", f"The file does not exist locally:\n{path}")
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))
        elif sys.platform.startswith("darwin"):
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception as e:
        messagebox.showerror("Error Opening File", f"Could not open file with default application:\n{e}")
        return False


IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".heic", ".heif", ".svg"
}


class ImageIndex:
    """Index local image and attachment files by filename and id for fast lookups."""

    def __init__(self, base_dirs: list[Path]):
        self.indexed_files: dict[str, list[Path]] = {}
        self.indexed_stems: dict[str, list[Path]] = {}
        self.day_images: dict[str, list[Path]] = {}
        for base_dir in base_dirs:
            if not base_dir.exists():
                continue
            for path in base_dir.rglob("*"):
                if path.is_file():
                    name_key = path.name.lower()
                    stem_key = path.stem.lower()
                    self.indexed_files.setdefault(name_key, []).append(path)
                    self.indexed_stems.setdefault(stem_key, []).append(path)
                    if path.suffix.lower() in IMAGE_EXTENSIONS:
                        parent_name = path.parent.name
                        if re.match(r"^\d{4}-\d{2}-\d{2}$", parent_name):
                            self.day_images.setdefault(parent_name, []).append(path)

    def get_day_images(self, day_key: str) -> list[Path]:
        """Return unique sorted list of image paths for a given date (YYYY-MM-DD)."""
        paths = self.day_images.get(day_key, [])
        seen = set()
        unique_paths = []
        for p in paths:
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                unique_paths.append(p)
        return sorted(unique_paths, key=lambda p: p.name.lower())

    def get_all_days_with_images(self) -> list[str]:
        """Return sorted list of all day keys (YYYY-MM-DD) that have images."""
        return sorted(self.day_images.keys())

    def find_images(self, attachment_list: list[dict], news_date: str = "") -> list[dict]:
        """
        Given attachments from a bulletin item, return matched image paths with metadata.
        """
        results = []
        seen_paths = set()

        for att in attachment_list or []:
            att_id = str(att.get("Id", "")).strip()
            title = att.get("Title") or ""
            filename = att.get("FileName") or ""
            
            candidates = []
            if filename:
                candidates.append(filename.lower())
            if title and title != filename:
                candidates.append(title.lower())
            
            matched_path = None
            for c in candidates:
                # Direct match
                if c in self.indexed_files:
                    matched_path = self.indexed_files[c][0]
                    break
                # Stem match
                stem = Path(c).stem.lower()
                if stem in self.indexed_stems:
                    matched_path = self.indexed_stems[stem][0]
                    break

            # Fallback check by Id
            if not matched_path and att_id:
                if att_id in self.indexed_stems:
                    matched_path = self.indexed_stems[att_id][0]

            display_name = filename or title or f"Attachment {att_id}"
            is_image = False
            if matched_path:
                ext = matched_path.suffix.lower()
                is_image = ext in IMAGE_EXTENSIONS
            else:
                ext = Path(display_name).suffix.lower()
                is_image = ext in IMAGE_EXTENSIONS

            if matched_path and matched_path not in seen_paths:
                seen_paths.add(matched_path)
                results.append({
                    "id": att_id,
                    "title": display_name,
                    "path": matched_path,
                    "is_image": is_image,
                    "exists": True
                })
            elif not matched_path:
                results.append({
                    "id": att_id,
                    "title": display_name,
                    "path": None,
                    "is_image": is_image,
                    "exists": False
                })

        return results


class ImageViewerDialog(tk.Toplevel):
    """Full-size image viewer window with scaling, navigation and zoom."""

    def __init__(self, parent, image_list: list[dict], start_index: int = 0):
        super().__init__(parent)
        self.image_list = [img for img in image_list if img.get("exists") and img.get("is_image") and img.get("path")]
        self.current_index = max(0, min(start_index, len(self.image_list) - 1)) if self.image_list else 0

        self.title("Image Viewer")
        self.geometry("900x700")
        self.minsize(500, 400)
        self.configure(bg="#222222")

        self.zoom_factor = 1.0
        self.original_image = None
        self.tk_image = None

        self._build_ui()
        self._load_current_image()

        # Keyboard shortcuts
        self.bind("<Left>", lambda e: self.prev_image())
        self.bind("<Right>", lambda e: self.next_image())
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<plus>", lambda e: self.zoom_in())
        self.bind("<equal>", lambda e: self.zoom_in())
        self.bind("<minus>", lambda e: self.zoom_out())
        self.bind("<0>", lambda e: self.zoom_reset())

    def _build_ui(self):
        # Top toolbar
        toolbar = tk.Frame(self, bg="#333333", pady=6, padx=10)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        self.btn_prev = tk.Button(toolbar, text="◀ Previous", bg="#444444", fg="#ffffff",
                                  activebackground="#666666", activeforeground="#ffffff",
                                  relief=tk.FLAT, padx=10, command=self.prev_image)
        self.btn_prev.pack(side=tk.LEFT, padx=4)

        self.btn_next = tk.Button(toolbar, text="Next ▶", bg="#444444", fg="#ffffff",
                                  activebackground="#666666", activeforeground="#ffffff",
                                  relief=tk.FLAT, padx=10, command=self.next_image)
        self.btn_next.pack(side=tk.LEFT, padx=4)

        self.lbl_counter = tk.Label(toolbar, text="", bg="#333333", fg="#dddddd", font=("Helvetica", 10, "bold"))
        self.lbl_counter.pack(side=tk.LEFT, padx=15)

        # Zoom controls
        btn_zoom_out = tk.Button(toolbar, text="➖ Zoom Out", bg="#444444", fg="#ffffff",
                                 relief=tk.FLAT, padx=8, command=self.zoom_out)
        btn_zoom_out.pack(side=tk.RIGHT, padx=4)

        btn_zoom_reset = tk.Button(toolbar, text="Fit / 100%", bg="#444444", fg="#ffffff",
                                   relief=tk.FLAT, padx=8, command=self.zoom_reset)
        btn_zoom_reset.pack(side=tk.RIGHT, padx=4)

        btn_zoom_in = tk.Button(toolbar, text="➕ Zoom In", bg="#444444", fg="#ffffff",
                                relief=tk.FLAT, padx=8, command=self.zoom_in)
        btn_zoom_in.pack(side=tk.RIGHT, padx=4)

        # Bottom info bar
        self.info_bar = tk.Label(self, text="", bg="#1a1a1a", fg="#aaaaaa", anchor="w", padx=10, pady=4, font=("Helvetica", 9))
        self.info_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Canvas for image display
        self.canvas_frame = tk.Frame(self, bg="#222222")
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.canvas_frame, bg="#222222", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_resize)

    def _on_resize(self, event=None):
        if self.original_image and self.zoom_factor == 1.0:
            self._display_image()

    def _load_current_image(self):
        if not self.image_list:
            self.lbl_counter.config(text="No images")
            return

        item = self.image_list[self.current_index]
        self.lbl_counter.config(text=f"Image {self.current_index + 1} of {len(self.image_list)}")
        img_path = item["path"]

        self.btn_prev.config(state=tk.NORMAL if self.current_index > 0 else tk.DISABLED)
        self.btn_next.config(state=tk.NORMAL if self.current_index < len(self.image_list) - 1 else tk.DISABLED)

        try:
            if HAS_PIL:
                self.original_image = Image.open(img_path)
                w, h = self.original_image.size
                file_size_kb = os.path.getsize(img_path) / 1024
                self.info_bar.config(text=f"📁 {img_path.name} | {w}x{h} px | {file_size_kb:.1f} KB | Path: {img_path}")
            else:
                self.original_image = None
                self.info_bar.config(text=f"📁 {img_path.name} (Pillow not installed, basic display)")
            self._display_image()
        except Exception as e:
            self.info_bar.config(text=f"Error opening image: {e}")

    def _display_image(self):
        self.canvas.delete("all")
        if not self.original_image or not HAS_PIL:
            return

        canvas_w = self.canvas.winfo_width() or 800
        canvas_h = self.canvas.winfo_height() or 600

        orig_w, orig_h = self.original_image.size
        scale = min(canvas_w / orig_w, canvas_h / orig_h)
        scaled_w = max(1, int(orig_w * scale * self.zoom_factor))
        scaled_h = max(1, int(orig_h * scale * self.zoom_factor))

        resized = self.original_image.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(resized)

        x_pos = max(canvas_w // 2, scaled_w // 2)
        y_pos = max(canvas_h // 2, scaled_h // 2)

        self.canvas.create_image(x_pos, y_pos, image=self.tk_image, anchor=tk.CENTER)
        self.canvas.config(scrollregion=(0, 0, max(canvas_w, scaled_w), max(canvas_h, scaled_h)))

    def prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.zoom_factor = 1.0
            self._load_current_image()

    def next_image(self):
        if self.current_index < len(self.image_list) - 1:
            self.current_index += 1
            self.zoom_factor = 1.0
            self._load_current_image()

    def zoom_in(self):
        self.zoom_factor = min(self.zoom_factor * 1.25, 5.0)
        self._display_image()

    def zoom_out(self):
        self.zoom_factor = max(self.zoom_factor / 1.25, 0.2)
        self._display_image()

    def zoom_reset(self):
        self.zoom_factor = 1.0
        self._display_image()


class BulletinViewerApp(tk.Tk):
    """Main application window for browsing PariKita bulletin entries."""

    def __init__(self, json_path: Path, image_dirs: list[Path], calendar_json_path: Path | None = None):
        super().__init__()
        self.title("PariKita Bulletin Viewer")
        self.geometry("1200x800")
        self.minsize(800, 600)

        self.json_path = json_path
        self.calendar_json_path = calendar_json_path or (json_path.parent / "calendar_entries.json")
        self.image_dirs = image_dirs
        self.image_index = ImageIndex(image_dirs)

        self.all_entries: list[dict] = []
        self.filtered_entries: list[dict] = []
        self.current_entry: dict | None = None
        self.thumbnail_images: list[ImageTk.PhotoImage] = []  # Keep references

        self._setup_styles()
        self._build_ui()
        self._load_data()

    def _setup_styles(self):
        self.style = ttk.Style(self)
        # Try to use a modern theme if available
        available_themes = self.style.theme_names()
        if "clam" in available_themes:
            self.style.theme_use("clam")

        self.style.configure("Treeview", font=("Helvetica", 10), rowheight=26)
        self.style.configure("Treeview.Heading", font=("Helvetica", 10, "bold"))
        self.style.configure("Header.TLabel", font=("Helvetica", 14, "bold"))
        self.style.configure("SubHeader.TLabel", font=("Helvetica", 10, "italic"), foreground="#555555")

    def _build_ui(self):
        # Top Navigation / Filter Bar
        top_bar = ttk.Frame(self, padding=(10, 8, 10, 8))
        top_bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top_bar, text="🔍 Search:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        search_entry = ttk.Entry(top_bar, textvariable=self.search_var, width=35)
        search_entry.pack(side=tk.LEFT, padx=(0, 15))

        self.only_with_images_var = tk.BooleanVar(value=False)
        chk_images = ttk.Checkbutton(top_bar, text="Only posts with available images",
                                     variable=self.only_with_images_var,
                                     command=self._apply_filter)
        chk_images.pack(side=tk.LEFT, padx=(0, 15))

        self.sort_desc_var = tk.BooleanVar(value=True)
        btn_sort = ttk.Button(top_bar, text="⇅ Toggle Date Order (Newest First)", command=self._toggle_sort)
        self.btn_sort = btn_sort
        btn_sort.pack(side=tk.LEFT, padx=(0, 15))

        self.lbl_stats = ttk.Label(top_bar, text="")
        self.lbl_stats.pack(side=tk.RIGHT)

        # Main Paned Window: Left sidebar (list), Right pane (content & gallery)
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Left List View
        left_frame = ttk.Frame(main_pane, padding=2)
        main_pane.add(left_frame, weight=1)

        tree_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL)
        self.tree = ttk.Treeview(
            left_frame,
            columns=("date", "title", "images", "attachments"),
            show="headings",
            selectmode="browse",
            yscrollcommand=tree_scroll.set
        )
        tree_scroll.config(command=self.tree.yview)

        self.tree.heading("date", text="Date")
        self.tree.heading("title", text="Title")
        self.tree.heading("images", text="🖼️")
        self.tree.heading("attachments", text="📎")

        self.tree.column("date", width=120, minwidth=100, stretch=False)
        self.tree.column("title", width=200, minwidth=130, stretch=True)
        self.tree.column("images", width=45, minwidth=35, stretch=False, anchor="center")
        self.tree.column("attachments", width=45, minwidth=35, stretch=False, anchor="center")

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self._on_entry_selected)

        # Right Detail View
        right_frame = ttk.Frame(main_pane, padding=6)
        main_pane.add(right_frame, weight=3)

        # Header area in detail view
        header_frame = ttk.Frame(right_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        self.lbl_entry_title = ttk.Label(header_frame, text="Select an entry from the list", style="Header.TLabel", wraplength=700)
        self.lbl_entry_title.pack(anchor="w")

        self.lbl_entry_meta = ttk.Label(header_frame, text="", style="SubHeader.TLabel")
        self.lbl_entry_meta.pack(anchor="w", pady=(3, 0))

        # Split detail view into Content (top) and Gallery (bottom)
        detail_paned = ttk.PanedWindow(right_frame, orient=tk.VERTICAL)
        detail_paned.pack(fill=tk.BOTH, expand=True)

        # Content Text Area with scrollbar
        content_frame = ttk.Frame(detail_paned)
        detail_paned.add(content_frame, weight=2)

        content_scroll = ttk.Scrollbar(content_frame, orient=tk.VERTICAL)
        self.text_content = tk.Text(
            content_frame,
            wrap=tk.WORD,
            font=("Helvetica", 11),
            padx=12,
            pady=10,
            bg="#ffffff",
            relief=tk.FLAT,
            yscrollcommand=content_scroll.set
        )
        content_scroll.config(command=self.text_content.yview)
        self.text_content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Tag styles for text
        self.text_content.tag_configure("teaser", font=("Helvetica", 11, "italic"), foreground="#333333")
        self.text_content.tag_configure("body", font=("Helvetica", 11), foreground="#111111")
        self.text_content.tag_configure("section", font=("Helvetica", 11, "bold"), foreground="#004488")
        self.text_content.tag_configure("attachment_link", font=("Helvetica", 10, "underline"), foreground="#0066cc")
        self.text_content.tag_configure("attachment_missing", font=("Helvetica", 10), foreground="#777777")
        self.text_content.tag_configure("attachment_status", font=("Helvetica", 9), foreground="#555555")

        self.text_content.tag_bind("attachment_link", "<Enter>", lambda e: self.text_content.config(cursor="hand2"))
        self.text_content.tag_bind("attachment_link", "<Leave>", lambda e: self.text_content.config(cursor=""))

        # Gallery Frame
        gallery_container = ttk.LabelFrame(detail_paned, text="📸 Image Gallery (Click thumbnail to view large)", padding=6)
        detail_paned.add(gallery_container, weight=1)

        # Scrollable canvas for thumbnails
        self.gallery_canvas = tk.Canvas(gallery_container, bg="#f5f5f5", highlightthickness=0)
        gallery_scroll_x = ttk.Scrollbar(gallery_container, orient=tk.HORIZONTAL, command=self.gallery_canvas.xview)
        self.gallery_canvas.configure(xscrollcommand=gallery_scroll_x.set)

        self.gallery_inner = tk.Frame(self.gallery_canvas, bg="#f5f5f5")
        self.gallery_canvas_window = self.gallery_canvas.create_window((0, 0), window=self.gallery_inner, anchor="nw")

        self.gallery_inner.bind("<Configure>", lambda e: self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all")))
        self.gallery_canvas.pack(fill=tk.BOTH, expand=True)
        gallery_scroll_x.pack(fill=tk.X)

    def _load_data(self):
        raw_data = []
        if self.json_path.exists():
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
            except Exception as e:
                messagebox.showerror("JSON Load Error", f"Failed to parse bulletin JSON file:\n{e}")
                return
        elif not (self.calendar_json_path and self.calendar_json_path.exists()):
            messagebox.showerror("File Not Found", f"Could not find bulletin JSON file at:\n{self.json_path}")
            return

        calendar_by_day = {}
        if self.calendar_json_path and self.calendar_json_path.exists():
            try:
                with open(self.calendar_json_path, "r", encoding="utf-8") as f:
                    cal_data = json.load(f)
                    for entry in cal_data or []:
                        items = entry.get("CalendarItems") or []
                        if items:
                            day_key = (entry.get("Day") or "")[:10]
                            if day_key:
                                calendar_by_day.setdefault(day_key, []).extend(items)
            except Exception as e:
                print(f"Failed to parse calendar JSON file: {e}")

        self.all_entries = []
        days_with_entries = set()

        for item in raw_data:
            date_raw = item.get("NewsDate") or item.get("PublishDate") or ""
            day_key = date_raw[:10] if date_raw else ""
            if day_key:
                days_with_entries.add(day_key)

            attachments = item.get("Attachments") or []
            matched_attachments = self.image_index.find_images(attachments, date_raw)

            # Build gallery images for this entry
            entry_images = []
            seen_image_paths = set()

            for att in matched_attachments:
                if att.get("exists") and att.get("is_image") and att.get("path"):
                    resolved = att["path"].resolve()
                    if resolved not in seen_image_paths:
                        seen_image_paths.add(resolved)
                        entry_images.append(att)

            # Add all images from the date folder for this day
            if day_key:
                day_imgs = self.image_index.get_day_images(day_key)
                for img_path in day_imgs:
                    resolved = img_path.resolve()
                    if resolved not in seen_image_paths:
                        seen_image_paths.add(resolved)
                        entry_images.append({
                            "id": "",
                            "title": img_path.name,
                            "path": img_path,
                            "is_image": True,
                            "exists": True
                        })

            total_imgs_count = len(entry_images)
            total_atts_count = len(attachments)
            content = clean_html(item.get("Content"))

            self.all_entries.append({
                "raw": item,
                "title": item.get("Title") or "(Untitled)",
                "date_raw": date_raw,
                "date_fmt": parse_datetime(date_raw),
                "teaser": clean_html(item.get("Teaser")),
                "content": content,
                "feed_item_id": item.get("FeedItemId"),
                "attachments": attachments,
                "matched_attachments": matched_attachments,
                "matched_images": entry_images,
                "has_images": total_imgs_count > 0,
                "image_count": total_imgs_count,
                "attachment_count": total_atts_count
            })

        # Append calendar items to existing date entries or create new entries
        for day_key, cal_items in calendar_by_day.items():
            cal_text = format_calendar_items(cal_items)
            if day_key in days_with_entries:
                for entry in self.all_entries:
                    if (entry.get("date_raw") or "")[:10] == day_key:
                        if entry["content"]:
                            entry["content"] = entry["content"] + "\n\n" + cal_text
                        else:
                            entry["content"] = cal_text
            else:
                day_imgs = self.image_index.get_day_images(day_key)
                entry_images = [
                    {
                        "id": "",
                        "title": img_path.name,
                        "path": img_path,
                        "is_image": True,
                        "exists": True
                    }
                    for img_path in day_imgs
                ]
                date_raw = f"{day_key}T00:00:00"
                title = get_calendar_title(cal_items)
                self.all_entries.append({
                    "raw": {
                        "Title": title,
                        "NewsDate": date_raw,
                        "PublishDate": date_raw,
                        "Attachments": [],
                        "CalendarItems": cal_items,
                    },
                    "title": title,
                    "date_raw": date_raw,
                    "date_fmt": parse_datetime(date_raw),
                    "teaser": "",
                    "content": cal_text,
                    "feed_item_id": None,
                    "attachments": [],
                    "matched_attachments": [],
                    "matched_images": entry_images,
                    "has_images": len(entry_images) > 0,
                    "image_count": len(entry_images),
                    "attachment_count": 0
                })
                days_with_entries.add(day_key)

        # Add new entries for days where images exist but no entry exists yet
        all_img_days = self.image_index.get_all_days_with_images()
        for day_key in all_img_days:
            if day_key not in days_with_entries:
                day_imgs = self.image_index.get_day_images(day_key)
                if not day_imgs:
                    continue

                entry_images = [
                    {
                        "id": "",
                        "title": img_path.name,
                        "path": img_path,
                        "is_image": True,
                        "exists": True
                    }
                    for img_path in day_imgs
                ]

                date_raw = f"{day_key}T00:00:00"
                self.all_entries.append({
                    "raw": {
                        "Title": "Gallery",
                        "NewsDate": date_raw,
                        "PublishDate": date_raw,
                        "Attachments": [],
                    },
                    "title": "Gallery",
                    "date_raw": date_raw,
                    "date_fmt": parse_datetime(date_raw),
                    "teaser": "",
                    "content": "",
                    "feed_item_id": None,
                    "attachments": [],
                    "matched_attachments": [],
                    "matched_images": entry_images,
                    "has_images": True,
                    "image_count": len(entry_images),
                    "attachment_count": 0
                })
                days_with_entries.add(day_key)

        self._apply_filter()

    def _toggle_sort(self):
        self.sort_desc_var.set(not self.sort_desc_var.get())
        if self.sort_desc_var.get():
            self.btn_sort.config(text="⇅ Toggle Date Order (Newest First)")
        else:
            self.btn_sort.config(text="⇅ Toggle Date Order (Oldest First)")
        self._apply_filter()

    def _apply_filter(self):
        query = self.search_var.get().strip().lower()
        only_images = self.only_with_images_var.get()

        self.filtered_entries = []
        for entry in self.all_entries:
            if only_images and not entry["has_images"]:
                continue
            if query:
                match_title = query in entry["title"].lower()
                match_teaser = query in entry["teaser"].lower()
                match_content = query in entry["content"].lower()
                match_date = query in entry["date_fmt"].lower()
                if not (match_title or match_teaser or match_content or match_date):
                    continue
            self.filtered_entries.append(entry)

        # Sort
        reverse = self.sort_desc_var.get()
        self.filtered_entries.sort(key=lambda x: x["date_raw"] or "", reverse=reverse)

        # Populate treeview
        self.tree.delete(*self.tree.get_children())
        for idx, entry in enumerate(self.filtered_entries):
            img_badge = f"{entry['image_count']}" if entry['image_count'] > 0 else ""
            att_badge = f"{entry['attachment_count']}" if entry['attachment_count'] > 0 else ""
            self.tree.insert("", tk.END, iid=str(idx), values=(entry["date_fmt"], entry["title"], img_badge, att_badge))

        self.lbl_stats.config(text=f"Showing {len(self.filtered_entries)} of {len(self.all_entries)} entries")

        # Select first entry if available
        if self.filtered_entries:
            self.tree.selection_set("0")
            self.tree.focus("0")
            self._show_entry(self.filtered_entries[0])
        else:
            self._clear_detail()

    def _on_entry_selected(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        if 0 <= idx < len(self.filtered_entries):
            self._show_entry(self.filtered_entries[idx])

    def _clear_detail(self):
        self.lbl_entry_title.config(text="No entries match the filter")
        self.lbl_entry_meta.config(text="")
        self.text_content.delete("1.0", tk.END)
        for child in self.gallery_inner.winfo_children():
            child.destroy()
        self.thumbnail_images.clear()

    def _show_entry(self, entry: dict):
        self.current_entry = entry

        # Header
        self.lbl_entry_title.config(text=entry["title"])
        meta_parts = []
        if entry["date_fmt"]:
            meta_parts.append(f"📅 {entry['date_fmt']}")
        if entry["feed_item_id"]:
            meta_parts.append(f"ID: {entry['feed_item_id']}")
        if entry["attachments"]:
            meta_parts.append(f"Attachments: {len(entry['attachments'])}")
        self.lbl_entry_meta.config(text="  •  ".join(meta_parts))

        # Content Text
        self.text_content.config(state=tk.NORMAL)
        self.text_content.delete("1.0", tk.END)

        # Clear previous attachment tags
        for tag in list(self.text_content.tag_names()):
            if tag.startswith("att_link_"):
                self.text_content.tag_delete(tag)

        if entry["teaser"]:
            self.text_content.insert(tk.END, entry["teaser"] + "\n\n", "teaser")

        if entry["content"]:
            # If teaser is identical to start of content, avoid duplicating
            if entry["teaser"] and entry["content"].startswith(entry["teaser"]):
                body = entry["content"][len(entry["teaser"]):].strip()
                if body:
                    self.text_content.insert(tk.END, body + "\n\n", "body")
            else:
                self.text_content.insert(tk.END, entry["content"] + "\n\n", "body")

        # List all attachments at the bottom of the text if any
        if entry["attachments"]:
            self.text_content.insert(tk.END, "— Attachments (click to open) —\n", "section")
            matched_atts = entry.get("matched_attachments") or entry.get("matched_images", [])
            for idx, att in enumerate(matched_atts):
                tag_name = f"att_link_{idx}"
                self.text_content.insert(tk.END, "• ")
                if att.get("exists") and att.get("path"):
                    self.text_content.insert(tk.END, att["title"], ("attachment_link", tag_name))
                    self.text_content.insert(tk.END, " [✓ on disk]\n", "attachment_status")

                    att_path = att["path"]
                    def _make_open_handler(p):
                        return lambda event: open_file_with_default_app(p)
                    self.text_content.tag_bind(tag_name, "<Button-1>", _make_open_handler(att_path))
                else:
                    self.text_content.insert(tk.END, att["title"], ("attachment_missing", tag_name))
                    self.text_content.insert(tk.END, " [✗ not downloaded]\n", "attachment_status")

                    att_title = att["title"]
                    def _make_missing_handler(t):
                        return lambda event: messagebox.showwarning(
                            "Attachment Not Found",
                            f"The attachment '{t}' is not downloaded locally."
                        )
                    self.text_content.tag_bind(tag_name, "<Button-1>", _make_missing_handler(att_title))

        self.text_content.config(state=tk.DISABLED)

        # Build Gallery
        for child in self.gallery_inner.winfo_children():
            child.destroy()
        self.thumbnail_images.clear()

        images = [img for img in entry["matched_images"] if img.get("exists") and img.get("is_image")]

        if not images:
            no_img_lbl = tk.Label(self.gallery_inner, text="No images linked to this post.", bg="#f5f5f5", fg="#888888", font=("Helvetica", 10, "italic"), pady=20, padx=20)
            no_img_lbl.pack(side=tk.LEFT)
            return

        for idx, img_info in enumerate(images):
            thumb_frame = tk.Frame(self.gallery_inner, bg="#ffffff", bd=1, relief=tk.SOLID, padx=4, pady=4)
            thumb_frame.pack(side=tk.LEFT, padx=6, pady=6)

            thumb_photo = self._create_thumbnail(img_info["path"])
            if thumb_photo:
                self.thumbnail_images.append(thumb_photo)
                img_btn = tk.Button(
                    thumb_frame,
                    image=thumb_photo,
                    bg="#ffffff",
                    activebackground="#e0e0e0",
                    relief=tk.FLAT,
                    cursor="hand2",
                    command=lambda i=idx, img_list=images: self._open_image_viewer(img_list, i)
                )
                img_btn.pack()
            else:
                lbl = tk.Label(thumb_frame, text=img_info["title"], width=30, height=12, bg="#eeeeee")
                lbl.pack()

            caption = get_image_description(img_info.get("path"))
            lbl_caption = tk.Label(thumb_frame, text=caption, font=("Helvetica", 8), bg="#ffffff", fg="#444444", wraplength=230, justify=tk.CENTER)
            lbl_caption.pack(pady=(2, 0))

    def _create_thumbnail(self, path: Path, size=(240, 180)):
        if not HAS_PIL:
            return None
        try:
            im = Image.open(path)
            im.thumbnail(size, Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(im)
        except Exception as e:
            print(f"Failed to generate thumbnail for {path}: {e}")
            return None

    def _open_image_viewer(self, image_list: list[dict], index: int):
        ImageViewerDialog(self, image_list, index)


def main():
    parser = argparse.ArgumentParser(description="View PariKita bulletin posts and gallery images.")
    parser.add_argument(
        "--json",
        type=Path,
        default=Path("parikita_backup/json/bulletin_all.json"),
        help="Path to bulletin_all.json"
    )
    parser.add_argument(
        "--calendar-json",
        type=Path,
        default=Path("parikita_backup/json/calendar_entries.json"),
        help="Path to calendar_entries.json"
    )
    parser.add_argument(
        "--images",
        type=Path,
        nargs="*",
        default=[
            Path("parikita_backup/downloads/images"),
            Path("parikita_backup/downloads/attachments"),
            Path("parikita_backup/downloads/mail_attachments"),
        ],
        help="Directories containing downloaded images and attachments"
    )

    args = parser.parse_args()

    app = BulletinViewerApp(args.json, args.images, calendar_json_path=args.calendar_json)
    app.mainloop()


if __name__ == "__main__":
    main()
