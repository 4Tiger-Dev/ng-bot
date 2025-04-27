from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextMessage, MessageEvent, TextSendMessage
from linebot.exceptions import InvalidSignatureError
from dotenv import load_dotenv
import re
import os
from janome.tokenizer import Tokenizer

# 環境変数からLINEの設定情報を取得
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

app = Flask(__name__)

# '/' パスへのルート
@app.route('/')
def home():
    return 'Hello, this is the home page!'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 形態素解析器を作成
tokenizer = Tokenizer()

def kaiseki(text):
    # 解析結果を格納するリスト
    result = []
    for token in tokenizer.tokenize(text):
        surface = token.surface  # 表層形（実際に表示されている単語）
        part_of_speech = token.part_of_speech  # 品詞情報
        result.append(f"{surface}\t{part_of_speech}")
    return '\n'.join(result)  # 結果を改行区切りで返す

# --- LINE webhookエンドポイント ---
@app.route("/webhook", methods=['POST'])
def webhook():
    # 署名検証
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- メッセージ受信時の処理 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    input_text = event.message.text
    dialect_text = kaiseki(input_text)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=dialect_text)
    )
    
# --- 起動 ---
if __name__ == "__main__":
    app.run(debug=False)