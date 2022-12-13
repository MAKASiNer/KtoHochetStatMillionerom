from random import choices, random
from telebot import TeleBot
from telebot.types import ReplyKeyboardMarkup, BotCommand
from telebot.formatting import hlink

from config import TG_TOKEN
from models import *


HINT_50X50 = '50 на 50'
HINT_FRIENDCALL = 'Звонок другу'
HINT_HALLHELP = 'Помощь зала'
HINT_DOUBLEANSWER = 'Право на ошибку'
USE_HINT = 'Использовать подсказку'
REPEAT_QUEST = 'Повторить вопрос'
CANCEL = 'Отменить'


bot = TeleBot(token=TG_TOKEN, parse_mode='html')


bot.set_my_commands([
    BotCommand('start', 'Приветсвие'),
    BotCommand('help', 'Помощь'),
    BotCommand('play', 'Начать или продолжить игру'),
    BotCommand('repeat_quest', 'Повторить вопрос'),
    BotCommand('hint', 'Использовать подсказку'),
])


def playlink():
    return hlink('/play', '/play')


def answers_markup(session):
    markup = ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=True
    )

    if (session.last_quest == session.quest_50x50):
        excludes = session.last_quest.excludes('var')
        var = []
        if 'A' not in excludes:
            var += ['A']
        if 'B' not in excludes:
            var += ['B']
        if 'C' not in excludes:
            var += ['C']
        if 'D' not in excludes:
            var += ['D']
        markup.add(*var, row_width=2)
    else:
        markup.add('A', 'B', 'C', 'D', row_width=2)

    return markup


def get_cur_session_handler(msg, session=None):
    if not session:
        session: GameSession = GameSession.get_actual(msg.from_user.id)

    if session is None:
        bot.send_message(
            chat_id=msg.chat.id,
            text=f'Ты еще не начал игру. Введи команда {playlink()} чтобы начать игру.'
        )
        return session

    return session


@bot.message_handler(commands=['start'])
def start_handler(msg):
    User.get_or_create(id=msg.from_user.id)
    bot.send_message(
        chat_id=msg.chat.id,
        text=f"Добро пожаловать. Введи команда {playlink()} чтобы начать игру.",
    )


@bot.message_handler(commands=['help'])
def help_handler(msg):
    bot.send_message(
        chat_id=msg.chat.id,
        text=('start        - Выводит приветсвие бота;\n'
              'help         - Выводит сообщение со списком команд;\n'
              'play         - Начать или продолжить игру;\n'
              'repeat_quest - Повторно напечатать вопрос;\n'
              'hint         - Воспользоваться подсказкой.\n'),
    )


@bot.message_handler(commands=['repeat_quest'])
def repeat_quest_handler(msg, session=None):
    if not (session := get_cur_session_handler(msg, session)):
        return

    text = (f'Вопрос №{session.last_quest.question.difficulty}\n'
            f'{session.last_quest.question}\n'
            f'• A) {session.last_quest.a}\n'
            f'• B) {session.last_quest.b}\n'
            f'• C) {session.last_quest.c}\n'
            f'• D) {session.last_quest.d}\n')

    bot.send_message(
        chat_id=msg.chat.id,
        text=text,
        reply_markup=answers_markup(session)
    )


@bot.message_handler(commands=['play'])
def play_handler(msg, session=None):
    if not session:
        session = GameSession.get_actual(msg.from_user.id)

    # открываем новую сессию если нет открытой
    if session is None:
        session = GameSession.create(player_id=msg.from_user.id, closed=False)
        session.setup_first_quest()
        repeat_quest_handler(msg)

    # спрашиваем "продолжить?" если открытая сессия есть
    else:
        markup = ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True,
        ).add('Продолжить', 'Начать новую', row_width=2)

        bot.send_message(
            chat_id=msg.chat.id,
            text='Ты уже в игре, хочешь продолжить или создать новую?',
            reply_markup=markup
        )

        bot.register_next_step_handler(msg, play_callback, session)


def play_callback(msg, session=None):
    if not session:
        session = GameSession.get_actual(msg.from_user.id)

    if msg.text == 'Продолжить':
        repeat_quest_handler(msg)

    elif msg.text == 'Начать новую':
        session.close()
        session = GameSession.create(player_id=msg.from_user.id, closed=False)
        session.setup_first_quest()
        repeat_quest_handler(msg)

    else:
        bot.send_message(
            chat_id=msg.chat.id,
            text='Я не понимаю твоего ответа.',
        )


@bot.message_handler(regexp=r'a|A|b|B|c|C|d|D')
def answer_handler(msg, session=None, scnd_answer=False):
    if not (session := get_cur_session_handler(msg, session)):
        return

    correct = session.last_quest.get_correct()
    user_var = msg.text.upper()

    if correct != user_var:

        # если право на ошибку, то спрашиваем 2 ответа
        if session.last_quest == session.quest_DoubleAnswer and not scnd_answer:
            markup = answers_markup(session)
            # исключая выбранный из вариантов
            for i, row in enumerate(markup.keyboard):
                if {'text': user_var} in row:
                    markup.keyboard[i].pop(row.index({'text': user_var}))
                    break
            bot.send_message(
                chat_id=msg.chat.id,
                text='Выбери второй варинат ответа',
                reply_markup=markup
            )
            # мы же не хотим, чтобы право на ошибку сработало опять
            bot.register_next_step_handler(msg, answer_handler, session, True)
            return

        # иначе просто проигрыш
        session.close()
        bot.send_message(
            chat_id=msg.chat.id,
            text=f'Ты ответил не правильно. Правильным ответом был вариант {correct}.'
        )
        return

    if not session.next():
        bot.send_message(
            chat_id=msg.chat.id,
            text=f'Поздравляю, ты победил!!!'
        )
        session.close()

    else:
        bot.send_message(
            chat_id=msg.chat.id,
            text=f'Ты ответил верно!'
        )
        repeat_quest_handler(msg, session)


@bot.message_handler(commands=['hint'])
def hint_handler(msg, session=None):
    if not (session := get_cur_session_handler(msg, session)):
        return

    if not session.has_any_hint():
        bot.send_message(
            chat_id=msg.chat.id,
            text='У тебя не осталось подсказок'
        )
        return

    markup = ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=True,
        row_width=2
    )
    if session.has_50x50():
        markup.add(HINT_50X50)
    if session.has_DoubleAnswer():
        markup.add(HINT_DOUBLEANSWER)
    if session.has_FriendCall():
        markup.add(HINT_FRIENDCALL)
    if session.has_HallHelp():
        markup.add(HINT_HALLHELP)
    markup.add(CANCEL, row_width=1)

    bot.send_message(
        chat_id=msg.chat.id,
        text='Выбери подсказку',
        reply_markup=markup
    )

    bot.register_next_step_handler(msg, hint_callback, session)


def hint_callback(msg, session=None):
    if not (session := get_cur_session_handler(msg, session)):
        return

    if msg.text == HINT_50X50 and session.has_50x50():
        session.quest_50x50 = session.last_quest
        session.save()

    elif msg.text == HINT_DOUBLEANSWER and session.has_DoubleAnswer():
        session.quest_DoubleAnswer = session.last_quest
        session.save()

    elif msg.text == HINT_FRIENDCALL and session.has_FriendCall():
        session.quest_FriendCall = session.last_quest
        session.save()

        w = [1, 1, 1, 1]
        if session.quest_50x50 == session.last_quest:
            i1, i2 = session.last_quest.excludes('indx')
            w[i1], w[i2] = 0, 0
        i = session.last_quest.get_correct('indx')
        w[i] = 2 * (15 - session.last_quest.question.difficulty.level)

        bot.send_message(
            chat_id=msg.chat.id,
            text=f"Твой друг думает, что это вариант {choices(['A', 'B', 'C', 'D'], w)[0]}"
        )

    elif msg.text == HINT_HALLHELP and session.has_HallHelp():
        session.quest_HallHelp = session.last_quest
        session.save()

        w = [1, 1, 1, 1]
        if session.quest_50x50 == session.last_quest:
            i1, i2 = session.last_quest.excludes('indx')
            w[i1], w[i2] = 0, 0
        i = session.last_quest.get_correct('indx')
        w[i] = 2 * (15 - session.last_quest.question.difficulty.level)
        w = list(map(lambda x: x * random(), w))
        t = sum(w)

        text = (f'A) {100 * w[0] / t: 3.3f}%\n'
                f'B) {100 * w[1] / t: 3.3f}%\n'
                f'C) {100 * w[2] / t: 3.3f}%\n'
                f'D) {100 * w[3] / t: 3.3f}%\n')

        bot.send_message(
            chat_id=msg.chat.id,
            text=text
        )
        return

    elif msg.text != CANCEL:
        bot.send_message(
            chat_id=msg.chat.id,
            text='Такой подсказки нет.',
            reply_markup=answers_markup(session)
        )
        return

    bot.send_message(
        chat_id=msg.chat.id,
        text='Выбери вариант ответа',
        reply_markup=answers_markup(session)
    )


if __name__ == '__main__':
    bot.infinity_polling()
