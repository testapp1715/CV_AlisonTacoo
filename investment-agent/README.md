# Agente de inversión (servidor MCP)

Servidor MCP en Python que analiza criptomonedas con datos públicos de CoinGecko,
valora tu portafolio, calcula riesgo, detecta señales y te avisa por Telegram.
**No ejecuta operaciones**: las compras y ventas las haces tú en la app.

## Herramientas

| Herramienta | Qué hace |
|---|---|
| `search_asset` | Encuentra el id de CoinGecko a partir de un nombre o símbolo |
| `get_market_prices` | Precio actual, variación en 24 h y capitalización |
| `get_portfolio` | Tus posiciones a precio actual, con peso y ganancia o pérdida |
| `analyze_asset` | Tendencia, medias de 20 y 50 días, RSI, volatilidad y caída máxima |
| `calculate_risk` | Concentración, volatilidad del portafolio y pérdida diaria estimada |
| `find_opportunities` | Evalúa tus reglas sobre la lista de seguimiento |
| `generate_trade_plan` | Entrada, stop, objetivos y tamaño de posición según el riesgo que aceptes |
| `send_alert` | Envía un mensaje a tu Telegram |

## Instalación

Requiere Python 3.10 o superior.

```bash
cd investment-agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp portfolio.example.json portfolio.json
```

Edita `portfolio.json` con tus posiciones reales. El archivo está en `.gitignore`
para que no se suba al repositorio. Actualízalo después de cada compra o venta.

- `holdings`: `id` de CoinGecko, `amount` (unidades) y, si quieres ver ganancias, `avg_cost_usd`.
- `watchlist`: activos que quieres vigilar aunque no los tengas.
- `rules`: umbrales de las señales (RSI, caída en 7 días, peso máximo por posición).

## Variables de entorno

| Variable | Uso |
|---|---|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Necesarias solo para `send_alert` y `scan.py`. El bot se crea con @BotFather |
| `COINGECKO_API_KEY` | Opcional: clave demo gratuita, sube el límite de peticiones |
| `PORTFOLIO_FILE` | Opcional: ruta alternativa al archivo de portafolio |

## Conectar a un cliente MCP

Claude Code:

```bash
claude mcp add agente-inversion -- /ruta/investment-agent/.venv/bin/python /ruta/investment-agent/server.py
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "agente-inversion": {
      "command": "/ruta/investment-agent/.venv/bin/python",
      "args": ["/ruta/investment-agent/server.py"],
      "env": { "TELEGRAM_BOT_TOKEN": "...", "TELEGRAM_CHAT_ID": "..." }
    }
  }
}
```

## Alertas automáticas

Un servidor MCP solo responde cuando se le pregunta. Para recibir avisos sin
abrir el chat, programa `scan.py`, que evalúa las reglas y escribe a Telegram
solo cuando hay señales:

```cron
0 * * * *  cd /ruta/investment-agent && .venv/bin/python scan.py
```

## Pruebas

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest
```

Las pruebas simulan CoinGecko y no necesitan red.

## Límites

- Solo cripto. Para acciones habría que añadir otro proveedor de datos.
- El portafolio se mantiene a mano porque Meru no publica una API.
- Las señales son reglas técnicas simples: sirven para decidir qué revisar, no predicen el precio.
