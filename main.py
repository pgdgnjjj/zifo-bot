import json
import os
import logging
import random
import string
from datetime import datetime, timedelta

from flask import Flask, request
from supabase import create_client, Client
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8966599896:AAHtq67RQAp_jDKYz37HPhwhZr0xnbqDCg8"
OWNER_IDS = ["8407513032","8221493883"]

SUPABASE_URL = "https://rnccpzqrjnwreigssxdg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJuY2NwenFyam53cmVpZ3NzeGRnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTEyNzczNjEsImV4cCI6MjEwNjg1MzM2MX0.4xOM3zS0i0tL1rUbriDLHjR_c3_PMribG68H1l0GvqM"

PORT = int(os.getenv("PORT", 8000))

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def gen_order_id():
    return f"ORD-{datetime.now().strftime('%Y%m%d')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"


def gen_req_id():
    return f"TOP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}"


def gen_ref_code(uid):
    return f"REF{str(uid)[-6:]}{random.randint(100, 999)}"


def fmt(p):
    return f"{int(p):,}"


def user_display(uid, uname=None):
    if uname:
        return f"`{uid}` | @{uname}"
    return f"`{uid}` | ندارد"


STATE_KEYS = [
    'awaiting_topup_amount', 'awaiting_topup_receipt', 'sending_config_for',
    'awaiting_wallet_user', 'awaiting_wallet_amount', 'awaiting_add_admin',
    'awaiting_remove_admin', 'awaiting_broadcast', 'awaiting_support',
    'awaiting_product_name', 'awaiting_product_price', 'awaiting_product_stock',
    'awaiting_product_configs', 'awaiting_stock_increase', 'awaiting_stock_decrease',
    'awaiting_user_check', 'awaiting_ban_toggle', 'awaiting_search_user',
    'awaiting_coupon_percent', 'awaiting_coupon_max', 'awaiting_coupon_code',
    'awaiting_ref_bonus', 'awaiting_welcome_msg', 'awaiting_coupon_input',
    'awaiting_order_track', 'awaiting_card_number', 'awaiting_card_holder',
    'awaiting_app_name', 'awaiting_app_file', 'awaiting_apps_text',
    'new_product_name', 'new_product_price', 'new_product_stock', 'new_card_number',
    'wallet_target', 'editing_product_id', 'awaiting_edit_product',
    'awaiting_increase_all', 'awaiting_decrease_all', 'topup_amount',
    'new_app_name'
]


def clear_states(context):
    for k in STATE_KEYS:
        context.user_data.pop(k, None)


async def send_long_message(update, text):
    max_len = 4000
    if len(text) <= max_len:
        await update.message.reply_text(text)
        return
    parts = []
    while len(text) > max_len:
        split_at = text.rfind('\n', 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at])
        text = text[split_at:]
    parts.append(text)
    for part in parts:
        await update.message.reply_text(part)


class DataManager:
    def __init__(self):
        self.data = self.load_data()

    def load_data(self):
        try:
            response = supabase.table("bot_data").select("data").eq("id", 1).execute()
            if response.data and len(response.data) > 0:
                data = response.data[0]["data"]
                data.setdefault("shop_status", {"is_open": True, "closed_message": "🚫 فروشگاه بسته است."})
                data.setdefault("broadcast_history", [])
                data.setdefault("banned_users", [])
                data.setdefault("coupons", {})
                data.setdefault("ref_settings", {"bonus": 5000, "min_purchase": 0, "enabled": True})
                data.setdefault("welcome_msg", "🌟 به فروشگاه Zifo خوش آمدید!")
                data.setdefault("cards", [])
                data.setdefault("apps", [])
                data.setdefault("apps_text", "📱 برای اتصال، از برنامه‌های زیر استفاده کن:")
                self.data = data
                return data
        except Exception as e:
            logger.error(f"Supabase load error: {e}")
        return self.create_empty()

    def create_empty(self):
        data = {
            "owners": OWNER_IDS, "admins": [], "products": [], "users": {},
            "orders": [], "topup_requests": [], "broadcast_history": [],
            "support_username": "@Zifo_support",
            "user_help_text": "🎮 راهنمای خرید",
            "banned_users": [], "coupons": {},
            "ref_settings": {"bonus": 5000, "min_purchase": 0, "enabled": True},
            "welcome_msg": "🌟 به فروشگاه Zifo خوش آمدید!",
            "cards": [], "apps": [],
            "apps_text": "📱 برای اتصال، از برنامه‌های زیر استفاده کن:",
            "shop_status": {"is_open": True, "closed_message": "🚫 فروشگاه بسته است."}
        }
        self.data = data
        self.save_data()
        return data

    def save_data(self, data=None):
        if data is None:
            data = self.data
        try:
            response = supabase.table("bot_data").select("id").eq("id", 1).execute()
            if response.data and len(response.data) > 0:
                supabase.table("bot_data").update({"data": data}).eq("id", 1).execute()
            else:
                supabase.table("bot_data").insert({"data": data}).execute()
        except Exception as e:
            logger.error(f"Supabase save error: {e}")
        self.data = data

    def get_user(self, uid):
        uid = str(uid)
        if uid not in self.data["users"]:
            self.data["users"][uid] = {
                "cart": [], "orders": [], "balance": 0,
                "join_date": datetime.now().strftime('%Y-%m-%d'),
                "username": "", "first_name": "",
                "ref_code": gen_ref_code(uid),
                "invited_by": None, "invited_count": 0
            }
            self.save_data()
        u = self.data["users"][uid]
        if "ref_code" not in u or not u["ref_code"]:
            u["ref_code"] = gen_ref_code(uid)
            self.save_data()
        return u

    def find_user_by_refcode(self, code):
        for uid, u in self.data["users"].items():
            if u.get("ref_code") == code:
                return uid, u
        return None, None

    def is_banned(self, uid):
        return str(uid) in self.data.get("banned_users", [])

    def ban(self, uid):
        uid = str(uid)
        if uid not in self.data["banned_users"]:
            self.data["banned_users"].append(uid)
            self.save_data()
            return True
        return False

    def unban(self, uid):
        uid = str(uid)
        if uid in self.data["banned_users"]:
            self.data["banned_users"].remove(uid)
            self.save_data()
            return True
        return False

    def is_owner(self, uid):
        return str(uid) in self.data["owners"]

    def is_admin(self, uid):
        uid = str(uid)
        return uid in self.data["owners"] or uid in self.data["admins"]

    def add_admin(self, uid):
        uid = str(uid)
        if uid not in self.data["admins"] and uid not in self.data["owners"]:
            self.data["admins"].append(uid)
            self.save_data()
            return True
        return False

    def remove_admin(self, uid):
        uid = str(uid)
        if uid in self.data["admins"]:
            self.data["admins"].remove(uid)
            self.save_data()
            return True
        return False

    def get_product(self, pid):
        return next((p for p in self.data["products"] if p["id"] == pid), None)

    def add_product(self, product):
        new_id = max((p["id"] for p in self.data["products"]), default=0) + 1
        product["id"] = new_id
        product.setdefault("stock", 0)
        product.setdefault("description", "")
        product.setdefault("configs", [])
        product["created_at"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.data["products"].append(product)
        self.save_data()
        return new_id

    def update_product(self, pid, updates):
        for p in self.data["products"]:
            if p["id"] == pid:
                p.update(updates)
                self.save_data()
                return True
        return False

    def delete_product(self, pid):
        before = len(self.data["products"])
        self.data["products"] = [p for p in self.data["products"] if p["id"] != pid]
        if len(self.data["products"]) != before:
            self.save_data()
            return True
        return False

    def adjust_stock(self, pid, delta):
        p = self.get_product(pid)
        if p:
            p["stock"] = max(0, p.get("stock", 0) + delta)
            self.save_data()
            return True
        return False

    def add_order(self, order):
        oid = gen_order_id()
        order["order_id"] = oid
        order["date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.data["orders"].append(order)
        u = self.get_user(order["user_id"])
        u["orders"].append(oid)
        self.save_data()
        return oid

    def get_order(self, oid):
        return next((o for o in self.data["orders"] if o["order_id"] == oid), None)

    def update_order(self, oid, updates):
        o = self.get_order(oid)
        if o:
            o.update(updates)
            self.save_data()
            return True
        return False

    def get_user_orders(self, uid):
        uid = str(uid)
        return [o for o in self.data["orders"] if o.get("user_id") == uid]

    def add_topup(self, req):
        rid = gen_req_id()
        req["request_id"] = rid
        req["date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        req["status"] = "pending"
        self.data["topup_requests"].append(req)
        self.save_data()
        return rid

    def get_topup(self, rid):
        return next((r for r in self.data["topup_requests"] if r["request_id"] == rid), None)

    def update_topup(self, rid, updates):
        r = self.get_topup(rid)
        if r:
            r.update(updates)
            self.save_data()
            return True
        return False

    def add_to_cart(self, uid, pid):
        u = self.get_user(uid)
        p = self.get_product(pid)
        if not p or p.get("stock", 0) <= 0:
            return False
        if any(i["id"] == pid for i in u["cart"]):
            return False
        u["cart"].append({"id": p["id"], "name": p["name"], "price": p["price"]})
        self.save_data()
        return True

    def remove_from_cart(self, uid, idx):
        u = self.get_user(uid)
        if 0 <= idx < len(u["cart"]):
            u["cart"].pop(idx)
            self.save_data()
            return True
        return False

    def clear_cart(self, uid):
        u = self.get_user(uid)
        u["cart"] = []
        self.save_data()

    def cart_total(self, uid):
        return sum(i["price"] for i in self.get_user(uid)["cart"])

    def cart_items(self, uid):
        return self.get_user(uid)["cart"]

    def increase_all(self, amount):
        n = 0
        for uid in self.data["users"]:
            u = self.get_user(uid)
            u["balance"] = u.get("balance", 0) + amount
            n += 1
        self.save_data()
        return n

    def decrease_all(self, amount):
        n = 0
        for uid in self.data["users"]:
            u = self.get_user(uid)
            u["balance"] = max(0, u.get("balance", 0) - amount)
            n += 1
        self.save_data()
        return n

    def add_broadcast(self, sent_msgs, text):
        self.data.setdefault("broadcast_history", [])
        self.data["broadcast_history"].append({
            "sent_messages": sent_msgs, "text": text[:100],
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        if len(self.data["broadcast_history"]) > 3:
            self.data["broadcast_history"] = self.data["broadcast_history"][-3:]
        self.save_data()

    def get_broadcast_history(self):
        return self.data.get("broadcast_history", [])

    def delete_broadcast(self, index):
        h = self.data.get("broadcast_history", [])
        if 0 <= index < len(h):
            removed = h.pop(index)
            self.data["broadcast_history"] = h
            self.save_data()
            return removed
        return None

    def get_coupons(self):
        return self.data.get("coupons", {})

    def add_coupon(self, code, percent, max_uses):
        self.data.setdefault("coupons", {})
        self.data["coupons"][code.upper()] = {
            "percent": percent, "max_uses": max_uses, "used": 0,
            "created": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.save_data()

    def delete_coupon(self, code):
        if code.upper() in self.data.get("coupons", {}):
            del self.data["coupons"][code.upper()]
            self.save_data()
            return True
        return False

    def use_coupon(self, code):
        coupons = self.data.get("coupons", {})
        code = code.upper()
        if code in coupons:
            c = coupons[code]
            if c["used"] < c["max_uses"] or c["max_uses"] == 0:
                c["used"] += 1
                self.save_data()
                return True
        return False

    def get_ref_settings(self):
        return self.data.get("ref_settings", {"bonus": 5000, "min_purchase": 0, "enabled": True})

    def set_ref_settings(self, bonus, min_purchase, enabled):
        self.data["ref_settings"] = {"bonus": bonus, "min_purchase": min_purchase, "enabled": enabled}
        self.save_data()

    def process_referral(self, new_uid, ref_code):
        settings = self.get_ref_settings()
        if not settings.get("enabled", True):
            return None
        inviter_uid, inviter = self.find_user_by_refcode(ref_code)
        if not inviter_uid or inviter_uid == new_uid:
            return None
        new_user = self.get_user(new_uid)
        if new_user.get("invited_by"):
            return None
        new_user["invited_by"] = inviter_uid
        inviter["invited_count"] = inviter.get("invited_count", 0) + 1
        bonus = settings.get("bonus", 5000)
        inviter["balance"] = inviter.get("balance", 0) + bonus
        self.save_data()
        return {"inviter_uid": inviter_uid, "bonus": bonus}

    def get_daily_stats(self, days=7):
        result = []
        today = datetime.now().date()
        for i in range(days - 1, -1, -1):
            day = today - timedelta(days=i)
            day_str = day.strftime('%Y-%m-%d')
            orders = [o for o in self.data["orders"]
                      if o.get("date", "").startswith(day_str) and o.get("status") == "completed"]
            revenue = sum(o["total"] for o in orders)
            result.append({"date": day_str, "orders": len(orders), "revenue": revenue})
        return result


dm = DataManager()


async def safe_edit(message, text, markup=None, reply_markup=None):
    final_markup = reply_markup or markup
    try:
        await message.edit_text(text, reply_markup=final_markup)
    except Exception as e:
        err = str(e).lower()
        if "not modified" not in err and "message to edit" not in err:
            logger.error(f"edit err: {e}")


async def answer_cb(q, text=""):
    try:
        await q.answer(text)
    except Exception:
        pass


def main_kb(uid):
    kb = [
        ["🛍️ محصولات"],
        ["🛒 سبد خرید", "👤 حساب کاربری"],
        ["💰 کیف پول", "📱 برنامه‌های اتصال"],
        ["🎁 دعوت دوستان", "📜 سفارش‌های من"],
        ["🔍 پیگیری سفارش", "ℹ️ راهنما"],
        ["📞 پشتیبانی"]
    ]
    if dm.is_admin(uid):
        kb.append(["⚙️ پنل ادمین"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)
# =========================================================
#                     منوی اصلی
# =========================================================

async def main_menu(upd, ctx):
    clear_states(ctx)
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
    else:
        msg = upd.message
        user = upd.effective_user
    uid = str(user.id)
    if dm.is_banned(uid):
        await msg.reply_text("🚫 مسدود هستی.")
        return
    welcome = dm.data.get("welcome_msg", "🌟 به فروشگاه Zifo خوش آمدید!")
    await msg.reply_text(welcome, reply_markup=main_kb(uid))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    user = update.effective_user
    uid = str(user.id)

    if context.args and len(context.args) > 0:
        ref_code = context.args[0]
        result = dm.process_referral(uid, ref_code)
        if result:
            try:
                await context.bot.send_message(
                    result["inviter_uid"],
                    f"🎁 یه کاربر با لینک دعوتت عضو شد!\n💰 {fmt(result['bonus'])} تومان به کیف پولت اضافه شد."
                )
            except Exception:
                pass

    u = dm.get_user(uid)
    u["username"] = user.username or ""
    u["first_name"] = user.first_name or ""
    dm.save_data()
    await main_menu(update, context)


async def cancel(update: Update, context):
    clear_states(context)
    await main_menu(update, context)


# =========================================================
#                     برنامه‌های اتصال
# =========================================================

async def show_apps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    apps = dm.data.get("apps", [])
    apps_text = dm.data.get("apps_text", "📱 برای اتصال، از برنامه‌های زیر استفاده کن:")
    if not apps:
        await update.message.reply_text("📭 برنامه‌ای برای اتصال موجود نیست.")
        return
    await update.message.reply_text(apps_text)
    for app in apps:
        try:
            if app.get("file_id"):
                await context.bot.send_document(
                    update.effective_user.id,
                    app["file_id"],
                    caption=f"📱 {app.get('name', 'برنامه')}"
                )
            elif app.get("link"):
                await update.message.reply_text(f"📱 {app.get('name', 'برنامه')}\n{app['link']}")
        except Exception as e:
            logger.error(f"App send err: {e}")


# =========================================================
#                     محصولات
# =========================================================

async def show_products(upd, ctx):
    clear_states(ctx)
    shop = dm.data["shop_status"]
    if not shop["is_open"]:
        if isinstance(upd, CallbackQuery):
            await answer_cb(upd)
            await safe_edit(upd.message, shop["closed_message"])
        else:
            await upd.message.reply_text(shop["closed_message"])
        return
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
    else:
        msg = upd.message
        user = upd.effective_user
    if dm.is_banned(str(user.id)):
        await msg.reply_text("🚫 مسدود هستی.")
        return
    products = dm.data["products"]
    if not products:
        await msg.reply_text("📭 محصولی نیست.")
        return
    kb = []
    for p in products:
        c = "🟢" if p.get("stock", 0) > 0 else "🔴"
        kb.append([InlineKeyboardButton(f"{c} {p['name']} | {fmt(p['price'])} ت", callback_data=f"prod_{p['id']}")])
    kb.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_menu")])
    markup = InlineKeyboardMarkup(kb)
    if isinstance(upd, CallbackQuery):
        await safe_edit(msg, "🛍️ **محصولات فروشگاه**", reply_markup=markup)
    else:
        await msg.reply_text("🛍️ **محصولات فروشگاه**", reply_markup=markup)


async def product_details(upd, ctx, pid):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    p = dm.get_product(pid)
    if not p:
        await msg.reply_text("❌ محصول یافت نشد.")
        return
    stock = p.get("stock", 0)
    configs_count = len(p.get("configs", []))
    text = (
        f"🎯 **{p['name']}**\n"
        f"💰 قیمت: {fmt(p['price'])} تومان\n"
        f"📦 موجودی: {stock}\n"
        f"🔑 کانفیگ آماده: {configs_count}\n"
        f"📝 {p.get('description', '---')}"
    )
    kb = []
    if stock > 0:
        kb.append([InlineKeyboardButton("🛒 افزودن به سبد", callback_data=f"cartadd_{pid}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="products_back")])
    markup = InlineKeyboardMarkup(kb)
    await safe_edit(msg, text, reply_markup=markup)


async def add_to_cart_cb(upd, ctx, pid):
    if isinstance(upd, CallbackQuery):
        user = upd.from_user
        await answer_cb(upd)
    else:
        user = upd.effective_user
    p = dm.get_product(pid)
    if not p or p.get("stock", 0) <= 0:
        await answer_cb(upd, "❌ ناموجود")
        return
    if dm.add_to_cart(str(user.id), pid):
        await answer_cb(upd, f"✅ {p['name']} اضافه شد")
        await show_cart(upd, ctx)
    else:
        await answer_cb(upd, "⚠️ قبلاً در سبد هست")


# =========================================================
#                     سبد خرید
# =========================================================

async def show_cart(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
    else:
        msg = upd.message
        user = upd.effective_user
    uid = str(user.id)
    cart = dm.cart_items(uid)
    if not cart:
        text = "🛒 **سبد خرید خالی است.**"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ محصولات", callback_data="products_back")]])
        try:
            await safe_edit(msg, text, reply_markup=kb)
        except Exception:
            await msg.reply_text(text, reply_markup=kb)
        return
    total = dm.cart_total(uid)
    text = "🛒 **سبد خرید:**\n\n"
    for i, it in enumerate(cart, 1):
        text += f"{i}. {it['name']} - {fmt(it['price'])} ت\n"
    text += f"\n💰 **مجموع:** {fmt(total)} ت"

    discount = ctx.user_data.get('applied_discount')
    if discount:
        new_total = int(total * (100 - discount['percent']) / 100)
        text += f"\n🎟️ تخفیف: {discount['percent']}%\n💰 **مبلغ نهایی:** {fmt(new_total)} ت"

    kb = []
    for i, it in enumerate(cart):
        kb.append([InlineKeyboardButton(f"❌ حذف {it['name']}", callback_data=f"cartdel_{i}")])
    kb.append([InlineKeyboardButton("🎟️ کد تخفیف", callback_data="apply_coupon")])
    kb.append([InlineKeyboardButton("✅ پرداخت با کیف پول", callback_data="checkout")])
    kb.append([
        InlineKeyboardButton("➕ ادامه خرید", callback_data="products_back"),
        InlineKeyboardButton("🗑️ خالی کردن", callback_data="clearcart")
    ])
    markup = InlineKeyboardMarkup(kb)
    try:
        await safe_edit(msg, text, reply_markup=markup)
    except Exception:
        await msg.reply_text(text, reply_markup=markup)


async def remove_cart_item(upd, ctx, idx):
    if isinstance(upd, CallbackQuery):
        user = upd.from_user
        await answer_cb(upd)
    else:
        user = upd.effective_user
    uid = str(user.id)
    dm.remove_from_cart(uid, idx)
    await show_cart(upd, ctx)


async def clear_cart(upd, ctx):
    if isinstance(upd, CallbackQuery):
        user = upd.from_user
        await answer_cb(upd)
    else:
        user = upd.effective_user
    dm.clear_cart(str(user.id))
    await show_cart(upd, ctx)


async def checkout(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
    else:
        msg = upd.message
        user = upd.effective_user
    uid = str(user.id)
    cart = dm.cart_items(uid)
    if not cart:
        await msg.reply_text("سبد خالیه.")
        return

    total = dm.cart_total(uid)
    discount = ctx.user_data.get('applied_discount')
    if discount:
        total = int(total * (100 - discount['percent']) / 100)

    bal = dm.get_user(uid).get("balance", 0)
    if bal < total:
        text = f"❌ **موجودی کافی نیست**\n💰 موجودی: {fmt(bal)} ت\n💰 نیاز: {fmt(total)} ت"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💰 شارژ کیف پول", callback_data="request_topup")]])
        await safe_edit(msg, text, reply_markup=kb)
        return

    text = f"✅ **نهایی کردن خرید**\n━━━━━━━━━━\n📦 تعداد: {len(cart)}\n"
    if discount:
        text += f"🎟️ تخفیف: {discount['percent']}%\n"
    text += f"💰 مبلغ نهایی: {fmt(total)} ت\n💳 موجودی: {fmt(bal)} ت\n━━━━━━━━━━\nمطمئنی؟"
    kb = [
        [InlineKeyboardButton("✅ بله، پرداخت", callback_data="pay_wallet")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="show_cart")]
    ]
    markup = InlineKeyboardMarkup(kb)
    await safe_edit(msg, text, reply_markup=markup)


async def pay_wallet(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
    else:
        msg = upd.message
        user = upd.effective_user
    uid = str(user.id)
    cart = dm.cart_items(uid)
    if not cart:
        await msg.reply_text("سبد خالیه.")
        return

    total = dm.cart_total(uid)
    discount = ctx.user_data.get('applied_discount')
    if discount:
        total = int(total * (100 - discount['percent']) / 100)
        dm.use_coupon(discount['code'])

    u = dm.get_user(uid)
    if u.get("balance", 0) < total:
        await msg.reply_text("❌ موجودی کافی نیست.")
        return

    u["balance"] -= total
    order = {
        "user_id": uid,
        "username": u.get("username", ""),
        "first_name": u.get("first_name", ""),
        "items": cart.copy(),
        "total": total,
        "discount": discount['percent'] if discount else 0,
        "status": "waiting_admin",
        "payment_method": "wallet",
        "account_info": None
    }
    oid = dm.add_order(order)
    dm.clear_cart(uid)
    ctx.user_data.pop('applied_discount', None)

    ud = user_display(uid, u.get("username", ""))
    items_str = "\n".join(f"{i['name']} - {fmt(i['price'])} ت" for i in cart)
    text = f"✅ **پرداخت موفق**\n🆔 سفارش: `{oid}`\n💰 {fmt(total)} ت\n\nمنتظر تأیید ادمین باش."
    await safe_edit(msg, text)
    for aid in dm.data["owners"] + dm.data["admins"]:
        try:
            await ctx.bot.send_message(int(aid), f"🛒 **سفارش جدید**\n🆔 `{oid}`\n👤 {ud}\n📦 {items_str}\n💰 {fmt(total)} ت")
        except Exception:
            pass


# =========================================================
#                     کد تخفیف
# =========================================================

async def apply_coupon_prompt(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    clear_states(ctx)
    ctx.user_data['awaiting_coupon_input'] = True
    await msg.reply_text("🎟️ کد تخفیف رو بفرست:\n(برای انصراف /cancel)")


async def handle_coupon_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_coupon_input'):
        return
    code = update.message.text.strip().upper()
    coupons = dm.get_coupons()
    if code not in coupons:
        await update.message.reply_text("❌ کد تخفیف نامعتبر.")
        context.user_data.pop('awaiting_coupon_input', None)
        return
    c = coupons[code]
    if c["max_uses"] > 0 and c["used"] >= c["max_uses"]:
        await update.message.reply_text("❌ ظرفیت کد تخفیف پر شده.")
        context.user_data.pop('awaiting_coupon_input', None)
        return
    context.user_data['applied_discount'] = {"code": code, "percent": c["percent"]}
    context.user_data.pop('awaiting_coupon_input', None)
    await update.message.reply_text(f"✅ کد تخفیف {c['percent']}% اعمال شد.")
    await show_cart(update, context)


# =========================================================
#                     کیف پول
# =========================================================

async def wallet_menu(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
    else:
        msg = upd.message
        user = upd.effective_user
    uid = str(user.id)
    bal = dm.get_user(uid).get("balance", 0)
    text = f"💰 **کیف پول شما**\nموجودی: {fmt(bal)} تومان"
    kb = [
        [InlineKeyboardButton("➕ درخواست شارژ", callback_data="request_topup")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_menu")]
    ]
    markup = InlineKeyboardMarkup(kb)
    if isinstance(upd, CallbackQuery):
        await safe_edit(msg, text, reply_markup=markup)
    else:
        await msg.reply_text(text, reply_markup=markup)


async def request_topup_start(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    clear_states(ctx)
    ctx.user_data['awaiting_topup_amount'] = True
    card = get_active_card()
    await msg.reply_text(
        f"💰 **مبلغ شارژ رو به تومان بنویس:**\n(مثال: 50000)\n\n"
        f"💳 کارت: `{card['number']}`\n"
        f"👤 {card.get('holder', '')}\n\nبرای انصراف /cancel"
    )


async def handle_topup_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_topup_amount'):
        return False
    text = update.message.text.strip()
    if text == "/cancel":
        clear_states(context)
        await main_menu(update, context)
        return True
    if not text.isdigit():
        await update.message.reply_text("❌ عدد معتبر بفرست.")
        return True
    amount = int(text)
    if amount <= 0:
        await update.message.reply_text("❌ مبلغ باید مثبت باشه.")
        return True
    context.user_data['topup_amount'] = amount
    context.user_data['awaiting_topup_amount'] = False
    context.user_data['awaiting_topup_receipt'] = True
    card = get_active_card()
    await update.message.reply_text(
        f"📸 تصویر رسید واریز {fmt(amount)} تومان رو بفرست.\n"
        f"💳 کارت: `{card['number']}`\n(برای انصراف /cancel)"
    )
    return True


async def handle_topup_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_topup_receipt'):
        return False
    if not update.message.photo:
        await update.message.reply_text("❌ عکس رسید بفرست.")
        return True
    file_id = update.message.photo[-1].file_id
    amount = context.user_data.get('topup_amount', 0)
    user = update.effective_user
    uid = str(user.id)
    u = dm.get_user(uid)
    req = {
        "user_id": uid, "username": u.get("username", ""),
        "first_name": u.get("first_name", ""),
        "amount": amount, "receipt_photo": file_id
    }
    rid = dm.add_topup(req)
    ud = user_display(uid, u.get("username", ""))
    clear_states(context)
    await update.message.reply_text(f"✅ **درخواست شارژ ثبت شد**\n🆔 `{rid}`\nمنتظر تأیید ادمین باش.")
    for aid in dm.data["owners"] + dm.data["admins"]:
        try:
            await context.bot.send_photo(
                int(aid), file_id,
                caption=f"💰 **شارژ جدید**\n🆔 `{rid}`\n👤 {ud}\n💰 {fmt(amount)} ت"
            )
        except Exception:
            pass
    return True


async def show_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    u = dm.get_user(uid)
    ud = user_display(uid, user.username)
    invited = u.get("invited_count", 0)
    await update.message.reply_text(
        f"👤 **حساب کاربری**\n\n"
        f"👤 {ud}\n"
        f"📛 {u.get('first_name', '-')}\n"
        f"💰 موجودی: {fmt(u.get('balance', 0))} ت\n"
        f"📦 سفارشات: {len(u.get('orders', []))}\n"
        f"🎁 دعوت‌شده‌ها: {invited}",
        reply_markup=main_kb(uid)
    )


async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    u = dm.get_user(uid)
    ref_code = u.get("ref_code", "---")
    settings = dm.get_ref_settings()
    if not settings.get("enabled", True):
        await update.message.reply_text("❌ سیستم دعوت موقتاً غیرفعاله.")
        return
    try:
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
    except Exception:
        bot_username = "YourBot"
    link = f"https://t.me/{bot_username}?start={ref_code}"
    bonus = settings.get("bonus", 5000)
    invited = u.get("invited_count", 0)
    total_earned = invited * bonus
    text = (
        f"🎁 **دعوت دوستان**\n\n"
        f"با دعوت هر دوست، {fmt(bonus)} تومان هدیه بگیر!\n\n"
        f"🔗 **لینک دعوت تو:**\n{link}\n\n"
        f"📊 **آمار تو:**\n"
        f"👥 دعوت‌شده‌ها: {invited}\n"
        f"💰 مجموع درآمد: {fmt(total_earned)} ت"
    )
    await update.message.reply_text(text, reply_markup=main_kb(uid))


async def show_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    orders = dm.get_user_orders(uid)
    if not orders:
        await update.message.reply_text("📭 هنوز سفارشی نداری.")
        return
    orders = sorted(orders, key=lambda x: x.get("date", ""), reverse=True)[:10]
    text = "📜 آخرین سفارش‌های شما:\n\n"
    for o in orders:
        status_emoji = {
            "waiting_admin": "⏳ در انتظار",
            "completed": "✅ تکمیل شده",
            "rejected": "❌ رد شده"
        }.get(o.get("status"), "❓")
        text += (
            f"{status_emoji}\n"
            f"کد: {o['order_id']}\n"
            f"مبلغ: {fmt(o['total'])} ت | تاریخ: {o.get('date', '')[:10]}\n\n"
        )
    await send_long_message(update, text)


async def track_order_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    context.user_data['awaiting_order_track'] = True
    await update.message.reply_text("🔍 **پیگیری سفارش**\nکد سفارش رو بنویس:")


async def handle_track_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_order_track'):
        return
    oid = update.message.text.strip()
    o = dm.get_order(oid)
    if not o:
        await update.message.reply_text("❌ سفارش با این کد پیدا نشد.")
        context.user_data.pop('awaiting_order_track', None)
        return
    status_text = {
        "waiting_admin": "⏳ در انتظار تأیید ادمین",
        "completed": "✅ تکمیل شده",
        "rejected": "❌ رد شده"
    }.get(o.get("status"), "❓ نامشخص")
    items_str = "\n".join(f"• {i['name']}" for i in o.get("items", []))
    text = (
        f"🔍 سفارش {oid}\n\n"
        f"📌 وضعیت: {status_text}\n"
        f"💰 مبلغ: {fmt(o['total'])} ت\n"
        f"📅 تاریخ: {o.get('date', '')}\n\n"
        f"📦 محصولات:\n{items_str}"
    )
    await update.message.reply_text(text, reply_markup=main_kb(update.effective_user.id))
    context.user_data.pop('awaiting_order_track', None)


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = dm.data.get("user_help_text", "راهنما موجود نیست.")
    await update.message.reply_text(txt, reply_markup=main_kb(update.effective_user.id))


async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = dm.data.get("support_username", "@Zifo_support")
    await update.message.reply_text(f"📞 پشتیبانی: {s}", reply_markup=main_kb(update.effective_user.id))
# =========================================================
#                     پنل ادمین
# =========================================================

async def admin_panel(upd, ctx):
    clear_states(ctx)
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
    else:
        msg = upd.message
        user = upd.effective_user
    if not dm.is_admin(user.id):
        await msg.reply_text("❌ دسترسی نداری.")
        return
    owner = dm.is_owner(user.id)
    if owner:
        kb = [
            ["➕ افزودن محصول", "📦 مدیریت محصولات"],
            ["📈 افزایش موجودی", "📉 کسر موجودی"],
            ["💰 افزایش همگانی", "💸 کسر همگانی"],
            ["📋 سفارش‌ها", "📊 آمار ربات"],
            ["📈 آمار فروش", "👥 آمار کاربران"],
            ["🔍 جستجوی کاربر", "💰 درخواست شارژ"],
            ["💰 کیف پول کاربر", "👤 بررسی کاربر"],
            ["🚫 مسدود/آزاد", "🎟️ کد تخفیف"],
            ["🎁 تنظیمات رفرال", "💳 مدیریت کارت‌ها"],
            ["📱 مدیریت برنامه‌ها", "📝 پیام خوش‌آمد"],
            ["🛠 پشتیبانی", "👥 لیست ادمین‌ها"],
            ["➕ ادمین", "➖ ادمین"],
            ["🛒 باز/بستن فروشگاه"],
            ["📢 پیام همگانی", "🗑️ حذف آخرین پیام"],
            ["🔙 بازگشت"]
        ]
    else:
        kb = [
            ["➕ افزودن محصول", "📦 مدیریت محصولات"],
            ["📈 افزایش موجودی", "📉 کسر موجودی"],
            ["📋 سفارش‌ها", "📊 آمار ربات"],
            ["📈 آمار فروش", "👥 آمار کاربران"],
            ["🔍 جستجوی کاربر", "💰 درخواست شارژ"],
            ["💰 کیف پول کاربر", "👤 بررسی کاربر"],
            ["🚫 مسدود/آزاد"],
            ["🔙 بازگشت"]
        ]
    await msg.reply_text("⚙️ **پنل مدیریت**", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))


async def toggle_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_admin(update.effective_user.id):
        return
    cur = dm.data["shop_status"]
    new = not cur["is_open"]
    dm.data["shop_status"]["is_open"] = new
    dm.save_data()
    if new:
        await update.message.reply_text("✅ فروشگاه باز شد.")
    else:
        await update.message.reply_text("🔒 فروشگاه بسته شد.")


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = len(dm.data["users"])
    orders = dm.data["orders"]
    completed = [o for o in orders if o.get("status") == "completed"]
    revenue = sum(o["total"] for o in completed)
    pending = [o for o in orders if o.get("status") == "waiting_admin"]
    products = dm.data["products"]
    total_stock = sum(p.get("stock", 0) for p in products)

    await update.message.reply_text(
        f"📊 **آمار ربات**\n\n"
        f"👥 کاربران: {users}\n"
        f"📦 محصولات: {len(products)}\n"
        f"📊 موجودی کل: {total_stock}\n"
        f"🛒 کل سفارش: {len(orders)}\n"
        f"⏳ در انتظار: {len(pending)}\n"
        f"✅ تکمیل: {len(completed)}\n"
        f"💰 درآمد: {fmt(revenue)} ت"
    )


async def show_daily_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    stats = dm.get_daily_stats(7)
    text = "📈 آمار فروش ۷ روز اخیر:\n\n"
    total_orders = 0
    total_revenue = 0
    for s in stats:
        text += f"📅 {s['date']}\n"
        text += f"   🛒 {s['orders']} سفارش | 💰 {fmt(s['revenue'])} ت\n\n"
        total_orders += s['orders']
        total_revenue += s['revenue']
    text += f"━━━━━━━━━━\n📊 مجموع: {total_orders} سفارش\n💰 درآمد کل: {fmt(total_revenue)} ت"
    await update.message.reply_text(text)


async def welcome_msg_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_welcome_msg'] = True
    current = dm.data.get("welcome_msg", "")
    await update.message.reply_text(f"📝 **تغییر پیام خوش‌آمد**\n\nپیام فعلی:\n{current}\n\nپیام جدید رو بنویس:")


async def handle_welcome_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_welcome_msg'):
        return
    dm.data["welcome_msg"] = update.message.text
    dm.save_data()
    clear_states(context)
    await update.message.reply_text("✅ پیام خوش‌آمد تغییر کرد.")


async def show_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_admin(update.effective_user.id):
        return
    users = dm.data["users"]
    if not users:
        await update.message.reply_text("📭 هیچ کاربری نیست.")
        return
    text = f"👥 آمار کاربران ({len(users)} نفر)\n\n"
    for i, (uid, u) in enumerate(list(users.items())[-30:], 1):
        name = u.get("first_name", "-") or "-"
        username = u.get("username", "")
        uname_str = f"@{username}" if username else "بدون یوزرنیم"
        balance = u.get("balance", 0)
        orders_count = len(u.get("orders", []))
        text += (
            f"{i}. ID: {uid}\n"
            f"   نام: {name}\n"
            f"   یوزرنیم: {uname_str}\n"
            f"   موجودی: {fmt(balance)} ت | سفارش: {orders_count}\n\n"
        )
    if len(users) > 30:
        text += f"... و {len(users) - 30} کاربر دیگه"
    await send_long_message(update, text)


async def search_user_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_admin(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_search_user'] = True
    await update.message.reply_text("🔍 **جستجوی کاربر**\nاسم، یوزرنیم یا آیدی عددی رو بنویس:\n(برای انصراف /cancel)")


async def handle_search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_search_user'):
        return
    query = update.message.text.strip().lower().replace("@", "")
    users = dm.data["users"]
    found = []
    for uid, u in users.items():
        if (query in uid.lower() or
            query in (u.get("username", "") or "").lower() or
            query in (u.get("first_name", "") or "").lower()):
            found.append((uid, u))
    clear_states(context)
    if not found:
        await update.message.reply_text("❌ کاربری پیدا نشد.")
        return
    text = f"🔍 نتیجه جستجو ({len(found)} کاربر)\n\n"
    for i, (uid, u) in enumerate(found[:10], 1):
        name = u.get("first_name", "-") or "-"
        username = u.get("username", "")
        uname_str = f"@{username}" if username else "ندارد"
        balance = u.get("balance", 0)
        orders_count = len(u.get("orders", []))
        banned = "🚫" if dm.is_banned(uid) else "✅"
        text += (
            f"{i}. ID: {uid}\n"
            f"   نام: {name} | {uname_str}\n"
            f"   موجودی: {fmt(balance)} ت | سفارش: {orders_count}\n"
            f"   وضعیت: {banned}\n\n"
        )
    await send_long_message(update, text)


# =========================================================
#                     مدیریت کارت‌ها
# =========================================================

def get_cards():
    data = dm.data
    if "cards" not in data or not isinstance(data.get("cards"), list):
        data["cards"] = []
        dm.save_data()
    return data["cards"]


def get_active_card():
    cards = get_cards()
    for c in cards:
        if c.get("active"):
            return c
    if cards:
        return cards[0]
    return {"number": "6037997599999999", "holder": "پیش‌فرض"}


async def cards_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    cards = get_cards()
    text = "💳 **مدیریت کارت‌های بانکی**\n\n"
    if not cards:
        text += "❌ هیچ کارتی ثبت نشده."
    else:
        for i, c in enumerate(cards, 1):
            status = "✅ فعال" if c.get("active") else "⚪ غیرفعال"
            text += f"{i}. {c['number']}\n   👤 {c.get('holder', '-')}\n   {status}\n\n"
    kb = [
        [InlineKeyboardButton("➕ افزودن کارت", callback_data="card_add")],
        [InlineKeyboardButton("🗑️ حذف کارت", callback_data="card_del_menu")],
        [InlineKeyboardButton("🔄 تغییر کارت فعال", callback_data="card_activate_menu")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def add_card_prompt(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    clear_states(ctx)
    ctx.user_data['awaiting_card_number'] = True
    await msg.reply_text("💳 **افزودن کارت جدید**\n\nشماره کارت رو بنویس (۱۶ رقم):\nمثال: `6037997512345678`")


async def handle_add_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_card_number'):
        return
    number = update.message.text.strip().replace("-", "").replace(" ", "")
    if not number.isdigit() or len(number) != 16:
        await update.message.reply_text("❌ شماره کارت باید ۱۶ رقم باشه.")
        return
    context.user_data['new_card_number'] = number
    context.user_data['awaiting_card_number'] = False
    context.user_data['awaiting_card_holder'] = True
    await update.message.reply_text("👤 نام صاحب کارت رو بنویس:")


async def handle_add_card_holder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_card_holder'):
        return
    holder = update.message.text.strip()
    number = context.user_data.get('new_card_number')
    cards = get_cards()
    is_first = len(cards) == 0
    cards.append({"number": number, "holder": holder, "active": is_first})
    dm.data["cards"] = cards
    dm.save_data()
    clear_states(context)
    await update.message.reply_text(
        f"✅ کارت اضافه شد\n\n💳 {number}\n👤 {holder}\n"
        f"{'✅ این کارت فعال شد' if is_first else ''}\n\n"
        f"برای بازگشت، دکمه ⚙️ پنل ادمین رو بزن."
    )


async def del_card_menu(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    cards = get_cards()
    if not cards:
        await msg.reply_text("❌ هیچ کارتی نیست.")
        return
    kb = []
    for i, c in enumerate(cards):
        kb.append([InlineKeyboardButton(
            f"🗑️ حذف {c['number'][-4:]} ({c.get('holder', '-')})",
            callback_data=f"card_del_{i}"
        )])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="card_menu")])
    await msg.reply_text("کدوم کارت رو حذف کنم؟", reply_markup=InlineKeyboardMarkup(kb))


async def del_card_execute(upd, ctx, idx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    cards = get_cards()
    if 0 <= idx < len(cards):
        removed = cards.pop(idx)
        if removed.get("active") and cards:
            cards[0]["active"] = True
        dm.data["cards"] = cards
        dm.save_data()
        await msg.reply_text(f"✅ کارت {removed['number'][-4:]} حذف شد.")
    else:
        await msg.reply_text("❌ کارت پیدا نشد.")
    await cards_menu(msg, ctx)


async def activate_card_menu(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    cards = get_cards()
    if not cards:
        await msg.reply_text("❌ هیچ کارتی نیست.")
        return
    kb = []
    for i, c in enumerate(cards):
        status = "✅" if c.get("active") else "⚪"
        kb.append([InlineKeyboardButton(
            f"{status} {c['number'][-4:]} ({c.get('holder', '-')})",
            callback_data=f"card_act_{i}"
        )])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="card_menu")])
    await msg.reply_text("کدوم کارت رو فعال کنم؟", reply_markup=InlineKeyboardMarkup(kb))


async def activate_card_execute(upd, ctx, idx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    cards = get_cards()
    if 0 <= idx < len(cards):
        for i, c in enumerate(cards):
            c["active"] = (i == idx)
        dm.data["cards"] = cards
        dm.save_data()
        await msg.reply_text(f"✅ کارت {cards[idx]['number'][-4:]} فعال شد.")
    else:
        await msg.reply_text("❌ کارت پیدا نشد.")
    await cards_menu(msg, ctx)


# =========================================================
#                     مدیریت برنامه‌ها (APK)
# =========================================================

async def apps_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    apps = dm.data.get("apps", [])
    apps_text = dm.data.get("apps_text", "📱 برای اتصال، از برنامه‌های زیر استفاده کن:")
    text = f"📱 **مدیریت برنامه‌های اتصال**\n\n📝 متن توضیحی:\n{apps_text}\n\n"
    if not apps:
        text += "❌ هیچ برنامه‌ای ثبت نشده."
    else:
        for i, a in enumerate(apps, 1):
            text += f"{i}. {a.get('name', 'بدون نام')}\n"
    kb = [
        [InlineKeyboardButton("➕ افزودن برنامه", callback_data="app_add")],
        [InlineKeyboardButton("🗑️ حذف برنامه", callback_data="app_del_menu")],
        [InlineKeyboardButton("📝 تغییر متن توضیحی", callback_data="app_text")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def add_app_prompt(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    clear_states(ctx)
    ctx.user_data['awaiting_app_name'] = True
    await msg.reply_text("📱 **افزودن برنامه جدید**\n\nاسم برنامه رو بنویس:")


async def handle_add_app_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_app_name'):
        return
    context.user_data['new_app_name'] = update.message.text.strip()
    context.user_data['awaiting_app_name'] = False
    context.user_data['awaiting_app_file'] = True
    await update.message.reply_text(
        "📤 حالا فایل APK برنامه رو بفرست:\n"
        "(به صورت Document یا فایل)"
    )


async def handle_add_app_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_app_file'):
        return
    name = context.user_data.get('new_app_name', 'برنامه')
    file_id = None
    file_type = "document"

    if update.message.document:
        file_id = update.message.document.file_id
    elif update.message.video:
        file_id = update.message.video.file_id
    else:
        await update.message.reply_text("❌ لطفاً فایل APK رو به صورت Document بفرست.")
        return

    apps = dm.data.get("apps", [])
    apps.append({"name": name, "file_id": file_id})
    dm.data["apps"] = apps
    dm.save_data()
    clear_states(context)
    await update.message.reply_text(
        f"✅ برنامه `{name}` اضافه شد.\n\n"
        f"برای بازگشت، دکمه ⚙️ پنل ادمین رو بزن."
    )


async def del_app_menu(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    apps = dm.data.get("apps", [])
    if not apps:
        await msg.reply_text("❌ هیچ برنامه‌ای نیست.")
        return
    kb = []
    for i, a in enumerate(apps):
        kb.append([InlineKeyboardButton(
            f"🗑️ حذف {a.get('name', 'بدون نام')}",
            callback_data=f"app_del_{i}"
        )])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="app_menu")])
    await msg.reply_text("کدوم برنامه رو حذف کنم؟", reply_markup=InlineKeyboardMarkup(kb))


async def del_app_execute(upd, ctx, idx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    apps = dm.data.get("apps", [])
    if 0 <= idx < len(apps):
        removed = apps.pop(idx)
        dm.data["apps"] = apps
        dm.save_data()
        await msg.reply_text(f"✅ برنامه {removed.get('name', '')} حذف شد.")
    else:
        await msg.reply_text("❌ برنامه پیدا نشد.")
    await apps_menu(msg, ctx)


async def app_text_prompt(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    clear_states(ctx)
    ctx.user_data['awaiting_apps_text'] = True
    current = dm.data.get("apps_text", "")
    await msg.reply_text(f"📝 متن فعلی:\n{current}\n\nمتن جدید رو بنویس:")


async def handle_apps_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_apps_text'):
        return
    dm.data["apps_text"] = update.message.text.strip()
    dm.save_data()
    clear_states(context)
    await update.message.reply_text("✅ متن توضیحی تغییر کرد.")


# =========================================================
#                     افزودن محصول
# =========================================================

async def add_product_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    context.user_data['awaiting_product_name'] = True
    await update.message.reply_text("➕ **افزودن محصول**\nنام محصول رو بنویس:\n(برای انصراف /cancel)")


async def handle_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_product_name'):
        context.user_data['new_product_name'] = update.message.text
        context.user_data['awaiting_product_name'] = False
        context.user_data['awaiting_product_price'] = True
        await update.message.reply_text("💰 قیمت رو به تومان بنویس:")
    elif context.user_data.get('awaiting_product_price'):
        try:
            price = int(update.message.text)
        except ValueError:
            await update.message.reply_text("❌ عدد بفرست.")
            return
        context.user_data['new_product_price'] = price
        context.user_data['awaiting_product_price'] = False
        context.user_data['awaiting_product_stock'] = True
        await update.message.reply_text("📦 موجودی اولیه رو بنویس:")
    elif context.user_data.get('awaiting_product_stock'):
        try:
            stock = int(update.message.text)
        except ValueError:
            await update.message.reply_text("❌ عدد بفرست.")
            return
        context.user_data['new_product_stock'] = stock
        context.user_data['awaiting_product_stock'] = False
        context.user_data['awaiting_product_configs'] = True
        await update.message.reply_text(
            "🔑 **کانفیگ‌ها رو بفرست**\n\nهر کانفیگ تو یه خط جداگانه.\nاگه نداری، بنویس: `ندارم`"
        )
    elif context.user_data.get('awaiting_product_configs'):
        configs_text = update.message.text.strip()
        configs = []
        if configs_text != "ندارم":
            configs = [c.strip() for c in configs_text.split("\n") if c.strip()]

        name = context.user_data.get('new_product_name')
        price = context.user_data.get('new_product_price')
        stock = context.user_data.get('new_product_stock')

        pid = dm.add_product({"name": name, "price": price, "stock": stock, "configs": configs})
        clear_states(context)
        await update.message.reply_text(
            f"✅ **محصول اضافه شد**\n\n"
            f"📛 {name}\n🆔 ID: {pid}\n"
            f"💰 {fmt(price)} ت\n📦 موجودی: {stock}\n"
            f"🔑 کانفیگ: {len(configs)}\n\n"
            f"برای بازگشت، دکمه ⚙️ پنل ادمین رو بزن."
        )
# =========================================================
#                     مدیریت محصولات
# =========================================================

async def manage_products(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    products = dm.data["products"]
    if not products:
        await msg.reply_text("📭 محصولی نیست.")
        return
    kb = []
    for p in products:
        configs_count = len(p.get("configs", []))
        kb.append([
            InlineKeyboardButton(
                f"✏️ {p['name']} ({p['stock']} | {configs_count}cfg)",
                callback_data=f"editp_{p['id']}"
            ),
            InlineKeyboardButton("❌", callback_data=f"delp_{p['id']}")
        ])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
    markup = InlineKeyboardMarkup(kb)
    await safe_edit(msg, "📦 **مدیریت محصولات**", reply_markup=markup)


async def delete_product_confirm(query: CallbackQuery, ctx, pid):
    p = dm.get_product(pid)
    if not p:
        await query.answer("یافت نشد")
        return
    kb = [
        [InlineKeyboardButton("✅ بله", callback_data=f"confirmdel_{pid}")],
        [InlineKeyboardButton("❌ انصراف", callback_data="manage_products")]
    ]
    await query.edit_message_text(f"⚠️ حذف {p['name']} مطمئنی؟", reply_markup=InlineKeyboardMarkup(kb))


async def confirm_delete_product(query: CallbackQuery, ctx, pid):
    dm.delete_product(pid)
    await query.answer("حذف شد")
    await manage_products(query, ctx)


async def edit_product_prompt(query: CallbackQuery, ctx, pid):
    p = dm.get_product(pid)
    if not p:
        await query.answer("یافت نشد")
        return
    configs_count = len(p.get("configs", []))
    kb = [
        [InlineKeyboardButton("✏️ ویرایش اطلاعات", callback_data=f"editinfo_{pid}")],
        [InlineKeyboardButton(f"🔑 افزودن کانفیگ ({configs_count})", callback_data=f"addcfg_{pid}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="manage_products")]
    ]
    await query.edit_message_text(
        f"✏️ {p['name']}\n\n💰 {fmt(p['price'])} ت\n📦 موجودی: {p['stock']}\n🔑 کانفیگ: {configs_count}",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def edit_product_info_prompt(query: CallbackQuery, ctx, pid):
    p = dm.get_product(pid)
    if not p:
        await query.answer("یافت نشد")
        return
    clear_states(ctx)
    ctx.user_data['editing_product_id'] = pid
    ctx.user_data['awaiting_edit_product'] = True
    await query.edit_message_text(
        f"✏️ ویرایش {p['name']}\n\n۴ خط بفرست:\nنام\nقیمت\nموجودی\nتوضیحات"
    )


async def handle_edit_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_edit_product'):
        return
    pid = context.user_data.get('editing_product_id')
    lines = update.message.text.strip().split('\n')
    if len(lines) < 4:
        await update.message.reply_text("❌ حداقل ۴ خط.")
        return
    name = lines[0].strip()
    try:
        price = int(lines[1].strip())
        stock = int(lines[2].strip())
    except ValueError:
        await update.message.reply_text("❌ قیمت و موجودی باید عدد باشن.")
        return
    desc = "\n".join(lines[3:]).strip()
    dm.update_product(pid, {"name": name, "price": price, "stock": stock, "description": desc})
    clear_states(context)
    await update.message.reply_text("✅ محصول ویرایش شد.\n\nبرای بازگشت، دکمه ⚙️ پنل ادمین رو بزن.")


async def add_config_prompt(query: CallbackQuery, ctx, pid):
    p = dm.get_product(pid)
    if not p:
        await query.answer("یافت نشد")
        return
    clear_states(ctx)
    ctx.user_data['adding_config_pid'] = pid
    ctx.user_data['awaiting_config_add'] = True
    await query.edit_message_text(f"🔑 افزودن کانفیگ به {p['name']}\n\nهر کانفیگ خط به خط:")


async def handle_add_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_config_add'):
        return
    pid = context.user_data.get('adding_config_pid')
    p = dm.get_product(pid)
    if not p:
        await update.message.reply_text("❌ محصول یافت نشد.")
        clear_states(context)
        return
    new_configs = [c.strip() for c in update.message.text.strip().split("\n") if c.strip()]
    p.setdefault("configs", [])
    p["configs"].extend(new_configs)
    dm.save_data()
    clear_states(context)
    await update.message.reply_text(f"✅ {len(new_configs)} کانفیگ اضافه شد. مجموع: {len(p['configs'])}")


async def increase_stock_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    context.user_data['awaiting_stock_increase'] = True
    await update.message.reply_text("📈 **افزایش موجودی**\n`product_id amount`\nمثال: `1 50`")


async def decrease_stock_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    context.user_data['awaiting_stock_decrease'] = True
    await update.message.reply_text("📉 **کسر موجودی**\n`product_id amount`\nمثال: `1 10`")


async def handle_stock_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_stock_increase') or context.user_data.get('awaiting_stock_decrease'):
        parts = update.message.text.split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            await update.message.reply_text("❌ مثال: `1 50`")
            return
        pid = int(parts[0])
        amount = int(parts[1])
        p = dm.get_product(pid)
        if not p:
            await update.message.reply_text("❌ محصول یافت نشد.")
            clear_states(context)
            return
        if context.user_data.get('awaiting_stock_increase'):
            dm.adjust_stock(pid, amount)
        else:
            dm.adjust_stock(pid, -amount)
        clear_states(context)
        await update.message.reply_text(f"✅ موجودی {p['name']}: {dm.get_product(pid)['stock']}")


async def increase_all_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_increase_all'] = True
    await update.message.reply_text("💰 مبلغ افزایش همگانی:")


async def decrease_all_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_decrease_all'] = True
    await update.message.reply_text("💸 مبلغ کسر همگانی:")


async def handle_all_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد مثبت بفرست.")
        return
    if context.user_data.get('awaiting_increase_all'):
        n = dm.increase_all(amount)
        clear_states(context)
        await update.message.reply_text(f"✅ {n} کاربر هر کدام {fmt(amount)} ت")
    elif context.user_data.get('awaiting_decrease_all'):
        n = dm.decrease_all(amount)
        clear_states(context)
        await update.message.reply_text(f"✅ از {n} کاربر {fmt(amount)} ت کسر شد")


# =========================================================
#                     کد تخفیف ادمین
# =========================================================

async def coupon_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    coupons = dm.get_coupons()
    text = "🎟️ **مدیریت کدهای تخفیف**\n\n"
    if coupons:
        for code, c in coupons.items():
            text += f"`{code}` → {c['percent']}% | استفاده: {c['used']}/{c['max_uses'] or '∞'}\n"
    else:
        text += "هیچ کدی نیست."
    kb = [
        [InlineKeyboardButton("➕ افزودن کد", callback_data="add_coupon")],
        [InlineKeyboardButton("🗑️ حذف کد", callback_data="del_coupon")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def add_coupon_prompt(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    clear_states(ctx)
    ctx.user_data['awaiting_coupon_percent'] = True
    await msg.reply_text("🎟️ درصد تخفیف (1-99):")


async def handle_add_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_coupon_percent'):
        try:
            percent = int(update.message.text)
            if percent < 1 or percent > 99:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ 1 تا 99.")
            return
        context.user_data['coupon_percent'] = percent
        context.user_data['awaiting_coupon_percent'] = False
        context.user_data['awaiting_coupon_max'] = True
        await update.message.reply_text("🔢 حداکثر استفاده (0=نامحدود):")
    elif context.user_data.get('awaiting_coupon_max'):
        try:
            max_uses = int(update.message.text)
        except ValueError:
            await update.message.reply_text("❌ عدد بفرست.")
            return
        context.user_data['coupon_max'] = max_uses
        context.user_data['awaiting_coupon_max'] = False
        context.user_data['awaiting_coupon_code'] = True
        await update.message.reply_text("🔤 کد تخفیف رو بنویس:")
    elif context.user_data.get('awaiting_coupon_code'):
        code = update.message.text.strip().upper()
        percent = context.user_data.get('coupon_percent')
        max_uses = context.user_data.get('coupon_max')
        dm.add_coupon(code, percent, max_uses)
        clear_states(context)
        await update.message.reply_text(f"✅ کد `{code}` با {percent}% ساخته شد.")


async def del_coupon_prompt(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    clear_states(ctx)
    ctx.user_data['awaiting_coupon_delete'] = True
    await msg.reply_text("🗑️ کد تخفیف مورد نظر:")


async def handle_del_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_coupon_delete'):
        return
    code = update.message.text.strip().upper()
    if dm.delete_coupon(code):
        await update.message.reply_text(f"✅ کد `{code}` حذف شد.")
    else:
        await update.message.reply_text("❌ کد پیدا نشد.")
    clear_states(context)


# =========================================================
#                     تنظیمات رفرال
# =========================================================

async def ref_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    s = dm.get_ref_settings()
    text = (
        f"🎁 **تنظیمات رفرال**\n\n"
        f"💰 پاداش هر دعوت: {fmt(s.get('bonus', 5000))} ت\n"
        f"🔘 وضعیت: {'✅ فعال' if s.get('enabled', True) else '❌ غیرفعال'}"
    )
    kb = [
        [InlineKeyboardButton("💰 تغییر پاداش", callback_data="set_ref_bonus")],
        [InlineKeyboardButton("🔘 روشن/خاموش", callback_data="toggle_ref")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def set_ref_bonus_prompt(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    clear_states(ctx)
    ctx.user_data['awaiting_ref_bonus'] = True
    await msg.reply_text("💰 پاداش هر دعوت به تومان:")


async def handle_set_ref_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_ref_bonus'):
        return
    try:
        bonus = int(update.message.text.strip())
        if bonus < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ عدد مثبت بفرست.")
        return
    s = dm.get_ref_settings()
    dm.set_ref_settings(bonus, s.get('min_purchase', 0), s.get('enabled', True))
    clear_states(context)
    await update.message.reply_text(f"✅ پاداش: {fmt(bonus)} ت")


async def toggle_ref(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    s = dm.get_ref_settings()
    dm.set_ref_settings(s.get('bonus', 5000), s.get('min_purchase', 0), not s.get('enabled', True))
    new_s = dm.get_ref_settings()
    await msg.reply_text(f"✅ رفرال {'فعال' if new_s['enabled'] else 'غیرفعال'} شد.")


# =========================================================
#                     سفارش‌ها
# =========================================================

async def show_orders_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📥 در انتظار", callback_data="ord_waiting")],
        [InlineKeyboardButton("✅ تکمیل شده", callback_data="ord_completed")],
        [InlineKeyboardButton("❌ رد شده", callback_data="ord_rejected")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ]
    await update.message.reply_text("📋 **مدیریت سفارش‌ها**", reply_markup=InlineKeyboardMarkup(kb))


async def show_orders_by_status(upd, ctx, statuses):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    orders = [o for o in dm.data["orders"] if o.get("status") in statuses]
    orders = sorted(orders, key=lambda x: x.get("date", ""), reverse=True)
    if not orders:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]])
        await safe_edit(msg, "📭 سفارشی نیست.", reply_markup=kb)
        return
    kb = []
    for o in orders[:20]:
        kb.append([InlineKeyboardButton(f"#{o['order_id']} | {fmt(o['total'])} ت", callback_data=f"orddet_{o['order_id']}")])
    kb.append([InlineKeyboardButton("🗑️ خالی کردن", callback_data=f"clrord_{'_'.join(statuses)}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
    title = "📥 در انتظار" if "waiting_admin" in statuses else ("✅ تکمیل" if "completed" in statuses else "❌ رد")
    markup = InlineKeyboardMarkup(kb)
    await safe_edit(msg, title, reply_markup=markup)


async def clear_orders(query: CallbackQuery, ctx, statuses_str):
    statuses = statuses_str.split('_')
    orders_to_remove = [o for o in dm.data["orders"] if o.get("status") in statuses]
    if not orders_to_remove:
        await query.edit_message_text("📭 سفارشی نیست.")
        return
    for o in orders_to_remove:
        u = dm.get_user(o.get("user_id", ""))
        if o["order_id"] in u.get("orders", []):
            u["orders"].remove(o["order_id"])
    dm.data["orders"] = [o for o in dm.data["orders"] if o.get("status") not in statuses]
    dm.save_data()
    await query.edit_message_text(f"✅ {len(orders_to_remove)} سفارش حذف شد.")


async def view_order_detail(query: CallbackQuery, ctx, oid):
    o = dm.get_order(oid)
    if not o:
        await query.answer("یافت نشد")
        return
    ud = user_display(o.get("user_id", ""), o.get("username", ""))
    items = "\n".join(f"{i+1}. {it['name']} - {fmt(it['price'])} ت" for i, it in enumerate(o.get("items", [])))
    text = (
        f"🆔 `{o['order_id']}`\n"
        f"👤 {ud}\n"
        f"💰 {fmt(o['total'])} ت\n"
    )
    if o.get('discount'):
        text += f"🎟️ تخفیف: {o['discount']}%\n"
    text += (
        f"📅 {o.get('date', '')}\n"
        f"📌 {o['status']}\n"
        f"━━━━━━━━━━\n{items}"
    )
    kb = []
    if o['status'] == 'waiting_admin':
        kb.append([
            InlineKeyboardButton("✅ تأیید", callback_data=f"appr_{oid}"),
            InlineKeyboardButton("❌ رد", callback_data=f"rej_{oid}")
        ])
    if o.get('account_info'):
        kb.append([InlineKeyboardButton("📤 مشاهده کانفیگ", callback_data=f"vcfg_{oid}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
    await safe_edit(query.message, text, reply_markup=InlineKeyboardMarkup(kb))


async def approve_order_prompt(query: CallbackQuery, ctx, oid):
    o = dm.get_order(oid)
    if not o or o['status'] != 'waiting_admin':
        await query.answer("قابل تأیید نیست.")
        return

    auto_configs = []
    for item in o.get('items', []):
        p = dm.get_product(item['id'])
        if p and p.get('configs') and len(p['configs']) > 0:
            auto_configs.append(p['configs'][0])

    if auto_configs:
        await query.edit_message_text(
            f"📤 **تأیید سفارش `{oid}`**\n\n🔑 {len(auto_configs)} کانفیگ آماده تو دیتابیسه.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 ارسال خودکار", callback_data=f"autocfg_{oid}")],
                [InlineKeyboardButton("✏️ ارسال دستی", callback_data=f"manualcfg_{oid}")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
            ])
        )
    else:
        clear_states(ctx)
        ctx.user_data['sending_config_for'] = oid
        await query.edit_message_text(f"📤 کانفیگ سفارش `{oid}` رو بفرست:")


async def send_config_auto(query: CallbackQuery, ctx, oid):
    o = dm.get_order(oid)
    if not o:
        await query.answer("یافت نشد")
        return
    sent_configs = []
    for item in o.get('items', []):
        p = dm.get_product(item['id'])
        if p and p.get('configs') and len(p['configs']) > 0:
            cfg = p['configs'].pop(0)
            sent_configs.append(cfg)
            dm.save_data()
    if not sent_configs:
        await query.answer("❌ کانفیگ نیست.", show_alert=True)
        return
    target = int(o['user_id'])
    cfg_text = "\n\n".join(sent_configs)
    try:
        await ctx.bot.send_message(target, f"🎁 **سفارش {oid}**\n\n`{cfg_text}`", parse_mode="Markdown")
        for it in o.get('items', []):
            dm.adjust_stock(it['id'], -1)
        dm.update_order(oid, {"status": "completed", "account_info": cfg_text})
        await query.edit_message_text(f"✅ ارسال شد.")
    except Exception as e:
        await query.edit_message_text(f"❌ خطا: {e}")


async def send_config_manual(query: CallbackQuery, ctx, oid):
    clear_states(ctx)
    ctx.user_data['sending_config_for'] = oid
    await query.edit_message_text(f"📤 کانفیگ سفارش `{oid}` رو بفرست:")


async def send_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    oid = context.user_data.get('sending_config_for')
    if not oid:
        return False
    o = dm.get_order(oid)
    if not o:
        await update.message.reply_text("❌ سفارش یافت نشد.")
        context.user_data.pop('sending_config_for', None)
        return True
    target = int(o['user_id'])
    cfg = update.message.text or update.message.caption or "کانفیگ"
    try:
        if update.message.photo:
            await context.bot.send_photo(target, update.message.photo[-1].file_id, caption=f"🎁 **سفارش {oid}**\n\n{cfg}")
        elif update.message.document:
            await context.bot.send_document(target, update.message.document.file_id, caption=f"🎁 **سفارش {oid}**\n\n{cfg}")
        else:
            await context.bot.send_message(target, f"🎁 **سفارش {oid}**\n\n{cfg}")
        for it in o.get('items', []):
            dm.adjust_stock(it['id'], -1)
        dm.update_order(oid, {"status": "completed", "account_info": cfg})
        context.user_data.pop('sending_config_for', None)
        await update.message.reply_text(f"✅ کانفیگ ارسال شد.")
    except Exception as e:
        logger.error(f"Config send err: {e}")
        await update.message.reply_text(f"❌ خطا: {e}")
    return True


async def view_config(query: CallbackQuery, ctx, oid):
    o = dm.get_order(oid)
    if not o or not o.get('account_info'):
        await query.answer("کانفیگ نیست.")
        return
    await safe_edit(
        query.message,
        f"**کانفیگ سفارش {oid}:**\n\n{o['account_info']}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data=f"orddet_{oid}")]])
    )


async def reject_order(query: CallbackQuery, ctx, oid):
    o = dm.get_order(oid)
    if not o or o['status'] != 'waiting_admin':
        await query.answer("قابل رد نیست.")
        return
    if o.get('payment_method') == 'wallet':
        u = dm.get_user(o['user_id'])
        u['balance'] = u.get('balance', 0) + o['total']
        dm.save_data()
        try:
            await ctx.bot.send_message(int(o['user_id']), f"❌ سفارش `{oid}` رد شد.\n💰 {fmt(o['total'])} ت برگشت.")
        except Exception:
            pass
    dm.update_order(oid, {"status": "rejected"})
    await query.answer("رد شد")
    await show_orders_by_status(query, ctx, ['waiting_admin'])
# =========================================================
#                     درخواست‌های شارژ
# =========================================================

async def show_topup_requests(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    pending = [r for r in dm.data["topup_requests"] if r.get("status") == "pending"]
    if not pending:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]])
        await safe_edit(msg, "📭 درخواستی نیست.", reply_markup=kb)
        return
    kb = []
    for r in pending[:20]:
        kb.append([InlineKeyboardButton(f"#{r['request_id']} | {fmt(r['amount'])} ت", callback_data=f"topdet_{r['request_id']}")])
    kb.append([InlineKeyboardButton("🗑️ خالی کردن", callback_data="clrtop")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
    markup = InlineKeyboardMarkup(kb)
    await safe_edit(msg, "💰 **درخواست‌های شارژ**", reply_markup=markup)


async def clear_topups(query: CallbackQuery, ctx):
    pending = [r for r in dm.data["topup_requests"] if r.get("status") == "pending"]
    if not pending:
        await query.edit_message_text("📭 چیزی نیست.")
        return
    dm.data["topup_requests"] = [r for r in dm.data["topup_requests"] if r.get("status") != "pending"]
    dm.save_data()
    await query.edit_message_text(f"✅ {len(pending)} درخواست حذف شد.")


async def view_topup_detail(query: CallbackQuery, ctx, rid):
    r = dm.get_topup(rid)
    if not r:
        await query.answer("یافت نشد")
        return
    ud = user_display(r.get("user_id", ""), r.get("username", ""))
    text = (
        f"💰 **درخواست شارژ**\n"
        f"🆔 `{r['request_id']}`\n"
        f"👤 {ud}\n"
        f"💰 {fmt(r['amount'])} ت\n"
        f"📅 {r.get('date', '')}"
    )
    kb = [
        [InlineKeyboardButton("✅ تأیید", callback_data=f"apprtop_{rid}"),
         InlineKeyboardButton("❌ رد", callback_data=f"rejtop_{rid}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_topup")]
    ]
    if r.get('receipt_photo'):
        try:
            await query.message.delete()
        except Exception:
            pass
        await ctx.bot.send_photo(query.message.chat_id, r['receipt_photo'], caption=text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await safe_edit(query.message, text, reply_markup=InlineKeyboardMarkup(kb))


async def approve_topup(query: CallbackQuery, ctx, rid):
    r = dm.get_topup(rid)
    if not r or r['status'] != 'pending':
        await query.answer("قابل تأیید نیست.")
        return
    u = dm.get_user(r['user_id'])
    u['balance'] = u.get('balance', 0) + r['amount']
    dm.save_data()
    dm.update_topup(rid, {"status": "approved"})
    await query.answer("تأیید شد")
    try:
        await ctx.bot.send_message(int(r['user_id']), f"✅ شارژ تأیید شد.\n💰 {fmt(r['amount'])} ت")
    except Exception:
        pass
    await show_topup_requests(query, ctx)


async def reject_topup(query: CallbackQuery, ctx, rid):
    r = dm.get_topup(rid)
    if not r or r['status'] != 'pending':
        await query.answer("قابل رد نیست.")
        return
    dm.update_topup(rid, {"status": "rejected"})
    await query.answer("رد شد")
    try:
        await ctx.bot.send_message(int(r['user_id']), "❌ درخواست شارژ رد شد.")
    except Exception:
        pass
    await show_topup_requests(query, ctx)


# =========================================================
#                     کاربر / بن / کیف پول
# =========================================================

async def user_check_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    context.user_data['awaiting_user_check'] = True
    await update.message.reply_text("👤 شناسه کاربر:")


async def handle_user_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()
    if not uid.isdigit():
        await update.message.reply_text("❌ عدد بفرست.")
        return
    u = dm.get_user(uid)
    banned = dm.is_banned(uid)
    ud = user_display(uid, u.get("username", ""))
    clear_states(context)
    await update.message.reply_text(
        f"👤 {ud}\n"
        f"📛 {u.get('first_name', '-')}\n"
        f"💰 {fmt(u.get('balance', 0))} ت\n"
        f"📦 {len(u.get('orders', []))} سفارش\n"
        f"🎁 {u.get('invited_count', 0)} دعوت\n"
        f"🚫 {'مسدود' if banned else 'فعال'}"
    )


async def ban_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    context.user_data['awaiting_ban_toggle'] = True
    await update.message.reply_text("🚫 شناسه کاربر:")


async def handle_ban_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()
    if not uid.isdigit():
        await update.message.reply_text("❌ عدد.")
        return
    if dm.is_banned(uid):
        dm.unban(uid)
        await update.message.reply_text(f"✅ آزاد شد.")
    else:
        dm.ban(uid)
        await update.message.reply_text(f"🚫 مسدود شد.")
    clear_states(context)


async def wallet_admin_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    context.user_data['awaiting_wallet_user'] = True
    await update.message.reply_text("💰 شناسه کاربر:")


async def handle_wallet_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_wallet_user'):
        uid = update.message.text.strip()
        if not uid.isdigit():
            await update.message.reply_text("❌ عدد.")
            return
        context.user_data['wallet_target'] = uid
        context.user_data['awaiting_wallet_user'] = False
        context.user_data['awaiting_wallet_amount'] = True
        u = dm.get_user(uid)
        await update.message.reply_text(f"موجودی: {fmt(u.get('balance', 0))} ت\nمبلغ (مثبت/منفی):")
    elif context.user_data.get('awaiting_wallet_amount'):
        try:
            amount = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ عدد.")
            return
        uid = context.user_data.get('wallet_target')
        u = dm.get_user(uid)
        u['balance'] = max(0, u.get('balance', 0) + amount)
        dm.save_data()
        clear_states(context)
        await update.message.reply_text(f"✅ {fmt(u['balance'])} ت")


# =========================================================
#                     تنظیمات / ادمین‌ها
# =========================================================

async def set_support_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_support'] = True
    await update.message.reply_text("🛠 آیدی پشتیبانی (مثال @username):")


async def handle_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_support'):
        dm.data["support_username"] = update.message.text.strip()
        dm.save_data()
        clear_states(context)
        await update.message.reply_text("✅ پشتیبانی ثبت شد.")


async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owners = dm.data["owners"]
    admins = dm.data["admins"]
    text = "👑 مالکین:\n" + "\n".join(owners) + "\n\n🛡 ادمین‌ها:\n"
    text += "\n".join(admins) if admins else "هیچ"
    await update.message.reply_text(text)


async def add_admin_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_add_admin'] = True
    await update.message.reply_text("➕ شناسه ادمین جدید:")


async def remove_admin_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_remove_admin'] = True
    await update.message.reply_text("➖ شناسه ادمین:")


async def handle_admin_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()
    if context.user_data.get('awaiting_add_admin'):
        if dm.add_admin(uid):
            await update.message.reply_text(f"✅ {uid} ادمین شد.")
        else:
            await update.message.reply_text("❌ از قبل ادمینه.")
    elif context.user_data.get('awaiting_remove_admin'):
        if dm.remove_admin(uid):
            await update.message.reply_text(f"✅ {uid} حذف شد.")
        else:
            await update.message.reply_text("❌ ادمین نیست.")
    clear_states(context)


# =========================================================
#                     پیام همگانی
# =========================================================

async def broadcast_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_broadcast'] = True
    await update.message.reply_text("📢 متن پیام همگانی:\n(برای انصراف /cancel)")


async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    users = dm.data["users"]
    sent = 0
    sent_msgs = []
    for uid in users:
        try:
            m = await context.bot.send_message(int(uid), text)
            sent += 1
            sent_msgs.append({"chat_id": int(uid), "message_id": m.message_id})
        except Exception:
            pass
    if sent_msgs:
        dm.add_broadcast(sent_msgs, text)
    clear_states(context)
    await update.message.reply_text(f"✅ به {sent} کاربر ارسال شد.")


async def delete_last_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    history = dm.get_broadcast_history()
    if not history:
        await update.message.reply_text("📭 تاریخچه خالیه.")
        return
    last = history[-1]
    deleted = 0
    for sm in last.get("sent_messages", []):
        try:
            await context.bot.delete_message(sm["chat_id"], sm["message_id"])
            deleted += 1
        except Exception:
            pass
    history.pop()
    dm.data["broadcast_history"] = history
    dm.save_data()
    await update.message.reply_text(f"✅ از {deleted} کاربر حذف شد.")


# =========================================================
#                     Callback Router
# =========================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    logger.info(f"CALLBACK: {data}")

    try:
        if not data:
            await query.answer("❌")
            return

        # منو
        if data == "back_menu":
            await main_menu(query, context)
        elif data == "admin_back":
            await admin_panel(query, context)
        elif data == "manage_products":
            await manage_products(query, context)
        elif data == "admin_topup":
            await show_topup_requests(query, context)
        elif data == "products_back":
            await show_products(query, context)
        elif data == "show_cart":
            await show_cart(query, context)
        elif data == "clearcart":
            await clear_cart(query, context)
        elif data == "checkout":
            await checkout(query, context)
        elif data == "pay_wallet":
            await pay_wallet(query, context)
        elif data == "request_topup":
            await request_topup_start(query, context)
        elif data == "apply_coupon":
            await apply_coupon_prompt(query, context)

        # کد تخفیف
        elif data == "add_coupon":
            await add_coupon_prompt(query, context)
        elif data == "del_coupon":
            await del_coupon_prompt(query, context)

        # رفرال
        elif data == "set_ref_bonus":
            await set_ref_bonus_prompt(query, context)
        elif data == "toggle_ref":
            await toggle_ref(query, context)

        # کارت‌ها
        elif data == "card_menu":
            await cards_menu(query, context)
        elif data == "card_add":
            await add_card_prompt(query, context)
        elif data == "card_del_menu":
            await del_card_menu(query, context)
        elif data == "card_activate_menu":
            await activate_card_menu(query, context)
        elif data.startswith("card_del_"):
            await del_card_execute(query, context, int(data.split("_")[2]))
        elif data.startswith("card_act_"):
            await activate_card_execute(query, context, int(data.split("_")[2]))

        # برنامه‌ها
        elif data == "app_menu":
            await apps_menu(query, context)
        elif data == "app_add":
            await add_app_prompt(query, context)
        elif data == "app_del_menu":
            await del_app_menu(query, context)
        elif data == "app_text":
            await app_text_prompt(query, context)
        elif data.startswith("app_del_"):
            await del_app_execute(query, context, int(data.split("_")[2]))

        # محصولات
        elif data.startswith("prod_"):
            await product_details(query, context, int(data.split("_")[1]))
        elif data.startswith("cartadd_"):
            await add_to_cart_cb(query, context, int(data.split("_")[1]))
        elif data.startswith("cartdel_"):
            await remove_cart_item(query, context, int(data.split("_")[1]))
        elif data.startswith("editp_"):
            await edit_product_prompt(query, context, int(data.split("_")[1]))
        elif data.startswith("editinfo_"):
            await edit_product_info_prompt(query, context, int(data.split("_")[1]))
        elif data.startswith("addcfg_"):
            await add_config_prompt(query, context, int(data.split("_")[1]))
        elif data.startswith("delp_"):
            await delete_product_confirm(query, context, int(data.split("_")[1]))
        elif data.startswith("confirmdel_"):
            await confirm_delete_product(query, context, int(data.split("_")[1]))

        # سفارش‌ها
        elif data.startswith("orddet_"):
            await view_order_detail(query, context, data[7:])
        elif data.startswith("appr_"):
            await approve_order_prompt(query, context, data[5:])
        elif data.startswith("autocfg_"):
            await send_config_auto(query, context, data[8:])
        elif data.startswith("manualcfg_"):
            await send_config_manual(query, context, data[10:])
        elif data.startswith("rej_"):
            await reject_order(query, context, data[4:])
        elif data.startswith("vcfg_"):
            await view_config(query, context, data[5:])
        elif data == "ord_waiting":
            await show_orders_by_status(query, context, ['waiting_admin'])
        elif data == "ord_completed":
            await show_orders_by_status(query, context, ['completed'])
        elif data == "ord_rejected":
            await show_orders_by_status(query, context, ['rejected'])
        elif data.startswith("clrord_"):
            await clear_orders(query, context, data[7:])

        # شارژ
        elif data.startswith("topdet_"):
            await view_topup_detail(query, context, data[7:])
        elif data.startswith("apprtop_"):
            await approve_topup(query, context, data[7:])
        elif data.startswith("rejtop_"):
            await reject_topup(query, context, data[7:])
        elif data == "clrtop":
            await clear_topups(query, context)

        else:
            await query.answer("❌ نامعتبر", show_alert=True)

    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        try:
            await query.answer("❌ خطا", show_alert=True)
        except Exception:
            pass


# =========================================================
#                     Admin Text Handler
# =========================================================

async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = str(update.effective_user.id)
    if not dm.is_admin(uid):
        return False

    if text == "⚙️ پنل ادمین":
        await admin_panel(update, context)
    elif text == "🔙 بازگشت":
        await main_menu(update, context)
    elif text == "📋 سفارش‌ها":
        await show_orders_menu(update, context)
    elif text == "➕ افزودن محصول":
        await add_product_prompt(update, context)
    elif text == "📦 مدیریت محصولات":
        await manage_products(update, context)
    elif text == "📈 افزایش موجودی":
        await increase_stock_prompt(update, context)
    elif text == "📉 کسر موجودی":
        await decrease_stock_prompt(update, context)
    elif text == "📊 آمار ربات":
        await admin_stats(update, context)
    elif text == "📈 آمار فروش":
        await show_daily_sales(update, context)
    elif text == "👥 آمار کاربران":
        await show_users_list(update, context)
    elif text == "🔍 جستجوی کاربر":
        await search_user_prompt(update, context)
    elif text == "💰 درخواست شارژ":
        await show_topup_requests(update, context)
    elif text == "💰 کیف پول کاربر":
        await wallet_admin_prompt(update, context)
    elif text == "👤 بررسی کاربر":
        await user_check_prompt(update, context)
    elif text == "🚫 مسدود/آزاد":
        await ban_prompt(update, context)
    elif text == "🎟️ کد تخفیف":
        await coupon_menu(update, context)
    elif text == "🎁 تنظیمات رفرال":
        await ref_settings_menu(update, context)
    elif text == "💳 مدیریت کارت‌ها":
        await cards_menu(update, context)
    elif text == "📱 مدیریت برنامه‌ها":
        await apps_menu(update, context)
    elif text == "📝 پیام خوش‌آمد":
        await welcome_msg_prompt(update, context)
    elif text == "🛒 باز/بستن فروشگاه":
        await toggle_shop(update, context)
    elif text == "🛠 پشتیبانی" and dm.is_owner(uid):
        await set_support_prompt(update, context)
    elif text == "👥 لیست ادمین‌ها" and dm.is_owner(uid):
        await list_admins(update, context)
    elif text == "➕ ادمین" and dm.is_owner(uid):
        await add_admin_prompt(update, context)
    elif text == "➖ ادمین" and dm.is_owner(uid):
        await remove_admin_prompt(update, context)
    elif text == "📢 پیام همگانی" and dm.is_owner(uid):
        await broadcast_prompt(update, context)
    elif text == "🗑️ حذف آخرین پیام" and dm.is_owner(uid):
        await delete_last_broadcast(update, context)
    elif text == "💰 افزایش همگانی" and dm.is_owner(uid):
        await increase_all_prompt(update, context)
    elif text == "💸 کسر همگانی" and dm.is_owner(uid):
        await decrease_all_prompt(update, context)
    else:
        return False
    return True
# =========================================================
#                     Message Handler
# =========================================================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if dm.is_banned(uid) and not dm.is_admin(uid):
        await update.message.reply_text("🚫 مسدود هستی.")
        return

    # ← اول همه state ها (ترتیب مهم!)
    if context.user_data.get('awaiting_topup_amount'):
        await handle_topup_amount(update, context); return
    if context.user_data.get('awaiting_topup_receipt'):
        await handle_topup_receipt(update, context); return
    if context.user_data.get('sending_config_for'):
        await send_config(update, context); return
    if context.user_data.get('awaiting_increase_all') or context.user_data.get('awaiting_decrease_all'):
        await handle_all_balance(update, context); return
    if context.user_data.get('awaiting_edit_product'):
        await handle_edit_product(update, context); return
    if context.user_data.get('awaiting_config_add'):
        await handle_add_config(update, context); return
    if context.user_data.get('awaiting_user_check'):
        await handle_user_check(update, context); return
    if context.user_data.get('awaiting_ban_toggle'):
        await handle_ban_toggle(update, context); return
    if context.user_data.get('awaiting_search_user'):
        await handle_search_user(update, context); return
    if context.user_data.get('awaiting_wallet_user') or context.user_data.get('awaiting_wallet_amount'):
        await handle_wallet_admin(update, context); return
    if context.user_data.get('awaiting_support'):
        await handle_settings(update, context); return
    if context.user_data.get('awaiting_add_admin') or context.user_data.get('awaiting_remove_admin'):
        await handle_admin_edit(update, context); return
    if context.user_data.get('awaiting_broadcast'):
        await handle_broadcast(update, context); return
    if (context.user_data.get('awaiting_product_name') or
        context.user_data.get('awaiting_product_price') or
        context.user_data.get('awaiting_product_stock') or
        context.user_data.get('awaiting_product_configs')):
        await handle_add_product(update, context); return
    if context.user_data.get('awaiting_stock_increase') or context.user_data.get('awaiting_stock_decrease'):
        await handle_stock_change(update, context); return
    if (context.user_data.get('awaiting_coupon_percent') or
        context.user_data.get('awaiting_coupon_max') or
        context.user_data.get('awaiting_coupon_code')):
        await handle_add_coupon(update, context); return
    if context.user_data.get('awaiting_coupon_delete'):
        await handle_del_coupon(update, context); return
    if context.user_data.get('awaiting_coupon_input'):
        await handle_coupon_input(update, context); return
    if context.user_data.get('awaiting_ref_bonus'):
        await handle_set_ref_bonus(update, context); return
    if context.user_data.get('awaiting_welcome_msg'):
        await handle_welcome_msg(update, context); return
    if context.user_data.get('awaiting_order_track'):
        await handle_track_order(update, context); return
    if context.user_data.get('awaiting_card_number'):
        await handle_add_card_number(update, context); return
    if context.user_data.get('awaiting_card_holder'):
        await handle_add_card_holder(update, context); return
    if context.user_data.get('awaiting_app_name'):
        await handle_add_app_name(update, context); return
    if context.user_data.get('awaiting_app_file'):
        await handle_add_app_file(update, context); return
    if context.user_data.get('awaiting_apps_text'):
        await handle_apps_text(update, context); return

    if await admin_text_handler(update, context):
        return

    text = update.message.text
    if text == "🛍️ محصولات":
        await show_products(update, context)
    elif text == "🛒 سبد خرید":
        await show_cart(update, context)
    elif text == "👤 حساب کاربری":
        await show_account(update, context)
    elif text == "💰 کیف پول":
        await wallet_menu(update, context)
    elif text == "📱 برنامه‌های اتصال":
        await show_apps(update, context)
    elif text == "🎁 دعوت دوستان":
        await show_referral(update, context)
    elif text == "📜 سفارش‌های من":
        await show_my_orders(update, context)
    elif text == "🔍 پیگیری سفارش":
        await track_order_prompt(update, context)
    elif text == "ℹ️ راهنما":
        await show_help(update, context)
    elif text == "📞 پشتیبانی":
        await show_support(update, context)
    else:
        await update.message.reply_text("از دکمه‌ها استفاده کن.")


# =========================================================
#                     Setup Application
# =========================================================

application = Application.builder().token(BOT_TOKEN).updater(None).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("cancel", cancel))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.PHOTO, message_handler))
application.add_handler(MessageHandler(filters.Document.ALL, message_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

flask_app = Flask(__name__)


@flask_app.route("/")
def index():
    return "✅ ربات فعال است"


@flask_app.route("/health")
def health():
    return "OK"


@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        update_data = request.get_json(force=True)
        update = Update.de_json(update_data, application.bot)

        import asyncio

        async def process():
            async with application:
                await application.initialize()
                await application.process_update(update)

        asyncio.run(process())
        return "OK"
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return "Error", 500


@flask_app.route("/set_webhook")
def set_webhook():
    try:
        webhook_url = f"https://{request.host}/{BOT_TOKEN}"
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def setup():
            async with application:
                await application.bot.set_webhook(url=webhook_url)

        loop.run_until_complete(setup())
        loop.close()
        return f"✅ Webhook set to: {webhook_url}"
    except Exception as e:
        return f"❌ Error: {e}", 500


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT)
