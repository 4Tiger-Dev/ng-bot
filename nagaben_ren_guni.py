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


LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

# Flaskアプリケーション
app = Flask(__name__)

# ログ出力
# print("Flask path:", flask.__file__)
# print("Flask version:", flask.__version__)

# LINE Bot設定 (v3仕様)
# グローバルで定義
handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
messaging_api = MessagingApi(api_client)


@handler.add(MessageEvent)
def handle_message(event):
    if isinstance(event.message, TextMessageContent):
        print("Event has come!!")
        input_text = event.message.text
        # 形態素解析リクエスト
        if input_text[0] == "*":
            # 形態素解析実行
            dialect_text = f"【解析結果】\n"
            for token in t.tokenize(input_text[1:]):
                    surface = token.surface
                    part_of_speech = token.part_of_speech
                    dialect_text = dialect_text + (f"{surface}{part_of_speech,token.base_form,token.infl_form,token.infl_type}\n")
            
        else:
            dialect_text = to_nagasaki_dialect(input_text)

        reply_request = ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=dialect_text)]
        )
        messaging_api.reply_message(reply_request)


# トップページ
@app.route('/')
def home():
    return 'Hello, this is the home page!'

# Webhook エンドポイント
@app.route('/webhook', methods=['POST'])
def webhook():
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

# 最大キー長を求める（辞書マッチ範囲）
MAX_DICT_LEN = max(len(k) for k in dialect_dict)


# 連結辞書の読み込み（新規）
connect_dict = {}
with open('connect_dict.txt', encoding='utf-8') as f:
    for line in f:
        if ' ' in line:
            key, val = line.strip().split(' ', 1)
            connect_dict[key] = val

# 形態素解析器
t = Tokenizer()

#　janome形態素解析での変換
def convert_token(text):
    tokens = list(t.tokenize(text, wakati=False))

    if not tokens:
        # 記号・数字などはそのまま1文字返す
        return text[0], 1
    
    # 形態素解析の結果をtokens_infoリストに格納
    tokens_info = [
        {
            'surface': token.surface, # 表層形
            'pos': token.part_of_speech.split(',')[0], # 品詞
            'base': token.base_form, # 基本形
            'conj_form': token.infl_form  # 活用形
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
            # matched_key に該当するトークンだけの表層文字列の長さを合計
            matched_surface_len = 0
            remaining = matched_key
            for i in range(2, 2 + used_tokens):
                token_surface = tokens_info[i]['surface']
                if remaining.startswith(token_surface):
                    matched_surface_len += len(token_surface)
                    remaining = remaining[len(token_surface):]
                    if not remaining:
                        break
                else:
                    if token_surface.startswith(remaining):
                        matched_surface_len += len(remaining)
                        break

            consumed_len = len(base) + len('て') + matched_surface_len
            return converted, consumed_len


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
    # 動詞＋なく＋て　→らんで　　例　走らなくて　→　走らんで
    elif (
        len(tokens_info) >= 3  and
        tokens_info[0]['pos'] == '動詞' and
        tokens_info[1].get('surface') == ('なく') and
        tokens_info[2].get('surface') == 'て'
    ):
    
        # 変換前の文字数を数えるため　変換前文を収納
        surface_used = tokens_info[0]['surface'] + tokens_info[1]['surface'] + tokens_info[2]['surface']
       
        converted = tokens_info[0]['surface'] + 'んで'
        
        return converted, len(surface_used)
    
    
    # 形容詞＋んだ　→だと　例　痛いんだ　→　痛かと　痛いんだと→痛かとて　痛いんじゃ→痛かとじゃ
    elif (
        len(tokens_info) >= 3  and
        tokens_info[0]['pos'] == '形容詞' and
        tokens_info[0].get('surface').endswith('い') and
        tokens_info[1].get('surface') == 'ん' and
        tokens_info[2].get('surface') in ('だ','じゃ','だって')
    ):
    
        # 変換前の文字数を数えるため　変換前文を収納
        surface_used = tokens_info[0]['surface'] + tokens_info[1]['surface'] + tokens_info[2]['surface']
        # 痛いんだと
        if (
            len(tokens_info) >= 4 and
            tokens_info[2].get('surface') == 'だ' and
            tokens_info[3].get('surface') == 'と'
        ):
            surface_used = surface_used + tokens_info[3]['surface']
            converted = tokens_info[0]['surface'][:-1] + 'かとて'
        # 痛いんじゃ
        elif (
            tokens_info[2].get('surface') == 'じゃ'
        ):
            converted = tokens_info[0]['surface'][:-1] + 'かとじゃ'
        # 痛いんだって
        elif (
            tokens_info[2].get('surface') == 'だって'
        ):
            converted = tokens_info[0]['surface'][:-1] + 'かとって'
        # 痛いんだ
        else:
            converted = tokens_info[0]['surface'][:-1] + 'かと'

        return converted, len(surface_used)
    
    # 動詞 基本形 + から　→ けん 　例　走るから　→　走るけん
    elif (
        len(tokens_info) >= 2 and
        tokens_info[0]['pos'] == '動詞' and 
        tokens_info[0]['conj_form'] == '基本形' and 
        tokens_info[1].get('surface') == 'から' 
    ):
        
        # 変換前の文字数を数えるため　変換前文を収納
        surface_used = tokens_info[0]['surface'] + tokens_info[1]['surface']
       
        converted = tokens_info[0]['surface'] +'けん'
        
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
        
    # 動詞連用形 + たい　→ たか 例　会いたい　→　会いたか
    elif (
        len(tokens_info) >= 2 and
        tokens_info[0]['pos'] == '動詞' and 
        tokens_info[0]['conj_form'] == '連用形' and 
        tokens_info[1].get('surface') == 'たい'
    ):
        
        # 変換前の文字数を数えるため　変換前文を収納
        surface_used = tokens_info[0]['surface'] + tokens_info[1]['surface']
       
        converted = tokens_info[0]['surface']+ tokens_info[1]['surface'][:-1]+'か'
        
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
        tokens_info[0]['conj_form'] == '基本形' and 
        tokens_info[0]['surface'] != 'くらい' and
        tokens_info[0]['surface'].endswith('い')
    ):
        # 変換前の文字数を数えるため　変換前文を収納
        surface_used = tokens_info[0]['surface']
        converted = tokens_info[0]['surface'][:-1]+'か'

        return converted, len(surface_used)
    
    # 形容詞語尾く → う
    elif (
        tokens_info[0]['pos'] == '形容詞' and 
        tokens_info[0]['surface'].endswith('く')
    ):
        # 変換前の文字数を数えるため　変換前文を収納
        surface_used = tokens_info[0]['surface']
        converted = tokens_info[0]['surface'][:-1]+'う'

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
