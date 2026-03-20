# Crypto Trading Bot — Gemini + Binance Testnet

Stack 100% gratuito. Funciona no Brasil. Sem dados fiscais. Sem dinheiro real.

## Pré-requisitos

- Python 3.10+
- Conta Google (para Gemini)
- Conta GitHub (para Binance Testnet)

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração (2 passos)

### 1. Chave do Gemini (grátis)
- Acesse https://aistudio.google.com/apikey
- Clique em "Create API Key"
- Cole em `GEMINI_API_KEY` no `config.py`

### 2. Chaves da Binance Testnet (grátis, sem cadastro fiscal)
- Acesse https://testnet.binance.vision
- Clique em **"Log in with GitHub"**
- Vá em **API Keys** → **Generate HMAC_SHA256 Key**
- Dê um nome qualquer e copie a API Key e Secret
- Cole em `BINANCE_API_KEY` e `BINANCE_SECRET_KEY` no `config.py`

> O saldo inicial no testnet é ~15.000 USDT virtual. Se acabar,
> clique em "Faucet" no dashboard para repor.

## Uso

```bash
python bot.py
```

## Estrutura

```
config.py   ← suas chaves e parâmetros
bot.py      ← orquestrador principal
  ├── get_market_data()      ← busca velas e ticker na Binance Testnet
  ├── analyze_with_gemini()  ← BUY / SELL / HOLD com confiança
  └── execute_trade()        ← ordem de mercado no testnet
bot.log     ← gerado automaticamente
```

## Limites gratuitos

| Serviço           | Limite                        |
|-------------------|-------------------------------|
| Gemini 2.0 Flash  | 10 req/min · 250 req/dia      |
| Binance Testnet   | Ilimitado                     |

3 símbolos × ciclo de 60 min = ~72 req/dia — dentro do limite.
