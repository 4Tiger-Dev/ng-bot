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

# グローバルで定義
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
messaging_api = None


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

# ファイルの先頭にグローバルで初期化
t = Tokenizer()

def init_linebot():
    global handler, messaging_api

    if messaging_api is not None:
        return  # すでに初期化済み

    LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

    configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    api_client = ApiClient(configuration)
    messaging_api = MessagingApi(api_client)


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
        if t1['surface'].startswith('[[') and t1['surface'].endswith(']]'):
            result.append(t1['surface'])
            i += 1
            continue

        # 否定形
        if (
            i + 1 < len(tokens_info) and
            t1['pos'] == '動詞' and
            t1['conj_form'] == '未然形' and
            tokens_info[i+1].get('surface') == 'ない' and
            tokens_info[i+1].get('pos') == '助動詞'
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
            i + 1 < len(tokens_info) and
            t1['pos'] == '動詞' and
            t1['conj_form'] == '連用タ接続' and
            tokens_info[i+1].get('surface') == 'た' and
            tokens_info[i+1].get('pos') == '助動詞'
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
            i + 1 < len(tokens_info) and
            t1['pos'] == '名詞' and
            tokens_info[i+1].get('surface') == 'が' and
            tokens_info[i+1].get('pos') == '助詞'
        ):
            result.append(t1['surface'] + 'の')
            i += 2
            continue

        # 名詞＋の
        elif (
            i + 1 < len(tokens_info) and
            t1['pos'] == '名詞' and
            tokens_info[i+1].get('surface') == 'の' and
            tokens_info[i+1].get('pos') == '助詞'
        ):
            result.append(t1['surface'] + 'ん')
            i += 2
            continue

        # 動詞連用テ接続＋動詞（みる等）
        elif (
            i + 2 < len(tokens_info) and
            t1['pos'] == '動詞' and
            tokens_info[i+1].get('surface') == 'て' and
            tokens_info[i+1].get('pos') == '助詞' and
            tokens_info[i+2].get('pos') == '動詞'
        ):
            base = t1['surface']

            # 「みる」以降を連結して辞書マッチング
            after_miru = tokens_info[i+2]['surface']
            if i+3 < len(tokens_info): after_miru += tokens_info[i+3]['surface']
            if i+4 < len(tokens_info): after_miru += tokens_info[i+4]['surface']

            matched = None
            used = 0

            for key in sorted(connect_dict.keys(), key=lambda x: -len(x)):
                if after_miru.startswith(key):
                    matched = key
                    used = 0
                    if i+3 < len(tokens_info) and key.startswith(tokens_info[i+2]['surface'] + tokens_info[i+3]['surface']):
                        used = 1
                    if i+4 < len(tokens_info)and key.startswith(tokens_info[i+2]['surface'] + tokens_info[i+3]['surface'] +  tokens_info[i+4]['surface']):
                        used = 2
                    break

            if matched:
                result.append(base + 'て' + connect_dict[matched])
                i += 3 + used
                continue
            else:
                result.append(base + 'て' + tokens_info[i+2]['surface'])  # デフォルト
                i += 3
            continue

         # 形容詞語尾い + から　→ かけん
        elif (t1['pos'] == '形容詞' and t1['surface'].endswith('い') and tokens_info[i+1].get('surface') == 'から'):
            
            if not t1['surface'].endswith(('ばい', 'たい', 'ない')):
                result.append(t1['surface'][:-1] + 'かけん')
            else:
                result.append(t1['surface'])
            i += 2
            continue
            
       # 形容詞語尾い → か
        elif t1['pos'] == '形容詞' and t1['surface'].endswith('い'):
            if not t1['surface'].endswith(('ばい', 'たい', 'ない')):
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
    # ステップ1：辞書変換前に [[...]] を保護    
        
    protected = []

    def protect(match):
        protected.append(match.group(0))
        return f"__PROTECTED_{len(protected)-1}__"

    text = re.sub(r'\[\[.*?\]\]', protect, text)

    # ステップ2：辞書マッチング
    for std in sorted(dialect_dict, key=len, reverse=True):
        text = re.sub(re.escape(std), f'[[{dialect_dict[std]}]]', text)

    # ステップ3：一時保護部分を復元
    for i, original in enumerate(protected):
        text = text.replace(f"__PROTECTED_{i}__", original)

    # ステップ4：形態素解析＋ルール変換（convert_all）
    text = convert_all(text)
    # ステップ5：「～を」→「～ば」
    text = re.sub(r'([\wぁ-んァ-ン一-龥]+)を', r'\1ば', text)
    # ステップ6：最終的に [[...]] を除去
    text = re.sub(r'\[\[(.*?)\]\]', r'\1', text)

    return text

