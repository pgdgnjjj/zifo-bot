import json
import os
import logging
import random
import string
from datetime import datetime, timedelta

from flask import Flask, request
from supabase import create_client, Client
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ChatMember
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# =========================================================
#             👑 تنظیمات مالکین و ادمین‌ها
# =========================================================
OWNER_IDS = [
    "8407513032",
    "8221493883",
    "8950854926",
]

DEFAULT_ADMIN_IDS = [
    # "123456789",
]

BOT_TOKEN = "8966599896:AAHir-ijsCTxm7C_7qO_ZGAcegp4RViUt8s"

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


def gen_test_id():
    return f"TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100,999)}"


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
    'new_app_name', 'awaiting_add_owner', 'awaiting_remove_owner',
    'adding_config_pid', 'awaiting_config_add', 'awaiting_coupon_delete',
    'awaiting_dm_user', 'awaiting_dm_text', 'dm_target_user',
    'awaiting_help_text', 'awaiting_test_config', 'awaiting_test_platform',
    'test_user_target', 'awaiting_test_review',
    'awaiting_channel', 'awaiting_group', 'awaiting_forced_channel',
    'awaiting_forced_group', 'awaiting_channel_id', 'awaiting_group_id',
    'awaiting_channel_link', 'awaiting_group_link'
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
                data.setdefault("admin_logs", [])
                data.setdefault("test_requests", [])
                data.setdefault("test_stats", {"total_tests": 0, "unique_users": []})
                data.setdefault("apps_text", "📱 برای اتصال، از برنامه‌های زیر استفاده کن:")

                # عضویت اجباری
                data.setdefault("force_join", {
                    "enabled": False,
                    "channel_id": "",
                    "channel_link": "",
                    "group_id": "",
                    "group_link": "",
                    "require_channel": False,
                    "require_group": False,
                    "message": "🔒 برای استفاده از ربات، ابتدا در کانال و گروه ما عضو شوید:"
                })

                db_owners = set(data.get("owners", []))
                db_admins = set(data.get("admins", []))
                data["owners"] = list(db_owners | set(OWNER_IDS))
                data["admins"] = list(db_admins | set(DEFAULT_ADMIN_IDS))

                self.data = data
                self.save_data()
                return data
        except Exception as e:
            logger.error(f"Supabase load error: {e}")
        return self.create_empty()

    def create_empty(self):
        data = {
            "owners": list(OWNER_IDS),
            "admins": list(DEFAULT_ADMIN_IDS),
            "products": [], "users": {},
            "orders": [], "topup_requests": [], "broadcast_history": [],
            "support_username": "@Zifo_support",
            "user_help_text": "🎮 راهنمای خرید",
            "banned_users": [], "coupons": {},
            "ref_settings": {"bonus": 5000, "min_purchase": 0, "enabled": True},
            "welcome_msg": "🌟 به فروشگاه Zifo خوش آمدید!",
            "cards": [], "apps": [],
            "admin_logs": [],
            "test_requests": [],
            "test_stats": {"total_tests": 0, "unique_users": []},
            "apps_text": "📱 برای اتصال، از برنامه‌های زیر استفاده کن:",
            "shop_status": {"is_open": True, "closed_message": "🚫 فروشگاه بسته است."},
            "force_join": {
                "enabled": False,
                "channel_id": "",
                "channel_link": "",
                "group_id": "",
                "group_link": "",
                "require_channel": False,
                "require_group": False,
                "message": "🔒 برای استفاده از ربات، ابتدا در کانال و گروه ما عضو شوید:"
            }
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
                "invited_by": None, "invited_count": 0,
                "tests_count": 0
            }
            self.save_data()
        u = self.data["users"][uid]
        if "ref_code" not in u or not u["ref_code"]:
            u["ref_code"] = gen_ref_code(uid)
            self.save_data()
        u.setdefault("tests_count", 0)
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

    def add_owner(self, uid):
        uid = str(uid)
        if uid not in self.data["owners"]:
            self.data["owners"].append(uid)
            if uid in self.data["admins"]:
                self.data["admins"].remove(uid)
            self.save_data()
            return True
        return False

    def remove_owner(self, uid):
        uid = str(uid)
        if uid in self.data["owners"]:
            if len(self.data["owners"]) <= 1:
                return False
            self.data["owners"].remove(uid)
            self.save_data()
            return True
        return False

    def get_owners_list(self):
        return list(self.data.get("owners", []))

    def get_admins_list(self):
        return list(self.data.get("admins", []))

    def is_source_owner(self, uid):
        return str(uid) in OWNER_IDS

    def is_source_admin(self, uid):
        return str(uid) in DEFAULT_ADMIN_IDS

    def add_admin_log(self, actor_id, target_id, action):
        self.data.setdefault("admin_logs", [])
        self.data["admin_logs"].append({
            "actor": str(actor_id),
            "target": str(target_id),
            "action": action,
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        if len(self.data["admin_logs"]) > 200:
            self.data["admin_logs"] = self.data["admin_logs"][-200:]
        self.save_data()

    def get_admin_logs(self, limit=30):
        logs = self.data.get("admin_logs", [])
        return logs[-limit:][::-1]

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

    def add_test_request(self, req):
        tid = gen_test_id()
        req["test_id"] = tid
        req["date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        req["status"] = "pending"
        self.data.setdefault("test_requests", [])
        self.data["test_requests"].append(req)

        self.data.setdefault("test_stats", {"total_tests": 0, "unique_users": []})
        self.data["test_stats"]["total_tests"] = self.data["test_stats"].get("total_tests", 0) + 1
        uid_str = str(req["user_id"])
        if uid_str not in self.data["test_stats"]["unique_users"]:
            self.data["test_stats"]["unique_users"].append(uid_str)

        u = self.get_user(req["user_id"])
        u["tests_count"] = u.get("tests_count", 0) + 1

        self.save_data()
        return tid

    def get_test(self, tid):
        return next((t for t in self.data.get("test_requests", []) if t.get("test_id") == tid), None)

    def update_test(self, tid, updates):
        t = self.get_test(tid)
        if t:
            t.update(updates)
            self.save_data()
            return True
        return False

    def get_test_stats(self):
        self.data.setdefault("test_stats", {"total_tests": 0, "unique_users": []})
        return self.data["test_stats"]

    # 🔒 توابع عضویت اجباری
    def get_force_join(self):
        self.data.setdefault("force_join", {
            "enabled": False,
            "channel_id": "",
            "channel_link": "",
            "group_id": "",
            "group_link": "",
            "require_channel": False,
            "require_group": False,
            "message": "🔒 برای استفاده از ربات، ابتدا در کانال و گروه ما عضو شوید:"
        })
        return self.data["force_join"]

    def set_force_join(self, updates):
        fj = self.get_force_join()
        fj.update(updates)
        self.data["force_join"] = fj
        self.save_data()


dm = DataManager()


async def safe_edit(message, text, markup=None, reply_markup=None):
    final_markup = reply_markup or markup
    try:
        await message.edit_text(text, reply_markup=final_markup)
        return True
    except Exception as e:
        err = str(e).lower()
        if "not modified" in err or "message to edit" in err or "can't be edited" in err:
            return False
        logger.error(f"edit err: {e}")
        try:
            await message.reply_text(text, reply_markup=final_markup)
        except Exception:
            pass
        return False


async def answer_cb(q, text="", show_alert=False):
    try:
        await q.answer(text, show_alert=show_alert)
    except Exception:
        pass


# =========================================================
#             🔒 بررسی عضویت اجباری
# =========================================================

async def check_membership(bot, user_id):
    """بررسی می‌کنه که کاربر توی کانال/گروه عضو هست یا نه"""
    fj = dm.get_force_join()
    if not fj.get("enabled", False):
        return True, []

    not_joined = []

    # بررسی کانال
    if fj.get("require_channel") and fj.get("channel_id"):
        try:
            member = await bot.get_chat_member(chat_id=fj["channel_id"], user_id=int(user_id))
            if member.status in ["left", "kicked"]:
                not_joined.append("channel")
        except Exception as e:
            logger.error(f"Channel check error: {e}")
            not_joined.append("channel")

    # بررسی گروه
    if fj.get("require_group") and fj.get("group_id"):
        try:
            member = await bot.get_chat_member(chat_id=fj["group_id"], user_id=int(user_id))
            if member.status in ["left", "kicked"]:
                not_joined.append("group")
        except Exception as e:
            logger.error(f"Group check error: {e}")
            not_joined.append("group")

    return len(not_joined) == 0, not_joined


async def show_force_join_message(upd, ctx):
    """پیام عضویت اجباری رو نشون می‌ده"""
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
        is_callback = True
    else:
        msg = upd.message
        user = upd.effective_user
        is_callback = False

    fj = dm.get_force_join()
    message = fj.get("message", "🔒 برای استفاده از ربات، ابتدا در کانال و گروه ما عضو شوید:")

    buttons = []
    if fj.get("require_channel") and fj.get("channel_link"):
        buttons.append([InlineKeyboardButton("📢 عضویت در کانال", url=fj["channel_link"])])
    if fj.get("require_group") and fj.get("group_link"):
        buttons.append([InlineKeyboardButton("👥 عضویت در گروه", url=fj["group_link"])])
    buttons.append([InlineKeyboardButton("✅ عضو شدم، بررسی کن", callback_data="check_membership")])

    kb = InlineKeyboardMarkup(buttons)

    if is_callback:
        await safe_edit(msg, message, reply_markup=kb)
    else:
        await msg.reply_text(message, reply_markup=kb)


def force_join_middleware(func):
    """دکوراتور برای بررسی عضویت قبل از اجرای هر تابع"""
    async def wrapper(upd, ctx, *args, **kwargs):
        # اگه callback هست و داده‌اش چک عضویت هست، skip کن
        if isinstance(upd, CallbackQuery) and upd.data == "check_membership":
            return await func(upd, ctx, *args, **kwargs)

        user = upd.from_user if isinstance(upd, CallbackQuery) else upd.effective_user
        uid = str(user.id)

        # مالکین و ادمین‌ها معاف
        if dm.is_admin(uid):
            return await func(upd, ctx, *args, **kwargs)

        is_member, missing = await check_membership(ctx.bot, uid)
        if not is_member:
            await show_force_join_message(upd, ctx)
            return

        return await func(upd, ctx, *args, **kwargs)

    return wrapper


def main_kb(uid):
    kb = [
        ["🛍️ مشاهده محصولات"],
        ["🛒 سبد خرید من", "👤 حساب کاربری"],
        ["💰 کیف پول", "📱 برنامه‌های اتصال"],
        ["🧪 تست کانفیگ", "🎁 دعوت دوستان"],
        ["📜 سفارش‌های من", "🔍 پیگیری سفارش"],
        ["📞 پشتیبانی", "ℹ️ راهنما"],
    ]
    if dm.is_admin(uid):
        kb.append(["⚙️ پنل مدیریت"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


# =========================================================
#                     منوی اصلی
# =========================================================

async def main_menu(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
    else:
        msg = upd.message
        user = upd.effective_user

    clear_states(ctx)
    uid = str(user.id)
    if dm.is_banned(uid):
        await msg.reply_text("🚫 مسدود هستی.")
        return

    # 🔒 چک عضویت اجباری
    if not dm.is_admin(uid):
        is_member, missing = await check_membership(ctx.bot, uid)
        if not is_member:
            await show_force_join_message(upd, ctx)
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
#                     🧪 سیستم تست کانفیگ
# =========================================================

async def test_config_menu(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
        is_callback = True
    else:
        msg = upd.message
        user = upd.effective_user
        is_callback = False

    uid = str(user.id)
    if dm.is_banned(uid):
        await msg.reply_text("🚫 مسدود هستی.")
        return

    # بررسی عضویت
    if not dm.is_admin(uid):
        is_member, missing = await check_membership(ctx.bot, uid)
        if not is_member:
            await show_force_join_message(upd, ctx)
            return

    text = (
        "🧪 **تست رایگان کانفیگ**\n"
        "━━━━━━━━━━━━━━━\n\n"
        "🎁 می‌تونی **یک بار** کانفیگ ما رو تست کنی\n"
        "✅ سرعت، پینگ و کیفیت رو ببین\n"
        "🚀 اگه راضی بودی، از فروشگاه خرید کن\n\n"
        "📱 **پلتفرم خودت رو انتخاب کن:**"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 اندروید", callback_data="test_android")],
        [InlineKeyboardButton("🍎 iOS", callback_data="test_ios")],
        [InlineKeyboardButton("💻 ویندوز", callback_data="test_windows")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_menu")]
    ])

    if is_callback:
        await safe_edit(msg, text, reply_markup=kb)
    else:
        await msg.reply_text(text, reply_markup=kb)


async def test_platform_selected(upd, ctx, platform):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd, f"📱 {platform}")
    else:
        msg = upd.message
        user = upd.effective_user

    uid = str(user.id)
    u = dm.get_user(uid)
    tests_count = u.get("tests_count", 0)

    if tests_count >= 1:
        await safe_edit(
            msg,
            "❌ **شما قبلاً تست گرفته‌اید!**\n\n"
            "🎯 هر کاربر فقط یک بار می‌تونه تست رایگان بگیره.\n"
            "برای استفاده بیشتر، از فروشگاه خرید کن."
        )
        return

    clear_states(ctx)
    ctx.user_data['awaiting_test_config'] = True
    ctx.user_data['test_user_platform'] = platform
    ctx.user_data['test_target_user'] = uid

    await safe_edit(
        msg,
        f"📱 پلتفرم: **{platform}**\n\n"
        "🔗 **حالا کانفیگت رو بفرست:**\n\n"
        "می‌تونی:\n"
        "• متن کانفیگ (vless/vmess/ss)\n"
        "• لینک ساب\n"
        "• یا فایل کانفیگ\n\n"
        "⚠️ بعد از ارسال، تیم پشتیبانی بررسی می‌کنه."
    )


async def handle_test_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_test_config'):
        return False

    user = update.effective_user
    uid = str(user.id)
    platform = context.user_data.get('test_user_platform', 'نامشخص')

    config_text = ""
    file_id = None
    file_type = None

    if update.message.text:
        config_text = update.message.text
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = "photo"
        config_text = update.message.caption or "(عکس)"
    elif update.message.document:
        file_id = update.message.document.file_id
        file_type = "document"
        config_text = update.message.caption or "(فایل)"

    if not config_text and not file_id:
        await update.message.reply_text("❌ لطفاً کانفیگ، لینک یا فایل بفرست.")
        return True

    u = dm.get_user(uid)
    req = {
        "user_id": uid,
        "username": u.get("username", ""),
        "first_name": u.get("first_name", ""),
        "platform": platform,
        "config_text": config_text[:1000],
        "file_id": file_id,
        "file_type": file_type
    }
    tid = dm.add_test_request(req)
    clear_states(context)

    await update.message.reply_text(
        f"✅ **درخواست تست ثبت شد**\n\n"
        f"🆔 کد: `{tid}`\n"
        f"📱 پلتفرم: {platform}\n\n"
        f"⏳ تیم پشتیبانی به زودی بررسی می‌کنه"
    )

    ud = user_display(uid, u.get("username", ""))
    admin_text = (
        f"🧪 **درخواست تست جدید**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🆔 `{tid}`\n"
        f"👤 {ud}\n"
        f"📛 {u.get('first_name', '-')}\n"
        f"📱 پلتفرم: {platform}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📄 محتوا:\n`{config_text[:500]}`"
    )

    for aid in dm.data["owners"] + dm.data["admins"]:
        try:
            if file_id and file_type == "photo":
                await context.bot.send_photo(
                    int(aid), file_id,
                    caption=admin_text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ قبول", callback_data=f"testok_{tid}"),
                         InlineKeyboardButton("❌ رد", callback_data=f"testno_{tid}")]
                    ])
                )
            elif file_id and file_type == "document":
                await context.bot.send_document(
                    int(aid), file_id,
                    caption=admin_text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ قبول", callback_data=f"testok_{tid}"),
                         InlineKeyboardButton("❌ رد", callback_data=f"testno_{tid}")]
                    ])
                )
            else:
                await context.bot.send_message(
                    int(aid), admin_text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ قبول", callback_data=f"testok_{tid}"),
                         InlineKeyboardButton("❌ رد", callback_data=f"testno_{tid}")]
                    ])
                )
        except Exception:
            pass

    return True


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
        is_callback = True
    else:
        msg = upd.message
        user = upd.effective_user
        is_callback = False

    if dm.is_banned(str(user.id)):
        await msg.reply_text("🚫 مسدود هستی.")
        return

    products = dm.data["products"]
    if not products:
        if is_callback:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_menu")]])
            await safe_edit(msg, "📭 محصولی نیست.", reply_markup=kb)
        else:
            await msg.reply_text("📭 محصولی نیست.")
        return

    kb = []
    for p in products:
        c = "🟢" if p.get("stock", 0) > 0 else "🔴"
        kb.append([InlineKeyboardButton(
            f"{c} {p['name']} ┃ {fmt(p['price'])} ت",
            callback_data=f"prod_{p['id']}"
        )])
    kb.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_menu")])
    markup = InlineKeyboardMarkup(kb)

    text = "🛍️ **محصولات فروشگاه**\n━━━━━━━━━━━━━━━\n👇 یکی رو انتخاب کن:"
    if is_callback:
        await safe_edit(msg, text, reply_markup=markup)
    else:
        await msg.reply_text(text, reply_markup=markup)


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
    stock_status = "🟢 موجود" if stock > 0 else "🔴 ناموجود"

    text = (
        f"🎯 **{p['name']}**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 قیمت: **{fmt(p['price'])} تومان**\n"
        f"📦 موجودی: {stock} عدد\n"
        f"🔑 کانفیگ آماده: {configs_count}\n"
        f"📊 وضعیت: {stock_status}\n"
    )
    if p.get('description'):
        text += f"━━━━━━━━━━━━━━━\n📝 {p['description']}"

    kb = []
    if stock > 0:
        kb.append([InlineKeyboardButton("🛒 افزودن به سبد خرید", callback_data=f"cartadd_{pid}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت به محصولات", callback_data="products_back")])
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
        await answer_cb(upd, "❌ ناموجود", show_alert=True)
        return

    if dm.add_to_cart(str(user.id), pid):
        await answer_cb(upd, "✅ به سبد اضافه شد")
        await show_cart(upd, ctx)
    else:
        await answer_cb(upd, "⚠️ قبلاً در سبد هست", show_alert=True)


# =========================================================
#                     سبد خرید
# =========================================================

async def show_cart(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
        is_callback = True
    else:
        msg = upd.message
        user = upd.effective_user
        is_callback = False

    uid = str(user.id)
    cart = dm.cart_items(uid)

    if not cart:
        text = "🛒 **سبد خرید شما خالی است**\n\n💡 از دکمه 🛍️ محصولات، آیتم اضافه کن."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛍️ مشاهده محصولات", callback_data="products_back")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_menu")]
        ])
        if is_callback:
            await safe_edit(msg, text, reply_markup=kb)
        else:
            await msg.reply_text(text, reply_markup=kb)
        return

    total = dm.cart_total(uid)
    discount = ctx.user_data.get('applied_discount')

    text = "🛒 **سبد خرید شما**\n━━━━━━━━━━━━━━━\n\n"
    for i, it in enumerate(cart, 1):
        text += f"{i}️⃣ {it['name']}\n     💵 {fmt(it['price'])} تومان\n"

    text += f"\n━━━━━━━━━━━━━━━\n💰 **جمع کل:** {fmt(total)} تومان"

    if discount:
        new_total = int(total * (100 - discount['percent']) / 100)
        off = total - new_total
        text += (
            f"\n🎟️ تخفیف: {discount['percent']}% ({fmt(off)} ت)"
            f"\n💵 **قابل پرداخت:** {fmt(new_total)} تومان"
        )

    buttons = []
    for i, it in enumerate(cart):
        buttons.append([InlineKeyboardButton(
            f"❌ حذف {it['name']}",
            callback_data=f"cartdel_{i}"
        )])

    buttons.append([InlineKeyboardButton("🎟️ اعمال کد تخفیف", callback_data="apply_coupon")])
    buttons.append([InlineKeyboardButton("✅ پرداخت با کیف پول", callback_data="checkout")])
    buttons.append([
        InlineKeyboardButton("➕ ادامه خرید", callback_data="products_back"),
        InlineKeyboardButton("🗑️ خالی کردن", callback_data="clearcart")
    ])
    buttons.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_menu")])
    kb = InlineKeyboardMarkup(buttons)

    if is_callback:
        await safe_edit(msg, text, reply_markup=kb)
    else:
        await msg.reply_text(text, reply_markup=kb)


async def remove_cart_item(upd, ctx, idx):
    if isinstance(upd, CallbackQuery):
        user = upd.from_user
        await answer_cb(upd, "حذف شد")
    else:
        user = upd.effective_user
    uid = str(user.id)
    dm.remove_from_cart(uid, idx)
    await show_cart(upd, ctx)


async def clear_cart(upd, ctx):
    if isinstance(upd, CallbackQuery):
        user = upd.from_user
        await answer_cb(upd, "سبد خالی شد")
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
        text = (
            f"❌ **موجودی کافی نیست**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 موجودی: {fmt(bal)} ت\n"
            f"💵 نیاز: {fmt(total)} ت\n"
            f"📉 کمبود: {fmt(total - bal)} ت"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 شارژ کیف پول", callback_data="request_topup")],
            [InlineKeyboardButton("🔙 بازگشت به سبد", callback_data="show_cart")]
        ])
        await safe_edit(msg, text, reply_markup=kb)
        return

    text = (
        f"✅ **تأیید نهایی خرید**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📦 تعداد: {len(cart)} آیتم\n"
    )
    if discount:
        text += f"🎟️ تخفیف: {discount['percent']}%\n"
    text += (
        f"💰 مبلغ: {fmt(total)} تومان\n"
        f"💳 موجودی: {fmt(bal)} تومان\n"
        f"━━━━━━━━━━━━━━━\n"
        f"مطمئنی؟"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ بله، پرداخت کن", callback_data="pay_wallet")],
        [InlineKeyboardButton("❌ انصراف", callback_data="show_cart")]
    ])
    await safe_edit(msg, text, reply_markup=kb)


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
    items_str = "\n".join(f"• {i['name']} - {fmt(i['price'])} ت" for i in cart)
    text = (
        f"✅ **پرداخت موفق!**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🆔 کد سفارش: `{oid}`\n"
        f"💰 مبلغ: {fmt(total)} تومان\n"
        f"📦 تعداد: {len(cart)}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⏳ منتظر تأیید ادمین باش"
    )
    await safe_edit(msg, text)

    for aid in dm.data["owners"] + dm.data["admins"]:
        try:
            await ctx.bot.send_message(
                int(aid),
                f"🛒 **سفارش جدید**\n"
                f"🆔 `{oid}`\n"
                f"👤 {ud}\n"
                f"📦 {items_str}\n"
                f"💰 {fmt(total)} ت"
            )
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
        is_callback = True
    else:
        msg = upd.message
        user = upd.effective_user
        is_callback = False

    uid = str(user.id)
    bal = dm.get_user(uid).get("balance", 0)
    text = (
        f"💰 **کیف پول شما**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💳 موجودی: **{fmt(bal)} تومان**\n"
        f"━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ درخواست شارژ", callback_data="request_topup")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_menu")]
    ])
    if is_callback:
        await safe_edit(msg, text, reply_markup=kb)
    else:
        await msg.reply_text(text, reply_markup=kb)


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
        f"💰 **مبلغ شارژ رو به تومان بنویس:**\n"
        f"(مثال: 50000)\n\n"
        f"💳 کارت: `{card['number']}`\n"
        f"👤 {card.get('holder', '')}\n\n"
        f"برای انصراف /cancel"
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
    await update.message.reply_text(
        f"✅ **درخواست شارژ ثبت شد**\n🆔 `{rid}`\nمنتظر تأیید ادمین باش."
    )
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
    tests = u.get("tests_count", 0)
    await update.message.reply_text(
        f"👤 **حساب کاربری شما**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🆔 {ud}\n"
        f"📛 {u.get('first_name', '-')}\n"
        f"💰 موجودی: {fmt(u.get('balance', 0))} ت\n"
        f"📦 سفارشات: {len(u.get('orders', []))}\n"
        f"🧪 تست‌ها: {tests}\n"
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
        f"🎁 **دعوت دوستان**\n"
        f"━━━━━━━━━━━━━━━\n"
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
    text = "📜 **آخرین سفارش‌های شما**\n━━━━━━━━━━━━━━━\n\n"
    for o in orders:
        status_emoji = {
            "waiting_admin": "⏳ در انتظار",
            "completed": "✅ تکمیل شده",
            "rejected": "❌ رد شده"
        }.get(o.get("status"), "❓")
        text += (
            f"{status_emoji}\n"
            f"🆔 {o['order_id']}\n"
            f"💰 {fmt(o['total'])} ت | 📅 {o.get('date', '')[:10]}\n\n"
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
        f"🔍 **سفارش {oid}**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📌 وضعیت: {status_text}\n"
        f"💰 مبلغ: {fmt(o['total'])} ت\n"
        f"📅 تاریخ: {o.get('date', '')}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📦 محصولات:\n{items_str}"
    )
    await update.message.reply_text(text, reply_markup=main_kb(update.effective_user.id))
    context.user_data.pop('awaiting_order_track', None)


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = dm.data.get("user_help_text", "راهنما موجود نیست.")
    await update.message.reply_text(txt, reply_markup=main_kb(update.effective_user.id))


async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = dm.data.get("support_username", "@Zifo_support")
    await update.message.reply_text(f"📞 **پشتیبانی**\n{s}", reply_markup=main_kb(update.effective_user.id))


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
            ["🛠 پشتیبانی", "📝 راهنمای کاربر"],
            ["👑 مدیریت مالکین", "🛡 مدیریت ادمین‌ها"],
            ["📜 لاگ تغییرات", "✉️ پیام به کاربر"],
            ["🧪 مدیریت تست‌ها", "📊 آمار تست‌ها"],
            ["🔒 عضویت اجباری"],
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
            ["🚫 مسدود/آزاد", "🧪 مدیریت تست‌ها"],
            ["🔙 بازگشت"]
        ]
    await msg.reply_text("⚙️ **پنل مدیریت**", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))


# =========================================================
#             🔒 مدیریت عضویت اجباری
# =========================================================

async def force_join_menu(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
        is_callback = True
    else:
        msg = upd.message
        user = upd.effective_user
        is_callback = False

    if not dm.is_owner(user.id):
        await msg.reply_text("❌ فقط مالکین دسترسی دارن.")
        return

    fj = dm.get_force_join()
    status = "✅ فعال" if fj.get("enabled") else "❌ غیرفعال"

    text = (
        f"🔒 **مدیریت عضویت اجباری**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 وضعیت کلی: {status}\n\n"
        f"📢 کانال:\n"
        f"   • نیاز: {'✅' if fj.get('require_channel') else '❌'}\n"
        f"   • آیدی: `{fj.get('channel_id') or 'تنظیم نشده'}`\n"
        f"   • لینک: {fj.get('channel_link') or 'تنظیم نشده'}\n\n"
        f"👥 گروه:\n"
        f"   • نیاز: {'✅' if fj.get('require_group') else '❌'}\n"
        f"   • آیدی: `{fj.get('group_id') or 'تنظیم نشده'}`\n"
        f"   • لینک: {fj.get('group_link') or 'تنظیم نشده'}\n"
        f"━━━━━━━━━━━━━━━"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'🔴 غیرفعال کن' if fj.get('enabled') else '🟢 فعال کن'}",
            callback_data="fj_toggle"
        )],
        [InlineKeyboardButton("📢 تنظیم کانال", callback_data="fj_channel")],
        [InlineKeyboardButton("👥 تنظیم گروه", callback_data="fj_group")],
        [InlineKeyboardButton("📝 تغییر پیام", callback_data="fj_message")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])

    if is_callback:
        await safe_edit(msg, text, reply_markup=kb)
    else:
        await msg.reply_text(text, reply_markup=kb)


async def fj_toggle(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message

    fj = dm.get_force_join()
    new_state = not fj.get("enabled", False)
    dm.set_force_join({"enabled": new_state})
    await answer_cb(upd, f"{'✅ فعال شد' if new_state else '❌ غیرفعال شد'}", show_alert=True)
    await force_join_menu(upd, ctx)


async def fj_channel_prompt(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message

    clear_states(ctx)
    ctx.user_data['awaiting_channel_id'] = True
    await msg.reply_text(
        "📢 **تنظیم کانال**\n\n"
        "🔹 مرحله ۱ از ۲\n\n"
        "آیدی عددی کانال رو بفرست:\n"
        "مثال: `-1001234567890`\n\n"
        "💡 برای گرفتن آیدی:\n"
        "کانال رو به @userinfobot فوروارد کن\n\n"
        "برای حذف کانال، بنویس: `حذف`"
    )


async def handle_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_channel_id'):
        return False
    text = update.message.text.strip()

    if text == "حذف":
        dm.set_force_join({"channel_id": "", "channel_link": "", "require_channel": False})
        clear_states(context)
        await update.message.reply_text("✅ کانال حذف شد.")
        return True

    # قبول هم آیدی عددی، هم لینک
    channel_id = text
    if text.startswith("https://t.me/"):
        channel_id = "@" + text.replace("https://t.me/", "")

    context.user_data['new_channel_id'] = channel_id
    context.user_data['awaiting_channel_id'] = False
    context.user_data['awaiting_channel_link'] = True
    await update.message.reply_text(
        "✅ ثبت شد\n\n"
        "🔹 مرحله ۲ از ۲\n\n"
        "حالا لینک کانال رو بفرست:\n"
        "مثال: `https://t.me/your_channel`"
    )
    return True


async def handle_channel_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_channel_link'):
        return False
    link = update.message.text.strip()
    channel_id = context.user_data.get('new_channel_id')

    # چک کن ربات توی کانال ادمینه
    try:
        chat = await context.bot.get_chat(channel_id)
        bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)
        if bot_member.status not in ["administrator", "creator"]:
            await update.message.reply_text(
                "⚠️ **هشدار:** ربات توی این کانال ادمین نیست!\n\n"
                "برای بررسی عضویت، ربات باید ادمین کانال باشه.\n"
                "لطفاً ربات رو ادمین کن و دوباره امتحان کن.\n\n"
                "ادامه می‌دم ولی ممکنه کار نکنه."
            )
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ نتونستم کانال رو چک کنم: {e}\n\n"
            f"مطمئن شو ربات توی کانال ادمینه.\n"
            f"ادامه می‌دم."
        )

    dm.set_force_join({
        "channel_id": channel_id,
        "channel_link": link,
        "require_channel": True
    })
    clear_states(context)
    await update.message.reply_text(
        f"✅ **کانال تنظیم شد**\n\n"
        f"📢 آیدی: `{channel_id}`\n"
        f"🔗 لینک: {link}\n"
        f"✅ نیاز به عضویت: فعال"
    )
    return True


async def fj_group_prompt(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message

    clear_states(ctx)
    ctx.user_data['awaiting_group_id'] = True
    await msg.reply_text(
        "👥 **تنظیم گروه**\n\n"
        "🔹 مرحله ۱ از ۲\n\n"
        "آیدی عددی گروه رو بفرست:\n"
        "مثال: `-1001234567890`\n\n"
        "💡 برای گرفتن آیدی:\n"
        "گروه رو به @userinfobot فوروارد کن\n\n"
        "برای حذف گروه، بنویس: `حذف`"
    )


async def handle_group_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_group_id'):
        return False
    text = update.message.text.strip()

    if text == "حذف":
        dm.set_force_join({"group_id": "", "group_link": "", "require_group": False})
        clear_states(context)
        await update.message.reply_text("✅ گروه حذف شد.")
        return True

    group_id = text
    if text.startswith("https://t.me/"):
        group_id = "@" + text.replace("https://t.me/", "")

    context.user_data['new_group_id'] = group_id
    context.user_data['awaiting_group_id'] = False
    context.user_data['awaiting_group_link'] = True
    await update.message.reply_text(
        "✅ ثبت شد\n\n"
        "🔹 مرحله ۲ از ۲\n\n"
        "حالا لینک گروه رو بفرست:\n"
        "مثال: `https://t.me/your_group`"
    )
    return True


async def handle_group_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_group_link'):
        return False
    link = update.message.text.strip()
    group_id = context.user_data.get('new_group_id')

    try:
        chat = await context.bot.get_chat(group_id)
        bot_member = await context.bot.get_chat_member(group_id, context.bot.id)
        if bot_member.status not in ["administrator", "creator", "member"]:
            await update.message.reply_text(
                "⚠️ **هشدار:** ربات توی این گروه نیست!\n\n"
                "برای بررسی عضویت، ربات باید توی گروه باشه.\n\n"
                "ادامه می‌دم ولی ممکنه کار نکنه."
            )
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ نتونستم گروه رو چک کنم: {e}\n\n"
            f"ادامه می‌دم."
        )

    dm.set_force_join({
        "group_id": group_id,
        "group_link": link,
        "require_group": True
    })
    clear_states(context)
    await update.message.reply_text(
        f"✅ **گروه تنظیم شد**\n\n"
        f"👥 آیدی: `{group_id}`\n"
        f"🔗 لینک: {link}\n"
        f"✅ نیاز به عضویت: فعال"
    )
    return True


async def fj_message_prompt(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message

    clear_states(ctx)
    ctx.user_data['awaiting_forced_message'] = True
    current = dm.get_force_join().get("message", "")
    await msg.reply_text(
        f"📝 **تغییر پیام عضویت اجباری**\n\n"
        f"متن فعلی:\n{current}\n\n"
        f"متن جدید رو بنویس:"
    )


async def handle_forced_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_forced_message'):
        return False
    dm.set_force_join({"message": update.message.text})
    clear_states(context)
    await update.message.reply_text("✅ پیام تغییر کرد.")
    return True


# =========================================================
#             ادامه پنل ادمین
# =========================================================

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

    test_stats = dm.get_test_stats()
    total_tests = test_stats.get("total_tests", 0)
    unique_testers = len(test_stats.get("unique_users", []))

    await update.message.reply_text(
        f"📊 **آمار ربات**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👥 کاربران: {users}\n"
        f"📦 محصولات: {len(products)}\n"
        f"📊 موجودی کل: {total_stock}\n"
        f"🛒 کل سفارش: {len(orders)}\n"
        f"⏳ در انتظار: {len(pending)}\n"
        f"✅ تکمیل: {len(completed)}\n"
        f"💰 درآمد: {fmt(revenue)} ت\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🧪 کل تست‌ها: {total_tests}\n"
        f"👤 کاربران تست‌کننده: {unique_testers}"
    )


async def show_test_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    stats = dm.get_test_stats()
    total = stats.get("total_tests", 0)
    unique_ids = stats.get("unique_users", [])

    text = (
        f"📊 **آمار تست کانفیگ**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🧪 کل تست‌ها: **{total}**\n"
        f"👤 کاربران یکتا: **{len(unique_ids)}**\n"
        f"━━━━━━━━━━━━━━━\n"
    )

    if unique_ids:
        text += "👥 **لیست کاربران تست‌کننده:**\n\n"
        recent = unique_ids[-20:]
        for i, uid in enumerate(recent, 1):
            u = dm.data["users"].get(str(uid), {})
            name = u.get("first_name", "?") or "?"
            uname = u.get("username", "")
            tests = u.get("tests_count", 0)
            uname_str = f"@{uname}" if uname else "—"
            text += f"{i}. {name} | {uname_str}\n   🆔 `{uid}` | 🧪 {tests} تست\n\n"
        if len(unique_ids) > 20:
            text += f"... و {len(unique_ids) - 20} کاربر دیگه"

    await send_long_message(update, text)


async def show_tests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_admin(update.effective_user.id):
        return

    tests = dm.data.get("test_requests", [])
    pending = [t for t in tests if t.get("status") == "pending"]
    approved = [t for t in tests if t.get("status") == "approved"]
    rejected = [t for t in tests if t.get("status") == "rejected"]

    text = (
        f"🧪 **مدیریت تست‌ها**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⏳ در انتظار: {len(pending)}\n"
        f"✅ تأیید شده: {len(approved)}\n"
        f"❌ رد شده: {len(rejected)}\n"
        f"📊 کل: {len(tests)}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⏳ در انتظار ({len(pending)})", callback_data="tests_pending")],
        [InlineKeyboardButton(f"✅ تأیید شده ({len(approved)})", callback_data="tests_approved")],
        [InlineKeyboardButton(f"❌ رد شده ({len(rejected)})", callback_data="tests_rejected")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    await update.message.reply_text(text, reply_markup=kb)


async def show_tests_by_status(upd, ctx, status):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
        is_callback = True
    else:
        msg = upd.message
        is_callback = False

    tests = [t for t in dm.data.get("test_requests", []) if t.get("status") == status]
    tests = sorted(tests, key=lambda x: x.get("date", ""), reverse=True)

    if not tests:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="tests_menu_back")]])
        label = {"pending": "⏳ در انتظار", "approved": "✅ تأیید شده", "rejected": "❌ رد شده"}.get(status, "")
        if is_callback:
            await safe_edit(msg, f"📭 هیچ تستی با وضعیت «{label}» نیست.", reply_markup=kb)
        else:
            await msg.reply_text(f"📭 هیچ تستی با وضعیت «{label}» نیست.", reply_markup=kb)
        return

    kb = []
    for t in tests[:20]:
        u = dm.data["users"].get(str(t['user_id']), {})
        name = u.get("first_name", "?") or "?"
        kb.append([InlineKeyboardButton(
            f"🧪 {name} | {t.get('platform', '?')} | {t['test_id'][-8:]}",
            callback_data=f"testdet_{t['test_id']}"
        )])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="tests_menu_back")])
    label = {"pending": "⏳ در انتظار", "approved": "✅ تأیید شده", "rejected": "❌ رد شده"}.get(status, "")

    if is_callback:
        await safe_edit(msg, f"🧪 **تست‌های {label}**\n({len(tests)} مورد)", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await msg.reply_text(f"🧪 **تست‌های {label}**\n({len(tests)} مورد)", reply_markup=InlineKeyboardMarkup(kb))


async def view_test_detail(query: CallbackQuery, ctx, tid):
    t = dm.get_test(tid)
    if not t:
        await query.answer("یافت نشد")
        return

    u = dm.data["users"].get(str(t['user_id']), {})
    name = u.get("first_name", "?") or "?"
    uname = u.get("username", "")
    uname_str = f"@{uname}" if uname else "—"

    status_text = {
        "pending": "⏳ در انتظار",
        "approved": "✅ تأیید شده",
        "rejected": "❌ رد شده"
    }.get(t.get("status"), "❓")

    text = (
        f"🧪 **تست کانفیگ**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🆔 `{t['test_id']}`\n"
        f"👤 {name} | {uname_str}\n"
        f"📱 `{t['user_id']}`\n"
        f"📲 پلتفرم: {t.get('platform', '?')}\n"
        f"📅 {t.get('date', '')}\n"
        f"📊 وضعیت: {status_text}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📄 محتوا:\n`{t.get('config_text', '')[:500]}`"
    )

    kb = []
    if t.get("status") == "pending":
        kb.append([
            InlineKeyboardButton("✅ تأیید", callback_data=f"testap_{tid}"),
            InlineKeyboardButton("❌ رد", callback_data=f"testrj_{tid}")
        ])
    kb.append([InlineKeyboardButton("✉️ پیام به کاربر", callback_data=f"testdm_{tid}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="tests_pending")])

    if t.get("file_id") and t.get("file_type") == "photo":
        try:
            await query.message.delete()
        except Exception:
            pass
        await ctx.bot.send_photo(
            query.message.chat_id, t['file_id'],
            caption=text,
            reply_markup=InlineKeyboardMarkup(kb)
        )
    elif t.get("file_id") and t.get("file_type") == "document":
        try:
            await query.message.delete()
        except Exception:
            pass
        await ctx.bot.send_document(
            query.message.chat_id, t['file_id'],
            caption=text,
            reply_markup=InlineKeyboardMarkup(kb)
        )
    else:
        await safe_edit(query.message, text, reply_markup=InlineKeyboardMarkup(kb))


async def approve_test(query: CallbackQuery, ctx, tid):
    t = dm.get_test(tid)
    if not t or t['status'] != 'pending':
        await query.answer("قابل تأیید نیست.")
        return
    dm.update_test(tid, {"status": "approved"})
    await query.answer("✅ تأیید شد")
    try:
        await ctx.bot.send_message(
            int(t['user_id']),
            f"✅ **تست کانفیگ شما تأیید شد!**\n\n"
            f"🆔 کد: `{tid}`\n"
            f"📱 پلتفرم: {t.get('platform', '?')}\n\n"
            f"🎉 کانفیگ شما در حال آماده‌سازی هست."
        )
    except Exception:
        pass
    await show_tests_by_status(query, ctx, 'pending')


async def reject_test(query: CallbackQuery, ctx, tid):
    t = dm.get_test(tid)
    if not t or t['status'] != 'pending':
        await query.answer("قابل رد نیست.")
        return
    dm.update_test(tid, {"status": "rejected"})
    await query.answer("❌ رد شد")
    try:
        await ctx.bot.send_message(
            int(t['user_id']),
            f"❌ **تست کانفیگ شما رد شد**\n\n"
            f"🆔 کد: `{tid}`\n\n"
            f"برای پیگیری با پشتیبانی در تماس باش."
        )
    except Exception:
        pass
    await show_tests_by_status(query, ctx, 'pending')


async def dm_test_user(query: CallbackQuery, ctx, tid):
    t = dm.get_test(tid)
    if not t:
        await query.answer("یافت نشد")
        return
    clear_states(ctx)
    ctx.user_data['awaiting_test_review'] = True
    ctx.user_data['test_user_target'] = t['user_id']
    ctx.user_data['test_review_id'] = tid
    await query.message.reply_text(
        f"✉️ **پیام به کاربر**\n🆔 `{t['user_id']}`\n\nمتن پیام رو بنویس:"
    )


async def handle_test_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_test_review'):
        return False
    target = context.user_data.get('test_user_target')
    text = update.message.text
    try:
        await context.bot.send_message(int(target), f"📩 **از تیم پشتیبانی:**\n\n{text}")
        await update.message.reply_text("✅ پیام ارسال شد.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {e}")
    clear_states(context)
    return True


async def show_daily_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    stats = dm.get_daily_stats(7)
    text = "📈 **آمار فروش ۷ روز اخیر**\n━━━━━━━━━━━━━━━\n\n"
    total_orders = 0
    total_revenue = 0
    for s in stats:
        text += f"📅 {s['date']}\n"
        text += f"   🛒 {s['orders']} | 💰 {fmt(s['revenue'])} ت\n\n"
        total_orders += s['orders']
        total_revenue += s['revenue']
    text += f"━━━━━━━━━━━━━━━\n📊 مجموع: {total_orders} سفارش\n💰 درآمد: {fmt(total_revenue)} ت"
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


async def help_text_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_help_text'] = True
    current = dm.data.get("user_help_text", "")
    await update.message.reply_text(f"📝 **تغییر راهنمای کاربر**\n\nمتن فعلی:\n{current}\n\nمتن جدید رو بنویس:")


async def handle_help_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_help_text'):
        return
    dm.data["user_help_text"] = update.message.text
    dm.save_data()
    clear_states(context)
    await update.message.reply_text("✅ راهنمای کاربر تغییر کرد.")


async def show_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_admin(update.effective_user.id):
        return
    users = dm.data["users"]
    if not users:
        await update.message.reply_text("📭 هیچ کاربری نیست.")
        return
    text = f"👥 **آمار کاربران ({len(users)} نفر)**\n━━━━━━━━━━━━━━━\n\n"
    for i, (uid, u) in enumerate(list(users.items())[-30:], 1):
        name = u.get("first_name", "-") or "-"
        username = u.get("username", "")
        uname_str = f"@{username}" if username else "بدون یوزرنیم"
        balance = u.get("balance", 0)
        orders_count = len(u.get("orders", []))
        tests_count = u.get("tests_count", 0)
        text += (
            f"{i}. 🆔 `{uid}`\n"
            f"   📛 {name} | {uname_str}\n"
            f"   💰 {fmt(balance)} ت | 📦 {orders_count} | 🧪 {tests_count}\n\n"
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
    text = f"🔍 **نتیجه جستجو ({len(found)} کاربر)**\n━━━━━━━━━━━━━━━\n\n"
    for i, (uid, u) in enumerate(found[:10], 1):
        name = u.get("first_name", "-") or "-"
        username = u.get("username", "")
        uname_str = f"@{username}" if username else "ندارد"
        balance = u.get("balance", 0)
        orders_count = len(u.get("orders", []))
        tests_count = u.get("tests_count", 0)
        banned = "🚫" if dm.is_banned(uid) else "✅"
        owner_badge = " 👑" if dm.is_owner(uid) else ""
        admin_badge = " 🛡" if (dm.is_admin(uid) and not dm.is_owner(uid)) else ""
        text += (
            f"{i}. 🆔 `{uid}`{owner_badge}{admin_badge}\n"
            f"   📛 {name} | {uname_str}\n"
            f"   💰 {fmt(balance)} ت | 📦 {orders_count} | 🧪 {tests_count}\n"
            f"   {banned}\n\n"
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
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن کارت", callback_data="card_add")],
        [InlineKeyboardButton("🗑️ حذف کارت", callback_data="card_del_menu")],
        [InlineKeyboardButton("🔄 تغییر کارت فعال", callback_data="card_activate_menu")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    await update.message.reply_text(text, reply_markup=kb)


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
        f"{'✅ این کارت فعال شد' if is_first else ''}"
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
#                     مدیریت برنامه‌ها
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
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن برنامه", callback_data="app_add")],
        [InlineKeyboardButton("🗑️ حذف برنامه", callback_data="app_del_menu")],
        [InlineKeyboardButton("📝 تغییر متن توضیحی", callback_data="app_text")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    await update.message.reply_text(text, reply_markup=kb)


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
    await update.message.reply_text("📤 حالا فایل APK برنامه رو بفرست:\n(به صورت Document)")


async def handle_add_app_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_app_file'):
        return
    name = context.user_data.get('new_app_name', 'برنامه')
    file_id = None
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
    await update.message.reply_text(f"✅ برنامه `{name}` اضافه شد.")


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
            f"🔑 کانفیگ: {len(configs)}"
        )


# =========================================================
#                     مدیریت محصولات
# =========================================================

async def manage_products(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
        is_callback = True
    else:
        msg = upd.message
        is_callback = False

    products = dm.data["products"]
    if not products:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]])
        if is_callback:
            await safe_edit(msg, "📭 محصولی نیست.", reply_markup=kb)
        else:
            await msg.reply_text("📭 محصولی نیست.", reply_markup=kb)
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

    if is_callback:
        await safe_edit(msg, "📦 **مدیریت محصولات**", reply_markup=markup)
    else:
        await msg.reply_text("📦 **مدیریت محصولات**", reply_markup=markup)


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
    await update.message.reply_text("✅ محصول ویرایش شد.")


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
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن کد", callback_data="add_coupon")],
        [InlineKeyboardButton("🗑️ حذف کد", callback_data="del_coupon")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


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
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 تغییر پاداش", callback_data="set_ref_bonus")],
        [InlineKeyboardButton("🔘 روشن/خاموش", callback_data="toggle_ref")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


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
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 در انتظار", callback_data="ord_waiting")],
        [InlineKeyboardButton("✅ تکمیل شده", callback_data="ord_completed")],
        [InlineKeyboardButton("❌ رد شده", callback_data="ord_rejected")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    await update.message.reply_text("📋 **مدیریت سفارش‌ها**", reply_markup=kb)


async def show_orders_by_status(upd, ctx, statuses):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
        is_callback = True
    else:
        msg = upd.message
        is_callback = False

    orders = [o for o in dm.data["orders"] if o.get("status") in statuses]
    orders = sorted(orders, key=lambda x: x.get("date", ""), reverse=True)

    if not orders:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]])
        if is_callback:
            await safe_edit(msg, "📭 سفارشی نیست.", reply_markup=kb)
        else:
            await msg.reply_text("📭 سفارشی نیست.", reply_markup=kb)
        return

    kb = []
    for o in orders[:20]:
        kb.append([InlineKeyboardButton(
            f"#{o['order_id'][-10:]} | {fmt(o['total'])} ت",
            callback_data=f"orddet_{o['order_id']}"
        )])
    kb.append([InlineKeyboardButton("🗑️ خالی کردن", callback_data=f"clrord_{'_'.join(statuses)}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
    title = "📥 در انتظار" if "waiting_admin" in statuses else ("✅ تکمیل" if "completed" in statuses else "❌ رد")
    markup = InlineKeyboardMarkup(kb)
    if is_callback:
        await safe_edit(msg, title, reply_markup=markup)
    else:
        await msg.reply_text(title, reply_markup=markup)


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
        is_callback = True
    else:
        msg = upd.message
        is_callback = False

    pending = [r for r in dm.data["topup_requests"] if r.get("status") == "pending"]
    if not pending:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]])
        if is_callback:
            await safe_edit(msg, "📭 درخواستی نیست.", reply_markup=kb)
        else:
            await msg.reply_text("📭 درخواستی نیست.", reply_markup=kb)
        return
    kb = []
    for r in pending[:20]:
        kb.append([InlineKeyboardButton(f"#{r['request_id'][-10:]} | {fmt(r['amount'])} ت", callback_data=f"topdet_{r['request_id']}")])
    kb.append([InlineKeyboardButton("🗑️ خالی کردن", callback_data="clrtop")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
    markup = InlineKeyboardMarkup(kb)

    if is_callback:
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
#                     کاربر / بن / کیف پول / پیام مستقیم
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
    owner_badge = " 👑" if dm.is_owner(uid) else (" 🛡" if dm.is_admin(uid) else "")
    clear_states(context)
    await update.message.reply_text(
        f"👤 {ud}{owner_badge}\n"
        f"📛 {u.get('first_name', '-')}\n"
        f"💰 {fmt(u.get('balance', 0))} ت\n"
        f"📦 {len(u.get('orders', []))} سفارش\n"
        f"🧪 {u.get('tests_count', 0)} تست\n"
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


async def dm_user_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not dm.is_owner(update.effective_user.id):
        return
    clear_states(context)
    context.user_data['awaiting_dm_user'] = True
    await update.message.reply_text("✉️ **ارسال پیام مستقیم**\nشناسه عددی کاربر:")


async def handle_dm_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()
    if not uid.isdigit():
        await update.message.reply_text("❌ عدد.")
        return
    u = dm.get_user(uid)
    if not u:
        await update.message.reply_text("❌ کاربر پیدا نشد.")
        return
    context.user_data['dm_target_user'] = uid
    context.user_data['awaiting_dm_user'] = False
    context.user_data['awaiting_dm_text'] = True
    name = u.get("first_name", "?") or "?"
    await update.message.reply_text(f"👤 {name}\n\nمتن پیام رو بنویس:")


async def handle_dm_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_dm_text'):
        return
    target = context.user_data.get('dm_target_user')
    text = update.message.text
    try:
        await context.bot.send_message(int(target), f"📩 **پیام از مدیریت:**\n\n{text}")
        await update.message.reply_text("✅ پیام ارسال شد.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {e}")
    clear_states(context)


# =========================================================
#                     تنظیمات / مالکین / ادمین‌ها
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


async def owners_management_menu(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
        is_callback = True
    else:
        msg = upd.message
        user = upd.effective_user
        is_callback = False

    if not dm.is_owner(user.id):
        await msg.reply_text("❌ فقط مالکین دسترسی دارن.")
        return

    owners = dm.get_owners_list()
    text = f"👑 **مدیریت مالکین**\n\n📊 تعداد: {len(owners)} نفر\n\n"
    for i, oid in enumerate(owners, 1):
        u = dm.data["users"].get(str(oid), {})
        name = u.get("first_name", "ناشناس") or "ناشناس"
        username = u.get("username", "")
        uname_str = f"@{username}" if username else "—"
        source_badge = " 🔒" if dm.is_source_owner(oid) else ""
        text += f"{i}. `{oid}`{source_badge}\n   📛 {name} | {uname_str}\n\n"

    text += "🔒 = مالک سورس (قابل حذف نیست)"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن مالک جدید", callback_data="owner_add")],
        [InlineKeyboardButton("🗑️ حذف مالک", callback_data="owner_del_menu")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    if is_callback:
        await safe_edit(msg, text, reply_markup=kb)
    else:
        await msg.reply_text(text, reply_markup=kb)


async def owner_add_prompt(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    clear_states(ctx)
    ctx.user_data['awaiting_add_owner'] = True
    await msg.reply_text(
        "👑 **افزودن مالک جدید**\n\n"
        "🔍 آیدی عددی کاربر رو بفرست:\n"
        "برای انصراف /cancel"
    )


async def owner_remove_menu(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message

    owners = dm.get_owners_list()
    removable = [o for o in owners if not dm.is_source_owner(o)]

    if not removable:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="owners_menu")]])
        await safe_edit(msg, "❌ هیچ مالکی قابل حذف نیست.\n(همه مالکین سورس هستن)", reply_markup=kb)
        return

    kb = []
    for oid in removable:
        u = dm.data["users"].get(str(oid), {})
        name = u.get("first_name", "ناشناس") or "ناشناس"
        kb.append([InlineKeyboardButton(
            f"❌ حذف {name} | {oid}",
            callback_data=f"owner_del_{oid}"
        )])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="owners_menu")])
    await safe_edit(msg, "🗑️ **کدوم مالک رو حذف کنم؟**", reply_markup=InlineKeyboardMarkup(kb))


async def owner_delete_confirm(upd, ctx, target_id):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message

    if dm.is_source_owner(target_id):
        await answer_cb(upd, "❌ این مالک سورس هست!", show_alert=True)
        return

    u = dm.data["users"].get(str(target_id), {})
    name = u.get("first_name", "ناشناس") or "ناشناس"

    kb = [
        [InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"owner_delok_{target_id}")],
        [InlineKeyboardButton("❌ انصراف", callback_data="owner_del_menu")]
    ]
    await safe_edit(
        msg,
        f"⚠️ **تأیید حذف مالک**\n\n👤 {name}\n🆔 `{target_id}`\n\nمطمئنی؟",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def owner_delete_execute(upd, ctx, target_id):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        actor = upd.from_user
        await answer_cb(upd)
    else:
        msg = upd.message
        actor = upd.effective_user

    if dm.is_source_owner(target_id):
        await msg.reply_text("❌ این مالک سورس هست!")
        return

    if str(target_id) == str(actor.id):
        await msg.reply_text("❌ نمی‌تونی خودت رو حذف کنی!")
        return

    if dm.remove_owner(target_id):
        dm.add_admin_log(actor.id, target_id, "حذف مالک")
        try:
            await ctx.bot.send_message(int(target_id), "❌ شما از لیست مالکین ربات حذف شدید.")
        except Exception:
            pass
        await msg.reply_text(f"✅ مالک `{target_id}` حذف شد.")
    else:
        await msg.reply_text("❌ حذف نشد.")


async def handle_owner_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()

    if uid.startswith("@"):
        await update.message.reply_text("❌ فقط آیدی عددی.")
        return
    if not uid.isdigit():
        await update.message.reply_text("❌ آیدی باید عدد باشه.")
        return

    if context.user_data.get('awaiting_add_owner'):
        actor = update.effective_user.id
        if dm.add_owner(uid):
            dm.add_admin_log(actor, uid, "افزودن مالک")
            clear_states(context)
            await update.message.reply_text(f"✅ `{uid}` به لیست مالکین اضافه شد.")
            try:
                await context.bot.send_message(
                    int(uid),
                    "👑 **شما به عنوان مالک ربات تعیین شدید!**\n\n"
                    "برای دسترسی به پنل، دستور /start رو بزن."
                )
            except Exception:
                pass
        else:
            await update.message.reply_text("❌ این کاربر از قبل مالکه.")


async def admins_management_menu(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        user = upd.from_user
        await answer_cb(upd)
        is_callback = True
    else:
        msg = upd.message
        user = upd.effective_user
        is_callback = False

    if not dm.is_owner(user.id):
        await msg.reply_text("❌ فقط مالکین دسترسی دارن.")
        return

    admins = dm.get_admins_list()
    text = f"🛡 **مدیریت ادمین‌ها**\n\n📊 تعداد: {len(admins)} نفر\n\n"
    if not admins:
        text += "❌ هیچ ادمینی وجود نداره."
    else:
        for i, aid in enumerate(admins, 1):
            u = dm.data["users"].get(str(aid), {})
            name = u.get("first_name", "ناشناس") or "ناشناس"
            username = u.get("username", "")
            uname_str = f"@{username}" if username else "—"
            source_badge = " 🔒" if dm.is_source_admin(aid) else ""
            text += f"{i}. `{aid}`{source_badge}\n   📛 {name} | {uname_str}\n\n"

    text += "🔒 = ادمین سورس (قابل حذف نیست)"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن ادمین جدید", callback_data="admin_add")],
        [InlineKeyboardButton("🗑️ حذف ادمین", callback_data="admin_del_menu")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ])
    if is_callback:
        await safe_edit(msg, text, reply_markup=kb)
    else:
        await msg.reply_text(text, reply_markup=kb)


async def admin_add_prompt(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message
    clear_states(ctx)
    ctx.user_data['awaiting_add_admin'] = True
    await msg.reply_text(
        "🛡 **افزودن ادمین جدید**\n\n"
        "🔍 آیدی عددی کاربر رو بفرست:\n"
        "برای انصراف /cancel"
    )


async def admin_remove_menu(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message

    admins = dm.get_admins_list()
    removable = [a for a in admins if not dm.is_source_admin(a)]

    if not removable:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admins_menu")]])
        await safe_edit(msg, "❌ هیچ ادمینی قابل حذف نیست.", reply_markup=kb)
        return

    kb = []
    for aid in removable:
        u = dm.data["users"].get(str(aid), {})
        name = u.get("first_name", "ناشناس") or "ناشناس"
        kb.append([InlineKeyboardButton(
            f"❌ حذف {name} | {aid}",
            callback_data=f"admin_del_{aid}"
        )])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admins_menu")])
    await safe_edit(msg, "🗑️ **کدوم ادمین رو حذف کنم؟**", reply_markup=InlineKeyboardMarkup(kb))


async def admin_delete_confirm(upd, ctx, target_id):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
    else:
        msg = upd.message

    if dm.is_source_admin(target_id):
        await answer_cb(upd, "❌ این ادمین سورس هست!", show_alert=True)
        return

    u = dm.data["users"].get(str(target_id), {})
    name = u.get("first_name", "ناشناس") or "ناشناس"

    kb = [
        [InlineKeyboardButton("✅ بله", callback_data=f"admin_delok_{target_id}")],
        [InlineKeyboardButton("❌ انصراف", callback_data="admin_del_menu")]
    ]
    await safe_edit(
        msg,
        f"⚠️ **تأیید حذف ادمین**\n\n👤 {name}\n🆔 `{target_id}`",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def admin_delete_execute(upd, ctx, target_id):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        actor = upd.from_user
        await answer_cb(upd)
    else:
        msg = upd.message
        actor = upd.effective_user

    if dm.is_source_admin(target_id):
        await msg.reply_text("❌ این ادمین سورس هست!")
        return

    if dm.remove_admin(target_id):
        dm.add_admin_log(actor.id, target_id, "حذف ادمین")
        try:
            await ctx.bot.send_message(int(target_id), "❌ شما از لیست ادمین‌های ربات حذف شدید.")
        except Exception:
            pass
        await msg.reply_text(f"✅ ادمین `{target_id}` حذف شد.")
    else:
        await msg.reply_text("❌ ادمین پیدا نشد.")


async def handle_admin_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()

    if uid.startswith("@"):
        await update.message.reply_text("❌ فقط آیدی عددی.")
        return
    if not uid.isdigit():
        await update.message.reply_text("❌ آیدی باید عدد باشه.")
        return

    if context.user_data.get('awaiting_add_admin'):
        actor = update.effective_user.id
        if dm.add_admin(uid):
            dm.add_admin_log(actor, uid, "افزودن ادمین")
            clear_states(context)
            await update.message.reply_text(f"✅ `{uid}` به لیست ادمین‌ها اضافه شد.")
            try:
                await context.bot.send_message(
                    int(uid),
                    "🛡 **شما به عنوان ادمین ربات تعیین شدید!**\n\n"
                    "برای دسترسی به پنل، دستور /start رو بزن."
                )
            except Exception:
                pass
        else:
            await update.message.reply_text("❌ این کاربر از قبل ادمین یا مالکه.")


async def show_admin_logs(upd, ctx):
    if isinstance(upd, CallbackQuery):
        msg = upd.message
        await answer_cb(upd)
        is_callback = True
    else:
        msg = upd.message
        is_callback = False

    logs = dm.get_admin_logs(30)
    if not logs:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]])
        if is_callback:
            await safe_edit(msg, "📭 هیچ لاگی نیست.", reply_markup=kb)
        else:
            await msg.reply_text("📭 هیچ لاگی نیست.", reply_markup=kb)
        return

    text = "📜 **آخرین تغییرات ادمین/مالک**\n\n"
    for log in logs:
        actor_u = dm.data["users"].get(str(log["actor"]), {})
        target_u = dm.data["users"].get(str(log["target"]), {})
        actor_name = actor_u.get("first_name", "?") or "?"
        target_name = target_u.get("first_name", "?") or "?"
        text += (
            f"🔹 **{log['action']}**\n"
            f"👤 {actor_name} → 🎯 {target_name}\n"
            f"📅 {log['date']}\n\n"
        )

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]])
    if is_callback:
        await safe_edit(msg, text, reply_markup=kb)
    else:
        await msg.reply_text(text, reply_markup=kb)


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

        # چک عضویت (از دکمه خودش)
        if data == "check_membership":
            user_id = str(query.from_user.id)
            is_member, missing = await check_membership(context.bot, user_id)
            if is_member:
                await query.answer("✅ عضویتت تأیید شد!", show_alert=True)
                try:
                    await query.message.delete()
                except Exception:
                    pass
                await main_menu(query, context)
            else:
                missing_text = []
                if "channel" in missing:
                    missing_text.append("📢 کانال")
                if "group" in missing:
                    missing_text.append("👥 گروه")
                await query.answer(
                    f"❌ هنوز عضو نشدی: {' و '.join(missing_text)}",
                    show_alert=True
                )
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

        # تست
        elif data == "test_menu":
            await test_config_menu(query, context)
        elif data == "test_android":
            await test_platform_selected(query, context, "اندروید")
        elif data == "test_ios":
            await test_platform_selected(query, context, "iOS")
        elif data == "test_windows":
            await test_platform_selected(query, context, "ویندوز")
        elif data == "tests_menu_back":
            await show_tests_menu(query, context)
        elif data == "tests_pending":
            await show_tests_by_status(query, context, 'pending')
        elif data == "tests_approved":
            await show_tests_by_status(query, context, 'approved')
        elif data == "tests_rejected":
            await show_tests_by_status(query, context, 'rejected')
        elif data.startswith("testdet_"):
            await view_test_detail(query, context, data[8:])
        elif data.startswith("testap_"):
            await approve_test(query, context, data[7:])
        elif data.startswith("testrj_"):
            await reject_test(query, context, data[7:])
        elif data.startswith("testdm_"):
            await dm_test_user(query, context, data[7:])
        elif data.startswith("testok_"):
            await approve_test(query, context, data[7:])
        elif data.startswith("testno_"):
            await reject_test(query, context, data[7:])

        # 🔒 عضویت اجباری
        elif data == "fj_toggle":
            await fj_toggle(query, context)
        elif data == "fj_channel":
            await fj_channel_prompt(query, context)
        elif data == "fj_group":
            await fj_group_prompt(query, context)
        elif data == "fj_message":
            await fj_message_prompt(query, context)

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

        # مالکین
        elif data == "owners_menu":
            await owners_management_menu(query, context)
        elif data == "owner_add":
            await owner_add_prompt(query, context)
        elif data == "owner_del_menu":
            await owner_remove_menu(query, context)
        elif data.startswith("owner_delok_"):
            await owner_delete_execute(query, context, data[12:])
        elif data.startswith("owner_del_"):
            await owner_delete_confirm(query, context, data[10:])

        # ادمین‌ها
        elif data == "admins_menu":
            await admins_management_menu(query, context)
        elif data == "admin_add":
            await admin_add_prompt(query, context)
        elif data == "admin_del_menu":
            await admin_remove_menu(query, context)
        elif data.startswith("admin_delok_"):
            await admin_delete_execute(query, context, data[12:])
        elif data.startswith("admin_del_"):
            await admin_delete_confirm(query, context, data[10:])

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

    if text == "⚙️ پنل مدیریت":
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
    elif text == "🧪 مدیریت تست‌ها":
        await show_tests_menu(update, context)
    elif text == "📊 آمار تست‌ها" and dm.is_owner(uid):
        await show_test_stats(update, context)
    elif text == "🔒 عضویت اجباری" and dm.is_owner(uid):
        await force_join_menu(update, context)
    elif text == "🛠 پشتیبانی" and dm.is_owner(uid):
        await set_support_prompt(update, context)
    elif text == "📝 راهنمای کاربر" and dm.is_owner(uid):
        await help_text_prompt(update, context)
    elif text == "👑 مدیریت مالکین" and dm.is_owner(uid):
        await owners_management_menu(update, context)
    elif text == "🛡 مدیریت ادمین‌ها" and dm.is_owner(uid):
        await admins_management_menu(update, context)
    elif text == "📜 لاگ تغییرات" and dm.is_owner(uid):
        await show_admin_logs(update, context)
    elif text == "✉️ پیام به کاربر" and dm.is_owner(uid):
        await dm_user_prompt(update, context)
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

    text = update.message.text or ""

    MAIN_MENU_BUTTONS = [
        "🛍️ مشاهده محصولات", "🛒 سبد خرید من", "👤 حساب کاربری",
        "💰 کیف پول", "📱 برنامه‌های اتصال", "🧪 تست کانفیگ",
        "🎁 دعوت دوستان", "📜 سفارش‌های من", "🔍 پیگیری سفارش",
        "📞 پشتیبانی", "ℹ️ راهنما", "⚙️ پنل مدیریت", "🔙 بازگشت"
    ]
    if text in MAIN_MENU_BUTTONS:
        clear_states(context)

    # 🔒 چک عضویت اجباری برای کاربران عادی
    if not dm.is_admin(uid) and text not in ["/start"] and not text.startswith("/"):
        is_member, missing = await check_membership(context.bot, uid)
        if not is_member:
            await show_force_join_message(update, context)
            return

    # State ها
    if context.user_data.get('awaiting_test_config'):
        await handle_test_config(update, context); return
    if context.user_data.get('awaiting_test_review'):
        await handle_test_review(update, context); return
    if context.user_data.get('awaiting_channel_id'):
        await handle_channel_id(update, context); return
    if context.user_data.get('awaiting_channel_link'):
        await handle_channel_link(update, context); return
    if context.user_data.get('awaiting_group_id'):
        await handle_group_id(update, context); return
    if context.user_data.get('awaiting_group_link'):
        await handle_group_link(update, context); return
    if context.user_data.get('awaiting_forced_message'):
        await handle_forced_message(update, context); return
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
    if context.user_data.get('awaiting_add_admin'):
        await handle_admin_edit(update, context); return
    if context.user_data.get('awaiting_add_owner'):
        await handle_owner_edit(update, context); return
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
    if context.user_data.get('awaiting_help_text'):
        await handle_help_text(update, context); return
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
    if context.user_data.get('awaiting_dm_user'):
        await handle_dm_user(update, context); return
    if context.user_data.get('awaiting_dm_text'):
        await handle_dm_text(update, context); return

    if await admin_text_handler(update, context):
        return

    if text == "🛍️ مشاهده محصولات":
        await show_products(update, context)
    elif text == "🛒 سبد خرید من":
        await show_cart(update, context)
    elif text == "👤 حساب کاربری":
        await show_account(update, context)
    elif text == "💰 کیف پول":
        await wallet_menu(update, context)
    elif text == "📱 برنامه‌های اتصال":
        await show_apps(update, context)
    elif text == "🧪 تست کانفیگ":
        await test_config_menu(update, context)
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