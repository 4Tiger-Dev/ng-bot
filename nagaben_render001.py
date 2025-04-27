from flask import Flask, request, abort
from dotenv import load_dotenv
from janome.tokenizer import Tokenizer
import os
import re

# LINE SDK
from linebot.v3 import WebhookHandler, Configuration, ApiClient
from linebot.v3.messaging import MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError

# 環境変数を読み込み
load_dotenv()
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

# Flaskアプリケーション
app = Flask(__name__)

# LINE API設定
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 長崎弁変換ロジック ---

# 長崎弁辞書の読み込み
dialect_dict = {}
with open('batten_utf8.txt', encoding='utf-8') as f:
    for line in f:
        if ' ' in line:
            key, val = line.strip().split(' ', 1)
            dialect_dict[key] = val

# 連結辞書の読み込み
connect_dict = {}
with open('connect_dict.txt', encoding='utf-8') as f:
    for line in f:
        if ' ' in line:
            key, val = line.strip().split(' ', 1)
            connect_dict[key] = val

def convert_all(text):
    t = Tokenizer()
    tokens = list(t.tokenize(text, wakati=False))

    tokens_info = []
    for token in tokens:
        features = token.part_of_speech.split(',')
        tokens_info.append({
            'surface': token.surface,
            'pos': features[0],
            'conj_type': token.infl_type,
            'conj_form': token.infl_form,
            'base': token.base_form,
        })

    result = []
    i = 0
    while i < len(tokens_info):
        t1 = tokens_info[i]
        t2 = tokens_info[i+1] if i+1 < len(tokens_info) else {}
        t3 = tokens_info[i+2] if i+2 < len(tokens_info) else {}
        t4 = tokens_info[i+3] if i+3 < len(tokens_info) else {}
        t5 = tokens_info[i+4] if i+4 < len(tokens_info) else {}

        # 否定形
        if (
            t1['pos'] == '動詞' and
            t1['conj_form'] == '未然形' and
            t2.get('surface') == 'ない' and
            t2.get('pos') == '助動詞'
        ):
            base = t1['base']
            if base == 'する':
                result.append('[[せん]]')
            elif base == 'くる':
                result.append('[[こん]]')
            else:
                result.append(f'[[{t1["surface"]}ん]]')
            i += 2
            continue

        # 動詞＋た
        elif (
            t1['pos'] == '動詞' and
            t1['conj_form'] == '連用タ接続' and
            t2.get('surface') == 'た' and
            t2.get('pos') == '助動詞'
        ):
            base = t1['base']
            if base.endswith('う'):
                result.append(f'{base[:-1]}うた')
            else:
                result.append(t1['surface'] + 'た')
            i += 2
            continue

        # 名詞＋が
        elif (
            t1['pos'] == '名詞' and
            t2.get('surface') == 'が' and
            t2.get('pos') == '助詞'
        ):
            result.append(t1['surface'] + 'の')
            i += 2
            continue

        # 動詞連用テ接続＋みる
        elif (
            t1['pos'] == '動詞' and
            t2.get('surface') == 'て' and
            t2.get('pos') == '助詞' 
        ):
            base = t1['surface']

            after_miru = t3['surface']
            if t4: after_miru += t4['surface']
            if t5: after_miru += t5['surface']

            matched = None
            used = 0

            if after_miru[:3] in connect_dict:
                matched = after_miru[:3]
                used = 2
            elif after_miru[:2] in connect_dict:
                matched = after_miru[:2]
                used = 1
            elif after_miru[:1] in connect_dict:
                matched = after_miru[:1]
                used = 0

            if matched:
                result.append(base + 'て' + connect_dict[matched])
                i += 3 + used
                continue
            else:
                result.append(base + 'てむっ')
                i += 3
            continue

        # 形容詞語尾い → か
        elif t1['pos'] == '形容詞' and t1['surface'].endswith('い'):
            if not any(t1['surface'].endswith(suffix) for suffix in ['ばい', 'たい', 'ない']):
                result.append(t1['surface'][:-1] + 'か')
            else:
                result.append(t1['surface'])
            i += 1
            continue

        else:
            result.append(t1['surface'])
            i += 1

    return ''.join(result)

def to_nagasaki_dialect(text):
    text = re.sub(r'(?<![\wぁ-んァ-ン一-龥])しない(?=[をがにのはへとで])', '[[せん]]', text)

    def dict_replace(text):
        protected = []
        def protect(match):
            protected.append(match.group(0))
            return f"__PROTECTED_{len(protected)-1}__"

        text = re.sub(r'\[\[.*?\]\]', protect, text)

        for std in sorted(dialect_dict, key=len, reverse=True):
            text = re.sub(re.escape(std), f'[[{dialect_dict[std]}]]', text)

        for i, original in enumerate(protected):
            text = text.replace(f"__PROTECTED_{i}__", original)

        return text

    text = dict_replace(text)
    text = convert_all(text)
    text = re.sub(r'([\wぁ-んァ-ン一-龥]+)を', r'\1ば', text)

    protected = {}
    def protect(match):
        key = f"__PROTECTED_{len(protected)}__"
        protected[key] = match.group(0)
        return key
    text = re.sub(r'\[\[.*?\]\]', protect, text)

    for key, val in protected.items():
        text = text.replace(key, val)
    text = text.replace('[[', '').replace(']]', '')
    return text

# --- ルート確認 ---
@app.route('/')
def home():
    return 'Hello, this is the home page!'

# --- webhookエンドポイント ---
@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- メッセージ受信時 ---
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    input_text = event.message.text
    dialect_text = to_nagasaki_dialect(input_text)

    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=dialect_text)]
            )
        )

# --- アプリ起動 ---
if __name__ == "__main__":
    app.run(debug=False)