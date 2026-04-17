import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import LabeledPrice, Message
from config import BOT_TOKEN, ADMIN_IDS
from database import init_db, add_admin, get_admins, get_products, add_product, delete_product, save_order

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Состояния для добавления товара (добавлен сервер)
class AddProductStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_price = State()
    waiting_for_server = State()
    waiting_for_description = State()

class DeleteProductStates(StatesGroup):
    waiting_for_product_id = State()

class AddAdminStates(StatesGroup):
    waiting_for_user_id = State()

@dp.message(Command("start"))
async def start(message: Message):
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="🛍️ Каталог")],
            [types.KeyboardButton(text="📦 Мои заказы")],
        ],
        resize_keyboard=True
    )
    if message.from_user.id in get_admins():
        keyboard.keyboard.append([types.KeyboardButton(text="🔧 Админ-панель")])
    await message.answer(
        "🏪 **Майнкрафт Шоп**\n\n"
        "Покупай заказы за Stars на разных серверах!\n\n"
        "🛍️ Каталог — посмотреть товары\n"
        "📦 Мои заказы — история покупок",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.message(F.text == "🛍️ Каталог")
async def catalog(message: Message):
    products = get_products()
    if not products:
        await message.answer("📭 Товаров пока нет. Загляни позже!")
        return
    
    # Группируем товары по серверам
    servers = {}
    for p in products:
        server = p[3]
        if server not in servers:
            servers[server] = []
        servers[server].append(p)
    
    # Создаём меню по серверам
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    for server in servers:
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text=f"🌐 {server}", callback_data=f"server_{server}")
        ])
    
    await message.answer("🏰 **Выбери сервер:**", reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("server_"))
async def show_server_products(callback: types.CallbackQuery):
    server_name = callback.data.replace("server_", "")
    products = get_products()
    
    # Фильтруем товары по выбранному серверу
    server_products = [p for p in products if p[3] == server_name]
    
    if not server_products:
        await callback.answer("На этом сервере пока нет товаров!")
        return
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    for p in server_products:
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=f"📦 {p[1]} — {p[2]} ⭐", 
                callback_data=f"buy_{p[0]}"
            )
        ])
    keyboard.inline_keyboard.append([types.InlineKeyboardButton(text="◀️ Назад к серверам", callback_data="back_to_servers")])
    
    await callback.message.edit_text(
        f"🛒 **Товары на сервере {server_name}:**",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_servers")
async def back_to_servers(callback: types.CallbackQuery):
    products = get_products()
    servers = {}
    for p in products:
        server = p[3]
        if server not in servers:
            servers[server] = []
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    for server in servers:
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text=f"🌐 {server}", callback_data=f"server_{server}")
        ])
    
    await callback.message.edit_text("🏰 **Выбери сервер:**", reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    products = get_products()
    product = next((p for p in products if p[0] == product_id), None)
    if not product:
        await callback.answer("Товар не найден!")
        return
    
    product_id, name, price, server, description = product
    
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"{name} [{server}]",
        description=description[:100] if description else f"Заказ на сервере {server}: {name}",
        payload=f"order_{product_id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=name, amount=price)],
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    product_id = int(payload.split("_")[1])
    products = get_products()
    product = next((p for p in products if p[0] == product_id), None)
    if product:
        product_id, name, price, server, description = product
        save_order(message.from_user.id, product_id, name, server, message.successful_payment.total_amount)
        
        await message.answer(
            f"✅ **Оплачено!**\n\n"
            f"📦 Товар: {name}\n"
            f"🌐 Сервер: {server}\n"
            f"📝 {description}\n\n"
            f"Спасибо за покупку! ❤️",
            parse_mode="Markdown"
        )
        
        for admin_id in get_admins():
            await bot.send_message(
                admin_id,
                f"🆕 **Новый заказ!**\n"
                f"👤 {message.from_user.full_name} (@{message.from_user.username})\n"
                f"📦 {name}\n"
                f"🌐 {server}\n"
                f"💰 {message.successful_payment.total_amount} ⭐"
            )

@dp.message(F.text == "📦 Мои заказы")
async def my_orders(message: Message):
    import sqlite3
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "SELECT product_name, server, amount, created_at FROM orders WHERE user_id = ? ORDER BY created_at DESC",
        (message.from_user.id,)
    )
    orders = cur.fetchall()
    conn.close()
    
    if not orders:
        await message.answer("📭 У тебя пока нет заказов.")
        return
    
    text = "📋 **Твои заказы:**\n\n"
    for o in orders[:10]:
        text += f"• {o[0]} [{o[1]}] — {o[2]} ⭐ ({o[3][:10]})\n"
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🔧 Админ-панель")
async def admin_panel(message: Message):
    if message.from_user.id not in get_admins():
        await message.answer("⛔ Доступ запрещён.")
        return
    
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="➕ Добавить товар")],
            [types.KeyboardButton(text="🗑️ Удалить товар")],
            [types.KeyboardButton(text="👑 Добавить админа")],
            [types.KeyboardButton(text="📊 Статистика")],
            [types.KeyboardButton(text="◀️ Назад")],
        ],
        resize_keyboard=True
    )
    
    await message.answer("🔧 **Админ-панель**\n\nВыбери действие:", reply_markup=keyboard, parse_mode="Markdown")

# ========== ДОБАВЛЕНИЕ ТОВАРА (теперь с сервером) ==========
@dp.message(F.text == "➕ Добавить товар")
async def start_add_product(message: Message, state: FSMContext):
    if message.from_user.id not in get_admins():
        return
    await state.set_state(AddProductStates.waiting_for_name)
    await message.answer("📝 Введи **название товара**:", parse_mode="Markdown")

@dp.message(AddProductStates.waiting_for_name)
async def add_product_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(AddProductStates.waiting_for_price)
    await message.answer("💰 Введи **цену в Stars** (только число):", parse_mode="Markdown")

@dp.message(AddProductStates.waiting_for_price)
async def add_product_price(message: Message, state: FSMContext):
    try:
        price = int(message.text)
        await state.update_data(price=price)
        await state.set_state(AddProductStates.waiting_for_server)
        await message.answer(
            "🌐 **Напиши название сервера Minecraft**\n\n"
            "Примеры: GrieferFun, Hypixel, MineFan, MCHammer\n\n"
            "Покупатель увидит этот сервер в каталоге.",
            parse_mode="Markdown"
        )
    except ValueError:
        await message.answer("❌ Введи число!")

@dp.message(AddProductStates.waiting_for_server)
async def add_product_server(message: Message, state: FSMContext):
    await state.update_data(server=message.text)
    await state.set_state(AddProductStates.waiting_for_description)
    await message.answer(
        "📄 **Введи описание/инструкцию** по получению товара\n\n"
        "Например: координаты, ник строителя, ссылка на файл и т.д.",
        parse_mode="Markdown"
    )

@dp.message(AddProductStates.waiting_for_description)
async def add_product_description(message: Message, state: FSMContext):
    data = await state.get_data()
    add_product(data['name'], data['price'], data['server'], message.text)
    await state.clear()
    await message.answer(
        f"✅ **Товар добавлен!**\n\n"
        f"📦 {data['name']}\n"
        f"💰 {data['price']} ⭐\n"
        f"🌐 {data['server']}\n"
        f"📄 {message.text[:100]}..."
    )

# ========== УДАЛЕНИЕ ТОВАРА ==========
@dp.message(F.text == "🗑️ Удалить товар")
async def start_delete_product(message: Message, state: FSMContext):
    if message.from_user.id not in get_admins():
        return
    
    products = get_products()
    if not products:
        await message.answer("📭 Нет товаров для удаления.")
        return
    
    text = "📋 **Список товаров:**\n\n"
    for p in products:
        text += f"ID: `{p[0]}` — {p[1]} ({p[2]} ⭐) [{p[3]}]\n"
    
    await state.set_state(DeleteProductStates.waiting_for_product_id)
    await message.answer(
        text + "\n🗑️ Введи **ID товара**, который хочешь удалить:",
        parse_mode="Markdown"
    )

@dp.message(DeleteProductStates.waiting_for_product_id)
async def delete_product_by_id(message: Message, state: FSMContext):
    try:
        product_id = int(message.text)
        delete_product(product_id)
        await state.clear()
        await message.answer(f"✅ Товар с ID {product_id} удалён!")
    except ValueError:
        await message.answer("❌ Введи число (ID товара)")

# ========== ДОБАВЛЕНИЕ АДМИНА ==========
@dp.message(F.text == "👑 Добавить админа")
async def start_add_admin(message: Message, state: FSMContext):
    if message.from_user.id not in get_admins():
        return
    await state.set_state(AddAdminStates.waiting_for_user_id)
    await message.answer(
        "👑 **Введи Telegram ID** пользователя, которого хочешь сделать админом.\n\n"
        "Узнать ID можно у бота @userinfobot",
        parse_mode="Markdown"
    )

@dp.message(AddAdminStates.waiting_for_user_id)
async def add_admin_by_id(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        add_admin(user_id)
        await state.clear()
        await message.answer(f"✅ Пользователь `{user_id}` теперь админ!", parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ Введи число (Telegram ID)")

# ========== СТАТИСТИКА ==========
@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: Message):
    if message.from_user.id not in get_admins():
        return
    
    import sqlite3
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM orders")
    total_orders = cur.fetchone()[0]
    
    cur.execute("SELECT SUM(amount) FROM orders")
    total_revenue = cur.fetchone()[0] or 0
    
    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0]
    
    # Статистика по серверам
    cur.execute("SELECT server, COUNT(*), SUM(amount) FROM orders GROUP BY server")
    server_stats = cur.fetchall()
    
    conn.close()
    
    text = f"📊 **Статистика магазина**\n\n"
    text += f"📦 Всего продаж: {total_orders}\n"
    text += f"💰 Выручка: {total_revenue} ⭐\n"
    text += f"🛍️ Товаров: {total_products}\n\n"
    
    if server_stats:
        text += "**По серверам:**\n"
        for s in server_stats:
            text += f"• {s[0]}: {s[1]} продаж, {s[2]} ⭐\n"
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "◀️ Назад")
async def back_to_main(message: Message):
    await start(message)

# ========== ЗАПУСК ==========
async def main():
    init_db()
    for admin_id in ADMIN_IDS:
        add_admin(admin_id)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())