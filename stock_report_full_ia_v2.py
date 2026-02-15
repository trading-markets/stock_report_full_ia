import json
import yfinance as yf
import openai
import requests
import smtplib
import argparse
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ==========================================
# CONFIGURATION (Utilisez des variables d'env)
# ==========================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "votre@email.com")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "destinataire@email.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "") # Mot de passe d'application
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

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
        print(f"Erreur OpenAI: {e}")
        return None

def get_dynamic_assets_from_ai():
    """L'IA sélectionne les actifs les plus pertinents avec noms complets."""
    print("🔍 L'IA sélectionne les actifs les plus pertinents...")
    
    system_prompt = """Tu es un analyste financier senior spécialisé dans la sélection d'actifs boursiers. 
Tu as une connaissance approfondie des marchés américains et européens, des secteurs porteurs et des catalyseurs de marché."""
    
    prompt = f"""Date du jour: {datetime.now().strftime('%d/%m/%Y')}

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
    """Récupère les données de marché avec noms complets."""
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
            
            # Formatage de l'heure de la dernière donnée
            last_update = hist.index[-1].strftime('%H:%M')
            
            # Informations supplémentaires
            info = stock.info
            currency = info.get('currency', 'USD')
            market_cap = info.get('marketCap', 0)
            
            data.append({
                "symbol": ticker,
                "name": name,
                "price": current_price,
                "change_pct": change_pct,
                "currency": currency,
                "market_cap": market_cap,
                "last_update": last_update
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
    
    prompt = f"""Date: {datetime.now().strftime('%A %d %B %Y')}

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

def generate_html(summary, us_data, eu_data, market_context, recommendations):
    """Génère un rapport HTML avec design moderne et épuré."""
    now = datetime.now().strftime('%d/%m/%Y à %H:%M')
    
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
            transform: scale(1.01);
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
            font-style: italic;
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
        .conf-high { background: #d1fae5; color: #065f46; }
        .conf-medium { background: #fef3c7; color: #92400e; }
        .conf-low { background: #fee2e2; color: #991b1b; }
        
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
        
        @media (max-width: 768px) {
            .market-grid { grid-template-columns: 1fr; }
            table { font-size: 11px; }
            th, td { padding: 10px 8px; }
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
            conf_class = f"conf-{conf.lower()}" if conf in ['Haute', 'Moyenne', 'Faible'] else "conf-medium"
            
            # Événement
            event = ""
            if item['ai']['event']:
                event = f"<span class='event-text'>⚠️ {item['ai']['event_desc']}</span>"
            
            # Indicateur de tendance court terme
            bias = item['ai'].get('short_term_bias', 'Neutre')
            bias_class = f"bias-{bias.lower()}"
            
            html += f"""
            <tr>
                <td>
                    <div class="asset-info">
                        <span class="ticker">{item['symbol']}</span>
                        <span class="asset-name">{item['name']}</span>
                        <span class="update-time">Màj: {item['last_update']}</span>
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
        <title>Rapport Boursier IA - {now}</title>
        {style}
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="header-content">
                    <h1>📊 Analyse Boursière Prédictive</h1>
                    <p>Rapport Stratégique Alimenté par Intelligence Artificielle • {now}</p>
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
            </div>
        </div>
    </body>
    </html>
    """

def send_email(html_content):
    """Envoie le rapport par e-mail."""
    if not EMAIL_PASSWORD or SENDER_EMAIL == "votre@email.com":
        print("❌ Configuration e-mail manquante. Définissez les variables d'environnement.")
        return False
    
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = f"💎 Rapport Boursier IA - {datetime.now().strftime('%d/%m/%Y')}"
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
    parser = argparse.ArgumentParser(description="Générateur de rapport boursier IA avancé")
    parser.add_argument('--send', action='store_true', help="Envoyer le rapport par e-mail")
    parser.add_argument('--output', type=str, default="rapport_boursier_ia.html", 
                       help="Nom du fichier de sortie (défaut: rapport_boursier_ia.html)")
    args = parser.parse_args()

    print("=" * 70)
    print("🚀 DÉMARRAGE DE L'ANALYSE BOURSIÈRE IA")
    print("=" * 70)
    
    # 1. Récupération du contexte de marché
    market_context = get_market_context()
    print(f"   └─ Sentiment: {market_context['market_sentiment']} | Risque: {market_context['risk_level']}")
    
    # 2. Sélection dynamique des actifs
    assets = get_dynamic_assets_from_ai()
    total_assets = len(assets['us_actions']) + len(assets['eu_actions']) + len(assets['etfs'])
    print(f"   └─ {total_assets} actifs sélectionnés")
    
    # 3. Récupération des données de marché
    print("\n📊 Récupération des cours en temps réel...")
    us_raw = get_market_data(assets['us_actions'] + assets['etfs'])
    eu_raw = get_market_data(assets['eu_actions'])
    print(f"   └─ {len(us_raw)} actifs US/ETF récupérés")
    print(f"   └─ {len(eu_raw)} actifs EU récupérés")
    
    # 4. Analyses IA individuelles
    print("\n🧠 Génération des analyses IA...")
    for item in us_raw:
        item['ai'] = get_ai_analysis(item, market_context)
    for item in eu_raw:
        item['ai'] = get_ai_analysis(item, market_context)
    print(f"   └─ {len(us_raw) + len(eu_raw)} analyses générées")
    
    # 5. Génération des recommandations stratégiques
    recommendations = generate_recommendations(us_raw, eu_raw, market_context)
    print(f"   └─ {len(recommendations['recommendations'])} recommandations créées")
    
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
    
    # 7. Génération du rapport HTML
    print("\n🎨 Génération du rapport HTML...")
    html = generate_html(summary, us_raw, eu_raw, market_context, recommendations)
    
    output_file = args.output
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Rapport généré : {output_file}")
    
    # 8. Envoi par e-mail (optionnel)
    if args.send:
        print("\n📧 Envoi du rapport par e-mail...")
        if send_email(html):
            print("✨ Rapport envoyé avec succès à", RECIPIENT_EMAIL)
        else:
            print("⚠️ Échec de l'envoi du rapport")
    
    print("\n" + "=" * 70)
    print("✅ ANALYSE TERMINÉE")
    print("=" * 70)

if __name__ == "__main__":
    main()

