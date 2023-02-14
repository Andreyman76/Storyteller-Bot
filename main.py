import base64
import fnmatch
import os
import urllib
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import sqlite3

token = ''  # Bot token taken from @BotFather https://t.me/BotFather
admins = []  # Usernames that can upload files to the bot

bot = telebot.TeleBot(token)

localizations = {
    'ru': {
        'downloading': 'Загружаю...',
        'saved': 'Файл успешно сохранен',
        'file_error': 'Допускаются только файлы *.story',
        'select_story': 'Выберите рассказ из списка',
        'help': 'Введите /start, чтобы открыть выбор истории',
        'story_removed': 'Ой, похоже, что эта история была удалена',
        'no_stories': 'На данный момент нет рассказов для выбора',
    },
    'en': {
        'downloading': 'Loading...',
        'saved': 'File saved successfully',
        'file_error': 'Only *.story files are allowed',
        'select_story': 'Choose a story from the list',
        'help': 'Type /start to open the story selection',
        'story_removed': 'Oops, looks like this story has been deleted',
        'no_stories': 'There are currently no stories to choose from',
    }
}


def get_localized_string(language: str, string: str) -> str:
    if language != 'ru':
        return localizations['en'][string]

    return localizations['ru'][string]


def add_hidden_data(text: str, data) -> str:
    hidden_data = json.dumps(data).encode('utf8')
    hidden_data = base64.urlsafe_b64encode(hidden_data).decode('utf8')
    result = f'<a href="tg://btn/{hidden_data}">\u200b</a>{text}'

    return result


def get_hidden_data(html_text: str):
    hidden_data = html_text.split('<a href="tg://btn/')[1].split('">\u200b</a>')[0]
    hidden_data = base64.urlsafe_b64decode(hidden_data.encode('utf8'))
    result = json.loads(hidden_data.decode('utf8'))

    return result


@bot.message_handler(content_types=['document'])
def download_file(message: telebot.types.Message) -> None:
    if message.from_user.username in admins:
        lang = message.from_user.language_code
        name = message.document.file_name

        if '.' in name:
            extension = name.split('.')[-1]
            if extension == 'story':
                document_id = message.document.file_id
                file_info = bot.get_file(document_id)
                fi = file_info.file_path

                bot.send_message(chat_id=message.from_user.id,
                                 text=get_localized_string(lang, 'downloading'))

                urllib.request.urlretrieve(f'https://api.telegram.org/file/bot{token}/{fi}', f'./Stories/{name}')

                bot.send_message(chat_id=message.from_user.id,
                                 text=get_localized_string(lang, 'saved'))
                return

        bot.send_message(chat_id=message.from_user.id,
                         text=get_localized_string(lang, 'file_error'))
    pass


@bot.message_handler(commands=['start'])
def start_command(message: telebot.types.Message) -> None:
    files = os.listdir('./Stories/')
    pattern = "*.story"
    stories = []

    for entry in files:
        if fnmatch.fnmatch(entry, pattern):
            stories.append(entry)

    lang = message.from_user.language_code

    if len(stories) == 0:
        bot.send_message(chat_id=message.from_user.id, text=get_localized_string(lang, 'no_stories'))
        return

    hidden_data = {'action': 'select_story', 'lang': lang, 'stories': stories}
    text = get_localized_string(lang, 'select_story')
    text = add_hidden_data(text, hidden_data)
    buttons = InlineKeyboardMarkup()
    i = 0

    for story in stories:
        button = InlineKeyboardButton(text=story.replace('.story', ''), callback_data=str(i))
        buttons.add(button)
        i += 1

    bot.send_message(chat_id=message.from_user.id, text=text, reply_markup=buttons, parse_mode='HTML')
    pass


@bot.message_handler(commands=['help'])
def help_command(message: telebot.types.Message) -> None:
    bot.send_message(chat_id=message.from_user.id, text=get_localized_string(message.from_user.language_code, 'help'))
    pass


def print_story(chat_id, story_file: str, lang: str, story_id: str = None) -> None:
    filepath = f'./Stories/{story_file}'

    if not os.path.exists(filepath):
        bot.send_message(text=get_localized_string(lang, 'story_removed'), chat_id=chat_id)
        return

    connection = sqlite3.connect(filepath)
    cursor = connection.cursor()

    if story_id is None:
        cursor.execute('SELECT * FROM metadata LIMIT 1;')
        story_id = cursor.fetchone()[0]

    cursor.execute('SELECT text, image FROM stories WHERE id = (?) LIMIT 1;', (story_id,))
    record = cursor.fetchone()
    text = record[0]
    image = record[1]

    cursor.execute(f'SELECT name, to_id FROM transitions WHERE from_id = (?);', (story_id,))
    transitions = cursor.fetchall()

    connection.close()
    hidden_data = {'action': 'select_transition', 'lang': lang, 'story_file': story_file, 'transitions': transitions}
    text = add_hidden_data(text, hidden_data)
    buttons = InlineKeyboardMarkup()
    i = 0
    for transition in transitions:
        button = InlineKeyboardButton(text=transition[0], callback_data=str(i))
        buttons.add(button)
        i += 1

    if image is not None:
        bot.send_photo(chat_id=chat_id,
                       photo=image,
                       caption=text,
                       reply_markup=buttons,
                       parse_mode='HTML')
    else:
        bot.send_message(text=text,
                         chat_id=chat_id,
                         reply_markup=buttons,
                         parse_mode='HTML')
    pass


@bot.callback_query_handler(func=lambda x: True)
def callback_handler(callback: telebot.types.CallbackQuery):
    bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.id, reply_markup=None)
    chat_id = callback.from_user.id

    html_text = callback.message.html_text if callback.message.html_caption is None else callback.message.html_caption
    hidden_data = get_hidden_data(html_text)
    action = hidden_data['action']
    lang = hidden_data['lang']

    if action == 'select_story':
        stories = hidden_data['stories']
        story_file = stories[int(callback.data)]

        print_story(chat_id=chat_id, story_file=story_file, lang=lang)

    if action == 'select_transition':
        story_file = hidden_data['story_file']
        transitions = hidden_data['transitions']
        story_id = transitions[int(callback.data)][1]

        print_story(chat_id=chat_id, story_file=story_file, lang=lang, story_id=story_id)
    pass


if __name__ == '__main__':
    if not os.path.exists('./Stories/'):
        os.mkdir('./Stories/')
    print('Bot started')

    while True:
        try:
            bot.polling(none_stop=True, interval=2)
        except Exception as ex:
            print(ex)
