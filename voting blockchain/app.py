import hashlib
import json
import datetime
import random
import os
import sqlite3
from flask import Flask, request, session, render_template_string, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "render-secure-key-change-it")

# ---------- CAPTCHA ----------
class Captcha:
    @staticmethod
    def generate():
        a = random.randint(1, 20)
        b = random.randint(1, 20)
        op = random.choice(['+', '-', '*'])
        if op == '+':
            return f"{a} + {b}", a + b
        elif op == '-':
            return f"{a} - {b}", a - b
        else:
            return f"{a} * {b}", a * b
    @staticmethod
    def verify(user_ans, correct):
        return user_ans == correct

# ---------- Блокчейн на SQLite ----------
DB_PATH = "blockchain.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            index INTEGER UNIQUE NOT NULL,
            votes_json TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            hash TEXT NOT NULL,
            nonce INTEGER NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS voters (
            voter_id TEXT PRIMARY KEY
        )
    ''')
    conn.commit()
    # Проверяем, есть ли генезис-блок
    c.execute("SELECT COUNT(*) FROM blocks")
    if c.fetchone()[0] == 0:
        # Создаём генезис-блок
        genesis = {
            "index": 0,
            "votes_json": json.dumps([]),
            "timestamp": str(datetime.datetime.now()),
            "prev_hash": "0",
            "nonce": 0,
            "hash": ""
        }
        genesis["hash"] = compute_hash(genesis)
        genesis = mine_block(genesis)
        c.execute('''
            INSERT INTO blocks (index, votes_json, timestamp, prev_hash, hash, nonce)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (genesis["index"], genesis["votes_json"], genesis["timestamp"],
              genesis["prev_hash"], genesis["hash"], genesis["nonce"]))
        conn.commit()
    conn.close()

def compute_hash(block):
    data = {
        "index": block["index"],
        "votes": json.loads(block["votes_json"]),
        "timestamp": block["timestamp"],
        "prev_hash": block["prev_hash"],
        "nonce": block["nonce"]
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

def mine_block(block, difficulty=3):
    target = "0" * difficulty
    while block["hash"][:difficulty] != target:
        block["nonce"] += 1
        block["hash"] = compute_hash(block)
    return block

def add_vote(voter_id, candidate):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Проверка, голосовал ли
    c.execute("SELECT 1 FROM voters WHERE voter_id = ?", (voter_id,))
    if c.fetchone():
        conn.close()
        return False
    # Получить последний блок
    c.execute("SELECT * FROM blocks ORDER BY index DESC LIMIT 1")
    last = c.fetchone()
    last_block = {
        "index": last[1],
        "votes_json": last[2],
        "timestamp": last[3],
        "prev_hash": last[4],
        "hash": last[5],
        "nonce": last[6]
    }
    new_index = last_block["index"] + 1
    vote = {
        "voter_id": voter_id,
        "candidate": candidate,
        "timestamp": str(datetime.datetime.now())
    }
    new_block = {
        "index": new_index,
        "votes_json": json.dumps([vote]),
        "timestamp": str(datetime.datetime.now()),
        "prev_hash": last_block["hash"],
        "nonce": 0,
        "hash": ""
    }
    new_block["hash"] = compute_hash(new_block)
    new_block = mine_block(new_block)
    c.execute('''
        INSERT INTO blocks (index, votes_json, timestamp, prev_hash, hash, nonce)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (new_block["index"], new_block["votes_json"], new_block["timestamp"],
          new_block["prev_hash"], new_block["hash"], new_block["nonce"]))
    c.execute("INSERT INTO voters (voter_id) VALUES (?)", (voter_id,))
    conn.commit()
    conn.close()
    return True

def get_results():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT votes_json FROM blocks ORDER BY index")
    rows = c.fetchall()
    conn.close()
    results = {}
    for row in rows:
        votes = json.loads(row[0])
        for v in votes:
            cand = v["candidate"]
            results[cand] = results.get(cand, 0) + 1
    return results

def is_chain_valid(difficulty=3):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM blocks ORDER BY index")
    rows = c.fetchall()
    conn.close()
    blocks = []
    for row in rows:
        blocks.append({
            "index": row[1],
            "votes_json": row[2],
            "timestamp": row[3],
            "prev_hash": row[4],
            "hash": row[5],
            "nonce": row[6]
        })
    for i, b in enumerate(blocks):
        if b["hash"] != compute_hash(b):
            return False
        if i > 0 and b["prev_hash"] != blocks[i-1]["hash"]:
            return False
        if b["hash"][:difficulty] != "0" * difficulty:
            return False
    return True

def get_all_blocks():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM blocks ORDER BY index")
    rows = c.fetchall()
    conn.close()
    blocks = []
    for row in rows:
        blocks.append({
            "index": row[1],
            "votes_json": row[2],
            "timestamp": row[3],
            "prev_hash": row[4],
            "hash": row[5],
            "nonce": row[6]
        })
    return blocks

# Инициализируем базу данных при старте
init_db()

# ---------- HTML-шаблоны ----------
MAIN_PAGE = """
<!DOCTYPE html>
<html>
<head><title>Блокчейн-голосование</title><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{font-family:Segoe UI;margin:0;padding:20px;background:#f0f2f5}.container{max-width:600px;margin:auto;background:white;padding:25px;border-radius:12px;box-shadow:0 2px 10px rgba(0,0,0,0.1)}h2{color:#2c3e50;text-align:center}.nav{text-align:center;margin-bottom:20px}.nav a{margin:0 10px;text-decoration:none;color:#3498db;font-weight:bold}label{font-weight:bold;display:block;margin-top:15px}input,select,button{width:100%;padding:10px;margin-top:5px;margin-bottom:10px;border:1px solid #ccc;border-radius:6px}button{background:#2ecc71;color:white;border:none;cursor:pointer}.message{padding:10px;border-radius:6px;margin-bottom:15px;text-align:center}.error{background:#f8d7da;color:#721c24}.success{background:#d4edda;color:#155724}footer{text-align:center;margin-top:20px;font-size:12px;color:#7f8c8d}
</style>
</head>
<body>
<div class="container">
<div class="nav"><a href="/">Голосование</a> | <a href="/results">Результаты</a> | <a href="/blockchain">Блокчейн</a></div>
<h2>🗳️ Электронное голосование</h2>
{% if message %}<div class="message {{ msg_type }}">{{ message }}</div>{% endif %}
<form method="post">
<label>Ваш уникальный ID:</label><input type="text" name="voter_id" required>
<label>Кандидат:</label><select name="candidate">
<option value="Кандидат 1">Кандидат 1</option>
<option value="Кандидат 2">Кандидат 2</option>
<option value="Кандидат 3">Кандидат 3</option>
</select>
<label>🔐 CAPTCHA: {{ captcha_q }} = ?</label><input type="number" name="captcha_answer" required>
<button type="submit">Проголосовать</button>
</form>
<footer>Один голос на человека. Голоса защищены блокчейном (Proof-of-Work).</footer>
</div>
</body>
</html>
"""

RESULTS_PAGE = """
<!DOCTYPE html>
<html><head><title>Результаты</title><style>body{font-family:Arial;margin:40px;background:#f0f2f5}.container{max-width:700px;margin:auto;background:white;padding:20px;border-radius:12px}.nav a{margin:0 10px}table{width:100%;border-collapse:collapse}th,td{border:1px solid #ddd;padding:8px;text-align:center}.valid{color:green}</style></head>
<body><div class="container"><div class="nav"><a href="/">Голосование</a> | <a href="/results">Результаты</a> | <a href="/blockchain">Блокчейн</a></div>
<h2>Результаты</h2><table>
<tr><th>Кандидат</th><th>Голосов</th></tr>
{% for cand,count in results.items() %}<tr><td>{{ cand }}</td><td>{{ count }}</td></tr>{% endfor %}
</table><p>Всего: {{ total_votes }}</p><p>Целостность блокчейна: <span class="valid">{{ "✓ Валидна" if is_valid else "✗ Нарушена" }}</span></p></div></body></html>
"""

BLOCKCHAIN_PAGE = """
<!DOCTYPE html>
<html><head><title>Блокчейн</title><style>body{font-family:monospace;margin:20px;background:#f0f2f5}.container{max-width:1200px;margin:auto;background:white;padding:20px;border-radius:12px}.block{border:1px solid #ccc;margin-bottom:20px;padding:10px;background:#fafafa}pre{background:#eee;padding:5px;overflow-x:auto}.valid{color:green}</style></head>
<body><div class="container"><div class="nav"><a href="/">Голосование</a> | <a href="/results">Результаты</a> | <a href="/blockchain">Блокчейн</a></div>
<h2>Блокчейн</h2><p>Проверка: {% if is_valid %}<span class="valid">✓ Валидна</span>{% else %}✗ Нарушена{% endif %}</p>
{% for block in chain %}<div class="block"><strong>Блок #{{ block.index }}</strong><br>Хеш: <code>{{ block.hash }}</code><br>Пред. хеш: <code>{{ block.prev_hash }}</code><br>Nonce: {{ block.nonce }}<br><strong>Голоса:</strong><pre>{{ block.votes | tojson(indent=2) }}</pre></div>{% endfor %}
</div></body></html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        voter_id = request.form.get('voter_id', '').strip()
        candidate = request.form.get('candidate', '').strip()
        captcha_answer = request.form.get('captcha_answer', '')
        if 'captcha_q' not in session or 'captcha_a' not in session:
            q, a = Captcha.generate()
            session['captcha_q'], session['captcha_a'] = q, a
            return render_template_string(MAIN_PAGE, captcha_q=q, message="Ошибка CAPTCHA", msg_type="error")
        try:
            user_ans = int(captcha_answer)
        except ValueError:
            q, a = Captcha.generate()
            session['captcha_q'], session['captcha_a'] = q, a
            return render_template_string(MAIN_PAGE, captcha_q=q, message="Введите число", msg_type="error")
        if not Captcha.verify(user_ans, session['captcha_a']):
            q, a = Captcha.generate()
            session['captcha_q'], session['captcha_a'] = q, a
            return render_template_string(MAIN_PAGE, captcha_q=q, message="Неверная CAPTCHA", msg_type="error")
        success = add_vote(voter_id, candidate)
        q, a = Captcha.generate()
        session['captcha_q'], session['captcha_a'] = q, a
        if success:
            return render_template_string(MAIN_PAGE, captcha_q=q, message=f"✓ Голос за {candidate} принят!", msg_type="success")
        else:
            return render_template_string(MAIN_PAGE, captcha_q=q, message="❌ Вы уже голосовали!", msg_type="error")
    q, a = Captcha.generate()
    session['captcha_q'], session['captcha_a'] = q, a
    return render_template_string(MAIN_PAGE, captcha_q=q, message=None)

@app.route('/results')
def results():
    res = get_results()
    total = sum(res.values())
    valid = is_chain_valid()
    return render_template_string(RESULTS_PAGE, results=res, total_votes=total, is_valid=valid)

@app.route('/blockchain')
def blockchain_view():
    blocks = get_all_blocks()
    for b in blocks:
        b["votes"] = json.loads(b["votes_json"])
    valid = is_chain_valid()
    return render_template_string(BLOCKCHAIN_PAGE, chain=blocks, is_valid=valid)

@app.route('/api/chain')
def api_chain():
    blocks = get_all_blocks()
    for b in blocks:
        b["votes"] = json.loads(b["votes_json"])
    return jsonify(blocks)

@app.route('/api/results')
def api_results():
    return jsonify(get_results())

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)