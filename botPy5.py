import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import Message
import sqlite3
import hashlib
from datetime import datetime, timedelta

drop_users_list = []

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token="7014679556:AAGPqYwhEIQ7jD7uhidFQg4GwfV2pCEOo88")
dp = Dispatcher()

# Подключение к базе данных SQLite
conn = sqlite3.connect('New db education.db', check_same_thread=False)
cursor = conn.cursor()

# Состояния FSM
class AuthState(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()
    waiting_for_full_name = State()
    waiting_for_group = State()
    waiting_for_student_id = State()

class MessageState(StatesGroup):
    waiting_for_recipient = State()
    waiting_for_message_text = State()
    waiting_for_confirmation = State()

class KnowledgeBaseState(StatesGroup):
    choosing_category = State()
    viewing_content = State()
    adding_content = State()
    adding_title = State()
    adding_text = State()
    adding_category = State()
    setting_permanent = State()
    editing_content = State()

class AdminState(StatesGroup):
    waiting_for_new_user_data = State()

# Инициализация базы данных
def setup_database():
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        login TEXT UNIQUE,
        password TEXT,
        full_name TEXT,
        role TEXT CHECK(role IN ('student', 'teacher', 'admin')),
        group_name TEXT,
        student_id TEXT,
        is_verified BOOLEAN DEFAULT FALSE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pre_registered_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT UNIQUE,
        password TEXT,
        full_name TEXT,
        role TEXT CHECK(role IN ('student', 'teacher', 'admin')),
        group_name TEXT,
        student_id TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id INTEGER,
        to_user_id INTEGER,
        text TEXT,
        timestamp DATETIME,
        is_read BOOLEAN DEFAULT FALSE,
        FOREIGN KEY (from_user_id) REFERENCES users(user_id),
        FOREIGN KEY (to_user_id) REFERENCES users(user_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS knowledge_base (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        content TEXT,
        category TEXT,
        is_permanent BOOLEAN,
        created_at DATETIME,
        updated_at DATETIME,
        author_id INTEGER,
        FOREIGN KEY (author_id) REFERENCES users(user_id)
    )
    ''')

    add_test_users()
    conn.commit()

def add_test_users():
    cursor.execute("SELECT COUNT(*) FROM pre_registered_users")
    if cursor.fetchone()[0] == 0:
        test_users = [
            ('student1', 'pass123', 'Иванов Иван Иванович', 'student', 'Группа 101', 'ST-001'),
            ('student2', 'pass123', 'Петров Петр Петрович', 'student', 'Группа 101', 'ST-002'),
            ('student3', 'pass123', 'Сергеев Сергей Сергеевич', 'student', 'Группа 102', 'ST-003'),
            ('student4', 'pass123', 'Александров Александр Александрович', 'student', 'Группа 102', 'ST-004'),
            ('student5', 'pass123', 'Андреев Андрей Андреевич', 'student', 'Группа 103', 'ST-005'),
            ('student6', 'pass123', 'Михайлов Михаил Михайлович', 'student', 'Группа 103', 'ST-006'),
            ('teacher1', 'pass123', 'Сидорова Анна Михайловна', 'teacher', None, None),
            ('teacher2', 'pass123', 'Кузнецов Дмитрий Сергеевич', 'teacher', None, None),
            ('teacher3', 'pass123', 'Морозова Юлия Денисовна', 'teacher', None, None),
            ('teacher4', 'pass123', 'Фёдоров Григорий Александрович', 'teacher', None, None),
            ('admin1', 'admin123', 'Главный Администратор', 'admin', None, None),
            ('admin2', 'admin123', 'Главный По туалетам', 'admin', None, None),
            ('admin3', 'admin123', 'Главный По коду', 'admin', None, None)
        ]

        for user in test_users:
            try:
                cursor.execute(
                    "INSERT INTO pre_registered_users (login, password, full_name, role, group_name, student_id) VALUES (?, ?, ?, ?, ?, ?)",
                    user
                )
            except sqlite3.IntegrityError:
                continue

# Вспомогательные функции
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_role(user_id: int) -> str:
    cursor.execute("SELECT role FROM users WHERE user_id = ? AND is_verified = TRUE", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None

def get_user_full_name(user_id: int) -> str:
    cursor.execute("SELECT full_name FROM users WHERE user_id = ? AND is_verified = TRUE", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else "Unknown"

def can_send_message(sender_id: int, recipient_id: int) -> bool:
    sender_role = get_user_role(sender_id)
    recipient_role = get_user_role(recipient_id)
    
    if not sender_role or not recipient_role:
        return False
        
    if sender_role == "admin":
        return True
    elif sender_role == "teacher":
        return recipient_role in ["student", "teacher", "admin"]
    elif sender_role == "student":
        return recipient_role == "teacher"
    return False

def get_last_message_time(user_id: int) -> datetime:
    cursor.execute("SELECT MAX(timestamp) FROM messages WHERE from_user_id = ?", (user_id,))
    result = cursor.fetchone()
    return datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S') if result and result[0] else None

def can_user_send_message_now(user_id: int) -> bool:
    last_message_time = get_last_message_time(user_id)
    if not last_message_time:
        return True
    return datetime.now() - last_message_time > timedelta(minutes=0)

async def show_main_menu(message: types.Message, user_id: int):
    role = get_user_role(user_id)
    
    builder = ReplyKeyboardBuilder()
    
    if role == "student":
        builder.button(text="Написать преподавателю")
        builder.button(text="База знаний")
    elif role == "teacher":
        builder.button(text="Написать студенту")
        builder.button(text="Написать преподавателю")
        builder.button(text="Написать администратору")
        builder.button(text="База знаний")
    elif role == "admin":
        builder.button(text="Написать студенту")
        builder.button(text="Написать преподавателю")
        builder.button(text="Написать администратору")
        builder.button(text="База знаний")
        builder.button(text="Администрирование")
    
    # Добавляем кнопку выхода для всех авторизованных пользователей
    builder.button(text="Выйти из аккаунта")
    
    builder.adjust(2)
    await message.answer(
        "Главное меню:\nДля подсказок напишите /подсказки",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    cursor.execute("SELECT * FROM users WHERE user_id = ? AND is_verified = TRUE", (user_id,))
    if cursor.fetchone():
        await show_main_menu(message, user_id)
    else:
        builder = ReplyKeyboardBuilder()
        builder.button(text="Войти")
        await message.answer(
            "Добро пожаловать! Для доступа к боту пройдите верификацию.",
            reply_markup=builder.as_markup(resize_keyboard=True)
        )

@dp.message(Command("подсказки"))
async def show_help(message: types.Message):
    user_id = message.from_user.id
    role = get_user_role(user_id)
    
    help_text = "📌 Доступные команды и функции:\n\n"
    
    # Общие команды для всех
    help_text += "🔹 Общие команды:\n"
    help_text += "/start - Начать работу с ботом\n"
    help_text += "/подсказки - Показать это сообщение\n"
    help_text += "Выйти из аккаунта - Завершить текущую сессию\n\n"
    
    # Команды для студентов
    if role == "student":
        help_text += "🔹 Команды для студентов:\n"
        help_text += "Написать преподавателю - Отправить сообщение преподавателю\n"
        help_text += "База знаний - Доступ к учебным материалам\n\n"
    
    # Команды для преподавателей
    elif role == "teacher":
        help_text += "🔹 Команды для преподавателей:\n"
        help_text += "Написать студенту - Отправить сообщение студенту\n"
        help_text += "Написать преподавателю - Отправить сообщение коллеге\n"
        help_text += "Написать администратору - Отправить сообщение администратору\n"
        help_text += "База знаний - Доступ к учебным материалам и их добавление\n\n"
    
    # Команды для администраторов
    elif role == "admin":
        help_text += "🔹 Команды для администраторов:\n"
        help_text += "Написать студенту - Отправить сообщение студенту\n"
        help_text += "Написать преподавателю - Отправить сообщение преподавателю\n"
        help_text += "Написать администратору - Отправить сообщение коллеге\n"
        help_text += "База знаний - Доступ к учебным материалам и их управление\n"
        help_text += "Администрирование - Управление пользователями\n"
        help_text += "Добавить пользователя - Зарегистрировать нового пользователя\n"
        help_text += "Список пользователей - Просмотр всех зарегистрированных пользователей\n"
        help_text += "Удалить пользователя - Удалить пользователя из системы\n\n"
    
    # Для неавторизованных пользователей
    else:
        help_text += "🔹 Для доступа к функциям бота необходимо войти.\n"
        help_text += "Войти - Начать процесс входа\n\n"
    
    await message.answer(help_text)

@dp.message(F.text == "Войти")
async def start_registration(message: types.Message, state: FSMContext):
    await message.answer("Введите ваш логин (как в системе учебного заведения):")
    await state.set_state(AuthState.waiting_for_login)

@dp.message(AuthState.waiting_for_login)
async def process_login(message: types.Message, state: FSMContext):
    login = message.text.strip()
    cursor.execute("SELECT * FROM pre_registered_users WHERE login = ?", (login,))
    user_data = cursor.fetchone()
    
    if not user_data:
        await message.answer("Логин не найден. Попробуйте еще раз.")
        return
    
    await state.update_data({
        'pre_registered_data': user_data,
        'login': login
    })
    await message.answer("Введите ваш пароль:")
    await state.set_state(AuthState.waiting_for_password)

@dp.message(AuthState.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    pre_data = data['pre_registered_data']
    
    if password != pre_data[2]:
        await message.answer("Неверный пароль. Попробуйте еще раз.")
        return
    
    if pre_data[4] == 'student':
        await message.answer("Введите ваше полное ФИО (как в студенческом билете):")
        await state.set_state(AuthState.waiting_for_full_name)
    else:
        await complete_registration(message, state)

@dp.message(AuthState.waiting_for_full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    data = await state.get_data()
    
    if full_name.lower() != data['pre_registered_data'][3].lower():
        await message.answer("ФИО не совпадает. Попробуйте еще раз.")
        return
    
    await state.update_data({'full_name': full_name})
    await message.answer("Введите номер вашей группы:")
    await state.set_state(AuthState.waiting_for_group)

@dp.message(AuthState.waiting_for_group)
async def process_group(message: types.Message, state: FSMContext):
    group = message.text.strip()
    data = await state.get_data()
    
    if group.lower() != data['pre_registered_data'][5].lower():
        await message.answer("Группа не совпадает. Попробуйте еще раз.")
        return
    
    await state.update_data({'group_name': group})
    await message.answer("Введите номер студенческого билета:")
    await state.set_state(AuthState.waiting_for_student_id)

@dp.message(AuthState.waiting_for_student_id)
async def process_student_id(message: types.Message, state: FSMContext):
    student_id = message.text.strip().upper()
    data = await state.get_data()
    
    if student_id != data['pre_registered_data'][6]:
        await message.answer("Номер студенческого не совпадает. Попробуйте еще раз.")
        return
    
    await state.update_data({'student_id': student_id})
    await complete_registration(message, state)

async def complete_registration(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pre_data = data['pre_registered_data']
    user_id = message.from_user.id
    
    try:
        cursor.execute(
            "INSERT INTO users (user_id, login, password, full_name, role, group_name, student_id, is_verified) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, TRUE)",
            (
                user_id,
                pre_data[1],
                hash_password(pre_data[2]),
                pre_data[3],
                pre_data[4],
                pre_data[5] if pre_data[4] == 'student' else None,
                pre_data[6] if pre_data[4] == 'student' else None
            )
        )
        conn.commit()
        await message.answer(f"Регистрация завершена! Добро пожаловать, {pre_data[3]}!")
        await show_main_menu(message, user_id)
    except sqlite3.IntegrityError:
        await message.answer("Ошибка: пользователь уже зарегистрирован.")
    
    await state.clear()

# Обработчик выхода из аккаунта
@dp.message(F.text == "Выйти из аккаунта")
async def logout_user(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    
    await state.clear()
    
    builder = ReplyKeyboardBuilder()
    builder.button(text="Войти")
    await message.answer(
        "Вы успешно вышли из аккаунта. Для доступа к боту пройдите верификацию снова.",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# Обработчики для сообщений
@dp.message(F.text.startswith("Написать"))
async def write_to_user(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    role = get_user_role(user_id)
    
    if not role:
        await message.answer("Доступ запрещен.")
        return
    
    target = message.text.split()[-1]
    if target == "преподавателю":
        cursor.execute("SELECT user_id, full_name FROM users WHERE role = 'teacher' AND is_verified = TRUE")
    elif target == "студенту":
        cursor.execute("SELECT user_id, full_name FROM users WHERE role = 'student' AND is_verified = TRUE")
    elif target == "администратору":
        cursor.execute("SELECT user_id, full_name FROM users WHERE role = 'admin' AND is_verified = TRUE")
    else:
        return
    
    users = cursor.fetchall()
    if not users:
        await message.answer("Нет доступных пользователей.")
        return
    
    builder = InlineKeyboardBuilder()
    for user in users:
        builder.button(text=user[1], callback_data=f"select_recipient_{user[0]}")
    builder.adjust(1)
    
    await message.answer("Выберите получателя:", reply_markup=builder.as_markup())
    await state.set_state(MessageState.waiting_for_recipient)

@dp.callback_query(F.data.startswith("select_recipient_"), MessageState.waiting_for_recipient)
async def select_recipient(callback: types.CallbackQuery, state: FSMContext):
    recipient_id = int(callback.data.split("_")[2])
    await state.update_data(recipient_id=recipient_id)
    await callback.message.answer("Введите текст сообщения:")
    await state.set_state(MessageState.waiting_for_message_text)
    await callback.answer()

@dp.message(MessageState.waiting_for_message_text)
async def process_message_text(message: types.Message, state: FSMContext):
    if not can_user_send_message_now(message.from_user.id):
        await message.answer("Вы можете отправлять сообщения не чаще одного раза в 30 минут.")
        await state.clear()
        return
    
    await state.update_data(message_text=message.text)
    data = await state.get_data()
    
    recipient_name = get_user_full_name(data['recipient_id'])
    sender_name = get_user_full_name(message.from_user.id)
    role = get_user_role(message.from_user.id)
    group = cursor.execute(
        "SELECT group_name FROM users WHERE user_id = ?", 
        (message.from_user.id,)
    ).fetchone()[0] if role == "student" else None
    
    preview = f"🔹 {sender_name} ({role.capitalize()}"
    if group:
        preview += f", Группа {group}"
    preview += f"\n   {data['message_text']}\n"
    preview += f"🕒 {datetime.now().strftime('%H:%M, %d.%m.%Y')}"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Отправить", callback_data="confirm_send")
    builder.button(text="Отменить", callback_data="cancel_send")
    
    await message.answer(f"Подтвердите отправку:\n\n{preview}", reply_markup=builder.as_markup())
    await state.set_state(MessageState.waiting_for_confirmation)

@dp.callback_query(F.data == "confirm_send", MessageState.waiting_for_confirmation)
async def confirm_send(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sender_id = callback.from_user.id
    recipient_id = data['recipient_id']
    message_text = data['message_text']
    
    if not can_send_message(sender_id, recipient_id):
        await callback.message.answer("У вас нет прав для отправки сообщения этому пользователю.")
        await state.clear()
        return
    
    cursor.execute(
        "INSERT INTO messages (from_user_id, to_user_id, text, timestamp) VALUES (?, ?, ?, ?)",
        (sender_id, recipient_id, message_text, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    )
    conn.commit()
    
    sender_name = get_user_full_name(sender_id)
    sender_role = get_user_role(sender_id)
    sender_group = cursor.execute(
        "SELECT group_name FROM users WHERE user_id = ?", 
        (sender_id,)
    ).fetchone()[0] if sender_role == "student" else None
    
    msg_to_recipient = f"🔹 {sender_name} ({sender_role.capitalize()}"
    if sender_group:
        msg_to_recipient += f", Группа {sender_group}"
    msg_to_recipient += f")\n   {message_text}\n"
    msg_to_recipient += f"🕒 {datetime.now().strftime('%H:%M, %d.%m.%Y')}"
    
    try:
        await bot.send_message(recipient_id, msg_to_recipient)
    except Exception as e:
        logger.error(f"Failed to send message to {recipient_id}: {e}")
    
    await callback.message.answer("Сообщение отправлено!")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "cancel_send", MessageState.waiting_for_confirmation)
async def cancel_send(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Отправка отменена.")
    await state.clear()
    await callback.answer()

# Обработчики для базы знаний
@dp.message(F.text == "База знаний")
async def knowledge_base_menu(message: types.Message, state: FSMContext):
    user_role = get_user_role(message.from_user.id)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📚 Постоянные материалы", callback_data="kb_permanent")
    builder.button(text="📌 Временные материалы", callback_data="kb_temporary")
    
    if user_role in ["teacher", "admin"]:
        builder.button(text="➕ Добавить материал", callback_data="kb_add")
        builder.button(text="✏️ Мои материалы", callback_data="kb_my")
    
    builder.adjust(1)
    await message.answer("📖 База знаний:", reply_markup=builder.as_markup())
    await state.set_state(KnowledgeBaseState.choosing_category)

@dp.callback_query(F.data.startswith("kb_"), KnowledgeBaseState.choosing_category)
async def process_kb_category(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    user_id = callback.from_user.id

    if action == "back":
        await knowledge_base_menu(callback.message, state)
        await callback.answer()
        return
        
    if action == "permanent":
        cursor.execute("""
            SELECT id, title FROM knowledge_base 
            WHERE is_permanent = 1 
            ORDER BY title
        """)
        materials = cursor.fetchall()
        title = "📚 Постоянные материалы"
        
    elif action == "temporary":
        cursor.execute("""
            SELECT id, title FROM knowledge_base 
            WHERE is_permanent = 0 
            ORDER BY created_at DESC
        """)
        materials = cursor.fetchall()
        title = "📌 Временные материалы"
        
    elif action == "my":
        cursor.execute("""
            SELECT id, title FROM knowledge_base 
            WHERE author_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
        materials = cursor.fetchall()
        title = "✏️ Мои материалы"
        
    elif action == "add":
        await callback.message.answer("Введите название материала:")
        await state.set_state(KnowledgeBaseState.adding_title)
        await callback.answer()
        return
    
    if not materials:
        await callback.message.answer("Материалы не найдены.")
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for material in materials:
        builder.button(text=material[1], callback_data=f"material_{material[0]}")
    builder.adjust(1)
    
    await callback.message.answer(title, reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await show_main_menu(callback.message, callback.from_user.id)
    await state.clear()
    await callback.answer()

@dp.message(KnowledgeBaseState.adding_title)
async def process_add_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Введите содержание материала:")
    await state.set_state(KnowledgeBaseState.adding_text)

@dp.message(KnowledgeBaseState.adding_text)
async def process_add_text(message: types.Message, state: FSMContext):
    await state.update_data(content=message.text)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Учебные материалы", callback_data="category_study")
    builder.button(text="Методички", callback_data="category_methods")
    builder.button(text="Расписание", callback_data="category_schedule")
    builder.button(text="Другое", callback_data="category_other")
    
    await message.answer("Выберите категорию:", reply_markup=builder.as_markup())
    await state.set_state(KnowledgeBaseState.adding_category)

@dp.callback_query(F.data.startswith("category_"), KnowledgeBaseState.adding_category)
async def process_add_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.split("_")[1]
    await state.update_data(category=category)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Постоянный материал", callback_data="permanent_1")
    builder.button(text="Временный материал", callback_data="permanent_0")
    
    await callback.message.answer("Выберите тип материала:", reply_markup=builder.as_markup())
    await state.set_state(KnowledgeBaseState.setting_permanent)
    await callback.answer()

@dp.callback_query(F.data.startswith("permanent_"), KnowledgeBaseState.setting_permanent)
async def process_set_permanent(callback: types.CallbackQuery, state: FSMContext):
    is_permanent = bool(int(callback.data.split("_")[1]))
    user_data = await state.get_data()
    user_id = callback.from_user.id
    
    cursor.execute("""
        INSERT INTO knowledge_base 
        (title, content, category, is_permanent, created_at, updated_at, author_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_data['title'],
        user_data['content'],
        user_data['category'],
        is_permanent,
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        user_id
    ))
    conn.commit()
    
    await callback.message.answer("✅ Материал успешно добавлен в базу знаний!")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data.startswith("material_"))
async def view_material(callback: types.CallbackQuery, state: FSMContext):
    material_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    cursor.execute("""
        SELECT title, content, category, is_permanent, created_at, author_id 
        FROM knowledge_base 
        WHERE id = ?
    """, (material_id,))
    material = cursor.fetchone()
    
    if not material:
        await callback.answer("Материал не найден!")
        return
    
    title, content, category, is_permanent, created_at, author_id = material
    author_name = get_user_full_name(author_id)
    
    text = f"<b>{title}</b>\n\n"
    text += f"{content}\n\n"
    text += f"📁 Категория: {category}\n"
    text += f"📅 Дата создания: {created_at}\n"
    text += f"👤 Автор: {author_name}\n"
    text += "🔒 Тип: " + ("Постоянный" if is_permanent else "Временный")
    
    builder = InlineKeyboardBuilder()
    
    if user_id == author_id or get_user_role(user_id) == "admin":
        builder.button(text="✏️ Редактировать", callback_data=f"edit_{material_id}")
        builder.button(text="🗑️ Удалить", callback_data=f"delete_{material_id}")
        builder.adjust(2)
    
    builder.button(text="🔙 В главное меню", callback_data="main_menu")
    
    await callback.message.answer(text, reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("edit_"))
async def edit_material(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    material_id = int(parts[-1])
    user_id = callback.from_user.id
    
    cursor.execute("SELECT author_id FROM knowledge_base WHERE id = ?", (material_id,))
    result = cursor.fetchone()
    
    if not result or (user_id != result[0] and get_user_role(user_id) != "admin"):
        await callback.answer("У вас нет прав для редактирования!")
        return
    
    if len(parts) == 2:
        builder = InlineKeyboardBuilder()
        builder.button(text="Название", callback_data=f"edit_title_{material_id}")
        builder.button(text="Содержание", callback_data=f"edit_content_{material_id}")
        builder.button(text="Категорию", callback_data=f"edit_category_{material_id}")
        builder.button(text="Тип", callback_data=f"edit_permanent_{material_id}")
        builder.adjust(2)
        
        await callback.message.answer("Что вы хотите изменить?", reply_markup=builder.as_markup())
        await callback.answer()
        return
    
    field = parts[1]
    await state.update_data(
        edit_field=field,
        material_id=material_id
    )
    
    if field == 'permanent':
        builder = InlineKeyboardBuilder()
        builder.button(text="Постоянный", callback_data="permanent_1")
        builder.button(text="Временный", callback_data="permanent_0")
        await callback.message.answer("Выберите тип материала:", reply_markup=builder.as_markup())
    elif field == 'category':
        builder = InlineKeyboardBuilder()
        builder.button(text="Учебные материалы", callback_data="category_study")
        builder.button(text="Методички", callback_data="category_methods")
        builder.button(text="Расписание", callback_data="category_schedule")
        builder.button(text="Другое", callback_data="category_other")
        await callback.message.answer("Выберите категорию:", reply_markup=builder.as_markup())
    else:
        await callback.message.answer(f"Введите новое значение для {field}:")
        await state.set_state(KnowledgeBaseState.editing_content)
    
    await callback.answer()

@dp.message(KnowledgeBaseState.editing_content)
async def save_edited_material(message: types.Message, state: FSMContext):
    data = await state.get_data()
    material_id = data['material_id']
    field = data['edit_field']
    new_value = message.text
    
    cursor.execute(f"""
        UPDATE knowledge_base 
        SET {field} = ?, updated_at = ?
        WHERE id = ?
    """, (
        new_value,
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        material_id
    ))
    conn.commit()
    
    await message.answer("✅ Изменения сохранены!")
    await state.clear()

@dp.callback_query(F.data.startswith(("category_", "permanent_")))
async def save_selected_option(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    material_id = data['material_id']
    field = data['edit_field']
    
    if callback.data.startswith("category_"):
        new_value = callback.data.split("_")[1]
    else:
        new_value = int(callback.data.split("_")[1])
    
    cursor.execute(f"""
        UPDATE knowledge_base 
        SET {field} = ?, updated_at = ?
        WHERE id = ?
    """, (
        new_value,
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        material_id
    ))
    conn.commit()
    
    await callback.message.answer("✅ Изменения сохранены!")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_"))
async def delete_material(callback: types.CallbackQuery):
    material_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    cursor.execute("SELECT author_id FROM knowledge_base WHERE id = ?", (material_id,))
    result = cursor.fetchone()
    
    if not result or (user_id != result[0] and get_user_role(user_id) != "admin"):
        await callback.answer("У вас нет прав для удаления!")
        return
    
    cursor.execute("DELETE FROM knowledge_base WHERE id = ?", (material_id,))
    conn.commit()
    
    await callback.message.answer("Материал удален!")
    await callback.answer()
    await callback.message.delete()

# Обработчики для администрирования
@dp.message(F.text == "Администрирование")
async def admin_panel(message: types.Message):
    if get_user_role(message.from_user.id) != "admin":
        await message.answer("Доступ запрещён.")
        return
    
    builder = ReplyKeyboardBuilder()
    builder.button(text="Добавить пользователя")
    builder.button(text="Список пользователей")
    builder.button(text="Удалить пользователя")
    builder.button(text="Назад")
    builder.adjust(2)
    
    await message.answer(
        "Админ-панель:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@dp.message(F.text == "Удалить пользователя")
async def drop_user_button(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) != "admin":
        await message.answer("Доступ запрещён.")
        return
    
    builder = ReplyKeyboardBuilder()
    builder.button(text="Выйти из меню удаления пользователей")
    await message.answer(text="Введите id пользователя для удаления:")
    drop_users_list.append(message.chat.id)

@dp.message()
async def drop_user(message: Message, bot: Bot):
    if message.chat.id in drop_users_list:
        if message.text == "Выйти из меню удаления пользователей":
            drop_users_list.remove(message.chat.id)
            await message.answer("Выход из меню удаления пользователей.")
            return
            
        cursor.execute('SELECT * FROM pre_registered_users WHERE id=?', (message.text,))
        info = cursor.fetchall()
        if not info:
            await message.answer("Такого пользователя не существует")
            return
            
        cursor.execute('DELETE FROM pre_registered_users WHERE id=?', (message.text,))
        conn.commit()
        await message.answer("Пользователь успешно удалён!")
        drop_users_list.remove(message.chat.id)

@dp.message(F.text == "Список пользователей")
async def list_users_command(message: types.Message):
    if get_user_role(message.from_user.id) != "admin":
        await message.answer("Доступ запрещен.")
        return
    
    cursor.execute("""
        SELECT full_name, role, group_name, is_verified 
        FROM users 
        ORDER BY role, full_name
    """)
    users = cursor.fetchall()
    
    if not users:
        await message.answer("Нет зарегистрированных пользователей.")
        return
    
    response = "📋 Список пользователей:\n\n"
    for user in users:
        full_name, role, group, is_verified = user
        verified_status = "✅" if is_verified else "❌"
        user_info = f"{full_name} ({role.capitalize()}) {verified_status}"
        if role == "student" and group:
            user_info += f", Группа: {group}"
        response += user_info + "\n"
    
    await message.answer(response)

@dp.message(F.text == "Назад")
async def back_to_main_menu_from_admin(message: types.Message):
    await show_main_menu(message, message.from_user.id)

@dp.message(F.text == "Добавить пользователя")
async def add_user_command(message: types.Message, state: FSMContext):
    if get_user_role(message.from_user.id) != "admin":
        return
    
    await message.answer(
        "Введите данные пользователя в формате:\n"
        "Логин, Пароль, ФИО, Роль(student/teacher/admin), Группа(если студент), Номер студенческого(если студент)\n\n"
        "Пример:\n"
        "ivanov, pass123, Иванов Иван Иванович, student, Группа 101, ST-001"
    )
    await state.set_state(AdminState.waiting_for_new_user_data)

@dp.message(AdminState.waiting_for_new_user_data)
async def process_new_user_data(message: types.Message, state: FSMContext):
    try:
        parts = [p.strip() for p in message.text.split(',')]
        if len(parts) not in [4, 6]:
            raise ValueError
        
        login, password, full_name, role = parts[:4]
        group_name = parts[4] if len(parts) > 4 else None
        student_id = parts[5] if len(parts) > 5 else None
        
        if role not in ['student', 'teacher', 'admin']:
            raise ValueError
        
        if role == 'student' and (not group_name or not student_id):
            raise ValueError
        
        cursor.execute(
            "INSERT INTO pre_registered_users (login, password, full_name, role, group_name, student_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (login, password, full_name, role, group_name, student_id)
        )
        conn.commit()
        await message.answer("Пользователь успешно добавлен!")
    except Exception as e:
        logger.error(f"Error adding user: {e}")
        await message.answer("Ошибка в формате данных. Попробуйте еще раз.")
    
    await state.clear()

# Запуск бота
async def main():
    setup_database()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
