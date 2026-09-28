#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pair_price.py — 交易对估值工具

只依赖公共 JSON-RPC（默认 BSC 官方 dataseed），不依赖任何需要 Key 的行情 API。
**只读**：全部调用为 eth_call / eth_getBalance。eth_call 是链上只读方法，
不会产生交易、不消耗 gas、不改变任何链上状态。

安全边界：
  * 输入只有「公开钱包地址」与「公开代币合约地址」，不含任何密钥信息。
  * 不签名、不发交易、不调用 approve。
  * 出口统一为用户指定的公共 RPC 节点，不向其他域名发送任何内容。

功能：
  1. 查地址原生币余额 + 指定 ERC-20 余额（eth_getBalance / eth_call balanceOf）
  2. 通过 DEX 交易对为任意代币定价（与主流钱包公开做法一致的估值链路）：
     a. V2 池：factory.getPair(token, QUOTE) → getReserves → price = R_quote / R_token
     b. V3 池：factory.getPool(token, QUOTE, fee) → slot0.sqrtPriceX96 → price
     c. 直连 USDT 无池时，经中间锚（如代币化股票 AAPLB）二跳换算：
        token → ANCHOR → USDT

用法：
  python pair_price.py <钱包地址> --token <合约> [--token ...] [--hop <锚代币合约>]
      [--rpc https://bsc-dataseed.bnbchain.org] [--quote 0x55d3...955] [--out report.json]

V2/V3 factory 默认取 BSC PancakeSwap，可用 --factory2/--factory3 覆盖其他链/DEX。
"""
import argparse, json, re, sys, urllib.request

V3_FEES = [100, 500, 2500, 10000]

# PancakeSwap (BSC) 默认
FACTORY_V2 = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
FACTORY_V3 = "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"
USDT_BSC   = "0x55d398326f99059fF775485246999027B3197955"
WBNB_BSC   = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"

# 地址格式校验：EVM 地址为 0x + 40 hex。形似私钥（64/128 hex）的输入一律拒收。
RE_EVM_ADDR = re.compile(r"0x[0-9a-fA-F]{40}")


def assert_public_address(value, label):
    """只接受公开账本地址。拒收形似私钥/种子的输入，避免误粘。"""
    v = (value or "").strip()
    if re.fullmatch(r"[0-9a-fA-F]{64}|[0-9a-fA-F]{128}", v):
        raise SystemExit(
            f"[拒绝] {label} 形似私钥/种子而非公开地址。\n"
            "本工具只接受公开账本地址，不处理任何私钥、助记词或种子短语。\n"
            "若确为私钥，请立即作废该钱包并转移资产。"
        )
    if not RE_EVM_ADDR.fullmatch(v):
        raise SystemExit(f"[拒绝] {label} 不是合法的 EVM 公开地址（应为 0x + 40 位十六进制）：{v[:16]}")
    return v


def assert_rpc_url(url):
    """出口约束：仅允许 http(s) 公共 RPC 节点，禁止其他 scheme。"""
    if not re.fullmatch(r"https?://[^\s]+", url or ""):
        raise SystemExit(f"[拒绝] RPC 端点必须是 http(s) URL：{url!r}")
    return url.rstrip("/")


SEL = {
    "balanceOf":   "70a08231",
    "decimals":    "313ce567",
    "symbol":      "95d89b41",
    "getReserves": "0902f1ac",
    "slot0":       "3850c7bd",
    "fee":         "ddca3f43",
    "token0":      "0dfe1681",
    "token1":      "d21220a7",
    "getPair_v2":  "e6a43905",   # getPair(address,address)
    "getPool_v3":  "1698ee82",   # getPool(address,address,uint24)
    "liquidity":   "1a686502",   # V3 pool liquidity() —— 空池鉴别用
}


class Chain:
    """极简只读 RPC 客户端。只实现 eth_call / eth_getBalance 两个只读方法。"""

    def __init__(self, rpc, timeout=15):
        self.rpc = assert_rpc_url(rpc)
        self.timeout = timeout

    def _rpc(self, method, params):
        # 白名单：本客户端只允许发起只读方法，写方法在此处即被拒绝。
        if method not in ("eth_call", "eth_getBalance"):
            raise RuntimeError(f"只读客户端不允许调用 {method}")
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": params}).encode()
        req = urllib.request.Request(self.rpc, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.loads(r.read().decode())
        if "error" in out:
            raise RuntimeError(out["error"].get("message", str(out["error"])))
        return out["result"]

    def call(self, to, data):
        return self._rpc("eth_call", [{"to": to, "data": "0x" + data}, "latest"])

    def balance(self, addr):
        return int(self._rpc("eth_getBalance", [addr, "latest"]), 16)


def pad(a):
    return a[2:].lower().rjust(64, "0")


def erc20(ch, token, sel, args=""):
    return ch.call(token, SEL[sel] + args)


def to_int(hexstr):
    return int(hexstr, 16)


def decimals_of(ch, token):
    try:
        return to_int(erc20(ch, token, "decimals"))
    except Exception:
        return 18


def v2_pair(ch, factory, a, b):
    try:
        p = ch.call(factory, SEL["getPair_v2"] + pad(a) + pad(b))
    except Exception:
        return None
    p = "0x" + p[-40:]
    return None if int(p, 16) == 0 else p


def v3_pool(ch, factory, a, b):
    for fee in V3_FEES:
        try:
            p = ch.call(factory, SEL["getPool_v3"] + pad(a) + pad(b) + pad(hex(fee)))
            p = "0x" + p[-40:]
            if int(p, 16) != 0:
                return p, fee
        except Exception:
            pass
    return None, None


def v2_price(ch, pool, base, qdec, bdec):
    """base 持仓代币的成交价（以 quote 计），由池内储备比给出。"""
    res = ch.call(pool, SEL["getReserves"])[2:]
    r0, r1 = int(res[0:64], 16), int(res[64:128], 16)
    t0 = "0x" + ch.call(pool, SEL["token0"])[-40:]
    r_base, r_quote = (r0, r1) if t0.lower() == base.lower() else (r1, r0)
    if r_base == 0:
        return None, 0.0
    price_native = (r_quote / 10 ** qdec) / (r_base / 10 ** bdec)
    return price_native, r_quote / 10 ** qdec   # (单价, quote 侧池深，上层据此判断死池)


def v3_price(ch, pool, base, qdec, bdec):
    """V3 池报价。返回 (单价, 诊断信息) 或 (None, 原因)。

    **空池鉴别**：getPool 返回非零 + slot0 有正常 sqrtPriceX96，并不代表池内有资金。
    实测踩坑：某 V3 池 liquidity()=0、两侧余额≈0，却报出比有效池高 21 倍的价格。
    因此这里强制读 liquidity()，为 0 即判定空池并放弃该报价。
    """
    try:
        liq = int(ch.call(pool, SEL["liquidity"]), 16)
    except Exception:
        liq = None
    if liq == 0:
        return None, "空池（liquidity=0），报价作废"

    s0 = ch.call(pool, SEL["slot0"])[2:]
    sqrt = int(s0[0:64], 16)
    if sqrt == 0:
        return None, "slot0.sqrtPriceX96=0"
    t0 = "0x" + ch.call(pool, SEL["token0"])[-40:]
    raw = (sqrt / 2 ** 96) ** 2
    if t0.lower() == base.lower():
        return raw * 10 ** (bdec - qdec), f"liquidity={liq}"
    return (1 / raw) * 10 ** (bdec - qdec), f"liquidity={liq}"


def price_via_pair(ch, base, quote, qdec, factories):
    """依次尝试 V2 工厂与 V3 工厂。返回 (单价, 描述) 或 (None, None)。"""
    bdec = decimals_of(ch, base)
    for f in factories[:1]:
        p = v2_pair(ch, f, base, quote)
        if p:
            v = v2_price(ch, p, base, qdec, bdec)
            if v and v[0]:
                depth = v[1]
                note = f"V2池 {p}（储备比，池深≈{depth:,.2f} quote）"
                if depth < 1000:
                    note += " ⚠ 池深<1000，参考价值低"
                return v[0], note
    for f in factories:
        p, fee = v3_pool(ch, f, base, quote)
        if p:
            v, diag = v3_price(ch, p, base, qdec, bdec)
            if v:
                return v, f"V3池 {p}（fee={fee}, sqrtPriceX96, {diag}）"
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("address")
    ap.add_argument("--token", action="append", default=[], help="ERC-20 合约，可多次")
    ap.add_argument("--hop", default=None,
                    help="中间锚代币合约（直接对 USDT 无池时二跳，如代币化股票 AAPLB）")
    ap.add_argument("--rpc", default="https://bsc-dataseed.bnbchain.org")
    ap.add_argument("--quote", default=USDT_BSC, help="最终计价代币（默认 BSC USDT）")
    ap.add_argument("--quote-price", type=float, default=1.0,
                    help="quote 的美元价（USDT=1；若 quote=WBNB 需注入 BNB 价）")
    ap.add_argument("--factory2", default=FACTORY_V2)
    ap.add_argument("--factory3", default=FACTORY_V3)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    # 输入校验前置：只接受公开地址，拒收形似密钥的输入。
    addr = assert_public_address(args.address, "钱包地址")
    for t in args.token:
        assert_public_address(t, "代币合约")
    if args.hop:
        assert_public_address(args.hop, "锚代币合约")
    for f in (args.factory2, args.factory3, args.quote):
        assert_public_address(f, "合约地址")

    ch = Chain(args.rpc)
    factories = [args.factory2, args.factory3]
    qdec = decimals_of(ch, args.quote)
    rep = {
        "address": addr,
        "rpc": ch.rpc,
        "assets": [],
        "notes": [
            "只读查询：仅使用 eth_call / eth_getBalance，不签名、不发交易。",
            "报价为池内瞬时理论价，薄池代币的实际可成交价值可能显著低于账面值。",
        ],
        "disclaimer": "链上公开数据只读聚合结果，非本人资产证明，不构成投资建议。",
    }

    nat = ch.balance(addr)
    rep["assets"].append({"asset": "native(gas)", "amount": nat / 1e18,
                          "price_source": "外部注入", "price_usd": None})

    for t in args.token:
        dec = decimals_of(ch, t)
        raw = int(erc20(ch, t, "balanceOf", pad(addr)), 16)
        amount = raw / 10 ** dec
        entry = {"asset": t, "amount": amount, "decimals": dec}
        price, how = price_via_pair(ch, t, args.quote, qdec, factories)
        if price is None and args.hop:
            p1, h1 = price_via_pair(ch, t, args.hop, 18, factories)
            p2, h2 = price_via_pair(ch, args.hop, args.quote, qdec, factories)
            if p1 and p2:
                price = p1 * p2
                how = f"二跳：{t}→锚 {args.hop} [{h1}] →USDT [{h2}]"
        if price is not None:
            entry["price_usd"] = price * args.quote_price
            entry["price_source"] = how
            entry["value_usd"] = amount * entry["price_usd"]
        else:
            entry["price_usd"] = None
            entry["price_source"] = "未找到有效交易对（含空池/死池判定），未定价"
        rep["assets"].append(entry)

    total = sum(a.get("value_usd", 0) for a in rep["assets"])
    rep["total_value_usd"] = round(total, 2)
    rep["notes"].append("gas 币价格未注入时不计入总额；为完整估值请配合公开行情源补 native 价。")

    text = json.dumps(rep, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()
