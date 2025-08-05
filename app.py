import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, g
from werkzeug.utils import secure_filename

# ── 設定 ─────────────────────────────────────────────────────────
BASE_DIR       = os.path.abspath(os.path.dirname(__file__))
DATABASE       = os.path.join(BASE_DIR, 'record.db')
UPLOAD_FOLDER  = os.path.join(BASE_DIR, 'static', 'images')
ALLOWED_EXT    = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.secret_key              = os.environ.get('SECRET_KEY', 'your_secret_key_here')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ── DB ヘルパー ───────────────────────────────────────────────────
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, '_database', None)
    if db:
        db.close()

# ── 初期化関数 ───────────────────────────────────────────────────
def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist TEXT NOT NULL,
            album TEXT NOT NULL,
            genre TEXT,
            year TEXT,
            store TEXT,
            filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS genres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            last_used TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            last_used TIMESTAMP
        );
    ''')
    db.commit()

# アプリ起動時／インポート時に必ず DB テーブルを初期化
with app.app_context():
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    init_db()

# ── ユーティリティ ────────────────────────────────────────────────
def update_choice(table, name):
    if not name:
        return
    db = get_db()
    now = datetime.utcnow().isoformat()
    cur = db.execute(f"SELECT id FROM {table} WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        db.execute(f"UPDATE {table} SET last_used = ? WHERE id = ?", (now, row['id']))
    else:
        db.execute(f"INSERT INTO {table}(name, last_used) VALUES(?, ?)", (name, now))
    db.commit()

def fetch_choices(table):
    db = get_db()
    rows = db.execute(f"SELECT name FROM {table} ORDER BY last_used DESC").fetchall()
    return [r['name'] for r in rows]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

# ── ルーティング ─────────────────────────────────────────────────
@app.route('/')
def root():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = False
    if request.method == 'POST':
        if request.form.get('username') == 'keito0301':
            session['logged_in'] = True
            return redirect(url_for('index'))
        error = True
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/index')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    db = get_db()
    cols = request.args.getlist('columns') or ['artist', 'album', 'created_at']

    # 検索条件（AND で結合）
    where, params = [], []
    free = request.args.get('search','').strip()
    if free:
        where.append("(artist LIKE ? OR album LIKE ?)")
        params += [f'%{free}%'] * 2

    # 詳細検索項目
    a = request.args.get('adv_artist','').strip()
    if a: where.append("artist LIKE ?");    params.append(f'%{a}%')
    b = request.args.get('adv_album','').strip()
    if b: where.append("album LIKE ?");     params.append(f'%{b}%')
    g0 = request.args.get('adv_genre','').strip()
    if g0: where.append("genre = ?");        params.append(g0)
    y1 = request.args.get('adv_year_start','').strip()
    y2 = request.args.get('adv_year_end','').strip()
    if y1 and y2:
        where.append("year BETWEEN ? AND ?"); params += [y1, y2]
    elif y1:
        where.append("year = ?");           params.append(y1)
    s0 = request.args.get('adv_store','').strip()
    if s0: where.append("store = ?");      params.append(s0)
    d1 = request.args.get('adv_date_start','').strip()
    d2 = request.args.get('adv_date_end','').strip()
    if d1 and d2:
        where.append("strftime('%Y-%m', created_at) BETWEEN ? AND ?")
        params += [d1, d2]
    elif d1:
        where.append("strftime('%Y-%m', created_at) = ?")
        params.append(d1)

    sql = "SELECT * FROM records"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC"
    records = db.execute(sql, params).fetchall()

    genres = fetch_choices('genres')
    stores = fetch_choices('stores')

    # 登録年月プルダウン生成
    min_date = db.execute("SELECT MIN(created_at) AS m FROM records").fetchone()['m']
    months = []
    if min_date:
        start = datetime.fromisoformat(min_date).replace(day=1)
        now   = datetime.utcnow().replace(day=1)
        y, m = start.year, start.month
        while (y, m) <= (now.year, now.month):
            months.append(f"{y:04d}-{m:02d}")
            m += 1
            if m == 13:
                m = 1; y += 1

    return render_template('index.html',
        records=records, columns=cols,
        all_columns=['artist','album','genre','year','store','created_at','filename'],
        genres=genres, stores=stores,
        search=free, adv_params=request.args,
        months=months
    )

@app.route('/add', methods=['GET','POST'])
def add():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    genres = fetch_choices('genres')
    stores = fetch_choices('stores')
    if request.method == 'POST':
        artist = request.form['artist'].strip()
        album  = request.form['album'].strip()
        genre  = request.form['genre'].strip()
        year   = request.form['year'].strip()
        store  = request.form['store'].strip()
        image  = request.files.get('image')
        fname  = None
        if image and allowed_file(image.filename):
            fname = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        db = get_db()
        db.execute(
            'INSERT INTO records(artist,album,genre,year,store,filename) VALUES(?,?,?,?,?,?)',
            (artist, album, genre, year, store, fname)
        )
        db.commit()
        update_choice('genres', genre)
        update_choice('stores', store)
        return redirect(url_for('index'))
    return render_template('add.html', genres=genres, stores=stores)

@app.route('/record/<int:record_id>')
def detail(record_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    record = get_db().execute(
        "SELECT * FROM records WHERE id = ?", (record_id,)
    ).fetchone()
    return render_template('detail.html', record=record)

@app.route('/record/<int:record_id>/edit', methods=['GET','POST'])
def edit(record_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    db     = get_db()
    record = db.execute(
        "SELECT * FROM records WHERE id = ?", (record_id,)
    ).fetchone()
    genres = fetch_choices('genres')
    stores = fetch_choices('stores')
    if request.method == 'POST':
        artist = request.form['artist'].strip()
        album  = request.form['album'].strip()
        genre  = request.form['genre'].strip()
        year   = request.form['year'].strip()
        store  = request.form['store'].strip()
        image  = request.files.get('image')
        fname  = record['filename']
        if image and allowed_file(image.filename):
            fname = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        db.execute(
            'UPDATE records SET artist=?,album=?,genre=?,year=?,store=?,filename=? WHERE id=?',
            (artist, album, genre, year, store, fname, record_id)
        )
        db.commit()
        update_choice('genres', genre)
        update_choice('stores', store)
        return redirect(url_for('index'))
    return render_template('edit.html', record=record, genres=genres, stores=stores)

@app.route('/record/<int:record_id>/delete', methods=['GET','POST'])
def delete(record_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    db     = get_db()
    record = db.execute(
        "SELECT * FROM records WHERE id = ?", (record_id,)
    ).fetchone()
    if request.method == 'POST':
        if request.form.get('confirm') == 'yes':
            db.execute("DELETE FROM records WHERE id = ?", (record_id,))
            db.commit()
            return redirect(url_for('index'))
        return redirect(url_for('detail', record_id=record_id))
    return render_template('confirm_delete.html', record=record)

# ── デバッグサーバ起動 ───────────────────────────────────────────
if __name__ == '__main__':
    # すでにインポート時に init_db＆static/images フォルダ生成済み
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
