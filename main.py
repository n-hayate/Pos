# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pymysql
from contextlib import contextmanager
import math
from datetime import datetime

# 自作モジュールとモデルのインポート
import database
from models import Product, ProductSearchResponse, PurchaseRequest, PurchaseResponse

app = FastAPI()

# --- CORS設定 ---
# フロントエンドのURLに合わせて適宜変更してください
origins = [
    "http://localhost:3000",
    "https://localhost:3000",
    "http://192.168.2.140:3000",
    "https://192.168.2.140:3000",
    # AzureのWeb AppのURLも追加しておくと安心です
    "https://app-002-gen10-step3-1-py-oshima42.azurewebsites.net",
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
    """
    データベース接続とカーソルを管理するコンテキストマネージャ。
    処理の開始時に接続を確立し、終了時に自動的に閉じる。
    """
    conn = None
    try:
        conn = database.get_db_connection()
        if conn is None:
            # データベース接続自体が失敗した場合
            raise HTTPException(status_code=503, detail="データベースに接続できませんでした。")
        
        # database.pyのcursorclass設定により、cursor()は辞書形式のカーソルを返す
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except pymysql.Error as err:
        # SQL実行時などのデータベース関連エラー
        if conn:
            conn.rollback()
        # エラーの詳細はログに出力し、クライアントには汎用的なメッセージを返す
        print(f"[DATABASE ERROR] {err}")
        raise HTTPException(status_code=500, detail="データベース処理中にエラーが発生しました。")
    finally:
        if conn:
            conn.close()


# --- APIエンドポイント ---
@app.post("/search_product", response_model=ProductSearchResponse)
def search_product(request_body: dict):
    """商品コードに基づいて商品を検索する"""
    product_code = request_body.get("code")
    print(f"\n--- 商品検索リクエスト受信 ---")
    print(f"検索コード: {product_code}")
    
    if not product_code:
        raise HTTPException(status_code=400, detail="商品コードが必要です。")

    try:
        with get_db_cursor() as cursor:
            # Pydanticモデルのフィールド名に合わせるため、SQLクエリでエイリアス(AS)を使用
            query = "SELECT PRD_ID as prd_id, CODE as prd_code, NAME as prd_name, PRICE as prd_price FROM m_product WHERE CODE = %s"
            
            cursor.execute(query, (product_code,))
            result = cursor.fetchone()

            print(f"データベース検索結果: {result}")
            print(f"---------------------------\n")

            if result:
                # `result`は既に辞書形式なので、そのままPydanticモデルに渡せる
                product_data = Product(**result)
                return ProductSearchResponse(product=product_data)
            else:
                # 商品が見つからなかった場合
                return ProductSearchResponse(product=None)
                
    except Exception as e:
        # Pydanticのバリデーションエラーなど、予期せぬエラーをキャッチ
        print(f"[ERROR] 商品検索処理で予期せぬエラー: {e}")
        raise HTTPException(status_code=500, detail=f"サーバー内部で予期せぬエラーが発生しました: {e}")


@app.post("/purchase", response_model=PurchaseResponse)
def purchase(request: PurchaseRequest):
    """商品の購入処理を行い、取引データをデータベースに記録する"""
    print(f"\n--- 購入リクエスト受信 ---")
    print(f"購入アイテム数: {len(request.items)}")
    
    if not request.items:
        raise HTTPException(status_code=400, detail="購入する商品がありません。")

    # 税抜き金額と合計金額を計算
    total_amount = sum(item.prd_price for item in request.items)
    total_amount_ex_tax = sum(math.floor(item.prd_price / 1.1) for item in request.items)

    try:
        with get_db_cursor() as cursor:
            # 1. 取引テーブル(t_txn)へ登録
            # emp_cdが空文字列の場合、デフォルト値（'9999999999'など）を設定
            employee_code = request.emp_cd if request.emp_cd else '9999999999'
            insert_txn_query = "INSERT INTO t_txn (DATETIME, EMP_CD, STORE_CD, POS_NO, TOTAL_AMT, TTL_AMT_EX_TAX) VALUES (%s, %s, %s, %s, %s, %s)"
            cursor.execute(insert_txn_query, (datetime.now(), employee_code, request.store_cd, request.pos_no, total_amount, total_amount_ex_tax))
            
            # 最後に挿入された行のID（この取引のID）を取得
            trd_id = cursor.lastrowid

            # 2. 取引明細テーブル(t_txn_dtl)へ購入商品を1つずつ登録
            insert_dtl_query = "INSERT INTO t_txn_dtl (TRD_ID, DTL_ID, PRD_ID, PRD_CODE, PRD_NAME, PRD_PRICE, TAX_CD) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            for index, item in enumerate(request.items, start=1):
                cursor.execute(insert_dtl_query, (trd_id, index, item.prd_id, item.prd_code, item.prd_name, item.prd_price, '10')) # 税コードは'10'で固定
        
        print(f"購入処理成功。取引ID: {trd_id}")
        print(f"-----------------------\n")
        return PurchaseResponse(success=True, total_amount=total_amount, total_amount_ex_tax=total_amount_ex_tax)

    except Exception as err:
        # 購入処理中の予期せぬエラー
        print(f"[ERROR] 購入処理失敗: {err}")
        print(f"-----------------------\n")
        raise HTTPException(status_code=500, detail=f"サーバー内部で予期せぬエラーが発生しました: {err}")