import hashlib
import json
import datetime
import random
import os
from typing import List, Dict, Tuple
from flask import Flask, render_template_string, request, session, jsonify

# ---------------------------- БЛОКЧЕЙН ----------------------------
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


class Block:
    def __init__(self, index: int, votes: List[Dict], timestamp: str, prev_hash: str, nonce: int = 0):
        self.index = index
        self.votes = votes
        self.timestamp = timestamp
        self.prev_hash = prev_hash
        self.nonce = nonce
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        data = {
            "index": self.index,
            "votes": self.votes,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "nonce": self.nonce
        }
        block_str = json.dumps(data, sort_keys=True).encode()
        return hashlib.sha256(block_str).hexdigest()

    def mine_block(self, difficulty: int):
        target = "0" * difficulty
        while self.hash[:difficulty] != target:
            self.nonce += 1
            self.hash = self.compute_hash()


class Blockchain:
    def __init__(self, difficulty: int = 3, storage_file: str = "blockchain.json"):
        self.difficulty = difficulty
        self.storage_file = storage_file
        self.chain: List[Block] = []
        self.voter_records: Dict[str, bool] = {}
        self.load_from_file()          # восстанавливаем цепочку из файла
        if not self.chain:
            self.create_genesis_block()
            self.save_to_file()

    def create_genesis_block(self):
        genesis = Block(0, [], str(datetime.datetime.now()), "0")
        genesis.mine_block(self.difficulty)
        self.chain.append(genesis)

    def get_latest_block(self) -> Block:
        return self.chain[-1]

    def add_vote(self, voter_id: str, candidate: str) -> bool:
        if voter_id in self.voter_records:
            return False
        vote = {
            "voter_id": voter_id,
            "candidate": candidate,
            "timestamp": str(datetime.datetime.now())
        }
        prev_block = self.get_latest_block()
        new_block = Block(
            index=prev_block.index + 1,
            votes=[vote],
            timestamp=str(datetime.datetime.now()),
            prev_hash=prev_block.hash
        )
        new_block.mine_block(self.difficulty)
        self.chain.append(new_block)
        self.voter_records[voter_id] = True
        self.save_to_file()
        return True

    def get_results(self) -> Dict[str, int]:
        results = {}
        for block in self.chain:
            for vote in block.votes:
                cand = vote["candidate"]
                results[cand] = results.get(cand, 0) + 1
        return results

    def is_chain_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            curr = self.chain[i]
            prev = self.chain[i-1]
            if curr.hash != curr.compute_hash():
                return False
            if curr.prev_hash != prev.hash:
                return False
            if curr.hash[:self.difficulty] != "0" * self.difficulty:
                return False
        return True

    def to_dict(self) -> List[Dict]:
        return [{
            "index": b.index,
            "votes": b.votes,
            "timestamp": b.timestamp,
            "prev_hash": b.prev_hash,
            "hash": b.hash,
            "nonce": b.nonce
        } for b in self.chain]

    def save_to_file(self):
        data = self.to_dict()
        with open(self.storage_file, "w") as f:
            json.dump(data, f, indent=2)

    def load_from_file(self):
        if not os.path.exists(self.storage_file):
            return
        try:
            with open(self.storage_file, "r") as f:
                data = json.load(f)
            self.chain = []
            for block_dict in data:
                block = Block(
                    index=block_dict["index"],
                    votes=block_dict["votes"],
                    timestamp=block_dict["timestamp"],
                    prev_hash=block_dict["prev_hash"],
                    nonce=block_dict["nonce"]
                )
                block.hash = block_dict["hash"]   # восстановить хеш
                self.chain.append(block)
            # восстановить voter_records из цепочки
            self.voter_records = {}
            for block in self.chain:
                for vote in block.votes:
                    self.voter_records[vote["voter_id"]] = True
        except Exception as e:
            print("Ошибка загрузки блокчейна:", e)


# ---------------------------- ВЕБ-ПРИЛОЖЕНИЕ ----------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecret-key-for-voting")

blockchain = Blockchain(difficulty=3)

# HTML-шаблоны (встроенные)
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
        .info { background: #d1ecf1; color: #0c5460; }
        hr { margin: 20px 0; }
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
        # Генерируем новую капчу для следующего голосования (если пользователь захочет голосовать снова)
        q, a = Captcha.generate()
        session['captcha_q'] = q
        session['captcha_a'] = a

        if success:
            return render_template_string(MAIN_PAGE, captcha_q=q, message=f"✓ Голос за {candidate} принят! Спасибо.", msg_type="success")
        else:
            return render_template_string(MAIN_PAGE, captcha_q=q, message=f"❌ Избиратель {voter_id} уже проголосовал!", msg_type="error")

    # GET: показываем форму с новой капчей
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
    chain_data = blockchain.to_dict()
    is_valid = blockchain.is_chain_valid()
    return render_template_string(BLOCKCHAIN_PAGE, chain=chain_data, is_valid=is_valid)


@app.route('/api/chain')
def api_chain():
    return jsonify(blockchain.to_dict())

@app.route('/api/results')
def api_results():
    return jsonify(blockchain.get_results())


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)