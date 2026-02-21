import json
import yfinance as yf
import openai
import requests
import smtplib
import argparse
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ==========================================
# CONFIGURATION (Utilisez des variables d'env)
# ==========================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "votre@email.com")
# Support de plusieurs destinataires séparés par des virgules
RECIPIENT_EMAILS = os.getenv("RECIPIENT_EMAILS", "destinataire1@email.com,destinataire2@email.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")  # Mot de passe d'application
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Configuration du fuseau horaire (modifiable)
TIMEZONE = "Europe/Paris"  # Changez selon votre localisation

def get_local_time():
    """Retourne l'heure locale actuelle dans le fuseau configuré."""
    return datetime.now(ZoneInfo(TIMEZONE))

def format_datetime(dt, format_str='%d/%m/%Y à %H:%M:%S'):
    """Formate une datetime dans le fuseau horaire local."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(TIMEZONE)).strftime(format_str)

def call_openai(prompt, system=None, model='gpt-4o-mini'):
    """Appel à l'API OpenAI avec gestion d'erreurs."""
    if not OPENAI_API_KEY:
        return None
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = client.chat.completions.create(model=model, messages=messages, temperature=0.7)
        return resp.choices[0].message.content
    except Exception as e:
        print(f"❌ Erreur OpenAI: {e}")
        return None

def get_dynamic_assets_from_ai():
    """L'IA sélectionne les actifs les plus pertinents avec noms complets."""
    print("🔍 L'IA sélectionne les actifs les plus pertinents...")
    
    system_prompt = """Tu es un analyste financier senior spécialisé dans la sélection d'actifs boursiers. 
Tu as une connaissance approfondie des marchés américains et européens, des secteurs porteurs et des catalyseurs de marché."""
    
    current_time = get_local_time()
    prompt = f"""Date et heure actuelles: {format_datetime(current_time, '%A %d %B %Y à %H:%M')}

Mission: Sélectionne les 20 actifs les plus stratégiques à surveiller aujourd'hui en tenant compte:
- Des tendances sectorielles actuelles (IA, semi-conducteurs, énergie, luxe, etc.)
- De la volatilité et liquidité des titres
- Des événements macro-économiques récents
- De la diversification sectorielle

Structure de réponse (JSON uniquement, sans markdown):
{{
  "us_actions": [
    {{"ticker": "NVDA", "name": "NVIDIA Corporation"}},
    {{"ticker": "TSLA", "name": "Tesla Inc."}},
    ... (8 actions US au total)
  ],
  "eu_actions": [
    {{"ticker": "ASML.AS", "name": "ASML Holding NV"}},
    {{"ticker": "MC.PA", "name": "LVMH Moët Hennessy"}},
    ... (8 actions EU au total avec suffixes corrects: .PA=Paris, .AS=Amsterdam, .DE=Francfort, .MI=Milan, .MC=Madrid, .CO=Copenhague)
  ],
  "etfs": [
    {{"ticker": "SPY", "name": "S&P 500 ETF Trust"}},
    {{"ticker": "QQQ", "name": "Nasdaq-100 ETF"}},
    ... (4 ETFs diversifiés: indices larges, sectoriels, géographiques)
  ]
}}

Critères de sélection:
- Actions US: Méga-caps tech + secteurs volatils + opportunités du moment
- Actions EU: Leaders européens multi-secteurs (luxe, industrie, tech, pharma, finance)
- ETFs: Mix d'indices larges + ETFs thématiques/sectoriels pertinents aujourd'hui

Retourne UNIQUEMENT le JSON, rien d'autre."""

    resp = call_openai(prompt, system=system_prompt)
    try:
        clean_resp = resp.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_resp)
    except Exception as e:
        print(f"⚠️ Erreur parsing IA, utilisation de la sélection par défaut: {e}")
        return {
            "us_actions": [
                {"ticker": "AAPL", "name": "Apple Inc."},
                {"ticker": "MSFT", "name": "Microsoft Corporation"},
                {"ticker": "NVDA", "name": "NVIDIA Corporation"},
                {"ticker": "TSLA", "name": "Tesla Inc."},
                {"ticker": "AMZN", "name": "Amazon.com Inc."},
                {"ticker": "META", "name": "Meta Platforms Inc."},
                {"ticker": "GOOGL", "name": "Alphabet Inc."},
                {"ticker": "AMD", "name": "Advanced Micro Devices"}
            ],
            "eu_actions": [
                {"ticker": "SAP.DE", "name": "SAP SE"},
                {"ticker": "ASML.AS", "name": "ASML Holding NV"},
                {"ticker": "MC.PA", "name": "LVMH Moët Hennessy"},
                {"ticker": "OR.PA", "name": "L'Oréal SA"},
                {"ticker": "SIE.DE", "name": "Siemens AG"},
                {"ticker": "AIR.PA", "name": "Airbus SE"},
                {"ticker": "TTE.PA", "name": "TotalEnergies SE"},
                {"ticker": "SAN.MC", "name": "Banco Santander SA"}
            ],
            "etfs": [
                {"ticker": "SPY", "name": "S&P 500 ETF Trust"},
                {"ticker": "QQQ", "name": "Nasdaq-100 ETF"},
                {"ticker": "SMH", "name": "VanEck Semiconductor ETF"},
                {"ticker": "VWO", "name": "Vanguard Emerging Markets ETF"}
            ]
        }

def get_market_data(assets_list):
    """Récupère les données de marché avec noms complets et timestamps précis."""
    data = []
    for asset in assets_list:
        ticker = asset['ticker']
        name = asset['name']
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="5d")
            if hist.empty:
                print(f"⚠️ Pas de données pour {ticker}")
                continue
            
            # Récupération du dernier cours
            last_row = hist.iloc[-1]
            current_price = float(last_row['Close'])
            prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_price
            change_pct = ((current_price - prev_close) / prev_close) * 100 if prev_close != 0 else 0
            
            # Formatage détaillé de l'heure de la dernière donnée
            last_timestamp = hist.index[-1]
            last_update_full = format_datetime(last_timestamp, '%d/%m/%Y %H:%M:%S')
            last_update_short = format_datetime(last_timestamp, '%H:%M')
            
            # Calcul du délai depuis la dernière mise à jour
            time_diff = get_local_time() - last_timestamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(TIMEZONE))
            minutes_ago = int(time_diff.total_seconds() / 60)
            
            if minutes_ago < 60:
                time_ago = f"il y a {minutes_ago} min"
            elif minutes_ago < 1440:  # moins de 24h
                hours_ago = minutes_ago // 60
                time_ago = f"il y a {hours_ago}h"
            else:
                days_ago = minutes_ago // 1440
                time_ago = f"il y a {days_ago}j"
            
            # Informations supplémentaires
            info = stock.info
            currency = info.get('currency', 'USD')
            market_cap = info.get('marketCap', 0)
            
            # Détermination du statut de marché
            market_status = "Fermé"
            if '.PA' in ticker or '.AS' in ticker or '.DE' in ticker or '.MI' in ticker or '.MC' in ticker:
                # Marchés européens (9h00-17h30 CET)
                current_hour = get_local_time().hour
                if 9 <= current_hour < 18:
                    market_status = "Ouvert"
            else:
                # Marchés US (9h30-16h00 EST = 15h30-22h00 CET)
                current_hour = get_local_time().hour
                if 15 <= current_hour < 22:
                    market_status = "Ouvert"
            
            data.append({
                "symbol": ticker,
                "name": name,
                "price": current_price,
                "change_pct": change_pct,
                "currency": currency,
                "market_cap": market_cap,
                "last_update_full": last_update_full,
                "last_update_short": last_update_short,
                "time_ago": time_ago,
                "market_status": market_status
            })
        except Exception as e:
            print(f"❌ Erreur pour {ticker} ({name}): {e}")
            continue
    return data

def get_market_context():
    """Récupère le contexte de marché et les événements du jour."""
    print("🌍 Récupération du contexte de marché...")
    
    system_prompt = """Tu es un analyste macro-économique qui suit l'actualité financière en temps réel.
Tu identifies les catalyseurs de marché, les événements géopolitiques et les publications économiques importantes."""
    
    current_time = get_local_time()
    prompt = f"""Date et heure: {format_datetime(current_time, '%A %d %B %Y à %H:%M')}

Analyse le contexte de marché actuel et fournis un JSON structuré:

{{
  "market_sentiment": "Haussier|Baissier|Neutre|Mixte",
  "main_events": [
    "Événement macro-économique majeur du jour",
    "Actualité géopolitique impactante",
    "Publication économique clé"
  ],
  "sector_focus": ["Secteur à surveiller 1", "Secteur 2", "Secteur 3"],
  "risk_level": "Faible|Modéré|Élevé",
  "key_message": "Message synthétique de 2 phrases sur l'ambiance de marché"
}}

Concentre-toi sur les éléments qui impactent réellement les marchés boursiers aujourd'hui.
Retourne UNIQUEMENT le JSON."""

    resp = call_openai(prompt, system=system_prompt)
    try:
        clean_resp = resp.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_resp)
    except Exception:
        return {
            "market_sentiment": "Mixte",
            "main_events": ["Données macro-économiques attendues", "Tension géopolitique persistante"],
            "sector_focus": ["Technologie", "Finance", "Énergie"],
            "risk_level": "Modéré",
            "key_message": "Les marchés évoluent dans un contexte d'incertitude modérée avec une attention particulière sur les valeurs technologiques."
        }

def get_ai_analysis(ticker_data, market_context):
    """Analyse IA améliorée avec contexte de marché."""
    system_prompt = """Tu es un analyste financier quantitatif senior. Tes analyses sont:
- Concises et factuelles
- Basées sur les tendances de prix et le contexte macro
- Orientées action avec des recommandations claires
- Conscientes des risques"""
    
    prompt = f"""Contexte de marché: {market_context['market_sentiment']} | Secteurs focus: {', '.join(market_context['sector_focus'])}

Actif: {ticker_data['symbol']} - {ticker_data['name']}
Prix actuel: {ticker_data['price']:.2f} {ticker_data['currency']}
Variation: {ticker_data['change_pct']:.2f}%
Cap. boursière: {ticker_data['market_cap']:,} (si disponible)
Statut: {ticker_data['market_status']} (dernière màj: {ticker_data['time_ago']})

Fournis une analyse JSON:
{{
  "recommendation": "🟢 Acheter|🔴 Vendre|🟡 Maintenir|⚪ Observer",
  "analysis": "Analyse en 1 phrase courte et percutante (max 15 mots)",
  "confidence": "Haute|Moyenne|Faible",
  "event": true|false,
  "event_desc": "Si événement spécifique détecté pour cet actif (résultats, news, catalyseur)",
  "short_term_bias": "Haussier|Baissier|Neutre"
}}

Sois précis et évite le jargon inutile. Retourne UNIQUEMENT le JSON."""

    resp = call_openai(prompt, system=system_prompt)
    try:
        clean_resp = resp.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_resp)
    except Exception:
        return {
            "recommendation": "🟡 Maintenir",
            "analysis": "Analyse indisponible",
            "confidence": "Faible",
            "event": False,
            "event_desc": "",
            "short_term_bias": "Neutre"
        }

def generate_recommendations(us_data, eu_data, market_context):
    """Génère des recommandations stratégiques personnalisées."""
    print("💡 Génération des recommandations stratégiques...")
    
    system_prompt = """Tu es un conseiller en investissement qui synthétise les analyses pour proposer des stratégies actionnables."""
    
    # Préparation des top movers
    all_data = us_data + eu_data
    top_gainers = sorted([d for d in all_data if d['change_pct'] > 0], key=lambda x: x['change_pct'], reverse=True)[:3]
    top_losers = sorted([d for d in all_data if d['change_pct'] < 0], key=lambda x: x['change_pct'])[:3]
    
    prompt = f"""Contexte: {market_context['key_message']}
Sentiment: {market_context['market_sentiment']}
Événements: {', '.join(market_context['main_events'])}

Top hausses: {', '.join([f"{d['symbol']} ({d['change_pct']:+.1f}%)" for d in top_gainers])}
Top baisses: {', '.join([f"{d['symbol']} ({d['change_pct']:+.1f}%)" for d in top_losers])}

Génère 3 recommandations stratégiques concrètes et actionnables pour aujourd'hui en JSON:
{{
  "recommendations": [
    {{
      "icon": "🎯|💰|⚡|🛡️|📊",
      "title": "Titre court et impactant",
      "description": "Recommandation concrète en 1-2 phrases (max 25 mots)"
    }},
    ... (3 au total)
  ]
}}

Les recommandations doivent être:
- Spécifiques au contexte du jour
- Orientées action (secteurs, types d'actifs, stratégies)
- Équilibrées (opportunités + risques)

Retourne UNIQUEMENT le JSON."""

    resp = call_openai(prompt, system=system_prompt)
    try:
        clean_resp = resp.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_resp)
    except Exception:
        return {
            "recommendations": [
                {"icon": "🎯", "title": "Diversification sectorielle", "description": "Répartir les positions entre tech, finance et matières premières."},
                {"icon": "📊", "title": "Surveillance des volumes", "description": "Observer les volumes de trading pour confirmer les tendances."},
                {"icon": "🛡️", "title": "Gestion du risque", "description": "Maintenir des stop-loss sur les positions volatiles."}
            ]
        }

def generate_html(summary, us_data, eu_data, market_context, recommendations, generation_time):
    """Génère un rapport HTML avec design moderne et épuré."""
    now = format_datetime(generation_time, '%d/%m/%Y à %H:%M:%S')
    now_short = format_datetime(generation_time, '%d/%m/%Y à %H:%M')
    
    # Calcul des statistiques
    all_data = us_data + eu_data
    nb_hausse = len([d for d in all_data if d['change_pct'] > 0])
    nb_baisse = len([d for d in all_data if d['change_pct'] < 0])
    avg_variation = sum([d['change_pct'] for d in all_data]) / len(all_data) if all_data else 0
    
    # Détermination de la couleur du sentiment
    sentiment_colors = {
        "Haussier": "#10b981",
        "Baissier": "#ef4444",
        "Neutre": "#f59e0b",
        "Mixte": "#8b5cf6"
    }
    sentiment_color = sentiment_colors.get(market_context['market_sentiment'], "#6b7280")
    
    style = """
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #1f2937;
            padding: 20px;
            line-height: 1.6;
        }
        .container { 
            max-width: 1200px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
            color: #ffffff;
            padding: 50px 40px;
            position: relative;
            overflow: hidden;
        }
        .header::before {
            content: '';
            position: absolute;
            top: -50%;
            right: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
        }
        .header-content { position: relative; z-index: 1; }
        .header h1 {
            font-size: 32px;
            font-weight: 800;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }
        .header p {
            opacity: 0.95;
            font-size: 15px;
            font-weight: 300;
        }
        .header-timestamp {
            display: inline-block;
            background: rgba(255,255,255,0.15);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 13px;
            margin-top: 10px;
            font-weight: 500;
        }
        
        .market-banner {
            background: linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%);
            padding: 30px 40px;
            border-bottom: 3px solid """ + sentiment_color + """;
        }
        .market-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .market-stat {
            background: white;
            padding: 15px 20px;
            border-radius: 12px;
            border-left: 4px solid """ + sentiment_color + """;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        .market-stat-label {
            font-size: 11px;
            text-transform: uppercase;
            color: #6b7280;
            font-weight: 600;
            letter-spacing: 0.5px;
            margin-bottom: 5px;
        }
        .market-stat-value {
            font-size: 24px;
            font-weight: 700;
            color: """ + sentiment_color + """;
        }
        .events-box {
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        .event-item {
            padding: 8px 0;
            border-left: 3px solid #3b82f6;
            padding-left: 12px;
            margin-bottom: 8px;
            font-size: 13px;
            color: #374151;
        }
        
        .content { padding: 40px; }
        
        .recommendations-section {
            background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 40px;
            border: 2px solid #fbbf24;
        }
        .recommendations-title {
            font-size: 20px;
            font-weight: 700;
            color: #92400e;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .recommendation-card {
            background: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-left: 5px solid #f59e0b;
        }
        .recommendation-card:last-child { margin-bottom: 0; }
        .rec-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;
        }
        .rec-icon {
            font-size: 24px;
        }
        .rec-title {
            font-size: 15px;
            font-weight: 700;
            color: #1f2937;
        }
        .rec-description {
            font-size: 13px;
            color: #4b5563;
            line-height: 1.6;
            padding-left: 36px;
        }
        
        .summary-box {
            background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
            border-radius: 16px;
            padding: 25px;
            margin-bottom: 40px;
            border: 2px solid #3b82f6;
        }
        .summary-box h2 {
            font-size: 18px;
            color: #1e3a8a;
            margin-bottom: 15px;
            font-weight: 700;
        }
        .summary-box p {
            color: #1e40af;
            line-height: 1.8;
            font-size: 14px;
        }
        
        .section-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 3px solid #e5e7eb;
        }
        .section-title {
            font-size: 22px;
            font-weight: 700;
            color: #1f2937;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .section-count {
            background: #3b82f6;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }
        
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            margin-bottom: 45px;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        }
        thead {
            background: linear-gradient(135deg, #1f2937 0%, #374151 100%);
        }
        th {
            text-align: left;
            padding: 16px 14px;
            color: #f9fafb;
            font-size: 11px;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.8px;
        }
        tbody tr {
            background: white;
            transition: all 0.2s ease;
        }
        tbody tr:hover {
            background: #f9fafb;
            transform: scale(1.002);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        tbody tr:nth-child(even) {
            background: #fafbfc;
        }
        td {
            padding: 20px 14px;
            border-bottom: 1px solid #e5e7eb;
            font-size: 13px;
            vertical-align: middle;
        }
        
        .asset-info {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .ticker {
            font-weight: 800;
            color: #1f2937;
            font-size: 15px;
            font-family: 'Courier New', monospace;
        }
        .asset-name {
            font-size: 11px;
            color: #6b7280;
            font-weight: 500;
        }
        .update-time {
            font-size: 10px;
            color: #9ca3af;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .market-status-badge {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 9px;
            font-weight: 700;
            text-transform: uppercase;
            margin-left: 4px;
        }
        .status-open {
            background: #d1fae5;
            color: #065f46;
        }
        .status-closed {
            background: #fee2e2;
            color: #991b1b;
        }
        .time-ago {
            color: #6b7280;
            font-weight: 600;
        }
        
        .price-cell {
            font-family: 'Courier New', Courier, monospace;
            font-weight: 700;
            font-size: 15px;
            color: #1f2937;
        }
        
        .pos { color: #10b981; font-weight: 700; }
        .neg { color: #ef4444; font-weight: 700; }
        .neutral { color: #6b7280; font-weight: 700; }
        
        .badge {
            padding: 6px 14px;
            border-radius: 8px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            display: inline-block;
            letter-spacing: 0.5px;
        }
        .badge-buy { background: #d1fae5; color: #065f46; border: 1px solid #10b981; }
        .badge-sell { background: #fee2e2; color: #991b1b; border: 1px solid #ef4444; }
        .badge-hold { background: #fef3c7; color: #92400e; border: 1px solid #f59e0b; }
        .badge-watch { background: #e5e7eb; color: #374151; border: 1px solid #6b7280; }
        
        .analysis-cell {
            line-height: 1.6;
            max-width: 400px;
        }
        .confidence-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 9px;
            font-weight: 600;
            margin-left: 6px;
            text-transform: uppercase;
        }
        .conf-haute { background: #d1fae5; color: #065f46; }
        .conf-moyenne { background: #fef3c7; color: #92400e; }
        .conf-faible { background: #fee2e2; color: #991b1b; }
        
        .event-text {
            color: #dc2626;
            font-size: 11px;
            font-weight: 600;
            margin-top: 8px;
            display: block;
            padding: 6px 10px;
            background: #fef2f2;
            border-left: 3px solid #ef4444;
            border-radius: 4px;
        }
        
        .bias-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 6px;
        }
        .bias-haussier { background: #10b981; }
        .bias-baissier { background: #ef4444; }
        .bias-neutre { background: #6b7280; }
        
        .footer {
            text-align: center;
            padding: 30px;
            font-size: 11px;
            color: #9ca3af;
            background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%);
            border-top: 2px solid #e5e7eb;
        }
        .footer strong {
            color: #374151;
            font-weight: 600;
        }
        .footer-timestamp {
            margin-top: 10px;
            font-size: 10px;
            color: #6b7280;
            font-style: italic;
        }
        
        @media (max-width: 768px) {
            .market-grid { grid-template-columns: 1fr; }
            table { font-size: 11px; }
            th, td { padding: 10px 8px; }
            .header h1 { font-size: 24px; }
            .content { padding: 20px; }
        }
    </style>
    """

    def build_rows(data):
        html = ""
        for item in data:
            # Détermination de la classe de couleur
            if item['change_pct'] > 0:
                color = "pos"
            elif item['change_pct'] < 0:
                color = "neg"
            else:
                color = "neutral"
            
            # Badge de recommandation
            reco = item['ai']['recommendation']
            if "Acheter" in reco:
                b_class = "badge-buy"
            elif "Vendre" in reco:
                b_class = "badge-sell"
            elif "Maintenir" in reco:
                b_class = "badge-hold"
            else:
                b_class = "badge-watch"
            
            # Badge de confiance
            conf = item['ai'].get('confidence', 'Moyenne')
            conf_class = f"conf-{conf.lower()}" if conf in ['Haute', 'Moyenne', 'Faible'] else "conf-moyenne"
            
            # Événement
            event = ""
            if item['ai']['event']:
                event = f"<span class='event-text'>⚠️ {item['ai']['event_desc']}</span>"
            
            # Indicateur de tendance court terme
            bias = item['ai'].get('short_term_bias', 'Neutre')
            bias_class = f"bias-{bias.lower()}"
            
            # Statut de marché
            status_class = "status-open" if item['market_status'] == "Ouvert" else "status-closed"
            
            html += f"""
            <tr>
                <td>
                    <div class="asset-info">
                        <span class="ticker">{item['symbol']}</span>
                        <span class="asset-name">{item['name']}</span>
                        <div class="update-time">
                            🕐 <span class="time-ago">{item['time_ago']}</span>
                            <span class="market-status-badge {status_class}">{item['market_status']}</span>
                        </div>
                    </div>
                </td>
                <td class="price-cell">{item['price']:.2f} {item['currency']}</td>
                <td>
                    <span class="bias-indicator {bias_class}"></span>
                    <span class="{color}">{item['change_pct']:+.2f}%</span>
                </td>
                <td><span class="badge {b_class}">{reco}</span></td>
                <td class="analysis-cell">
                    {item['ai']['analysis']}
                    <span class="confidence-badge {conf_class}">{conf}</span>
                    {event}
                </td>
            </tr>
            """
        return html

    # Construction des recommandations
    reco_html = ""
    for rec in recommendations['recommendations']:
        reco_html += f"""
        <div class="recommendation-card">
            <div class="rec-header">
                <span class="rec-icon">{rec['icon']}</span>
                <span class="rec-title">{rec['title']}</span>
            </div>
            <div class="rec-description">{rec['description']}</div>
        </div>
        """
    
    # Construction des événements
    events_html = ""
    for event in market_context['main_events']:
        events_html += f'<div class="event-item">📌 {event}</div>'

    return f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Rapport Boursier IA - {now_short}</title>
        {style}
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="header-content">
                    <h1>📊 Analyse Boursière Prédictive</h1>
                    <p>Rapport Stratégique Alimenté par Intelligence Artificielle</p>
                    <div class="header-timestamp">
                        🗓️ Généré le {now}
                    </div>
                </div>
            </div>
            
            <div class="market-banner">
                <div class="market-grid">
                    <div class="market-stat">
                        <div class="market-stat-label">Sentiment de Marché</div>
                        <div class="market-stat-value">{market_context['market_sentiment']}</div>
                    </div>
                    <div class="market-stat">
                        <div class="market-stat-label">Niveau de Risque</div>
                        <div class="market-stat-value">{market_context['risk_level']}</div>
                    </div>
                    <div class="market-stat">
                        <div class="market-stat-label">Actifs en Hausse</div>
                        <div class="market-stat-value">{nb_hausse}/{len(all_data)}</div>
                    </div>
                    <div class="market-stat">
                        <div class="market-stat-label">Variation Moyenne</div>
                        <div class="market-stat-value">{avg_variation:+.2f}%</div>
                    </div>
                </div>
                
                <div class="events-box">
                    <div class="market-stat-label" style="margin-bottom: 12px;">ÉVÉNEMENTS DU JOUR</div>
                    {events_html}
                </div>
            </div>
            
            <div class="content">
                <div class="recommendations-section">
                    <div class="recommendations-title">
                        💡 Recommandations Stratégiques du Jour
                    </div>
                    {reco_html}
                </div>
                
                <div class="summary-box">
                    <h2>📝 Synthèse du Marché</h2>
                    <p>{summary}</p>
                </div>
                
                <div class="section-header">
                    <div class="section-title">
                        🇺🇸 Marchés US & ETFs
                    </div>
                    <div class="section-count">{len(us_data)} actifs</div>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Actif</th>
                            <th>Prix</th>
                            <th>Variation</th>
                            <th>Recommandation</th>
                            <th>Analyse IA</th>
                        </tr>
                    </thead>
                    <tbody>{build_rows(us_data)}</tbody>
                </table>

                <div class="section-header">
                    <div class="section-title">
                        🇪🇺 Marchés Européens
                    </div>
                    <div class="section-count">{len(eu_data)} actifs</div>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Actif</th>
                            <th>Prix</th>
                            <th>Variation</th>
                            <th>Recommandation</th>
                            <th>Analyse IA</th>
                        </tr>
                    </thead>
                    <tbody>{build_rows(eu_data)}</tbody>
                </table>
            </div>
            
            <div class="footer">
                <strong>Données temps réel</strong> via Yahoo Finance • <strong>Analyses générées par IA</strong> (GPT-4o-mini)<br>
                ⚠️ Ce document est fourni à titre informatif uniquement et ne constitue pas un conseil en investissement.<br>
                Les performances passées ne préjugent pas des performances futures. Investir comporte des risques.
                <div class="footer-timestamp">
                    Rapport généré le {now} • Fuseau horaire: {TIMEZONE}
                </div>
            </div>
        </div>
    </body>
    </html>
    """

def send_email(html_content):
    """Envoie le rapport par e-mail à plusieurs destinataires."""
    if not EMAIL_PASSWORD or SENDER_EMAIL == "votre@email.com":
        print("❌ Configuration e-mail manquante. Définissez les variables d'environnement.")
        print("   SENDER_EMAIL, RECIPIENT_EMAILS, EMAIL_PASSWORD")
        return False
    
    # Parse des destinataires (séparés par des virgules)
    recipients = [email.strip() for email in RECIPIENT_EMAILS.split(',') if email.strip()]
    
    if not recipients:
        print("❌ Aucun destinataire configuré dans RECIPIENT_EMAILS")
        return False
    
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = ', '.join(recipients)  # Affichage de tous les destinataires
    msg['Subject'] = f"💎 Rapport Boursier IA - {format_datetime(get_local_time(), '%d/%m/%Y')}"
    msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"❌ Erreur d'envoi e-mail: {e}")
        return False

def main():
    """Fonction principale."""
    parser = argparse.ArgumentParser(
        description="Générateur de rapport boursier IA avancé",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples d'utilisation:
  python financial_report_final.py
  python financial_report_final.py --send
  python financial_report_final.py --output rapport_2026-02-15.html --send

Variables d'environnement requises:
  OPENAI_API_KEY       : Clé API OpenAI
  SENDER_EMAIL         : Email expéditeur (Gmail)
  RECIPIENT_EMAILS     : Emails destinataires (séparés par des virgules)
  EMAIL_PASSWORD       : Mot de passe d'application Gmail
        """
    )
    parser.add_argument('--send', action='store_true', 
                       help="Envoyer le rapport par e-mail")
    parser.add_argument('--output', type=str, 
                       default=f"rapport_boursier_{format_datetime(get_local_time(), '%Y%m%d_%H%M')}.html",
                       help="Nom du fichier de sortie (défaut: rapport_boursier_YYYYMMDD_HHMM.html)")
    args = parser.parse_args()

    generation_time = get_local_time()
    
    print("=" * 80)
    print("🚀 ANALYSE BOURSIÈRE IA - RAPPORT DÉTAILLÉ")
    print("=" * 80)
    print(f"📅 Date de génération: {format_datetime(generation_time, '%A %d %B %Y à %H:%M:%S')}")
    print(f"🌍 Fuseau horaire: {TIMEZONE}")
    print("=" * 80)
    
    # 1. Récupération du contexte de marché
    market_context = get_market_context()
    print(f"   ├─ Sentiment: {market_context['market_sentiment']}")
    print(f"   └─ Niveau de risque: {market_context['risk_level']}")
    
    # 2. Sélection dynamique des actifs
    assets = get_dynamic_assets_from_ai()
    total_assets = len(assets['us_actions']) + len(assets['eu_actions']) + len(assets['etfs'])
    print(f"\n📊 Sélection des actifs")
    print(f"   ├─ Actions US: {len(assets['us_actions'])}")
    print(f"   ├─ Actions EU: {len(assets['eu_actions'])}")
    print(f"   ├─ ETFs: {len(assets['etfs'])}")
    print(f"   └─ TOTAL: {total_assets} actifs")
    
    # 3. Récupération des données de marché
    print("\n📈 Récupération des cours en temps réel...")
    us_raw = get_market_data(assets['us_actions'] + assets['etfs'])
    eu_raw = get_market_data(assets['eu_actions'])
    print(f"   ├─ {len(us_raw)} actifs US/ETF récupérés")
    print(f"   └─ {len(eu_raw)} actifs EU récupérés")
    
    # 4. Analyses IA individuelles
    print("\n🧠 Génération des analyses IA...")
    for i, item in enumerate(us_raw, 1):
        item['ai'] = get_ai_analysis(item, market_context)
        print(f"   ├─ [{i}/{len(us_raw)}] {item['symbol']}: {item['ai']['recommendation']}")
    for i, item in enumerate(eu_raw, 1):
        item['ai'] = get_ai_analysis(item, market_context)
        print(f"   ├─ [{i}/{len(eu_raw)}] {item['symbol']}: {item['ai']['recommendation']}")
    print(f"   └─ {len(us_raw) + len(eu_raw)} analyses complétées")
    
    # 5. Génération des recommandations stratégiques
    recommendations = generate_recommendations(us_raw, eu_raw, market_context)
    print(f"\n💡 {len(recommendations['recommendations'])} recommandations stratégiques générées")
    
    # 6. Résumé global
    print("\n📝 Rédaction du résumé exécutif...")
    all_syms = [f"{x['symbol']} ({x['name']})" for x in us_raw + eu_raw]
    summary_prompt = f"""Contexte: {market_context['key_message']}

Actifs analysés: {', '.join(all_syms[:10])}... et {len(all_syms)-10} autres.

Rédige un résumé financier expert de 3-4 phrases maximum qui:
1. Résume la tendance générale observée
2. Identifie les secteurs les plus dynamiques
3. Mentionne les points d'attention pour les investisseurs

Ton professionnel et synthétique. Pas de jargon inutile."""
    
    summary = call_openai(summary_prompt, 
                         system="Tu es un rédacteur financier senior qui synthétise l'information de manière claire et impactante.")
    if not summary:
        summary = "Marchés en évolution avec des opportunités sectorielles. Surveillance recommandée sur les valeurs technologiques et les ETFs diversifiés."
    print("   └─ Synthèse rédigée")
    
    # 7. Génération du rapport HTML
    print("\n🎨 Génération du rapport HTML...")
    html = generate_html(summary, us_raw, eu_raw, market_context, recommendations, generation_time)
    
    output_file = args.output
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   └─ ✅ Rapport sauvegardé: {output_file}")
    
    # 8. Envoi par e-mail (optionnel)
    if args.send:
        print("\n📧 Envoi du rapport par e-mail...")
        recipients = [email.strip() for email in RECIPIENT_EMAILS.split(',') if email.strip()]
        print(f"   ├─ Destinataires: {len(recipients)}")
        for email in recipients:
            print(f"   │  • {email}")
        
        if send_email(html):
            print(f"   └─ ✅ Rapport envoyé avec succès à {len(recipients)} destinataire(s)")
        else:
            print("   └─ ⚠️ Échec de l'envoi du rapport")
    
    print("\n" + "=" * 80)
    print("✅ ANALYSE TERMINÉE AVEC SUCCÈS")
    print("=" * 80)
    print(f"📄 Fichier généré: {output_file}")
    print(f"⏰ Durée: {(get_local_time() - generation_time).total_seconds():.1f} secondes")
    print("=" * 80)

if __name__ == "__main__":
    main()
