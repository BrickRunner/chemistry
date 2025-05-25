import os
import sqlite3
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, Router
from aiogram.enums import ParseMode
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
from db import init_db, get_sections, get_topics_by_section, get_files_for_topic, delete_file_by_type
from dotenv import load_dotenv

# Загрузка переменных окружения
os.makedirs("files", exist_ok=True)
load_dotenv() 
TOKEN = os.getenv("TOKEN")
GROUP = os.getenv("GROUP")
TEACHERS = os.getenv("TEACHER") 
ADMINS = os.getenv("ADMIN")  

# Инициализация бота
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# Определение состояний для FSM
class Form(StatesGroup):
    section = State()
    topic = State()
    action = State()
    add_section = State()
    add_topic = State()
    file_type = State()
    file_upload = State()
    delete_section = State()
    delete_topic = State()
    delete_type = State()

# Кнопка "Назад" для универсального использования
def back_button():
    """Кнопка назад для всех состояний"""
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="Назад")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# Команда /start: выбор раздела
@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    sections = get_sections()
    print("Sections from DB:", sections)  # <-- добавь для отладки
    buttons = [types.KeyboardButton(text=s) for s in get_sections()]
    keyboard = types.ReplyKeyboardMarkup(
    keyboard=[[btn] for btn in buttons],  # каждая кнопка в своей строке
    resize_keyboard=True
    )

    await message.answer("Выберите раздел:", reply_markup=keyboard)
    await state.set_state(Form.section)

# Выбор темы после раздела
@dp.message(Form.section)
async def choose_topic(message: Message, state: FSMContext):
    if message.text == "Назад":
        # На /start нет куда назад — просто сброс
        await start(message, state)
        return

    section = message.text
    await state.update_data(section=section)
    topics = get_topics_by_section(section)

    buttons = [InlineKeyboardButton(text=t, callback_data=f"topic:{t}") for t in topics]
    buttons.append(InlineKeyboardButton(text="Назад", callback_data="back_to_sections"))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])


    await message.answer("Выберите тему:", reply_markup=keyboard)
    await state.set_state(None)

# Callback: пользователь выбрал тему
@dp.callback_query(lambda c: c.data and c.data.startswith("topic:"))
async def topic_callback(callback: CallbackQuery, state: FSMContext):
    topic = callback.data.split("topic:")[1]
    await state.update_data(topic=topic)

    actions = ["Теория", "Задание", "Домашнее задание", "Назад"]
    buttons = [types.KeyboardButton(text=a) for a in actions]
    keyboard = types.ReplyKeyboardMarkup(
    keyboard=[[btn] for btn in buttons], 
    resize_keyboard=True)
    await callback.message.answer("Что вы хотите получить?", reply_markup=keyboard)
    await state.set_state(Form.action)
    await callback.answer() 

# Callback: возврат к выбору разделов
@dp.callback_query(lambda c: c.data == "back_to_sections")
async def back_to_sections_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete_reply_markup()  # Убираем inline-клавиатуру
    await start(callback.message, state)
    await callback.answer()

# Блокировка текстовых сообщений, когда нужно выбрать тему через кнопки
@dp.message(Form.topic)
async def dummy_topic_message(message: Message, state: FSMContext):
    await message.answer("Пожалуйста, выберите тему с помощью кнопок ниже.")

# Отправка запрошенного файла пользователю и уведомление в группу
@dp.message(Form.action)
async def send_file(message: Message, state: FSMContext):
    if message.text == "Назад":
        data = await state.get_data()
        section = data.get("section")
        if section:
            await choose_topic(message, state)
        else:
            await start(message, state)
        return

    action = message.text
    data = await state.get_data()
    section = data["section"]
    topic = data["topic"]
    files = get_files_for_topic(topic)

    file_path = None
    if action == "Теория":
        file_path = files[0]
    elif action == "Задание":
        file_path = files[1]
    elif action == "Домашнее задание":
        file_path = files[2]

    if file_path:
        await message.answer_document(document=types.FSInputFile(f"files/{file_path}"))
        report = f"📘 *{message.from_user.full_name}* запросил: {section} > {topic} > {action}"
        await bot.send_message(chat_id=GROUP, text=report, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("Файл не найден.")
    
    await start(message, state)

# Команда /add_file — проверка прав
@dp.message(Command("add_file"))
async def add_file_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    print(user_id)
    if user_id != int(TEACHERS) and user_id != int(ADMINS):
        await message.answer("❌ У вас нет прав для добавления файлов.")
        return

    buttons = [types.KeyboardButton(text=s) for s in get_sections()]
    buttons.append(types.KeyboardButton(text="Назад"))
    keyboard = types.ReplyKeyboardMarkup(
    keyboard=[[btn] for btn in buttons],  # каждая кнопка в своей строке
    resize_keyboard=True)
    await message.answer("Выберите раздел для добавления файла:", reply_markup=keyboard)
    await state.set_state(Form.add_section)

# Ввод темы
@dp.message(Form.add_section)
async def add_file_topic(message: Message, state: FSMContext):
    if message.text == "Назад":
        await state.clear()
        await message.answer("Отмена добавления файла.", reply_markup=types.ReplyKeyboardRemove())
        return

    await state.update_data(section=message.text)
    await message.answer("Введите название темы (если она уже есть — файл будет обновлён):", reply_markup=back_button())
    await state.set_state(Form.add_topic)

# Выбор типа файла (теория, задание, дом.задание)
@dp.message(Form.add_topic)
async def add_file_type(message: Message, state: FSMContext):
    if message.text == "Назад":
        await add_file_start(message, state)
        return

    await state.update_data(topic=message.text)
    buttons = [
        types.KeyboardButton(text="Теория"),
        types.KeyboardButton(text="Задание"),
        types.KeyboardButton(text="Домашнее задание"),
        types.KeyboardButton(text="Назад")
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=[buttons], resize_keyboard=True)
    await message.answer("Выберите тип файла:", reply_markup=keyboard)
    await state.set_state(Form.file_type)

# Получение файла от пользователя
@dp.message(Form.file_type)
async def upload_file_prompt(message: Message, state: FSMContext):
    if message.text == "Назад":
        await add_file_topic(message, state)
        return

    await state.update_data(file_type=message.text)
    await message.answer("Отправьте файл (PDF, DOC и т.д.):", reply_markup=back_button())
    await state.set_state(Form.file_upload)

# Удаление файла
@dp.message(Command("delete_file"))
async def delete_file_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id != int(TEACHERS) and user_id != int(ADMINS):
        await message.answer("❌ У вас нет прав для удаления файлов.")
        return

    sections = get_sections()
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=s)] for s in sections] + [[types.KeyboardButton(text="Назад")]],
        resize_keyboard=True
    )
    await message.answer("Выберите раздел:", reply_markup=keyboard)
    await state.set_state(Form.delete_section)

# Ввод темы
@dp.message(Form.delete_section)
async def delete_file_choose_topic(message: Message, state: FSMContext):
    if message.text == "Назад":
        await state.clear()
        await message.answer("Удаление отменено.", reply_markup=types.ReplyKeyboardRemove())
        return

    section = message.text
    topics = get_topics_by_section(section)
    if not topics:
        await message.answer("В этом разделе нет тем.")
        return

    await state.update_data(section=section)
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=t)] for t in topics] + [[types.KeyboardButton(text="Назад")]],
        resize_keyboard=True
    )
    await message.answer("Выберите тему:", reply_markup=keyboard)
    await state.set_state(Form.delete_topic)

# Выбор типа файла (теория, задание, дом.задание)
@dp.message(Form.delete_topic)
async def delete_file_choose_type(message: Message, state: FSMContext):
    if message.text == "Назад":
        await delete_file_start(message, state)
        return

    await state.update_data(topic=message.text)
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Теория")],
            [types.KeyboardButton(text="Задание")],
            [types.KeyboardButton(text="Домашнее задание")],
            [types.KeyboardButton(text="Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите тип файла для удаления:", reply_markup=keyboard)
    await state.set_state(Form.delete_type)

# Удаление
@dp.message(Form.delete_type)
async def delete_selected_file(message: Message, state: FSMContext):
    if message.text == "Назад":
        await delete_file_choose_type(message, state)
        return

    data = await state.get_data()
    section = data["section"]
    topic = data["topic"]
    file_type = message.text

    result = delete_file_by_type(section, topic, file_type)

    if result == "not_found":
        await message.answer(f"❗ Файл {file_type} уже удалён или отсутствует.")
    elif result == "no_topic":
        await message.answer("❌ Тема не найдена.")
    elif result == "deleted":
        await message.answer(f"✅ Файл удалён из темы *{topic}*.", parse_mode=ParseMode.MARKDOWN)
    elif result == "topic_removed":
        await message.answer(f"✅ Файл удалён.\n📂 Поскольку больше файлов в теме *{topic}* не осталось — тема удалена.", parse_mode=ParseMode.MARKDOWN)

    await state.clear()
    await message.answer("Готово.", reply_markup=types.ReplyKeyboardRemove())

# Сохранение
@dp.message(Form.file_upload)
async def receive_file(message: Message, state: FSMContext):
    if message.text == "Назад":
        await add_file_type(message, state)
        return

    if not message.document:
        await message.answer("Пожалуйста, отправьте файл как документ.", reply_markup=back_button())
        return

    data = await state.get_data()
    section = data["section"]
    topic = data["topic"]
    file_type = data["file_type"]

    file = message.document
    filename = f"{section}_{topic}_{file_type}_{file.file_name}".replace(" ", "_")
    file_path = f"files/{filename}"

    await bot.download(file, destination=file_path)

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM topics WHERE section = ? AND topic = ?", (section, topic))
    row = cursor.fetchone()

    if row:
        column = {
            "Теория": "theory_file",
            "Задание": "task_file",
            "Домашнее задание": "homework_file"
        }[file_type]

        cursor.execute(f"UPDATE topics SET {column} = ? WHERE id = ?", (filename, row[0]))
    else:
        theory = task = hw = None
        if file_type == "Теория": theory = filename
        elif file_type == "Задание": task = filename
        elif file_type == "Домашнее задание": hw = filename

        cursor.execute('''
            INSERT INTO topics (section, topic, theory_file, task_file, homework_file)
            VALUES (?, ?, ?, ?, ?)
        ''', (section, topic, theory, task, hw))

    conn.commit()
    conn.close()

    await message.answer("Файл успешно загружен!", reply_markup=types.ReplyKeyboardRemove())
    await state.clear()

# Команда запуска
async def main():
    logging.basicConfig(level=logging.INFO)
    dp.include_router(router)
    print("🚀 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
