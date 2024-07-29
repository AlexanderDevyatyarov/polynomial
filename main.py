import json
from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
import numpy as np
import smtplib
import redis
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from celery import Celery
from config import Config
import sqlite3

#инициализируем приложение
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///new.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
app.config.from_object(Config)
app.secret_key = app.config['SECRET_KEY']
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)
engine=db.create_engine('sqlite:///new.db')
conn=engine.connect()
metadata=db.MetaData()

#создаем таблицу с данными
table1 = db.Table('table1', metadata,
                db.Column('id', db.Integer, primary_key=True),
                db.Column('email', db.String(100)),
                db.Column('polynomial', db.String(100)),
                db.Column('left_border', db.String(100)),
                db.Column('right_border', db.String(100)),
                db.Column('solution', db.String(100)))

metadata.create_all(engine)


#преобразование исходного полинома в список коэффициентов
def list_of_coef(polynomial):
    s1=[]
    if polynomial == 'x':
        coeff = [0] * 100
        coeff[0] = 1
        return coeff
    if polynomial == '-x':
        coeff = [0] * 100
        coeff[0] = -1
        return coeff
    s = polynomial.split('+')

    i = 0
    while i < len(s):
        if s[i] == "":
            del s[i]
            i = i - 1
        if s[i][0] != '-':
            s[i] = '+' + s[i]
        i = i + 1

    for i in range(len(s)):
        s1.append(s[i].split('-'))

    s2=[]
    for i in range(len(s1)):
        for j in range(len(s1[i])):
            s2.append(s1[i][j])

    i = 0
    while i<len(s2):
        if s2[i] == "":
            del s2[i]
        else:
            i += 1

    for i in range(len(s2)):
        if s2[i][0] != '+':
            s2[i] = '-'+s2[i]

    coeff = [0]*100


    for i in range(len(s2)):
        if "x^" in s2[i]:
            s2[i]=s2[i].split("x^")
            if s2[i][0] == '+' or s2[i][0] == '-':
                s2[i][0] = s2[i][0] + '1'
            coeff[int(s2[i][1])] = int(s2[i][0])
        elif "x" in s2[i]:
            s2[i] = s2[i].split('x')
            coeff[1] = int(s2[i][0])
        else:
            coeff[0] = int(s2[i])

    return(coeff)




#получение корней полинома с учетом граничных условий
def reshenie(coeff, left, right):
  roots = np.roots(coeff)
  X = (roots[np.isreal(roots)])
  lst=X.real
  i=0
  lst1=[]

  while i < len(lst):
    if lst[i]>=left and lst[i]<=right:
      lst1.append(lst[i])
    i=i+1

  return lst1



#функция для отправления решения по почте
def email_post(email, text):
    smtp_server = smtplib.SMTP("smtp.gmail.com", 587)
    smtp_server.starttls()
    smtp_server.login("r.ilai2016@gmail.com", "jzrk tdoj fuob varu")

    # Создание объекта сообщения
    msg = MIMEMultipart()

    # Настройка параметров сообщения
    msg["From"] = "your_email@gmail.com"
    msg["To"] = "recipient_email@example.com"
    msg["Subject"] = "Тестовое письмо 📧"

    # Добавление текста в сообщение
    msg.attach(MIMEText(text, "plain"))

    # Отправка письма
    smtp_server.sendmail("r.ilai2016@gmail.com", email, msg.as_string())

    # Закрытие соединения
    smtp_server.quit()



#объединение ранее рассмотренных функций в одну функцию universal и реализация очереди
@celery.task
def universal(polynomial, left, right, left_border, right_border, email):
    redis_client = redis.Redis()
    coef = list_of_coef(polynomial)
    solution = reshenie(coef[::-1], left, right)
    email_post(email, str(solution))
    redis_client.rpush(polynomial, left_border, right_border, str(solution))
    insertion_querty = table1.insert().values([
        {'polynomial': polynomial, 'left_border': left_border, 'right_border': right_border, 'solution': str(solution) }
    ])

    conn.execute(insertion_querty)
    conn.commit()



#инициализация главной страницы сайта
@app.route('/')
def index():
    return render_template('index.html')


#кэширование ранее полученных решений уравнения
@app.route('/', methods=['POST', 'GET'])
def create():
    if request.method == "POST":
        email = request.form['email']
        polynomial = request.form['polynomial']
        left_border = request.form['left_border']
        right_border = request.form['right_border']
        left = float(left_border)
        right = float(right_border)

        connection = sqlite3.connect(database='new.db')
        cursor = connection.cursor()
        redis_client = redis.Redis()

        cache_value = redis_client.lrange(name=polynomial, start=0, end=100)
        if cache_value == []:
            universal.apply_async(args=[polynomial, left, right, left_border, right_border, email])
        else:
            parametrs=redis_client.lrange(polynomial, 0, 100)
            if parametrs[0] == left_border and parametrs[1]==right_border:
                email_post(email, parametrs[2])
            else:
                universal.apply_async(args=[polynomial, left, right, left_border, right_border, email])

        cursor.close()
        redis_client.close()
        try:
            db.session.commit()
            return render_template('index.html')
        except:
            return render_template('index.html')
    return render_template('index.html')



#запуск приложения с включенным режимом дебага
if __name__ == "__main__":
    app.run(debug=True)