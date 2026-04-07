import hashlib
import json
import datetime
import random
import os
import sqlite3
from typing import List, Dict, Tuple
from flask import Flask, render_template_string, request, session, jsonify

# ---------------------------- CAPTCHA ----------------------------
class Captcha:
    @staticmethod
    def generate() -> Tuple[str, int]:
        a = random.randint(1, 20)
        b = random.randint(1, 20)
        op = random.choice(['+', '-', '*'])
        if op == '+':
            ans = a + b
            q = f"{a} + {b}"
        elif op == '-':
            ans = a - b
            q = f"{a} - {b}"
        else:
            ans = a * b
            q = f"{a} * {b}"
        return q, ans

    @staticmethod
    def verify(user_ans: int, correct: int) -> bool:
        return user_ans == correct


# ---------------------------- БЛОКЧЕЙН С SQLITE ----------------------------
class Block:
    def __init__(self, index: int, votes_json: str, timestamp: str, prev_hash: str, hash_val: str, nonce: int = 0):
        self.index = index
        self.votes_json = votes_json   # храним JSON-строку голосов
        self.timestamp = timestamp
        self.prev_hash = prev_hash
        self.hash = hash_val
        self.nonce = nonce

    def compute_hash(self) -> str:
        data = {
            "index": self.index,
            "votes": json.loads(self.votes_json),
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "nonce": self.nonce
        }
        block_str = json.dumps(data, sort_keys=True).encode()
        return hashlib.sha256(block_str).hexdigest()

    @staticmethod
    def mine_new_block(index: int, votes_list: List[Dict], timestamp: str, prev_hash: str, difficulty: int):
        votes_json = json.dumps(votes_list)
        nonce = 0
        target = "0" * difficulty
        while True:
            data = {
                "index": index,
                "votes": votes_list,
                "timestamp": timestamp,
                "prev_hash": prev_hash,
                "nonce": nonce
            }
            block_str = json.dumps(data, sort_keys=True).encode()
            hash_val = hashlib.sha256(block_str).hexdigest()
            if hash_val[:difficulty] == target:
                return Block(index, votes_json, timestamp, prev_hash, hash_val, nonce)
            nonce += 1


class BlockchainDB:
    def __init__(self, db_path: str = "blockchain.db", difficulty: int = 3):
        self.db_path = db_path
        self.difficulty = difficulty
        self.init_db()
        if self.get_last_block() is None:
            self.create_genesis_block()

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                index INTEGER UNIQUE,
                votes_json TEXT,
                timestamp TEXT,
                prev_hash TEXT,
                hash TEXT,
                nonce INTEGER
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS voters (
                voter_id TEXT PRIMARY KEY
            )
        ''')
        conn.commit()
        conn.close()

    def create_genesis_block(self):
        genesis = Block.mine_new_block(0, [], str(datetime.datetime.now()), "0", self.difficulty)
        self.add_block(genesis)

    def add_block(self, block: Block):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            INSERT INTO blocks (index, votes_json, timestamp, prev_hash, hash, nonce)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (block.index, block.votes_json, block.timestamp, block.prev_hash, block.hash, block.nonce))
        conn.commit()
        conn.close()

    def get_last_block(self) -> Block | None:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT index, votes_json, timestamp, prev_hash, hash, nonce FROM blocks ORDER BY index DESC LIMIT 1')
        row = c.fetchone()
        conn.close()
        if row:
            return Block(row[0], row[1], row[2], row[3], row[4], row[5])
        return None

    def get_all_blocks(self) -> List[Block]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT index, votes_json, timestamp, prev_hash, hash, nonce FROM blocks ORDER BY index')
        rows = c.fetchall()
        conn.close()
        return [Block(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows]

    def has_voter(self, voter_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT 1 FROM voters WHERE voter_id = ?', (voter_id,))
        exists = c.fetchone() is not None
        conn.close()
        return exists

    def add_voter(self, voter_id: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('INSERT INTO voters (voter_id) VALUES (?)', (voter_id,))
        conn.commit()
        conn.close()

    def add_vote(self, voter_id: str, candidate: str) -> bool:
        if self.has_voter(voter_id):
            return False
        last_block = self.get_last_block()
        new_index = last_block.index + 1
        vote = {
            "voter_id": voter_id,
            "candidate": candidate,
            "timestamp": str(datetime.datetime.now())
        }
        # Получаем все предыдущие голоса? Нет, каждый блок содержит только один голос (для простоты)
        # Но можно собрать все голоса из последнего блока? Нет, мы храним один голос на блок.
        # Однако для проверки целостности нам нужно сохранить список голосов в блоке. Пусть будет один голос.
        new_block = Block.mine_new_block(new_index, [vote], str(datetime.datetime.now()), last_block.hash, self.difficulty)
        self.add_block(new_block)
        self.add_voter(voter_id)
        return True

    def get_results(self) -> Dict[str, int]:
        results = {}
        blocks = self.get_all_blocks()
        for block in blocks:
            votes = json.loads(block.votes_json)
            for v in votes:
                cand = v["candidate"]
                results[cand] = results.get(cand, 0) + 1
        return results

    def is_chain_valid(self) -> bool:
        blocks = self.get_all_blocks()
        for i, block in enumerate(blocks):
            # проверка хеша
            if block.hash != block.compute_hash():
                print(f"Block {block.index} hash mismatch")
                return False
            if i > 0:
                prev = blocks[i-1]
                if block.prev_hash != prev.hash:
                    print(f"Block {block.index} prev_hash mismatch")
                    return False
            if block.hash[:self.difficulty] != "0" * self.difficulty:
                print(f"Block {block.index} invalid PoW")
                return False
        return True

    def to_dict_list(self) -> List[Dict]:
        blocks = self.get_all_blocks()
        return [{
            "index": b.index,
            "votes": json.loads(b.votes_json),
            "timestamp": b.timestamp,
            "prev_hash": b.prev_hash,
            "hash": b.hash,
            "nonce": b.nonce
        } for b in blocks]


# ---------------------------- ВЕБ-ПРИЛОЖЕНИЕ ----------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecret-key-for-voting")

# Инициализация блокчейна с SQLite
blockchain = BlockchainDB(db_path="blockchain.db", difficulty=3)

# HTML-шаблоны (те же, что и ранее, но с небольшими улучшениями)
MAIN_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Блокчейн-голосование</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #f0f2f5; }
        .container { max-width: 600px; margin: auto; background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h2 { color: #2c3e50; text-align: center; }
        .nav { text-align: center; margin-bottom: 20px; }
        .nav a { margin: 0 10px; text-decoration: none; color: #3498db; font-weight: bold; }
        .nav a:hover { text-decoration: underline; }
        label { font-weight: bold; display: block; margin-top: 15px; }
        input, select, button { width: 100%; padding: 10px; margin-top: 5px; margin-bottom: 10px; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
        button { background-color: #2ecc71; color: white; border: none; cursor: pointer; font-size: 16px; }
        button:hover { background-color: #27ae60; }
        .message { padding: 10px; border-radius: 6px; margin-bottom: 15px; text-align: center; }
        .error { background: #f8d7da; color: #721c24; }
        .success { background: #d4edda; color: #155724; }
        footer { text-align: center; margin-top: 20px; font-size: 12px; color: #7f8c8d; }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/">Голосование</a> |
            <a href="/results">Результаты</a> |
            <a href="/blockchain">Блокчейн</a>
        </div>
        <h2>🗳️ Электронное голосование</h2>
        {% if message %}
            <div class="message {{ msg_type }}">{{ message }}</div>
        {% endif %}
        <form method="post">
            <label>Ваш уникальный ID (паспорт, email, логин):</label>
            <input type="text" name="voter_id" required placeholder="например, ivanov2026">

            <label>Выберите кандидата:</label>
            <select name="candidate" required>
                <option value="Кандидат 1">Кандидат 1</option>
                <option value="Кандидат 2">Кандидат 2</option>
                <option value="Кандидат 3">Кандидат 3</option>
            </select>

            <label>🔐 Решите CAPTCHA: {{ captcha_q }} = ?</label>
            <input type="number" name="captcha_answer" required placeholder="Введите число">

            <button type="submit">Проголосовать</button>
        </form>
        <footer>Каждый избиратель может проголосовать только один раз.<br>Голоса защищены блокчейном (Proof-of-Work).</footer>
    </div>
</body>
</html>
"""

RESULTS_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Результаты голосования</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #f0f2f5; }
        .container { max-width: 700px; margin: auto; background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .nav { text-align: center; margin-bottom: 20px; }
        .nav a { margin: 0 10px; text-decoration: none; color: #3498db; font-weight: bold; }
        h2 { color: #2c3e50; text-align: center; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: center; }
        th { background-color: #f2f2f2; }
        .valid { color: green; font-weight: bold; }
        .invalid { color: red; font-weight: bold; }
        .total { text-align: center; margin-top: 20px; font-size: 18px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/">Голосование</a> |
            <a href="/results">Результаты</a> |
            <a href="/blockchain">Блокчейн</a>
        </div>
        <h2>📊 Текущие результаты</h2>
        <table>
            <tr><th>Кандидат</th><th>Голосов</th></tr>
            {% for cand, count in results.items() %}
            <tr><td>{{ cand }}</td><td>{{ count }}</td></tr>
            {% endfor %}
        </table>
        <div class="total">Всего проголосовало: <strong>{{ total_votes }}</strong></div>
        <div>Целостность блокчейна: 
            {% if is_valid %}
                <span class="valid">✓ ВАЛИДНА (не подделан)</span>
            {% else %}
                <span class="invalid">✗ НАРУШЕНА</span>
            {% endif %}
        </div>
        <p style="text-align:center; margin-top:20px;"><a href="/">← Вернуться к голосованию</a></p>
    </div>
</body>
</html>
"""

BLOCKCHAIN_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Блокчейн голосования</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: monospace; margin: 0; padding: 20px; background: #f0f2f5; }
        .container { max-width: 1200px; margin: auto; background: white; padding: 20px; border-radius: 12px; }
        .nav { text-align: center; margin-bottom: 20px; }
        .nav a { margin: 0 10px; text-decoration: none; color: #3498db; font-weight: bold; font-family: sans-serif; }
        h2 { color: #2c3e50; text-align: center; }
        .block { background: #fafafa; border: 1px solid #ddd; margin: 20px 0; padding: 15px; border-radius: 8px; overflow-x: auto; }
        .block pre { background: #eee; padding: 10px; border-radius: 5px; }
        .valid { color: green; }
        .invalid { color: red; }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/">Голосование</a> |
            <a href="/results">Результаты</a> |
            <a href="/blockchain">Блокчейн</a>
        </div>
        <h2>🔗 Блокчейн (неизменяемая цепочка)</h2>
        <p>Проверка целостности: 
            {% if is_valid %}
                <span class="valid">✓ ВАЛИДНА</span>
            {% else %}
                <span class="invalid">✗ НАРУШЕНА</span>
            {% endif %}
        </p>
        {% for block in chain %}
        <div class="block">
            <strong>Блок #{{ block.index }}</strong><br>
            Хеш: <code>{{ block.hash }}</code><br>
            Пред. хеш: <code>{{ block.prev_hash }}</code><br>
            Время: {{ block.timestamp }}<br>
            Nonce: {{ block.nonce }}<br>
            <strong>Голоса:</strong>
            <pre>{{ block.votes | tojson(indent=2) }}</pre>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        voter_id = request.form.get('voter_id', '').strip()
        candidate = request.form.get('candidate', '').strip()
        captcha_answer = request.form.get('captcha_answer', '')

        if not voter_id or not candidate:
            q, a = Captcha.generate()
            session['captcha_q'] = q
            session['captcha_a'] = a
            return render_template_string(MAIN_PAGE, captcha_q=q, message="Заполните все поля!", msg_type="error")

        if 'captcha_q' not in session or 'captcha_a' not in session:
            q, a = Captcha.generate()
            session['captcha_q'] = q
            session['captcha_a'] = a
            return render_template_string(MAIN_PAGE, captcha_q=q, message="Ошибка CAPTCHA, обновите страницу", msg_type="error")

        try:
            user_ans = int(captcha_answer)
        except ValueError:
            q, a = Captcha.generate()
            session['captcha_q'] = q
            session['captcha_a'] = a
            return render_template_string(MAIN_PAGE, captcha_q=q, message="Ответ должен быть числом", msg_type="error")

        if not Captcha.verify(user_ans, session['captcha_a']):
            q, a = Captcha.generate()
            session['captcha_q'] = q
            session['captcha_a'] = a
            return render_template_string(MAIN_PAGE, captcha_q=q, message="Неверная CAPTCHA, попробуйте ещё раз", msg_type="error")

        # CAPTCHA пройдена
        success = blockchain.add_vote(voter_id, candidate)
        q, a = Captcha.generate()
        session['captcha_q'] = q
        session['captcha_a'] = a

        if success:
            return render_template_string(MAIN_PAGE, captcha_q=q, message=f"✓ Голос за {candidate} принят! Спасибо.", msg_type="success")
        else:
            return render_template_string(MAIN_PAGE, captcha_q=q, message=f"❌ Избиратель {voter_id} уже проголосовал!", msg_type="error")

    # GET
    q, a = Captcha.generate()
    session['captcha_q'] = q
    session['captcha_a'] = a
    return render_template_string(MAIN_PAGE, captcha_q=q, message=None, msg_type=None)


@app.route('/results')
def results():
    results = blockchain.get_results()
    total = sum(results.values())
    is_valid = blockchain.is_chain_valid()
    return render_template_string(RESULTS_PAGE, results=results, total_votes=total, is_valid=is_valid)


@app.route('/blockchain')
def blockchain_view():
    chain_data = blockchain.to_dict_list()
    is_valid = blockchain.is_chain_valid()
    return render_template_string(BLOCKCHAIN_PAGE, chain=chain_data, is_valid=is_valid)


@app.route('/api/chain')
def api_chain():
    return jsonify(blockchain.to_dict_list())


@app.route('/api/results')
def api_results():
    return jsonify(blockchain.get_results())


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

