import peewee as pw
from random import randint, shuffle
from dataclasses import dataclass

from config import DB_NAME, DB_DBMS


if DB_DBMS == 'sqlite':
    db = pw.SqliteDatabase(DB_NAME)
else:
    raise RuntimeError("Unavailable dbms '%s' (use 'sqlite')" % DB_DBMS)


class BaseModel(pw.Model):
    class Meta:
        database = db


class User(BaseModel):
    '''
    Пользователи. Пользователь регистрируется нажимая "/start".
    Fields:
        id:        int  - соответсвует user_id телеграмма (pk)
        amount:    int  - суммарный выигрыш
        superuser: bool - права администратора
    '''
    amount: int = pw.BigIntegerField(default=0)
    superuser: bool = pw.BooleanField(default=0)

    class Meta:
        db_table = 'Users'


class DifficultyLevel(BaseModel):
    '''
    Уровни сожности. По умолчанию их должно быть 15, как и вопросов.

    Fields:
        level: int - уровень (pk)
        cost:  int - цена за уровень
    '''
    level: int = pw.IntegerField(primary_key=True)
    cost: int = pw.IntegerField()

    class Meta:
        db_table = 'DifficultyLevels'

    def next_level(self):
        return DifficultyLevel.get_by_id(self.level+1)


class Question(BaseModel):
    '''
    База вопросов. У каждого вопроса есть сложность и текст.

    Fields:
        id:            int             - pk
        difficulty:    DifficultyLevel - уровень сложности вопроса
        question_text: str             - текст вопроса
    '''
    difficulty: DifficultyLevel = pw.ForeignKeyField(DifficultyLevel, 'level')
    question_text: str = pw.TextField()

    class Meta:
        db_table = 'Questions'

    def select_answers(self, count, condition):
        pool = list(QuestionDetails.filter(question=self, correct=condition))
        answers = list()
        while len(pool) > 0 and count > 0:
            count -= 1
            i = randint(0, len(pool) - 1)
            answers.append(pool.pop(i).answer)
        return answers

    def __str__(self) -> str:
        return self.question_text


class Answer(BaseModel):
    '''
    База ответов. Вопросы существуют отдельно от базы вопросов.

    Fields:
        id:          int - pk
        answer_text: str - текст ответа
    '''

    answer_text: str = pw.TextField()

    class Meta:
        db_table = 'Answers'

    def __str__(self) -> str:
        return self.answer_text


class QuestionDetails(BaseModel):
    '''
    Детали вопроса. Содержат информацию о том, какие ответы какому вопросу принадлежат.

    Fields:
        question: Question - вопрос (pk)
        answer:   Answer   - ответ (pk)
        correct:  bool     - верный ли ответ для данного вопроса
    '''
    question: Question = pw.ForeignKeyField(Question, 'id')
    answer: Answer = pw.ForeignKeyField(Answer, 'id')
    correct: bool = pw.BooleanField()

    class Meta:
        db_table = 'QuestionsDetails'
        primary_key = pw.CompositeKey('question', 'answer')


class Quest(BaseModel):
    '''
    Квест. Это уже готовый вопрос с 4 вариантами ответа.

    Fields:
        question: Question - 
        a:        Answer   -
        b:        Answer   -
        c:        Answer   -
        d:        Answer   -
    '''
    question: Question = pw.ForeignKeyField(Question, 'id')
    a: Answer = pw.ForeignKeyField(Answer, 'id')
    b: Answer = pw.ForeignKeyField(Answer, 'id')
    c: Answer = pw.ForeignKeyField(Answer, 'id')
    d: Answer = pw.ForeignKeyField(Answer, 'id')

    class Meta:
        db_table = 'Quests'

    @staticmethod
    def create_by_difficulty(difficulty):
        potential = list(Question.filter(difficulty=difficulty))

        while potential:
            i = randint(0, len(potential) - 1)
            question: Question = potential.pop(i)

            correct = question.select_answers(1, True)
            incorrect = question.select_answers(3, False)

            if len(correct) + len(incorrect) == 4:
                answers = correct + incorrect
                shuffle(answers)

                return Quest.get_or_create(
                    question=question,
                    a=answers[0],
                    b=answers[1],
                    c=answers[2],
                    d=answers[3]
                )[0]

    def get_correct(self, indx_or_var='var'):
        all_corects = list(map(lambda qd: qd.answer.answer_text,
                               QuestionDetails.filter(question=self.question, correct=True)))

        restype = (True if indx_or_var.startswith('v') else
                   False if indx_or_var.startswith('i') else None)

        if self.a.answer_text in all_corects:
            return 'A' if restype else 0
        elif self.b.answer_text in all_corects:
            return 'B' if restype else 1
        elif self.c.answer_text in all_corects:
            return 'C' if restype else 2
        elif self.d.answer_text in all_corects:
            return 'D' if restype else 3

    def excludes(self, indx_or_var='var'):
        answers = [self.a.answer_text,
                   self.b.answer_text,
                   self.c.answer_text,
                   self.d.answer_text]
        s_answers = sorted(answers)
        s_i = s_answers.index(answers[self.get_correct('indx')])
        i1 = answers.index(s_answers[(s_i + 1) % 4])
        i2 = answers.index(s_answers[(s_i + 2) % 4])

        restype = (True if indx_or_var.startswith('v') else
                   False if indx_or_var.startswith('i') else None)

        if restype:
            return ['A', 'B', 'C', 'D'][i1], ['A', 'B', 'C', 'D'][i2]
        else:
            return i1, i2


class GameSession(BaseModel):
    '''
    Игровая сессия содержит информацию об игроке, последнем заданном вопросе и использованных подсказках.

    Fields:
        id:                 int      - pk
        last_quest:         Quest    - квест, на котором остановился игрок
        player:             User     - игрок
        closed:             bool     - закрыта ли сессия?
        quest_50x50:        Quest    - на какой квест потрачена подсказка "50 на 50" ?
        quest_FriendCall:   Quest    - на какой квест потрачена подсказка "Звонок другу" ?
        quest_HallHelp:     Quest    - на какой квест потрачена подсказка "Помощь зала" ?
        quest_DoubleAnswer: Quest    - на какой квест потрачена подсказка "Право на ошибку" ?
    '''
    last_quest: Quest = pw.ForeignKeyField(Quest, 'id', null=True)
    player: User = pw.ForeignKeyField(User, 'id')
    closed: bool = pw.BooleanField(default=False)
    quest_50x50: Quest = pw.ForeignKeyField(Quest, 'id', null=True)
    quest_FriendCall: Quest = pw.ForeignKeyField(Quest, 'id', null=True)
    quest_HallHelp: Quest = pw.ForeignKeyField(Quest, 'id', null=True)
    quest_DoubleAnswer: Quest = pw.ForeignKeyField(Quest, 'id', null=True)

    class Meta:
        db_table = 'GameSessions'

    @staticmethod
    def get_actual(user):
        return GameSession.get_or_none(player=user, closed=False)

    def has_50x50(self):
        return self.quest_50x50 is None

    def has_FriendCall(self):
        return self.quest_FriendCall is None

    def has_HallHelp(self):
        return self.quest_HallHelp is None

    def has_DoubleAnswer(self):
        return self.quest_DoubleAnswer is None

    def has_any_hint(self):
        return (self.has_50x50() or self.has_FriendCall() or
                self.has_HallHelp() or self.has_DoubleAnswer())

    def setup_first_quest(self):
        self.last_quest = Quest.create_by_difficulty(difficulty=1)
        self.save()

    def next(self):
        lvl = self.last_quest.question.difficulty.level + 1

        if not (d := list(DifficultyLevel.filter(level=lvl))):
            return None

        self.last_quest = Quest.create_by_difficulty(difficulty=d[0])
        self.save()
        return self.last_quest

    def close(self):
        self.closed = True
        self.save()


db.create_tables([
    User,
    DifficultyLevel,
    Question,
    Answer,
    QuestionDetails,
    Quest,
    GameSession,
])


DifficultyLevel.get_or_create(cost=500)
DifficultyLevel.get_or_create(cost=1000)
DifficultyLevel.get_or_create(cost=2000)
DifficultyLevel.get_or_create(cost=3000)
DifficultyLevel.get_or_create(cost=5000)
DifficultyLevel.get_or_create(cost=10000)
DifficultyLevel.get_or_create(cost=15000)
DifficultyLevel.get_or_create(cost=25000)
DifficultyLevel.get_or_create(cost=50000)
DifficultyLevel.get_or_create(cost=100000)
DifficultyLevel.get_or_create(cost=200000)
DifficultyLevel.get_or_create(cost=400000)
DifficultyLevel.get_or_create(cost=800000)
DifficultyLevel.get_or_create(cost=1500000)
DifficultyLevel.get_or_create(cost=3000000)


q = Question.get_or_create(
    difficulty=1, question_text='Как называют манекенщицу супер-класса?')[0]
a = Answer.get_or_create(answer_text='Топ-модель')[0]
b = Answer.get_or_create(answer_text='Тяп-модель')[0]
c = Answer.get_or_create(answer_text='Поп-модель')[0]
d = Answer.get_or_create(answer_text='Ляп-модель')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=True)
QuestionDetails.get_or_create(question=q, answer=b, correct=False)
QuestionDetails.get_or_create(question=q, answer=c, correct=False)
QuestionDetails.get_or_create(question=q, answer=d, correct=False)

q = Question.get_or_create(
    difficulty=2, question_text='Кто вырос в джунглях среди диких зверей?')[0]
a = Answer.get_or_create(answer_text='Колобок')[0]
b = Answer.get_or_create(answer_text='Маугли')[0]
c = Answer.get_or_create(answer_text='Бэтмен')[0]
d = Answer.get_or_create(answer_text='Чарльз Дарвин')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=False)
QuestionDetails.get_or_create(question=q, answer=b, correct=True)
QuestionDetails.get_or_create(question=q, answer=c, correct=False)
QuestionDetails.get_or_create(question=q, answer=d, correct=False)

q = Question.get_or_create(
    difficulty=3, question_text='Как называлась детская развлекательная программа, популярная в прошлые годы?')[0]
a = Answer.get_or_create(answer_text='АБВГДейка')[0]
b = Answer.get_or_create(answer_text='ЁКЛМНейка')[0]
c = Answer.get_or_create(answer_text='ЁПРСТейка')[0]
d = Answer.get_or_create(answer_text='ЁЖЗИКейка')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=True)
QuestionDetails.get_or_create(question=q, answer=b, correct=False)
QuestionDetails.get_or_create(question=q, answer=c, correct=False)
QuestionDetails.get_or_create(question=q, answer=d, correct=False)

q = Question.get_or_create(
    difficulty=4, question_text='Как звали невесту Эдмона Дантеса, будущего графа Монте-Кристо?')[0]
a = Answer.get_or_create(answer_text='Мерседес')[0]
b = Answer.get_or_create(answer_text='Тойота')[0]
c = Answer.get_or_create(answer_text='Хонда')[0]
d = Answer.get_or_create(answer_text='Лада')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=True)
QuestionDetails.get_or_create(question=q, answer=b, correct=False)
QuestionDetails.get_or_create(question=q, answer=c, correct=False)
QuestionDetails.get_or_create(question=q, answer=d, correct=False)

q = Question.get_or_create(
    difficulty=5, question_text='Какой цвет получается при смешении синего и красного?')[0]
a = Answer.get_or_create(answer_text='Коричневый')[0]
b = Answer.get_or_create(answer_text='Фиолетовый')[0]
c = Answer.get_or_create(answer_text='Зелёный')[0]
d = Answer.get_or_create(answer_text='Голубой')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=False)
QuestionDetails.get_or_create(question=q, answer=b, correct=True)
QuestionDetails.get_or_create(question=q, answer=c, correct=False)
QuestionDetails.get_or_create(question=q, answer=d, correct=False)

q = Question.get_or_create(
    difficulty=6, question_text='Из какого мяса традиционно готовится начинка для чебуреков?')[0]
a = Answer.get_or_create(answer_text='Баранина')[0]
b = Answer.get_or_create(answer_text='Свинина')[0]
c = Answer.get_or_create(answer_text='Конина')[0]
d = Answer.get_or_create(answer_text='Телятина')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=True)
QuestionDetails.get_or_create(question=q, answer=b, correct=False)
QuestionDetails.get_or_create(question=q, answer=c, correct=False)
QuestionDetails.get_or_create(question=q, answer=d, correct=False)

q = Question.get_or_create(
    difficulty=7, question_text='Какой народ придумал танец чардаш?')[0]
a = Answer.get_or_create(answer_text='Венгры')[0]
b = Answer.get_or_create(answer_text='Румыны')[0]
c = Answer.get_or_create(answer_text='Чехи')[0]
d = Answer.get_or_create(answer_text='Молдаване')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=True)
QuestionDetails.get_or_create(question=q, answer=b, correct=False)
QuestionDetails.get_or_create(question=q, answer=c, correct=False)
QuestionDetails.get_or_create(question=q, answer=d, correct=False)

q = Question.get_or_create(
    difficulty=8, question_text='Изучение соединений какого элемента является основой органической химии?')[0]
a = Answer.get_or_create(answer_text='Кислород')[0]
b = Answer.get_or_create(answer_text='Углерод')[0]
c = Answer.get_or_create(answer_text='Азот')[0]
d = Answer.get_or_create(answer_text='Кремний')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=False)
QuestionDetails.get_or_create(question=q, answer=b, correct=True)
QuestionDetails.get_or_create(question=q, answer=c, correct=False)
QuestionDetails.get_or_create(question=q, answer=d, correct=False)

q = Question.get_or_create(
    difficulty=9, question_text='Кто открыл тайну трёх карт графине из «Пиковой дамы» А. С. Пушкина?')[0]
a = Answer.get_or_create(answer_text='Казанова')[0]
b = Answer.get_or_create(answer_text='Калиостро')[0]
c = Answer.get_or_create(answer_text='Сен-Жермен')[0]
d = Answer.get_or_create(answer_text='Воган')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=False)
QuestionDetails.get_or_create(question=q, answer=b, correct=False)
QuestionDetails.get_or_create(question=q, answer=c, correct=True)
QuestionDetails.get_or_create(question=q, answer=d, correct=False)

q = Question.get_or_create(
    difficulty=10, question_text='В какой стране была пробурена первая промышленная нефтяная скважина?')[0]
a = Answer.get_or_create(answer_text='Кувейт')[0]
b = Answer.get_or_create(answer_text='Иран')[0]
c = Answer.get_or_create(answer_text='Ирак')[0]
d = Answer.get_or_create(answer_text='Азербайджан')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=False)
QuestionDetails.get_or_create(question=q, answer=b, correct=False)
QuestionDetails.get_or_create(question=q, answer=c, correct=False)
QuestionDetails.get_or_create(question=q, answer=d, correct=True)

q = Question.get_or_create(
    difficulty=11, question_text='Какой поэт написал: «Я очень люблю копчёную сельдь, и яйца, и жирный творог»?')[0]
a = Answer.get_or_create(answer_text='Джордж Байрон')[0]
b = Answer.get_or_create(answer_text='Генрих Гейне')[0]
c = Answer.get_or_create(answer_text='Поль Верлен')[0]
d = Answer.get_or_create(answer_text='Гавриил Державин')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=False)
QuestionDetails.get_or_create(question=q, answer=b, correct=True)
QuestionDetails.get_or_create(question=q, answer=c, correct=False)
QuestionDetails.get_or_create(question=q, answer=d, correct=False)

q = Question.get_or_create(
    difficulty=12, question_text='Что делали персонажи Шекспира в саду в четвертой сцене второго акта пьесы «Генрих VI»?')[0]
a = Answer.get_or_create(answer_text='закапывали сундук')[0]
b = Answer.get_or_create(answer_text='срывали розы')[0]
c = Answer.get_or_create(answer_text='собирали виноград')[0]
d = Answer.get_or_create(answer_text='играли в фанты')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=False)
QuestionDetails.get_or_create(question=q, answer=b, correct=True)
QuestionDetails.get_or_create(question=q, answer=c, correct=False)
QuestionDetails.get_or_create(question=q, answer=d, correct=False)

q = Question.get_or_create(
    difficulty=13, question_text='Кто в 1881 году был определен в Николаевский военный госпиталь как «вольнонаемный денщик ординатора Бертенсона»?')[0]
a = Answer.get_or_create(answer_text='композитор Мусоргский')[0]
b = Answer.get_or_create(answer_text='писатель Куприн')[0]
c = Answer.get_or_create(answer_text='художник Айвазовский')[0]
d = Answer.get_or_create(answer_text='хирург Пирогов')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=True)
QuestionDetails.get_or_create(question=q, answer=b, correct=False)
QuestionDetails.get_or_create(question=q, answer=c, correct=False)
QuestionDetails.get_or_create(question=q, answer=d, correct=False)

q = Question.get_or_create(
    difficulty=14, question_text='Из-за чего на самой знаменитой фотографии Уинстона Черчилля 1941 года у него такой сердитый вид?')[0]
a = Answer.get_or_create(answer_text='встал с похмелья')[0]
b = Answer.get_or_create(answer_text='встал с похмелья')[0]
c = Answer.get_or_create(answer_text='болел зуб')[0]
d = Answer.get_or_create(answer_text='фотограф отобрал сигару')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=False)
QuestionDetails.get_or_create(question=q, answer=b, correct=False)
QuestionDetails.get_or_create(question=q, answer=c, correct=False)
QuestionDetails.get_or_create(question=q, answer=d, correct=True)

q = Question.get_or_create(
    difficulty=15, question_text='Что запрещал указ, который в 1726 году подписала Екатерина I?')[0]
a = Answer.get_or_create(answer_text='Точить лясы')[0]
b = Answer.get_or_create(answer_text='Бить баклуши')[0]
c = Answer.get_or_create(answer_text='Пускать пыль в глаза')[0]
d = Answer.get_or_create(answer_text='Переливать из пустого в порожнее')[0]
QuestionDetails.get_or_create(question=q, answer=a, correct=False)
QuestionDetails.get_or_create(question=q, answer=b, correct=False)
QuestionDetails.get_or_create(question=q, answer=c, correct=True)
QuestionDetails.get_or_create(question=q, answer=d, correct=False)
