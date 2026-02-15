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

def call_openai(prompt, system=None, model='gpt-4.1-mini'):
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
    """L'IA sélectionne les actifs les plus pertinents du moment."""
    print("🔍 L'IA sélectionne les actifs les plus pertinents...")
    prompt = (
        "En tant qu'expert en marchés financiers, sélectionne les actifs les plus intéressants à surveiller aujourd'hui.\n"
        "Fournis un objet JSON avec trois listes de tickers valides pour Yahoo Finance :\n"
        "- `us_actions`: 8 actions US majeures ou volatiles (ex: NVDA, TSLA)\n"
        "- `eu_actions`: 8 actions Européennes majeures (ex: ASML.AS, MC.PA, SAP.DE)\n"
        "- `etfs`: 4 ETFs globaux ou sectoriels (ex: QQQ, SMH, SPY)\n"
        "Retourne uniquement le JSON brut, sans balises markdown."
    )
    resp = call_openai(prompt)
    try:
        clean_resp = resp.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_resp)
    except Exception:
        return {
            "us_actions": ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL", "NFLX"],
            "eu_actions": ["SAP.DE", "ASML.AS", "MC.PA", "OR.PA", "SIE.DE", "AIR.PA", "TTE.PA", "BNP.PA"],
            "etfs": ["SPY", "QQQ", "SMH", "VTI"]
        }

def get_market_data(symbols):
    data = []
    for sym in symbols:
        try:
            stock = yf.Ticker(sym)
            hist = stock.history(period="5d")
            if hist.empty: continue
            
            # Récupération du dernier cours et de l'heure de mise à jour
            last_row = hist.iloc[-1]
            current_price = float(last_row['Close'])
            prev_close = float(hist['Close'].iloc[-2])
            change_pct = ((current_price - prev_close) / prev_close) * 100
            
            # Formatage de l'heure de la dernière donnée (index de yfinance est en datetime)
            last_update = hist.index[-1].strftime('%H:%M')
            
            data.append({
                "symbol": sym,
                "price": current_price,
                "change_pct": change_pct,
                "currency": stock.info.get('currency', 'USD'),
                "last_update": last_update
            })
        except Exception as e:
            print(f"Erreur pour {sym}: {e}")
            continue
    return data

def get_ai_analysis(ticker_data):
    prompt = (
        f"Analyse flash pour {ticker_data['symbol']}. Prix: {ticker_data['price']:.2f}, Variation: {ticker_data['change_pct']:.2f}%.\n"
        "Réponds en JSON: {\"recommendation\": \"Acheter|Vendre|Maintenir\", \"analysis\": \"1 phrase d'expert\", \"event\": true|false, \"event_desc\": \"...\"}"
    )
    resp = call_openai(prompt)
    try:
        clean_resp = resp.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_resp)
    except Exception:
        return {"recommendation": "Maintenir", "analysis": "Analyse indisponible", "event": False, "event_desc": ""}

def generate_html(summary, us_data, eu_data):
    now = datetime.now().strftime('%d/%m/%Y à %H:%M')
    
    style = """
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #2c3e50; margin: 0; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; background: #ffffff; border-radius: 12px; box-shadow: 0 4px 25px rgba(0,0,0,0.06); overflow: hidden; }
        .header { background: #1a2a6c; background: linear-gradient(to right, #b21f1f, #fdbb2d, #1a2a6c); color: #ffffff; padding: 45px 30px; text-align: center; }
        .header h1 { margin: 0; font-size: 26px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; }
        .header p { margin: 10px 0 0; opacity: 0.9; font-size: 14px; }
        .content { padding: 35px; }
        .summary-box { background: #fdfdfd; border: 1px solid #edf2f7; border-radius: 10px; padding: 25px; margin-bottom: 35px; border-left: 6px solid #1a2a6c; }
        .summary-box h2 { margin-top: 0; font-size: 17px; color: #1a2a6c; text-transform: uppercase; margin-bottom: 15px; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 35px; }
        th { text-align: left; padding: 14px; background: #f8fafc; color: #718096; font-size: 11px; text-transform: uppercase; border-bottom: 2px solid #edf2f7; }
        td { padding: 18px 14px; border-bottom: 1px solid #f7fafc; font-size: 13px; vertical-align: top; }
        .ticker { font-weight: 800; color: #2d3748; font-size: 14px; }
        .update-time { display: block; font-size: 10px; color: #a0aec0; font-weight: normal; margin-top: 2px; }
        .pos { color: #38a169; font-weight: bold; }
        .neg { color: #e53e3e; font-weight: bold; }
        .badge { padding: 6px 12px; border-radius: 6px; font-size: 10px; font-weight: 800; text-transform: uppercase; display: inline-block; }
        .badge-buy { background: #c6f6d5; color: #22543d; }
        .badge-sell { background: #fed7d7; color: #822727; }
        .badge-hold { background: #feebc8; color: #744210; }
        .event-text { color: #e53e3e; font-size: 11px; font-style: italic; margin-top: 6px; display: block; font-weight: 600; }
        .footer { text-align: center; padding: 25px; font-size: 11px; color: #a0aec0; background: #f8fafc; border-top: 1px solid #edf2f7; }
    </style>
    """

    def build_rows(data):
        html = ""
        for item in data:
            color = "pos" if item['change_pct'] >= 0 else "neg"
            reco = item['ai']['recommendation']
            b_class = "badge-buy" if "Acheter" in reco else ("badge-sell" if "Vendre" in reco else "badge-hold")
            event = f"<span class='event-text'>⚠️ {item['ai']['event_desc']}</span>" if item['ai']['event'] else ""
            html += f"""
            <tr>
                <td>
                    <span class="ticker">{item['symbol']}</span>
                    <span class="update-time">MàJ: {item['last_update']}</span>
                </td>
                <td style="font-family: 'Courier New', Courier, monospace; font-weight: bold;">{item['price']:.2f}</td>
                <td class="{color}">{item['change_pct']:+.2f}%</td>
                <td><span class="badge {b_class}">{reco}</span></td>
                <td style="line-height: 1.5;">{item['ai']['analysis']}{event}</td>
            </tr>
            """
        return html

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8">{style}</head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Analyse Boursière Prédictive</h1>
                <p>Rapport Stratégique IA • {now}</p>
            </div>
            <div class="content">
                <div class="summary-box">
                    <h2>Synthèse du Marché</h2>
                    <p style="line-height:1.7; margin:0; color: #4a5568;">{summary}</p>
                </div>
                
                <h3 style="color:#1a2a6c; font-size:16px; border-bottom:2px solid #edf2f7; padding-bottom:12px; margin-bottom: 20px;">Marchés US & ETFs</h3>
                <table>
                    <thead><tr><th>Actif / Heure</th><th>Prix</th><th>Var.</th><th>Reco.</th><th>Analyse IA</th></tr></thead>
                    <tbody>{build_rows(us_data)}</tbody>
                </table>

                <h3 style="color:#1a2a6c; font-size:16px; border-bottom:2px solid #edf2f7; padding-bottom:12px; margin-top:45px; margin-bottom: 20px;">Marchés Européens</h3>
                <table>
                    <thead><tr><th>Actif / Heure</th><th>Prix</th><th>Var.</th><th>Reco.</th><th>Analyse IA</th></tr></thead>
                    <tbody>{build_rows(eu_data)}</tbody>
                </table>
            </div>
            <div class="footer">
                Données temps réel via Yahoo Finance • Analyses générées par IA • Ce document est à but informatif uniquement.
            </div>
        </div>
    </body>
    </html>
    """

def send_email(html_content):
    if not EMAIL_PASSWORD or SENDER_EMAIL == "votre@email.com":
        print("❌ Configuration e-mail manquante.")
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
        print(f"❌ Erreur d'envoi: {e}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--send', action='store_true', help="Envoyer le rapport par e-mail")
    args = parser.parse_args()

    print("🚀 Démarrage de l'analyse boursière (Version avec Horodatage)...")
    
    # 1. Sélection dynamique
    assets = get_dynamic_assets_from_ai()
    
    # 2. Récupération des prix avec horodatage
    print("📊 Récupération des cours et des heures de mise à jour...")
    us_raw = get_market_data(assets['us_actions'] + assets['etfs'])
    eu_raw = get_market_data(assets['eu_actions'])
    
    # 3. Analyse IA par actif
    print("🧠 Génération des analyses stratégiques...")
    for i in us_raw: i['ai'] = get_ai_analysis(i)
    for i in eu_raw: i['ai'] = get_ai_analysis(i)
    
    # 4. Résumé global
    print("📝 Rédaction du résumé exécutif...")
    all_syms = [x['symbol'] for x in us_raw + eu_raw]
    summary = call_openai(f"Fais un résumé financier expert de 4 phrases sur la situation actuelle de ces actifs: {', '.join(all_syms)}. Ton pro et synthétique.")
    
    # 5. Génération HTML
    html = generate_html(summary, us_raw, eu_raw)
    
    with open("rapport_ia_horodatage.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ Rapport généré : rapport_ia_horodatage.html")

    if args.send:
        print("📧 Envoi de l'e-mail...")
        if send_email(html):
            print("✨ Rapport envoyé avec succès !")
        else:
            print("⚠️ Échec de l'envoi.")

if __name__ == "__main__":
    main()
