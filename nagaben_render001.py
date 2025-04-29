from flask import Flask, request, abort
from linebot.v3.webhook import WebhookHandler, MessageEvent  # ←ここ
from linebot.v3.messaging import MessagingApi, Configuration
from linebot.v3.messaging.models import TextMessage, ReplyMessageRequest
from linebot.v3.exceptions import InvalidSignatureError
from dotenv import load_dotenv
import os
from janome.tokenizer import Tokenizer

# 環境変数をロード
load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

# Flaskアプリケーション
app = Flask(__name__)

# LINE Bot設定 (v3仕様)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
line_bot_api = MessagingApi(configuration)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 形態素解析器
tokenizer = Tokenizer()

def kaiseki(text):
    result = []
    for token in tokenizer.tokenize(text):
        surface = token.surface
        part_of_speech = token.part_of_speech
        result.append(f"{surface}\t{part_of_speech}")
    return '\n'.join(result)

@app.route('/')
def home():
    return 'Hello, this is the home page!'

@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent)
def handle_message(event):
    print("handle_message triggered!")  # ここを追加

    if isinstance(event.message, TextMessage):
        input_text = event.message.text
        dialect_text = kaiseki(input_text)

        reply = ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=dialect_text)]
        )
        print("Replying:",reply)
        line_bot_api.reply_message(reply)

#if __name__ == "__main__":
#    app.run(debug=False, host='0.0.0.0', port=5000)
