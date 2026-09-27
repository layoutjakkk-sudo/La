import asyncio
from datetime import datetime
from io import BytesIO
import json
import logging
import os
import re
import time

from aiogram import BaseMiddleware, Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
import qrcode
import requests

# ============================================================
# CONFIGURATION & CONSTANTS
# ============================================================
TOKEN =“8675192537:AAF11LuQseJP1sRa9JV6kBstR8pe94k53RU"
INITIAL_ADMIN_ID = 7686361815

SETTINGS_FILE = "bot_settings.json"
STOCK_FILE = "stock_keys.json"
DATA_FILE = "services_data.json"
SELL_STOCK_FILE = "sellstock.txt"
USER_HISTORY_FILE = "user_history.json"
USERS_LIST_FILE = "users_list.json"
SALES_LEDGER_FILE = "sales_ledger.json"
AUDIT_LOG_FILE = "admin_audit_log.json"


LOW_STOCK_THRESHOLD = 2



LOW_STOCK_THRESHOLD = 2

PREMIUM_ICONS = [
    {"num": 1, "id": "5904258298764334001"},
    {"num": 2, "id": "6039404727542747508"},
    {"num": 3, "id": "6039451237743595514"},
    {"num": 4, "id": "6039779802741739617"},
    {"num": 5, "id": "5944753741512052670"},
    {"num": 6, "id": "6028205772117118673"},
    {"num": 7, "id": "6039522349517115015"},
    {"num": 8, "id": "5983580310292402968"},
    {"num": 9, "id": "5778570255555105942"},
    {"num": 10, "id": "5294225191562400452"},
    {"num": 11, "id": "6075534731171079238"},
    {"num": 12, "id": "5773677501825945508"},
    {"num": 13, "id": "6041730074376410123"},
    {"num": 14, "id": "6035130900075777681"},
    {"num": 15, "id": "6039522349517115015"},
    {"num": 16, "id": "6039381989985882045"},
    {"num": 17, "id": "6030722571412967168"},
    {"num": 18, "id": "6034831751308644168"},
    {"num": 19, "id": "6033108709213736873"},
    {"num": 20, "id": "5891207662678317861"},
    {"num": 21, "id": "6042137469204303531"},
    {"num": 22, "id": "5884479287171485878"},
    {"num": 23, "id": "5938539885907415367"},
    {"num": 24, "id": "5805648413743651862"},
]

DEFAULT_SETTINGS = {
    "admin_ids": [INITIAL_ADMIN_ID],
    "bot_name": "AngkorMusic Store",
    "welcome_text": (
        "សូមស្វាគមន៍មកកាន់ប្រព័ន្ធទិញទំនិញស្វ័យប្រវត្តិ!"
        " សូមជ្រើសរើសមុខងារខាងក្រោម៖"
    ),
    "maintenance_mode": False,
    "log_group_id": -1004299324806,
    "gateway_url": "https://khmer-system.com",
    "active_provider": "bakong",  # 'aba' or 'bakong'
    "aba_api_key": "PK_c7f5d9f13cd9dd37793345c7a528ca751d6543db",
    “merchant id”:”3zSJZ2”
}

# ============================================================
# STORAGE UTILITIES & AUDITING
# ============================================================

def log_admin_action(admin_id: int, admin_name: str, action: str, details: str):
  logs = []
  if os.path.exists(AUDIT_LOG_FILE):
    try:
      with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
        logs = json.load(f)
    except Exception:
      logs = []

  logs.append({
      "admin_id": admin_id,
      "admin_name": admin_name,
      "action": action,
      "details": details,
      "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
  })

  try:
    with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
      json.dump(logs, f, ensure_ascii=False, indent=2)
  except Exception:
    pass


def load_settings():
  if os.path.exists(SETTINGS_FILE):
    try:
      with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        for k, v in DEFAULT_SETTINGS.items():
          if k not in data:
            data[k] = v
        # Legacy key migration support
        if "gateway_key" in data and "bakong_api_key" not in data:
          data["bakong_api_key"] = data["gateway_key"]
        return data
    except Exception:
      pass
  return DEFAULT_SETTINGS.copy()


def save_settings(data):
  try:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=2)
  except Exception:
    pass


def is_admin(user_id: int) -> bool:
  settings = load_settings()
  return user_id in set(settings.get("admin_ids", [INITIAL_ADMIN_ID]))


def load_stock():
  if os.path.exists(STOCK_FILE):
    try:
      with open(STOCK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      pass
  return {}


def save_stock(stock_data):
  try:
    with open(STOCK_FILE, "w", encoding="utf-8") as f:
      json.dump(stock_data, f, ensure_ascii=False, indent=2)
  except Exception:
    pass


def load_data():
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("services", {}), set(data.get("resellers", []))
    except Exception:
      pass
  return {}, set()


def save_data(services, resellers):
  try:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
      json.dump(
          {"services": services, "resellers": list(resellers)},
          f,
          ensure_ascii=False,
          indent=2,
      )
  except Exception:
    pass


def load_users():
  if os.path.exists(USERS_LIST_FILE):
    try:
      with open(USERS_LIST_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))
    except Exception:
      pass
  return set()


def save_users(users_set):
  try:
    with open(USERS_LIST_FILE, "w", encoding="utf-8") as f:
      json.dump(list(users_set), f)
  except Exception:
    pass


def save_user_history(
    user_id: int,
    order_id: str,
    item_name: str,
    key: str,
    guide_info: str,
    amount: float = 0.0,
):
  history = {}
  if os.path.exists(USER_HISTORY_FILE):
    try:
      with open(USER_HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
    except Exception:
      history = {}

  uid_str = str(user_id)
  if uid_str not in history:
    history[uid_str] = []

  history[uid_str].append({
      "order_id": order_id,
      "item_name": item_name,
      "key": key,
      "amount": amount,
      "guide_info": guide_info,
      "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
  })

  try:
    with open(USER_HISTORY_FILE, "w", encoding="utf-8") as f:
      json.dump(history, f, ensure_ascii=False, indent=2)
  except Exception:
    pass


def get_user_history(user_id: int):
  if os.path.exists(USER_HISTORY_FILE):
    try:
      with open(USER_HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
        return history.get(str(user_id), [])
    except Exception:
      pass
  return []


def record_sales_ledger(
    order_id: str, buyer_id: int, username: str, item_name: str, amount: float
):
  sales = []
  if os.path.exists(SALES_LEDGER_FILE):
    try:
      with open(SALES_LEDGER_FILE, "r", encoding="utf-8") as f:
        sales = json.load(f)
    except Exception:
      sales = []

  now = datetime.now()
  sales.append({
      "order_id": order_id,
      "buyer_id": buyer_id,
      "username": username,
      "item_name": item_name,
      "amount": amount,
      "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
      "year_month": now.strftime("%Y-%m"),
  })

  try:
    with open(SALES_LEDGER_FILE, "w", encoding="utf-8") as f:
      json.dump(sales, f, ensure_ascii=False, indent=2)
  except Exception:
    pass


def get_sales_analytics():
  if not os.path.exists(SALES_LEDGER_FILE):
    return {
        "total_revenue": 0.0,
        "this_month_revenue": 0.0,
        "last_month_revenue": 0.0,
        "growth_percentage": 0.0,
        "total_orders": 0,
        "this_month_orders": 0,
        "recent_transactions": [],
    }
  try:
    with open(SALES_LEDGER_FILE, "r", encoding="utf-8") as f:
      sales = json.load(f)
  except Exception:
    sales = []

  now = datetime.now()
  current_ym = now.strftime("%Y-%m")
  last_year = now.year if now.month > 1 else now.year - 1
  last_month = now.month - 1 if now.month > 1 else 12
  last_ym = f"{last_year:04d}-{last_month:02d}"

  total_revenue = 0.0
  this_month_revenue = 0.0
  last_month_revenue = 0.0
  this_month_orders = 0

  for tx in sales:
    amt = float(tx.get("amount", 0.0))
    total_revenue += amt
    ym = tx.get("year_month", "")
    if ym == current_ym:
      this_month_revenue += amt
      this_month_orders += 1
    elif ym == last_ym:
      last_month_revenue += amt

  if last_month_revenue > 0:
    growth_pct = (
        (this_month_revenue - last_month_revenue) / last_month_revenue
    ) * 100.0
  else:
    growth_pct = 100.0 if this_month_revenue > 0 else 0.0

  return {
      "total_revenue": total_revenue,
      "this_month_revenue": this_month_revenue,
      "last_month_revenue": last_month_revenue,
      "growth_percentage": growth_pct,
      "total_orders": len(sales),
      "this_month_orders": this_month_orders,
      "recent_transactions": sales[-6:],
  }


def get_detailed_user_statistics():
  bot_users = load_users()
  sales = []
  if os.path.exists(SALES_LEDGER_FILE):
    try:
      with open(SALES_LEDGER_FILE, "r", encoding="utf-8") as f:
        sales = json.load(f)
    except Exception:
      sales = []

  buyer_spending = {}
  for tx in sales:
    uid = tx.get("buyer_id")
    uname = tx.get("username", "Unknown")
    amt = float(tx.get("amount", 0.0))
    if uid not in buyer_spending:
      buyer_spending[uid] = {
          "orders": 0,
          "total_spent": 0.0,
          "username": uname,
      }
    buyer_spending[uid]["orders"] += 1
    buyer_spending[uid]["total_spent"] += amt

  sorted_buyers = sorted(
      buyer_spending.items(), key=lambda x: x[1]["total_spent"], reverse=True
  )

  return {
      "total_users": len(bot_users),
      "total_buyers": len(buyer_spending),
      "top_buyers": sorted_buyers[:5],
  }


# ============================================================
# AI ASSISTANT FUNCTION
# ============================================================

async def ask_ai_assistant(prompt: str) -> str:
  prompt_lower = prompt.lower()
  if any(w in prompt_lower for w in ["ទិញ", "buy", "order", "របៀបទិញ"]):
    return (
        "💡 <b>របៀបទិញទំនិញក្នុង Bot:</b>\n"
        "1. ចុចប៊ូតុង <b>BUY NOW</b>\n"
        "2. ជ្រើសរើស Category និង Plan ដែលចង់បាន\n"
        "3. ចុច <b>បញ្ជាក់ការទិញ</b> រួចស្កេន QR Payment\n"
        "4. ប្រព័ន្ធនឹងផ្ញើ License Key ពីស្តុក File និង Video Guide ជូនភ្លាមៗស្វ័យប្រវត្ត!"
    )
  elif any(w in prompt_lower for w in ["key", "file", "បាត់ key", "មើល key"]):
    return (
        "🔑 អ្នកអាចមើល Key, Link ឬ File ដែលធ្លាប់បានទិញ ដោយចុចប៊ូតុង <b>Key"
        " របស់ខ្ញុំ</b> នៅ Menu ខាងក្រោម។"
    )
  elif any(
      w in prompt_lower
      for w in ["admin", "ទាក់ទង", "contact", "support", "ជួយ"]
  ):
    return (
        "👨‍💻 សម្រាប់ជំនួយបន្ថែម ឬបញ្ហាទូទាត់ប្រាក់ សូមទាក់ទងមកកាន់ Admin"
        " ផ្ទាល់។"
    )
  else:
    return (
        "🤖 <b>AI Assistant:</b>\n"
        f'ខ្ញុំបានទទួលសំណួរ: <i>"{prompt}"</i>\n\n'
        "លោកអ្នកអាចសាកសួរអំពី៖\n"
        "• របៀបទិញទំនិញ (BUY NOW)\n"
        "• ពិនិត្យមើល Key/File ចាស់ៗ (Key របស់ខ្ញុំ)\n"
        "• ជំនួយបច្ចេកទេស និងការទូទាត់ប្រាក់"
    )


# ============================================================
# MAINTENANCE MIDDLEWARE
# ============================================================

class MaintenanceMiddleware(BaseMiddleware):

  async def __call__(self, handler, event, data):
    settings = load_settings()
    is_maintenance = settings.get("maintenance_mode", False)

    user = data.get("event_from_user")
    if user and is_maintenance and not is_admin(user.id):
      if isinstance(event, types.Message):
        await event.answer(
            '<tg-emoji emoji-id="6039522349517115015">🛠</tg-emoji> '
            "<b>ប្រព័ន្ធកំពុងដំណើរការជួសជុល (MAINTENANCE MODE)</b>\n\n"
            "<i>សូមអភ័យទោស Bot កំពុង Update ប្រព័ន្ធជាបណ្ដោះអាសន្ន។"
            " សូមត្រឡប់មកវិញនៅពេលក្រោយ!</i>"
        )
      elif isinstance(event, types.CallbackQuery):
        await event.answer(
            "🛠 Bot កំពុងជួសជុលប្រព័ន្ធ (Maintenance)!",
            show_alert=True,
        )
      return

    return await handler(event, data)


bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
dp.message.middleware(MaintenanceMiddleware())
dp.callback_query.middleware(MaintenanceMiddleware())

stock_lock = asyncio.Lock()
active_payment = {}
active_payments_global = {}


class UserState(StatesGroup):
  chatting_with_ai = State()


class AdminState(StatesGroup):
  waiting_for_keys = State()
  waiting_for_normal_price = State()
  waiting_for_reseller_price = State()
  waiting_for_add_reseller = State()
  waiting_for_remove_reseller = State()
  waiting_for_broadcast = State()

  # Order Lookup
  waiting_for_order_lookup = State()

  # Admin Permission Config
  waiting_for_new_admin_id = State()
  waiting_for_del_admin_id = State()

  # Welcome / Bot Info Config
  waiting_for_bot_name = State()
  waiting_for_welcome_text = State()

  # Gateway & Group Settings
  waiting_for_log_group_id = State()
  waiting_for_gateway_url = State()
  waiting_for_provider_key = State()

  # Category states
  cat_name = State()
  cat_custom_emoji_input = State()
  cat_guide_video = State()

  # Plan states
  plan_name = State()
  plan_price = State()
  plan_reseller_price = State()
  plan_guide_video = State()
  plan_attachment = State()
  plan_file_update = State()


async def safe_edit_text(message: types.Message, text: str, reply_markup=None):
  try:
    await message.edit_text(text, reply_markup=reply_markup)
  except TelegramBadRequest as e:
    if "message is not modified" not in str(e):
      raise e


# ============================================================
# MULTI-PAYMENT HANDLER (ABA & BAKONG DYNAMIC)
# ============================================================

def create_payment(amount, reference, provider=None):
  settings = load_settings()
  gw_url = settings.get("gateway_url", "https://api.tolasaint.com")
  
  if not provider:
    provider = settings.get("active_provider", "bakong")
  
  gw_key = settings.get("aba_api_key" if provider == "aba" else "bakong_api_key", "")
  
  try:
    payload = {
        "amount": f"{float(amount):.2f}",
        "currency": "USD",
        "reference": str(reference),
        "provider": provider,
    }
    response = requests.post(
        f"{gw_url}/v1/payment",
        headers={
            "x-api-key": gw_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=35,
    )
    if response.status_code in [200, 201]:
      return response.json()
    return {"error": "BANK_SERVER_BUSY"}
  except Exception:
    return {"error": "CONNECTION_TIMEOUT"}


def check_payment(payment_id, provider=None):
  settings = load_settings()
  gw_url = settings.get("gateway_url", "https://api.tolasaint.com")
  
  if not provider:
    provider = settings.get("active_provider", "bakong")
    
  gw_key = settings.get("aba_api_key" if provider == "aba" else "bakong_api_key", "")
  
  try:
    response = requests.get(
        f"{gw_url}/v1/payment/status",
        headers={"x-api-key": gw_key},
        params={"id": payment_id},
        timeout=25,
    )
    if response.status_code in [200, 201]:
      return response.json()
    return {"status": "pending"}
  except Exception:
    return {"status": "pending"}


def get_qr_photo(qr_string):
  if not qr_string:
    return None
  try:
    img = qrcode.make(qr_string).convert("RGB")
    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return output
  except Exception:
    return None


def append_and_get_sellstock(
    order_id: str,
    buyer_id: int,
    username: str,
    item_name: str,
    key: str,
    amount: float,
):
  current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  if not os.path.exists(SELL_STOCK_FILE):
    with open(SELL_STOCK_FILE, "w", encoding="utf-8") as f:
      f.write(
          "========================================================================================\n"
      )
      f.write(
          "                                📜 BOT SALES TRANSACTION"
          " HISTORY                        \n"
      )
      f.write(
          "========================================================================================\n"
      )
      f.write(
          f"{'DATE & TIME':<20} | {'ORDER ID':<16} | {'BUYER ID':<12} |"
          f" {'USERNAME':<15} | {'AMOUNT':<7} | {'ITEM':<25} | {'KEY'}\n"
      )
      f.write("-" * 120 + "\n")

  log_line = (
      f"{current_time:<20} | {order_id:<16} | {buyer_id:<12} | {username:<15} |"
      f" ${amount:<6.2f} | {item_name:<25} | {key}\n"
  )
  with open(SELL_STOCK_FILE, "a", encoding="utf-8") as f:
    f.write(log_line)

  with open(SELL_STOCK_FILE, "rb") as f:
    return f.read()


# ============================================================
# KEYBOARDS
# ============================================================

def get_main_reply_keyboard(user_id: int = None) -> ReplyKeyboardMarkup:
  builder = ReplyKeyboardBuilder()
  builder.row(
      KeyboardButton(
          text="BUY NOW",
          style="success",
          icon_custom_emoji_id="5773677501825945508",
      ),
      KeyboardButton(
          text="Key របស់ខ្ញុំ",
          style="success",
          icon_custom_emoji_id="6041730074376410123",
      ),
  )
  builder.row(
      KeyboardButton(
          text="AI Assistant",
          style="primary",
          icon_custom_emoji_id="6030722571412967168",
      )
  )
  if user_id and is_admin(user_id):
    builder.row(
        KeyboardButton(
            text="ADMIN PANEL",
            style="danger",
            icon_custom_emoji_id="5904258298764334001",
        )
    )
  return builder.as_markup(resize_keyboard=True)


def get_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
  builder = ReplyKeyboardBuilder()
  builder.row(
      KeyboardButton(
          text="ចេញ/បោះបង់ (Cancel QR)",
          style="danger",
          icon_custom_emoji_id="6039522349517115015",
      )
  )
  return builder.as_markup(resize_keyboard=True)


def get_inline_category_keyboard() -> InlineKeyboardMarkup:
  current_services, _ = load_data()
  builder = InlineKeyboardBuilder()
  for cat_key, cat_data in current_services.items():
    emoji_id = cat_data.get("emoji_id", "5805648413743651862")
    btn_text = cat_data.get("name", "Category")
    builder.row(
        InlineKeyboardButton(
            text=btn_text,
            callback_data=f"open_{cat_key}",
            style="primary",
            icon_custom_emoji_id=str(emoji_id),
        )
    )
  return builder.as_markup()


def get_duration_keyboard(cat_key: str, user_id: int) -> InlineKeyboardMarkup:
  current_services, resellers_list = load_data()
  stock_keys = load_stock()
  builder = InlineKeyboardBuilder()
  service = current_services.get(cat_key, {})
  is_reseller = user_id in resellers_list

  for plan_code, plan in service.get("plans", {}).items():
    price = plan["reseller_price"] if is_reseller else plan["price"]
    role_label = " (Reseller)" if is_reseller else ""
    stock_count = len(stock_keys.get(plan_code, []))

    att_info = plan.get("attachment")
    tag = ""
    if att_info:
      tag = " [File]" if att_info.get("type") == "file" else " [Link]"

    btn_text = f"{plan['name']} - ${price:.2f}{role_label}{tag} (សល់ {stock_count})"

    builder.row(
        InlineKeyboardButton(
            text=btn_text,
            callback_data=f"select|{cat_key}|{plan_code}",
            style="success",
            icon_custom_emoji_id="6039779802741739617",
        )
    )

  if service.get("guide_video"):
    builder.row(
        InlineKeyboardButton(
            text="មើលវីដេអូនែនាំ (Guide Video)",
            callback_data=f"view_cat_video|{cat_key}",
            style="primary",
            icon_custom_emoji_id="5944753741512052670",
        )
    )

  builder.row(
      InlineKeyboardButton(
          text="ថយក្រោយ",
          callback_data="back_to_categories",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  return builder.as_markup()


def get_confirmation_keyboard(
    cat_key: str, plan_code: str
) -> InlineKeyboardMarkup:
  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="បញ្ជាក់ការទិញ",
          callback_data=f"confirm|{cat_key}|{plan_code}",
          style="success",
          icon_custom_emoji_id="6039451237743595514",
      ),
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data=f"open_{cat_key}",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      ),
  )
  return builder.as_markup()


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
  settings = load_settings()
  is_maint = settings.get("maintenance_mode", False)
  maint_text = "Maintenance: [ON 🔴]" if is_maint else "Maintenance: [OFF 🟢]"

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="📖 How To Use Admin Panel",
          callback_data="admin_how_to_use",
          style="primary",
          icon_custom_emoji_id="5944753741512052670",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="របាយការណ៍លក់ (Balance)",
          callback_data="admin_view_balance",
          style="success",
          icon_custom_emoji_id="6039779802741739617",
      ),
      InlineKeyboardButton(
          text="ស្ថិតិ Users (Statistics)",
          callback_data="admin_view_user_stats",
          style="primary",
          icon_custom_emoji_id="6033108709213736873",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text="🔍 Check Order ID",
          callback_data="admin_check_order_start",
          style="success",
          icon_custom_emoji_id="6039404727542747508",
      ),
      InlineKeyboardButton(
          text="📜 Admin Activity Audit",
          callback_data="admin_view_audit_logs",
          style="primary",
          icon_custom_emoji_id="5805648413743651862",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text="💳 Settings Payment",
          callback_data="admin_payment_settings_menu",
          style="primary",
          icon_custom_emoji_id="6075534731171079238",
      ),
      InlineKeyboardButton(
          text="Telegram Log Group",
          callback_data="admin_set_log_group",
          style="primary",
          icon_custom_emoji_id="6034831751308644168",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text=maint_text,
          callback_data="admin_toggle_maintenance",
          style="danger" if is_maint else "primary",
          icon_custom_emoji_id="6039522349517115015",
      ),
      InlineKeyboardButton(
          text="Bot Content (Welcome)",
          callback_data="admin_edit_welcome_menu",
          style="primary",
          icon_custom_emoji_id="6039404727542747508",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text="Categories & Plans",
          callback_data="admin_manage_categories",
          style="primary",
          icon_custom_emoji_id="6042137469204303531",
      ),
      InlineKeyboardButton(
          text="File Manager",
          callback_data="admin_manage_files_menu",
          style="success",
          icon_custom_emoji_id="5805648413743651862",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text="Add Key",
          callback_data="admin_add_key_menu",
          style="primary",
          icon_custom_emoji_id="5773677501825945508",
      ),
      InlineKeyboardButton(
          text="Clear Stock",
          callback_data="admin_clear_stock_menu",
          style="danger",
          icon_custom_emoji_id="6039522349517115015",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text="Check Stock",
          callback_data="admin_check_stock",
          style="primary",
          icon_custom_emoji_id="5884479287171485878",
      ),
      InlineKeyboardButton(
          text="Broadcast",
          callback_data="admin_broadcast_prompt",
          style="primary",
          icon_custom_emoji_id="6039381989985882045",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text="Export Log",
          callback_data="admin_export_sell_log",
          style="primary",
          icon_custom_emoji_id="6035130900075777681",
      ),
      InlineKeyboardButton(
          text="Admin IDs (Permin)",
          callback_data="admin_manage_perms",
          style="primary",
          icon_custom_emoji_id="6033108709213736873",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text="តម្លៃទូទៅ",
          callback_data="admin_price_menu_normal",
          style="primary",
          icon_custom_emoji_id="5938539885907415367",
      ),
      InlineKeyboardButton(
          text="តម្លៃ Reseller",
          callback_data="admin_price_menu_reseller",
          style="primary",
          icon_custom_emoji_id="5938539885907415367",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text="Add Reseller",
          callback_data="admin_add_reseller",
          style="primary",
          icon_custom_emoji_id="6033108709213736873",
      ),
      InlineKeyboardButton(
          text="Del Reseller",
          callback_data="admin_remove_reseller",
          style="danger",
          icon_custom_emoji_id="5891207662678317861",
      ),
  )
  return builder.as_markup()


def get_admin_plans_keyboard(action_prefix: str) -> InlineKeyboardMarkup:
  current_services, _ = load_data()
  builder = InlineKeyboardBuilder()
  for cat_key, service in current_services.items():
    for plan_code, plan in service.get("plans", {}).items():
      builder.row(
          InlineKeyboardButton(
              text=f"{service['name']} - {plan['name']}",
              callback_data=f"{action_prefix}|{plan_code}",
              style="primary",
          )
      )
  builder.row(
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_back_main",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  return builder.as_markup()


# ============================================================
# HOW TO USE ADMIN PANEL HANDLER
# ============================================================

@dp.callback_query(F.data == "admin_how_to_use")
async def admin_how_to_use_handler(callback: CallbackQuery):
  await callback.answer()

  guide_text = (
      '<tg-emoji emoji-id="5944753741512052670">📖</tg-emoji> <b>សៀវភៅណែនាំការប្រើប្រាស់ ADMIN PANEL</b>\n'
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
      '<tg-emoji emoji-id="6075534731171079238">💳</tg-emoji> <b>Settings Payment ៖</b>\n'
      "• ជ្រើសរើសផ្លាស់ប្តូរការទូទាត់រវាង <b>ABA</b> ឬ <b>Bakong</b> និងកំណត់ API Key ដោយមិនបាច់កែកូដ។\n\n"
      '<tg-emoji emoji-id="6039779802741739617">💵</tg-emoji> <b>របាយការណ៍លក់ (Balance) ៖</b>\n'
      "• ពិនិត្យមើលចំណូលសរុប ចំណូលប្រចាំខែ កំណើននៃការលក់ និងប្រតិបត្តិការចុងក្រោយ។\n\n"
      '<tg-emoji emoji-id="6033108709213736873">👥</tg-emoji> <b>ស្ថិតិ Users (Statistics) ៖</b>\n'
      "• ពិនិត្យមើលចំនួន Users សរុប អ្នកធ្លាប់ទិញ និង Top Buyers ដែលចំណាយច្រើនជាងគេ។\n\n"
      '<tg-emoji emoji-id="6039404727542747508">🔍</tg-emoji> <b>Check Order ID ៖</b>\n'
      "• វាយបញ្ចូលលេខវិក្កយបត្រ (Order ID) ដើម្បីឆែកមើលថាជារបស់ User ណា ទិញថ្ងៃណា និងបាន Key/File អ្វីខ្លះ។\n\n"
      '<tg-emoji emoji-id="5805648413743651862">📜</tg-emoji> <b>Admin Activity Audit ៖</b>\n'
      "• កត់ត្រារាល់សកម្មភាពដែល Admin នីមួយៗបានធ្វើ (ប្តូរតម្លៃ, បន្ថែម Key, បង្កើត Plan...)។\n\n"
      '<tg-emoji emoji-id="6034831751308644168">📢</tg-emoji> <b>Telegram Log Group ៖</b>\n'
      "• ភ្ជាប់ Telegram Group សម្រាប់ឱ្យ Bot ផ្ញើវិក្កយបត្រ និង Notification ស្វ័យប្រវត្តពេលមានគេទិញរួច។\n\n"
      '<tg-emoji emoji-id="6039522349517115015">🛠</tg-emoji> <b>Maintenance Mode ៖</b>\n'
      "• បើក/បិទ ការជួសជុល Bot (ពេលបើក មានតែ Admin ទេដែលអាចប្រើ Bot បាន)។\n\n"
      '<tg-emoji emoji-id="6042137469204303531">🗂</tg-emoji> <b>Categories & Plans ៖</b>\n'
      "• បង្កើត Category, បន្ថែម Plan (ដាក់ Video Guide, File/Link អមជាមួយ Stock Key) និងលុបទំនិញ។\n\n"
      '<tg-emoji emoji-id="5805648413743651862">📁</tg-emoji> <b>File Manager ៖</b>\n'
      "• ពិនិត្យមើល និងផ្លាស់ប្តូរឯកសារ File សម្រាប់ Plans ដែលមានភ្ជាប់ File Attachment។\n\n"
      '<tg-emoji emoji-id="5773677501825945508">🔑</tg-emoji> <b>Add Key / Clear Stock / Check Stock ៖</b>\n'
      "• បញ្ចូល License Key ថ្មីចូលស្តុក, មើលចំនួនស្តុកដែលនៅសល់ ឬលុប Key ចាស់ៗចោល។\n\n"
      '<tg-emoji emoji-id="6039381989985882045">📢</tg-emoji> <b>Broadcast ៖</b>\n'
      "• ផ្ញើសារ រូបភាព ឬប្រូម៉ូសិន ទៅកាន់ Users ទាំងអស់ដែលធ្លាប់ Start Bot។\n\n"
      '<tg-emoji emoji-id="5938539885907415367">💵</tg-emoji> <b>តម្លៃទូទៅ / តម្លៃ Reseller ៖</b>\n'
      "• កែប្រែតម្លៃលក់រាយ និងតម្លៃពិសេសសម្រាប់សមាជិក Reseller។\n\n"
      '<tg-emoji emoji-id="6033108709213736873">💎</tg-emoji> <b>Add / Del Reseller ៖</b>\n'
      "• បន្ថែម ឬដកសិទ្ធិ User ID ឱ្យទទួលបានតម្លៃពិសេស (Reseller Discount)។\n\n"
      '<tg-emoji emoji-id="5904258298764334001">👑</tg-emoji> <b>Admin IDs (Permin) ៖</b>\n'
      "• បន្ថែម Admin ថ្មី ឬដកសិទ្ធិ Admin ចេញពី Bot។\n"
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  )

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_back_main",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )

  await safe_edit_text(
      callback.message, guide_text, reply_markup=builder.as_markup()
  )


# ============================================================
# ASYNC PAYMENT CHECKER (AUTO KEY FROM STOCK + FILE/VIDEO)
# ============================================================

async def cleanup_existing_payment(chat_id: int):
  pay = active_payment.pop(chat_id, None)
  if pay:
    active_payments_global.pop(pay.get("payment_id"), None)
    try:
      await bot.delete_message(chat_id=chat_id, message_id=pay["message_id"])
    except Exception:
      pass


async def check_payment_async(
    chat_id: int,
    payment_id: str,
    item_name: str,
    plan_code: str,
    cat_key: str = "",
    provider: str = "bakong",
):
  max_checks = 60
  for _ in range(max_checks):
    await asyncio.sleep(3)
    payment = active_payment.get(chat_id)
    if not payment or payment.get("payment_id") != payment_id:
      return

    try:
      data = await asyncio.to_thread(check_payment, payment_id, provider)
      status = str(data.get("status", "")).lower()

      if status in ["paid", "approved", "success"]:
        pay = active_payment.pop(chat_id, None)
        active_payments_global.pop(payment_id, None)
        if not pay:
          return

        try:
          await bot.delete_message(
              chat_id=chat_id, message_id=pay["message_id"]
          )
        except Exception:
          pass

        buyer_username = (
            f"@{pay.get('username')}" if pay.get("username") else "Unknown"
        )
        amount_paid = float(pay.get("amount", 0.0))

        current_services, _ = load_data()
        cat_info = current_services.get(cat_key, {})
        plan_info = cat_info.get("plans", {}).get(plan_code, {})
        att_info = plan_info.get("attachment")
        guide_video = plan_info.get("guide_video") or cat_info.get(
            "guide_video"
        )

        license_key = ""
        remaining_stock = 0

        # Always pull Key from Stock
        async with stock_lock:
          stock_keys = load_stock()
          if stock_keys.get(plan_code) and len(stock_keys[plan_code]) > 0:
            license_key = stock_keys[plan_code].pop(0)
            save_stock(stock_keys)
            remaining_stock = len(stock_keys[plan_code])

        if not license_key:
          license_key = "Key អស់ពីស្តុក! សូមទាក់ទង Admin។"

        delivered_content = license_key
        if att_info:
          if att_info.get("type") == "file":
            delivered_content += f" | File: {att_info.get('file_name')}"
          elif att_info.get("type") == "link":
            delivered_content += f" | Link: {att_info.get('link_text')}"

        save_user_history(
            chat_id,
            payment_id,
            item_name,
            delivered_content,
            "Video Guide Attached" if guide_video else "None",
            amount_paid,
        )
        record_sales_ledger(
            payment_id,
            chat_id,
            buyer_username,
            item_name,
            amount_paid,
        )

        # Message with License Key
        success_text = (
            '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji>'
            " <b>ការបង់ប្រាក់ជោគជ័យ</b>\n\n"
            f'<tg-emoji emoji-id="5773677501825945508">🔑</tg-emoji> <b>License Key :</b> <code>{license_key}</code>\n'
            f'<tg-emoji emoji-id="5904258298764334001">🆔</tg-emoji> <b>Order ID :</b> <code>{payment_id}</code>\n'
            f'<tg-emoji emoji-id="6041730074376410123">📦</tg-emoji> <b>ទំនិញ :</b> {item_name}\n\n'
        )

        if att_info and att_info.get("type") == "link":
          success_text += (
              f'<tg-emoji emoji-id="6039404727542747508">🔗</tg-emoji> <b>Link Download/Install :</b>\n<code>{att_info.get("link_text")}</code>\n\n'
          )

        success_text += "<i>សូមអរគុណសម្រាប់ការគាំទ្រ!</i>"

        await bot.send_message(
            chat_id=chat_id,
            text=success_text,
            reply_markup=get_main_reply_keyboard(chat_id),
        )

        # Auto Send File Attachment (if any)
        if att_info and att_info.get("type") == "file":
          f_id = att_info.get("file_id")
          f_name = att_info.get("file_name", "File Attachment")
          if f_id:
            try:
              await bot.send_document(
                  chat_id=chat_id,
                  document=f_id,
                  caption=(
                      f'<tg-emoji emoji-id="5805648413743651862">📁</tg-emoji> <b>{f_name}</b>\n\n'
                      f'🔑 <b>License Key របស់អ្នក :</b> <code>{license_key}</code>\n'
                      '👉 <i>សូមដំឡើង File នេះ រួចយក License Key ខាងលើទៅ activate ប្រើប្រាស់។</i>'
                  ),
              )
            except Exception as e:
              logging.error(f"Error sending file: {e}")

        # Auto Send Guide Video (if any)
        if guide_video:
          try:
            await bot.send_video(
                chat_id=chat_id,
                video=guide_video,
                caption=(
                    '<tg-emoji emoji-id="5944753741512052670">🎥</tg-emoji>'
                    f" <b>វីដេអូនែនាំពីរបៀបដំឡើង និង Activate Key ({item_name})</b>"
                ),
            )
          except Exception:
            pass

        # Low Stock Alert
        if remaining_stock <= LOW_STOCK_THRESHOLD:
          alert_status = (
              "អស់ពីស្តុកហើយ"
              if remaining_stock == 0
              else "ជិតអស់ពីស្តុកហើយ"
          )
          admin_alert_text = (
              '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji>'
              f" <b>[ការជូនដំណឹងពីស្តុក - {alert_status}]</b>\n\n"
              '<tg-emoji emoji-id="6041730074376410123">📦</tg-emoji>'
              f" <b>កញ្ចប់ទំនិញ :</b> {item_name}\n"
              '<tg-emoji emoji-id="5773677501825945508">🔑</tg-emoji> <b>Plan'
              f" Code :</b> <code>{plan_code}</code>\n"
              '<tg-emoji emoji-id="5938539885907415367">📊</tg-emoji>'
              " <b>ស្តុក Key នៅសល់បច្ចុប្បន្ន :</b>"
              f" <b>{remaining_stock} Key</b>"
          )
          settings = load_settings()
          for aid in settings.get("admin_ids", [INITIAL_ADMIN_ID]):
            try:
              await bot.send_message(chat_id=aid, text=admin_alert_text)
            except Exception:
              pass

        # Send Log to Group
        try:
          file_bytes = await asyncio.to_thread(
              append_and_get_sellstock,
              payment_id,
              chat_id,
              buyer_username,
              item_name,
              delivered_content,
              amount_paid,
          )
          txt_file = BufferedInputFile(file_bytes, filename="sellstock.txt")
          group_caption = (
              '<tg-emoji emoji-id="6039779802741739617">🛍</tg-emoji> <b>[NEW'
              " SALE COMPLETED]</b>\n\n"
              f'<tg-emoji emoji-id="5904258298764334001">🆔</tg-emoji> <b>Order'
              f" ID :</b> <code>{payment_id}</code>\n"
              f'<tg-emoji emoji-id="6033108709213736873">👤</tg-emoji> <b>អ្នកទិញ'
              f" :</b> <code>{chat_id}</code> ({buyer_username})\n"
              f'<tg-emoji emoji-id="6041730074376410123">📦</tg-emoji> <b>ទំនិញ'
              f" :</b> {item_name}\n"
              '<tg-emoji emoji-id="5938539885907415367">💵</tg-emoji> <b>តម្លៃ'
              f" :</b> <b>${amount_paid:.2f}</b>\n"
              f'<tg-emoji emoji-id="5773677501825945508">🔑</tg-emoji>'
              f" <b>Delivery :</b> <code>{delivered_content}</code>"
          )
          target_group = load_settings().get(
              "log_group_id", -1001234567890
          )
          await bot.send_document(
              chat_id=target_group,
              document=txt_file,
              caption=group_caption,
          )
        except Exception:
          pass

        return

      if status in ["expired", "failed", "cancelled"]:
        pay = active_payment.pop(chat_id, None)
        active_payments_global.pop(payment_id, None)
        if pay:
          try:
            await bot.delete_message(
                chat_id=chat_id, message_id=pay["message_id"]
            )
          except Exception:
            pass
        await bot.send_message(
            chat_id=chat_id,
            text=(
                '<tg-emoji emoji-id="6039522349517115015">❌</tg-emoji>'
                " <b>ការបង់ប្រាក់ត្រូវបានបរាជ័យ ឬផុតកំណត់។</b>"
            ),
            reply_markup=get_main_reply_keyboard(chat_id),
        )
        return

    except Exception:
      pass

  pay = active_payment.pop(chat_id, None)
  active_payments_global.pop(payment_id, None)
  if pay:
    try:
      await bot.delete_message(chat_id=chat_id, message_id=pay["message_id"])
    except Exception:
      pass
    await bot.send_message(
        chat_id=chat_id,
        text=(
            '<tg-emoji emoji-id="6039522349517115015">⏰</tg-emoji> <b>QR'
            " Payment បានផុតកំណត់។</b>"
        ),
        reply_markup=get_main_reply_keyboard(chat_id),
    )


# ============================================================
# ORDER LOOKUP & VERIFICATION HANDLER
# ============================================================

@dp.callback_query(F.data == "admin_check_order_start")
async def admin_check_order_start_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  await state.set_state(AdminState.waiting_for_order_lookup)

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="បោះបង់",
          callback_data="admin_back_main",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )

  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6039404727542747508">🔍</tg-emoji> <b>ស្វែងរក និងផ្ទៀងផ្ទាត់វិក្កយបត្រ (Order Lookup)</b>\n\n'
      "👉 សូមផ្ញើ <b>Order ID</b> (ឧទាហរណ៍៖ <code>100234</code>)៖",
      reply_markup=builder.as_markup(),
  )


@dp.message(AdminState.waiting_for_order_lookup)
async def process_order_lookup_input(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return

  target_order_id = message.text.strip()
  await state.clear()

  found_order = None
  buyer_id = "N/A"
  buyer_username = "N/A"

  if os.path.exists(SALES_LEDGER_FILE):
    try:
      with open(SALES_LEDGER_FILE, "r", encoding="utf-8") as f:
        sales = json.load(f)
        for tx in sales:
          if (
              tx.get("order_id", "").lower() == target_order_id.lower()
              or target_order_id.lower() in tx.get("order_id", "").lower()
          ):
            found_order = tx
            buyer_id = str(tx.get("buyer_id"))
            buyer_username = tx.get("username", "Unknown")
            break
    except Exception:
      pass

  key_delivered = "N/A"
  date_purchased = "N/A"

  if os.path.exists(USER_HISTORY_FILE):
    try:
      with open(USER_HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
        for uid, orders in history.items():
          for o in orders:
            if (
                o.get("order_id", "").lower() == target_order_id.lower()
                or target_order_id.lower() in o.get("order_id", "").lower()
            ):
              key_delivered = o.get("key", "N/A")
              date_purchased = o.get("date", "N/A")
              buyer_id = uid
              if not found_order:
                found_order = o
              break
    except Exception:
      pass

  if not found_order:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="សាកល្បងម្ដងទៀត",
            callback_data="admin_check_order_start",
            style="primary",
            icon_custom_emoji_id="6039404727542747508",
        ),
        InlineKeyboardButton(
            text="ត្រឡប់ក្រោយ",
            callback_data="admin_back_main",
            style="danger",
            icon_custom_emoji_id="6035130900075777681",
        ),
    )
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> <b>រកមិនឃើញព័ត៌មាននៃ Order ID: <code>'
        + target_order_id
        + "</code> នេះទេ!</b>",
        reply_markup=builder.as_markup(),
    )
    return

  amount = found_order.get("amount", 0.0)
  item_name = found_order.get("item_name", "N/A")
  order_full_id = found_order.get("order_id", target_order_id)
  timestamp = (
      found_order.get("timestamp")
      or date_purchased
      or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  )

  text = (
      '<tg-emoji emoji-id="6039451237743595514">🧾</tg-emoji> <b>ព័ត៌មានលម្អិតនៃវិក្កយបត្រ (ORDER VERIFIED)</b>\n'
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      f'<tg-emoji emoji-id="5904258298764334001">🆔</tg-emoji> <b>Order ID :</b> <code>{order_full_id}</code>\n'
      f'<tg-emoji emoji-id="6033108709213736873">👤</tg-emoji> <b>អ្នកទិញ :</b> <code>{buyer_id}</code> ({buyer_username})\n'
      f'<tg-emoji emoji-id="6041730074376410123">📦</tg-emoji> <b>មុខទំនិញ :</b> {item_name}\n'
      f'<tg-emoji emoji-id="5938539885907415367">💵</tg-emoji> <b>ចំនួនទឹកប្រាក់ :</b> <b>${float(amount):.2f}</b>\n'
      f'<tg-emoji emoji-id="6039404727542747508">📅</tg-emoji> <b>កាលបរិច្ឆេទ :</b> {timestamp}\n'
      f'<tg-emoji emoji-id="5773677501825945508">🔑</tg-emoji> <b>Key / Content Delivered :</b>\n<code>{key_delivered}</code>\n'
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  )

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="🔍 ឆែក Order ផ្សេងទៀត",
          callback_data="admin_check_order_start",
          style="primary",
          icon_custom_emoji_id="6039404727542747508",
      ),
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_back_main",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      ),
  )

  await message.answer(text, reply_markup=builder.as_markup())


# ============================================================
# AUDIT LOG VIEWER HANDLER
# ============================================================

@dp.callback_query(F.data == "admin_view_audit_logs")
async def admin_view_audit_logs_handler(callback: CallbackQuery):
  await callback.answer()

  logs = []
  if os.path.exists(AUDIT_LOG_FILE):
    try:
      with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
        logs = json.load(f)
    except Exception:
      logs = []

  text = (
      '<tg-emoji emoji-id="5805648413743651862">📜</tg-emoji> <b>កំណត់ត្រាសកម្មភាព'
      " ADMIN (AUDIT LOGS)</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
  )

  if not logs:
    text += "<i>(មិនទាន់មានសកម្មភាពត្រូវបានកត់ត្រានៅឡើយទេ)</i>\n"
  else:
    for idx, item in enumerate(reversed(logs[-8:]), start=1):
      text += (
          f"<b>{idx}. {item['action']}</b>\n"
          f"   • ដោយ: <b>{item['admin_name']}</b> (<code>{item['admin_id']}</code>)\n"
          f"   • លម្អិត: {item['details']}\n"
          f"   • ម៉ោង: <code>{item['timestamp']}</code>\n\n"
      )

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="Refresh",
          callback_data="admin_view_audit_logs",
          style="success",
          icon_custom_emoji_id="6039451237743595514",
      ),
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_back_main",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      ),
  )
  await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


# ============================================================
# USER STATISTICS HANDLER
# ============================================================

@dp.callback_query(F.data == "admin_view_user_stats")
async def admin_view_user_stats_handler(callback: CallbackQuery):
  await callback.answer()
  stats = get_detailed_user_statistics()

  text = (
      '<tg-emoji emoji-id="6033108709213736873">👥</tg-emoji> <b>ស្ថិតិអ្នកប្រើប្រាស់ (USER'
      " STATISTICS)</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      f'<tg-emoji emoji-id="6033108709213736873">👤</tg-emoji> <b>Users'
      f" ចុះឈ្មោះសរុប :</b> <b>{stats['total_users']} នាក់</b>\n"
      f'<tg-emoji emoji-id="6041730074376410123">🛍</tg-emoji> <b>Users'
      f" ធ្លាប់បានទិញ :</b> <b>{stats['total_buyers']} នាក់</b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      '<tg-emoji emoji-id="5938539885907415367">🏆</tg-emoji> <b>TOP BUYERS'
      " (អ្នកទិញច្រើនជាងគេ) :</b>\n\n"
  )

  if not stats["top_buyers"]:
    text += "<i>(មិនទាន់មានទិន្នន័យអ្នកទិញនៅឡើយទេ)</i>\n"
  else:
    for idx, (uid, bdata) in enumerate(stats["top_buyers"], start=1):
      text += (
          f"<b>{idx}. {bdata['username']}</b> (<code>{uid}</code>)\n"
          f"   • ទិញ: <b>{bdata['orders']} ដង</b> | ចំណាយ:"
          f" <b>${bdata['total_spent']:.2f}</b>\n"
      )

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="Refresh",
          callback_data="admin_view_user_stats",
          style="success",
          icon_custom_emoji_id="6039451237743595514",
      ),
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_back_main",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      ),
  )
  await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


# ============================================================
# TELEGRAM LOG GROUP LINKING
# ============================================================

@dp.callback_query(F.data == "admin_set_log_group")
async def admin_set_log_group_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  settings = load_settings()
  current_group = settings.get("log_group_id", "Not set")

  text = (
      '<tg-emoji emoji-id="6034831751308644168">📢</tg-emoji> <b>ការភ្ជាប់'
      " TELEGRAM LOG GROUP</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      f'<tg-emoji emoji-id="5904258298764334001">🆔</tg-emoji> <b>Log Group ID'
      f" បច្ចុប្បន្ន :</b> <code>{current_group}</code>\n\n"
      "👉 <i>សូមចុចប៊ូតុងខាងក្រោមដើម្បីផ្លាស់ប្តូរ ID Group ថ្មី៖</i>"
  )
  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="ប្តូរ Group ID",
          callback_data="admin_input_group_id",
          style="primary",
          icon_custom_emoji_id="6039404727542747508",
      ),
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_back_main",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      ),
  )
  await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


@dp.callback_query(F.data == "admin_input_group_id")
async def admin_input_group_id_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  await state.set_state(AdminState.waiting_for_log_group_id)
  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="បោះបង់",
          callback_data="admin_set_log_group",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6034831751308644168">✍️</tg-emoji> <b>សូមផ្ញើ Telegram'
      " Group ID ថ្មី (ឧទាហរណ៍៖ <code>-1001234567890</code>)៖</b>\n\n💡"
      " <i>កុំភ្លេច Add Bot ចូលក្នុង Group នោះ និងផ្ដល់សិទ្ធិជា Admin ផង!</i>",
      reply_markup=builder.as_markup(),
  )


@dp.message(AdminState.waiting_for_log_group_id)
async def process_log_group_id_save(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  try:
    gid = int(message.text.strip())
    settings = load_settings()
    settings["log_group_id"] = gid
    save_settings(settings)

    log_admin_action(
        message.from_user.id,
        message.from_user.full_name,
        "Update Log Group",
        f"ប្តូរ Group ID ទៅជា: {gid}",
    )

    await state.clear()
    await message.answer(
        '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> <b>បានភ្ជាប់'
        f" Telegram Log Group ID: <code>{gid}</code> ជោគជ័យ!</b>",
        reply_markup=get_admin_main_keyboard(),
    )
  except ValueError:
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> សូមបញ្ចូលលេខ'
        " Group ID ឱ្យបានត្រឹមត្រូវ!"
    )


# ============================================================
# SETTINGS PAYMENT (ABA & BAKONG SWITCHER & CONFIG)
# ============================================================

@dp.callback_query(F.data == "admin_payment_settings_menu")
async def admin_payment_settings_menu_handler(callback: CallbackQuery, state: FSMContext):
  await state.clear()
  await callback.answer()
  settings = load_settings()
  active_p = settings.get("active_provider", "bakong")
  gw_url = settings.get("gateway_url", "https://api.tolasaint.com")
  
  aba_key = settings.get("aba_api_key", "Not Set")
  bakong_key = settings.get("bakong_api_key", "Not Set")

  aba_badge = " [✅ កំពុងប្រើ]" if active_p == "aba" else ""
  bakong_badge = " [✅ កំពុងប្រើ]" if active_p == "bakong" else ""

  text = (
      '<tg-emoji emoji-id="6075534731171079238">💳</tg-emoji> <b>ផ្ទាំងគ្រប់គ្រងការទូទាត់ (SETTINGS PAYMENT)</b>\n'
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      f'<tg-emoji emoji-id="6039451237743595514">⚡️</tg-emoji> <b>Active Gateway បច្ចុប្បន្ន :</b> <b>{active_p.upper()}</b>\n'
      f'<tg-emoji emoji-id="6039404727542747508">🌐</tg-emoji> <b>Base Gateway URL :</b> <code>{gw_url}</code>\n\n'
      f"🏦 <b>ABA PayWay Status :</b> {aba_badge}\n"
      f"   • API Key: <code>{aba_key[:6]}...{aba_key[-4:] if len(aba_key) > 10 else ''}</code>\n\n"
      f"🔴 <b>Bakong KHQR Status :</b> {bakong_badge}\n"
      f"   • API Key: <code>{bakong_key[:6]}...{bakong_key[-4:] if len(bakong_key) > 10 else ''}</code>\n"
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      "👉 <i>សូមជ្រើសរើសធនាគារដែលលោកអ្នកចង់ផ្លាស់ប្តូរ ឬកំណត់ API Key ៖</i>"
  )

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text=f"🏦 ABA PayWay{aba_badge}",
          callback_data="admin_config_provider|aba",
          style="primary",
          icon_custom_emoji_id="6075534731171079238",
      ),
      InlineKeyboardButton(
          text=f"🔴 Bakong KHQR{bakong_badge}",
          callback_data="admin_config_provider|bakong",
          style="primary",
          icon_custom_emoji_id="6039779802741739617",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text="🌐 កែប្រែ Gateway URL",
          callback_data="admin_set_gw_url",
          style="primary",
          icon_custom_emoji_id="6039404727542747508",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_back_main",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )

  await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("admin_config_provider|"))
async def admin_config_provider_handler(callback: CallbackQuery):
  await callback.answer()
  provider = callback.data.split("|")[1]
  settings = load_settings()
  active_p = settings.get("active_provider", "bakong")
  is_active = (active_p == provider)

  key_field = f"{provider}_api_key"
  current_key = settings.get(key_field, "Not set")
  p_name = "ABA PayWay" if provider == "aba" else "Bakong KHQR"

  text = (
      f'<tg-emoji emoji-id="6075534731171079238">⚙️</tg-emoji> <b>ការកំណត់ {p_name.upper()}</b>\n'
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      f"• <b>ស្ថានភាព :</b> {'🟢 កំពុងដំណើរការ (Active)' if is_active else '⚪️ អសកម្ម (Inactive)'}\n"
      f"• <b>API Key បច្ចុប្បន្ន :</b> <code>{current_key}</code>\n"
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      "👉 <i>លោកអ្នកអាចកំណត់យកវាជា Gateway ចម្បង ឬផ្លាស់ប្តូរ API Key៖</i>"
  )

  builder = InlineKeyboardBuilder()
  if not is_active:
    builder.row(
        InlineKeyboardButton(
            text=f"✅ ជ្រើសរើសយក {p_name} សម្រាប់ Bot",
            callback_data=f"admin_set_active_provider|{provider}",
            style="success",
            icon_custom_emoji_id="6039451237743595514",
        )
    )
  builder.row(
      InlineKeyboardButton(
          text=f"🔑 ប្តូរ API Key របស់ {provider.upper()}",
          callback_data=f"admin_input_prov_key|{provider}",
          style="primary",
          icon_custom_emoji_id="5773677501825945508",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_payment_settings_menu",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )

  await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("admin_set_active_provider|"))
async def admin_set_active_provider_handler(callback: CallbackQuery):
  provider = callback.data.split("|")[1]
  settings = load_settings()
  settings["active_provider"] = provider
  save_settings(settings)

  p_name = "ABA PayWay" if provider == "aba" else "Bakong KHQR"
  log_admin_action(
      callback.from_user.id,
      callback.from_user.full_name,
      "Switch Payment Provider",
      f"បានប្តូរទៅប្រើ: {p_name}",
  )

  await callback.answer(f"បានជ្រើសរើស {p_name} ជោគជ័យ!", show_alert=True)
  await admin_config_provider_handler(callback)


@dp.callback_query(F.data.startswith("admin_input_prov_key|"))
async def admin_input_prov_key_handler(callback: CallbackQuery, state: FSMContext):
  await callback.answer()
  provider = callback.data.split("|")[1]
  await state.update_data(target_provider=provider)
  await state.set_state(AdminState.waiting_for_provider_key)

  p_name = "ABA PayWay" if provider == "aba" else "Bakong KHQR"
  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="បោះបង់",
          callback_data=f"admin_config_provider|{provider}",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )

  await safe_edit_text(
      callback.message,
      f'<tg-emoji emoji-id="5773677501825945508">🔑</tg-emoji> <b>សូមផ្ញើ API Secret Key ថ្មីសម្រាប់ {p_name} មកទីនេះ៖</b>',
      reply_markup=builder.as_markup(),
  )


@dp.message(AdminState.waiting_for_provider_key)
async def process_provider_key_save(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  data = await state.get_data()
  provider = data.get("target_provider", "bakong")
  key_val = message.text.strip()

  settings = load_settings()
  settings[f"{provider}_api_key"] = key_val
  save_settings(settings)

  p_name = "ABA" if provider == "aba" else "Bakong"
  log_admin_action(
      message.from_user.id,
      message.from_user.full_name,
      f"Update {p_name} Key",
      f"បានប្តូរ API Key របស់ {p_name}",
  )

  await state.clear()
  await message.answer(
      f'<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> <b>បានរក្សាទុក API Key របស់ {p_name} ជោគជ័យ!</b>',
      reply_markup=get_admin_main_keyboard(),
  )


@dp.callback_query(F.data == "admin_set_gw_url")
async def admin_set_gw_url_handler(callback: CallbackQuery, state: FSMContext):
  await callback.answer()
  await state.set_state(AdminState.waiting_for_gateway_url)
  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="បោះបង់",
          callback_data="admin_payment_settings_menu",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6039404727542747508">🌐</tg-emoji> <b>សូមបញ្ចូល Base URL ថ្មី (ឧ. <code>https://api.tolasaint.com</code>)៖</b>',
      reply_markup=builder.as_markup(),
  )


@dp.message(AdminState.waiting_for_gateway_url)
async def process_gw_url_save(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  url = message.text.strip().rstrip("/")
  settings = load_settings()
  settings["gateway_url"] = url
  save_settings(settings)

  log_admin_action(
      message.from_user.id,
      message.from_user.full_name,
      "Update Gateway URL",
      f"កំណត់ URL: {url}",
  )

  await state.clear()
  await message.answer(
      '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> <b>បានផ្លាស់ប្តូរ Gateway URL: <code>'
      + url
      + "</code> ជោគជ័យ!</b>",
      reply_markup=get_admin_main_keyboard(),
  )


# ============================================================
# BOT CONTENT & MAINTENANCE TOGGLE
# ============================================================

@dp.callback_query(F.data == "admin_toggle_maintenance")
async def admin_toggle_maintenance_handler(callback: CallbackQuery):
  settings = load_settings()
  current_status = settings.get("maintenance_mode", False)
  settings["maintenance_mode"] = not current_status
  save_settings(settings)

  status_str = "បើក (ON)" if settings["maintenance_mode"] else "បិទ (OFF)"

  log_admin_action(
      callback.from_user.id,
      callback.from_user.full_name,
      "Toggle Maintenance",
      f"បានប្តូរ Maintenance Mode ទៅជា: {status_str}",
  )

  await callback.answer(f"Maintenance Mode: {status_str}", show_alert=True)
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="5904258298764334001">👑</tg-emoji> <b>ផ្ទាំងគ្រប់គ្រង'
      " ADMIN PANEL</b>",
      reply_markup=get_admin_main_keyboard(),
  )


@dp.callback_query(F.data == "admin_edit_welcome_menu")
async def admin_edit_welcome_menu_handler(callback: CallbackQuery):
  await callback.answer()
  settings = load_settings()
  text = (
      '<tg-emoji emoji-id="6039404727542747508">⚙️</tg-emoji> <b>ការកំណត់ BOT'
      " CONTENT & WELCOME</b>\n\n"
      f'<tg-emoji emoji-id="5904258298764334001">🏷</tg-emoji> <b>ឈ្មោះ Bot :</b>'
      f' <code>{settings.get("bot_name", "N/A")}</code>\n'
      '<tg-emoji emoji-id="6034831751308644168">💬</tg-emoji> <b>សារ Welcome'
      f' បច្ចុប្បន្ន :</b>\n"{settings.get("welcome_text", "N/A")}"\n\n'
      "👉 <i>សូមជ្រើសរើសផ្នែកដែលអ្នកចង់កែប្រែ៖</i>"
  )
  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="កែប្រែឈ្មោះ Bot",
          callback_data="admin_set_bot_name",
          style="primary",
          icon_custom_emoji_id="6039404727542747508",
      ),
      InlineKeyboardButton(
          text="កែប្រែសារ Welcome",
          callback_data="admin_set_welcome_text",
          style="primary",
          icon_custom_emoji_id="6034831751308644168",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_back_main",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


@dp.callback_query(F.data == "admin_set_bot_name")
async def admin_set_bot_name_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  await state.set_state(AdminState.waiting_for_bot_name)
  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="បោះបង់",
          callback_data="admin_edit_welcome_menu",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6039404727542747508">✍️</tg-emoji> <b>សូមបញ្ចូលឈ្មោះ'
      " Bot ថ្មី៖</b>",
      reply_markup=builder.as_markup(),
  )


@dp.message(AdminState.waiting_for_bot_name)
async def process_bot_name_update(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  settings = load_settings()
  settings["bot_name"] = message.text.strip()
  save_settings(settings)

  log_admin_action(
      message.from_user.id,
      message.from_user.full_name,
      "Update Bot Name",
      f"ប្តូរឈ្មោះ Bot ទៅ: {settings['bot_name']}",
  )

  await state.clear()
  await message.answer(
      '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> <b>បានប្តូរឈ្មោះ'
      f' Bot ទៅជា៖ <code>{settings["bot_name"]}</code> ជោគជ័យ!</b>',
      reply_markup=get_admin_main_keyboard(),
  )


@dp.callback_query(F.data == "admin_set_welcome_text")
async def admin_set_welcome_text_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  await state.set_state(AdminState.waiting_for_welcome_text)
  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="បោះបង់",
          callback_data="admin_edit_welcome_menu",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6034831751308644168">✍️</tg-emoji> <b>សូមផ្ញើសារស្វាគមន៍ថ្មីសម្រាប់'
      " Bot៖</b>",
      reply_markup=builder.as_markup(),
  )


@dp.message(AdminState.waiting_for_welcome_text)
async def process_welcome_text_update(
    message: types.Message, state: FSMContext
):
  if not is_admin(message.from_user.id):
    return
  settings = load_settings()
  settings["welcome_text"] = message.text.strip()
  save_settings(settings)

  log_admin_action(
      message.from_user.id,
      message.from_user.full_name,
      "Update Welcome Text",
      "បានកែប្រែសារស្វាគមន៍",
  )

  await state.clear()
  await message.answer(
      '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji>'
      " <b>បានកែប្រែសារស្វាគមន៍ជោគជ័យ!</b>",
      reply_markup=get_admin_main_keyboard(),
  )


# ============================================================
# AI ASSISTANT USER HANDLER
# ============================================================

@dp.message(F.text.endswith("AI Assistant"))
async def ai_assistant_start(message: types.Message, state: FSMContext):
  await state.set_state(UserState.chatting_with_ai)
  cancel_builder = ReplyKeyboardBuilder()
  cancel_builder.row(
      KeyboardButton(
          text="ចាកចេញពី AI",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )

  await message.answer(
      '<tg-emoji emoji-id="6030722571412967168">🤖</tg-emoji> <b>សូមស្វាគមន៍មកកាន់'
      " AI Assistant!</b>\n\n"
      "អ្នកអាចវាយសំណួរ ឬបញ្ហាផ្សេងៗដើម្បីឱ្យ AI ជួយឆ្លើយភ្លាមៗ។\n"
      "<i>(ចុច 'ចាកចេញពី AI' ដើម្បីត្រឡប់ទៅ Menu ដើម)</i>",
      reply_markup=cancel_builder.as_markup(resize_keyboard=True),
  )


@dp.message(UserState.chatting_with_ai)
async def ai_chat_process(message: types.Message, state: FSMContext):
  if message.text and "ចាកចេញពី AI" in message.text:
    await state.clear()
    await message.answer(
        '<tg-emoji emoji-id="6039451237743595514">👋</tg-emoji> <b>បានចាកចេញពី'
        " AI Assistant!</b>",
        reply_markup=get_main_reply_keyboard(message.from_user.id),
    )
    return

  reply_text = await ask_ai_assistant(message.text or "")
  await message.answer(reply_text)


# ============================================================
# ADMIN PERMISSION / ID CONFIGURATION
# ============================================================

@dp.callback_query(F.data == "admin_manage_perms")
async def admin_manage_perms_handler(callback: CallbackQuery):
  await callback.answer()
  settings = load_settings()
  admin_list = settings.get("admin_ids", [INITIAL_ADMIN_ID])
  text = (
      '<tg-emoji emoji-id="6033108709213736873">⚙️</tg-emoji> <b>ការគ្រប់គ្រងសិទ្ធិ'
      " ADMIN (PERMISSIONS)</b>\n\n"
      '<tg-emoji emoji-id="5904258298764334001">👑</tg-emoji> <b>បញ្ជី ADMIN IDs'
      " បច្ចុប្បន្ន ៖</b>\n"
  )
  for idx, aid in enumerate(admin_list, start=1):
    text += f"{idx}. <code>{aid}</code>\n"

  text += "\n👉 <i>លោកអ្នកអាចបន្ថែម ID ថ្មី ឬលប ID ចាស់បាន៖</i>"

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="បន្ថែម Admin ថ្មី",
          callback_data="admin_add_perm_id",
          style="success",
          icon_custom_emoji_id="6033108709213736873",
      ),
      InlineKeyboardButton(
          text="លុប Admin ID",
          callback_data="admin_del_perm_id",
          style="danger",
          icon_custom_emoji_id="5891207662678317861",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_back_main",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


@dp.callback_query(F.data == "admin_add_perm_id")
async def admin_add_perm_id_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  await state.set_state(AdminState.waiting_for_new_admin_id)
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6033108709213736873">➕</tg-emoji> <b>សូមផ្ញើ Telegram'
      " User ID របស់ Admin ថ្មីដែលចង់បន្ថែម៖</b>",
  )


@dp.message(AdminState.waiting_for_new_admin_id)
async def process_new_admin_id(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  try:
    new_id = int(message.text.strip())
    settings = load_settings()
    admin_set = set(settings.get("admin_ids", [INITIAL_ADMIN_ID]))
    admin_set.add(new_id)
    settings["admin_ids"] = list(admin_set)
    save_settings(settings)

    log_admin_action(
        message.from_user.id,
        message.from_user.full_name,
        "Add Admin Permission",
        f"បន្ថែម Admin ID: {new_id}",
    )

    await state.clear()
    await message.answer(
        '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> <b>បានបន្ថែម'
        f" Telegram ID: <code>{new_id}</code> ជា Admin ជោគជ័យ!</b>",
        reply_markup=get_admin_main_keyboard(),
    )
  except ValueError:
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> សូមបញ្ចូលលេខ'
        " Telegram ID ឱ្យបានត្រឹមត្រូវ!"
    )


@dp.callback_query(F.data == "admin_del_perm_id")
async def admin_del_perm_id_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  await state.set_state(AdminState.waiting_for_del_admin_id)
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="5891207662678317861">➖</tg-emoji> <b>សូមផ្ញើ Telegram'
      " User ID ដែលចង់ដកសិទ្ធិ Admin ចេញ៖</b>",
  )


@dp.message(AdminState.waiting_for_del_admin_id)
async def process_del_admin_id(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  try:
    del_id = int(message.text.strip())
    settings = load_settings()
    admin_set = set(settings.get("admin_ids", [INITIAL_ADMIN_ID]))
    if del_id in admin_set:
      if len(admin_set) <= 1:
        await message.answer(
            '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> មិនអាចលុប'
            " Admin ទាំងអស់បានទេ! ត្រូវមានយ៉ាងហោចណាស់ 1 ID។"
        )
        return
      admin_set.remove(del_id)
      settings["admin_ids"] = list(admin_set)
      save_settings(settings)

      log_admin_action(
          message.from_user.id,
          message.from_user.full_name,
          "Revoke Admin Permission",
          f"ដកហូត Admin ID: {del_id}",
      )

      await message.answer(
          '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> <b>បានដក ID:'
          f" <code>{del_id}</code> ចេញពី Admin រួចរាល់!</b>",
          reply_markup=get_admin_main_keyboard(),
      )
    else:
      await message.answer(
          '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> ID'
          " នេះមិនមាននៅក្នុងបញ្ជី Admin ទេ!",
          reply_markup=get_admin_main_keyboard(),
      )
    await state.clear()
  except ValueError:
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> សូមបញ្ចូលលេខ'
        " Telegram ID ឱ្យបានត្រឹមត្រូវ!"
    )


# ============================================================
# FILE MANAGER
# ============================================================

@dp.callback_query(F.data == "admin_manage_files_menu")
async def admin_manage_files_menu_handler(callback: CallbackQuery):
  await callback.answer()
  current_services, _ = load_data()
  builder = InlineKeyboardBuilder()
  count = 0
  for cat_key, service in current_services.items():
    for plan_code, plan in service.get("plans", {}).items():
      att = plan.get("attachment")
      if att and att.get("type") == "file":
        count += 1
        builder.row(
            InlineKeyboardButton(
                text=f"{service['name']} - {plan['name']}",
                callback_data=f"filedetail|{plan_code}",
                style="primary",
                icon_custom_emoji_id="5805648413743651862",
            )
        )
  builder.row(
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_back_main",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )

  if count == 0:
    await safe_edit_text(
        callback.message,
        '<tg-emoji emoji-id="5805648413743651862">📭</tg-emoji> <b>មិនទាន់មានមុខទំនិញភ្ជាប់'
        " File នៅក្នុង Bot នៅឡើយទេ!</b>",
        reply_markup=builder.as_markup(),
    )
  else:
    await safe_edit_text(
        callback.message,
        '<tg-emoji emoji-id="5805648413743651862">📁</tg-emoji> <b>ផ្ទាំងគ្រប់គ្រងមើល'
        " និងផ្លាស់ប្តូរ FILES (File Manager)</b>\n\nសូមជ្រើសរើសមុខទំនិញដើម្បីពិនិត្យមើល"
        " ឬ Update File៖",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("filedetail|"))
async def file_detail_handler(callback: CallbackQuery):
  await callback.answer()
  plan_code = callback.data.split("|")[1]
  current_services, _ = load_data()

  target_plan = None
  target_cat = None
  for c_key, c_val in current_services.items():
    if plan_code in c_val.get("plans", {}):
      target_plan = c_val["plans"][plan_code]
      target_cat = c_val
      break

  if not target_plan:
    await callback.answer("រកមិនឃើញទិន្នន័យ!", show_alert=True)
    return

  file_info = target_plan.get("attachment", {})
  f_name = file_info.get("file_name", "Unknown")
  f_size_mb = file_info.get("file_size_mb", 0.0)
  f_date = file_info.get("upload_date", "N/A")
  f_id = file_info.get("file_id")

  text = (
      '<tg-emoji emoji-id="5805648413743651862">📁</tg-emoji> <b>ព័ត៌មានលម្អិតនៃ'
      " FILE</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      f'<tg-emoji emoji-id="6042137469204303531">🏷</tg-emoji> <b>Category :</b>'
      f' {target_cat["name"]}\n'
      f'<tg-emoji emoji-id="6041730074376410123">📦</tg-emoji> <b>ទំនិញ :</b>'
      f' {target_plan["name"]}\n'
      f'<tg-emoji emoji-id="5805648413743651862">📄</tg-emoji> <b>ឈ្មោះ File :</b>'
      f" <code>{f_name}</code>\n"
      f'<tg-emoji emoji-id="5938539885907415367">📊</tg-emoji> <b>ទំហំ :</b>'
      f" <b>{f_size_mb:.2f} MB</b>\n"
      '<tg-emoji emoji-id="6039404727542747508">📅</tg-emoji> <b>កាលបរិច្ឆេទ'
      f" Upload :</b> {f_date}\n"
      f'<tg-emoji emoji-id="5904258298764334001">🆔</tg-emoji> <b>File ID :</b>'
      f" <code>{str(f_id)[:20]}...</code>\n"
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n👉 <i>អ្នកអាចចុចទាញយក File មកមើល ឬ Upload"
      " File ថ្មីមកជំនួសបាន៖</i>"
  )

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="ទាញយក Test មើល",
          callback_data=f"filetest|{plan_code}",
          style="success",
          icon_custom_emoji_id="6028205772117118673",
      ),
      InlineKeyboardButton(
          text="ប្តូរ File ថ្មី",
          callback_data=f"filechange|{plan_code}",
          style="primary",
          icon_custom_emoji_id="6039404727542747508",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_manage_files_menu",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )

  await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("filetest|"))
async def file_test_download_handler(callback: CallbackQuery):
  plan_code = callback.data.split("|")[1]
  current_services, _ = load_data()

  target_plan = None
  for c_val in current_services.values():
    if plan_code in c_val.get("plans", {}):
      target_plan = c_val["plans"][plan_code]
      break

  if not target_plan:
    await callback.answer("រកមិនឃើញទិន្នន័យ!", show_alert=True)
    return

  file_info = target_plan.get("attachment", {})
  f_id = file_info.get("file_id")
  f_name = file_info.get("file_name", "Test File")

  if not f_id:
    await callback.answer("មុខទំនិញនេះមិនមាន File ទេ!", show_alert=True)
    return

  await callback.answer("កំពុងទាញយក File ផ្ញើជូន...")
  try:
    await bot.send_document(
        chat_id=callback.message.chat.id,
        document=f_id,
        caption=(
            '<tg-emoji emoji-id="5805648413743651862">📁</tg-emoji>'
            f" <b>ឈ្មោះ File :</b> <code>{f_name}</code>\n"
            '<tg-emoji emoji-id="6041730074376410123">📦</tg-emoji>'
            f" <b>ទំនិញ :</b> {target_plan['name']}"
        ),
    )
  except Exception as e:
    await callback.message.answer(f"Error: {e}")


@dp.callback_query(F.data.startswith("filechange|"))
async def file_change_start_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  plan_code = callback.data.split("|")[1]
  await state.update_data(target_change_plan=plan_code)
  await state.set_state(AdminState.plan_file_update)

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="បោះបង់",
          callback_data="admin_manage_files_menu",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )

  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="5805648413743651862">📥</tg-emoji> <b>Upload File'
      " ថ្មីសម្រាប់ជំនួសមុខទំនិញនេះ</b>\n\n👉 សូម Upload File ថ្មីមកទីនេះ (.ipa, .deb, .zip, .pdf...)៖",
      reply_markup=builder.as_markup(),
  )


@dp.message(AdminState.plan_file_update, F.document)
async def process_file_update(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return

  data = await state.get_data()
  plan_code = data.get("target_change_plan")

  doc = message.document
  file_info = {
      "type": "file",
      "file_id": doc.file_id,
      "file_name": doc.file_name,
      "file_size_mb": (doc.file_size or 0) / (1024 * 1024),
      "mime_type": doc.mime_type,
      "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
  }

  current_services, resellers_list = load_data()
  found = False
  for cat_val in current_services.values():
    if plan_code in cat_val.get("plans", {}):
      cat_val["plans"][plan_code]["attachment"] = file_info
      found = True
      break

  if found:
    save_data(current_services, resellers_list)
    log_admin_action(
        message.from_user.id,
        message.from_user.full_name,
        "Update Plan File",
        f"បានប្តូរ File សម្រាប់ Plan {plan_code}: {doc.file_name}",
    )
    await state.clear()
    await message.answer(
        '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> <b>បាន Update'
        " File ថ្មីជោគជ័យ!</b>\n\n"
        '<tg-emoji emoji-id="5805648413743651862">📄</tg-emoji> <b>ឈ្មោះ File'
        f" :</b> <code>{doc.file_name}</code>\n"
        '<tg-emoji emoji-id="5938539885907415367">📊</tg-emoji> <b>ទំហំ :</b>'
        f" <b>{file_info['file_size_mb']:.2f} MB</b>",
        reply_markup=get_admin_main_keyboard(),
    )
  else:
    await state.clear()
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> រកមិនឃើញមុខទំនិញនេះទេ!',
        reply_markup=get_admin_main_keyboard(),
    )


# ============================================================
# DYNAMIC CATEGORY & PLAN CREATION FLOW
# ============================================================

@dp.callback_query(F.data == "admin_manage_categories")
async def admin_manage_categories_handler(
    callback: CallbackQuery, state: FSMContext
):
  await state.clear()
  await callback.answer()
  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="បង្កើត Category ថ្មី",
          callback_data="cat_add_new",
          style="success",
          icon_custom_emoji_id="6042137469204303531",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="បន្ថែម Plan ថ្មី",
          callback_data="cat_add_plan_menu",
          style="primary",
          icon_custom_emoji_id="5773677501825945508",
      ),
      InlineKeyboardButton(
          text="លុប Plan",
          callback_data="plan_delete_menu",
          style="danger",
          icon_custom_emoji_id="6039522349517115015",
      ),
  )
  builder.row(
      InlineKeyboardButton(
          text="លុប Category ទាំងមូល",
          callback_data="cat_delete_menu",
          style="danger",
          icon_custom_emoji_id="6039522349517115015",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_back_main",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6042137469204303531">🗂</tg-emoji> <b>ការគ្រប់គ្រង'
      " CATEGORIES & PLANS</b>\n\nសូមជ្រើសរើសជម្រើសខាងក្រោម៖",
      reply_markup=builder.as_markup(),
  )


@dp.callback_query(F.data == "cat_add_new")
async def cat_add_new_start(callback: CallbackQuery, state: FSMContext):
  await callback.answer()
  await state.set_state(AdminState.cat_name)
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6039404727542747508">✍️</tg-emoji> <b>សូមបញ្ចូលឈ្មោះ'
      " Category ថ្មី</b> (ឧទាហរណ៍: <code>FILE IPA VIP</code>):",
  )


@dp.message(AdminState.cat_name)
async def cat_name_received(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  name = message.text.strip()
  await state.update_data(new_cat_name=name)

  builder = InlineKeyboardBuilder()
  for item in PREMIUM_ICONS[:12]:
    builder.add(
        InlineKeyboardButton(
            text=f"Icon {item['num']}",
            callback_data=f"selpreseticon|{item['id']}",
            style="primary",
            icon_custom_emoji_id=item["id"],
        )
    )
  builder.adjust(3)

  builder.row(
      InlineKeyboardButton(
          text="ដាក់ Emoji/ID ដោយខ្លួនឯង",
          callback_data="custom_emoji_input",
          style="success",
          icon_custom_emoji_id="6039404727542747508",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="បោះបង់",
          callback_data="admin_manage_categories",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )

  await message.answer(
      f'<tg-emoji emoji-id="6042137469204303531">✨</tg-emoji> ឈ្មោះ Category:'
      f" <b>{name}</b>\n\n👉 <b>សូមជ្រើសរើស Logo Icon ឬចុច 'ដាក់ Emoji/ID"
      " ដោយខ្លួនឯង'៖</b>",
      reply_markup=builder.as_markup(),
  )


@dp.callback_query(F.data.startswith("selpreseticon|"))
async def selpreseticon_handler(callback: CallbackQuery, state: FSMContext):
  await callback.answer()
  emoji_id = callback.data.split("|")[1]
  await state.update_data(selected_emoji_id=emoji_id)
  await state.set_state(AdminState.cat_guide_video)

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="រំលង (មិនដាក់ Video)",
          callback_data="skip_cat_video",
          style="primary",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="បោះបង់",
          callback_data="admin_manage_categories",
          style="danger",
          icon_custom_emoji_id="6039522349517115015",
      )
  )

  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="5944753741512052670">🎥</tg-emoji> <b>សូមផ្ញើ/Upload'
      " វីដេអូនែនាំ (Guide Video) សម្រាប់ Category នេះ (ឬចុចរំលង)៖</b>",
      reply_markup=builder.as_markup(),
  )


@dp.callback_query(F.data == "custom_emoji_input")
async def custom_emoji_input_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  await state.set_state(AdminState.cat_custom_emoji_input)
  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="បោះបង់",
          callback_data="admin_manage_categories",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6039404727542747508">✍️</tg-emoji> <b>សូមផ្ញើ'
      " Telegram Premium Custom Emoji ឬលេខ Custom Emoji ID មកទីនេះ៖</b>\n\n💡"
      " <i>ឧទាហរណ៍៖ ផ្ញើ Emoji ផ្ទាល់ ឬលេខ ID (ឧ."
      " <code>5773677501825945508</code>)</i>",
      reply_markup=builder.as_markup(),
  )


@dp.message(AdminState.cat_custom_emoji_input)
async def process_custom_emoji_input(
    message: types.Message, state: FSMContext
):
  if not is_admin(message.from_user.id):
    return

  emoji_id = None
  if message.entities:
    for ent in message.entities:
      if ent.custom_emoji_id:
        emoji_id = str(ent.custom_emoji_id)
        break

  if not emoji_id and message.text:
    text_val = message.text.strip()
    if text_val.isdigit():
      emoji_id = text_val

  if not emoji_id:
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> មិនត្រឹមត្រូវទេ!'
        " សូមផ្ញើជា <b>Premium Emoji</b> ឬជា <b>លេខ ID (Digits)</b>។"
    )
    return

  await state.update_data(selected_emoji_id=emoji_id)
  await state.set_state(AdminState.cat_guide_video)

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="រំលង (មិនដាក់ Video)",
          callback_data="skip_cat_video",
          style="primary",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="បោះបង់",
          callback_data="admin_manage_categories",
          style="danger",
          icon_custom_emoji_id="6039522349517115015",
      )
  )

  await message.answer(
      f'<tg-emoji emoji-id="{emoji_id}">✨</tg-emoji> ទទួលបាន Emoji ID:'
      f" <code>{emoji_id}</code>\n\n<tg-emoji"
      ' emoji-id="5944753741512052670">🎥</tg-emoji> <b>សូមផ្ញើ/Upload'
      " វីដេអូនែនាំ (Guide Video) សម្រាប់ Category នេះ (ឬចុចរំលង)៖</b>",
      reply_markup=builder.as_markup(),
  )


@dp.message(AdminState.cat_guide_video, F.video | F.video_note | F.animation)
async def cat_video_received(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return

  video_id = None
  if message.video:
    video_id = message.video.file_id
  elif message.video_note:
    video_id = message.video_note.file_id
  elif message.animation:
    video_id = message.animation.file_id

  data = await state.get_data()
  cat_name = data.get("new_cat_name")
  emoji_id = data.get("selected_emoji_id")

  clean_slug = re.sub(r"[^a-zA-Z0-9]", "_", cat_name.lower())[:10]
  cat_key = f"cat_{clean_slug}_{int(datetime.now().timestamp()) % 10000}"

  current_services, resellers_list = load_data()
  current_services[cat_key] = {
      "name": cat_name,
      "guide_video": video_id,
      "emoji_id": emoji_id,
      "plans": {},
  }
  save_data(current_services, resellers_list)

  log_admin_action(
      message.from_user.id,
      message.from_user.full_name,
      "Create Category",
      f"បានបង្កើត Category: {cat_name}",
  )

  await state.clear()
  await message.answer(
      '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> <b>បានបង្កើត'
      f" Category [{cat_name}] ជោគជ័យ!</b>",
      reply_markup=get_admin_main_keyboard(),
  )


@dp.callback_query(AdminState.cat_guide_video, F.data == "skip_cat_video")
async def cat_video_skip(callback: CallbackQuery, state: FSMContext):
  await callback.answer()
  data = await state.get_data()
  cat_name = data.get("new_cat_name")
  emoji_id = data.get("selected_emoji_id")

  clean_slug = re.sub(r"[^a-zA-Z0-9]", "_", cat_name.lower())[:10]
  cat_key = f"cat_{clean_slug}_{int(datetime.now().timestamp()) % 10000}"

  current_services, resellers_list = load_data()
  current_services[cat_key] = {
      "name": cat_name,
      "guide_video": None,
      "emoji_id": emoji_id,
      "plans": {},
  }
  save_data(current_services, resellers_list)

  log_admin_action(
      callback.from_user.id,
      callback.from_user.full_name,
      "Create Category",
      f"បានបង្កើត Category (គ្មានវីដេអូ): {cat_name}",
  )

  await state.clear()
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> <b>បានបង្កើត'
      f" Category [{cat_name}] ជោគជ័យ!</b>",
      reply_markup=get_admin_main_keyboard(),
  )


@dp.callback_query(F.data == "cat_add_plan_menu")
async def cat_add_plan_menu_handler(callback: CallbackQuery):
  await callback.answer()
  current_services, _ = load_data()
  builder = InlineKeyboardBuilder()
  for c_key, c_data in current_services.items():
    emoji_id = c_data.get("emoji_id", "5805648413743651862")
    builder.row(
        InlineKeyboardButton(
            text=c_data["name"],
            callback_data=f"selcatforplan|{c_key}",
            style="primary",
            icon_custom_emoji_id=str(emoji_id),
        )
    )
  builder.row(
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_manage_categories",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6041730074376410123">📦</tg-emoji> <b>ជ្រើសរើស'
      " Category ដែលត្រូវបន្ថែម Plan (មុខទំនិញ)៖</b>",
      reply_markup=builder.as_markup(),
  )


# STEP 1: Plan Name
@dp.callback_query(F.data.startswith("selcatforplan|"))
async def selcatforplan_handler(callback: CallbackQuery, state: FSMContext):
  await callback.answer()
  cat_key = callback.data.split("|")[1]
  current_services, _ = load_data()
  await state.update_data(target_cat_key=cat_key)
  await state.set_state(AdminState.plan_name)
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6039404727542747508">✍️</tg-emoji>'
      " <b>បញ្ចូលឈ្មោះមុខទំនិញ/Plan</b> សម្រាប់"
      f" <b>{current_services[cat_key]['name']}</b>:",
  )


# STEP 2: Normal Price & Reseller Price
@dp.message(AdminState.plan_name)
async def plan_name_received(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  await state.update_data(new_plan_name=message.text.strip())
  await state.set_state(AdminState.plan_price)
  await message.answer(
      '<tg-emoji emoji-id="5938539885907415367">💵</tg-emoji> <b>សូមបញ្ចូលតម្លៃទូទៅ'
      " (USD)</b> (ឧ. 3.00):"
  )


@dp.message(AdminState.plan_price)
async def plan_price_received(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  try:
    price = float(message.text.strip())
    await state.update_data(new_plan_price=price)
    await state.set_state(AdminState.plan_reseller_price)
    await message.answer(
        '<tg-emoji emoji-id="5938539885907415367">💎</tg-emoji> <b>សូមបញ្ចូលតម្លៃ'
        " Reseller (USD)</b> (ឧ. 2.00):"
    )
  except ValueError:
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji>'
        " សូមបញ្ចូលជាលេខតម្លៃត្រឹមត្រូវ!"
    )


# STEP 3: Prompt for Guide Video
@dp.message(AdminState.plan_reseller_price)
async def plan_reseller_price_received(
    message: types.Message, state: FSMContext
):
  if not is_admin(message.from_user.id):
    return
  try:
    reseller_price = float(message.text.strip())
    await state.update_data(new_plan_reseller_price=reseller_price)
    await state.set_state(AdminState.plan_guide_video)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="រំលង (មិនដាក់ Video)",
            callback_data="skip_plan_video",
            style="primary",
            icon_custom_emoji_id="6035130900075777681",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="បោះបង់",
            callback_data="admin_manage_categories",
            style="danger",
            icon_custom_emoji_id="6039522349517115015",
        )
    )

    await message.answer(
        '<tg-emoji emoji-id="5944753741512052670">🎥</tg-emoji> <b>សូម Upload/ផ្ញើ'
        " វីដេអូនែនាំ (Guide Video) សម្រាប់ Plan នេះ (ឬចុចរំលង)៖</b>",
        reply_markup=builder.as_markup(),
    )
  except ValueError:
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji>'
        " សូមបញ្ចូលជាលេខតម្លៃត្រឹមត្រូវ!"
    )


# STEP 4: Guide Video Received / Skipped -> Prompt File or Link or Skip
@dp.message(AdminState.plan_guide_video, F.video | F.video_note | F.animation)
async def process_plan_video_save(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return

  video_id = None
  if message.video:
    video_id = message.video.file_id
  elif message.video_note:
    video_id = message.video_note.file_id
  elif message.animation:
    video_id = message.animation.file_id

  await state.update_data(temp_guide_video=video_id)
  await prompt_attachment_step(message, state)


@dp.callback_query(AdminState.plan_guide_video, F.data == "skip_plan_video")
async def process_plan_video_skip(callback: CallbackQuery, state: FSMContext):
  await callback.answer()
  await state.update_data(temp_guide_video=None)
  await prompt_attachment_step(callback.message, state)


async def prompt_attachment_step(message_or_msg: types.Message, state: FSMContext):
  await state.set_state(AdminState.plan_attachment)
  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="រំលង (មិនដាក់ File/Link)",
          callback_data="skip_plan_attachment",
          style="primary",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  builder.row(
      InlineKeyboardButton(
          text="បោះបង់",
          callback_data="admin_manage_categories",
          style="danger",
          icon_custom_emoji_id="6039522349517115015",
      )
  )

  text = (
      '<tg-emoji emoji-id="5805648413743651862">📁</tg-emoji> <b>សូម Upload File/Document '
      "(.ipa, .deb, .zip, .pdf...) ឬផ្ញើ Link/Text ដំឡើងមកទីនេះ (ឬចុចរំលង)៖</b>\n\n"
      "💡 <i>ពេលអតិថិជនទិញជោគជ័យ ប្រព័ន្ធនឹងទាញយក Key ចេញពីស្តុក (Stock Keys) ស្វ័យប្រវត្ត។</i>"
  )

  if isinstance(message_or_msg, types.CallbackQuery):
    await safe_edit_text(message_or_msg.message, text, reply_markup=builder.as_markup())
  else:
    await message_or_msg.answer(text, reply_markup=builder.as_markup())


# STEP 5: File Upload / Link Text / Skip Attachment -> Finalize Plan
@dp.message(AdminState.plan_attachment, F.document)
async def process_attachment_file(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  doc = message.document
  att_payload = {
      "type": "file",
      "file_id": doc.file_id,
      "file_name": doc.file_name,
      "file_size_mb": (doc.file_size or 0) / (1024 * 1024),
      "mime_type": doc.mime_type,
      "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
  }
  await finalize_plan_creation(message, state, att_payload, message.from_user)


@dp.message(AdminState.plan_attachment, F.text)
async def process_attachment_link(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  att_payload = {
      "type": "link",
      "link_text": message.text.strip(),
  }
  await finalize_plan_creation(message, state, att_payload, message.from_user)


@dp.callback_query(AdminState.plan_attachment, F.data == "skip_plan_attachment")
async def process_attachment_skip(callback: CallbackQuery, state: FSMContext):
  await callback.answer()
  await finalize_plan_creation(callback.message, state, None, callback.from_user)


async def finalize_plan_creation(
    message_or_msg: types.Message,
    state: FSMContext,
    attachment_payload=None,
    admin_user: types.User = None,
):
  data = await state.get_data()
  cat_key = data.get("target_cat_key")
  p_name = data.get("new_plan_name")
  price = data.get("new_plan_price")
  reseller_price = data.get("new_plan_reseller_price")
  video_id = data.get("temp_guide_video")

  clean_slug = re.sub(r"[^a-zA-Z0-9]", "_", p_name.lower())[:8]
  plan_code = f"p_{clean_slug}_{int(datetime.now().timestamp()) % 10000}"

  current_services, resellers_list = load_data()
  current_services[cat_key]["plans"][plan_code] = {
      "name": p_name,
      "price": price,
      "reseller_price": reseller_price,
      "attachment": attachment_payload,
      "guide_video": video_id,
  }
  save_data(current_services, resellers_list)

  # Auto initialize key stock
  async with stock_lock:
    stock_keys = load_stock()
    stock_keys[plan_code] = []
    save_stock(stock_keys)

  if admin_user:
    log_admin_action(
        admin_user.id,
        admin_user.full_name,
        "Create Plan",
        f"បន្ថែម Plan [{p_name}] ទៅក្នុង {current_services[cat_key]['name']}",
    )

  await state.clear()
  has_video = "✅ មាន" if video_id else "❌ គ្មាន"
  has_att = "❌ គ្មាន"
  if attachment_payload:
    has_att = "✅ File" if attachment_payload.get("type") == "file" else "✅ Link/Text"

  await message_or_msg.answer(
      f'<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> <b>បានបន្ថែម Plan'
      f" [{p_name}] ជោគជ័យ!</b>\n\n<tg-emoji"
      f' emoji-id="6042137469204303531">📦</tg-emoji> Category :'
      f' <b>{current_services[cat_key]["name"]}</b>\n<tg-emoji'
      f' emoji-id="5938539885907415367">💵</tg-emoji> តម្លៃទូទៅ :'
      f" <b>${price:.2f}</b> | 💎 Reseller : <b>${reseller_price:.2f}</b>\n<tg-emoji"
      f' emoji-id="5944753741512052670">🎥</tg-emoji> Video Guide : {has_video}\n'
      f'📁 Attachment : {has_att}\n\n'
      '💡 <i>សូមចូលទៅកាន់ <b>Add Key</b> ដើម្បីបញ្ចូល License Key ចូលក្នុងស្តុកសម្រាប់ Plan នេះ!</i>',
      reply_markup=get_admin_main_keyboard(),
  )


@dp.callback_query(F.data == "plan_delete_menu")
async def plan_delete_menu_handler(callback: CallbackQuery):
  await callback.answer()
  current_services, _ = load_data()
  builder = InlineKeyboardBuilder()
  count = 0
  for cat_key, service in current_services.items():
    for plan_code, plan in service.get("plans", {}).items():
      count += 1
      builder.row(
          InlineKeyboardButton(
              text=f"{service['name']} - {plan['name']}",
              callback_data=f"delplan|{plan_code}",
              style="danger",
              icon_custom_emoji_id="6039522349517115015",
          )
      )
  builder.row(
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_manage_categories",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  if count == 0:
    await safe_edit_text(
        callback.message,
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> <b>មិនមាន Plan'
        " សម្រាប់លុបទេ!</b>",
        reply_markup=builder.as_markup(),
    )
  else:
    await safe_edit_text(
        callback.message,
        '<tg-emoji emoji-id="6039522349517115015">🗑</tg-emoji> <b>ជ្រើសរើស Plan'
        " ដែលចង់លុប៖</b>",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("delplan|"))
async def delplan_handler(callback: CallbackQuery):
  plan_code = callback.data.split("|")[1]
  current_services, resellers_list = load_data()
  for cat_key, service in current_services.items():
    if plan_code in service.get("plans", {}):
      del service["plans"][plan_code]
      break

  save_data(current_services, resellers_list)
  async with stock_lock:
    stock_keys = load_stock()
    if plan_code in stock_keys:
      del stock_keys[plan_code]
      save_stock(stock_keys)

  log_admin_action(
      callback.from_user.id,
      callback.from_user.full_name,
      "Delete Plan",
      f"បានលុប Plan: {plan_code}",
  )

  await callback.answer("បានលុប Plan រួចរាល់!", show_alert=True)
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="5904258298764334001">👑</tg-emoji> <b>ផ្ទាំងគ្រប់គ្រង'
      " ADMIN PANEL</b>",
      reply_markup=get_admin_main_keyboard(),
  )


@dp.callback_query(F.data == "cat_delete_menu")
async def cat_delete_menu_handler(callback: CallbackQuery):
  await callback.answer()
  current_services, _ = load_data()
  builder = InlineKeyboardBuilder()
  for c_key, c_data in current_services.items():
    builder.row(
        InlineKeyboardButton(
            text=c_data["name"],
            callback_data=f"delcat|{c_key}",
            style="danger",
            icon_custom_emoji_id="6039522349517115015",
        )
    )
  builder.row(
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_manage_categories",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      )
  )
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> <b>ជ្រើសរើស'
      " Category ដែលចង់លុបចោល៖</b>",
      reply_markup=builder.as_markup(),
  )


@dp.callback_query(F.data.startswith("delcat|"))
async def delcat_handler(callback: CallbackQuery):
  cat_key = callback.data.split("|")[1]
  current_services, resellers_list = load_data()
  if cat_key in current_services:
    cat_name = current_services[cat_key]["name"]
    async with stock_lock:
      stock_keys = load_stock()
      for plan_code in current_services[cat_key].get("plans", {}).keys():
        if plan_code in stock_keys:
          del stock_keys[plan_code]
      save_stock(stock_keys)
    del current_services[cat_key]
    save_data(current_services, resellers_list)

    log_admin_action(
        callback.from_user.id,
        callback.from_user.full_name,
        "Delete Category",
        f"បានលុប Category [{cat_name}]",
    )

    await callback.answer("បានលុប Category រួចរាល់!", show_alert=True)
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="5904258298764334001">👑</tg-emoji> <b>ផ្ទាំងគ្រប់គ្រង'
      " ADMIN PANEL</b>",
      reply_markup=get_admin_main_keyboard(),
  )


# ============================================================
# ADMIN HANDLERS (STOCK & ANALYTICS)
# ============================================================

@dp.message(F.text.endswith("ADMIN PANEL"))
@dp.message(Command("admin"))
async def admin_command_handler(message: types.Message):
  if not is_admin(message.from_user.id):
    return
  bot_users = load_users()
  await message.answer(
      '<tg-emoji emoji-id="5904258298764334001">👑</tg-emoji> <b>ផ្ទាំងគ្រប់គ្រង'
      " ADMIN PANEL</b>\n\n"
      '<tg-emoji emoji-id="6033108709213736873">👥</tg-emoji> <b>Users សរុប:</b>'
      f" {len(bot_users)} នាក់",
      reply_markup=get_admin_main_keyboard(),
  )


@dp.callback_query(F.data == "admin_back_main")
async def admin_back_main_handler(callback: CallbackQuery, state: FSMContext):
  await state.clear()
  await callback.answer()
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="5904258298764334001">👑</tg-emoji> <b>ផ្ទាំងគ្រប់គ្រង'
      " ADMIN PANEL</b>",
      reply_markup=get_admin_main_keyboard(),
  )


@dp.callback_query(F.data == "admin_view_balance")
async def admin_view_balance_handler(callback: CallbackQuery):
  await callback.answer()
  analytics = get_sales_analytics()
  growth_sym = "+" if analytics["growth_percentage"] >= 0 else ""

  text = (
      '<tg-emoji emoji-id="5938539885907415367">📊</tg-emoji> <b>របាយការណ៍ចំណូល'
      " និងតុល្យភាពហិរញ្ញវត្ថុ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      f'<tg-emoji emoji-id="6039779802741739617">💵</tg-emoji> <b>ចំណូលសរុប :</b>'
      f" <b>${analytics['total_revenue']:.2f}</b>\n"
      '<tg-emoji emoji-id="6039404727542747508">📅</tg-emoji> <b>ចំណូលប្រចាំខែនេះ'
      f" :</b> <b>${analytics['this_month_revenue']:.2f}</b>\n"
      f'<tg-emoji emoji-id="6039779802741739617">💳</tg-emoji> <b>ចំណូលខែមុន'
      f" :</b> ${analytics['last_month_revenue']:.2f}\n"
      f'<tg-emoji emoji-id="5938539885907415367">📊</tg-emoji> <b>កំណើនចំណេញ'
      f" :</b> <b>{growth_sym}{analytics['growth_percentage']:.1f}%</b>\n"
      f'<tg-emoji emoji-id="6041730074376410123">🛍</tg-emoji> <b>ការលក់សរុប'
      f" :</b> {analytics['total_orders']} ដង\n"
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📝 <b>ប្រតិបត្តិការចុងក្រោយ :</b>\n\n"
  )
  if not analytics["recent_transactions"]:
    text += "<i>(មិនទាន់មានប្រតិបត្តិការលក់នៅឡើយទេ)</i>"
  else:
    for idx, tx in enumerate(
        reversed(analytics["recent_transactions"]), start=1
    ):
      text += (
          f"<b>{idx}. ${tx['amount']:.2f}</b> | {tx['item_name']}"
          f" ({tx['username']})\n"
      )

  builder = InlineKeyboardBuilder()
  builder.row(
      InlineKeyboardButton(
          text="Refresh Data",
          callback_data="admin_view_balance",
          style="success",
          icon_custom_emoji_id="6039451237743595514",
      ),
      InlineKeyboardButton(
          text="ត្រឡប់ក្រោយ",
          callback_data="admin_back_main",
          style="danger",
          icon_custom_emoji_id="6035130900075777681",
      ),
  )
  await safe_edit_text(callback.message, text, reply_markup=builder.as_markup())


@dp.callback_query(F.data == "admin_check_stock")
async def admin_check_stock_handler(callback: CallbackQuery):
  await callback.answer()
  current_services, _ = load_data()
  stock_keys = load_stock()
  stock_report = (
      '<tg-emoji emoji-id="5884479287171485878">📊</tg-emoji> <b>ស្តុកទំនិញ'
      " និងតម្លៃបច្ចុប្បន្ន៖</b>\n\n"
  )
  for cat_key, s_data in current_services.items():
    emoji_id = s_data.get("emoji_id", "5805648413743651862")
    stock_report += (
        f'<tg-emoji emoji-id="{emoji_id}">📁</tg-emoji> <b>{s_data["name"]}'
        " :</b>\n"
    )
    for p_code, p_data in s_data.get("plans", {}).items():
      count = len(stock_keys.get(p_code, []))
      att = p_data.get("attachment")
      tag = ""
      if att:
        tag = " [File]" if att.get("type") == "file" else " [Link]"
      stock_report += (
          f" • {p_data['name']}{tag}: <b>{count} Key</b> |"
          f" ${p_data['price']:.2f}\n"
      )
    stock_report += "\n"
  await safe_edit_text(
      callback.message, stock_report, reply_markup=get_admin_main_keyboard()
  )


@dp.callback_query(F.data == "admin_add_key_menu")
async def admin_add_key_menu_handler(callback: CallbackQuery):
  await callback.answer()
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="5773677501825945508">➕</tg-emoji> <b>ជ្រើសរើសកញ្ចប់ដែលចង់បញ្ចូល'
      " Key៖</b>",
      reply_markup=get_admin_plans_keyboard("admin_addkey"),
  )


@dp.callback_query(F.data.startswith("admin_addkey|"))
async def admin_addkey_select_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  plan_code = callback.data.split("|")[1]
  await state.update_data(selected_plan=plan_code)
  await state.set_state(AdminState.waiting_for_keys)
  await safe_edit_text(
      callback.message,
      f'<tg-emoji emoji-id="5773677501825945508">📥</tg-emoji> <b>បញ្ចូល Key'
      f" សម្រាប់ ({plan_code})</b>\n\n👉 ផ្ញើ Key មួយជួរមួយ Key (Enter"
      " ចុះបន្ទាត់)៖",
  )


@dp.message(AdminState.waiting_for_keys)
async def process_add_keys(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  data = await state.get_data()
  plan_code = data.get("selected_plan")
  keys_list = [k.strip() for k in message.text.strip().split("\n") if k.strip()]
  if not keys_list:
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> មិនមាន Key'
        " ត្រឹមត្រូវទេ!"
    )
    return

  async with stock_lock:
    stock_keys = load_stock()
    if plan_code not in stock_keys:
      stock_keys[plan_code] = []
    stock_keys[plan_code].extend(keys_list)
    save_stock(stock_keys)
    total_now = len(stock_keys[plan_code])

  log_admin_action(
      message.from_user.id,
      message.from_user.full_name,
      "Add Stock Keys",
      f"បានបន្ថែម {len(keys_list)} Keys ទៅក្នុង Plan ({plan_code})",
  )

  await state.clear()
  await message.answer(
      '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> <b>បានបញ្ចូល'
      f" {len(keys_list)} Key!</b>\nសរុបបច្ចុប្បន្ន: <b>{total_now} Key</b>",
      reply_markup=get_admin_main_keyboard(),
  )


@dp.callback_query(F.data == "admin_clear_stock_menu")
async def admin_clear_stock_menu_handler(callback: CallbackQuery):
  await callback.answer()
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6039522349517115015">🗑</tg-emoji>'
      " <b>ជ្រើសរើសកញ្ចប់ដែលចង់សម្អាត Stock Key៖</b>",
      reply_markup=get_admin_plans_keyboard("admin_clearplan"),
  )


@dp.callback_query(F.data.startswith("admin_clearplan|"))
async def admin_clearplan_handler(callback: CallbackQuery):
  plan_code = callback.data.split("|")[1]
  async with stock_lock:
    stock_keys = load_stock()
    removed_count = len(stock_keys.get(plan_code, []))
    stock_keys[plan_code] = []
    save_stock(stock_keys)

  log_admin_action(
      callback.from_user.id,
      callback.from_user.full_name,
      "Clear Stock",
      f"បានលុបសម្អាត {removed_count} Keys ចេញពី Plan ({plan_code})",
  )

  await callback.answer(f"បានសម្អាត {removed_count} Key!", show_alert=True)
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="5904258298764334001">👑</tg-emoji> <b>ផ្ទាំងគ្រប់គ្រង'
      " ADMIN PANEL</b>",
      reply_markup=get_admin_main_keyboard(),
  )


@dp.callback_query(F.data == "admin_export_sell_log")
async def admin_export_sell_log_handler(callback: CallbackQuery):
  if not os.path.exists(SELL_STOCK_FILE):
    await callback.answer("មិនទាន់មានទិន្នន័យការលក់នៅឡើយទេ!", show_alert=True)
    return
  with open(SELL_STOCK_FILE, "rb") as f:
    file_bytes = f.read()
  txt_file = BufferedInputFile(file_bytes, filename="sellstock.txt")
  await bot.send_document(
      chat_id=callback.message.chat.id,
      document=txt_file,
      caption=(
          '<tg-emoji emoji-id="5805648413743651862">📜</tg-emoji>'
          " <b>ប្រវត្តិនៃការលក់ទាំងអស់ (sellstock.txt)</b>"
      ),
  )


@dp.callback_query(F.data == "admin_broadcast_prompt")
async def admin_broadcast_prompt_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  await state.set_state(AdminState.waiting_for_broadcast)
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6039381989985882045">📢</tg-emoji> <b>ផ្ញើសារ ឬរូបភាពដែលចង់'
      " Broadcast ទៅកាន់ Users ទាំងអស់៖</b>",
  )


@dp.message(AdminState.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  await state.clear()
  bot_users = load_users()
  sent_count = 0
  for uid in list(bot_users):
    try:
      await message.copy_to(chat_id=uid)
      sent_count += 1
      await asyncio.sleep(0.05)
    except Exception:
      pass

  log_admin_action(
      message.from_user.id,
      message.from_user.full_name,
      "Broadcast Message",
      f"បានផ្ញើសារ Broadcast ទៅកាន់ {sent_count} នាក់",
  )

  await message.answer(
      '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> <b>Broadcast'
      f" បានផ្ញើទៅកាន់ {sent_count} នាក់រួចរាល់!</b>",
      reply_markup=get_admin_main_keyboard(),
  )


@dp.callback_query(F.data == "admin_price_menu_normal")
async def admin_price_menu_normal_handler(callback: CallbackQuery):
  await callback.answer()
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="5938539885907415367">💵</tg-emoji>'
      " <b>ជ្រើសរើសមុខទំនិញដែលចង់កែប្រែតម្លៃទូទៅ៖</b>",
      reply_markup=get_admin_plans_keyboard("admin_setnormprice"),
  )


@dp.callback_query(F.data.startswith("admin_setnormprice|"))
async def admin_setnormprice_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  plan_code = callback.data.split("|")[1]
  await state.update_data(selected_plan=plan_code)
  await state.set_state(AdminState.waiting_for_normal_price)
  await safe_edit_text(
      callback.message,
      f'<tg-emoji emoji-id="5938539885907415367">💵</tg-emoji> បញ្ចូលតម្លៃថ្មីសម្រាប់'
      f" <b>{plan_code}</b>:",
  )


@dp.message(AdminState.waiting_for_normal_price)
async def process_set_normal_price(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  try:
    new_price = float(message.text.strip())
    data = await state.get_data()
    plan_code = data.get("selected_plan")
    current_services, resellers_list = load_data()
    for s_data in current_services.values():
      if plan_code in s_data.get("plans", {}):
        s_data["plans"][plan_code]["price"] = new_price
    save_data(current_services, resellers_list)

    log_admin_action(
        message.from_user.id,
        message.from_user.full_name,
        "Change Normal Price",
        f"ប្តូរតម្លៃ Plan ({plan_code}) ទៅជា: ${new_price:.2f}",
    )

    await state.clear()
    await message.answer(
        '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> បានផ្លាស់ប្តូរតម្លៃទៅជា'
        f" <b>${new_price:.2f}</b>",
        reply_markup=get_admin_main_keyboard(),
    )
  except ValueError:
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji>'
        " សូមបញ្ចូលលេខតម្លៃត្រឹមត្រូវ!"
    )


@dp.callback_query(F.data == "admin_price_menu_reseller")
async def admin_price_menu_reseller_handler(callback: CallbackQuery):
  await callback.answer()
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="5938539885907415367">💎</tg-emoji>'
      " <b>ជ្រើសរើសមុខទំនិញដែលចង់កែប្រែតម្លៃ Reseller៖</b>",
      reply_markup=get_admin_plans_keyboard("admin_setresellerprice"),
  )


@dp.callback_query(F.data.startswith("admin_setresellerprice|"))
async def admin_setresellerprice_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  plan_code = callback.data.split("|")[1]
  await state.update_data(selected_plan=plan_code)
  await state.set_state(AdminState.waiting_for_reseller_price)
  await safe_edit_text(
      callback.message,
      f'<tg-emoji emoji-id="5938539885907415367">💎</tg-emoji> បញ្ចូលតម្លៃ'
      f" Reseller ថ្មីសម្រាប់ <b>{plan_code}</b>:",
  )


@dp.message(AdminState.waiting_for_reseller_price)
async def process_set_reseller_price(
    message: types.Message, state: FSMContext
):
  if not is_admin(message.from_user.id):
    return
  try:
    new_price = float(message.text.strip())
    data = await state.get_data()
    plan_code = data.get("selected_plan")
    current_services, resellers_list = load_data()
    for s_data in current_services.values():
      if plan_code in s_data.get("plans", {}):
        s_data["plans"][plan_code]["reseller_price"] = new_price
    save_data(current_services, resellers_list)

    log_admin_action(
        message.from_user.id,
        message.from_user.full_name,
        "Change Reseller Price",
        f"ប្តូរតម្លៃ Reseller Plan ({plan_code}) ទៅជា: ${new_price:.2f}",
    )

    await state.clear()
    await message.answer(
        '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> បានផ្លាស់ប្តូរតម្លៃ'
        f" Reseller ទៅជា <b>${new_price:.2f}</b>",
        reply_markup=get_admin_main_keyboard(),
    )
  except ValueError:
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji>'
        " សូមបញ្ចូលលេខតម្លៃត្រឹមត្រូវ!"
    )


@dp.callback_query(F.data == "admin_add_reseller")
async def admin_add_reseller_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  await state.set_state(AdminState.waiting_for_add_reseller)
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6033108709213736873">➕</tg-emoji> សូមផ្ញើ <b>Telegram'
      " User ID</b> របស់ Reseller៖",
  )


@dp.message(AdminState.waiting_for_add_reseller)
async def process_add_reseller(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  try:
    reseller_id = int(message.text.strip())
    current_services, resellers_list = load_data()
    resellers_list.add(reseller_id)
    save_data(current_services, resellers_list)

    log_admin_action(
        message.from_user.id,
        message.from_user.full_name,
        "Add Reseller",
        f"បន្ថែម Reseller ID: {reseller_id}",
    )

    await state.clear()
    await message.answer(
        '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> បានបន្ថែម'
        f" Reseller ID <code>{reseller_id}</code>!",
        reply_markup=get_admin_main_keyboard(),
    )
  except ValueError:
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> សូមបញ្ចូលលេខ ID'
        " ត្រឹមត្រូវ!"
    )


@dp.callback_query(F.data == "admin_remove_reseller")
async def admin_remove_reseller_handler(
    callback: CallbackQuery, state: FSMContext
):
  await callback.answer()
  await state.set_state(AdminState.waiting_for_remove_reseller)
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="5891207662678317861">➖</tg-emoji> សូមផ្ញើ <b>Telegram'
      " User ID</b> របស់ Reseller ដែលចង់លុប៖",
  )


@dp.message(AdminState.waiting_for_remove_reseller)
async def process_remove_reseller(message: types.Message, state: FSMContext):
  if not is_admin(message.from_user.id):
    return
  try:
    reseller_id = int(message.text.strip())
    current_services, resellers_list = load_data()
    if reseller_id in resellers_list:
      resellers_list.remove(reseller_id)
      save_data(current_services, resellers_list)

      log_admin_action(
          message.from_user.id,
          message.from_user.full_name,
          "Remove Reseller",
          f"លុប Reseller ID: {reseller_id}",
      )

      await message.answer(
          '<tg-emoji emoji-id="6039451237743595514">✅</tg-emoji> បានលុប ID'
          f" <code>{reseller_id}</code> ចេញពី Reseller!",
          reply_markup=get_admin_main_keyboard(),
      )
    else:
      await message.answer(
          '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> មិនមាន ID'
          " នេះក្នុងបញ្ជីទេ!",
          reply_markup=get_admin_main_keyboard(),
      )
    await state.clear()
  except ValueError:
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> សូមបញ្ចូលលេខ ID'
        " ត្រឹមត្រូវ!"
    )


# ============================================================
# USER SHOPPING FLOW
# ============================================================

@dp.message(CommandStart())
async def start_handler(message: types.Message):
  bot_users = load_users()
  if message.from_user.id not in bot_users:
    bot_users.add(message.from_user.id)
    save_users(bot_users)

  settings = load_settings()
  bot_name = settings.get("bot_name", "AngkorMusic Store")
  welcome_text = settings.get(
      "welcome_text",
      "សូមស្វាគមន៍មកកាន់ប្រព័ន្ធទិញទំនិញស្វ័យប្រវត្តិ! សូមជ្រើសរើសមុខងារខាងក្រោម៖",
  )

  await cleanup_existing_payment(message.chat.id)
  await message.answer(
      f'<tg-emoji emoji-id="5904258298764334001">👋</tg-emoji> <b>{bot_name}</b>\n\n{welcome_text}',
      reply_markup=get_main_reply_keyboard(message.from_user.id),
  )


@dp.message(F.text.endswith("Key របស់ខ្ញុំ"))
async def my_keys_handler(message: types.Message):
  user_history = get_user_history(message.from_user.id)
  if not user_history:
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">📭</tg-emoji> <b>មិនទាន់មានការទិញមុខម្ដងឡើយ!</b>\n\n'
        "👉 លោកអ្នកអាចចុចប៊ូតុង <b>BUY NOW</b> ដើម្បីធ្វើការបញ្ជាទិញទំនិញបាន។"
    )
    return

  text = (
      '<tg-emoji emoji-id="5805648413743651862">📋</tg-emoji>'
      " <b>ប្រវត្តិទំនិញដែលអ្នកធ្លាប់បានទិញ៖</b>\n\n"
  )
  for idx, item in enumerate(reversed(user_history[-10:]), start=1):
    text += (
        f"<b>{idx}. {item['item_name']}</b>\n"
        f'<tg-emoji emoji-id="5773677501825945508">🔑</tg-emoji> <b>ទំនិញ/Key/File'
        f' :</b> <code>{item["key"]}</code>\n'
        f'<tg-emoji emoji-id="5904258298764334001">🆔</tg-emoji> <b>Order ID'
        f' :</b> <code>{item["order_id"]}</code>\n'
        f'<tg-emoji emoji-id="6039404727542747508">📅</tg-emoji> <b>កាលបរិច្ឆេទ'
        f' :</b> {item["date"]}\n'
        f'<tg-emoji emoji-id="5944753741512052670">🎥</tg-emoji> <b>Guide'
        f' :</b> {item.get("guide_info", "None")}\n'
        "----------------------------------------\n"
    )
  await message.answer(
      text, link_preview_options=types.LinkPreviewOptions(is_disabled=True)
  )


@dp.message(F.text.endswith("BUY NOW"))
async def buy_now_handler(message: types.Message):
  if message.chat.id in active_payment:
    await cleanup_existing_payment(message.chat.id)

  current_services, _ = load_data()
  if not current_services:
    await message.answer(
        '<tg-emoji emoji-id="5805648413743651862">📭</tg-emoji> <b>មិនទាន់មានទំនិញ'
        " ឬ Category ត្រូវបានបង្កើតនៅឡើយទេ!</b>\n\n👉 <i>សូមចូលទៅកាន់ <b>ADMIN"
        " PANEL</b> ➔ <b>Categories & Plans</b> ដើម្បីបង្កើត Category ថ្មី។</i>"
    )
    return

  text = (
      '<tg-emoji emoji-id="6042137469204303531">🔘</tg-emoji>'
      " <b>សូមជ្រើសរើសប្រភេទសេវាកម្ម៖</b>"
  )
  await message.answer(text, reply_markup=get_inline_category_keyboard())


@dp.message(F.text.endswith("ចេញ/បោះបង់ (Cancel QR)"))
async def cancel_qr_handler(message: types.Message):
  if message.chat.id in active_payment:
    await cleanup_existing_payment(message.chat.id)
    await message.answer(
        '<tg-emoji emoji-id="6039522349517115015">❌</tg-emoji>'
        " <b>អ្នកបានបោះបង់ការទិញ!</b>",
        reply_markup=get_main_reply_keyboard(message.from_user.id),
    )
  else:
    await message.answer(
        "សូមជ្រើសរើសជម្រើសខាងក្រោម៖",
        reply_markup=get_main_reply_keyboard(message.from_user.id),
    )


@dp.callback_query(F.data.startswith("open_"))
async def open_service_category(callback: CallbackQuery):
  await callback.answer()
  cat_key = callback.data.replace("open_", "")
  current_services, _ = load_data()
  service = current_services.get(cat_key)
  if not service:
    await callback.answer("សេវាកម្មនេះមិនមានទេ!", show_alert=True)
    return
  emoji_id = service.get("emoji_id", "5805648413743651862")
  text = (
      f'<tg-emoji emoji-id="{emoji_id}">🌐</tg-emoji> <b>{service["name"]} -'
      " សូមជ្រើសរើសកញ្ចប់ទំនិញ៖</b>"
  )
  await safe_edit_text(
      callback.message,
      text,
      reply_markup=get_duration_keyboard(cat_key, callback.from_user.id),
  )


@dp.callback_query(F.data.startswith("view_cat_video|"))
async def view_cat_video_handler(callback: CallbackQuery):
  cat_key = callback.data.split("|")[1]
  current_services, _ = load_data()
  service = current_services.get(cat_key, {})
  video_id = service.get("guide_video")
  if video_id:
    await callback.answer("កំពុងផ្ញើវីដេអូនែនាំ...")
    try:
      await bot.send_video(
          chat_id=callback.message.chat.id,
          video=video_id,
          caption=(
              '<tg-emoji emoji-id="5944753741512052670">🎥</tg-emoji>'
              f" <b>វីដេអូនែនាំសម្រាប់ {service['name']}</b>"
          ),
      )
    except Exception as e:
      await callback.message.answer(f"Error: {e}")
  else:
    await callback.answer("មិនមានវីដេអូនែនាំទេ!", show_alert=True)


@dp.callback_query(F.data == "back_to_categories")
async def back_to_categories_handler(callback: CallbackQuery):
  await callback.answer()
  await safe_edit_text(
      callback.message,
      '<tg-emoji emoji-id="6042137469204303531">🔘</tg-emoji>'
      " <b>សូមជ្រើសរើសប្រភេទសេវាកម្ម៖</b>",
      reply_markup=get_inline_category_keyboard(),
  )


@dp.callback_query(F.data.startswith("select|"))
async def select_plan_handler(callback: CallbackQuery):
  await callback.answer()
  _, cat_key, plan_code = callback.data.split("|")
  current_services, resellers_list = load_data()
  stock_keys = load_stock()

  service = current_services.get(cat_key)
  if not service:
    return
  plan = service.get("plans", {}).get(plan_code)
  if not plan:
    return

  if len(stock_keys.get(plan_code, [])) == 0:
    await callback.answer("កញ្ចប់នេះអស់ Key ពីស្តុកហើយ!", show_alert=True)
    return

  is_reseller = callback.from_user.id in resellers_list
  price = plan["reseller_price"] if is_reseller else plan["price"]

  text = (
      '<tg-emoji emoji-id="6039404727542747508">📝</tg-emoji>'
      " <b>ផ្ទៀងផ្ទាត់ការទិញ (CONFIRM ORDER)</b>\n\n"
      f'<tg-emoji emoji-id="6041730074376410123">📦</tg-emoji> ឈ្មោះទំនិញ:'
      f" <b>{service['name']} - {plan['name']}</b>\n"
      f'<tg-emoji emoji-id="5938539885907415367">💵</tg-emoji> តម្លៃសរុប:'
      f" <b>${price:.2f}</b>\n\n"
      "❓ <i>តើអ្នកពិតជាចង់ទិញមុខទំនិញនេះមែនដែរឬទេ?</i>"
  )
  await safe_edit_text(
      callback.message,
      text,
      reply_markup=get_confirmation_keyboard(cat_key, plan_code),
  )


@dp.callback_query(F.data.startswith("confirm|"))
async def confirm_purchase_handler(callback: CallbackQuery):
  await callback.answer()
  chat_id = callback.message.chat.id
  await cleanup_existing_payment(chat_id)

  _, cat_key, plan_code = callback.data.split("|")
  current_services, resellers_list = load_data()
  stock_keys = load_stock()

  service = current_services.get(cat_key)
  if not service:
    return
  plan = service.get("plans", {}).get(plan_code)
  if not plan:
    return

  if len(stock_keys.get(plan_code, [])) == 0:
    await safe_edit_text(
        callback.message,
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> <b>សូមអភ័យទោស'
        " ទំនិញនេះទើបតែអស់ Key ពីស្តុក!</b>",
    )
    return

  is_reseller = callback.from_user.id in resellers_list
  amount = plan["reseller_price"] if is_reseller else plan["price"]
  item_name = f"{service['name']} ({plan['name']})"

  settings = load_settings()
  active_provider = settings.get("active_provider", "bakong")
  provider_title = "ABA PAYWAY" if active_provider == "aba" else "BAKONG KHQR"
  provider_instruction = (
      "សូមបើក App ABA Mobile ដើម្បីស្កេនទូទាត់ប្រាក់"
      if active_provider == "aba"
      else "សូមបើក App Bakong ឬ Mobile Banking ណាមួយដើម្បីស្កេនទូទាត់ប្រាក់"
  )

  await safe_edit_text(
      callback.message,
      f'<tg-emoji emoji-id="6075534731171079238">⏳</tg-emoji> <b>កំពុងបង្កើតវិក្កយបត្រ {provider_title} សូមរង់ចាំ...</b>',
  )

  ref = f"{active_provider.upper()}{chat_id}{int(datetime.now().timestamp()) % 100000}"
  data = await asyncio.to_thread(create_payment, amount, ref, active_provider)

  payment_id = data.get("id")
  qr_string = data.get("qr_string")

  if not payment_id or not qr_string or data.get("error"):
    await safe_edit_text(
        callback.message,
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji> <b>ប្រព័ន្ធធនាគារកំពុងរវល់'
        " សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ!</b>",
    )
    return

  output_io = await asyncio.to_thread(get_qr_photo, qr_string)
  if not output_io:
    await safe_edit_text(
        callback.message,
        '<tg-emoji emoji-id="6039522349517115015">⚠️</tg-emoji>'
        " <b>មិនអាចដំណើរការ QR បានទេ។</b>",
    )
    return

  input_file = BufferedInputFile(output_io.getvalue(), filename=f"{active_provider}_qr.png")

  try:
    await callback.message.delete()
  except Exception:
    pass

  msg = await bot.send_photo(
      chat_id=chat_id,
      photo=input_file,
      caption=(
          f'<tg-emoji emoji-id="6075534731171079238">💳</tg-emoji> <b>{provider_title} (ស្កេនបង់ប្រាក់)</b>\n\n'
          f'<tg-emoji emoji-id="6041730074376410123">📦</tg-emoji> <b>ទំនិញ :</b> {item_name}\n'
          f'<tg-emoji emoji-id="5938539885907415367">💵</tg-emoji> <b>តម្លៃ :</b> <b>${amount:.2f}</b>\n\n'
          f"📲 <i>{provider_instruction}</i>"
      ),
      reply_markup=get_cancel_reply_keyboard(),
  )

  username = callback.from_user.username or callback.from_user.first_name
  active_payment[chat_id] = {
      "payment_id": payment_id,
      "amount": amount,
      "message_id": msg.message_id,
      "username": username,
      "provider": active_provider,
  }
  active_payments_global[payment_id] = chat_id

  asyncio.create_task(
      check_payment_async(chat_id, payment_id, item_name, plan_code, cat_key, active_provider)
  )


# ============================================================
# MAIN RUNNER
# ============================================================

async def main():
  logging.basicConfig(level=logging.INFO)
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())

