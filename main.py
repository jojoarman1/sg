import logging
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import pytz


API_TOKEN = '7352744899:AAFQmRbAAzkV8QPA75xdml04jw1l7q88vds'
CHANNEL_ID = -1002244000979  # ID вашего канала
DISCUSSION_GROUP_ID = -1002225022005  # ID вашей группы обсуждений
logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
dp.middleware.setup(LoggingMiddleware())

# Словарь для хранения текущих сообщений и их кнопок
current_messages = {}

# Словарь для хранения запланированных сообщений
scheduled_messages = {}

last_sent_dates = {}

# Словарь для перевода дней недели
weekdays_translation = {
    "monday": "Понедельник",
    "tuesday": "Вторник",
    "wednesday": "Среда",
    "thursday": "Четверг",
    "friday": "Пятница",
    "saturday": "Суббота",
    "sunday": "Воскресенье"
}

# Устанавливаем часовой пояс MSK
msk_tz = pytz.timezone('Europe/Moscow')

# Определяем состояния для админ времени и шаблонов сообщений
class AdminTime(StatesGroup):
    waiting_for_time = State()
    waiting_for_custom_time = State()


class ScheduleTemplate(StatesGroup):
    waiting_for_day = State()
    waiting_for_time = State()
    waiting_for_message = State()


# Создатель канала (установите здесь правильный ID создателя канала)
CREATOR_ID = 1250100261  # замените на фактический ID создателя канала

# Время в минутах, на которое предоставляются права администратора (по умолчанию 1 минута)
admin_time_minutes = 60


# Функция для создания клавиатуры с предустановленными временными значениями и кнопкой для ввода своего времени
def create_time_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton(text="Ввести время", callback_data="set_time_custom")
    ]
    keyboard.add(*buttons)
    return keyboard


def create_template_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton(text="Мои шаблоны", callback_data="view_templates"),
        InlineKeyboardButton(text="Создать шаблон", callback_data="create_template")
    ]
    keyboard.add(*buttons)
    return keyboard


@dp.callback_query_handler(lambda callback_query: callback_query.data == "view_templates")
async def view_templates(callback_query: types.CallbackQuery):
    if callback_query.from_user.id == CREATOR_ID:
        if not scheduled_messages:
            # Добавляем кнопку "Создать шаблон"
            keyboard = InlineKeyboardMarkup(row_width=1)
            create_template_button = InlineKeyboardButton(text="Создать шаблон", callback_data="create_template")
            back_button = InlineKeyboardButton(text="Назад", callback_data="main_menu")
            keyboard.add(create_template_button, back_button)

            await callback_query.message.edit_text("У вас нет созданных шаблонов.", reply_markup=keyboard)
        else:
            # Собираем информацию о шаблонах
            keyboard = InlineKeyboardMarkup(row_width=1)
            for weekday, templates in scheduled_messages.items():
                translated_weekday = weekdays_translation[weekday]
                for index, template in enumerate(templates):
                    time = template['time'].strftime('%H:%M')
                    content = template['content']
                    button_text = f"{translated_weekday} в {time}: {content.text if content.text else 'Медиа'}"
                    button_callback_data = f"select_template_{weekday}_{index}"
                    keyboard.add(InlineKeyboardButton(text=button_text, callback_data=button_callback_data))

            # Добавляем кнопку "Назад"
            back_button = InlineKeyboardButton(text="Назад", callback_data="main_menu")
            keyboard.add(back_button)

            await callback_query.message.edit_text("Ваши шаблоны:", reply_markup=keyboard)
    else:
        await callback_query.answer("У вас нет прав для выполнения этой команды.", show_alert=True)


@dp.callback_query_handler(lambda callback_query: callback_query.data.startswith("select_template_"))
async def select_template(callback_query: types.CallbackQuery):
    if callback_query.from_user.id == CREATOR_ID:
        data = callback_query.data.split("_")
        weekday = data[2]
        index = int(data[3])

        template = scheduled_messages[weekday][index]
        time = template['time'].strftime('%H:%M')
        content = template['content']

        # Создаем кнопки для редактирования или удаления шаблона
        keyboard = InlineKeyboardMarkup(row_width=1)
        delete_button = InlineKeyboardButton(text="Удалить", callback_data=f"delete_template_{weekday}_{index}")
        back_button = InlineKeyboardButton(text="Назад", callback_data="view_templates")
        keyboard.add(delete_button, back_button)

        await callback_query.message.edit_text(
            f"Шаблон для {weekdays_translation[weekday]} в {time}:\n{content.text if content.text else 'Медиа'}",
            reply_markup=keyboard
        )
    else:
        await callback_query.answer("У вас нет прав для выполнения этой команды.", show_alert=True)


@dp.callback_query_handler(lambda callback_query: callback_query.data.startswith("delete_template_"))
async def delete_template(callback_query: types.CallbackQuery):
    if callback_query.from_user.id == CREATOR_ID:
        data = callback_query.data.split("_")
        weekday = data[2]
        index = int(data[3])

        # Удаляем шаблон
        del scheduled_messages[weekday][index]
        if not scheduled_messages[weekday]:
            del scheduled_messages[weekday]

        await callback_query.answer("Шаблон удален.", show_alert=True)

        # Возвращаемся к списку шаблонов
        await view_templates(callback_query)
    else:
        await callback_query.answer("У вас нет прав для выполнения этой команды.", show_alert=True)


def create_weekday_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton(text="Понедельник", callback_data="weekday_monday"),
        InlineKeyboardButton(text="Вторник", callback_data="weekday_tuesday"),
        InlineKeyboardButton(text="Среда", callback_data="weekday_wednesday"),
        InlineKeyboardButton(text="Четверг", callback_data="weekday_thursday"),
        InlineKeyboardButton(text="Пятница", callback_data="weekday_friday"),
        InlineKeyboardButton(text="Суббота", callback_data="weekday_saturday"),
        InlineKeyboardButton(text="Воскресенье", callback_data="weekday_sunday"),
        InlineKeyboardButton(text="Вернуться в меню", callback_data="main_menu")
    ]
    keyboard.add(*buttons)
    return keyboard


def create_main_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton(text="Установить время админа", callback_data="set_admin_time"),
        InlineKeyboardButton(text="Планирование сообщений", callback_data="schedule_message")
    ]
    keyboard.add(*buttons)
    return keyboard


@dp.callback_query_handler(lambda callback_query: callback_query.data == "main_menu", state="*")
async def return_to_main_menu(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id == CREATOR_ID:
        keyboard = create_main_menu()
        await callback_query.message.edit_text("Вы вернулись в главное меню.", reply_markup=keyboard)
        await state.finish()  # Завершаем текущее состояние
    else:
        await callback_query.answer("У вас нет прав для выполнения этой команды.", show_alert=True)


async def update_admin_button():
    if CHANNEL_ID in current_messages:
        try:
            await bot.delete_message(chat_id=CHANNEL_ID, message_id=current_messages[CHANNEL_ID])
            logging.info(f"{datetime.now()} - Удалена предыдущая кнопка для сообщения {current_messages[CHANNEL_ID]}")
        except Exception as e:
            logging.error(f"{datetime.now()} - Ошибка при удалении предыдущей кнопки: {e}")

    # Создаем новую Inline кнопку для предоставления прав администратора
    keyboard = InlineKeyboardMarkup()
    button = InlineKeyboardButton(text="💬", callback_data=f"promote_{datetime.now().timestamp()}")
    keyboard.add(button)

    try:
        # Отправляем сообщение с кнопкой в канал
        sent_message = await bot.send_message(
            chat_id=CHANNEL_ID,
            text="Создать и опубликовать пост",
            reply_markup=keyboard
        )
        current_messages[CHANNEL_ID] = sent_message.message_id
        logging.info(f"{datetime.now()} - Отправлена кнопка для нового сообщения")
    except Exception as e:
        logging.error(f"{datetime.now()} - Ошибка при отправке кнопки для нового сообщения: {e}")


@dp.channel_post_handler(content_types=['text', 'photo', 'audio', 'video', 'document'])
async def on_post(message: types.Message):
    if message.chat.id == CHANNEL_ID:
        await update_admin_button()


@dp.callback_query_handler(lambda callback_query: callback_query.data.startswith("promote_"))
async def on_publish_post(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    try:
        # Проверка, что бот является администратором канала
        chat = await bot.get_chat(CHANNEL_ID)
        if chat.type != 'channel':
            await callback_query.answer("Бот должен быть администратором канала.")
            logging.error(f"{datetime.now()} - Бот не является администратором канала.")
            return

        # Проверяем, является ли пользователь владельцем канала
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status == 'creator':
            await callback_query.answer("Вы уже являетесь владельцем канала.")
            logging.info(f"{datetime.now()} - Пользователь {user_id} является владельцем канала.")
            return

        # Предоставляем права администратора
        await bot.promote_chat_member(
            chat_id=CHANNEL_ID,
            user_id=user_id,
            can_post_messages=True,
        )

        await callback_query.answer(f"Пожалуйста, создайте и опубликуйте свой пост.")
        logging.info(
            f"{datetime.now()} - Пользователь {user_id} получил права администратора на {admin_time_minutes} минут")

        # Ожидаем указанное время перед отзывом прав администратора
        await asyncio.sleep(admin_time_minutes * 60)

        # Отзываем права администратора
        await revoke_admin_rights(user_id)

    except Exception as e:
        logging.error(f"{datetime.now()} - Ошибка при предоставлении прав администратора пользователю {user_id}: {e}")


async def revoke_admin_rights(user_id):
    try:
        # Понижаем пользователя до обычного участника
        await bot.promote_chat_member(
            chat_id=CHANNEL_ID,
            user_id=user_id,
            can_post_messages=False,
            can_edit_messages=False,
            can_delete_messages=False,
            can_invite_users=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False,
            can_manage_chat=False,
            can_manage_voice_chats=False,
            can_change_info=False
        )
        logging.info(f"{datetime.now()} - Права администратора отозваны у пользователя {user_id}")

    except Exception as e:
        logging.error(f"{datetime.now()} - Ошибка при отзыве прав администратора у пользователя {user_id}: {e}")


@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    if message.from_user.id == CREATOR_ID:
        keyboard = create_main_menu()
        await message.answer("Добро пожаловать! Выберите действие:", reply_markup=keyboard)
    else:
        await message.answer("У вас нет прав для использования этого бота.")


@dp.callback_query_handler(lambda callback_query: callback_query.data == "set_admin_time")
async def set_admin_time(callback_query: types.CallbackQuery):
    if callback_query.from_user.id == CREATOR_ID:
        keyboard = create_time_keyboard()
        await callback_query.message.edit_text("Выберите время для предоставления прав администратора:",
                                               reply_markup=keyboard)
    else:
        await callback_query.answer("У вас нет прав для выполнения этой команды.", show_alert=True)


@dp.callback_query_handler(lambda callback_query: callback_query.data == "set_time_custom")
async def set_time_custom(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text(
        "Пожалуйста, введите время в минутах для предоставления прав администратора:")
    await AdminTime.waiting_for_custom_time.set()


@dp.message_handler(state=AdminTime.waiting_for_custom_time)
async def process_custom_time(message: types.Message, state: FSMContext):
    global admin_time_minutes
    try:
        admin_time_minutes = int(message.text)
        # Добавляем кнопку "Вернуться в меню"
        keyboard = InlineKeyboardMarkup(row_width=1)
        back_button = InlineKeyboardButton(text="Вернуться в меню", callback_data="main_menu")
        keyboard.add(back_button)

        await message.answer(
            f"Время для предоставления прав администратора установлено на {admin_time_minutes} минут.",
            reply_markup=keyboard)
        await state.finish()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")


@dp.callback_query_handler(lambda callback_query: callback_query.data == "schedule_message")
async def schedule_message(callback_query: types.CallbackQuery):
    if callback_query.from_user.id == CREATOR_ID:
        keyboard = create_template_menu()
        await callback_query.message.edit_text("Выберите действие:", reply_markup=keyboard)
    else:
        await callback_query.answer("У вас нет прав для выполнения этой команды.", show_alert=True)


@dp.callback_query_handler(lambda callback_query: callback_query.data == "create_template")
async def create_template(callback_query: types.CallbackQuery):
    if callback_query.from_user.id == CREATOR_ID:
        keyboard = create_weekday_keyboard()
        await callback_query.message.edit_text("Выберите день недели:", reply_markup=keyboard)
        await ScheduleTemplate.waiting_for_day.set()  # Переводим состояние в ожидание дня недели
    else:
        await callback_query.answer("У вас нет прав для выполнения этой команды.", show_alert=True)


@dp.callback_query_handler(lambda callback_query: callback_query.data.startswith("weekday_"),
                           state=ScheduleTemplate.waiting_for_day)
async def process_weekday(callback_query: types.CallbackQuery, state: FSMContext):
    weekday = callback_query.data.split("_")[1]
    translated_weekday = weekdays_translation[weekday]
    await state.update_data(weekday=weekday)

    # Добавляем кнопку "Назад"
    keyboard = InlineKeyboardMarkup(row_width=1)
    back_button = InlineKeyboardButton(text="Назад", callback_data="main_menu")
    keyboard.add(back_button)

    await callback_query.message.edit_text(f"Выбран день недели: {translated_weekday}")
    await callback_query.message.answer("Пожалуйста, введите время в формате ЧЧ:ММ", reply_markup=keyboard)
    await ScheduleTemplate.waiting_for_time.set()


@dp.message_handler(state=ScheduleTemplate.waiting_for_time)
async def process_template_time(message: types.Message, state: FSMContext):
    try:
        time = datetime.strptime(message.text, "%H:%M").time()
        await state.update_data(time=time)

        # Добавляем кнопку "Назад"
        keyboard = InlineKeyboardMarkup(row_width=1)
        back_button = InlineKeyboardButton(text="Назад", callback_data="create_template")
        keyboard.add(back_button)

        await message.answer("Пожалуйста, введите сообщение для планирования:", reply_markup=keyboard)
        await ScheduleTemplate.waiting_for_message.set()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное время в формате ЧЧ:ММ.")


@dp.message_handler(state=ScheduleTemplate.waiting_for_message, content_types=types.ContentType.ANY)
async def process_template_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    weekday = data.get("weekday")
    time = data.get("time")

    if weekday not in scheduled_messages:
        scheduled_messages[weekday] = []

    scheduled_messages[weekday].append({
        'time': time,
        'content_type': message.content_type,
        'content': message
    })

    translated_weekday = weekdays_translation[weekday]
    await message.answer(f"Сообщение для {translated_weekday} в {time.strftime('%H:%M')} запланировано.")
    await state.finish()

    keyboard = create_main_menu()
    await message.answer("Вы вернулись в главное меню.", reply_markup=keyboard)


async def scheduler():
    moscow_tz = pytz.timezone('Europe/Moscow')

    while True:
        now = datetime.now(moscow_tz)
        current_weekday = now.strftime("%A").lower()
        current_time = now.time()
        logging.info(f"{datetime.now()} - Текущий день: {current_weekday}, текущее время: {current_time}")

        if current_weekday in scheduled_messages:
            for template in scheduled_messages[current_weekday]:
                last_sent_key = f"{current_weekday}_{template['time']}"
                last_sent_date = last_sent_dates.get(last_sent_key)

                if (last_sent_date != now.date() and
                        template['time'].hour == current_time.hour and
                        template['time'].minute == current_time.minute):

                    logging.info(f"{datetime.now()} - Время отправки запланированного сообщения: {template['time']}")

                    content_type = template['content_type']
                    content = template['content']

                    try:
                        if content_type == 'text':
                            await bot.send_message(chat_id=CHANNEL_ID, text=content.text)
                        elif content_type == 'photo':
                            await bot.send_photo(chat_id=CHANNEL_ID, photo=content.photo[-1].file_id,
                                                 caption=content.caption)
                        elif content_type == 'video':
                            await bot.send_video(chat_id=CHANNEL_ID, video=content.video.file_id,
                                                 caption=content.caption)
                        elif content_type == 'audio':
                            await bot.send_audio(chat_id=CHANNEL_ID, audio=content.audio.file_id,
                                                 caption=content.caption)
                        elif content_type == 'document':
                            await bot.send_document(chat_id=CHANNEL_ID, document=content.document.file_id,
                                                    caption=content.caption)

                        last_sent_dates[last_sent_key] = now.date()
                        logging.info(
                            f"{datetime.now()} - Отправлено запланированное сообщение на {current_weekday} в {template['time']}")

                        # Обновление кнопки после отправки запланированного сообщения
                        await update_admin_button()

                    except Exception as e:
                        logging.error(f"{datetime.now()} - Ошибка при отправке запланированного сообщения: {e}")

        await asyncio.sleep(60)

def escape_markdown_v2(text):
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

@dp.message_handler(content_types=types.ContentType.ANY, chat_id=DISCUSSION_GROUP_ID)
async def handle_discussion_message(message: types.Message):
    # Проверяем, что сообщение является ответом на другое сообщение
    if message.reply_to_message:
        commenter = escape_markdown_v2(message.from_user.username)
        original_message = message.reply_to_message

        # Выводим идентификатор исходного сообщения в лог для проверки
        print(f"ID исходного сообщения: {original_message.message_id}")

        if original_message.text:
            original_message_text = escape_markdown_v2(original_message.text[:30])
        elif original_message.caption:
            original_message_text = escape_markdown_v2(original_message.caption[:30])
        else:
            original_message_text = 'Медиа'

        # Формируем ссылку на оригинальное сообщение
        original_message_link = f"t.me/c/2225022005/{original_message.message_id}?thread={original_message.message_id}"
        print(f"Ссылка на исходное сообщение: {original_message_link}")

        notification_text = (
            f"Пользователь @{commenter} оставил новый комментарий к публикации "
            f"[{original_message_text}]({original_message_link})"
        )

        try:
            # Отправляем уведомление с кликабельной ссылкой
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=notification_text,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True  # Опционально, чтобы предотвратить открытие страницы веб-предварительного просмотра
            )

            # Обновляем кнопку после отправки уведомления
            await update_admin_button()

        except Exception as e:
            logging.error(f"Ошибка при отправке уведомления: {e}")


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler())
    executor.start_polling(dp, skip_updates=True)
