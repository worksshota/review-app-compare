import json
import os
import time
import requests
import markdown
from google import genai

# --- 1. Gemini API呼び出し ---
def call_gemini_with_retry(client: genai.Client, prompt: str, max_retries: int = 3) -> any:
    model_name = 'gemini-3.6-flash'
    for attempt in range(max_retries):
        try:
            print(f"Gemini API呼び出し試行中: {model_name} (Attempt {attempt + 1})")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            return response
        except Exception as e:
            print(f"Gemini API Error ({model_name}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                raise e

# --- 2. 比較記事専用プロンプト ---
def generate_compare_article(client: genai.Client, products: list) -> str:
    p1, p2, p3 = products[0], products[1], products[2]
   
    prompt = f"""
あなたはプロのWEBライターおよびアフィリエイターです。
以下の3つの人気商品を徹底比較し、読者が自分にぴったりの1台を選べる視認性の高いレビュー・比較まとめ記事を作成してください。

比較対象商品:
1. {p1}
2. {p2}
3. {p3}

# 執筆・レイアウトの絶対ルール（視認性重視）
1. **比較表（Markdownテーブル）の設置**:
   - 序盤に必ず3商品の特徴・価格帯・おすすめタイプを網羅した比較表を作成してください。
2. **文章の壁を作らない（改行の徹底）**:
   - 2〜3文ごとに必ず1行の「空行」を挟んでください。
3. **箇条書き（- ）と太字の多用**:
   - メリット・デメリットや選び方は必ず箇条書き（`- `）にし、重要単語は **太字** にしてください。

# 記事の構成テンプレート:
## 1. 【結論】迷ったらどれを買うべき？
（3商品のざっくりとした違いと、一番おすすめの1台を先に記述）

## 2. 3商品のスペック・特徴比較表
| 商品名 | 主な特徴 | コスパ | こんな人向け |
| :--- | :--- | :--- | :--- |
| {p1} | （特徴） | （評価） | （対象） |
| {p2} | （特徴） | （評価） | （対象） |
| {p3} | （特徴） | （評価） | （対象） |

## 3. 各商品のメリット・デメリット詳細
### ① {p1}
- **メリット**:
- **デメリット**:

### ② {p2}
- **メリット**:
- **デメリット**:

### ③ {p3}
- **メリット**:
- **デメリット**:

## 4. 目的別のおすすめな選び方
- **◯◯を最優先したい人**: {p1} がおすすめ
- **コスパ・バランス重視の人**: {p2} がおすすめ
- **◯◯な機能を求める人**: {p3} がおすすめ

## 5. まとめ

"""
    res = call_gemini_with_retry(client, prompt)
    return res.text

# --- 3. はてなブログAtomPub投稿 ---
def post_to_hatena(hatena_id: str, blog_id: str, api_key: str, title: str, md_content: str):
    url = f"https://blog.hatena.ne.jp/{hatena_id}/{blog_id}/atom/entry"
   
    # テーブル・コードブロック対応のHTML変換
    html_content = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
   
    xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom"
       xmlns:app="http://www.w3.org/2007/app">
  <title>{title}</title>
  <content type="text/html"><![CDATA[
{html_content}
]]></content>
  <app:control>
    <app:draft>yes</app:draft>
  </app:control>
</entry>
"""
    headers = {'Content-Type': 'application/xml'}
    response = requests.post(
        url,
        data=xml_payload.encode('utf-8'),
        auth=(hatena_id, api_key),
        headers=headers
    )
   
    if response.status_code == 201:
        print("比較記事の下書き投稿が完了しました！（テーブルHTML変換済み）")
    else:
        print(f"はてなブログ投稿失敗: {response.status_code} - {response.text}")

# --- 4. メイン処理 ---
def main():
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    hatena_id = os.environ.get("HATENA_ID")
    hatena_blog_id = os.environ.get("HATENA_BLOG_ID")
    hatena_api_key = os.environ.get("HATENA_API_KEY")

    if not all([gemini_api_key, hatena_id, hatena_blog_id, hatena_api_key]):
        print("エラー: 必要な環境変数が設定されていません。")
        return

    client = genai.Client(api_key=gemini_api_key)

    if not os.path.exists("products.txt"):
        print("products.txt が見つかりません。")
        return

    with open("products.txt", "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines:
        print("products.txt に対象商品がありません。")
        return

    # 1行からカンマ区切りで3商品を取得
    target_line = lines[0]
    remaining_lines = lines[1:]
    products = [p.strip() for p in target_line.split(",") if p.strip()]

    if len(products) < 3:
        print("エラー: products.txt の1行にはカンマ区切りで3つの商品名を入力してください。")
        return

    print(f"今回の比較対象3商品: {products}")

    # 1. 比較記事の生成
    print("Geminiで比較記事を生成中...")
    article_md = generate_compare_article(client, products)
    title = f"【徹底比較】{products[0]} VS {products[1]} VS {products[2]} おすすめ人気3選"

    # 2. はてなブログへ下書き投稿
    print("はてなブログへ下書き送信中...")
    post_to_hatena(hatena_id, hatena_blog_id, hatena_api_key, title, article_md)

    # 3. products.txt の更新
    with open("products.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(remaining_lines) + ("\n" if remaining_lines else ""))

    print("処理完了: 比較記事を投稿し、リストを更新しました。")

if __name__ == "__main__":
    main()
