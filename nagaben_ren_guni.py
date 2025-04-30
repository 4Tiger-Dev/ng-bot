import flask
from flask import Flask, request, abort
from dotenv import load_dotenv
import os
import re
from janome.tokenizer import Tokenizer

from linebot.v3.webhook import WebhookHandler, MessageEvent
from linebot.v3.webhooks import TextMessageContent
from linebot.v3.messaging.configuration import Configuration
from linebot.v3.messaging.api_client import ApiClient
from linebot.v3.messaging import MessagingApi
from linebot.v3.messaging.models import ReplyMessageRequest, TextMessage
from linebot.v3.exceptions import InvalidSignatureError

# 環境変数を読み込み
load_dotenv()

# Flaskアプリケーション
app = Flask(__name__)

# ログ出力
# print("Flask path:", flask.__file__)
# print("Flask version:", flask.__version__)

# LINE Bot SDK 遅延初期化用
handler = None
messaging_api = None

def init_linebot():
    global handler, messaging_api

    if handler is not None and messaging_api is not None:
        return  # すでに初期化済み

    LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
    LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

    handler = WebhookHandler(LINE_CHANNEL_SECRET)
    configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    api_client = ApiClient(configuration)
    messaging_api = MessagingApi(api_client)

    # ファイルの先頭にグローバルで初期化
    # t = Tokenizer()

    @handler.add(MessageEvent)
    def handle_message(event):
        if isinstance(event.message, TextMessageContent):
            print("Event has come!!")
            input_text = event.message.text
            dialect_text = to_nagasaki_dialect(input_text)

            reply_request = ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=dialect_text)]
            )
            messaging_api.reply_message(reply_request)

@app.before_first_request
def startup():
    print("Initializing LINE Bot handler...")
    init_linebot()

# トップページ
@app.route('/')
def home():
    return 'Hello, this is the home page!'

# Webhook エンドポイント
@app.route('/webhook', methods=['POST'])
def webhook():
    init_linebot()  # 念のため再確認
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# 長崎弁辞書の読み込み 
dialect_dict = {}
with open('batten_utf8.txt', encoding='utf-8') as f:
    for line in f:
        if ' ' in line:
            key, val = line.strip().split(' ', 1)
            dialect_dict[key] = val

# 連結辞書の読み込み（新規）
connect_dict = {}
with open('connect_dict.txt', encoding='utf-8') as f:
    for line in f:
        if ' ' in line:
            key, val = line.strip().split(' ', 1)
            connect_dict[key] = val


#　janome形態素解析での変換
def convert_all(text):
    t = Tokenizer() 
    tokens = list(t.tokenize(text, wakati=False))

    # 形態素解析の結果をtokens_infoリストに格納
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

        # 動詞（基本形語末う＋た　例　拾った
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

        # 名詞＋の
        elif (
            t1['pos'] == '名詞' and
            t2.get('surface') == 'の' and
            t2.get('pos') == '助詞'
        ):
            result.append(t1['surface'] + 'ん')
            i += 2
            continue

        # 動詞連用テ接続＋動詞（みる等）
        elif (
            t1['pos'] == '動詞' and
            t2.get('surface') == 'て' and
            t2.get('pos') == '助詞' and
            t3.get('pos') == '動詞'
        ):
            base = t1['surface']

            # 「みる」以降を連結して辞書マッチング
            after_miru = t3['surface']
            if t4: after_miru += t4['surface']
            if t5: after_miru += t5['surface']

            matched = None
            used = 0

            for key in sorted(connect_dict.keys(), key=lambda x: -len(x)):
                if after_miru.startswith(key):
                    matched = key
                    used = 0
                    if t4 and key.startswith(t3['surface'] + t4['surface']):
                        used = 1
                    if t5 and key.startswith(t3['surface'] + t4['surface'] + t5['surface']):
                        used = 2
                    break

            if matched:
                result.append(base + 'て' + connect_dict[matched])
                i += 3 + used
                continue
            else:
                result.append(base + 'て' + t3['surface'])  # デフォルト
                i += 3
            continue

         # 形容詞語尾い + から　→ かけん
        elif (t1['pos'] == '形容詞' and t1['surface'].endswith('い') and t2.get('surface') == 'から'):
            
            if not any(t1['surface'].endswith(suffix) for suffix in ['ばい', 'たい', 'ない']):
                result.append(t1['surface'][:-1] + 'かけん')
            else:
                result.append(t1['surface'])
            i += 2
            continue
            
       # 形容詞語尾い → か
        elif t1['pos'] == '形容詞' and t1['surface'].endswith('い'):
            if not any(t1['surface'].endswith(suffix) for suffix in ['ばい', 'たい', 'ない']):
                result.append(t1['surface'][:-1] + 'か')
            else:
                result.append(t1['surface'])
            i += 1
            continue
        # 接続助詞　から　けん
        elif (
            t1['pos'] == '接続助詞' and
            t1.get('surface') == 'から'
            
        ):
            result.append('[[けん]]')
            i += 1
            continue

        else:
            result.append(t1['surface'])
            i += 1

    return ''.join(result)

# 長崎弁変換エンジン
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
