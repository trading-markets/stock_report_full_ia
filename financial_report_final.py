import json
import yfinance as yf
import anthropic
import smtplib
import argparse
import os
import sys
from datetime import datetime, timezone

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ==========================================
# CONFIGURATION
# ==========================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "votre@email.com")
RECIPIENT_EMAILS = os.getenv("RECIPIENT_EMAILS", "destinataire1@email.com,destinataire2@email.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

TIMEZONE = "Europe/Paris"

# Indices benchmarks toujours suivis (marché pulse)
BENCHMARK_TICKERS = [
    {"ticker": "^GSPC", "name": "S&P 500"},
    {"ticker": "^IXIC", "name": "NASDAQ"},
    {"ticker": "^FCHI", "name": "CAC 40"},
    {"ticker": "^GDAXI", "name": "DAX"},
    {"ticker": "^VIX", "name": "VIX"},
]


def get_local_time():
    return datetime.now(ZoneInfo(TIMEZONE))


def format_datetime(dt, format_str='%d/%m/%Y à %H:%M:%S'):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(TIMEZONE)).strftime(format_str)


def call_claude(prompt, system=None, model=None):
    """Appel Claude API avec cache sur les system prompts pour réduire les coûts."""
    if not ANTHROPIC_API_KEY:
        return None
    target_model = model or CLAUDE_MODEL
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    kwargs = {
        "model": target_model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }

    if system:
        kwargs["system"] = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]

    try:
        resp = client.messages.create(**kwargs)
        return resp.content[0].text
    except Exception as e:
        print(f"❌ Erreur Claude: {e}")
        return None


def get_dynamic_assets_from_ai():
    """L'IA sélectionne les actifs les plus pertinents."""
    print("🔍 Claude sélectionne les actifs les plus pertinents...")

    system_prompt = (
        "Tu es un analyste financier senior spécialisé dans la sélection d'actifs boursiers. "
        "Tu as une connaissance approfondie des marchés américains et européens, des secteurs porteurs et des catalyseurs de marché."
    )

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
    ... (8 actions EU au total avec suffixes: .PA=Paris, .AS=Amsterdam, .DE=Francfort, .MI=Milan, .MC=Madrid)
  ],
  "etfs": [
    {{"ticker": "SPY", "name": "S&P 500 ETF Trust"}},
    {{"ticker": "QQQ", "name": "Nasdaq-100 ETF"}},
    ... (4 ETFs diversifiés)
  ]
}}

Retourne UNIQUEMENT le JSON, rien d'autre."""

    resp = call_claude(prompt, system=system_prompt)
    try:
        clean_resp = resp.strip().replace("```json", "").replace("```", "")
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
                {"ticker": "AMD", "name": "Advanced Micro Devices"},
            ],
            "eu_actions": [
                {"ticker": "SAP.DE", "name": "SAP SE"},
                {"ticker": "ASML.AS", "name": "ASML Holding NV"},
                {"ticker": "MC.PA", "name": "LVMH Moët Hennessy"},
                {"ticker": "OR.PA", "name": "L'Oréal SA"},
                {"ticker": "SIE.DE", "name": "Siemens AG"},
                {"ticker": "AIR.PA", "name": "Airbus SE"},
                {"ticker": "TTE.PA", "name": "TotalEnergies SE"},
                {"ticker": "SAN.MC", "name": "Banco Santander SA"},
            ],
            "etfs": [
                {"ticker": "SPY", "name": "S&P 500 ETF Trust"},
                {"ticker": "QQQ", "name": "Nasdaq-100 ETF"},
                {"ticker": "SMH", "name": "VanEck Semiconductor ETF"},
                {"ticker": "VWO", "name": "Vanguard Emerging Markets ETF"},
            ],
        }


def _fetch_ticker_data(asset):
    """Récupère les données enrichies pour un actif (prix, volume, momentum, 52s)."""
    ticker = asset["ticker"]
    name = asset["name"]
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d")
        if hist.empty:
            print(f"⚠️ Pas de données pour {ticker}")
            return None

        last_row = hist.iloc[-1]
        current_price = float(last_row["Close"])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price
        change_pct = ((current_price - prev_close) / prev_close) * 100 if prev_close != 0 else 0

        # Timestamps
        last_timestamp = hist.index[-1]
        last_update_full = format_datetime(last_timestamp, "%d/%m/%Y %H:%M:%S")
        last_update_short = format_datetime(last_timestamp, "%H:%M")
        time_diff = get_local_time() - last_timestamp.replace(tzinfo=timezone.utc).astimezone(
            ZoneInfo(TIMEZONE)
        )
        minutes_ago = int(time_diff.total_seconds() / 60)
        if minutes_ago < 60:
            time_ago = f"il y a {minutes_ago} min"
        elif minutes_ago < 1440:
            time_ago = f"il y a {minutes_ago // 60}h"
        else:
            time_ago = f"il y a {minutes_ago // 1440}j"

        # Volume
        current_vol = float(last_row.get("Volume", 0) or 0)
        avg_vol = float(hist["Volume"].mean()) if "Volume" in hist.columns and hist["Volume"].sum() > 0 else 0
        vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
        if vol_ratio >= 1.5:
            vol_signal = "Fort"
        elif vol_ratio <= 0.5:
            vol_signal = "Faible"
        else:
            vol_signal = "Normal"

        # Momentum 5 jours
        first_price = float(hist["Close"].iloc[0])
        momentum_5d = ((current_price - first_price) / first_price) * 100

        # Séance (high/low du jour)
        day_high = float(last_row.get("High", current_price) or current_price)
        day_low = float(last_row.get("Low", current_price) or current_price)

        # Position dans la plage 52 semaines
        try:
            fi = stock.fast_info
            high_52w = getattr(fi, "fifty_two_week_high", None) or 0
            low_52w = getattr(fi, "fifty_two_week_low", None) or 0
            currency = getattr(fi, "currency", "USD") or "USD"
            market_cap = getattr(fi, "market_cap", 0) or 0
        except Exception:
            info = stock.info
            high_52w = info.get("fiftyTwoWeekHigh", 0) or 0
            low_52w = info.get("fiftyTwoWeekLow", 0) or 0
            currency = info.get("currency", "USD") or "USD"
            market_cap = info.get("marketCap", 0) or 0

        if high_52w and low_52w and high_52w != low_52w:
            pos_52w = ((current_price - low_52w) / (high_52w - low_52w)) * 100
        else:
            pos_52w = 50.0

        # Statut de marché
        current_hour = get_local_time().hour
        if any(s in ticker for s in [".PA", ".AS", ".DE", ".MI", ".MC", ".CO"]):
            market_status = "Ouvert" if 9 <= current_hour < 18 else "Fermé"
        elif ticker.startswith("^"):
            market_status = "Ouvert" if 15 <= current_hour < 22 else "Fermé"
        else:
            market_status = "Ouvert" if 15 <= current_hour < 22 else "Fermé"

        return {
            "symbol": ticker,
            "name": name,
            "price": current_price,
            "change_pct": change_pct,
            "currency": currency,
            "market_cap": market_cap,
            "last_update_full": last_update_full,
            "last_update_short": last_update_short,
            "time_ago": time_ago,
            "market_status": market_status,
            "day_high": day_high,
            "day_low": day_low,
            "momentum_5d": momentum_5d,
            "vol_signal": vol_signal,
            "vol_ratio": vol_ratio,
            "pos_52w": pos_52w,
            "high_52w": high_52w,
            "low_52w": low_52w,
        }
    except Exception as e:
        print(f"❌ Erreur pour {ticker} ({name}): {e}")
        return None


def get_market_data(assets_list):
    """Récupère les données enrichies pour une liste d'actifs."""
    data = []
    for asset in assets_list:
        result = _fetch_ticker_data(asset)
        if result:
            data.append(result)
    return data


def get_benchmark_data():
    """Récupère les données des indices de référence."""
    data = []
    for asset in BENCHMARK_TICKERS:
        result = _fetch_ticker_data(asset)
        if result:
            data.append(result)
    return data


def get_market_context():
    """Récupère le contexte de marché via Claude."""
    print("🌍 Analyse du contexte de marché par Claude...")

    system_prompt = (
        "Tu es un analyste macro-économique qui suit l'actualité financière en temps réel. "
        "Tu identifies les catalyseurs de marché, les événements géopolitiques et les publications économiques importantes."
    )

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

    resp = call_claude(prompt, system=system_prompt)
    try:
        clean_resp = resp.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_resp)
    except Exception:
        return {
            "market_sentiment": "Mixte",
            "main_events": ["Données macro-économiques attendues", "Tension géopolitique persistante"],
            "sector_focus": ["Technologie", "Finance", "Énergie"],
            "risk_level": "Modéré",
            "key_message": "Les marchés évoluent dans un contexte d'incertitude modérée avec attention sur les valeurs technologiques.",
        }


def get_ai_analysis(ticker_data, market_context):
    """Analyse enrichie par Claude avec données de momentum et volume."""
    system_prompt = (
        "Tu es un analyste financier quantitatif senior. Tes analyses sont: "
        "concises, factuelles, basées sur les tendances de prix et le contexte macro, "
        "orientées action avec des recommandations claires, et conscientes des risques."
    )

    pos_52w_label = f"{ticker_data['pos_52w']:.0f}% de la plage 52s"
    vol_label = f"{ticker_data['vol_signal']} ({ticker_data['vol_ratio']:.1f}x moy.)"

    prompt = f"""Contexte: {market_context['market_sentiment']} | Secteurs: {', '.join(market_context['sector_focus'])}

Actif: {ticker_data['symbol']} - {ticker_data['name']}
Prix: {ticker_data['price']:.2f} {ticker_data['currency']}  |  Var. jour: {ticker_data['change_pct']:+.2f}%
Séance: {ticker_data['day_low']:.2f} – {ticker_data['day_high']:.2f}
Momentum 5j: {ticker_data['momentum_5d']:+.1f}%  |  Volume: {vol_label}
Position 52 sem.: {pos_52w_label}
Statut: {ticker_data['market_status']} (màj: {ticker_data['time_ago']})

Fournis une analyse JSON:
{{
  "recommendation": "🟢 Acheter|🔴 Vendre|🟡 Maintenir|⚪ Observer",
  "analysis": "Analyse en 1 phrase courte et percutante (max 15 mots)",
  "confidence": "Haute|Moyenne|Faible",
  "event": true|false,
  "event_desc": "Si événement spécifique détecté (résultats, news, catalyseur)",
  "short_term_bias": "Haussier|Baissier|Neutre"
}}

Retourne UNIQUEMENT le JSON."""

    resp = call_claude(prompt, system=system_prompt)
    try:
        clean_resp = resp.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_resp)
    except Exception:
        return {
            "recommendation": "🟡 Maintenir",
            "analysis": "Analyse indisponible",
            "confidence": "Faible",
            "event": False,
            "event_desc": "",
            "short_term_bias": "Neutre",
        }


def generate_recommendations(us_data, eu_data, market_context):
    """Génère des recommandations stratégiques personnalisées via Claude."""
    print("💡 Génération des recommandations stratégiques...")

    system_prompt = "Tu es un conseiller en investissement qui synthétise les analyses pour proposer des stratégies actionnables."

    all_data = us_data + eu_data
    top_gainers = sorted([d for d in all_data if d["change_pct"] > 0], key=lambda x: x["change_pct"], reverse=True)[:3]
    top_losers = sorted([d for d in all_data if d["change_pct"] < 0], key=lambda x: x["change_pct"])[:3]
    high_vol = [d for d in all_data if d.get("vol_signal") == "Fort"]

    prompt = f"""Contexte: {market_context['key_message']}
Sentiment: {market_context['market_sentiment']}
Événements: {', '.join(market_context['main_events'])}

Top hausses: {', '.join([f"{d['symbol']} ({d['change_pct']:+.1f}%)" for d in top_gainers])}
Top baisses: {', '.join([f"{d['symbol']} ({d['change_pct']:+.1f}%)" for d in top_losers])}
Volumes forts: {', '.join([d['symbol'] for d in high_vol]) if high_vol else "Aucun signal de volume exceptionnel"}

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

Retourne UNIQUEMENT le JSON."""

    resp = call_claude(prompt, system=system_prompt)
    try:
        clean_resp = resp.strip().replace("```json", "").replace("```", "")
        return json.loads(clean_resp)
    except Exception:
        return {
            "recommendations": [
                {"icon": "🎯", "title": "Diversification sectorielle", "description": "Répartir les positions entre tech, finance et matières premières."},
                {"icon": "📊", "title": "Surveillance des volumes", "description": "Observer les volumes de trading pour confirmer les tendances."},
                {"icon": "🛡️", "title": "Gestion du risque", "description": "Maintenir des stop-loss sur les positions volatiles."},
            ]
        }


def validate_report(us_data, eu_data, benchmarks, generation_time):
    """Valide la qualité du rapport généré."""
    print("\n" + "=" * 60)
    print("🔍 VALIDATION DU RAPPORT")
    print("=" * 60)

    errors = []
    warnings = []
    checks_passed = 0
    checks_total = 0

    # 1. Vérification des données de marché
    checks_total += 1
    total_expected = 20
    total_got = len(us_data) + len(eu_data)
    coverage = total_got / total_expected * 100
    if coverage >= 80:
        print(f"   ✅ Couverture actifs: {total_got}/{total_expected} ({coverage:.0f}%)")
        checks_passed += 1
    elif coverage >= 50:
        warnings.append(f"Couverture actifs faible: {total_got}/{total_expected}")
        print(f"   ⚠️  Couverture actifs: {total_got}/{total_expected} ({coverage:.0f}%)")
    else:
        errors.append(f"Couverture actifs insuffisante: {total_got}/{total_expected}")
        print(f"   ❌ Couverture actifs: {total_got}/{total_expected} ({coverage:.0f}%)")

    # 2. Vérification des analyses IA
    checks_total += 1
    ai_ok = sum(1 for d in us_data + eu_data if d.get("ai") and d["ai"].get("recommendation") != "🟡 Maintenir" or (d.get("ai") and d["ai"].get("analysis") != "Analyse indisponible"))
    ai_total = total_got
    ai_pct = (ai_ok / ai_total * 100) if ai_total > 0 else 0
    if ai_pct >= 80:
        print(f"   ✅ Analyses IA: {ai_ok}/{ai_total} valides ({ai_pct:.0f}%)")
        checks_passed += 1
    else:
        warnings.append(f"Qualité analyses IA: {ai_ok}/{ai_total}")
        print(f"   ⚠️  Analyses IA: {ai_ok}/{ai_total} valides ({ai_pct:.0f}%)")

    # 3. Vérification des prix (plausibilité)
    checks_total += 1
    price_ok = sum(1 for d in us_data + eu_data if d.get("price", 0) > 0)
    if price_ok == total_got:
        print(f"   ✅ Prix valides: {price_ok}/{total_got}")
        checks_passed += 1
    else:
        errors.append(f"Prix invalides détectés: {total_got - price_ok} actifs à 0")
        print(f"   ❌ Prix valides: {price_ok}/{total_got}")

    # 4. Vérification des benchmarks
    checks_total += 1
    if len(benchmarks) >= 3:
        print(f"   ✅ Benchmarks: {len(benchmarks)}/{len(BENCHMARK_TICKERS)} récupérés")
        checks_passed += 1
    else:
        warnings.append(f"Benchmarks incomplets: {len(benchmarks)}/{len(BENCHMARK_TICKERS)}")
        print(f"   ⚠️  Benchmarks: {len(benchmarks)}/{len(BENCHMARK_TICKERS)} récupérés")

    # 5. Vérification de la clé API Claude
    checks_total += 1
    if ANTHROPIC_API_KEY:
        print(f"   ✅ Clé API Claude: configurée")
        checks_passed += 1
    else:
        errors.append("Clé API Claude manquante (ANTHROPIC_API_KEY)")
        print(f"   ❌ Clé API Claude: NON configurée")

    # Résumé
    print(f"\n   Score: {checks_passed}/{checks_total} contrôles réussis")
    if warnings:
        print(f"\n   Avertissements:")
        for w in warnings:
            print(f"     ⚠️  {w}")
    if errors:
        print(f"\n   Erreurs:")
        for e in errors:
            print(f"     ❌  {e}")

    duration = (get_local_time() - generation_time).total_seconds()
    print(f"\n   Durée de génération: {duration:.1f}s")
    print("=" * 60)

    return len(errors) == 0


def generate_html(summary, us_data, eu_data, benchmarks, market_context, recommendations, generation_time):
    """Génère un rapport HTML avec design moderne, benchmarks et données enrichies."""
    now = format_datetime(generation_time, "%d/%m/%Y à %H:%M:%S")
    now_short = format_datetime(generation_time, "%d/%m/%Y à %H:%M")

    all_data = us_data + eu_data
    nb_hausse = len([d for d in all_data if d["change_pct"] > 0])
    nb_baisse = len([d for d in all_data if d["change_pct"] < 0])
    avg_variation = sum(d["change_pct"] for d in all_data) / len(all_data) if all_data else 0

    sentiment_colors = {
        "Haussier": "#10b981",
        "Baissier": "#ef4444",
        "Neutre": "#f59e0b",
        "Mixte": "#8b5cf6",
    }
    sentiment_color = sentiment_colors.get(market_context["market_sentiment"], "#6b7280")

    style = f"""
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #1f2937;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
            color: #ffffff;
            padding: 50px 40px;
            position: relative;
            overflow: hidden;
        }}
        .header::before {{
            content: '';
            position: absolute; top: -50%; right: -50%;
            width: 200%; height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
        }}
        .header-content {{ position: relative; z-index: 1; }}
        .header h1 {{ font-size: 32px; font-weight: 800; margin-bottom: 10px; text-shadow: 2px 2px 4px rgba(0,0,0,0.2); }}
        .header p {{ opacity: 0.95; font-size: 15px; font-weight: 300; }}
        .header-timestamp {{
            display: inline-block; background: rgba(255,255,255,0.15);
            padding: 8px 16px; border-radius: 8px; font-size: 13px;
            margin-top: 10px; font-weight: 500;
        }}
        .market-banner {{
            background: linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%);
            padding: 30px 40px;
            border-bottom: 3px solid {sentiment_color};
        }}
        .market-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px; margin-bottom: 20px;
        }}
        .market-stat {{
            background: white; padding: 15px 20px; border-radius: 12px;
            border-left: 4px solid {sentiment_color};
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        .market-stat-label {{ font-size: 11px; text-transform: uppercase; color: #6b7280; font-weight: 600; letter-spacing: 0.5px; margin-bottom: 5px; }}
        .market-stat-value {{ font-size: 24px; font-weight: 700; color: {sentiment_color}; }}
        .events-box {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
        .event-item {{ padding: 8px 0; border-left: 3px solid #3b82f6; padding-left: 12px; margin-bottom: 8px; font-size: 13px; color: #374151; }}

        /* Market Pulse */
        .pulse-section {{
            background: #0f172a; padding: 20px 40px; overflow-x: auto;
        }}
        .pulse-title {{ color: #94a3b8; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }}
        .pulse-grid {{ display: flex; gap: 20px; }}
        .pulse-card {{
            background: #1e293b; border-radius: 10px; padding: 12px 18px;
            min-width: 140px; border: 1px solid #334155;
        }}
        .pulse-name {{ color: #94a3b8; font-size: 11px; margin-bottom: 4px; }}
        .pulse-price {{ color: #f1f5f9; font-weight: 700; font-size: 16px; font-family: monospace; }}
        .pulse-change {{ font-size: 13px; font-weight: 700; margin-top: 2px; }}

        .content {{ padding: 40px; }}
        .recommendations-section {{
            background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
            border-radius: 16px; padding: 30px; margin-bottom: 40px;
            border: 2px solid #fbbf24;
        }}
        .recommendations-title {{ font-size: 20px; font-weight: 700; color: #92400e; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; }}
        .recommendation-card {{ background: white; padding: 20px; border-radius: 12px; margin-bottom: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-left: 5px solid #f59e0b; }}
        .recommendation-card:last-child {{ margin-bottom: 0; }}
        .rec-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }}
        .rec-icon {{ font-size: 24px; }}
        .rec-title {{ font-size: 15px; font-weight: 700; color: #1f2937; }}
        .rec-description {{ font-size: 13px; color: #4b5563; line-height: 1.6; padding-left: 36px; }}

        .summary-box {{ background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%); border-radius: 16px; padding: 25px; margin-bottom: 40px; border: 2px solid #3b82f6; }}
        .summary-box h2 {{ font-size: 18px; color: #1e3a8a; margin-bottom: 15px; font-weight: 700; }}
        .summary-box p {{ color: #1e40af; line-height: 1.8; font-size: 14px; }}

        .section-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 3px solid #e5e7eb; }}
        .section-title {{ font-size: 22px; font-weight: 700; color: #1f2937; display: flex; align-items: center; gap: 10px; }}
        .section-count {{ background: #3b82f6; color: white; padding: 5px 15px; border-radius: 20px; font-size: 12px; font-weight: 600; }}

        table {{ width: 100%; border-collapse: separate; border-spacing: 0; margin-bottom: 45px; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
        thead {{ background: linear-gradient(135deg, #1f2937 0%, #374151 100%); }}
        th {{ text-align: left; padding: 16px 14px; color: #f9fafb; font-size: 11px; text-transform: uppercase; font-weight: 700; letter-spacing: 0.8px; }}
        tbody tr {{ background: white; transition: all 0.2s ease; }}
        tbody tr:hover {{ background: #f9fafb; }}
        tbody tr:nth-child(even) {{ background: #fafbfc; }}
        td {{ padding: 18px 14px; border-bottom: 1px solid #e5e7eb; font-size: 13px; vertical-align: middle; }}

        .asset-info {{ display: flex; flex-direction: column; gap: 4px; }}
        .ticker {{ font-weight: 800; color: #1f2937; font-size: 15px; font-family: 'Courier New', monospace; }}
        .asset-name {{ font-size: 11px; color: #6b7280; font-weight: 500; }}
        .update-time {{ font-size: 10px; color: #9ca3af; display: flex; align-items: center; gap: 4px; }}
        .market-status-badge {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 9px; font-weight: 700; text-transform: uppercase; margin-left: 4px; }}
        .status-open {{ background: #d1fae5; color: #065f46; }}
        .status-closed {{ background: #fee2e2; color: #991b1b; }}
        .time-ago {{ color: #6b7280; font-weight: 600; }}

        .price-cell {{ font-family: 'Courier New', monospace; font-weight: 700; font-size: 15px; color: #1f2937; }}
        .price-range {{ font-size: 10px; color: #9ca3af; margin-top: 3px; }}

        .pos {{ color: #10b981; font-weight: 700; }}
        .neg {{ color: #ef4444; font-weight: 700; }}
        .neutral {{ color: #6b7280; font-weight: 700; }}

        .momentum-row {{ display: flex; flex-direction: column; gap: 3px; }}
        .momentum-5d {{ font-size: 11px; color: #6b7280; }}

        .vol-badge {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 9px; font-weight: 700; margin-top: 3px; }}
        .vol-fort {{ background: #fef3c7; color: #92400e; }}
        .vol-normal {{ background: #f3f4f6; color: #6b7280; }}
        .vol-faible {{ background: #ede9fe; color: #5b21b6; }}

        .pos52w-bar {{ width: 80px; height: 6px; background: #e5e7eb; border-radius: 3px; margin-top: 4px; position: relative; overflow: hidden; }}
        .pos52w-fill {{ height: 100%; background: linear-gradient(90deg, #ef4444, #f59e0b, #10b981); border-radius: 3px; }}

        .badge {{ padding: 6px 14px; border-radius: 8px; font-size: 11px; font-weight: 700; text-transform: uppercase; display: inline-block; letter-spacing: 0.5px; }}
        .badge-buy {{ background: #d1fae5; color: #065f46; border: 1px solid #10b981; }}
        .badge-sell {{ background: #fee2e2; color: #991b1b; border: 1px solid #ef4444; }}
        .badge-hold {{ background: #fef3c7; color: #92400e; border: 1px solid #f59e0b; }}
        .badge-watch {{ background: #e5e7eb; color: #374151; border: 1px solid #6b7280; }}

        .analysis-cell {{ line-height: 1.6; max-width: 350px; }}
        .confidence-badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 9px; font-weight: 600; margin-left: 6px; text-transform: uppercase; }}
        .conf-haute {{ background: #d1fae5; color: #065f46; }}
        .conf-moyenne {{ background: #fef3c7; color: #92400e; }}
        .conf-faible {{ background: #fee2e2; color: #991b1b; }}

        .event-text {{ color: #dc2626; font-size: 11px; font-weight: 600; margin-top: 8px; display: block; padding: 6px 10px; background: #fef2f2; border-left: 3px solid #ef4444; border-radius: 4px; }}

        .bias-indicator {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }}
        .bias-haussier {{ background: #10b981; }}
        .bias-baissier {{ background: #ef4444; }}
        .bias-neutre {{ background: #6b7280; }}

        .footer {{ text-align: center; padding: 30px; font-size: 11px; color: #9ca3af; background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%); border-top: 2px solid #e5e7eb; }}
        .footer strong {{ color: #374151; font-weight: 600; }}
        .footer-timestamp {{ margin-top: 10px; font-size: 10px; color: #6b7280; font-style: italic; }}

        @media (max-width: 768px) {{
            .market-grid {{ grid-template-columns: 1fr; }}
            .pulse-grid {{ flex-wrap: wrap; }}
            table {{ font-size: 11px; }}
            th, td {{ padding: 10px 8px; }}
            .header h1 {{ font-size: 24px; }}
            .content {{ padding: 20px; }}
        }}
    </style>
    """

    def build_pulse_cards(bench_data):
        cards = ""
        for b in bench_data:
            change_color = "#10b981" if b["change_pct"] >= 0 else "#ef4444"
            sign = "+" if b["change_pct"] >= 0 else ""
            cards += f"""
            <div class="pulse-card">
                <div class="pulse-name">{b['name']}</div>
                <div class="pulse-price">{b['price']:.2f}</div>
                <div class="pulse-change" style="color:{change_color}">{sign}{b['change_pct']:.2f}%</div>
            </div>"""
        return cards

    def build_rows(data):
        html = ""
        for item in data:
            color = "pos" if item["change_pct"] > 0 else ("neg" if item["change_pct"] < 0 else "neutral")

            reco = item["ai"]["recommendation"]
            if "Acheter" in reco:
                b_class = "badge-buy"
            elif "Vendre" in reco:
                b_class = "badge-sell"
            elif "Maintenir" in reco:
                b_class = "badge-hold"
            else:
                b_class = "badge-watch"

            conf = item["ai"].get("confidence", "Moyenne")
            conf_class = f"conf-{conf.lower()}" if conf in ["Haute", "Moyenne", "Faible"] else "conf-moyenne"

            event_html = ""
            if item["ai"].get("event"):
                event_html = f"<span class='event-text'>⚠️ {item['ai']['event_desc']}</span>"

            bias = item["ai"].get("short_term_bias", "Neutre")
            bias_class = f"bias-{bias.lower()}"

            status_class = "status-open" if item["market_status"] == "Ouvert" else "status-closed"

            vol_sig = item.get("vol_signal", "Normal")
            vol_class = f"vol-{vol_sig.lower()}"

            mom5 = item.get("momentum_5d", 0)
            mom_color = "#10b981" if mom5 >= 0 else "#ef4444"
            mom_sign = "+" if mom5 >= 0 else ""

            pos52 = min(100, max(0, item.get("pos_52w", 50)))

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
                <td>
                    <div class="price-cell">{item['price']:.2f} {item['currency']}</div>
                    <div class="price-range">{item['day_low']:.2f} – {item['day_high']:.2f}</div>
                    <div class="pos52w-bar"><div class="pos52w-fill" style="width:{pos52:.0f}%"></div></div>
                </td>
                <td>
                    <div class="momentum-row">
                        <div><span class="bias-indicator {bias_class}"></span><span class="{color}">{item['change_pct']:+.2f}%</span></div>
                        <div class="momentum-5d" style="color:{mom_color}">5j: {mom_sign}{mom5:.1f}%</div>
                        <span class="vol-badge {vol_class}">Vol. {vol_sig}</span>
                    </div>
                </td>
                <td><span class="badge {b_class}">{reco}</span></td>
                <td class="analysis-cell">
                    {item['ai']['analysis']}
                    <span class="confidence-badge {conf_class}">{conf}</span>
                    {event_html}
                </td>
            </tr>
            """
        return html

    reco_html = "".join(
        f"""<div class="recommendation-card">
            <div class="rec-header"><span class="rec-icon">{r['icon']}</span><span class="rec-title">{r['title']}</span></div>
            <div class="rec-description">{r['description']}</div>
        </div>"""
        for r in recommendations["recommendations"]
    )

    events_html = "".join(f'<div class="event-item">📌 {e}</div>' for e in market_context["main_events"])

    pulse_html = build_pulse_cards(benchmarks)

    return f"""<!DOCTYPE html>
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
                <p>Rapport Stratégique Alimenté par Claude (Anthropic)</p>
                <div class="header-timestamp">🗓️ Généré le {now}</div>
            </div>
        </div>

        <div class="pulse-section">
            <div class="pulse-title">📡 Market Pulse — Indices de Référence</div>
            <div class="pulse-grid">{pulse_html}</div>
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
                <div class="recommendations-title">💡 Recommandations Stratégiques du Jour</div>
                {reco_html}
            </div>

            <div class="summary-box">
                <h2>📝 Synthèse du Marché</h2>
                <p>{summary}</p>
            </div>

            <div class="section-header">
                <div class="section-title">🇺🇸 Marchés US & ETFs</div>
                <div class="section-count">{len(us_data)} actifs</div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Actif</th>
                        <th>Prix / Plage 52s</th>
                        <th>Var. / Momentum</th>
                        <th>Recommandation</th>
                        <th>Analyse Claude</th>
                    </tr>
                </thead>
                <tbody>{build_rows(us_data)}</tbody>
            </table>

            <div class="section-header">
                <div class="section-title">🇪🇺 Marchés Européens</div>
                <div class="section-count">{len(eu_data)} actifs</div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Actif</th>
                        <th>Prix / Plage 52s</th>
                        <th>Var. / Momentum</th>
                        <th>Recommandation</th>
                        <th>Analyse Claude</th>
                    </tr>
                </thead>
                <tbody>{build_rows(eu_data)}</tbody>
            </table>
        </div>

        <div class="footer">
            <strong>Données temps réel</strong> via Yahoo Finance &bull;
            <strong>Analyses générées par Claude</strong> ({CLAUDE_MODEL} — Anthropic)<br>
            ⚠️ Ce document est fourni à titre informatif uniquement et ne constitue pas un conseil en investissement.<br>
            Les performances passées ne préjugent pas des performances futures. Investir comporte des risques.
            <div class="footer-timestamp">
                Rapport généré le {now} &bull; Fuseau horaire: {TIMEZONE}
            </div>
        </div>
    </div>
</body>
</html>"""


def send_email(html_content):
    """Envoie le rapport par e-mail à plusieurs destinataires."""
    if not EMAIL_PASSWORD or SENDER_EMAIL == "votre@email.com":
        print("❌ Configuration e-mail manquante. Définissez SENDER_EMAIL, RECIPIENT_EMAILS, EMAIL_PASSWORD.")
        return False

    recipients = [e.strip() for e in RECIPIENT_EMAILS.split(",") if e.strip()]
    if not recipients:
        print("❌ Aucun destinataire configuré dans RECIPIENT_EMAILS")
        return False

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"💎 Rapport Boursier IA - {format_datetime(get_local_time(), '%d/%m/%Y')}"
    msg.attach(MIMEText(html_content, "html"))

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
    parser = argparse.ArgumentParser(
        description="Générateur de rapport boursier IA (Claude)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python financial_report_final.py
  python financial_report_final.py --send
  python financial_report_final.py --validate
  python financial_report_final.py --output rapport.html --send

Variables d'environnement:
  ANTHROPIC_API_KEY  : Clé API Claude (Anthropic)
  CLAUDE_MODEL       : Modèle Claude (défaut: claude-haiku-4-5-20251001)
  SENDER_EMAIL       : Email expéditeur (Gmail)
  RECIPIENT_EMAILS   : Emails destinataires (séparés par virgules)
  EMAIL_PASSWORD     : Mot de passe d'application Gmail
        """,
    )
    parser.add_argument("--send", action="store_true", help="Envoyer le rapport par e-mail")
    parser.add_argument("--validate", action="store_true", help="Valider le rapport après génération")
    parser.add_argument(
        "--output",
        type=str,
        default=f"rapport_boursier_{format_datetime(get_local_time(), '%Y%m%d_%H%M')}.html",
        help="Nom du fichier de sortie",
    )
    args = parser.parse_args()

    generation_time = get_local_time()

    print("=" * 80)
    print("🚀 ANALYSE BOURSIÈRE IA — CLAUDE (ANTHROPIC)")
    print("=" * 80)
    print(f"📅 Date: {format_datetime(generation_time, '%A %d %B %Y à %H:%M:%S')}")
    print(f"🤖 Modèle: {CLAUDE_MODEL}")
    print(f"🌍 Fuseau: {TIMEZONE}")
    print("=" * 80)

    if not ANTHROPIC_API_KEY:
        print("⚠️  ATTENTION: ANTHROPIC_API_KEY non configurée — les analyses IA seront vides.")

    # 1. Contexte de marché
    market_context = get_market_context()
    print(f"   ├─ Sentiment: {market_context['market_sentiment']}")
    print(f"   └─ Risque: {market_context['risk_level']}")

    # 2. Benchmarks (indices de référence)
    print("\n📡 Récupération des benchmarks...")
    benchmarks = get_benchmark_data()
    for b in benchmarks:
        sign = "+" if b["change_pct"] >= 0 else ""
        print(f"   ├─ {b['name']}: {b['price']:.2f} ({sign}{b['change_pct']:.2f}%)")

    # 3. Sélection des actifs
    assets = get_dynamic_assets_from_ai()
    total_assets = len(assets["us_actions"]) + len(assets["eu_actions"]) + len(assets["etfs"])
    print(f"\n📊 Actifs sélectionnés: {len(assets['us_actions'])} US + {len(assets['eu_actions'])} EU + {len(assets['etfs'])} ETFs = {total_assets}")

    # 4. Données de marché enrichies
    print("\n📈 Récupération des cours en temps réel...")
    us_raw = get_market_data(assets["us_actions"] + assets["etfs"])
    eu_raw = get_market_data(assets["eu_actions"])
    print(f"   ├─ {len(us_raw)} actifs US/ETF récupérés")
    print(f"   └─ {len(eu_raw)} actifs EU récupérés")

    # 5. Analyses IA
    print("\n🧠 Génération des analyses Claude...")
    for i, item in enumerate(us_raw, 1):
        item["ai"] = get_ai_analysis(item, market_context)
        print(f"   ├─ [{i:02d}/{len(us_raw):02d}] {item['symbol']}: {item['ai']['recommendation']}")
    for i, item in enumerate(eu_raw, 1):
        item["ai"] = get_ai_analysis(item, market_context)
        print(f"   ├─ [{i:02d}/{len(eu_raw):02d}] {item['symbol']}: {item['ai']['recommendation']}")
    print(f"   └─ {len(us_raw) + len(eu_raw)} analyses complétées")

    # 6. Recommandations stratégiques
    recommendations = generate_recommendations(us_raw, eu_raw, market_context)
    print(f"\n💡 {len(recommendations['recommendations'])} recommandations stratégiques générées")

    # 7. Résumé exécutif
    print("\n📝 Rédaction du résumé exécutif...")
    all_syms = [f"{x['symbol']} ({x['name']})" for x in us_raw + eu_raw]
    summary_prompt = f"""Contexte: {market_context['key_message']}

Actifs analysés: {', '.join(all_syms[:10])}... et {len(all_syms) - 10} autres.

Rédige un résumé financier expert de 3-4 phrases maximum qui:
1. Résume la tendance générale observée
2. Identifie les secteurs les plus dynamiques
3. Mentionne les points d'attention pour les investisseurs

Ton professionnel et synthétique. Pas de jargon inutile."""

    summary = call_claude(
        summary_prompt,
        system="Tu es un rédacteur financier senior qui synthétise l'information de manière claire et impactante.",
    )
    if not summary:
        summary = "Marchés en évolution avec des opportunités sectorielles. Surveillance recommandée sur les valeurs technologiques et les ETFs diversifiés."
    print("   └─ Synthèse rédigée")

    # 8. Génération HTML
    print("\n🎨 Génération du rapport HTML...")
    html = generate_html(summary, us_raw, eu_raw, benchmarks, market_context, recommendations, generation_time)

    output_file = args.output
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)
    file_size_kb = os.path.getsize(output_file) / 1024
    print(f"   └─ ✅ Rapport sauvegardé: {output_file} ({file_size_kb:.1f} KB)")

    # 9. Validation (si --validate)
    if args.validate:
        valid = validate_report(us_raw, eu_raw, benchmarks, generation_time)
        if not valid:
            print("\n⚠️  Des erreurs ont été détectées dans la validation. Vérifiez les logs ci-dessus.")
            sys.exit(1)

    # 10. Envoi email
    if args.send:
        print("\n📧 Envoi du rapport par e-mail...")
        recipients = [e.strip() for e in RECIPIENT_EMAILS.split(",") if e.strip()]
        print(f"   ├─ Destinataires: {len(recipients)}")
        for email in recipients:
            print(f"   │  • {email}")
        if send_email(html):
            print(f"   └─ ✅ Rapport envoyé avec succès à {len(recipients)} destinataire(s)")
        else:
            print("   └─ ⚠️  Échec de l'envoi du rapport")

    print("\n" + "=" * 80)
    print("✅ ANALYSE TERMINÉE AVEC SUCCÈS")
    print("=" * 80)
    print(f"📄 Fichier: {output_file} ({file_size_kb:.1f} KB)")
    print(f"⏰ Durée: {(get_local_time() - generation_time).total_seconds():.1f} secondes")
    print("=" * 80)


if __name__ == "__main__":
    main()
