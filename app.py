import streamlit as st
import pandas as pd
import time
import sys

# 既存のファイルからクラスと設定をインポート
# ※ ファイル名が indeed_job_analyzer.py である前提
from indeed_job_analyzer import TalentScopeAI, GROQ_API_KEY

# ==========================================
# ページ設定
# ==========================================
st.set_page_config(
    page_title="TalentScope AI Dashboard",
    page_icon="🕵️",
    layout="wide"
)

# タイトルエリア
st.title("🕵️ TalentScope AI - 競合分析ダッシュボード")
st.markdown("Indeedの求人情報をAIが自動収集・分析し、レポートを作成します。")

# ==========================================
# サイドバー（設定エリア）
# ==========================================
with st.sidebar:
    st.header("⚙️ 設定")
    
    # APIキー入力（デフォルトはファイルの定数を使用）
    api_key_input = st.text_input("Groq API Key", value=GROQ_API_KEY, type="password")
    
    st.markdown("---")
    st.subheader("📋 分析対象リスト")
    st.caption("形式: 企業名@エリア (カンマ区切り)")
    
    # デフォルト値の設定
    default_companies = """
    株式会社エレファントストーン@東京都渋谷区,
    株式会社Example@大阪府
    """
    
    company_input = st.text_area("企業リスト", value=default_companies.strip(), height=150)
    
    start_button = st.button("🚀 分析を開始する", type="primary", use_container_width=True)
    
    st.markdown("---")
    st.info("※ Indeedへのアクセスはスクレイピング対策によりブロックされる可能性があります。")

# ==========================================
# メイン処理
# ==========================================
if start_button:
    if not api_key_input:
        st.error("❌ APIキーが設定されていません。")
        st.stop()
        
    if not company_input:
        st.warning("⚠️ 企業リストを入力してください。")
        st.stop()

    # 入力データの整形
    input_str = company_input.replace("，", ",").replace("　", " ").strip()
    raw_list = [x.strip() for x in input_str.split(",") if x.strip()]
    
    companies_info = []
    for item in raw_list:
        if "@" in item:
            parts = item.split("@")
            companies_info.append({"name": parts[0].strip(), "loc": parts[1].strip()})
        else:
            companies_info.append({"name": item, "loc": None})

    # インスタンス化
    analyzer = TalentScopeAI(api_key=api_key_input)
    results = {}
    
    # 全体進捗バー
    progress_bar = st.progress(0)
    
    # コンテナを作成（ログ表示用）
    log_container = st.container()

    try:
        # 1. 業界情報の学習
        with st.status("🌍 業界コンテキストを学習中...", expanded=True) as status:
            status.write("Web検索を実行中...")
            web_info = analyzer.search_web_for_company_info(companies_info)
            status.write("業界フィルターを生成中...")
            filter_data = analyzer.generate_strict_filter(web_info)
            status.update(label="✅ 準備完了", state="complete", expanded=False)
            
            st.success(f"ターゲット業界: **{filter_data.get('target_industry')}**")

        # 2. 各企業の検索実行
        all_jobs_df = [] # テーブル表示用データ
        
        for i, comp in enumerate(companies_info):
            company_name = comp['name']
            
            # ステータス表示（折りたたみ可能なログ）
            with st.status(f"🔍 {company_name} を調査中... ({i+1}/{len(companies_info)})", expanded=True) as status:
                
                # 実際の検索処理を実行
                # コンソールへのprint出力をキャプチャするのは難しいため、
                # 処理が終わるのを待って結果を表示する形になります
                data = analyzer.run_single_search(comp, filter_data)
                
                if data and data['count'] > 0:
                    status.write(f"✅ {data['count']}件の求人を検出しました")
                    results[company_name] = data
                    
                    # テーブル用データの蓄積（手順1の修正をしていない場合はここはスキップされます）
                    if 'raw_data' in data:
                        for job in data['raw_data']:
                            if isinstance(job, dict):
                                job['company'] = company_name # 企業名を追加
                                all_jobs_df.append(job)
                else:
                    status.write("⚠️ 求人が見つかりませんでした")
                    results[company_name] = {"count": 0, "jobs": "", "raw_data": []}
                
                status.update(label=f"✅ {company_name} 完了", state="complete", expanded=False)
            
            # 進捗バー更新
            progress_bar.progress((i + 1) / len(companies_info))

        # 3. 最終レポート生成
        if results:
            st.divider()
            st.header("📊 分析結果")
            
            # タブで表示を切り替え
            tab1, tab2 = st.tabs(["📝 AIレポート", "📋 求人データ一覧"])
            
            with tab1:
                with st.spinner("🧠 最終レポートを作成中..."):
                    final_report = analyzer.analyze_with_groq(results, companies_info, filter_data)
                    
                    # テキストエリアでコピーしやすく表示
                    st.text_area("分析レポート", value=final_report, height=600)
                    
                    # ダウンロードボタン
                    st.download_button(
                        label="📥 レポートをダウンロード (.txt)",
                        data=final_report,
                        file_name="indeed_analysis_report.txt"
                    )

            with tab2:
                if all_jobs_df:
                    df = pd.DataFrame(all_jobs_df)
                    # 不要なカラムや順序の整理（存在する場合のみ）
                    display_cols = [c for c in ['company', 'title', 'salary', 'location', 'url'] if c in df.columns]
                    if display_cols:
                        st.dataframe(
                            df[display_cols],
                            column_config={
                                "url": st.column_config.LinkColumn("リンク"),
                                "salary": "給与",
                                "title": "職種",
                                "company": "企業名"
                            },
                            use_container_width=True
                        )
                    else:
                        st.dataframe(df)
                else:
                    st.info("表示できる求人データがありません。")
        
    except Exception as e:
        st.error(f"エラーが発生しました: {e}")