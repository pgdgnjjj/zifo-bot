import json
import os
import logging
import random
import string
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, Union

from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "توکن_پیش‌فرض")
OWNER_IDS = [os.getenv("OWNER_ID", "آیدی_پیش‌فرض")]
DATA_FILE = "/tmp/data.json"
PORT = int(os.getenv("PORT", 8000))

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def gen_order_id():
    return f"ORD-{datetime.now().strftime('%Y%m%d')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"


def gen_req_id():
    return f"TOP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}"


def fmt(p):
    return f"{int(p):,}"


def user_display(uid, uname=None):
    if uname:
        return f"`{uid}` | @{uname}"
    return f"`{uid}` | ندارد"


STATE_KEYS = [
    'awaiting_discount', 'awaiting_topup_amount', 'awaiting_topup_receipt',
    'awaiting_receipt', 'add_discount_step', 'edit_step', 'sending_account_for_order',
    'awaiting_wallet_user', 'awaiting_wallet_user_id', 'awaiting_wallet_amount',
    'awaiting_add_admin', 'awaiting_remove_admin', 'awaiting_broadcast',
    'awaiting_card', 'awaiting_support', 'awaiting_product_name',
    'awaiting_product_price', 'awaiting_product_stock',
    'awaiting_stock_increase', 'awaiting_stock_decrease', 'awaiting_user_check',
    'awaiting_ban_toggle', 'new_product_name', 'new_product_price',
    'wallet_target', 'wallet_target_uid', 'editing_product_id', 'awaiting_edit_product',
    'awaiting_increase_all', 'awaiting_decrease_all', 'sending_config_for',
    'receipt_order_id', 'topup_amount'
]


def clear_states(context):
    for k in STATE_KEYS:
        context.user_data.pop(k, None)


class DataManager:
    def __init__(self):
        self.data = self.load_data()

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data.setdefault("shop_status", {"is_open": True, "closed_message": "🚫 فروشگاه بسته است."})
                data.setdefault("broadcast_history", [])
                data.setdefault("banned_users", [])
                self.save_data(data)
                return data
            except Exception as e:
                logger.error(f"Load error: {e}")
                return self.create_empty()
        return self.create_empty()

    def create_empty(self):
        data = {
            "owners": OWNER_IDS,
            "admins": [],
            "products": [],
            "users": {},
            "orders": [],
            "topup_requests": [],
            "broadcast_history": [],
            "card_number": "6037997599999999",
            "support_username": "@Zifo_support",
            "user_help_text": "🎮 راهنمای خرید\n\n1. محصول انتخاب کن\n2. به سبد اضافه کن\n3. پرداخت کن\n4. کانفیگ دریافت کن",
            "banned_users": [],
            "shop_status": {"is_open": True, "closed_message": "🚫 فروشگاه بسته است."}
        }
        self.save_data(data)
        return data

    def save_data(self, data=None):
        if data is None:
            data = self.data
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.data = data

    def get_user(self, uid):
        uid = str(uid)
        if uid not in self.data["users"]:
            self.data["users"][uid] = {
                "cart": [], "orders": [], "balance": 0,
                "join_date": datetime.now().strftime('%Y-%m-%d'),
                "username": "", "first_name": ""
            }
            self.save_data()
        return self.data["users"][uid]

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
            "sent_messages": sent_msgs,
            "text": text[:100],
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


dm = DataManager()


async def safe_edit(message, text, markup=None):
    try:
        await message.edit_text(text, reply_markup=markup)
    except Exception as e:
        if "not modified" not in str(e).lower():
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
        ["💰 کیف پول"],
        ["ℹ️ راهنما", "📞 پشتیبانی"]
    ]
    if dm.is_admin(uid):
        kb.append(["⚙️ پنل ادمین"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


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
    await msg.reply_text("🌟 **به فروشگاه Zifo خوش آمدید!**", reply_markup=main_kb(uid))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    u = dm.get_user(update.effective_user.id)
    u["username"] = update.effective_user.username or ""
    u["first_name"] = update.effective_user.first_name or ""
    dm.save_data()
    await main_menu(update, context)


async def cancel(update: Update, context):
    clear_states(context)
    await main_menu(update, context)


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
        await msg.reply_text("❌ یافت نشد.")
        return
    text = f"🎯 **{p['name']}**\n💰 {fmt(p['price'])} تومان\n📦 موجودی: {p.get('stock', 0)}\n📝 {p.get('description', '---')}"
    kb = []
    if p.get("stock", 0) > 0:
        kb.append([InlineKeyboardButton("🛒 افزودن به سبد", callback_data=f"cartadd_{pid}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="products_back")])
    markup = InlineKeyboardMarkup(kb)
    if isinstance(upd, CallbackQuery):
        await safe_edit(msg, text, reply_markup=markup)
    else:
        await msg.reply_text(text, reply_markup=markup)


async def add_to_cart_cb(upd, ctx, pid):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
    else:
        msg = upd.message
        user = upd.effective_user
    p = dm.get_product(pid)
    if not p or p.get("stock", 0) <= 0:
        await msg.reply_text("❌ ناموجود.")
        return
    if dm.add_to_cart(str(user.id), pid):
        await msg.reply_text(f"✅ {p['name']} به سبد اضافه شد.")
    else:
        await msg.reply_text("⚠️ قبلاً در سبد هست.")


async def show_cart(upd, ctx):
    clear_states(ctx)
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
        if isinstance(upd, CallbackQuery):
            await safe_edit(msg, text, reply_markup=kb)
        else:
            await msg.reply_text(text, reply_markup=kb)
        return
    total = dm.cart_total(uid)
    text = "🛒 **سبد خرید:**\n\n"
    for i, it in enumerate(cart, 1):
        text += f"{i}. {it['name']} - {fmt(it['price'])} ت\n"
    text += f"\n💰 **مجموع:** {fmt(total)} ت"
    kb = []
    for i, it in enumerate(cart):
        kb.append([InlineKeyboardButton(f"❌ حذف {it['name']}", callback_data=f"cartdel_{i}")])
    kb.append([InlineKeyboardButton("✅ پرداخت با کیف پول", callback_data="checkout")])
    kb.append([
        InlineKeyboardButton("➕ ادامه خرید", callback_data="products_back"),
        InlineKeyboardButton("🗑️ خالی کردن", callback_data="clearcart")
    ])
    markup = InlineKeyboardMarkup(kb)
    if isinstance(upd, CallbackQuery):
        await safe_edit(msg, text, reply_markup=markup)
    else:
        await msg.reply_text(text, reply_markup=markup)


async def remove_cart_item(upd, ctx, idx):
    user = upd.from_user if isinstance(upd, CallbackQuery) else upd.effective_user
    if isinstance(upd, CallbackQuery):
        await answer_cb(upd)
    uid = str(user.id)
    dm.remove_from_cart(uid, idx)
    await show_cart(upd, ctx)


async def clear_cart(upd, ctx):
    user = upd.from_user if isinstance(upd, CallbackQuery) else upd.effective_user
    if isinstance(upd, CallbackQuery):
        await answer_cb(upd)
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
    bal = dm.get_user(uid).get("balance", 0)
    card = dm.data["card_number"]
    if bal < total:
        await msg.reply_text(f"❌ موجودی کافی نیست.\n💰 موجودی: {fmt(bal)} ت\n💰 نیاز: {fmt(total)} ت")
        return
    text = (
        f"✅ **نهایی کردن خرید**\n━━━━━━━━━━\n"
        f"📦 تعداد: {len(cart)}\n"
        f"💰 مبلغ: {fmt(total)} ت\n"
        f"💳 موجودی: {fmt(bal)} ت\n"
        f"💳 کارت: `{card}`\n━━━━━━━━━━\nمطمئنی؟"
    )
    kb = [
        [InlineKeyboardButton("✅ بله، پرداخت", callback_data="pay_wallet")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="show_cart")]
    ]
    markup = InlineKeyboardMarkup(kb)
    if isinstance(upd, CallbackQuery):
        await safe_edit(msg, text, reply_markup=markup)
    else:
        await msg.reply_text(text, reply_markup=markup)


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
        "status": "waiting_admin",
        "payment_method": "wallet",
        "account_info": None
    }
    oid = dm.add_order(order)
    dm.clear_cart(uid)
    ud = user_display(uid, u.get("username", ""))
    items_str = "\n".join(f"{i['name']} - {fmt(i['price'])} ت" for i in cart)
    await msg.reply_text(f"✅ **پرداخت موفق**\n🆔 سفارش: `{oid}`\n💰 {fmt(total)} ت\n\nمنتظر تأیید ادمین باش.")
    for aid in dm.data["owners"] + dm.data["admins"]:
        try:
            await ctx.bot.send_message(int(aid), f"🛒 **سفارش جدید**\n🆔 `{oid}`\n👤 {ud}\n📦 {items_str}\n💰 {fmt(total)} ت")
        except Exception:
            pass
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
    card = dm.data.get("card_number", "6037997599999999")
    await msg.reply_text(
        f"💰 **مبلغ شارژ رو به تومان بنویس:**\n(مثال: 50000)\n\n"
        f"💳 کارت: `{card}`\n\nبرای انصراف /cancel"
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
        await update.message.reply_text("❌ عدد معتبر بفرست.\nبرای انصراف /cancel")
        return True
    amount = int(text)
    if amount <= 0:
        await update.message.reply_text("❌ مبلغ باید مثبت باشه.")
        return True
    context.user_data['topup_amount'] = amount
    context.user_data['awaiting_topup_amount'] = False
    context.user_data['awaiting_topup_receipt'] = True
    card = dm.data.get("card_number", "6037997599999999")
    await update.message.reply_text(
        f"📸 تصویر رسید واریز *{fmt(amount)}* تومان رو بفرست.\n"
        f"💳 کارت: `{card}`\n(برای انصراف /cancel)"
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
        "user_id": uid,
        "username": u.get("username", ""),
        "first_name": u.get("first_name", ""),
        "amount": amount,
        "receipt_photo": file_id
    }
    rid = dm.add_topup(req)
    ud = user_display(uid, u.get("username", ""))
    await update.message.reply_text(f"✅ **درخواست شارژ ثبت شد**\n🆔 `{rid}`\nمنتظر تأیید ادمین باش.")
    for aid in dm.data["owners"] + dm.data["admins"]:
        try:
            await context.bot.send_photo(
                int(aid), file_id,
                caption=f"💰 **شارژ جدید**\n🆔 `{rid}`\n👤 {ud}\n💰 {fmt(amount)} ت"
            )
        except Exception:
            pass
    context.user_data.pop('awaiting_topup_receipt', None)
    context.user_data.pop('topup_amount', None)
    return True


async def show_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    u = dm.get_user(uid)
    ud = user_display(uid, user.username)
    await update.message.reply_text(
        f"👤 **حساب کاربری**\n\n"
        f"👤 {ud}\n"
        f"💰 موجودی: {fmt(u.get('balance', 0))} ت\n"
        f"📦 سفارشات: {len(u.get('orders', []))}",
        reply_markup=main_kb(uid)
    )


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = dm.data.get("user_help_text", "راهنما موجود نیست.")
    await update.message.reply_text(txt, reply_markup=main_kb(update.effective_user.id))


async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = dm.data.get("support_username", "@Zifo_support")
    await update.message.reply_text(f"📞 پشتیبانی: {s}", reply_markup=main_kb(update.effective_user.id))


async def admin_panel(upd, ctx):
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
            ["💰 درخواست‌های شارژ", "💰 کیف پول کاربر"],
            ["👤 بررسی کاربر", "🚫 مسدود/آزاد"],
            ["💳 شماره کارت", "🛠 پشتیبانی"],
            ["👥 لیست ادمین‌ها", "➕ افزودن ادمین", "➖ حذف ادمین"],
            ["🛒 باز/بستن فروشگاه"],
            ["📢 پیام همگانی", "🗑️ حذف آخرین پیام"],
            ["🔙 بازگشت"]
        ]
    else:
        kb = [
            ["➕ افزودن محصول", "📦 مدیریت محصولات"],
            ["📈 افزایش موجودی", "📉 کسر موجودی"],
            ["📋 سفارش‌ها", "📊 آمار ربات"],
            ["💰 درخواست‌های شارژ", "💰 کیف پول کاربر"],
            ["👤 بررسی کاربر", "🚫 مسدود/آزاد"],
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
        await update.message.reply_text(f"🔒 فروشگاه بسته شد.\n{cur['closed_message']}")


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = len(dm.data["users"])
    orders = dm.data["orders"]
    completed = [o for o in orders if o.get("status") == "completed"]
    revenue = sum(o["total"] for o in completed)
    await update.message.reply_text(
        f"📊 **آمار ربات**\n"
        f"👥 کاربران: {users}\n"
        f"🛒 کل سفارش: {len(orders)}\n"
        f"✅ تکمیل: {len(completed)}\n"
        f"💰 درآمد: {fmt(revenue)} ت"
    )


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
        name = context.user_data.get('new_product_name')
        price = context.user_data.get('new_product_price')
        pid = dm.add_product({"name": name, "price": price, "stock": stock})
        await update.message.reply_text(f"✅ محصول `{name}` اضافه شد (ID: {pid})")
        clear_states(context)
        await admin_panel(update, context)


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
        kb.append([
            InlineKeyboardButton(f"✏️ {p['name']}", callback_data=f"editp_{p['id']}"),
            InlineKeyboardButton("❌", callback_data=f"delp_{p['id']}")
        ])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
    markup = InlineKeyboardMarkup(kb)
    if isinstance(upd, CallbackQuery):
        await safe_edit(msg, "📦 **مدیریت محصولات**", reply_markup=markup)
    else:
        await msg.reply_text("📦 **مدیریت محصولات**", reply_markup=markup)


async def edit_product_prompt(query: CallbackQuery, ctx, pid):
    p = dm.get_product(pid)
    if not p:
        await query.answer("یافت نشد")
        return
    clear_states(ctx)
    ctx.user_data['editing_product_id'] = pid
    ctx.user_data['awaiting_edit_product'] = True
    await query.edit_message_text(
        f"✏️ ویرایش *{p['name']}*\n\n"
        f"اطلاعات جدید رو تو ۴ خط بفرست:\n"
        f"نام\nقیمت\nموجودی\nتوضیحات"
    )


async def handle_edit_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_edit_product'):
        return
    pid = context.user_data.get('editing_product_id')
    lines = update.message.text.strip().split('\n')
    if len(lines) < 4:
        await update.message.reply_text("❌ حداقل ۴ خط بفرست.")
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
    await update.message.reply_text("✅ محصول ویرایش شد.")
    clear_states(context)
    await admin_panel(update, context)


async def delete_product_confirm(query: CallbackQuery, ctx, pid):
    p = dm.get_product(pid)
    if not p:
        await query.answer("یافت نشد")
        return
    kb = [
        [InlineKeyboardButton("✅ بله", callback_data=f"confirmdel_{pid}")],
        [InlineKeyboardButton("❌ انصراف", callback_data="manage_products")]
    ]
    await query.edit_message_text(f"⚠️ حذف `{p['name']}` مطمئنی؟", reply_markup=InlineKeyboardMarkup(kb))


async def confirm_delete_product(query: CallbackQuery, ctx, pid):
    dm.delete_product(pid)
    await query.answer("حذف شد")
    await manage_products(query, ctx)


async def increase_stock_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    context.user_data['awaiting_stock_increase'] = True
    await update.message.reply_text("📈 **افزایش موجودی**\nبنویس: `product_id amount`\nمثال: `1 50`")


async def decrease_stock_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    context.user_data['awaiting_stock_decrease'] = True
    await update.message.reply_text("📉 **کسر موجودی**\nبنویس: `product_id amount`\nمثال: `1 10`")


async def handle_stock_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_stock_increase') or context.user_data.get('awaiting_stock_decrease'):
        parts = update.message.text.split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            await update.message.reply_text("❌ فرمت اشتباه. مثال: `1 50`")
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
        await update.message.reply_text(f"✅ موجودی {p['name']} شد: {dm.get_product(pid)['stock']}")
        clear_states(context)
        await admin_panel(update, context)


async def increase_all_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_increase_all'] = True
    await update.message.reply_text("💰 مبلغ افزایش همگانی رو بنویس:")


async def decrease_all_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_decrease_all'] = True
    await update.message.reply_text("💸 مبلغ کسر همگانی رو بنویس:")


async def handle_all_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        if amount <= 0:
            await update.message.reply_text("❌ عدد مثبت بفرست.")
            return
    except ValueError:
        await update.message.reply_text("❌ عدد بفرست.")
        return
    if context.user_data.get('awaiting_increase_all'):
        n = dm.increase_all(amount)
        await update.message.reply_text(f"✅ {n} کاربر هر کدام {fmt(amount)} ت گرفتند.")
        context.user_data.pop('awaiting_increase_all', None)
    elif context.user_data.get('awaiting_decrease_all'):
        n = dm.decrease_all(amount)
        await update.message.reply_text(f"✅ از {n} کاربر هر کدام {fmt(amount)} ت کسر شد.")
        context.user_data.pop('awaiting_decrease_all', None)
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
        if isinstance(upd, CallbackQuery):
            await safe_edit(msg, "📭 سفارشی نیست.", reply_markup=kb)
        else:
            await msg.reply_text("📭 سفارشی نیست.", reply_markup=kb)
        return
    kb = []
    for o in orders[:20]:
        kb.append([InlineKeyboardButton(f"#{o['order_id']} | {fmt(o['total'])} ت", callback_data=f"orddet_{o['order_id']}")])
    kb.append([InlineKeyboardButton("🗑️ خالی کردن", callback_data=f"clrord_{'_'.join(statuses)}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
    if "waiting_admin" in statuses:
        title = "📥 سفارش‌های در انتظار"
    elif "completed" in statuses:
        title = "✅ سفارش‌های تکمیل شده"
    else:
        title = "❌ سفارش‌های رد شده"
    markup = InlineKeyboardMarkup(kb)
    if isinstance(upd, CallbackQuery):
        await safe_edit(msg, f"**{title}**", reply_markup=markup)
    else:
        await msg.reply_text(f"**{title}**", reply_markup=markup)


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
    clear_states(ctx)
    ctx.user_data['sending_config_for'] = oid
    await query.edit_message_text(f"📤 کانفیگ سفارش `{oid}` رو بفرست (متن/عکس/فایل):")


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
        await update.message.reply_text(f"✅ کانفیگ ارسال شد و سفارش `{oid}` تکمیل شد.")
        context.user_data.pop('sending_config_for', None)
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
            await ctx.bot.send_message(
                int(o['user_id']),
                f"❌ سفارش `{oid}` رد شد.\n💰 {fmt(o['total'])} ت برگشت به کیف پول."
            )
        except Exception:
            pass
    dm.update_order(oid, {"status": "rejected"})
    await query.answer("رد شد")
    await show_orders_by_status(query, ctx, ['waiting_admin'])


async def show_topup_requests(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    pending = [r for r in dm.data["topup_requests"] if r.get("status") == "pending"]
    if not pending:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]])
        if isinstance(upd, CallbackQuery):
            await safe_edit(msg, "📭 درخواستی نیست.", reply_markup=kb)
        else:
            await msg.reply_text("📭 درخواستی نیست.", reply_markup=kb)
        return
    kb = []
    for r in pending[:20]:
        kb.append([InlineKeyboardButton(f"#{r['request_id']} | {fmt(r['amount'])} ت", callback_data=f"topdet_{r['request_id']}")])
    kb.append([InlineKeyboardButton("🗑️ خالی کردن", callback_data="clrtop")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
    markup = InlineKeyboardMarkup(kb)
    if isinstance(upd, CallbackQuery):
        await safe_edit(msg, "💰 **درخواست‌های شارژ**", reply_markup=markup)
    else:
        await msg.reply_text("💰 **درخواست‌های شارژ**", reply_markup=markup)


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
        f"📅 {r.get('date', '')}\n"
        f"📌 {r.get('status', 'pending')}"
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
        await ctx.bot.send_photo(
            query.message.chat_id, r['receipt_photo'],
            caption=text, reply_markup=InlineKeyboardMarkup(kb)
        )
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
        await ctx.bot.send_message(
            int(r['user_id']),
            f"✅ شارژ تأیید شد.\n💰 {fmt(r['amount'])} ت اضافه شد."
        )
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


async def user_check_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    context.user_data['awaiting_user_check'] = True
    await update.message.reply_text("👤 شناسه عددی کاربر رو بنویس:")


async def handle_user_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()
    if not uid.isdigit():
        await update.message.reply_text("❌ عدد بفرست.")
        return
    u = dm.get_user(uid)
    banned = dm.is_banned(uid)
    ud = user_display(uid, u.get("username", ""))
    await update.message.reply_text(
        f"👤 **اطلاعات کاربر**\n\n{ud}\n"
        f"💰 موجودی: {fmt(u.get('balance', 0))} ت\n"
        f"📦 سفارشات: {len(u.get('orders', []))}\n"
        f"🚫 وضعیت: {'مسدود' if banned else 'فعال'}"
    )
    context.user_data.pop('awaiting_user_check', None)


async def ban_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    context.user_data['awaiting_ban_toggle'] = True
    await update.message.reply_text("🚫 شناسه عددی کاربر رو بنویس:")


async def handle_ban_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()
    if not uid.isdigit():
        await update.message.reply_text("❌ عدد بفرست.")
        return
    if dm.is_banned(uid):
        dm.unban(uid)
        await update.message.reply_text(f"✅ کاربر `{uid}` آزاد شد.")
    else:
        dm.ban(uid)
        await update.message.reply_text(f"🚫 کاربر `{uid}` مسدود شد.")
    context.user_data.pop('awaiting_ban_toggle', None)


async def wallet_admin_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_states(context)
    context.user_data['awaiting_wallet_user'] = True
    await update.message.reply_text("💰 شناسه عددی کاربر رو بنویس:")


async def handle_wallet_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_wallet_user'):
        uid = update.message.text.strip()
        if not uid.isdigit():
            await update.message.reply_text("❌ عدد بفرست.")
            return
        context.user_data['wallet_target'] = uid
        context.user_data['awaiting_wallet_user'] = False
        context.user_data['awaiting_wallet_amount'] = True
        u = dm.get_user(uid)
        await update.message.reply_text(
            f"موجودی فعلی: {fmt(u.get('balance', 0))} ت\n"
            f"مبلغ تغییر (مثبت یا منفی) رو بنویس:"
        )
    elif context.user_data.get('awaiting_wallet_amount'):
        try:
            amount = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ عدد بفرست.")
            return
        uid = context.user_data.get('wallet_target')
        u = dm.get_user(uid)
        u['balance'] = max(0, u.get('balance', 0) + amount)
        dm.save_data()
        await update.message.reply_text(f"✅ موجودی `{uid}` شد {fmt(u['balance'])} ت")
        context.user_data.pop('wallet_target', None)
        context.user_data.pop('awaiting_wallet_amount', None)


async def set_card_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_card'] = True
    await update.message.reply_text("💳 شماره کارت جدید رو بفرست:")


async def set_support_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_support'] = True
    await update.message.reply_text("🛠 آیدی پشتیبانی (مثال @username):")


async def handle_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_card'):
        dm.data["card_number"] = update.message.text.strip()
        dm.save_data()
        await update.message.reply_text("✅ شماره کارت ثبت شد.")
        context.user_data.pop('awaiting_card', None)
    elif context.user_data.get('awaiting_support'):
        dm.data["support_username"] = update.message.text.strip()
        dm.save_data()
        await update.message.reply_text("✅ پشتیبانی ثبت شد.")
        context.user_data.pop('awaiting_support', None)


async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owners = dm.data["owners"]
    admins = dm.data["admins"]
    await update.message.reply_text(
        f"👑 **مالکین:**\n" + "\n".join(owners) +
        f"\n\n🛡 **ادمین‌ها:**\n" + ("\n".join(admins) if admins else "هیچ")
    )


async def add_admin_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_add_admin'] = True
    await update.message.reply_text("➕ شناسه عددی ادمین جدید:")


async def remove_admin_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_remove_admin'] = True
    await update.message.reply_text("➖ شناسه عددی ادمین:")


async def handle_admin_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()
    if context.user_data.get('awaiting_add_admin'):
        if dm.add_admin(uid):
            await update.message.reply_text(f"✅ `{uid}` ادمین شد.")
        else:
            await update.message.reply_text("❌ از قبل ادمینه.")
        context.user_data.pop('awaiting_add_admin', None)
    elif context.user_data.get('awaiting_remove_admin'):
        if dm.remove_admin(uid):
            await update.message.reply_text(f"✅ `{uid}` حذف شد.")
        else:
            await update.message.reply_text("❌ ادمین نیست.")
        context.user_data.pop('awaiting_remove_admin', None)


async def broadcast_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_broadcast'] = True
    await update.message.reply_text("📢 متن پیام همگانی رو بفرست:\n(برای انصراف /cancel)")


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
    await update.message.reply_text(f"✅ به {sent} کاربر ارسال شد.")
    context.user_data.pop('awaiting_broadcast', None)


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
    async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    try:
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
        elif data == "admin_orders_pending":
            await show_orders_by_status(query, context, ['waiting_admin', 'waiting_receipt'])
        elif data == "admin_orders_completed":
            await show_orders_by_status(query, context, ['completed'])
        elif data == "admin_orders_rejected":
            await show_orders_by_status(query, context, ['rejected'])
        elif data.startswith("prod_"):
            await product_details(query, context, int(data.split("_")[1]))
        elif data.startswith("cartadd_"):
            await add_to_cart_cb(query, context, int(data.split("_")[1]))
        elif data.startswith("cartdel_"):
            await remove_cart_item(query, context, int(data.split("_")[1]))
        elif data == "clearcart":
            await clear_cart(query, context)
        elif data == "checkout":
            await checkout(query, context)
        elif data == "pay_wallet":
            await pay_wallet(query, context)
        elif data == "request_topup":
            await request_topup_start(query, context)
        elif data.startswith("orddet_"):
            await view_order_detail(query, context, data[7:])
        elif data.startswith("appr_"):
            await approve_order_prompt(query, context, data[5:])
        elif data.startswith("rej_"):
            await reject_order(query, context, data[4:])
        elif data.startswith("vcfg_"):
            await view_config(query, context, data[5:])
        elif data.startswith("editp_"):
            await edit_product_prompt(query, context, int(data.split("_")[1]))
        elif data.startswith("delp_"):
            await delete_product_confirm(query, context, int(data.split("_")[1]))
        elif data.startswith("confirmdel_"):
            await confirm_delete_product(query, context, int(data.split("_")[1]))
        elif data.startswith("topdet_"):
            await view_topup_detail(query, context, data[7:])
        elif data.startswith("apprtop_"):
            await approve_topup(query, context, data[7:])
        elif data.startswith("rejtop_"):
            await reject_topup(query, context, data[7:])
        elif data == "clrtop":
            await clear_topups(query, context)
        elif data == "ord_waiting":
            await show_orders_by_status(query, context, ['waiting_admin'])
        elif data == "ord_completed":
            await show_orders_by_status(query, context, ['completed'])
        elif data == "ord_rejected":
            await show_orders_by_status(query, context, ['rejected'])
        elif data.startswith("clrord_"):
            await clear_orders(query, context, data[7:])
        else:
            await query.answer()
    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        try:
            await query.answer("❌ خطا", show_alert=True)
        except Exception:
            pass


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
    elif text == "💰 درخواست‌های شارژ":
        await show_topup_requests(update, context)
    elif text == "💰 کیف پول کاربر":
        await wallet_admin_prompt(update, context)
    elif text == "👤 بررسی کاربر":
        await user_check_prompt(update, context)
    elif text == "🚫 مسدود/آزاد":
        await ban_prompt(update, context)
    elif text == "🛒 باز/بستن فروشگاه":
        await toggle_shop(update, context)
    elif text == "💳 شماره کارت" and dm.is_owner(uid):
        await set_card_prompt(update, context)
    elif text == "🛠 پشتیبانی" and dm.is_owner(uid):
        await set_support_prompt(update, context)
    elif text == "👥 لیست ادمین‌ها" and dm.is_owner(uid):
        await list_admins(update, context)
    elif text == "➕ افزودن ادمین" and dm.is_owner(uid):
        await add_admin_prompt(update, context)
    elif text == "➖ حذف ادمین" and dm.is_owner(uid):
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


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if dm.is_banned(uid) and not dm.is_admin(uid):
        await update.message.reply_text("🚫 مسدود هستی.")
        return

    if context.user_data.get('awaiting_topup_amount'):
        await handle_topup_amount(update, context)
        return
    if context.user_data.get('awaiting_topup_receipt'):
        await handle_topup_receipt(update, context)
        return
    if context.user_data.get('sending_config_for'):
        await send_config(update, context)
        return
    if context.user_data.get('awaiting_increase_all') or context.user_data.get('awaiting_decrease_all'):
        await handle_all_balance(update, context)
        return
    if context.user_data.get('awaiting_edit_product'):
        await handle_edit_product(update, context)
        return
    if context.user_data.get('awaiting_user_check'):
        await handle_user_check(update, context)
        return
    if context.user_data.get('awaiting_ban_toggle'):
        await handle_ban_toggle(update, context)
        return
    if context.user_data.get('awaiting_wallet_user') or context.user_data.get('awaiting_wallet_amount'):
        await handle_wallet_admin(update, context)
        return
    if context.user_data.get('awaiting_card') or context.user_data.get('awaiting_support'):
        await handle_settings(update, context)
        return
    if context.user_data.get('awaiting_add_admin') or context.user_data.get('awaiting_remove_admin'):
        await handle_admin_edit(update, context)
        return
    if context.user_data.get('awaiting_broadcast'):
        await handle_broadcast(update, context)
        return
    if (context.user_data.get('awaiting_product_name') or
        context.user_data.get('awaiting_product_price') or
        context.user_data.get('awaiting_product_stock')):
        await handle_add_product(update, context)
        return
    if context.user_data.get('awaiting_stock_increase') or context.user_data.get('awaiting_stock_decrease'):
        await handle_stock_change(update, context)
        return

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
    elif text == "ℹ️ راهنما":
        await show_help(update, context)
    elif text == "📞 پشتیبانی":
        await show_support(update, context)
    else:
        await update.message.reply_text("از دکمه‌ها استفاده کن.")


application = Application.builder().token(BOT_TOKEN).updater(None).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("cancel", cancel))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.PHOTO, message_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

flask_app = Flask(__name__)


@flask_app.route("/")
def index():
    return "✅ Zifo Shop Bot فعال است"


@flask_app.route("/health")
def health():
    return "OK"


@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        update_data = request.get_json(force=True)
        update = Update.de_json(update_data, application.bot)

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
