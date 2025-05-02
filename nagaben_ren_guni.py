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

# ファイルの先頭にグローバルで初期化
t = Tokenizer()

# 長崎弁辞書の読み込み 
dialect_dict = {}
with open('batten_utf8.txt', encoding='utf-8') as f:
    for line in f:
        if ' ' in line:
            key, val = line.strip().split(' ', 1)
            dialect_dict[key] = val

# 最大キー長を求める（辞書マッチ範囲）
MAX_DICT_LEN = max(len(k) for k in dialect_dict)


# 連結辞書の読み込み（新規）
connect_dict = {}
with open('connect_dict.txt', encoding='utf-8') as f:
    for line in f:
        if ' ' in line:
            key, val = line.strip().split(' ', 1)
            connect_dict[key] = val


#　janome形態素解析での変換
def convert_token(text):
    tokens = list(t.tokenize(text, wakati=False))

    if not tokens:
        # 記号・数字などはそのまま1文字返す
        return text[0], 1
    
    # 形態素解析の結果をtokens_infoリストに格納
    tokens_info = [
        {
            'surface': token.surface,
            'pos': token.part_of_speech.split(',')[0],
            'base': token.base_form,
            'conj_form': token.infl_form  # ←追加
        } for token in tokens
    ]


    # 動詞連用テ接続＋動詞　例　行ってみる　→　行ってむう
    if (
        len(tokens_info) >= 3  and
        tokens_info[0]['pos'] == '動詞' and
        tokens_info[1].get('surface') == 'て' and
        tokens_info[1].get('pos') == '助詞' and
        tokens_info[2].get('pos') == '動詞'
    ):
        base = tokens_info[0]['surface']
        miru_seq = tokens_info[2]['surface']
        surface_used = base + 'て' + miru_seq
        used_tokens = 3

        # 「て＋みる」以降のトークンを最大2つ追加してマッチ
        for extra in range(1, 3):
            if len(tokens_info) > 2 + extra:
                miru_seq += tokens_info[2 + extra]['surface']
                surface_used += tokens_info[2 + extra]['surface']
                used_tokens += 1

        # connect_dict でマッチ検索（長い順）
        matched_key = None
        for key in sorted(connect_dict.keys(), key=lambda x: -len(x)):
            if miru_seq.startswith(key):
                matched_key = key
                break

        if matched_key:
            converted = base + 'て' + connect_dict[matched_key]
            consumed_len = len(surface_used)
            return converted, consumed_len
        else:
            return surface_used, len(surface_used)


    # 動詞＋から　→けん　　例　走ったから　→　走ったけん
    elif (
        len(tokens_info) >= 3  and
        tokens_info[0]['pos'] == '動詞' and
        tokens_info[1].get('surface') in ('た','だ') and
        tokens_info[1].get('pos') == '助動詞' and
        tokens_info[2].get('surface') == 'から'
    ):
    
        # 変換前の文字数を数えるため　変換前文を収納
        surface_used = tokens_info[0]['surface'] + tokens_info[1]['surface'] + tokens_info[2]['surface']
       
        converted = tokens_info[0]['surface'] + tokens_info[1]['surface'] +'けん'
        
        return converted, len(surface_used)
    
    # 否定形
    elif (
        len(tokens_info) >= 2 and
        tokens_info[0]['pos'] == '動詞' and
        tokens_info[0]['conj_form'] == '未然形' and
        tokens_info[1].get('surface') == 'ない' and
        tokens_info[1].get('pos') == '助動詞'
    ):
        # 変換前の文字数を数えるため　変換前文を収納
        surface_used = tokens_info[0]['surface'] + tokens_info[1]['surface']

        base = tokens_info[0]['base']
        # しない→せん
        if base == 'する':
            converted = 'せん'
        # くる→こん
        elif base == 'くる':
            converted = 'こん'
        # それ以外の動詞　例　売らない　→　売らん
        else:
            converted = tokens_info[0]['surface'] +'ん'
        
        return converted, len(surface_used)


    # 動詞の基本形語末が「う」の場合　例　基本形：拾う　surface：拾った　→　拾うた
    elif (
        len(tokens_info) >= 2  and
        tokens_info[0]['pos'] == '動詞' and
        tokens_info[0]['base'].endswith('う') and
        tokens_info[0]['conj_form'] == '連用タ接続' and
        tokens_info[1].get('surface') == 'た' and
        tokens_info[1].get('pos') == '助動詞'
    ):
        # 変換前の文字数を数えるため　変換前文を収納
        surface_used = tokens_info[0]['surface'] + tokens_info[1]['surface']
       
        converted = tokens_info[0]['base']+'た'
        
        return converted, len(surface_used)

    # 名詞＋が　例　花が　花の
    elif (
        len(tokens_info) >= 2 and
        tokens_info[0]['pos'] == '名詞' and
        tokens_info[1].get('surface') == 'が' and
        tokens_info[1].get('pos') == '助詞'
    ):
        # 変換前の文字数を数えるため　変換前文を収納
        surface_used = tokens_info[0]['surface'] + tokens_info[1]['surface']
       
        converted = tokens_info[0]['surface']+'の'
        
        return converted, len(surface_used)


    # 形容詞語尾い + から　→ かけん 例　美しいから　→　美しかけん
    elif (
        len(tokens_info) >= 2 and
        tokens_info[0]['pos'] == '形容詞' and 
        tokens_info[0]['surface'].endswith('い') and 
        tokens_info[1].get('surface') == 'から'
    ):
        
        # 変換前の文字数を数えるため　変換前文を収納
        surface_used = tokens_info[0]['surface'] + tokens_info[1]['surface']
       
        converted = tokens_info[0]['surface'][:-1]+'かけん'
        
        return converted, len(surface_used)
        

    # 名詞＋の　男の→男ん　
    elif (
        len(tokens_info) >= 2 and
        tokens_info[0]['pos'] == '名詞' and
        tokens_info[1].get('surface') == 'の' and
        tokens_info[1].get('pos') == '助詞'
    ):
        # 変換前の文字数を数えるため　変換前文を収納
        surface_used = tokens_info[0]['surface'] + tokens_info[1]['surface']
       
        converted = tokens_info[0]['surface']+'ん'
        
        return converted, len(surface_used)

    # 形容詞語尾い → か
    elif (
        tokens_info[0]['pos'] == '形容詞' and 
        tokens_info[0]['surface'].endswith('い')
    ):
        # 変換前の文字数を数えるため　変換前文を収納
        surface_used = tokens_info[0]['surface']
        converted = tokens_info[0]['surface'][:-1]+'か'

        return converted, len(surface_used)
   
    # どの条件にも該当しなかった場合
    # return text[:1], 1
    
    # デフォルト：先頭単語そのまま
    return tokens_info[0]['surface'], len(tokens_info[0]['surface'])


# 長崎弁変換エンジン
def to_nagasaki_dialect(text):
    # result 初期化
    result = ""   
    i = 0 # 文字インデックス　初期化　textの何文字目かを表すインデックス
    
    # textの残りがある間
    while i < len(text):
        matched = False

        # 辞書マッチ（長い順）
        for j in range(MAX_DICT_LEN, 0, -1):
            chunk = text[i:i+j]
            if chunk in dialect_dict:
                result += dialect_dict[chunk]
                i += j
                matched = True
                break
        
        if matched:
            continue

        # Janome 形態素変換
        # 2. Janomeで先頭単語変換
        converted, length = convert_token(text[i:])
        if converted != text[i:i+length]:
            result += converted
            i += length
            continue

        # 3. どちらにもマッチしなかった → 1文字そのまま
        if text[i] in '！？?!。、「」':
            result += text[i]
            i += 1
        else:
            result += text[i]
            i += 1    
    return result


