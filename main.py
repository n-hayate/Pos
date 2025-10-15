# main.py
import os
import math
from datetime import datetime
from contextlib import contextmanager
from typing import List, Optional

import pymysql
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# ================== Pydanticモデル ==================
class Product(BaseModel):
    prd_id: int
    prd_code: str
    prd_name: str
    prd_price: int


class ProductSearchResponse(BaseModel):
    product: Optional[Product] = None


class PurchaseItem(BaseModel):
    prd_id: int
    prd_code: str
    prd_name: str
    prd_price: int
    quantity: int


class PurchaseRequest(BaseModel):
    emp_cd: Optional[str] = ""
    store_cd: str = "30"
    pos_no: str = "90"
    items: List[PurchaseItem]


class PurchaseResponse(BaseModel):
    success: bool
    total_amount: int
    total_amount_ex_tax: int


# ================== FastAPIアプリ初期化 ==================
app = FastAPI(title="POS API", version="1.0.0")

# CORS設定
origins = [
    "http://localhost:3000",
    "https://localhost:3000",
    "http://192.168.2.140:3000",
    "https://192.168.2.140:3000",
    "https://app-002-gen10-step3-1-py-oshima42.azurewebsites.net",
    "https://app-002-gen10-step3-1-node-oshima42.azurewebsites.net",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================== データベース接続 ==================
def get_db_connection():
    """データベース接続を取得"""
    try:
        conn = pymysql.connect(
            host=os.environ.get("DB_HOST"),
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD"),
            database=os.environ.get("DB_NAME"),
            port=int(os.environ.get("DB_PORT", 3306)),
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            ssl_verify_cert=True,
            ssl_verify_identity=True
        )
        return conn
    except Exception as e:
        print(f"[DB接続エラー] {e}")
        raise HTTPException(status_code=503, detail="データベースに接続できませんでした")


@contextmanager
def get_db_cursor():
    """データベースカーソルのコンテキストマネージャ"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except pymysql.Error as err:
        if conn:
            conn.rollback()
        print(f"[DB ERROR] {err}")
        raise HTTPException(status_code=500, detail=f"データベースエラー: {str(err)}")
    finally:
        if conn:
            conn.close()


# ================== APIエンドポイント ==================
@app.get("/")
def health_check():
    """ヘルスチェック"""
    return {
        "status": "ok",
        "service": "POS API",
        "version": "1.0.0"
    }


@app.post("/search_product", response_model=ProductSearchResponse)
def search_product(request_body: dict):
    """商品コードで商品を検索"""
    product_code = request_body.get("code")
    
    if not product_code:
        raise HTTPException(status_code=400, detail="商品コードが必要です")
    
    print(f"[商品検索] コード: {product_code}")
    
    try:
        with get_db_cursor() as cursor:
            query = """
                SELECT 
                    PRD_ID as prd_id,
                    CODE as prd_code,
                    NAME as prd_name,
                    PRICE as prd_price
                FROM m_product
                WHERE CODE = %s
            """
            cursor.execute(query, (product_code,))
            result = cursor.fetchone()
            
            if result:
                print(f"[検索成功] 商品: {result['prd_name']}")
                return ProductSearchResponse(product=Product(**result))
            else:
                print(f"[検索失敗] 商品が見つかりません")
                return ProductSearchResponse(product=None)
                
    except Exception as e:
        print(f"[商品検索エラー] {e}")
        raise HTTPException(status_code=500, detail=f"商品検索エラー: {str(e)}")


@app.post("/purchase", response_model=PurchaseResponse)
def purchase(request: PurchaseRequest):
    """購入処理"""
    if not request.items:
        raise HTTPException(status_code=400, detail="購入する商品がありません")
    
    print(f"[購入開始] アイテム数: {len(request.items)}")
    
    # 合計金額計算
    total_amount = sum(item.prd_price * item.quantity for item in request.items)
    total_amount_ex_tax = sum(
        math.floor(item.prd_price / 1.1) * item.quantity 
        for item in request.items
    )
    
    try:
        with get_db_cursor() as cursor:
            # 1. 取引テーブルに登録
            emp_cd = request.emp_cd if request.emp_cd else "9999999999"
            
            insert_txn = """
                INSERT INTO t_txn 
                (DATETIME, EMP_CD, STORE_CD, POS_NO, TOTAL_AMT, TTL_AMT_EX_TAX)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(
                insert_txn,
                (datetime.now(), emp_cd, request.store_cd, request.pos_no, 
                 total_amount, total_amount_ex_tax)
            )
            
            trd_id = cursor.lastrowid
            print(f"[取引登録] 取引ID: {trd_id}")
            
            # 2. 取引明細テーブルに登録
            insert_dtl = """
                INSERT INTO t_txn_dtl
                (TRD_ID, DTL_ID, PRD_ID, PRD_CODE, PRD_NAME, PRD_PRICE, TAX_CD)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            dtl_id = 1
            for item in request.items:
                for _ in range(item.quantity):
                    cursor.execute(
                        insert_dtl,
                        (trd_id, dtl_id, item.prd_id, item.prd_code, 
                         item.prd_name, item.prd_price, "10")
                    )
                    dtl_id += 1
            
            print(f"[購入成功] 合計: {total_amount}円")
            
            return PurchaseResponse(
                success=True,
                total_amount=total_amount,
                total_amount_ex_tax=total_amount_ex_tax
            )
            
    except Exception as e:
        print(f"[購入エラー] {e}")
        raise HTTPException(status_code=500, detail=f"購入処理エラー: {str(e)}")


# ================== Azureエントリポイント ==================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
