#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""区块链钱包资产全链查询 —— 多链钱包持仓汇总引擎。

数据通道（全部为无密钥公开接口）：
  EVM    Blockscout v2 实例（eth/optimism/gnosis/base/polygon/arbitrum/avalanche/
         scroll/zksync/linea/mantle）+ BSC 官方 dataseed 公共 RPC
  BTC    Blockstream Esplora API
  TRON   Tronscan（主）/ TronGrid（兜底）
  SOL    Solana 公共 JSON-RPC
  价格   DeFiLlama coins.llama.fi；聚合器未收录的长尾代币由 pair_price.py 链上算价

用法：
  python wallet_full_chain.py 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045
  python wallet_full_chain.py 0x... --cny
  python wallet_full_chain.py 0x... --chains 1,56,137
  python wallet_full_chain.py TN4... --family tron

只读查询：不读取私钥、不签名、不发交易。
安全边界：
  * 只接受公开账本地址；形似私钥/助记词/种子的输入一律拒收。
  * 不使用、不读取、不传输任何 API 凭证（无 API Key / Secret / Passphrase / Token）。
    全部出口均为公开只读端点，无账号身份、无签名环节。
  * 出口域名在代码中静态写死，不接受运行时传入的任意主机。
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; wallet-full-chain-assets/2.0)"}
TIMEOUT = 20

# 出口域名白名单：全部为公开、只读、无需凭证的端点。
# 代码中静态写死，不接受任何运行时传入的主机参数。
LLAMA_PRICES = "https://coins.llama.fi/prices/current/"
CNY_RATE_URL = "https://open.er-api.com/v6/latest/USD"

# ---------------------------------------------------------------- 链字典
# chainIndex -> (显示名, DeFiLlama 链前缀, 原生币 coingecko id, 链族)
CHAIN_META = {
    # --- 非 EVM 主链 ---
    "0":     ("Bitcoin",        None,        "bitcoin",       "btc"),
    "501":   ("Solana",         "solana",    "solana",        "solana"),
    "195":   ("Tron",           "tron",      "tron",          "tron"),
    "607":   ("TON",            None,        "the-open-network", "ton"),
    "784":   ("SUI",            "sui",       "sui",           "sui"),
    # --- EVM ---
    "1":     ("Ethereum",       "ethereum",  "ethereum",      "evm"),
    "56":    ("BNB Chain",      "bsc",       "binancecoin",   "evm"),
    "137":   ("Polygon",        "polygon",   "matic-network", "evm"),
    "42161": ("Arbitrum One",   "arbitrum",  "ethereum",      "evm"),
    "10":    ("Optimism",       "optimism",  "ethereum",      "evm"),
    "8453":  ("Base",           "base",      "ethereum",      "evm"),
    "43114": ("Avalanche C",    "avax",      "avalanche-2",   "evm"),
    "250":   ("Fantom",         "fantom",    "fantom",        "evm"),
    "324":   ("zkSync Era",     "zksync",    "ethereum",      "evm"),
    "59144": ("Linea",          "linea",     "ethereum",      "evm"),
    "534352":("Scroll",         "scroll",    "ethereum",      "evm"),
    "5000":  ("Mantle",         "mantle",    "mantle",        "evm"),
    "81457": ("Blast",          "blast",     "ethereum",      "evm"),
    "169":   ("Manta Pacific",  "manta",     "ethereum",      "evm"),
    "1088":  ("Metis",          "metis",     "metis-token",   "evm"),
    "25":    ("Cronos",         "cronos",    "crypto-com-chain", "evm"),
    "100":   ("Gnosis",         "gnosis",    "xdai",          "evm"),
    "1030":  ("Conflux",        "conflux",   "conflux-token", "evm"),
    "146":   ("Sonic",          "sonic",     "sonic-3",       "evm"),
    "1101":  ("Polygon zkEVM",  "polygon_zkevm", "ethereum",  "evm"),
    "130":   ("Uni Chain",      "unichain",  "ethereum",      "evm"),
    "7000":  ("ZetaChain",      "zetachain", "zetachain",     "evm"),
    "999":   ("HyperEVM",       "hyperevm",  "hyperliquid",   "evm"),
    "57073": ("Ink",            "ink",       "ethereum",      "evm"),
    "5042":  ("Arc",            None,        "ethereum",      "evm"),
    "143":   ("Monad",          "monad",     "ethereum",      "evm"),
    "9745":  ("Plasma",         None,        "ethereum",      "evm"),
    "1672":  ("Pharos",         None,        "ethereum",      "evm"),
    "4200":  ("Merlin",         "merlin",    "bitcoin",       "evm"),
    "196":   ("X Layer",        "xlayer",    "okb",           "evm"),
    # --- 代币化股票 / RWA 专链 ---
    "4663":  ("Robinhood",      None,        None,            "equity"),
    # BTC 生态铭文
    "0_brc20": ("Bitcoin BRC-20", None,      None,            "inscription"),
}

# 无密钥 EVM 兜底：chainIndex -> Blockscout v2 实例
BLOCKSCOUT = {
    "1":     "https://eth.blockscout.com",
    "10":    "https://optimism.blockscout.com",
    "100":   "https://gnosis.blockscout.com",
    "8453":  "https://base.blockscout.com",
    "137":   "https://polygon.blockscout.com",
    "42161": "https://arbitrum.blockscout.com",
    "43114": "https://avalanche.blockscout.com",
    "534352":"https://scroll.blockscout.com",
    "324":   "https://zksync.blockscout.com",
    "59144": "https://linea.blockscout.com",
    "5000":  "https://mantle.blockscout.com",
}

# 无密钥非 EVM 兜底端点
BLOCKSTREAM = "https://blockstream.info/api"
TRONGRID = "https://api.trongrid.io"
TRONSCAN = "https://apilist.tronscan.org/api"
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

# ---------------------------------------------------------------- 资产分类
# 这些是"头寸型/衍生型"资产，计价方式与普通代币不同，必须单独归类，
# 否则会漏算（LP 凭证常被当成垃圾币丢弃）或重复计算（质押凭证与其底层）。
LP_HINTS = [
    "UNI-V2", "SLP", "CAKE-LP", "G-UNI", "3CRV", "CRV3", "PENDLE-LPT",
    "BALANCER", "AERO", "VELO", "VAMM", "HYPER", "LPT", "CURVE",
]
LP_ADDR_HINTS = ["uniswap", "pancake", "sushi", "curve", "balancer", "aerodrome"]
STAKING_HINTS = [
    "STETH", "WSTETH", "RETH", "FRXETH", "SFRXETH", "EZETH", "RSETH", "EETH",
    "SUSDE", "SUSDS", "AEth", "AARB", "AOPT", "AMATIC", "AETH", "CETHV3",
    "STKAAVE", "SFRX", "ANKRETH", "CBETH", "OSETH", "METH", "SWETH",
]
# 代币化股票 / RWA 常见后缀（xStocks 用 x 后缀，Ondo 用 on 后缀）
EQUITY_SUFFIX = ("X", "ON")
EQUITY_TICKERS = {
    "AAPL", "TSLA", "NVDA", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NFLX",
    "AMD", "COIN", "MSTR", "SPY", "QQQ", "VOO", "IVV", "GLD", "SLV", "BRK.B",
    "ORCL", "INTC", "PLTR", "UBER", "ABNB", "DIS", "BA", "JPM", "V", "MA",
    "COST", "WMT", "KO", "PEP", "XOM", "CVX", "PFE", "JNJ", "UNH", "CRCL",
    "BNC", "HOOD", "SPCX",
}
# 代币化股票的名称关键词（用于 Robinhood Chain 等“股票链”上区分股票与 meme 币）
EQUITY_NAMES = {
    "APPLE", "NVIDIA", "TESLA", "MICROSOFT", "ALPHABET", "AMAZON", "META",
    "NETFLIX", "COINBASE", "MICROSTRATEGY", "CEA INDUSTRIES", "BERKSHIRE",
    "PALANTIR", "ORACLE", "INTEL", "BOEING", "JPMORGAN", "VISA", "MASTERCARD",
}


def is_equity(sym, nm):
    """代币化股票 / RWA 判定。

    **必须按「符号 + 名称」自身判定，不可因「所处链是股票链」而整链判定**——
    实测 Robinhood Chain（4663）上同时部署了大量普通 meme 币（AI / Artificial Inu、NEST），
    整链硬编码会把 meme 币误标为股票，并进而用错计价锚。
    识别形态：符号 = 股票代码（AAPL），或 股票代码 + B/X/ON/4 后缀（AAPLB / GOOGLB / NVDAB / BNC4）；
    名称命中已知公司名（Apple / NVIDIA Corp / Cea Industries …）。
    """
    if any(n in nm for n in EQUITY_NAMES):
        return True
    if sym in EQUITY_TICKERS:
        return True
    for suf in ("B", "X", "ON", "4"):
        if sym.endswith(suf) and sym[: -len(suf)] in EQUITY_TICKERS:
            return True
    return False


def classify(symbol, contract, chain_index, name=""):
    """返回资产类别标签。脚本给初判，最终由助手复核。"""
    sym = (symbol or "").upper()
    ct = (contract or "").lower()
    nm = (name or "").upper()
    if ct == "" or ct == "native":
        return "native"
    for h in LP_HINTS:
        if h in sym or h in nm:
            return "lp_position"
    if any(h in ct for h in LP_ADDR_HINTS):
        return "lp_position"
    if is_equity(sym, nm):
        return "equity_rwa"
    # 收益凭证（Pendle PT/YT）必须先于质押凭证判定：
    # 符号如 PT-sUSDE-27FEB2025 同时含 "SUSDE"，顺序颠倒会误判为质押。
    if sym.startswith("PT-") or sym.startswith("YT-") or "-PT-" in sym:
        return "yield_token"
    for h in STAKING_HINTS:
        if h in sym:
            return "staking_receipt"
    return "token"


# ---------------------------------------------------------------- HTTP
# 使用标准库的默认网络出口：遵循系统代理设置与 no_proxy 环境变量。
# 不在代码层强制指定、改写或绕过任何代理配置——网络路径完全交由用户环境决定。
# 按域名做短期熔断，避免对不可达域名重复付出超时代价。
_DEAD_HOSTS = {}          # netloc -> True 表示本进程内已判定不可达


def http_json(url, method="GET", body=None, headers=None, timeout=TIMEOUT):
    data = body.encode("utf-8") if isinstance(body, str) else body
    hdrs = dict(UA)
    if headers:
        hdrs.update(headers)
    host = urllib.parse.urlparse(url).netloc
    if _DEAD_HOSTS.get(host):
        raise ConnectionError(f"{host} 在本进程内已判定不可达，跳过重试")
    try:
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        _DEAD_HOSTS[host] = True
        raise e


# ---------------------------------------------------------------- 无密钥通道
def fetch_blockscout(base, addr):
    """Blockscout v2：原生币 + 代币余额。返回 (native, tokens) 或抛异常。"""
    info = http_json(f"{base}/api/v2/addresses/{addr}")
    native_raw = info.get("coin_balance")
    native = (int(native_raw) / 1e18) if native_raw not in (None, "") else 0.0
    tokens = []
    if info.get("has_tokens"):
        items = http_json(f"{base}/api/v2/addresses/{addr}/token-balances")
        if isinstance(items, dict):
            items = items.get("items", [])
        for it in items or []:
            tok = it.get("token") or {}
            if (tok.get("type") or "").upper() not in ("ERC-20", "ERC-721", "ERC-1155", ""):
                continue
            dec = tok.get("decimals")
            try:
                amt = int(it.get("value") or 0) / (10 ** int(dec or 18))
            except (TypeError, ValueError, OverflowError):
                continue
            if amt <= 0:
                continue
            tokens.append({
                "asset": tok.get("symbol") or "?",
                "contract": str(tok.get("address_hash") or tok.get("address") or "").lower(),
                "amount": amt,
                "name": tok.get("name") or "",
                "exchange_rate": it.get("exchange_rate") or tok.get("exchange_rate"),
            })
    return native, tokens


def fetch_btc(addr):
    d = http_json(f"{BLOCKSTREAM}/address/{addr}")
    funded = (d.get("chain_stats") or {}).get("funded_txo_sum", 0)
    spent = (d.get("chain_stats") or {}).get("spent_txo_sum", 0)
    return (funded - spent) / 1e8


TRON_SOURCE = {"mode": "tronscan"}   # 供报告说明实际使用的数据源


def fetch_tron(addr):
    """Tron 持仓。优先 Tronscan（返回代币符号 + 以 TRX 计价的价格），
    TronGrid 仅作兜底（只有合约地址、无符号、精度不可靠）。"""
    TRON_SOURCE["mode"] = "tronscan"
    try:
        d = http_json(f"{TRONSCAN}/account?address={addr}", timeout=15)
        trx = float(d.get("balance") or 0) / 1e6
        tokens = []
        for t in d.get("trc20token_balances") or []:
            if (t.get("tokenType") or "trc20").lower() != "trc20":
                continue          # 排除 trc10 / trc721
            try:
                amt = float(t.get("amount") or 0)
                if amt <= 0:
                    dec = int(t.get("tokenDecimal") or 6)
                    amt = int(t.get("balance") or 0) / (10 ** dec)
            except (TypeError, ValueError, OverflowError):
                continue
            if amt <= 0:
                continue
            try:
                pin = float(t.get("tokenPriceInTrx") or 0) or None
            except (TypeError, ValueError):
                pin = None
            tokens.append({
                "asset": t.get("tokenAbbr") or (t.get("tokenId") or "?")[:10] + "…",
                "contract": t.get("tokenId") or "",
                "amount": amt,
                "name": t.get("tokenName") or "",
                "price_in_native": pin,       # 以 TRX 计价，稍后乘 TRX/USD
            })
        if tokens or trx > 0:
            return trx, tokens
    except Exception as e:
        sys.stderr.write(f"tronscan failed, fallback to trongrid: {str(e)[:90]}\n")

    TRON_SOURCE["mode"] = "trongrid"
    d = http_json(f"{TRONGRID}/v1/accounts/{addr}", timeout=15)
    if not d.get("data"):
        return 0.0, []
    acct = d["data"][0]
    trx = (acct.get("balance") or 0) / 1e6
    tokens = []
    for t in acct.get("trc20") or []:
        for contract, raw in t.items():
            try:
                tokens.append({"asset": contract[:10] + "…", "contract": contract,
                               "amount": float(raw) / 1e6, "name": "",
                               "price_in_native": None})
            except (TypeError, ValueError):
                continue
    return trx, tokens


def fetch_solana(addr):
    bal = http_json(SOLANA_RPC, method="POST", body=json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [addr]}),
        headers={"Content-Type": "application/json"})
    lamports = (bal.get("result") or {}).get("value", 0)
    native = lamports / 1e9
    tokens = []
    try:
        res = http_json(SOLANA_RPC, method="POST", body=json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "getTokenAccountsByOwner",
            "params": [addr, {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                       {"encoding": "jsonParsed"}]}),
            headers={"Content-Type": "application/json"})
        for acc in ((res.get("result") or {}).get("value") or []):
            info = (((acc.get("account") or {}).get("data") or {}).get("parsed") or {}).get("info") or {}
            amt = ((info.get("tokenAmount") or {}).get("uiAmount") or 0)
            if amt and amt > 0:
                tokens.append({"asset": (info.get("mint") or "?")[:6] + "…",
                               "contract": info.get("mint") or "", "amount": float(amt),
                               "name": ""})
    except Exception as e:
        sys.stderr.write(f"solana token scan failed: {e}\n")
    return native, tokens


# ---------------------------------------------------------------- 地址识别
B58 = r"[1-9A-HJ-NP-Za-km-z]"          # base58 字符集（去掉 0 O I l）

FAMILY_LABEL = {
    "evm": "EVM 系（ETH/BSC/Polygon/Arbitrum/Base…）",
    "btc": "Bitcoin", "ltc": "Litecoin", "doge": "Dogecoin",
    "tron": "Tron（TRC-20）", "solana": "Solana（SPL）",
    "ton": "TON", "sui": "SUI / Aptos（Move 系）",
    "cosmos": "Cosmos 生态（cosmos1…）",
    "xrp": "XRP Ledger", "polkadot": "Polkadot / Substrate（SS58）",
    "unknown": "无法识别",
}

# ---------------------------------------------------------------- 地址校验与脱敏
# 本技能的所有输入都是「公开账本地址」，地址本身不含任何可用作凭证的信息。
# 校验目的仅为拦截明显非地址的输入（如误粘贴的私钥长度串），并统一大小写处理。
ADDR_RULES = {
    "evm":      r"0x[0-9a-fA-F]{40}",
    "sui":      r"0x[0-9a-fA-F]{64}",
    "btc":      r"(bc1|BC1)[0-9a-zA-Z]{25,62}|[13][1-9A-HJ-NP-Za-km-z]{25,39}",
    "ltc":      r"(ltc1|LTC1)[0-9a-z]{25,62}|L[1-9A-HJ-NP-Za-km-z]{26,33}",
    "doge":     r"D[1-9A-HJ-NP-Za-km-z]{33}",
    "tron":     r"T[1-9A-HJ-NP-Za-km-z]{33}",
    "ton":      r"(EQ|UQ)[A-Za-z0-9_\-]{46}|0:[0-9a-fA-F]{64}",
    "cosmos":   r"cosmos1[a-z0-9]{38}",
    "xrp":      r"r[1-9A-HJ-NP-Za-km-z]{24,34}",
    "solana":   r"[1-9A-HJ-NP-Za-km-z]{32,44}",
    "polkadot": r"[1-9A-HJ-NP-Za-km-z]{45,50}",
}


def validate_address(addr):
    """校验并归一化地址。返回 (ok, addr, err)。

    仅做「格式是否像公开地址」的判断。**不做任何校验和计算、不接触任何密钥**。
    额外拦截 64 位纯 hex（可能是公私钥/种子），此类输入一律拒收。
    """
    a = (addr or "").strip()
    if not a:
        return False, a, "地址为空"
    if len(a) > 128 or any(c.isspace() for c in a):
        return False, a, "地址含空白字符或长度异常，请检查是否误粘贴了其他内容"
    if re.fullmatch(r"[0-9a-fA-F]{64}", a) or re.fullmatch(r"[0-9a-fA-F]{128}", a):
        return False, a, "该输入形似密钥/种子而非账本地址，本技能只接受公开地址，已拒绝处理"
    fam = detect_family(a)
    if fam == "unknown":
        return False, a, "无法识别的地址格式，请确认链族"
    if not re.fullmatch(ADDR_RULES[fam], a):
        return False, a, f"地址格式与识别出的链族（{FAMILY_LABEL.get(fam, fam)}）不符"
    return True, a, None


def mask_addr(a):
    """脱敏：报告默认只写前 8 位 + 后 6 位，中间省略。"""
    if not a or len(a) <= 14:
        return a or ""
    return f"{a[:8]}…{a[-6:]}"


def detect_family(addr):
    """按前缀 + 长度精确路由链族。顺序敏感：先具体后泛化。"""
    a = addr.strip()
    if re.fullmatch(r"0x[0-9a-fA-F]{40}", a):
        return "evm"
    if re.fullmatch(r"0x[0-9a-fA-F]{64}", a):
        return "sui"                                    # SUI / Aptos
    if a.startswith(("bc1", "BC1")) or re.fullmatch(rf"[13]{B58}{{25,39}}", a):
        return "btc"
    if a.startswith(("ltc1", "LTC1")) or re.fullmatch(rf"L{B58}{{26,33}}", a):
        return "ltc"
    if re.fullmatch(rf"D{B58}{{33}}", a):
        return "doge"
    if re.fullmatch(rf"T{B58}{{33}}", a):
        return "tron"
    if a.startswith(("EQ", "UQ", "0:")) or re.fullmatch(r"E[Qq][A-Za-z0-9_\-]{46}", a):
        return "ton"
    if re.fullmatch(r"cosmos1[a-z0-9]{38}", a):
        return "cosmos"
    if re.fullmatch(rf"r{B58}{{24,34}}", a):
        return "xrp"
    if re.fullmatch(rf"{B58}{{32,44}}", a):
        return "solana"
    if re.fullmatch(rf"{B58}{{45,50}}", a):
        return "polkadot"
    return "unknown"


# ---------------------------------------------------------------- 估值
def llama_prices(ids):
    """批量取价。内建熔断：连续失败 2 次即放弃剩余请求——
    价格源在受限网络下不可达时，逐块重试会让整个查询卡死数分钟。"""
    out = {}
    ids = [i for i in ids if i]
    fails = 0
    for i in range(0, len(ids), 30):
        if fails >= 2:
            sys.stderr.write(f"price source unreachable, skipped {len(ids)-i} remaining ids\n")
            break
        chunk = ",".join(ids[i:i + 30])
        try:
            out.update((http_json(LLAMA_PRICES + chunk, timeout=8) or {}).get("coins", {}))
            fails = 0
        except Exception as e:
            fails += 1
            sys.stderr.write(f"price chunk failed ({fails}): {str(e)[:80]}\n")
    return out


def build_report(addr, source, holdings, notes, errors, want_cny, full_addr=False):
    priced, unpriced = [], []
    for h in holdings:
        p = h.get("price_usd")
        if p is None:
            unpriced.append({k: h[k] for k in ("chain", "asset", "amount", "class", "contract")})
            continue
        v = h["amount"] * p
        priced.append({
            "chain": h["chain"], "asset": h["asset"], "class": h["class"],
            "amount": round(h["amount"], 8), "price_usd": p, "value_usd": round(v, 2),
            "contract": h.get("contract", ""),
        })

    by_chain = {}
    for r in sorted(priced, key=lambda x: -x["value_usd"]):
        c = by_chain.setdefault(r["chain"], {"assets": [], "subtotal_usd": 0.0})
        c["assets"].append(r)
        c["subtotal_usd"] = round(c["subtotal_usd"] + r["value_usd"], 2)

    by_class = {}
    for r in priced:
        by_class[r["class"]] = round(by_class.get(r["class"], 0.0) + r["value_usd"], 2)

    total = round(sum(r["value_usd"] for r in priced), 2)
    rep = {
        "address": addr if full_addr else mask_addr(addr),
        "address_masked": not full_addr,
        "source": source,
        "total_usd": total,
        "by_class_usd": by_class,
        "chains": by_chain,
        "unpriced_assets": unpriced,
        "notes": notes, "errors": errors,
        "disclaimer": "链上公开数据只读聚合结果，非本人资产证明，不构成投资建议。",
    }
    if want_cny:
        try:
            rep["usd_cny_rate"] = http_json(CNY_RATE_URL)["rates"]["CNY"]
            rep["total_cny"] = round(total * rep["usd_cny_rate"], 2)
        except Exception as e:
            rep["cny_error"] = str(e)[:100]
    return rep


# ---------------------------------------------------------------- 主流程
CHAIN_NAME_TO_ID = {m[0]: k for k, m in CHAIN_META.items()}


def resolve_prices(holdings, price_ids, price_file, notes, errors):
    """统一取价：DeFiLlama → price-file 覆盖 → 按原生币/合约地址匹配 → TRX 计价二次换算。"""
    prices = llama_prices(price_ids)
    if price_file:
        try:
            with open(price_file, "r", encoding="utf-8") as f:
                extra = json.load(f)
            for k, v in (extra or {}).items():
                prices[k] = v if isinstance(v, dict) else {"price": float(v)}
            notes.append(f"已注入离线价格 {len(extra)} 条（--price-file）")
        except Exception as e:
            errors.append(f"price-file 读取失败: {type(e).__name__} {str(e)[:120]}")
    if not prices and price_ids:
        notes.append("价格源不可达且未提供 --price-file：仅能列出数量，无法估值")

    for h in holdings:
        if h.get("price_usd") is not None:
            continue
        if h["class"] == "native":
            cid = str(h.get("chain_index") or CHAIN_NAME_TO_ID.get(h.get("chain", ""), ""))
            cg = CHAIN_META.get(cid, (None, None, None, None))[2]
            if cg:
                h["price_usd"] = (prices.get(f"coingecko:{cg}") or {}).get("price")
        elif h.get("contract"):
            for pre in ("ethereum", "bsc", "polygon", "arbitrum", "optimism", "base",
                        "avax", "tron", "solana", "xlayer", "linea", "scroll", "mantle"):
                key = f"{pre}:{h['contract']}"
                if key in prices:
                    h["price_usd"] = prices[key]["price"]
                    break

    trx_usd = (prices.get("coingecko:tron") or {}).get("price")
    if trx_usd:
        for h in holdings:
            if h.get("price_usd") is None and h.get("price_in_native"):
                h["price_usd"] = h["price_in_native"] * trx_usd
    return prices


def emit(rep, out_path):
    txt = json.dumps(rep, ensure_ascii=False, indent=2)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(txt)
    else:
        print(txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("address")
    ap.add_argument("--chains", default="all")
    ap.add_argument("--family", default=None, help="evm|btc|solana|tron|ton|sui")
    ap.add_argument("--price-file", default=None,
                    help='离线价格注入（价格源不可达时使用）。JSON 形如 '
                         '{"coingecko:tron":0.32,"ethereum:0xa0b8...":1.0}')
    ap.add_argument("--holdings", default=None,
                    help='离线持仓注入：跳过全部网络抓取，直接对给定持仓做分类+估值+汇总。'
                         'JSON 数组，每项 {"chain","asset","amount","contract","class"}（class 可省）')
    ap.add_argument("--out", default=None, help="把报告写入文件而不是打印")
    ap.add_argument("--cny", action="store_true")
    ap.add_argument("--full-address", action="store_true",
                    help="报告中输出完整地址（默认脱敏为 前8…后6）")
    args = ap.parse_args()

    ok, addr, verr = validate_address(args.address)
    if not ok:
        print(json.dumps({
            "error": verr,
            "policy": "本技能只接受公开账本地址（0x…/bc1…/T…/base58…）。"
                      "不接受、不解析、不存储任何私钥、助记词或种子短语。",
        }, ensure_ascii=False, indent=2))
        sys.exit(2)

    family = args.family or detect_family(addr)
    notes, errors, holdings = [], [], []
    notes.append("数据来源为公开链上账本与公开价格接口，全部请求均为只读（HTTP GET / eth_call）。")
    notes.append("地址已脱敏输出（如需完整地址加 --full-address）。")

    # 选择链集合
    if args.chains.lower() == "all":
        chain_ids = list(CHAIN_META.keys())
    else:
        chain_ids = [c.strip() for c in args.chains.split(",")]

    # ---- 离线持仓注入：跳过全部网络抓取，仅做分类 + 估值 + 汇总 ----
    # 适用场景：脚本出口被阻断，但助手已通过自身抓取通道拿到原始持仓。
    if args.holdings:
        try:
            with open(args.holdings, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            emit({"error": f"holdings 读取失败: {type(e).__name__} {str(e)[:120]}"}, None)
            sys.exit(2)
        rows = raw if isinstance(raw, list) else raw.get("holdings", [])
        price_ids = []
        for h in rows:
            try:
                amt = float(h.get("amount") or 0)
            except (TypeError, ValueError):
                continue
            if amt <= 0:
                continue
            chain = h.get("chain") or "Unknown"
            ci = str(h.get("chain_index") or CHAIN_NAME_TO_ID.get(chain, ""))
            contract = (h.get("contract") or "").strip()
            asset = h.get("asset") or "?"
            cls = h.get("class") or classify(asset, contract, ci, h.get("name", ""))
            entry = {"chain": chain, "asset": asset, "contract": contract,
                     "amount": amt, "class": cls, "price_usd": None}
            if h.get("price_usd") is not None:
                try:
                    entry["price_usd"] = float(h["price_usd"])
                except (TypeError, ValueError):
                    entry["price_usd"] = None
            if h.get("price_in_native") is not None:
                entry["price_in_native"] = h["price_in_native"]
            holdings.append(entry)
            meta = CHAIN_META.get(ci, (None, None, None, None))
            if entry["price_usd"] is None:
                if cls == "native" and meta[2]:
                    price_ids.append(f"coingecko:{meta[2]}")
                elif contract and meta[1]:
                    price_ids.append(f"{meta[1]}:{contract}")
        notes.append(f"离线持仓注入：{len(holdings)} 项（已跳过网络抓取）")
        resolve_prices(holdings, price_ids, args.price_file, notes, errors)
        rep = build_report(addr, "offline_holdings_injection", holdings, notes, errors,
                           args.cny, args.full_address)
        rep["detected_family"] = family
        emit(rep, args.out)
        return

    # 本技能不使用任何 API 凭证：取数一律走无密钥公开只读接口
    source = "keyless_public_apis"
    notes.append("数据通道：无密钥公开只读接口（全程不使用任何 API 凭证）")
    price_ids = []

    if family == "evm":
        for cid in chain_ids:
            base = BLOCKSCOUT.get(cid)
            if not base:
                continue
            try:
                native, toks = fetch_blockscout(base, addr)
                name, llama, cg, _ = CHAIN_META.get(cid, (f"Chain {cid}", None, None, "evm"))
                if native > 0:
                    holdings.append({"chain": name, "asset": name, "contract": "",
                                     "amount": native, "class": "native",
                                     "price_usd": None})
                    price_ids.append(f"coingecko:{cg}" if cg else None)
                for t in toks:
                    holdings.append({"chain": name, "asset": t["asset"],
                                     "contract": t["contract"], "amount": t["amount"],
                                     "class": classify(t["asset"], t["contract"], cid, t.get("name", "")),
                                     "price_usd": None})
                    price_ids.append(f"{llama}:{t['contract']}" if llama else None)
            except Exception as e:
                errors.append(f"{CHAIN_META.get(cid, (cid,))[0]}: {type(e).__name__} {str(e)[:90]}")
    elif family == "btc":
        try:
            b = fetch_btc(addr)
            if b > 0:
                holdings.append({"chain": "Bitcoin", "asset": "BTC", "contract": "",
                                 "amount": b, "class": "native", "price_usd": None})
                price_ids.append("coingecko:bitcoin")
        except Exception as e:
            errors.append(f"Bitcoin: {type(e).__name__} {str(e)[:90]}")
    elif family == "tron":
        try:
            trx, toks = fetch_tron(addr)
            if TRON_SOURCE["mode"] == "trongrid":
                notes.append("⚠ Tron 数据来自 TronGrid 兜底：代币符号缺失、精度按 6 位估算，"
                             "数量可能失真。建议稍后重试 Tronscan 获取准确结果")
            if trx > 0:
                holdings.append({"chain": "Tron", "asset": "TRX", "contract": "",
                                 "amount": trx, "class": "native", "price_usd": None})
                price_ids.append("coingecko:tron")
            for t in toks:
                holdings.append({"chain": "Tron", "asset": t["asset"], "contract": t["contract"],
                                 "amount": t["amount"],
                                 "class": classify(t["asset"], t["contract"], "195", t.get("name", "")),
                                 "price_usd": None,
                                 "price_in_native": t.get("price_in_native")})
                price_ids.append(f"tron:{t['contract']}")
        except Exception as e:
            errors.append(f"Tron: {type(e).__name__} {str(e)[:90]}")
    elif family == "solana":
        try:
            lam, toks = fetch_solana(addr)
            if lam > 0:
                holdings.append({"chain": "Solana", "asset": "SOL", "contract": "",
                                 "amount": lam, "class": "native", "price_usd": None})
                price_ids.append("coingecko:solana")
            for t in toks:
                holdings.append({"chain": "Solana", "asset": t["asset"], "contract": t["contract"],
                                 "amount": t["amount"],
                                 "class": classify(t["asset"], t["contract"], "501", t.get("name", "")),
                                 "price_usd": None})
                price_ids.append(f"solana:{t['contract']}")
        except Exception as e:
            errors.append(f"Solana: {type(e).__name__} {str(e)[:90]}")
    else:
        errors.append(
            f"暂无可用的免费公开数据通道覆盖「{FAMILY_LABEL.get(family, family)}」地址。"
            "本技能仅使用无需凭证的公开只读接口，故该链族不在覆盖范围内；"
            "已覆盖：EVM 全链（含 BSC、Robinhood Chain）、Bitcoin、Tron、Solana。"
        )

    # 价格补齐
    resolve_prices(holdings, price_ids, args.price_file, notes, errors)

    rep = build_report(addr, source, holdings, notes, errors, args.cny, args.full_address)
    rep["detected_family"] = family
    emit(rep, args.out)


if __name__ == "__main__":
    main()
