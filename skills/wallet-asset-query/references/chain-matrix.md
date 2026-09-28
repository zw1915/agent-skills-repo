# 全链覆盖矩阵

本技能的链覆盖由两条通道叠加而成。**判断某条链能否查到，先看这张表。**

## 1. 覆盖范围说明（V3.1 起）

本技能的链覆盖**完全由无密钥公开接口决定**，不存在任何需要凭证的增强通道。可查范围见第 2 节；不在其中的链族一律如实声明为"未覆盖"，不得引导用户去申请 API Key。

## 2. 无密钥公开接口覆盖

| 链族 | 端点 | 覆盖面 |
|---|---|---|
| EVM | Blockscout v2 公共实例 | eth / optimism / gnosis / base / polygon / arbitrum / zksync / unichain / celo（avalanche/scroll/linea/mantle/bsc 实例不存在） |
| **BSC** | `bsc-dataseed.bnbchain.org`（POST JSON-RPC，2026-09-14 实测脚本可直连） | 原生币 + 已知合约 balanceOf + 池子 getReserves/slot0（无代币枚举） |
| **Robinhood Chain** | `robinhoodchain.blockscout.com/api/v2`（chain 4663，gas=ETH） | 原生币 + ERC-20 列表（标准 Blockscout） |
| BTC | `blockstream.info/api` | 余额（UTXO 汇总） |
| Tron | `api.trongrid.io` | TRX + TRC-20 |
| Solana | `api.mainnet-beta.solana.com` | SOL + SPL（`getTokenAccountsByOwner`） |

**未覆盖**：TON、SUI、Cosmos、XRP、Dogecoin、Litecoin、Polkadot 及其他长尾链——它们缺少免费公开数据通道，须如实告知用户，不得编造数据、也不得引导用户申请凭证。

## 2.5 价格兜底：交易对直算（V2.0 新增）

长尾代币（meme/新币/股票池锚定币）聚合器常无收录。定价链：

```
Blockscout exchange_rate（内联，最省调用）
  → DexScreener latest/dex/tokens/{合约}（含全部池 + liquidity.usd）
    → 链上直算 scripts/pair_price.py（V2 储备比 / V3 sqrtPriceX96 / 多跳）
```

常用锚（BSC）：USDT `0x55d3…955`、WBNB `0xbb4C…95c`、**AAPLB 代币化苹果股 `0x431a3BEE82E2ca41e49895CbECE5bB0F76A89b7A`**（当前 meme 币主力计价锚）。
Pancake V2 factory `0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73`；V3 factory `0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865`（fee 档 100/500/2500/10000 逐档枚举）。方法学详见 SKILL.md 第 5 步。

## 3. RPC 直连可能性（尽力而为）

部分链的 JSON-RPC 节点在国内网络下偶可直连。EVM 链可用 `eth_getBalance`（原生币）与 `eth_call` + `balanceOf`（已知合约的代币），但**无法枚举代币列表**，仅适合已知持仓的定点核实，不适合全量盘点。

## 4. 通道选择决策

```
地址已校验为公开地址（非密钥形态）
   ├─ 链族属 EVM/BTC/Tron/Solana ──→ 无密钥公开接口（默认路径，不需要任何凭证）
   │                                  ├─ 脚本出口可达 ──→ 直接取数
   │                                  └─ 脚本出口被阻断 → 助手抓取通道两段式
   └─ 链族属 TON/SUI/Cosmos 等 ────→ 如实告知"未覆盖"，不编造数据、不引导申请凭证
```

> **出口约束（重要）**：出口域名在代码中静态写死，CLI 无任何主机参数。**不得自行引入未列出的第三方域名，更不得将任何凭证发往任何主机。**

