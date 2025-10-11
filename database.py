# database.py (最終版)
import mysql.connector
import os
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

def get_db_connection():
    """データベース接続を取得する関数"""
    try:
        # SSL設定を辞書として準備
        ssl_args = {
            'ssl_ca': os.getenv("SSL_CA_PATH"),
            'ssl_verify_cert': True  # SSL証明書の検証を強制する
        }
        
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            use_pure=True,  # より安定したPure Python実装を使用する
            **ssl_args      # SSL設定を渡す
        )
        print("--- データベース接続成功！ ---")
        return conn
    except mysql.connector.Error as err:
        print(f"データベース接続エラー: {err}")
        return None