# -*- coding: utf-8 -*-
"""
ربات پایش موجودی کویر تایر
مرورگر Chrome باید روی ویندوز نصب باشد.
ورود به حساب و پرداخت توسط خود کاربر انجام می‌شود.
"""
import os
import re
import sys
import time
import queue
import threading
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

PRODUCTS_URL = "https://kavirtire.ir/products"
ESALE_URL = "https://kavirtire.ir/esale"
ESALE_PRODUCTS_URL = "https://kavirtire.ir/esale/products"
INTERVAL = 4

UNAVAILABLE = (
    "اتمام موجودی", "ناموجود", "اتمام‌موجودی", "موجود نیست",
    "در حال حاضر موجود نیست", "غیرفعال"
)
AVAILABLE_WORDS = (
    "افزودن به سبد خرید", "افزودن به سبد", "اضافه به سبد",
    "سبد خرید", "افزودن", "اضافه کردن", "ثبت سفارش"
)

def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def find_chrome():
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for item in candidates:
        if item and Path(item).is_file():
            return item
    return None

def norm(s):
    return " ".join((s or "").replace("\u200c", " ").split()).casefold()

class KavirBot:
    def __init__(self, root):
        self.root = root
        self.root.title("ربات پایش موجودی کویر تایر")
        self.root.geometry("900x690")
        self.root.minsize(820, 620)
        self.root.configure(bg="#f2f4f7")
        self.events = queue.Queue()
        self.commands = queue.Queue()
        self.worker = None
        self.browser_ready = False
        self.monitoring = False
        self.products = []
        self._build_ui()
        self.root.after(150, self._poll_events)
        self.log("برنامه آماده است. ابتدا مرورگر را باز کنید.")
        self.set_status("لطفاً ابتدا مرورگر را باز کنید.")

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TButton", font=("Tahoma", 9), padding=6)
        style.configure("TLabel", font=("Tahoma", 9), background="#f2f4f7")
        style.configure("TLabelframe.Label", font=("Tahoma", 10, "bold"))
        style.configure("Title.TLabel", font=("Tahoma", 19, "bold"), foreground="#172554")
        style.configure("Status.TLabel", font=("Tahoma", 10, "bold"), foreground="#1d4ed8")

        header = ttk.Frame(self.root, padding=(18, 14))
        header.pack(fill="x")
        ttk.Label(header, text="پایش موجودی کویر تایر", style="Title.TLabel").pack(anchor="e")
        ttk.Label(header, text="انتخاب محصول، ورود به حساب کاربری و پایش خودکار موجودی",
                  font=("Tahoma", 9)).pack(anchor="e", pady=(5, 0))

        group = ttk.LabelFrame(self.root, text="مشخصات محصول", padding=12)
        group.pack(fill="x", padx=14, pady=7)

        ttk.Button(group, text="دریافت / نوسازی فهرست محصولات سایت",
                   command=self.fetch_products).grid(row=0, column=0, padx=5, pady=6, sticky="w")
        ttk.Label(group, text="محصولات استخراج‌شده از سایت:").grid(row=0, column=1, sticky="e")
        self.product_var = tk.StringVar(value="175/60R13 | Special KB2000")
        self.product_combo = ttk.Combobox(group, textvariable=self.product_var,
                                          values=[], width=44, state="normal", justify="right")
        self.product_combo.grid(row=1, column=0, padx=5, pady=6, sticky="ew")
        ttk.Label(group, text="انتخاب محصول:").grid(row=1, column=1, sticky="e")

        self.size_var = tk.StringVar(value="175/60R13")
        self.model_var = tk.StringVar(value="Special KB2000")
        ttk.Entry(group, textvariable=self.size_var, width=24, justify="right").grid(
            row=2, column=0, padx=5, pady=5, sticky="w")
        ttk.Label(group, text="سایز:").grid(row=2, column=1, sticky="e")
        ttk.Entry(group, textvariable=self.model_var, width=24, justify="right").grid(
            row=3, column=0, padx=5, pady=5, sticky="w")
        ttk.Label(group, text="مدل / مشخصات:").grid(row=3, column=1, sticky="e")

        self.qty_var = tk.IntVar(value=2)
        ttk.Spinbox(group, from_=1, to=4, textvariable=self.qty_var,
                    width=8, justify="center").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        ttk.Label(group, text="تعداد حلقه (۱ تا ۴):").grid(row=4, column=1, sticky="e")

        ttk.Button(group, text="افزودن محصول دستی به فهرست",
                   command=self.add_manual).grid(row=5, column=0, padx=5, pady=8, sticky="w")
        group.columnconfigure(0, weight=1)

        actions = ttk.Frame(self.root, padding=(14, 8))
        actions.pack(fill="x")
        self.open_btn = ttk.Button(actions, text="باز کردن مرورگر و ورود", command=self.open_browser)
        self.open_btn.pack(side="right", padx=4)
        self.start_btn = ttk.Button(actions, text="شروع پایش (هر ۴ ثانیه)", command=self.start_monitor, state="disabled")
        self.start_btn.pack(side="right", padx=4)
        self.stop_btn = ttk.Button(actions, text="توقف", command=self.stop_monitor, state="disabled")
        self.stop_btn.pack(side="right", padx=4)
        ttk.Button(actions, text="رفتن به صفحه فروش", command=self.go_sale).pack(side="right", padx=4)

        self.status_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel",
                  wraplength=850, justify="right").pack(fill="x", padx=18, pady=(4, 8))

        log_frame = ttk.LabelFrame(self.root, text="گزارش فعالیت", padding=8)
        log_frame.pack(fill="both", expand=True, padx=14, pady=(2, 14))
        self.log_box = tk.Text(log_frame, height=15, wrap="word", font=("Tahoma", 9),
                               bg="white", fg="#172033", relief="flat")
        self.log_box.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(log_frame, command=self.log_box.yview)
        scroll.pack(side="right", fill="y")
        self.log_box.configure(yscrollcommand=scroll.set, state="disabled")

        note = ttk.Label(self.root, text="توجه: ورود به حساب، انتخاب درگاه و پرداخت فقط توسط کاربر انجام می‌شود.",
                         foreground="#7c2d12")
        note.pack(anchor="e", padx=18, pady=(0, 8))

    def log(self, msg):
        stamp = time.strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{stamp}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def set_status(self, msg):
        self.status_var.set(msg)

    def post(self, kind, value=None):
        self.events.put((kind, value))

    def _poll_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self.log(value)
                elif kind == "status":
                    self.set_status(value)
                elif kind == "products":
                    self.products = value
                    self.product_combo["values"] = value
                    if value:
                        # مقدار پیش‌فرض Special KB2000 حفظ می‌شود.
                        preferred = next((p for p in value if "175/60R13" in p and "KB2000" in p), None)
                        if preferred:
                            self.product_var.set(preferred)
                        self.log(f"{len(value)} محصول از سایت دریافت شد.")
                elif kind == "ready":
                    self.browser_ready = True
                    self.start_btn.configure(state="normal")
                elif kind == "monitor":
                    self.monitoring = bool(value)
                    self.start_btn.configure(state="disabled" if value else "normal")
                    self.stop_btn.configure(state="normal" if value else "disabled")
                elif kind == "found":
                    self.monitoring = False
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    try:
                        self.root.bell()
                    except Exception:
                        pass
                    messagebox.showinfo("محصول موجود شد",
                        "دکمه افزودن به سبد خرید کلیک شد.\n"
                        "لطفاً صفحه سبد / مرحله بعد را بررسی کنید، تعداد حلقه را کنترل کنید "
                        "و خرید را شخصاً ادامه دهید.")
                elif kind == "error":
                    self.log("خطا: " + str(value))
        except queue.Empty:
            pass
        self.root.after(150, self._poll_events)

    def _ensure_worker(self):
        if not self.worker or not self.worker.is_alive():
            self.worker = threading.Thread(target=self._browser_worker, daemon=True)
            self.worker.start()

    def open_browser(self):
        if self.browser_ready:
            self.commands.put(("open", None))
            return
        self._ensure_worker()
        self.commands.put(("open", None))

    def fetch_products(self):
        self._ensure_worker()
        self.commands.put(("fetch", None))

    def go_sale(self):
        self._ensure_worker()
        self.commands.put(("sale", None))

    def start_monitor(self):
        if not self.browser_ready:
            messagebox.showwarning("مرورگر باز نیست", "ابتدا مرورگر را باز کنید و وارد حساب کاربری شوید.")
            return
        size, model = self._selected()
        if not size or not model:
            messagebox.showwarning("مشخصات محصول", "سایز و مدل محصول را وارد یا انتخاب کنید.")
            return
        try:
            qty = int(self.qty_var.get())
            if qty < 1 or qty > 4:
                raise ValueError()
        except Exception:
            messagebox.showwarning("تعداد نامعتبر", "تعداد حلقه باید بین ۱ تا ۴ باشد.")
            return
        self.commands.put(("start", (size, model, qty)))
        self.log(f"درخواست شروع پایش برای {size} - {model} | تعداد انتخابی: {qty}")
        self.set_status("پایش آغاز شد؛ هر ۴ ثانیه موجودی بررسی می‌شود.")

    def stop_monitor(self):
        self.commands.put(("stop", None))

    def _selected(self):
        raw = self.product_var.get().strip()
        # انتخاب از فهرست یا ورود دستی در فیلدهای سایز/مدل
        if raw and "|" in raw:
            a, b = raw.split("|", 1)
            return a.strip(), b.strip()
        return self.size_var.get().strip(), self.model_var.get().strip()

    def add_manual(self):
        size, model = self.size_var.get().strip(), self.model_var.get().strip()
        if not size or not model:
            messagebox.showwarning("اطلاعات ناقص", "سایز و مدل را وارد کنید.")
            return
        item = f"{size} | {model}"
        values = list(self.product_combo["values"])
        if item not in values:
            values.append(item)
            self.product_combo["values"] = values
        self.product_var.set(item)
        self.log(f"محصول دستی اضافه شد: {item}")

    def _browser_worker(self):
        pw = None
        context = None
        page = None
        monitoring = False
        try:
            while True:
                try:
                    cmd, data = self.commands.get(timeout=0.2)
                except queue.Empty:
                    if monitoring and page:
                        cycle_start = time.monotonic()
                        if self._monitor_once(page, data_cache):
                            monitoring = False
                            self.post("monitor", False)
                        elapsed = time.monotonic() - cycle_start
                        time.sleep(max(0, INTERVAL - elapsed))
                    continue

                if cmd == "open":
                    if context:
                        try:
                            page.bring_to_front()
                        except Exception:
                            pass
                        continue
                    chrome = find_chrome()
                    if not chrome:
                        self.post("error", "Google Chrome پیدا نشد. لطفاً Chrome را نصب کنید.")
                        continue
                    pw = sync_playwright().start()
                    profile = str(app_dir() / "kavir_chrome_profile")
                    context = pw.chromium.launch_persistent_context(
                        user_data_dir=profile,
                        executable_path=chrome,
                        headless=False,
                        viewport={"width": 1440, "height": 950},
                        args=["--start-maximized"],
                        ignore_default_args=["--no-sandbox"]
                    )
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(PRODUCTS_URL, wait_until="domcontentloaded", timeout=60000)
                    self.post("status", "مرورگر باز شد. در صورت نیاز وارد حساب سایت شوید؛ سپس صفحه فروش را باز کنید.")
                    self.post("log", "Chrome با پروفایل اختصاصی برنامه باز شد.")
                    self.post("ready", True)

                elif cmd == "fetch":
                    if not page:
                        self.post("error", "ابتدا دکمه باز کردن مرورگر را بزنید.")
                        continue
                    page.goto(PRODUCTS_URL, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1800)
                    items = self._scrape_products(page)
                    self.post("products", items)
                    self.post("status", "فهرست محصولات دریافت شد. برای ورود به حساب، صفحه فروش را باز کنید.")

                elif cmd == "sale":
                    if not page:
                        self.post("error", "ابتدا مرورگر را باز کنید.")
                        continue
                    page.goto(ESALE_URL, wait_until="domcontentloaded", timeout=60000)
                    self.post("status", "لطفاً ابتدا محصول خود را انتخاب یا وارد کنید و به حساب کاربری خود در سایت کویر تایر وارد شوید سپس وارد صفحه خرید بشوید و دکمه پایش برنامه را بزنید...")
                    self.post("log", "صفحه فروش کویر تایر باز شد. ورود به حساب با کاربر است.")

                elif cmd == "start":
                    if not page:
                        self.post("error", "مرورگر باز نیست.")
                        continue
                    size, model, qty = data
                    current = norm(page.url)
                    if "esale" not in current:
                        page.goto(ESALE_PRODUCTS_URL, wait_until="domcontentloaded", timeout=60000)
                    elif current.rstrip("/") == ESALE_URL.rstrip("/"):
                        page.goto(ESALE_PRODUCTS_URL, wait_until="domcontentloaded", timeout=60000)
                    data_cache = (size, model, qty)
                    monitoring = True
                    self.post("monitor", True)
                    self.post("log", f"پایش {size} / {model} شروع شد؛ فاصله بررسی ۴ ثانیه است.")
                    self.post("status", "در حال بررسی موجودی؛ برای توقف از دکمه توقف استفاده کنید.")

                elif cmd == "stop":
                    monitoring = False
                    self.post("monitor", False)
                    self.post("status", "پایش متوقف شد.")
                    self.post("log", "پایش به درخواست کاربر متوقف شد.")

        except Exception as exc:
            self.post("error", repr(exc))
        finally:
            try:
                if context:
                    context.close()
                if pw:
                    pw.stop()
            except Exception:
                pass

    def _scrape_products(self, page):
        # لینک‌های محصول در کاتالوگ عمومی؛ فقط متن‌های دارای الگوی سایز استخراج می‌شوند.
        anchors = page.locator("a")
        found = []
        for i in range(min(anchors.count(), 1000)):
            try:
                a = anchors.nth(i)
                txt = " ".join(a.inner_text(timeout=500).split())
                if re.search(r"\b\d{3}/\d{2,3}R\d{2}\b", txt, re.I) and len(txt) < 180:
                    # سایز را جدا می‌کنیم تا در فرم انتخاب و پایش دقیق باشد.
                    m = re.search(r"\b\d{3}/\d{2,3}R\d{2}\b", txt, re.I)
                    size = m.group(0).upper()
                    model = (txt[:m.start()] + " " + txt[m.end():]).strip(" -|")
                    model = re.sub(r"مشاهده مشخصات", "", model).strip()
                    if model:
                        item = f"{size} | {model}"
                        if item not in found:
                            found.append(item)
            except Exception:
                continue
        # گزینه پیش‌فرض حتی اگر در صفحه عمومی یافت نشود.
        default = "175/60R13 | Special KB2000"
        if default not in found:
            found.insert(0, default)
        return found

    def _monitor_once(self, page, selection):
        size, model, qty = selection
        try:
            # هر چرخه ابتدا دکمه بروزرسانی موجودی را می‌زند.
            refresh = page.get_by_text(re.compile("بروزرسانی موجودی|به.?روزرسانی موجودی"))
            clicked = False
            for i in range(min(refresh.count(), 8)):
                el = refresh.nth(i)
                try:
                    if el.is_visible() and el.is_enabled():
                        el.click(timeout=2500)
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                self.post("status", "دکمه «بروزرسانی موجودی» پیدا نشد؛ صفحه فروش / فهرست محصولات را بررسی کنید.")
                time.sleep(INTERVAL)
                return

            page.wait_for_timeout(900)
            target_text = f"{size} {model}"
            # متن محصول را پیدا کرده و نزدیک‌ترین کارت دارای کنترل خرید را بررسی می‌کند.
            target = page.get_by_text(re.compile(re.escape(size), re.I)).filter(has_text=re.compile(re.escape(model), re.I)).first
            if target.count() == 0:
                target = page.get_by_text(re.compile(re.escape(model), re.I)).first
            if target.count() == 0:
                self.post("status", f"محصول {target_text} در صفحه پیدا نشد؛ مشخصات یا صفحه را بررسی کنید.")
                time.sleep(INTERVAL)
                return

            card = target.locator("xpath=ancestor::*[.//button or .//a][1]")
            if card.count() == 0:
                self.post("status", "کارت محصول پیدا نشد؛ ساختار صفحه ممکن است تغییر کرده باشد.")
                time.sleep(INTERVAL)
                return

            card_text = norm(card.inner_text(timeout=2500))
            if any(norm(w) in card_text for w in UNAVAILABLE):
                self.post("status", f"{target_text}: هنوز ناموجود است.")
                time.sleep(INTERVAL)
                return

            controls = card.locator("button, a, input[type=button], input[type=submit]")
            for i in range(min(controls.count(), 30)):
                el = controls.nth(i)
                try:
                    if not el.is_visible() or not el.is_enabled():
                        continue
                    label = norm(el.inner_text(timeout=700) or el.get_attribute("value") or el.get_attribute("aria-label") or "")
                    if any(norm(w) in label for w in UNAVAILABLE):
                        continue
                    # کلیک فقط با نشانه صریح افزودن/سبد؛ از کلیک حدسی جلوگیری می‌شود.
                    explicit_buy = any(norm(w) in label for w in AVAILABLE_WORDS)
                    generic_buy = any(norm(w) in label for w in ("خرید", "سفارش", "انتخاب"))
                    color_available = False
                    if generic_buy:
                        try:
                            colors = el.evaluate("""e => {
                                const s = getComputedStyle(e);
                                return {bg:s.backgroundColor, color:s.color};
                            }""")
                            def rgb(v):
                                nums = re.findall(r"\\d+(?:\\.\\d+)?", v or "")
                                return tuple(float(x) for x in nums[:3]) if len(nums) >= 3 else (0,0,0)
                            bg = rgb(colors.get("bg", ""))
                            fg = rgb(colors.get("color", ""))
                            bg_green = bg[1] > 95 and bg[1] > bg[0] * 1.18 and bg[1] >= bg[2] * 0.85
                            fg_green = fg[1] > 85 and fg[1] > fg[0] * 1.18 and fg[1] >= fg[2] * 0.85
                            color_available = bg_green or (min(bg) > 220 and fg_green)
                        except Exception:
                            color_available = False
                    if explicit_buy or (generic_buy and color_available):
                        el.click(timeout=5000)
                        page.wait_for_timeout(1800)
                        qty_inputs = page.locator("input[type='number'], input[inputmode='numeric']")
                        qty_set = False
                        for qidx in range(min(qty_inputs.count(), 10)):
                            qbox = qty_inputs.nth(qidx)
                            try:
                                if qbox.is_visible() and qbox.is_enabled():
                                    qbox.fill(str(qty), timeout=1500)
                                    qbox.dispatch_event("change")
                                    qty_set = True
                                    break
                            except Exception:
                                continue
                        self.post("log", f"دکمه خرید برای {target_text} کلیک شد.")
                        self.post("log", f"تعداد {qty} حلقه ثبت شد." if qty_set else "ورودی تعداد شناسایی نشد؛ تعداد را دستی کنترل کنید.")
                        self.post("status", "محصول به مرحله بعد / سبد خرید منتقل شد. تعداد حلقه و اطلاعات را بررسی کنید.")
                        self.post("found", True)
                        return True
                except Exception:
                    continue

            self.post("status", f"{target_text}: دکمه خرید فعال و قابل تشخیص نیست؛ پایش ادامه دارد.")
        except PlaywrightTimeoutError:
            self.post("status", "پاسخ سایت طول کشید؛ نوبت بعدی دوباره تلاش می‌کند.")
        except Exception as exc:
            self.post("error", f"خطا در پایش: {exc}")
        return False


def main():
    root = tk.Tk()
    KavirBot(root)
    root.mainloop()

if __name__ == "__main__":
    main()
