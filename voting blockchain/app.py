import hashlib
import json
import datetime
import random
import io
import base64
import os
from typing import List, Dict
from flask import Flask, render_template, request, jsonify, session
from PIL import Image, ImageDraw, ImageFont, ImageFilter

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key_for_voting')

# ---------------------- БЛОКЧЕЙН ----------------------
class Block:
    def __init__(self, index: int, votes: List[Dict], timestamp: str, previous_hash: str, nonce: int = 0):
        self.index = index
        self.votes = votes
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        block_string = json.dumps({
            "index": self.index,
            "votes": self.votes,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce
        }, sort_keys=True, ensure_ascii=False).encode('utf-8')
        return hashlib.sha256(block_string).hexdigest()

    def mine_block(self, difficulty: int):
        target = "0" * difficulty
        max_attempts = 100000
        attempts = 0
        while self.hash[:difficulty] != target and attempts < max_attempts:
            self.nonce += 1
            self.hash = self.compute_hash()
            attempts += 1


class Blockchain:
    def __init__(self, difficulty: int = 2):
        self.chain: List[Block] = []
        self.difficulty = difficulty
        self.voter_records: Dict[str, bool] = {}
        self.create_genesis_block()

    def create_genesis_block(self):
        genesis_block = Block(0, [], str(datetime.datetime.now()), "0")
        genesis_block.mine_block(self.difficulty)
        self.chain.append(genesis_block)

    def get_latest_block(self) -> Block:
        return self.chain[-1]

    @staticmethod
    def verify_signature(voter_id: str, candidate: str, signature: str) -> bool:
        if not signature or len(signature) < 3:
            return False
        if voter_id not in signature:
            return False
        return True

    def add_vote(self, voter_id: str, candidate: str, signature: str) -> bool:
        if voter_id in self.voter_records:
            return False
        if not self.verify_signature(voter_id, candidate, signature):
            return False

        vote = {
            "voter_id": voter_id,
            "candidate": candidate,
            "signature": signature,
            "timestamp": str(datetime.datetime.now())
        }
        prev_block = self.get_latest_block()
        new_block = Block(
            index=prev_block.index + 1,
            votes=[vote],
            timestamp=str(datetime.datetime.now()),
            previous_hash=prev_block.hash
        )
        new_block.mine_block(self.difficulty)
        self.chain.append(new_block)
        self.voter_records[voter_id] = True
        return True

    def is_chain_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            curr = self.chain[i]
            prev = self.chain[i-1]
            if curr.hash != curr.compute_hash():
                return False
            if curr.previous_hash != prev.hash:
                return False
            if curr.hash[:self.difficulty] != "0" * self.difficulty:
                return False
        return True

    def get_results(self) -> Dict[str, int]:
        results = {}
        for block in self.chain:
            for vote in block.votes:
                cand = vote["candidate"]
                results[cand] = results.get(cand, 0) + 1
        return results

    def get_chain_data(self) -> List[Dict]:
        chain_data = []
        for block in self.chain:
            chain_data.append({
                "index": block.index,
                "hash": block.hash,
                "previous_hash": block.previous_hash,
                "timestamp": block.timestamp,
                "nonce": block.nonce,
                "votes": block.votes
            })
        return chain_data


voting_system = Blockchain(difficulty=2)

# ---------------------- КАПЧА ----------------------
def generate_captcha_text(length=4):
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(random.choice(chars) for _ in range(length))

def create_captcha_image(text):
    width = 180
    height = 60
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    for _ in range(3):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)), width=1)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
    except:
        font = ImageFont.load_default()
    
    for i, char in enumerate(text):
        x = 15 + i * 35 + random.randint(-3, 3)
        y = random.randint(10, 25)
        draw.text((x, y), char, fill=(random.randint(0, 80), random.randint(0, 80), random.randint(0, 80)), font=font)
    
    return image

@app.route('/captcha')
def captcha():
    captcha_text = generate_captcha_text()
    session['captcha'] = captcha_text
    image = create_captcha_image(captcha_text)
    
    buffered = io.BytesIO()
    image.save(buffered, format='PNG')
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return jsonify({'image': f'data:image/png;base64,{img_str}'})

# ---------------------- ВЕБ-МАРШРУТЫ ----------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/candidates')
def get_candidates():
    return jsonify(["Alice", "Bob", "Charlie", "Diana"])

@app.route('/api/vote', methods=['POST'])
def vote():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Invalid data"}), 400
        
        voter_id = data.get('voter_id', '').strip()
        candidate = data.get('candidate', '').strip()
        signature = data.get('signature', '').strip()
        captcha_input = data.get('captcha', '').strip()
        
        if 'captcha' not in session or captcha_input != session['captcha']:
            return jsonify({"success": False, "error": "Invalid captcha"}), 400
        
        if not voter_id or not candidate or not signature:
            return jsonify({"success": False, "error": "All fields required"}), 400
        
        success = voting_system.add_vote(voter_id, candidate, signature)
        if success:
            session.pop('captcha', None)
            return jsonify({"success": True, "message": "Vote recorded!"})
        else:
            return jsonify({"success": False, "error": "Already voted or invalid signature"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/results')
def results():
    return jsonify(voting_system.get_results())

@app.route('/api/blockchain')
def blockchain():
    return jsonify({
        "chain": voting_system.get_chain_data(),
        "length": len(voting_system.chain),
        "valid": voting_system.is_chain_valid()
    })

@app.route('/api/verify')
def verify():
    return jsonify({"valid": voting_system.is_chain_valid()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)