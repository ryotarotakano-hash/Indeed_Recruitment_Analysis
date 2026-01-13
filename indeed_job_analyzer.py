# -*- coding: utf-8 -*-
import time
import random
import sys
import json
import re
import os
import urllib.parse
from DrissionPage import ChromiumPage, ChromiumOptions
from bs4 import BeautifulSoup
from groq import Groq, RateLimitError
from duckduckgo_search import DDGS

# ==========================================
# 設定エリア
# ==========================================
GROQ_API_KEY = "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"

MODEL_HEAVY = "llama-3.3-70b-versatile"
MODEL_LIGHT = "llama-3.1-8b-instant"

class TalentScopeAI:
    def __init__(self, api_key):
        if not api_key:
            print("❌ エラー: APIキー設定なし")
            sys.exit(1)
        self.client = Groq(api_key=api_key)

    def _call_groq_safe(self, messages, model_id, response_format=None, allow_fallback=False):
        max_retries = 5
        wait_time = 20
        current_model = model_id

        for attempt in range(max_retries):
            try:
                if response_format:
                    return self.client.chat.completions.create(
                        messages=messages,
                        model=current_model,
                        temperature=0.1,
                        response_format=response_format
                    )
                else:
                    return self.client.chat.completions.create(
                        messages=messages,
                        model=current_model,
                        temperature=0.6,
                    )
            except RateLimitError:
                print(f"   ⏳ API制限({current_model})。{wait_time}秒 待機...")
                time.sleep(wait_time)
                wait_time += 15
                if allow_fallback and current_model == MODEL_HEAVY and attempt >= 1:
                    current_model = MODEL_LIGHT
            except Exception as e:
                if "decommissioned" in str(e) or "not found" in str(e):
                    current_model = MODEL_LIGHT
                    continue
                return None
        return None

    def search_web_for_company_info(self, companies_list):
        print(f"\n🌍 Web検索で業界コンテキストを学習中...")
        search_results_text = ""
        with DDGS() as ddgs:
            for comp in companies_list:
                name = comp['name']
                try:
                    query = f"{name} 事業内容 業界"
                    results = list(ddgs.text(query, max_results=2))
                    info = f"■{name}の情報:\n"
                    for r in results:
                        info += f"- {r['body']}\n"
                    search_results_text += info + "\n"
                    print(f"   🔎 {name}: 情報を取得")
                    time.sleep(1)
                except Exception as e:
                    print(f"   ⚠️ {name}の検索失敗: {e}")
        return search_results_text

    def generate_strict_filter(self, search_results):
        print("🧠 AIが業界フィルターを作成中...")
        prompt = f"""
        Based on these search results, define the industry and negative keywords.
        Results: {search_results}
        JSON Format: {{ "target_industry": "Industry Name", "negative_keywords": "List of keywords to exclude" }}
        """
        response = self._call_groq_safe(
            messages=[{"role": "user", "content": prompt}],
            model_id=MODEL_HEAVY,
            response_format={"type": "json_object"}
        )
        try:
            return json.loads(response.choices[0].message.content)
        except:
            return {"target_industry": "General", "negative_keywords": ""}

    # ==========================================
    # ▼ DrissionPage設定 (ステルス強化版)
    # ==========================================
    def _create_drission_driver(self):
        co = ChromiumOptions()
        
        # 記憶（Cookie）を保存するフォルダを設定
        # これにより、一度突破すれば次回から「顔なじみ」になります
        current_dir = os.getcwd()
        user_data_path = os.path.join(current_dir, "browser_data_stealth")
        co.set_user_data_path(user_data_path)

        # 必須: 自動化フラグを消す
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-infobars')
        co.set_argument('--lang=ja-JP')
        
        # 必須: 最新のChromeとして振る舞うUser-Agent
        co.set_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')

        # ポート衝突回避
        co.auto_port()

        try:
            page = ChromiumPage(co)
            return page
        except Exception as e:
            print(f"   ⚠️ ブラウザ起動エラー(自動修復します): {e}")
            time.sleep(3)
            return ChromiumPage(co)

    def _human_like_mouse_move(self, page):
        """ マウスを人間のようにランダムに動かす """
        try:
            # 画面の中央付近で適当に動かす
            width = 1920
            height = 1080
            for _ in range(3):
                x = random.randint(100, width - 100)
                y = random.randint(100, height - 100)
                # DrissionPageにはマウス移動シミュレーションがないため
                # JSを使ってスクロール等で代用して「活動」をアピール
                page.scroll.to_location(x, y)
                time.sleep(random.uniform(0.1, 0.3))
        except:
            pass

    def _solve_cloudflare(self, page):
        """ Cloudflare突破ロジック（強化版） """
        time.sleep(2)
        title = page.title.lower() if page.title else ""
        
        # Cloudflareの画面かチェック
        if "verify" in title or "challenge" in title or "security" in title or page.ele("text:人間であることを確認"):
            print("   🛡️ Cloudflare検知。ステルス突破モード起動...")
            
            # 1. まず人間らしくマウスを揺らす（超重要）
            self._human_like_mouse_move(page)
            time.sleep(random.uniform(1.5, 3.0))

            # 2. iframeの中のチェックボックスを探してクリック
            found_checkbox = False
            for _ in range(5): # 5回トライ
                try:
                    iframe = page.get_frame('@src^https://challenges.cloudflare.com')
                    if iframe:
                        # チェックボックスっぽい要素を全検索
                        # input type=checkbox だけでなく、クリック可能なbodyも狙う
                        target = iframe.ele('tag:input')
                        if not target: target = iframe.ele('@type=checkbox')
                        if not target: target = iframe.ele('tag:body') # 最終手段：iframe全体を押す

                        if target:
                            print("   👉 自動クリックを実行します...")
                            target.click()
                            found_checkbox = True
                            break
                except:
                    pass
                time.sleep(1)

            # 3. 結果待ち (もし自動でダメなら、人間が押すのを待つ)
            # 待機時間を【3分】に延長しました。ゆっくり手動クリックしてください。
            print("   ⏳ 【重要】認証画面です。もし画面が変わらない場合、")
            print("   ⏳ 手動で『人間であることを確認』をクリックしてください！(3分待ちます)")
            
            start_time = time.time()
            while time.time() - start_time < 180: # 180秒待機
                title = page.title.lower() if page.title else ""
                if "verify" not in title and "challenge" not in title and "security" not in title:
                    print("   🚀 突破成功！（または手動認証完了）")
                    # 成功したら少し待ってCookieを馴染ませる
                    time.sleep(3)
                    return
                time.sleep(1)
            
            print("   ⚠️ 時間切れ。今回はスキップします。")

    def extract_jobs_via_ai(self, raw_html, company, location, filter_data):
        print(f"   🤖 Groq解析中... ({company})")
        soup = BeautifulSoup(raw_html, "html.parser")

        extracted_jobs_text = ""
        
        job_titles = soup.find_all("h2", class_=lambda x: x and "jobTitle" in x)
        if not job_titles:
            job_links = soup.find_all("a", href=True)
            candidates = [a for a in job_links if "jk=" in a['href'] or "/rc/clk" in a['href']]
        else:
            candidates = [h2.find("a") for h2 in job_titles if h2.find("a")]

        for i, a_tag in enumerate(candidates):
            if not a_tag: continue
            
            href = a_tag.get('href', '')
            jk_id = ""
            if "jk=" in href:
                match = re.search(r'jk=([a-zA-Z0-9]+)', href)
                if match: jk_id = match.group(1)
            
            stable_url = f"https://jp.indeed.com/viewjob?jk={jk_id}" if jk_id else "URL_NOT_FOUND"
            title = a_tag.get_text(strip=True)
            
            card = a_tag.find_parent("div", class_=lambda x: x and "card" in x.lower()) 
            if not card: card = a_tag.find_parent("td")
            if not card: card = a_tag.find_parent("div")

            card_text = card.get_text(separator=" | ", strip=True) if card else ""
            
            extracted_jobs_text += f"""
            [JOB_BLOCK_{i+1}]
            Title: {title}
            URL: {stable_url}
            RawContent: {card_text}
            --------------------------------
            """

        if not extracted_jobs_text:
            print("   ⚠️ 構造化抽出失敗。全文モードへ。")
            for tag in soup(["script", "style", "svg", "path", "footer", "nav", "noscript", "header"]):
                tag.decompose()
            extracted_jobs_text = soup.get_text(separator=" ", strip=True)[:18000]

        location_instruction = ""
        if location:
            location_instruction = f"4. LOCATION: Prioritize jobs in '{location}', but if the job is clearly for {company}, include it."

        prompt = f"""
        Extract job postings for "{company}" from the text.
        FILTERING RULES:
        1. Industry: {filter_data['target_industry']}
        2. Exclude keywords: {filter_data['negative_keywords']}
        3. Exclude Hotel/Clinic staff unless target is one.
        {location_instruction}
        
        Return JSON list: 
        [
          {{
            "title": "Job Title",
            "url": "URL found in block", 
            "salary": "Salary text",
            "location": "Location",
            "remote": "Remote Info",
            "details": "Summary"
          }}
        ]
        If no relevant jobs found, return [].
        
        TEXT BLOCKS:
        {extracted_jobs_text[:25000]}
        """

        response = self._call_groq_safe(
            messages=[{"role": "user", "content": prompt}],
            model_id=MODEL_LIGHT, 
            response_format={"type": "json_object"}
        )

        if not response: return []
        try:
            data = json.loads(response.choices[0].message.content)
            if isinstance(data, dict):
                for key in data:
                    if isinstance(data[key], list): return data[key]
                return [] 
            return data
        except:
            return []

    def _extract_prefecture(self, address):
        if not address: return None
        match = re.search(r'(.+?[都道府県])', address)
        if match: return match.group(1)
        return None

    def run_single_search(self, company_info, filter_data):
        raw_name = company_info['name']
        original_loc = company_info['loc']

        clean_name = raw_name
        search_loc = original_loc
        if not search_loc and (" " in raw_name or "　" in raw_name):
            parts = re.split(r'[ 　]', raw_name)
            if any(x in parts[1] for x in ["都", "道", "府", "県", "市", "区"]):
                print(f"   💡 住所自動検出: {parts[1]}")
                clean_name = parts[0]
                search_loc = parts[1]

        strategies = []
        strategies.append({"q": clean_name, "l": search_loc, "desc": "指定エリア"})
        if search_loc:
            pref = self._extract_prefecture(search_loc)
            if pref and pref != search_loc:
                strategies.append({"q": clean_name, "l": pref, "desc": "都道府県"})
        strategies.append({"q": clean_name, "l": None, "desc": "全国"})

        MAX_RETRIES = 2 

        for strategy in strategies:
            q_val = strategy["q"]
            l_val = strategy["l"]
            desc = strategy["desc"]

            for attempt in range(MAX_RETRIES):
                page = None
                try:
                    retry_label = f" ({desc} - 試行{attempt+1})"
                    print(f"🔍 '{q_val}' を検索中... エリア: {l_val if l_val else '全国'}{retry_label}")
                    
                    page = self._create_drission_driver()
                    
                    # 戦略: まずトップページに行って、人間アピールをする
                    if attempt == 0:
                        page.get("https://jp.indeed.com/")
                        self._solve_cloudflare(page)
                    
                    # 本番検索
                    base_url = f"https://jp.indeed.com/jobs?q={urllib.parse.quote(q_val)}"
                    if l_val:
                        base_url += f"&l={urllib.parse.quote(l_val)}"
                    
                    page.get(base_url)
                    
                    # 再度チェック
                    self._solve_cloudflare(page)
                    
                    # 読み込み待機
                    time.sleep(2)
                    page.scroll.to_bottom()
                    time.sleep(1)
                    
                    html_content = page.html
                    jobs_data = self.extract_jobs_via_ai(html_content, q_val, l_val, filter_data)
                    
                    page.quit() # 終わったら閉じる
                    
                    if jobs_data is not None and len(jobs_data) > 0:
                        print(f"   ✅ ヒットしました！ ({len(jobs_data)}件)")
                        
                        formatted_jobs = ""
                        count = 0
                        for job in jobs_data[:10]:
                            if isinstance(job, dict):
                                t = job.get('title', '不明')
                                u = job.get('url', '#')
                                sal = job.get('salary', 'なし')
                                l = job.get('location', 'なし')
                                r = job.get('remote', '不明')
                                d = job.get('details', '')
                                formatted_jobs += f"JOB_START\nTitle:{t}\nURL:{u}\nSalary:{sal}\nLoc:{l}\nRem:{r}\nDet:{d}\nJOB_END\n"
                                count += 1
                        
                        return {"count": len(jobs_data), "jobs": formatted_jobs, "raw_data": jobs_data}
                    
                    else:
                        print(f"   ⚠️ 求人なし (次の戦略へ)")
                        continue 

                except Exception as e:
                    print(f"   ⚠️ エラー: {e}")
                    time.sleep(3)
                    continue 

        return None

    def analyze_with_groq(self, company_data_list, companies_info, filter_data):
        print("\n🧠 Groqで最終レポートを作成中...")
        input_data_str = ""
        for comp in companies_info:
            name = comp['name'] 
            loc_req = comp['loc']
            data = company_data_list.get(name)
            
            input_data_str += f"\n### 対象企業: {name} (希望エリア: {loc_req if loc_req else '指定なし/自動検出'})\n"
            if data and data['count'] > 0:
                input_data_str += f"検出数: {data['count']}\n{data['jobs']}\n"
            else:
                input_data_str += f"ステータス: 該当求人なし\n"
            input_data_str += "-"*10

        prompt = f"""
        あなたは採用アナリストです。以下のデータからレポートを作成してください。
        ターゲット業界: {filter_data['target_industry']}
        
        【重要指示: 出力形式】
        1. プレーンテキストのみ使用 (Markdown記号なし)。
        2. 以下のテンプレに完全に準拠すること。
        3. 「8. 求人票リンク」のセクションを最後に追加し、そこにURLをまとめること。
        
        【出力テンプレート】
        
        【企業名】 (エリア: [エリア])
        
        1. 給料
           [職種名] : [金額]
           [職種名] : [金額]
        
        2. 福利厚生
           [内容]
        
        3. 訴求ポイント
           [内容]
        
        4. 勤務地
           [内容]
        
        5. 勤務時間
           [内容]
        
        6. リモートワーク
           [内容]
        
        7. 業務内容・案件
           [内容]
        
        8. 求人票リンク
           [職種名] : [URL]
           [職種名] : [URL]
        
        --------------------------------------------------
        
        【データ】
        {input_data_str}
        """
        response = self._call_groq_safe(
            messages=[{"role": "user", "content": prompt}],
            model_id=MODEL_HEAVY,
            allow_fallback=True 
        )
        text = response.choices[0].message.content if response else "❌ 生成失敗"
        
        clean_text = text.replace("**", "").replace("##", "■").replace("###", "■").replace("* ", "・")
        clean_text = re.sub(r'^\s*-\s', '・', clean_text, flags=re.MULTILINE)
        
        return clean_text

def main():
    print("=========================================")
    print("   TalentScope AI - Final Stealth Ver    ")
    print("=========================================")
    
    input_str = input("企業リストを入力してください (例: 株式会社エレファントストーン@東京都渋谷区)\n> ")
    input_str = input_str.replace("，", ",").replace("　", " ").strip()
    
    raw_list = [x.strip() for x in input_str.split(",") if x.strip()]
    companies_info = []
    
    for item in raw_list:
        if "@" in item:
            parts = item.split("@")
            companies_info.append({"name": parts[0].strip(), "loc": parts[1].strip()})
        else:
            companies_info.append({"name": item, "loc": None})
            
    if not companies_info: return

    analyzer = TalentScopeAI(api_key=GROQ_API_KEY)
    
    web_info = analyzer.search_web_for_company_info(companies_info)
    filter_data = analyzer.generate_strict_filter(web_info)
    
    results = {}
    for comp in companies_info:
        if len(results) > 0:
            print("   ☕ 次の検索へ...")
            time.sleep(2)
        
        data = analyzer.run_single_search(comp, filter_data)
        results[comp['name']] = data

    if results:
        report = analyzer.analyze_with_groq(results, companies_info, filter_data)
        print("\n" + "="*50)
        print("          分析レポート結果")
        print("="*50 + "\n")
        print(report)

if __name__ == "__main__":
    main()
