# main.py (最終完成版)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from contextlib import contextmanager
import math
from datetime import datetime

# 自作モジュールとモデルのインポート
import database
from models import Product, ProductSearchResponse, PurchaseRequest, PurchaseResponse

app = FastAPI()

# --- CORS設定 ---
origins = [
    "http://localhost:3000",
    "https://localhost:3000",
    "http://192.168.2.140:3000",
    "https://192.168.2.140:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- データベース接続 ---
@contextmanager
def get_db_cursor():
    conn = None
    try:
        conn = database.get_db_connection()
        if conn is None:
            # データベース接続自体が失敗した場合
            raise HTTPException(status_code=503, detail="データベースに接続できませんでした。")
        
        cursor = conn.cursor(dictionary=True)
        yield cursor
        conn.commit()
    except mysql.connector.Error as err:
        # SQL実行時などのデータベース関連エラー
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"データベースエラー: {err}")
    finally:
        if conn and conn.is_connected():
            conn.close()


# --- APIエンドポイント ---
@app.post("/search_product", response_model=ProductSearchResponse)
def search_product(request_body: dict):
    product_code = request_body.get("code")
    print(f"\n--- 商品検索リクエスト受信 ---")
    print(f"検索コード: {product_code}")
    
    if not product_code:
        raise HTTPException(status_code=400, detail="商品コードが必要です。")

    try:
        with get_db_cursor() as cursor:
            # 全てのカラムに小文字のエイリアスを設定
            query = "SELECT PRD_ID as prd_id, CODE as prd_code, NAME as prd_name, PRICE as prd_price FROM m_product WHERE CODE = %s"
            
            # クエリの実行と結果の取得
            cursor.execute(query, (product_code,))
            result = cursor.fetchone()

            print(f"データベース検索結果: {result}")
            print(f"---------------------------\n")

            if result:
                # Pydanticモデルへの変換
                product_data = Product(**result)
                return ProductSearchResponse(product=product_data)
            else:
                # 商品が見つからなかった場合
                return ProductSearchResponse(product=None)
    except Exception as e:
        # Pydanticのバリデーションエラーなど、予期せぬエラーをキャッチ
        print(f"[ERROR] 商品検索処理でエラー: {e}")
        raise HTTPException(status_code=500, detail=f"サーバー内部エラー: {e}")


@app.post("/purchase", response_model=PurchaseResponse)
def purchase(request: PurchaseRequest):
    print(f"\n--- 購入リクエスト受信 ---")
    print(f"購入アイテム数: {len(request.items)}")
    
    # 税抜き金額と合計金額を計算
    total_amount = sum(item.prd_price for item in request.items)
    total_amount_ex_tax = sum(math.floor(item.prd_price / 1.1) for item in request.items)

    try:
        with get_db_cursor() as cursor:
            # 1. 取引テーブル(t_txn)へ登録
            insert_txn_query = "INSERT INTO t_txn (DATETIME, EMP_CD, STORE_CD, POS_NO, TOTAL_AMT, TTL_AMT_EX_TAX) VALUES (%s, %s, %s, %s, %s, %s)"
            cursor.execute(insert_txn_query, (datetime.now(), request.emp_cd or '9999999999', '30', '90', total_amount, total_amount_ex_tax))
            
            # 最後に挿入された取引IDを取得
            trd_id = cursor.lastrowid

            # 2. 取引明細テーブル(t_txn_dtl)へ登録
            insert_dtl_query = "INSERT INTO t_txn_dtl (TRD_ID, DTL_ID, PRD_ID, PRD_CODE, PRD_NAME, PRD_PRICE, TAX_CD) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            for index, item in enumerate(request.items, start=1):
                cursor.execute(insert_dtl_query, (trd_id, index, item.prd_id, item.prd_code, item.prd_name, item.prd_price, '10'))
        
        print(f"購入処理成功。取引ID: {trd_id}")
        print(f"-----------------------\n")
        return PurchaseResponse(success=True, total_amount=total_amount, total_amount_ex_tax=total_amount_ex_tax)

    except Exception as err:
        # 購入処理中の予期せぬエラー
        print(f"[ERROR] 購入処理失敗: {err}")
        print(f"-----------------------\n")
        raise HTTPException(status_code=500, detail=f"サーバー内部エラー: {err}")