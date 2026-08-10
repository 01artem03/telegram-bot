from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
import sqlite3
import re

TOKEN = "8928869639:AAFVoOnbsyxtZ67rIvBw0JMtrSpdOcBOvVw"
ADMIN_ID = 6933621963

NAME, PHONE = range(2)
ADD_NAME, ADD_DESC, ADD_PRICE, ADD_PHOTO = range(4)

def clean_price(price):
    return int(re.sub(r"\D", "", str(price)) or 0)

# ===== БАЗА =====
conn = sqlite3.connect("shop.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT,
    description TEXT,
    price TEXT,
    photo TEXT
)
""")
conn.commit()

# ===== СТАРТ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Товари", callback_data="products")],
        [InlineKeyboardButton("🛒 Корзина", callback_data="cart")]
    ])

    if update.message:
        await update.message.reply_text("🏪 Магазин", reply_markup=keyboard)
    else:
        await update.callback_query.message.reply_text("🏪 Магазин", reply_markup=keyboard)

# ===== МЕНЮ =====
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "products":
        await show_products(update, context)
    elif query.data == "cart":
        await show_cart(update, context)

# ===== ТОВАРИ =====
async def show_products(update, context):
    query = update.callback_query

    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()

    if not products:
        await query.message.reply_text("❌ Нема товарів")
        return

    index = context.user_data.get("product_index", 0)
    product = products[index]

    price = clean_price(product[3])

    keyboard = [
        [
            InlineKeyboardButton("⬅️", callback_data="prev"),
            InlineKeyboardButton("➡️", callback_data="next")
        ],
        [InlineKeyboardButton("🛒 Додати", callback_data=f"add_{product[0]}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back")]
    ]

    await query.message.reply_photo(
        photo=product[4],
        caption=f"{product[1]}\n{product[2]}\n💰 {price} грн",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ===== NEXT / PREV =====
async def next_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cursor.execute("SELECT COUNT(*) FROM products")
    total = cursor.fetchone()[0]

    context.user_data["product_index"] = (context.user_data.get("product_index", 0) + 1) % total
    await show_products(update, context)

async def prev_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cursor.execute("SELECT COUNT(*) FROM products")
    total = cursor.fetchone()[0]

    context.user_data["product_index"] = (context.user_data.get("product_index", 0) - 1) % total
    await show_products(update, context)

# ===== КОРЗИНА =====
async def show_cart(update, context):
    query = update.callback_query
    await query.answer()

    cart = context.user_data.get("cart", {})

    if not cart:
        await query.message.reply_text("🛒 Корзина пуста")
        return

    total = 0
    text = "🛒 Корзина:\n\n"
    keyboard = []

    for pid, qty in cart.items():
        cursor.execute("SELECT name, price FROM products WHERE id=?", (pid,))
        product = cursor.fetchone()

        price = clean_price(product[1])
        total += price * qty

        text += f"{product[0]} x{qty} = {price*qty} грн\n"

        keyboard.append([
            InlineKeyboardButton("➖", callback_data=f"minus_{pid}"),
            InlineKeyboardButton(str(qty), callback_data="none"),
            InlineKeyboardButton("➕", callback_data=f"plus_{pid}"),
            InlineKeyboardButton("❌", callback_data=f"remove_{pid}")
        ])

    text += f"\n💰 Всього: {total} грн"

    keyboard.append([InlineKeyboardButton("✅ Оформити", callback_data="checkout")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back")])

    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ===== ДІЇ =====
async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pid = int(query.data.split("_")[1])
    cart = context.user_data.setdefault("cart", {})
    cart[pid] = cart.get(pid, 0) + 1

async def plus(update, context):
    pid = int(update.callback_query.data.split("_")[1])
    context.user_data["cart"][pid] += 1
    await show_cart(update, context)

async def minus(update, context):
    pid = int(update.callback_query.data.split("_")[1])
    cart = context.user_data["cart"]

    cart[pid] -= 1
    if cart[pid] <= 0:
        del cart[pid]

    await show_cart(update, context)

async def remove_item(update, context):
    pid = int(update.callback_query.data.split("_")[1])
    del context.user_data["cart"][pid]
    await show_cart(update, context)

# ===== НАЗАД =====
async def back(update, context):
    await start(update, context)

# ===== ОФОРМЛЕННЯ =====
async def checkout(update, context):
    await update.callback_query.message.reply_text("Ім’я:")
    return NAME

async def get_name(update, context):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("Телефон:")
    return PHONE

async def get_phone(update, context):
    cart = context.user_data.get("cart", {})

    text = f"🔥 Замовлення\n👤 {context.user_data['name']}\n📞 {update.message.text}\n\n"

    for pid, qty in cart.items():
        cursor.execute("SELECT name FROM products WHERE id=?", (pid,))
        text += f"{cursor.fetchone()[0]} x{qty}\n"

    await context.bot.send_message(chat_id=ADMIN_ID, text=text)

    context.user_data["cart"] = {}
    await update.message.reply_text("✅ Замовлення оформлено!")
    return ConversationHandler.END

# ===== ДОДАТИ =====
async def add_start(update, context):
    if update.message.from_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Назва:")
    return ADD_NAME

async def add_name(update, context):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("Опис:")
    return ADD_DESC

async def add_desc(update, context):
    context.user_data["desc"] = update.message.text
    await update.message.reply_text("Ціна:")
    return ADD_PRICE

async def add_price(update, context):
    context.user_data["price"] = update.message.text
    await update.message.reply_text("Фото:")
    return ADD_PHOTO

async def add_photo(update, context):
    cursor.execute(
        "INSERT INTO products (name, description, price, photo) VALUES (?, ?, ?, ?)",
        (
            context.user_data["name"],
            context.user_data["desc"],
            context.user_data["price"],
            update.message.photo[-1].file_id
        )
    )
    conn.commit()

    await update.message.reply_text("✅ Додано")
    return ConversationHandler.END

# ===== ЗАПУСК =====
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(menu, pattern="^(products|cart)$"))
app.add_handler(CallbackQueryHandler(add_to_cart, pattern="add_"))
app.add_handler(CallbackQueryHandler(next_product, pattern="next"))
app.add_handler(CallbackQueryHandler(prev_product, pattern="prev"))
app.add_handler(CallbackQueryHandler(plus, pattern="plus_"))
app.add_handler(CallbackQueryHandler(minus, pattern="minus_"))
app.add_handler(CallbackQueryHandler(remove_item, pattern="remove_"))
app.add_handler(CallbackQueryHandler(back, pattern="back"))

app.add_handler(ConversationHandler(
    entry_points=[CallbackQueryHandler(checkout, pattern="checkout")],
    states={
        NAME: [MessageHandler(filters.TEXT, get_name)],
        PHONE: [MessageHandler(filters.TEXT, get_phone)],
    },
    fallbacks=[]
))

app.add_handler(ConversationHandler(
    entry_points=[CommandHandler("add", add_start)],
    states={
        ADD_NAME: [MessageHandler(filters.TEXT, add_name)],
        ADD_DESC: [MessageHandler(filters.TEXT, add_desc)],
        ADD_PRICE: [MessageHandler(filters.TEXT, add_price)],
        ADD_PHOTO: [MessageHandler(filters.PHOTO, add_photo)],
    },
    fallbacks=[]
))

app.run_polling()