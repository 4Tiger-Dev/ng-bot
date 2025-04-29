import flask
from flask import Flask, request, abort
from dotenv import load_dotenv
import os

from janome.tokenizer import Tokenizer

from linebot.v3.webhook import WebhookHandler, MessageEvent
from linebot.v3.webhooks import TextMessageContent
from linebot.v3 import Configuration, ApiClient
from linebot.v3.messaging import MessagingApi
from linebot.v3.messaging.models import ReplyMessageRequest, TextMessage
from linebot.v3.exceptions import InvalidSignatureError

# 環境変数を読み込み
load_dotenv()

# Flaskアプリケーション
app = Flask(__name__)

# ログ出力
print("Flask path:", flask.__file__)
print("Flask version:", flask.__version__)

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
    
    @handler.add(MessageEvent)
    def handle_message(event):
        if isinstance(event.message, TextMessageContent):
            input_text = event.message.text
            dialect_text = kaiseki(input_text)

            reply_request = ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=dialect_text)]
            )
            print("ready to send reply")
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

# 形態素解析用関数
def kaiseki(text):
    tokenizer = Tokenizer()
    result = []
    for token in tokenizer.tokenize(text):
        surface = token.surface
        part_of_speech = token.part_of_speech
        result.append(f"{surface}\t{part_of_speech}")
    return '\n'.join(result)