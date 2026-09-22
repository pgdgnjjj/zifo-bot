import json
import os
import logging
import random
import string
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, Union

from flask import Flask, request, Response
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# =========================================================
#                     تنظیمات (از Environment)
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "توکن_پیش‌فرض")
OWNER_IDS = [os.getenv("OWNER_ID", "آیدی_پیش‌فرض")]
DATA_FILE = "/tmp/data.json"

PORT = int(os.getenv("PORT", 8000))

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_order_id() -> str:
    date_part = datetime.now().strftime("%Y%m%d")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ORD-{date_part}-{random_part}"


def generate_request_id() -> str:
    return f"TOP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}"


def format_price(price: int) -> str:
    return f"{price:,}"


def get_user_display(user_id: str, username: str = None) -> str:
    if username:
        return f"`{user_id}` | @{username}"
    return f"`{user_id}` | ندارد"


def clear_user_states(context):
    state_keys = [
        'awaiting_discount', 'awaiting_topup_amount', 'awaiting_topup_receipt',
        'awaiting_receipt', 'add_discount_step', 'edit_step', 'sending_account_for_order',
        'awaiting_wallet_user', 'awaiting_wallet_user_id', 'awaiting_wallet_amount',
        'awaiting_add_admin', 'awaiting_remove_admin', 'awaiting_broadcast',
        'awaiting_card', 'awaiting_support', 'awaiting_product_name',
        'awaiting_product_price', 'awaiting_product_stock',
        'awaiting_stock_increase', 'awaiting_stock_decrease', 'awaiting_user_check',
        'awaiting_ban_toggle', 'discount_product_id', 'discount_product_price',
        'new_product_name', 'new_product_price', 'wallet_target', 'wallet_target_uid',
        'editing_product_id', 'awaiting_edit_product', 'discount_usage_type',
        'discount_applies_to_all', 'awaiting_gift_amount', 'awaiting_deduct_amount',
        'awaiting_increase_all', 'awaiting_decrease_all',
        'sending_config_for', 'receipt_order_id', 'topup_amount'
    ]
    for key in state_keys:
        context.user_data.pop(key, None)


class DataManager:
    def __init__(self):
        self.data = self.load_data()

    def load_data(self) -> Dict:
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if "shop_status" not in data:
                    data["shop_status"] = {"is_open": True, "closed_message": "🚫 فروشگاه موقتاً بسته است."}
                if "broadcast_history" not in data:
                    data["broadcast_history"] = []
                self.save_data(data)
                return data
            except Exception as e:
                logger.error(f"Error loading data: {e}")
                return self.create_empty_data()
        return self.create_empty_data()

    def create_empty_data(self) -> Dict:
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
            "user_help_text": "🎮 **راهنمای خرید**\n\n1. محصول را انتخاب کنید\n2. به سبد خرید اضافه کنید\n3. پرداخت را انجام دهید\n4. پس از تأیید بلافاصله (کیف پول) محصول ارسال می‌شود",
            "admin_help_text": "⚙️ راهنمای پنل ادمین ...",
            "banned_users": [],
            "shop_status": {
                "is_open": True,
                "closed_message": "🚫 فروشگاه موقتاً بسته است. لطفاً بعداً مراجعه فرمایید."
            }
        }
        self.save_data(data)
        return data

    def save_data(self, data: Optional[Dict] = None):
        if data is None:
            data = self.data
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.data = data

    def get_shop_status(self) -> Dict:
        return self.data.get("shop_status", {"is_open": True, "closed_message": "🚫 فروشگاه بسته است"})

    def set_shop_status(self, is_open: bool, closed_message: str = None):
        if "shop_status" not in self.data:
            self.data["shop_status"] = {"is_open": True, "closed_message": "🚫 فروشگاه بسته است"}
        self.data["shop_status"]["is_open"] = is_open
        if closed_message:
            self.data["shop_status"]["closed_message"] = closed_message
        self.save_data()

    def get_user(self, user_id: Union[int, str]) -> Dict:
        uid = str(user_id)
        if uid not in self.data["users"]:
            self.data["users"][uid] = {
                "cart": [],
                "orders": [],
                "balance": 0,
                "join_date": datetime.now().strftime('%Y-%m-%d'),
                "username": "",
                "first_name": "",
                "is_banned": False
            }
            self.save_data()
        return self.data["users"][uid]

    def is_user_banned(self, user_id: Union[int, str]) -> bool:
        return str(user_id) in self.data.get("banned_users", [])

    def ban_user(self, user_id: Union[int, str]) -> bool:
        uid = str(user_id)
        if uid not in self.data.setdefault("banned_users", []):
            self.data["banned_users"].append(uid)
            self.save_data()
            return True
        return False

    def unban_user(self, user_id: Union[int, str]) -> bool:
        uid = str(user_id)
        if uid in self.data.get("banned_users", []):
            self.data["banned_users"].remove(uid)
            self.save_data()
            return True
        return False

    def is_owner(self, user_id: Union[int, str]) -> bool:
        return str(user_id) in self.data["owners"]

    def is_admin(self, user_id: Union[int, str]) -> bool:
        uid = str(user_id)
        return uid in self.data["owners"] or uid in self.data["admins"]

    def add_admin(self, user_id: Union[int, str]) -> bool:
        uid = str(user_id)
        if uid not in self.data["admins"] and uid not in self.data["owners"]:
            self.data["admins"].append(uid)
            self.save_data()
            return True
        return False

    def remove_admin(self, user_id: Union[int, str]) -> bool:
        uid = str(user_id)
        if uid in self.data["admins"]:
            self.data["admins"].remove(uid)
            self.save_data()
            return True
        return False

    def get_product(self, product_id: int) -> Optional[Dict]:
        return next((p for p in self.data["products"] if p["id"] == product_id), None)

    def add_product(self, product: Dict) -> int:
        if self.data["products"]:
            new_id = max(p["id"] for p in self.data["products"]) + 1
        else:
            new_id = 1
        product["id"] = new_id
        product["created_at"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        product.setdefault("stock", 0)
        self.data["products"].append(product)
        self.save_data()
        return new_id

    def update_product(self, product_id: int, updates: Dict) -> bool:
        for p in self.data["products"]:
            if p["id"] == product_id:
                p.update(updates)
                self.save_data()
                return True
        return False

    def delete_product(self, product_id: int) -> bool:
        original_len = len(self.data["products"])
        self.data["products"] = [p for p in self.data["products"] if p["id"] != product_id]
        if len(self.data["products"]) != original_len:
            self.save_data()
            return True
        return False

    def adjust_stock(self, product_id: int, delta: int) -> bool:
        product = self.get_product(product_id)
        if product:
            new_stock = max(0, product.get("stock", 0) + delta)
            product["stock"] = new_stock
            self.save_data()
            return True
        return False

    def add_order(self, order: Dict) -> str:
        order_id = generate_order_id()
        order["order_id"] = order_id
        order["date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.data["orders"].append(order)
        user = self.get_user(order["user_id"])
        user["orders"].append(order_id)
        self.save_data()
        return order_id

    def get_order(self, order_id: str) -> Optional[Dict]:
        return next((o for o in self.data["orders"] if o["order_id"] == order_id), None)

    def update_order(self, order_id: str, updates: Dict) -> bool:
        order = self.get_order(order_id)
        if order:
            order.update(updates)
            self.save_data()
            return True
        return False

    def add_topup_request(self, request: Dict) -> str:
        req_id = generate_request_id()
        request["request_id"] = req_id
        request["date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        request["status"] = "pending"
        self.data["topup_requests"].append(request)
        self.save_data()
        return req_id

    def get_topup_request(self, req_id: str) -> Optional[Dict]:
        return next((r for r in self.data["topup_requests"] if r["request_id"] == req_id), None)

    def update_topup_request(self, req_id: str, updates: Dict) -> bool:
        req = self.get_topup_request(req_id)
        if req:
            req.update(updates)
            self.save_data()
            return True
        return False

    def add_to_cart(self, user_id: Union[int, str], product_id: int) -> bool:
        user = self.get_user(user_id)
        product = self.get_product(product_id)
        if not product or product.get("stock", 0) <= 0:
            return False
        if any(item["id"] == product_id for item in user["cart"]):
            return False
        user["cart"].append({
            "id": product["id"],
            "name": product["name"],
            "price": product["price"]
        })
        self.save_data()
        return True

    def remove_from_cart(self, user_id: Union[int, str], index: int) -> bool:
        user = self.get_user(user_id)
        if 0 <= index < len(user["cart"]):
            user["cart"].pop(index)
            self.save_data()
            return True
        return False

    def clear_cart(self, user_id: Union[int, str]):
        user = self.get_user(user_id)
        user["cart"] = []
        self.save_data()

    def get_cart_total(self, user_id: Union[int, str]) -> int:
        user = self.get_user(user_id)
        return sum(item["price"] for item in user["cart"])

    def get_cart_items(self, user_id: Union[int, str]) -> list:
        return self.get_user(user_id)["cart"]

    def increase_all_balance(self, amount: int) -> int:
        count = 0
        for uid in self.data["users"].keys():
            user = self.get_user(uid)
            user["balance"] = user.get("balance", 0) + amount
            count += 1
        self.save_data()
        return count

    def decrease_all_balance(self, amount: int) -> int:
        count = 0
        for uid in self.data["users"].keys():
            user = self.get_user(uid)
            current = user.get("balance", 0)
            user["balance"] = max(0, current - amount)
            count += 1
        self.save_data()
        return count

    def add_broadcast_message(self, sent_messages: list, text: str):
        if "broadcast_history" not in self.data:
            self.data["broadcast_history"] = []
        self.data["broadcast_history"].append({
            "sent_messages": sent_messages,
            "text": text[:100],
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        if len(self.data["broadcast_history"]) > 3:
            self.data["broadcast_history"] = self.data["broadcast_history"][-3:]
        self.save_data()

    def get_broadcast_history(self) -> list:
        return self.data.get("broadcast_history", [])

    def delete_broadcast_by_index(self, index: int) -> Optional[Dict]:
        history = self.data.get("broadcast_history", [])
        if 0 <= index < len(history):
            removed = history.pop(index)
            self.data["broadcast_history"] = history
            self.save_data()
            return removed
        return None


data_manager = DataManager()


# =========================================================
#                     توابع کمکی
# =========================================================

async def safe_edit_message(message, text, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception as e:
        err = str(e).lower()
        if "message is not modified" in err:
            pass
        elif "message to edit not found" in err or "message can't be edited" in err:
            try:
                await message.reply_text(text, reply_markup=reply_markup)
            except Exception as e2:
                logger.error(f"safe_edit fallback error: {e2}")
        else:
            logger.error(f"safe_edit error: {e}")


async def answer_callback(query: CallbackQuery, text: str = ""):
    try:
        await query.answer(text)
    except Exception as e:
        logger.error(f"Callback answer error: {e}")


def get_main_keyboard(user_id: Union[int, str]) -> ReplyKeyboardMarkup:
    kb = [
        ["🛍️ محصولات"],
        ["🛒 سبد خرید", "👤 حساب کاربری"],
        ["💰 کیف پول"],
        ["ℹ️ راهنما", "📞 پشتیبانی"]
    ]
    if data_manager.is_admin(user_id):
        kb.append(["⚙️ پنل ادمین"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


async def main_menu(update_or_query, context):
    clear_user_states(context)
    
    if isinstance(update_or_query, CallbackQuery):
        message = update_or_query.message
        user = update_or_query.from_user
        await answer_callback(update_or_query)
    else:
        message = update_or_query.message
        user = update_or_query.effective_user

    uid = str(user.id)
    if data_manager.is_user_banned(uid):
        await message.reply_text("🚫 شما مسدود شده‌اید.")
        return
    await message.reply_text("🌟 **به فروشگاه Zifo خوش آمدید!**", reply_markup=get_main_keyboard(uid))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_user_states(context)
    user = data_manager.get_user(update.effective_user.id)
    user["username"] = update.effective_user.username or ""
    user["first_name"] = update.effective_user.first_name or ""
    data_manager.save_data()
    await main_menu(update, context)


async def cancel(update: Update, context):
    clear_user_states(context)
    await main_menu(update, context)
  # =========================================================
#                     محصولات
# =========================================================

async def show_products(update_or_query, context):
    clear_user_states(context)
    
    shop_status = data_manager.get_shop_status()
    if not shop_status["is_open"]:
        if isinstance(update_or_query, CallbackQuery):
            await answer_callback(update_or_query)
            await safe_edit_message(update_or_query.message, shop_status["closed_message"])
        else:
            await update_or_query.message.reply_text(shop_status["closed_message"])
        return

    if isinstance(update_or_query, CallbackQuery):
        message = update_or_query.message
        user = update_or_query.from_user
        await answer_callback(update_or_query)
    else:
        message = update_or_query.message
        user = update_or_query.effective_user

    uid = str(user.id)
    if data_manager.is_user_banned(uid):
        await message.reply_text("🚫 شما مسدود شده‌اید.")
        return

    products = data_manager.data["products"]
    if not products:
        await message.reply_text("📭 **هیچ محصولی یافت نشد.** لطفاً بعداً مراجعه کنید.")
        return

    keyboard = []
    for p in products:
        stock = p.get("stock", 0)
        circle = "🟢" if stock > 0 else "🔴"
        btn_text = f"{circle} {p['name']} | {format_price(p['price'])} ت"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"product_{p['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_menu")])

    if isinstance(update_or_query, CallbackQuery):
        await safe_edit_message(message, "🛍️ **محصولات فروشگاه**", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await message.reply_text("🛍️ **محصولات فروشگاه**", reply_markup=InlineKeyboardMarkup(keyboard))


async def product_details(update_or_query, context, product_id: int):
    if isinstance(update_or_query, CallbackQuery):
        message = update_or_query.message
        user = update_or_query.from_user
        await answer_callback(update_or_query)
    else:
        message = update_or_query.message
        user = update_or_query.effective_user

    product = data_manager.get_product(product_id)
    if not product:
        await message.reply_text("❌ محصول یافت نشد.")
        return

    stock = product.get("stock", 0)
    text = (
        f"🎯 **{product['name']}**\n"
        f"💰 قیمت: {format_price(product['price'])} تومان\n"
        f"📦 موجودی: {stock}\n"
        f"📝 {product.get('description', '---')}"
    )
    keyboard = []
    if stock > 0:
        keyboard.append([InlineKeyboardButton("🛒 افزودن به سبد", callback_data=f"cart_add_{product_id}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="products_back")])

    if isinstance(update_or_query, CallbackQuery):
        await safe_edit_message(message, text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def add_to_cart(update_or_query, context, product_id: int):
    shop_status = data_manager.get_shop_status()
    if not shop_status["is_open"]:
        if isinstance(update_or_query, CallbackQuery):
            await answer_callback(update_or_query, shop_status["closed_message"])
        else:
            await update_or_query.message.reply_text(shop_status["closed_message"])
        return

    if isinstance(update_or_query, CallbackQuery):
        message = update_or_query.message
        user = update_or_query.from_user
        await answer_callback(update_or_query)
    else:
        message = update_or_query.message
        user = update_or_query.effective_user

    uid = str(user.id)
    product = data_manager.get_product(product_id)
    if not product or product.get("stock", 0) <= 0:
        await message.reply_text("❌ این محصول موجود نیست.")
        return

    if data_manager.add_to_cart(uid, product_id):
        await message.reply_text(f"✅ {product['name']} به سبد خرید اضافه شد.")
    else:
        await message.reply_text("⚠️ این محصول قبلاً در سبد شما وجود دارد.")


# =========================================================
#                     سبد خرید
# =========================================================

async def show_cart(update_or_query, context):
    clear_user_states(context)
    
    if isinstance(update_or_query, CallbackQuery):
        message = update_or_query.message
        user = update_or_query.from_user
        await answer_callback(update_or_query)
    else:
        message = update_or_query.message
        user = update_or_query.effective_user

    uid = str(user.id)
    cart = data_manager.get_cart_items(uid)
    if not cart:
        text = "🛒 **سبد خرید خالی است.**"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ محصولات", callback_data="products_back")]])
        if isinstance(update_or_query, CallbackQuery):
            await safe_edit_message(message, text, reply_markup=kb)
        else:
            await message.reply_text(text, reply_markup=kb)
        return

    total = data_manager.get_cart_total(uid)
    text = "🛒 **سبد خرید شما:**\n\n"
    for idx, item in enumerate(cart, 1):
        text += f"{idx}. {item['name']} - {format_price(item['price'])} ت\n"
    text += f"\n💰 **مجموع:** {format_price(total)} تومان"

    keyboard = []
    for idx, item in enumerate(cart):
        keyboard.append([InlineKeyboardButton(f"❌ حذف {item['name']}", callback_data=f"cart_remove_{idx}")])
    keyboard.append([InlineKeyboardButton("✅ پرداخت با کیف پول", callback_data="checkout")])
    keyboard.append([
        InlineKeyboardButton("➕ ادامه خرید", callback_data="products_back"),
        InlineKeyboardButton("🗑️ خالی کردن سبد", callback_data="clear_cart")
    ])
    kb = InlineKeyboardMarkup(keyboard)
    if isinstance(update_or_query, CallbackQuery):
        await safe_edit_message(message, text, reply_markup=kb)
    else:
        await message.reply_text(text, reply_markup=kb)


async def remove_from_cart(update_or_query, context, idx: int):
    if isinstance(update_or_query, CallbackQuery):
        user = update_or_query.from_user
        await answer_callback(update_or_query)
    else:
        user = update_or_query.effective_user

    uid = str(user.id)
    if data_manager.remove_from_cart(uid, idx):
        await show_cart(update_or_query, context)
    else:
        await update_or_query.message.reply_text("❌ حذف آیتم امکان‌پذیر نیست.")


async def clear_cart(update_or_query, context):
    if isinstance(update_or_query, CallbackQuery):
        user = update_or_query.from_user
        await answer_callback(update_or_query)
    else:
        user = update_or_query.effective_user

    uid = str(user.id)
    data_manager.clear_cart(uid)
    await show_cart(update_or_query, context)


# =========================================================
#                     پرداخت
# =========================================================

async def checkout(update_or_query, context):
    shop_status = data_manager.get_shop_status()
    if not shop_status["is_open"]:
        if isinstance(update_or_query, CallbackQuery):
            await answer_callback(update_or_query, shop_status["closed_message"])
        else:
            await update_or_query.message.reply_text(shop_status["closed_message"])
        return

    if isinstance(update_or_query, CallbackQuery):
        message = update_or_query.message
        user = update_or_query.from_user
        await answer_callback(update_or_query)
    else:
        message = update_or_query.message
        user = update_or_query.effective_user

    uid = str(user.id)
    cart = data_manager.get_cart_items(uid)
    if not cart:
        await message.reply_text("🛒 **سبد خرید خالی است.**")
        return

    total = data_manager.get_cart_total(uid)
    user_balance = data_manager.get_user(uid).get("balance", 0)
    card_number = data_manager.data["card_number"]

    if user_balance < total:
        await message.reply_text(
            f"❌ **موجودی کیف پول کافی نیست.**\n"
            f"💰 موجودی: {format_price(user_balance)} تومان\n"
            f"💰 مبلغ قابل پرداخت: {format_price(total)} تومان\n\n"
            f"لطفاً کیف پول خود را از طریق بخش «کیف پول» شارژ کنید."
        )
        return

    text = (
        f"✅ **نهایی کردن خرید**\n━━━━━━━━━━\n"
        f"📦 تعداد آیتم‌ها: {len(cart)}\n"
        f"💰 مبلغ قابل پرداخت: {format_price(total)} تومان\n"
        f"💳 موجودی کیف پول: {format_price(user_balance)} تومان\n"
        f"💳 شماره کارت: `{card_number}`\n━━━━━━━━━━\n"
        f"آیا از پرداخت مطمئن هستید؟"
    )
    keyboard = [
        [InlineKeyboardButton("✅ بله، پرداخت کن", callback_data="pay_wallet")],
        [InlineKeyboardButton("🔙 بازگشت به سبد", callback_data="show_cart")]
    ]
    kb = InlineKeyboardMarkup(keyboard)
    if isinstance(update_or_query, CallbackQuery):
        await safe_edit_message(message, text, reply_markup=kb)
    else:
        await message.reply_text(text, reply_markup=kb)


async def pay_wallet(update_or_query, context):
    if isinstance(update_or_query, CallbackQuery):
        message = update_or_query.message
        user = update_or_query.from_user
        await answer_callback(update_or_query)
    else:
        message = update_or_query.message
        user = update_or_query.effective_user

    uid = str(user.id)
    cart = data_manager.get_cart_items(uid)
    if not cart:
        await message.reply_text("سبد خرید خالی است.")
        return

    total = data_manager.get_cart_total(uid)
    user_data = data_manager.get_user(uid)
    if user_data.get("balance", 0) < total:
        await message.reply_text("❌ **موجودی کیف پول کافی نیست.**")
        return

    user_data["balance"] -= total

    order = {
        "user_id": uid,
        "username": user_data.get("username", ""),
        "first_name": user_data.get("first_name", ""),
        "items": cart.copy(),
        "total": total,
        "status": "waiting_admin",
        "payment_method": "wallet",
        "receipt_photo": None,
        "account_info": None
    }
    order_id = data_manager.add_order(order)
    data_manager.clear_cart(uid)

    user_display = get_user_display(uid, user_data.get("username", ""))

    items_list = []
    for item in cart:
        items_list.append(f"{item['name']} - {format_price(item['price'])} تومان")
    items_str = "\n".join(items_list)

    await message.reply_text(
        f"✅ **پرداخت با کیف پول موفقیت‌آمیز بود.**\n"
        f"🆔 شماره سفارش: `{order_id}`\n"
        f"💰 مبلغ پرداختی: {format_price(total)} تومان\n\n"
        f"سفارش شما در انتظار تأیید ادمین است. پس از تأیید، کانفیگ ارسال خواهد شد."
    )

    for admin_id in data_manager.data["owners"] + data_manager.data["admins"]:
        try:
            await context.bot.send_message(
                int(admin_id),
                f"🛒 **سفارش جدید با کیف پول**\n"
                f"🆔 سفارش: `{order_id}`\n"
                f"👤 کاربر: {user_display}\n"
                f"📦 **محصولات:**\n{items_str}\n"
                f"💰 **مبلغ کل:** {format_price(total)} تومان"
            )
        except Exception:
            pass
      # =========================================================
#                     کیف پول
# =========================================================

async def wallet_menu(update_or_query, context):
    if isinstance(update_or_query, CallbackQuery):
        message = update_or_query.message
        user = update_or_query.from_user
        await answer_callback(update_or_query)
    else:
        message = update_or_query.message
        user = update_or_query.effective_user

    uid = str(user.id)
    balance = data_manager.get_user(uid).get("balance", 0)
    text = f"💰 **کیف پول شما**\nموجودی: {format_price(balance)} تومان"
    keyboard = [[InlineKeyboardButton("➕ درخواست شارژ", callback_data="request_topup")]]
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu")])
    kb = InlineKeyboardMarkup(keyboard)
    if isinstance(update_or_query, CallbackQuery):
        await safe_edit_message(message, text, reply_markup=kb)
    else:
        await message.reply_text(text, reply_markup=kb)


async def request_topup_start(update_or_query, context):
    if isinstance(update_or_query, CallbackQuery):
        message = update_or_query.message
        await answer_callback(update_or_query)
    else:
        message = update_or_query.message

    clear_user_states(context)
    context.user_data['awaiting_topup_amount'] = True
    card_number = data_manager.data.get("card_number", "6037997599999999")
    await message.reply_text(
        f"💰 **مبلغ شارژ را به تومان وارد کنید:**\n"
        f"(مثال: 50000)\n\n"
        f"💳 **شماره کارت:** `{card_number}`\n\n"
        f"برای انصراف /cancel را بزنید"
    )


async def handle_topup_amount(update: Update, context):
    if not context.user_data.get('awaiting_topup_amount'):
        return False
    text = update.message.text.strip()
    if text == "/cancel":
        clear_user_states(context)
        await main_menu(update, context)
        return True
    if not text.isdigit():
        await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید.\nبرای انصراف /cancel را بزنید")
        return True
    amount = int(text)
    if amount <= 0:
        await update.message.reply_text("❌ مبلغ باید بزرگتر از صفر باشد.\nبرای انصراف /cancel را بزنید")
        return True
    context.user_data['topup_amount'] = amount
    context.user_data['awaiting_topup_amount'] = False
    context.user_data['awaiting_topup_receipt'] = True
    card_number = data_manager.data.get("card_number", "6037997599999999")
    await update.message.reply_text(
        f"📸 **لطفاً تصویر رسید واریز مبلغ {format_price(amount)} تومان را ارسال کنید.**\n"
        f"💳 شماره کارت: `{card_number}`\n(برای انصراف /cancel را بزنید)"
    )
    return True


async def handle_topup_receipt(update: Update, context):
    if not context.user_data.get('awaiting_topup_receipt'):
        return False
    if not update.message.photo:
        await update.message.reply_text("❌ لطفاً تصویر رسید را ارسال کنید.\nبرای انصراف /cancel را بزنید")
        return True

    file_id = update.message.photo[-1].file_id
    amount = context.user_data.get('topup_amount', 0)
    user = update.effective_user
    uid = str(user.id)
    user_data = data_manager.get_user(uid)

    request_data = {
        "user_id": uid,
        "username": user_data.get("username", ""),
        "first_name": user_data.get("first_name", ""),
        "amount": amount,
        "receipt_photo": file_id
    }
    req_id = data_manager.add_topup_request(request_data)

    user_display = get_user_display(uid, user_data.get("username", ""))

    await update.message.reply_text(
        f"✅ **درخواست شارژ شما ثبت شد.**\n"
        f"🆔 کد پیگیری: `{req_id}`\n"
        f"پس از تأیید ادمین، موجودی کیف پول شما افزایش می‌یابد."
    )

    for admin_id in data_manager.data["owners"] + data_manager.data["admins"]:
        try:
            await context.bot.send_photo(
                int(admin_id),
                file_id,
                caption=(
                    f"💰 **درخواست شارژ جدید**\n"
                    f"🆔 کد: `{req_id}`\n"
                    f"👤 کاربر: {user_display}\n"
                    f"💰 مبلغ: {format_price(amount)} تومان"
                )
            )
        except Exception:
            pass

    context.user_data.pop('awaiting_topup_receipt', None)
    context.user_data.pop('topup_amount', None)
    return True


async def show_account(update: Update, context):
    user = update.effective_user
    uid = str(user.id)
    user_data = data_manager.get_user(uid)
    user_display = get_user_display(uid, user.username)
    text = (
        f"👤 **حساب کاربری شما**\n\n"
        f"👤 کاربر: {user_display}\n"
        f"💰 موجودی: {format_price(user_data.get('balance',0))} تومان\n"
        f"📦 سفارشات: {len(user_data.get('orders',[]))}"
    )
    await update.message.reply_text(text, reply_markup=get_main_keyboard(uid))


async def show_help(update: Update, context):
    help_text = data_manager.data.get("user_help_text", "راهنمایی در دسترس نیست.")
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard(update.effective_user.id))


async def show_support(update: Update, context):
    support = data_manager.data.get("support_username", "@Zifo_support")
    text = f"📞 **پشتیبانی:** {support}"
    await update.message.reply_text(text, reply_markup=get_main_keyboard(update.effective_user.id))


# =========================================================
#                     پنل ادمین
# =========================================================

async def admin_panel(update_or_query, context):
    if isinstance(update_or_query, CallbackQuery):
        message = update_or_query.message
        user = update_or_query.from_user
        await answer_callback(update_or_query)
    else:
        message = update_or_query.message
        user = update_or_query.effective_user

    if not data_manager.is_admin(user.id):
        await message.reply_text("❌ شما دسترسی ادمین ندارید.")
        return

    is_owner = data_manager.is_owner(user.id)
    if is_owner:
        keyboard = [
            ["➕ افزودن محصول", "📦 مدیریت محصولات"],
            ["📈 افزایش موجودی", "📉 کسر موجودی"],
            ["💰 افزایش همگانی", "💸 کسر همگانی"],
            ["📋 سفارش‌ها", "📊 آمار ربات"],
            ["💰 درخواست‌های شارژ", "💰 کیف پول کاربر"],
            ["👤 بررسی کاربر", "🚫 مسدود/آزاد کاربر"],
            ["💳 تنظیم شماره کارت"],
            ["👥 لیست ادمین‌ها", "➕ افزودن ادمین", "➖ حذف ادمین"],
            ["🛒 باز/بستن فروشگاه"],
            ["📢 پیام همگانی", "🗑️ حذف آخرین پیام همگانی", "🛠 تنظیم پشتیبانی"],
            ["🔙 بازگشت"]
        ]
    else:
        keyboard = [
            ["➕ افزودن محصول", "📦 مدیریت محصولات"],
            ["📈 افزایش موجودی", "📉 کسر موجودی"],
            ["📋 سفارش‌ها", "📊 آمار ربات"],
            ["💰 درخواست‌های شارژ", "💰 کیف پول کاربر"],
            ["👤 بررسی کاربر", "🚫 مسدود/آزاد کاربر"],
            ["🔙 بازگشت"]
        ]
    await message.reply_text("⚙️ **پنل مدیریت**", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))


async def toggle_shop(update: Update, context):
    user_id = update.effective_user.id
    if not data_manager.is_admin(user_id):
        await update.message.reply_text("❌ دسترسی غیرمجاز.")
        return
    current = data_manager.get_shop_status()
    new_status = not current["is_open"]
    data_manager.set_shop_status(new_status)
    if new_status:
        await update.message.reply_text("✅ **فروشگاه باز شد**\nکاربران می‌توانند خرید کنند.")
    else:
        await update.message.reply_text(f"🔒 **فروشگاه بسته شد**\n{current['closed_message']}")


async def increase_all_balance(update: Update, context):
    user_id = update.effective_user.id
    if not data_manager.is_owner(user_id):
        await update.message.reply_text("❌ فقط مالک می‌تواند افزایش همگانی انجام دهد.")
        return
    clear_user_states(context)
    context.user_data['awaiting_increase_all'] = True
    await update.message.reply_text("💰 **افزایش همگانی موجودی**\nمبلغ مورد نظر را به تومان وارد کنید:\n(برای انصراف /cancel را بزنید)")


async def decrease_all_balance(update: Update, context):
    user_id = update.effective_user.id
    if not data_manager.is_owner(user_id):
        await update.message.reply_text("❌ فقط مالک می‌تواند کسر همگانی انجام دهد.")
        return
    clear_user_states(context)
    context.user_data['awaiting_decrease_all'] = True
    await update.message.reply_text("💸 **کسر همگانی موجودی**\nمبلغ مورد نظر را به تومان وارد کنید:\n(برای انصراف /cancel را بزنید)")


async def handle_all_balance(update: Update, context):
    if context.user_data.get('awaiting_increase_all'):
        try:
            amount = int(update.message.text.strip())
            if amount <= 0:
                await update.message.reply_text("❌ مبلغ باید بزرگتر از صفر باشد.")
                return
            count = data_manager.increase_all_balance(amount)
            await update.message.reply_text(f"✅ {count} کاربر هر کدام {format_price(amount)} تومان دریافت کردند.")
            context.user_data.pop('awaiting_increase_all', None)
        except ValueError:
            await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید.")
    elif context.user_data.get('awaiting_decrease_all'):
        try:
            amount = int(update.message.text.strip())
            if amount <= 0:
                await update.message.reply_text("❌ مبلغ باید بزرگتر از صفر باشد.")
                return
            count = data_manager.decrease_all_balance(amount)
            await update.message.reply_text(f"✅ از {count} کاربر هر کدام {format_price(amount)} تومان کسر شد.")
            context.user_data.pop('awaiting_decrease_all', None)
        except ValueError:
            await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید.")


# =========================================================
#                     پیام همگانی
# =========================================================

async def broadcast_prompt(update: Update, context):
    user_id = update.effective_user.id
    if not data_manager.is_owner(user_id):
        await update.message.reply_text("❌ فقط مالک می‌تواند پیام همگانی ارسال کند.")
        return
    clear_user_states(context)
    context.user_data['awaiting_broadcast'] = True
    await update.message.reply_text(
        "📢 **پیام همگانی**\n\n"
        "متن پیام را ارسال کنید:\n"
        "برای انصراف /cancel را بزنید"
    )


async def handle_broadcast(update: Update, context):
    if not context.user_data.get('awaiting_broadcast'):
        return
    text = update.message.text
    users = data_manager.data["users"]
    sent = 0
    sent_messages = []
    
    for uid in users:
        try:
            msg = await context.bot.send_message(int(uid), text)
            sent += 1
            sent_messages.append({"chat_id": int(uid), "message_id": msg.message_id})
        except Exception:
            pass
    
    if sent_messages:
        data_manager.add_broadcast_message(sent_messages, text)
    
    await update.message.reply_text(f"✅ پیام به {sent} کاربر ارسال شد.")
    context.user_data.pop('awaiting_broadcast', None)


async def delete_last_broadcast(update: Update, context):
    user_id = update.effective_user.id
    if not data_manager.is_owner(user_id):
        await update.message.reply_text("❌ فقط مالک می‌تواند پیام همگانی را حذف کند.")
        return
    
    history = data_manager.get_broadcast_history()
    if not history:
        await update.message.reply_text("📭 هیچ پیام همگانی در تاریخچه وجود ندارد.")
        return
    
    last_msg = history[-1]
    sent_messages = last_msg.get("sent_messages", [])
    deleted_count = 0
    
    for sm in sent_messages:
        try:
            await context.bot.delete_message(sm["chat_id"], sm["message_id"])
            deleted_count += 1
        except Exception:
            pass
    
    data_manager.delete_broadcast_by_index(len(history) - 1)
    
    await update.message.reply_text(
        f"✅ آخرین پیام همگانی از {deleted_count} کاربر حذف شد."
    )


# =========================================================
#                     سفارش‌ها
# =========================================================

async def show_orders_menu(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("📥 سفارش‌های در انتظار", callback_data="admin_orders_pending")],
        [InlineKeyboardButton("✅ سفارش‌های تکمیل شده", callback_data="admin_orders_completed")],
        [InlineKeyboardButton("❌ سفارش‌های رد شده", callback_data="admin_orders_rejected")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]
    ]
    await update.message.reply_text("📋 **مدیریت سفارش‌ها**", reply_markup=InlineKeyboardMarkup(keyboard))


async def show_orders_by_status(update_or_query, context, status_list):
    if isinstance(update_or_query, CallbackQuery):
        message = update_or_query.message
        await answer_callback(update_or_query)
    else:
        message = update_or_query.message

    orders = [o for o in data_manager.data["orders"] if o.get("status") in status_list]
    orders = sorted(orders, key=lambda x: x.get("date", ""), reverse=True)

    if not orders:
        text = "📭 **هیچ سفارشی یافت نشد.**"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]])
        if isinstance(update_or_query, CallbackQuery):
            await safe_edit_message(message, text, reply_markup=kb)
        else:
            await message.reply_text(text, reply_markup=kb)
        return

    keyboard = []
    for o in orders[:20]:
        user_display = get_user_display(o.get("user_id", ""), o.get("username", ""))
        text_btn = f"#{o['order_id']} | {format_price(o['total'])} ت"
        keyboard.append([InlineKeyboardButton(text_btn, callback_data=f"admin_order_{o['order_id']}")])

    keyboard.append([InlineKeyboardButton("🗑️ خالی کردن لیست", callback_data=f"clear_orders_{'_'.join(status_list)}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])

    if 'waiting_admin' in status_list or 'waiting_receipt' in status_list:
        title = "📥 سفارش‌های در انتظار"
    elif 'completed' in status_list:
        title = "✅ سفارش‌های تکمیل شده"
    else:
        title = "❌ سفارش‌های رد شده"
    
    kb = InlineKeyboardMarkup(keyboard)
    if isinstance(update_or_query, CallbackQuery):
        await safe_edit_message(message, f"**{title}**", reply_markup=kb)
    else:
        await message.reply_text(f"**{title}**", reply_markup=kb)


async def clear_orders_by_status(update: Update, context, status_list_str: str):
    query = update.callback_query
    await query.answer()
    status_list = status_list_str.split('_')

    orders_to_remove = [o for o in data_manager.data["orders"] if o.get("status") in status_list]

    if not orders_to_remove:
        await query.edit_message_text("📭 **هیچ سفارشی برای حذف وجود ندارد.**")
        return

    for order in orders_to_remove:
        user_id = order.get("user_id")
        if user_id:
            user = data_manager.get_user(user_id)
            if order["order_id"] in user.get("orders", []):
                user["orders"].remove(order["order_id"])

    data_manager.data["orders"] = [o for o in data_manager.data["orders"] if o.get("status") not in status_list]
    data_manager.save_data()

    await query.edit_message_text(f"✅ **{len(orders_to_remove)} سفارش با موفقیت حذف شدند.**")


async def view_order_detail(query: CallbackQuery, context, order_id: str):
    order = data_manager.get_order(order_id)
    if not order:
        await query.answer("سفارش یافت نشد!")
        return

    user_display = get_user_display(order.get("user_id", ""), order.get("username", ""))

    items_text = ""
    for idx, item in enumerate(order.get('items', []), 1):
        items_text += f"{idx}. {item['name']} - {format_price(item['price'])} تومان\n"

    text = (
        f"🆔 **سفارش:** `{order['order_id']}`\n"
        f"👤 **کاربر:** {user_display}\n"
        f"💰 **مبلغ:** {format_price(order['total'])} تومان\n"
        f"📅 **تاریخ:** {order.get('date', '')}\n"
        f"📌 **وضعیت:** {order['status']}\n"
        f"━━━━━━━━━━\n"
        f"**محصولات:**\n"
        f"{items_text}"
    )

    keyboard = []
    if order['status'] == 'waiting_admin':
        keyboard.append([
            InlineKeyboardButton("✅ تأیید سفارش", callback_data=f"approve_order_{order_id}"),
            InlineKeyboardButton("❌ رد سفارش", callback_data=f"reject_order_{order_id}")
        ])
    if order.get('account_info'):
        keyboard.append([InlineKeyboardButton("📤 مشاهده کانفیگ", callback_data=f"view_config_{order_id}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])

    await safe_edit_message(query.message, text, reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)


async def approve_order(query: CallbackQuery, context, order_id: str):
    order = data_manager.get_order(order_id)
    if not order or order['status'] != 'waiting_admin':
        await query.answer("سفارش قابل تأیید نیست.")
        return
    clear_user_states(context)
    context.user_data['sending_config_for'] = order_id
    await query.edit_message_text(
        f"📤 **لطفاً متن کانفیگ را برای سفارش `{order_id}` ارسال کنید.**\n"
        f"(می‌توانید متن، عکس یا فایل ارسال کنید)\nبرای انصراف /cancel را بزنید"
    )


async def reject_order(query: CallbackQuery, context, order_id: str):
    order = data_manager.get_order(order_id)
    if not order or order['status'] != 'waiting_admin':
        await query.answer("سفارش قابل رد نیست.")
        return

    if order.get('payment_method') == 'wallet':
        user_id = order['user_id']
        user = data_manager.get_user(user_id)
        user['balance'] = user.get('balance', 0) + order['total']
        try:
            await context.bot.send_message(
                int(user_id),
                f"❌ **سفارش شما رد شد.**\n"
                f"🆔 سفارش: `{order_id}`\n"
                f"💰 مبلغ {format_price(order['total'])} تومان به کیف پول شما بازگردانده شد."
            )
        except Exception:
            pass

    data_manager.update_order(order_id, {"status": "rejected"})
    await query.answer("سفارش رد شد.")
    await show_orders_by_status(query, context, ['waiting_admin', 'waiting_receipt'])


async def send_config_to_user(update: Update, context):
    if not context.user_data.get('sending_config_for'):
        return
    order_id = context.user_data['sending_config_for']
    order = data_manager.get_order(order_id)
    if not order:
        await update.message.reply_text("❌ سفارش یافت نشد.")
        context.user_data.pop('sending_config_for', None)
        return

    user_id = int(order['user_id'])
    config_text = update.message.text or update.message.caption or "کانفیگ ارسال شد."
    
    items_list = []
    for item in order.get('items', []):
        items_list.append(f"{item['name']} - {format_price(item['price'])} تومان")
    items_str = "\n".join(items_list)
    
    await update.message.reply_text(
        f"📦 **محصولات سفارش {order_id}:**\n{items_str}\n\n"
        f"💰 **مبلغ کل:** {format_price(order['total'])} تومان\n\n"
        f"در حال ارسال کانفیگ به کاربر..."
    )
    
    try:
        if update.message.photo:
            await context.bot.send_photo(user_id, update.message.photo[-1].file_id, caption=config_text)
        elif update.message.document:
            await context.bot.send_document(user_id, update.message.document.file_id, caption=config_text)
        else:
            await context.bot.send_message(user_id, f"🎁 **کانفیگ سفارش {order_id}:**\n\n{config_text}")

        for item in order.get('items', []):
            data_manager.adjust_stock(item['id'], -1)

        data_manager.update_order(order_id, {"status": "completed", "account_info": config_text})
        await update.message.reply_text(f"✅ کانفیگ برای سفارش `{order_id}` ارسال و سفارش تکمیل شد.")
        context.user_data.pop('sending_config_for', None)
    except Exception as e:
        logger.error(f"Error sending config: {e}")
        await update.message.reply_text(f"❌ خطا در ارسال کانفیگ: {e}")


async def view_config(query: CallbackQuery, context, order_id: str):
    order = data_manager.get_order(order_id)
    if not order or not order.get('account_info'):
        await query.answer("کانفیگی موجود نیست.")
        return
    await safe_edit_message(
        query.message,
        f"**کانفیگ سفارش {order_id}:**\n\n{order['account_info']}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin_order_{order_id}")]])
      # =========================================================
#                     مدیریت محصولات (ادمین)
# =========================================================

async def manage_products(update_or_query, context):
    if isinstance(update_or_query, CallbackQuery):
        message = update_or_query.message
        await answer_callback(update_or_query)
    else:
        message = update_or_query.message

    products = data_manager.data["products"]
    if not products:
        text = "📭 هیچ محصولی وجود ندارد."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]])
        if isinstance(update_or_query, CallbackQuery):
            await safe_edit_message(message, text, reply_markup=kb)
        else:
            await message.reply_text(text, reply_markup=kb)
        return

    keyboard = []
    for p in products:
        keyboard.append([
            InlineKeyboardButton(f"✏️ {p['name']}", callback_data=f"edit_product_{p['id']}"),
            InlineKeyboardButton("❌ حذف", callback_data=f"delete_product_{p['id']}")
        ])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
    kb = InlineKeyboardMarkup(keyboard)
    if isinstance(update_or_query, CallbackQuery):
        await safe_edit_message(message, "📦 **مدیریت محصولات**", reply_markup=kb)
    else:
        await message.reply_text("📦 **مدیریت محصولات**", reply_markup=kb)


async def edit_product_prompt(query: CallbackQuery, context, product_id: int):
    product = data_manager.get_product(product_id)
    if not product:
        await query.answer("محصول یافت نشد.")
        return
    clear_user_states(context)
    context.user_data['editing_product_id'] = product_id
    context.user_data['awaiting_edit_product'] = True
    await query.edit_message_text(
        f"✏️ **ویرایش محصول:** {product['name']}\n"
        f"در ۴ خط بفرست:\nنام\nقیمت\nموجودی\nتوضیحات"
    )


async def handle_edit_product(update: Update, context):
    if not context.user_data.get('awaiting_edit_product'):
        return
    product_id = context.user_data.get('editing_product_id')
    if product_id is None:
        context.user_data.pop('awaiting_edit_product', None)
        return
    lines = update.message.text.strip().split('\n')
    if len(lines) < 4:
        await update.message.reply_text("❌ حداقل ۴ خط بفرست.")
        return
    name = lines[0].strip()
    try:
        price = int(lines[1].strip())
        stock = int(lines[2].strip())
    except ValueError:
        await update.message.reply_text("❌ قیمت و موجودی باید عدد باشند.")
        return
    description = "\n".join(lines[3:]).strip()

    data_manager.update_product(product_id, {"name": name, "price": price, "stock": stock, "description": description})
    await update.message.reply_text("✅ محصول ویرایش شد.")
    context.user_data.pop('editing_product_id', None)
    context.user_data.pop('awaiting_edit_product', None)
    await admin_panel(update, context)


async def delete_product_confirm(query: CallbackQuery, context, product_id: int):
    product = data_manager.get_product(product_id)
    if not product:
        await query.answer("محصول یافت نشد.")
        return
    keyboard = [
        [InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"confirm_delete_{product_id}")],
        [InlineKeyboardButton("❌ انصراف", callback_data="manage_products")]
    ]
    await safe_edit_message(
        query.message,
        f"⚠️ **آیا از حذف محصول `{product['name']}` مطمئن هستید؟**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def confirm_delete_product(query: CallbackQuery, context, product_id: int):
    data_manager.delete_product(product_id)
    await query.answer("محصول حذف شد.")
    await manage_products(query, context)


async def increase_stock(update: Update, context):
    clear_user_states(context)
    context.user_data['awaiting_stock_increase'] = True
    await update.message.reply_text("📈 **افزایش موجودی**\nبنویس: `product_id amount`\nمثال: `1 50`")


async def decrease_stock(update: Update, context):
    clear_user_states(context)
    context.user_data['awaiting_stock_decrease'] = True
    await update.message.reply_text("📉 **کسر موجودی**\nبنویس: `product_id amount`\nمثال: `1 10`")


async def handle_stock_change(update: Update, context):
    if context.user_data.get('awaiting_stock_increase'):
        parts = update.message.text.split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            await update.message.reply_text("❌ فرمت اشتباه. مثال: `1 50`")
            return
        pid = int(parts[0])
        amount = int(parts[1])
        product = data_manager.get_product(pid)
        if not product:
            await update.message.reply_text("❌ محصول یافت نشد.")
        else:
            data_manager.adjust_stock(pid, amount)
            await update.message.reply_text(f"✅ موجودی {product['name']} به {product.get('stock', 0)} افزایش یافت.")
        context.user_data.pop('awaiting_stock_increase', None)
        await admin_panel(update, context)

    elif context.user_data.get('awaiting_stock_decrease'):
        parts = update.message.text.split()
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            await update.message.reply_text("❌ فرمت اشتباه. مثال: `1 10`")
            return
        pid = int(parts[0])
        amount = int(parts[1])
        product = data_manager.get_product(pid)
        if not product:
            await update.message.reply_text("❌ محصول یافت نشد.")
        else:
            data_manager.adjust_stock(pid, -amount)
            await update.message.reply_text(f"✅ موجودی {product['name']} به {product.get('stock', 0)} کاهش یافت.")
        context.user_data.pop('awaiting_stock_decrease', None)
        await admin_panel(update, context)


# =========================================================
#                     درخواست‌های شارژ (ادمین)
# =========================================================

async def show_topup_requests(update_or_query, context):
    if isinstance(update_or_query, CallbackQuery):
        message = update_or_query.message
        await answer_callback(update_or_query)
    else:
        message = update_or_query.message

    requests = data_manager.data["topup_requests"]
    pending = [r for r in requests if r.get("status") == "pending"]
    if not pending:
        text = "📭 هیچ درخواست شارژی نیست."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")]])
        if isinstance(update_or_query, CallbackQuery):
            await safe_edit_message(message, text, reply_markup=kb)
        else:
            await message.reply_text(text, reply_markup=kb)
        return

    keyboard = []
    for r in pending[:20]:
        text_btn = f"#{r['request_id']} | {format_price(r['amount'])} ت"
        keyboard.append([InlineKeyboardButton(text_btn, callback_data=f"view_topup_{r['request_id']}")])

    keyboard.append([InlineKeyboardButton("🗑️ خالی کردن لیست", callback_data="clear_topup_requests")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
    kb = InlineKeyboardMarkup(keyboard)
    if isinstance(update_or_query, CallbackQuery):
        await safe_edit_message(message, "💰 **درخواست‌های شارژ**", reply_markup=kb)
    else:
        await message.reply_text("💰 **درخواست‌های شارژ**", reply_markup=kb)


async def clear_topup_requests(update: Update, context):
    query = update.callback_query
    await query.answer()

    pending_reqs = [r for r in data_manager.data["topup_requests"] if r.get("status") == "pending"]

    if not pending_reqs:
        await query.edit_message_text("📭 چیزی برای حذف نیست.")
        return

    data_manager.data["topup_requests"] = [r for r in data_manager.data["topup_requests"] if r.get("status") != "pending"]
    data_manager.save_data()

    await query.edit_message_text(f"✅ {len(pending_reqs)} درخواست حذف شد.")


async def view_topup_detail(query: CallbackQuery, context, req_id: str):
    req = data_manager.get_topup_request(req_id)
    if not req:
        await query.answer("یافت نشد.")
        return

    user_display = get_user_display(req.get("user_id", ""), req.get("username", ""))

    text = (
        f"💰 **درخواست شارژ**\n"
        f"🆔 `{req['request_id']}`\n"
        f"👤 {user_display}\n"
        f"💰 {format_price(req['amount'])} تومان\n"
        f"📅 {req.get('date', '')}"
    )
    keyboard = [
        [InlineKeyboardButton("✅ تأیید", callback_data=f"approve_topup_{req_id}"),
         InlineKeyboardButton("❌ رد", callback_data=f"reject_topup_{req_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_topup_requests")]
    ]
    if req.get('receipt_photo'):
        try:
            await query.message.delete()
        except Exception:
            pass
        await context.bot.send_photo(
            query.message.chat_id, req['receipt_photo'],
            caption=text, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await safe_edit_message(query.message, text, reply_markup=InlineKeyboardMarkup(keyboard))


async def approve_topup(query: CallbackQuery, context, req_id: str):
    req = data_manager.get_topup_request(req_id)
    if not req or req['status'] != 'pending':
        await query.answer("قابل تأیید نیست.")
        return
    user_id = req['user_id']
    user = data_manager.get_user(user_id)
    user['balance'] = user.get('balance', 0) + req['amount']
    data_manager.update_topup_request(req_id, {"status": "approved"})
    await query.answer("تأیید شد")
    try:
        await context.bot.send_message(int(user_id), f"✅ شارژ تأیید شد.\n💰 {format_price(req['amount'])} ت اضافه شد.")
    except Exception:
        pass
    await show_topup_requests(query, context)


async def reject_topup(query: CallbackQuery, context, req_id: str):
    req = data_manager.get_topup_request(req_id)
    if not req or req['status'] != 'pending':
        await query.answer("قابل رد نیست.")
        return
    data_manager.update_topup_request(req_id, {"status": "rejected"})
    await query.answer("رد شد")
    try:
        await context.bot.send_message(int(req['user_id']), "❌ درخواست شارژ رد شد.")
    except Exception:
        pass
    await show_topup_requests(query, context)


# =========================================================
#                     بررسی کاربر / بن / کیف پول ادمین
# =========================================================

async def user_check_prompt(update: Update, context):
    clear_user_states(context)
    context.user_data['awaiting_user_check'] = True
    await update.message.reply_text("👤 شناسه عددی کاربر:")


async def handle_user_check(update: Update, context):
    if not context.user_data.get('awaiting_user_check'):
        return
    uid = update.message.text.strip()
    if not uid.isdigit():
        await update.message.reply_text("❌ عدد بفرست.")
        return
    user = data_manager.get_user(uid)
    banned = data_manager.is_user_banned(uid)
    user_display = get_user_display(uid, user.get("username", ""))
    text = (f"👤 **اطلاعات کاربر**\n\n{user_display}\n"
            f"💰 موجودی: {format_price(user.get('balance',0))} ت\n"
            f"📦 سفارشات: {len(user.get('orders',[]))}\n🚫 وضعیت: {'مسدود' if banned else 'فعال'}")
    await update.message.reply_text(text)
    context.user_data.pop('awaiting_user_check', None)


async def ban_toggle_prompt(update: Update, context):
    clear_user_states(context)
    context.user_data['awaiting_ban_toggle'] = True
    await update.message.reply_text("🚫 شناسه عددی کاربر:")


async def handle_ban_toggle(update: Update, context):
    if not context.user_data.get('awaiting_ban_toggle'):
        return
    uid = update.message.text.strip()
    if not uid.isdigit():
        await update.message.reply_text("❌ عدد بفرست.")
        return
    if data_manager.is_user_banned(uid):
        data_manager.unban_user(uid)
        await update.message.reply_text(f"✅ کاربر `{uid}` آزاد شد.")
    else:
        data_manager.ban_user(uid)
        await update.message.reply_text(f"🚫 کاربر `{uid}` مسدود شد.")
    context.user_data.pop('awaiting_ban_toggle', None)


async def wallet_admin_prompt(update: Update, context):
    clear_user_states(context)
    context.user_data['awaiting_wallet_user_id'] = True
    await update.message.reply_text("💰 شناسه عددی کاربر:")


async def handle_wallet_admin(update: Update, context):
    if context.user_data.get('awaiting_wallet_user_id'):
        uid = update.message.text.strip()
        if not uid.isdigit():
            await update.message.reply_text("❌ عدد بفرست.")
            return
        context.user_data['wallet_target_uid'] = uid
        context.user_data['awaiting_wallet_user_id'] = False
        context.user_data['awaiting_wallet_amount'] = True
        user = data_manager.get_user(uid)
        await update.message.reply_text(
            f"موجودی فعلی: {format_price(user.get('balance',0))} ت\n"
            f"مبلغ تغییر (مثبت یا منفی):"
        )
    elif context.user_data.get('awaiting_wallet_amount'):
        try:
            amount = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ عدد بفرست.")
            return
        uid = context.user_data.get('wallet_target_uid')
        if not uid:
            context.user_data.pop('awaiting_wallet_amount', None)
            return
        user = data_manager.get_user(uid)
        new_balance = max(0, user.get('balance', 0) + amount)
        user['balance'] = new_balance
        data_manager.save_data()
        await update.message.reply_text(f"✅ موجودی `{uid}` شد {format_price(new_balance)} ت")
        context.user_data.pop('wallet_target_uid', None)
        context.user_data.pop('awaiting_wallet_amount', None)


# =========================================================
#                     تنظیمات / ادمین‌ها
# =========================================================

async def set_card_number(update: Update, context):
    clear_user_states(context)
    context.user_data['awaiting_card'] = True
    await update.message.reply_text("💳 شماره کارت جدید:")


async def set_support(update: Update, context):
    clear_user_states(context)
    context.user_data['awaiting_support'] = True
    await update.message.reply_text("🛠 آیدی پشتیبانی:")


async def handle_settings(update: Update, context):
    if context.user_data.get('awaiting_card'):
        data_manager.data["card_number"] = update.message.text.strip()
        data_manager.save_data()
        await update.message.reply_text("✅ ثبت شد.")
        context.user_data.pop('awaiting_card', None)
    elif context.user_data.get('awaiting_support'):
        data_manager.data["support_username"] = update.message.text.strip()
        data_manager.save_data()
        await update.message.reply_text("✅ ثبت شد.")
        context.user_data.pop('awaiting_support', None)


async def list_admins(update: Update, context):
    owners = data_manager.data["owners"]
    admins = data_manager.data["admins"]
    text = "👑 **مالکین:**\n" + "\n".join(owners) + "\n\n🛡 **ادمین‌ها:**\n" + ("\n".join(admins) if admins else "هیچ")
    await update.message.reply_text(text)


async def add_admin_prompt(update: Update, context):
    clear_user_states(context)
    context.user_data['awaiting_add_admin'] = True
    await update.message.reply_text("➕ شناسه ادمین جدید:")


async def remove_admin_prompt(update: Update, context):
    clear_user_states(context)
    context.user_data['awaiting_remove_admin'] = True
    await update.message.reply_text("➖ شناسه ادمین:")


async def handle_admin_edit(update: Update, context):
    if context.user_data.get('awaiting_add_admin'):
        uid = update.message.text.strip()
        if data_manager.add_admin(uid):
            await update.message.reply_text(f"✅ `{uid}` ادمین شد.")
        else:
            await update.message.reply_text("❌ از قبل ادمین است.")
        context.user_data.pop('awaiting_add_admin', None)
    elif context.user_data.get('awaiting_remove_admin'):
        uid = update.message.text.strip()
        if data_manager.remove_admin(uid):
            await update.message.reply_text(f"✅ `{uid}` حذف شد.")
        else:
            await update.message.reply_text("❌ ادمین نیست.")
        context.user_data.pop('awaiting_remove_admin', None)


async def admin_stats(update: Update, context):
    users_count = len(data_manager.data["users"])
    orders_count = len(data_manager.data["orders"])
    completed_orders = [o for o in data_manager.data["orders"] if o.get("status") == "completed"]
    total_revenue = sum(o["total"] for o in completed_orders)
    text = (f"📊 **آمار ربات**\n👥 کاربران: {users_count}\n🛒 سفارشات: {orders_count}\n"
            f"✅ تکمیل: {len(completed_orders)}\n💰 درآمد: {format_price(total_revenue)} ت")
    await update.message.reply_text(text)


async def add_product_prompt(update: Update, context):
    clear_user_states(context)
    context.user_data['awaiting_product_name'] = True
    await update.message.reply_text("➕ نام محصول:")


async def handle_add_product(update: Update, context):
    if context.user_data.get('awaiting_product_name'):
        context.user_data['new_product_name'] = update.message.text
        context.user_data['awaiting_product_name'] = False
        context.user_data['awaiting_product_price'] = True
        await update.message.reply_text("💰 قیمت:")
    elif context.user_data.get('awaiting_product_price'):
        try:
            price = int(update.message.text)
        except ValueError:
            await update.message.reply_text("❌ عدد بفرست.")
            return
        context.user_data['awaiting_product_price'] = False
        context.user_data['awaiting_product_stock'] = True
        context.user_data['new_product_price'] = price
        await update.message.reply_text("📦 موجودی:")
    elif context.user_data.get('awaiting_product_stock'):
        try:
            stock = int(update.message.text)
        except ValueError:
            await update.message.reply_text("❌ عدد بفرست.")
            return
        name = context.user_data.get('new_product_name')
        price = context.user_data.get('new_product_price')
        data_manager.add_product({"name": name, "price": price, "stock": stock, "description": ""})
        await update.message.reply_text(f"✅ محصول `{name}` اضافه شد.")
        context.user_data.pop('new_product_name', None)
        context.user_data.pop('new_product_price', None)
        context.user_data.pop('awaiting_product_stock', None)
        await admin_panel(update, context)


# =========================================================
#                     Callback Router
# =========================================================

async def button_handler(update: Update, context):
    query = update.callback_query
    data = query.data
    try:
        if data == "back_to_menu":
            await main_menu(query, context)
        elif data == "admin_back":
            await admin_panel(query, context)
        elif data == "manage_products":
            await manage_products(query, context)
        elif data == "admin_topup_requests":
            await show_topup_requests(query, context)
        elif data == "products_back":
            await show_products(query, context)
        elif data == "admin_orders_pending":
            await show_orders_by_status(query, context, ['waiting_admin', 'waiting_receipt'])
        elif data == "admin_orders_completed":
            await show_orders_by_status(query, context, ['completed'])
        elif data == "admin_orders_rejected":
            await show_orders_by_status(query, context, ['rejected'])
        elif data.startswith("product_"):
            await product_details(query, context, int(data.split("_")[1]))
        elif data.startswith("cart_add_"):
            await add_to_cart(query, context, int(data.split("_")[2]))
        elif data.startswith("cart_remove_"):
            await remove_from_cart(query, context, int(data.split("_")[2]))
        elif data == "show_cart":
            await show_cart(query, context)
        elif data == "clear_cart":
            await clear_cart(query, context)
        elif data == "checkout":
            await checkout(query, context)
        elif data == "pay_wallet":
            await pay_wallet(query, context)
        elif data == "request_topup":
            await request_topup_start(query, context)
        elif data.startswith("admin_order_"):
            await view_order_detail(query, context, data.split("_")[2])
        elif data.startswith("approve_order_"):
            await approve_order(query, context, data.split("_")[2])
        elif data.startswith("reject_order_"):
            await reject_order(query, context, data.split("_")[2])
        elif data.startswith("view_config_"):
            await view_config(query, context, data.split("_")[2])
        elif data.startswith("edit_product_"):
            await edit_product_prompt(query, context, int(data.split("_")[2]))
        elif data.startswith("delete_product_"):
            await delete_product_confirm(query, context, int(data.split("_")[2]))
        elif data.startswith("confirm_delete_"):
            await confirm_delete_product(query, context, int(data.split("_")[2]))
        elif data.startswith("view_topup_"):
            await view_topup_detail(query, context, data.split("_")[2])
        elif data.startswith("approve_topup_"):
            await approve_topup(query, context, data.split("_")[2])
        elif data.startswith("reject_topup_"):
            await reject_topup(query, context, data.split("_")[2])
        elif data.startswith("clear_orders_"):
            status_str = data[len("clear_orders_"):]
            await clear_orders_by_status(update, context, status_str)
        elif data == "clear_topup_requests":
            await clear_topup_requests(update, context)
        elif data == "none":
            await query.answer()
        else:
            await query.answer("⚠️ نامعتبر", show_alert=True)
    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        try:
            await query.answer("❌ خطا", show_alert=True)
        except Exception:
            pass


async def admin_text_handler(update: Update, context):
    text = update.message.text
    uid = str(update.effective_user.id)
    if not data_manager.is_admin(uid):
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
        await increase_stock(update, context)
    elif text == "📉 کسر موجودی":
        await decrease_stock(update, context)
    elif text == "📊 آمار ربات":
        await admin_stats(update, context)
    elif text == "💰 درخواست‌های شارژ":
        await show_topup_requests(update, context)
    elif text == "💰 کیف پول کاربر":
        await wallet_admin_prompt(update, context)
    elif text == "👤 بررسی کاربر":
        await user_check_prompt(update, context)
    elif text == "🚫 مسدود/آزاد کاربر":
        await ban_toggle_prompt(update, context)
    elif text == "💳 تنظیم شماره کارت" and data_manager.is_owner(uid):
        await set_card_number(update, context)
    elif text == "🛠 تنظیم پشتیبانی" and data_manager.is_owner(uid):
        await set_support(update, context)
    elif text == "👥 لیست ادمین‌ها" and data_manager.is_owner(uid):
        await list_admins(update, context)
    elif text == "➕ افزودن ادمین" and data_manager.is_owner(uid):
        await add_admin_prompt(update, context)
    elif text == "➖ حذف ادمین" and data_manager.is_owner(uid):
        await remove_admin_prompt(update, context)
    elif text == "📢 پیام همگانی" and data_manager.is_owner(uid):
        await broadcast_prompt(update, context)
    elif text == "🗑️ حذف آخرین پیام همگانی" and data_manager.is_owner(uid):
        await delete_last_broadcast(update, context)
    elif text == "💰 افزایش همگانی" and data_manager.is_owner(uid):
        await increase_all_balance(update, context)
    elif text == "💸 کسر همگانی" and data_manager.is_owner(uid):
        await decrease_all_balance(update, context)
    elif text == "🛒 باز/بستن فروشگاه" and data_manager.is_admin(uid):
        await toggle_shop(update, context)
    else:
        return False
    return True


async def message_handler(update: Update, context):
    uid = str(update.effective_user.id)
    if data_manager.is_user_banned(uid) and not data_manager.is_admin(uid):
        await update.message.reply_text("🚫 مسدود هستی.")
        return

    if context.user_data.get('awaiting_topup_amount'):
        await handle_topup_amount(update, context)
        return
    if context.user_data.get('awaiting_topup_receipt'):
        await handle_topup_receipt(update, context)
        return
    if context.user_data.get('sending_config_for'):
        await send_config_to_user(update, context)
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
    if context.user_data.get('awaiting_wallet_user_id') or context.user_data.get('awaiting_wallet_amount'):
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


# =========================================================
#                     ساخت Application
# =========================================================

application = Application.builder().token(BOT_TOKEN).updater(None).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("cancel", cancel))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.PHOTO, message_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))


# =========================================================
#                     Flask Webhook
# =========================================================

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


# =========================================================
#                     Launch
# =========================================================

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT)
