import os
import base64
from io import BytesIO
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import requests 
import hashlib
import re
import sqlite3
import datetime
from datetime import date
from flask import Flask, render_template, request, Response, make_response
from flask_wtf import FlaskForm
from wtforms import SubmitField, FloatField, HiddenField
from wtforms.validators import DataRequired, NumberRange, ValidationError
from flask_wtf.file import FileField, FileAllowed, FileRequired
from flask_bootstrap import Bootstrap5
from werkzeug.utils import secure_filename
import json
import lxml.etree as ET

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('uploads.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS files
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  filename TEXT,
                  size INTEGER,
                  upload_time TEXT)''')
    conn.commit()
    conn.close()

init_db()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_KEY = 'secret_key_here'
app.config['SECRET_KEY'] = SECRET_KEY

# --- КЛЮЧИ ЯНДЕКС SMART CAPTCHA ---
app.config['YANDEX_CAPTCHA_CLIENT_KEY'] = 'ysc1_AJeBSoopTbBmuVfjI9i1XjOlp0KKGTJMr5o4csh8e8556fd9'
app.config['YANDEX_CAPTCHA_SERVER_KEY'] = os.environ.get('YANDEX_CAPTCHA_SERVER_KEY', 'ВСТАВЬ_КЛЮЧ_СЮДА_ВРУЧНУЮ')

bootstrap = Bootstrap5(app)
 
class BlendForm(FlaskForm):
    alpha = FloatField('Alpha (0 to 1)', validators=[DataRequired(), NumberRange(min=0, max=1)], default=0.5)
    upload1 = FileField('First Image', validators=[FileRequired(), FileAllowed(['jpg', 'png', 'jpeg'])])
    upload2 = FileField('Second Image', validators=[FileRequired(), FileAllowed(['jpg', 'png', 'jpeg'])])
    # Скрытое поле для токена капчи
    smart_token = HiddenField()
    submit = SubmitField('Mix Images')

    # Валидация капчи
    def validate_smart_token(self, field):
        token = field.data
        if not token:
            raise ValidationError('Пожалуйста, подтвердите, что вы не робот.')

        server_key = app.config['YANDEX_CAPTCHA_SERVER_KEY']
        url = 'https://smartcaptcha.yandexcloud.net/validate'
        data = {
            'secret': server_key,
            'token': token,
            'ip': request.remote_addr
        }
        
        try:
            response = requests.post(url, data=data, timeout=5)
            result = response.json()
            if result.get('status') != 'ok':
                raise ValidationError('Капча не пройдена. Попробуйте еще раз.')
        except Exception as e:
            raise ValidationError('Ошибка проверки капчи. Попробуйте позже.')

def process_images(path1, path2, alpha):
    img1 = Image.open(path1).resize((224, 224)).convert('RGB')
    img2 = Image.open(path2).resize((224, 224)).convert('RGB')
    arr1 = np.array(img1) / 255.0
    arr2 = np.array(img2) / 255.0
    mixed_arr = arr1 * alpha + arr2 * (1 - alpha)
    res_img = Image.fromarray((mixed_arr * 255).astype(np.uint8))
    return arr1, arr2, mixed_arr, res_img

def make_plot(arr1, arr2, mixed_arr):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    colors = ['red', 'green', 'blue']
    for i, color in enumerate(colors):
        axes[i].hist(arr1[:,:,i].ravel(), bins=50, color=color, alpha=0.3, label='Img 1')
        axes[i].hist(arr2[:,:,i].ravel(), bins=50, color=color, alpha=0.3, label='Img 2', histtype='step')
        axes[i].hist(mixed_arr[:,:,i].ravel(), bins=50, color=color, alpha=0.7, label='Mixed', histtype='step', linewidth=2)
        axes[i].set_title(f'{color.upper()} Channel')
        axes[i].legend()
    img_io = BytesIO()
    plt.savefig(img_io, format='png', bbox_inches='tight')
    img_io.seek(0)
    plot_url = base64.b64encode(img_io.getvalue()).decode('utf8')
    plt.close()
    return plot_url

@app.route("/", methods=['GET', 'POST'])
@app.route("/net", methods=['GET', 'POST'])
def net():
    form = BlendForm()
    result_image_url = None
    plot_url = None

    if form.validate_on_submit():
        alpha = form.alpha.data
        static_dir = os.path.join(BASE_DIR, 'static')
        os.makedirs(static_dir, exist_ok=True)

        path1 = os.path.join(static_dir, secure_filename(form.upload1.data.filename))
        path2 = os.path.join(static_dir, secure_filename(form.upload2.data.filename))
        form.upload1.data.save(path1)
        form.upload2.data.save(path2)

        # Сохраняем информацию о файлах в БД
        conn = sqlite3.connect('uploads.db')
        c = conn.cursor()
        for f, path in [(form.upload1.data, path1), (form.upload2.data, path2)]:
            size = os.path.getsize(path)
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO files (filename, size, upload_time) VALUES (?, ?, ?)",
                      (f.filename, size, now))
        conn.commit()
        conn.close()


        arr1, arr2, mixed_arr, res_img = process_images(path1, path2, alpha)
        
        res_path = os.path.join(static_dir, 'result.png')
        res_img.save(res_path)
        result_image_url = 'result.png'
        plot_url = make_plot(arr1, arr2, mixed_arr)

    # Передаем публичный ключ капчи в шаблон
    return render_template('net.html', form=form, image_name=result_image_url, plot_url=plot_url, 
                           captcha_key=app.config['YANDEX_CAPTCHA_CLIENT_KEY'])

# --- API JSON и XML остаются без изменений ---
@app.route("/apinet", methods=['GET', 'POST'])
def apinet():
    if request.mimetype == 'application/json':
        data = request.get_json()
        filebytes = data['imagebin'].encode('utf-8')
        cfile = base64.b64decode(filebytes)
        img = Image.open(BytesIO(cfile))
        ret = json.dumps({"width": img.width, "height": img.height})
        return Response(response=ret, status=200, mimetype="application/json")
    return Response(response=json.dumps({"error": "Not JSON"}), status=400, mimetype="application/json")

@app.route("/apixml", methods=['GET', 'POST'])
def apixml():
    dom = ET.parse(os.path.join(BASE_DIR, "static", "xml", "file.xml"))
    xslt = ET.parse(os.path.join(BASE_DIR, "static", "xml", "file.xslt"))
    transform = ET.XSLT(xslt)
    newhtml = transform(dom)
    strfile = ET.tostring(newhtml)
    return strfile

# --- ЗАДАНИЕ НА ВЕРИФИКАЦИЮ ---
VERIFY_TOKEN = 'TUSUR-ANDREEVA-20261108-2A3FC1D3'  

def normalize_html(html: str) -> str:
    lines = [line.strip() for line in html.split('\n')]
    lines = [line for line in lines if line]
    lines = [re.sub(r'\s+', ' ', line) for line in lines]
    return '\n'.join(lines)

@app.route('/verify')
def verify():
    today = date.today().isoformat()
    html = f'''
    <html>
    <head><title>Verification</title></head>
    <body>
    <h1>Verification</h1>
    <p>Token: {VERIFY_TOKEN}</p>
    <p>Date: {today}</p>
    </body>
    </html>
    '''
    normalized = normalize_html(html)
    body_hash = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    response = make_response(html)
    response.headers['X-Verify-Hash'] = body_hash
    return response

@app.route('/files')
def show_files():
    conn = sqlite3.connect('uploads.db')
    c = conn.cursor()
    c.execute("SELECT filename, size, upload_time FROM files ORDER BY id DESC")
    files = c.fetchall()
    conn.close()
    
    html = "<h1>Загруженные файлы</h1><table border='1'><tr><th>Имя файла</th><th>Размер (байт)</th><th>Дата и время</th></tr>"
    for f in files:
        html += f"<tr><td>{f[0]}</td><td>{f[1]}</td><td>{f[2]}</td></tr>"
    html += "</table><br><a href='/'>На главную</a>"
    return html

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)