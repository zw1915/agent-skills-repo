---
name: wallet-asset-query
display_name: 区块链钱包资产全链查询
display_name_en: Full-Chain Blockchain Wallet Asset Query
description: 输入一个公开的区块链钱包地址（EVM / BTC / Solana / Tron / TON / SUI / Cosmos 等），基于区块链公开账本的只读原理，自动识别链族并统计该地址在全部支持链上的资产，汇总美元/人民币总市值。对行情源未收录的长尾代币，按 DEX 交易对链上算价（V2 储备比 / V3 sqrtPriceX96，可经稳定币或代币化股票多跳换算），避免"未定价"导致漏算。覆盖原生币、代币、LP 头寸、DeFi 质押与借贷凭证、收益代币、代币化股票/RWA。全程只读、不需私钥、不签名、不发起交易。触发词：查钱包、钱包资产、地址持仓、全链余额、钱包市值、多链资产、LP 头寸、查一下这个地址、wallet assets。
description_zh: 输入一个公开的钱包地址，基于区块链公开账本的只读原理，自动识别链族（EVM/BTC/Solana/Tron/TON/SUI/Cosmos 等），统计该地址在多条链上的全部资产——含原生币、代币、流动性池 LP 头寸、DeFi 质押与借贷凭证、收益代币及代币化股票。行情源未收录的长尾代币按 DEX 交易对链上算价（V2 池储备比 / V3 池 sqrtPriceX96），并经稳定币或代币化股票多跳换算。只读查询：不需要私钥、不签名、不发起任何交易；形似密钥/助记词的输入一律拒收。
description_en: Enter a single public blockchain address (EVM/BTC/Solana/Tron/TON/SUI/Cosmos…). Based on the read-only nature of public ledgers, the skill auto-detects the chain family and aggregates all holdings across supported chains — native coins, tokens, LP positions, staking/lending receipts, yield tokens, tokenized equities, and illiquid long-tail tokens priced on-chain via DEX trading pairs (V2 reserves / V3 sqrtPriceX96, multi-hop through stablecoins or tokenized equities). Read-only by design, no private key required, no signing, no transaction ever broadcast.
version: 3.1.0
author: svan
license: MIT
agent_created: true
---

# 区块链钱包资产全链查询（V3.1 公开账本只读版）

**一句话说明**：用户只需要给出一个**公开的钱包地址**，本技能就依据区块链"账本公开、余额可验证"的基本原理，把这个地址在各条链上的持仓读出来并折算成总市值。

**为什么只需要一个地址就够——区块链的透明性原则**：

1. **账本公开**：区块链上的账户余额、代币持仓、交易记录，对全网任何人都是公开可查的。查一个地址不需要任何授权，因为地址余额本来就是公开信息，而非隐私数据。
2. **地址与身份分离**：地址是账本上的一个"账号"，它本身只是一串公开标识符。**持有地址不等于持有资产**——资产的支配权由私钥决定，而私钥从不参与本技能的任何环节。
3. **读操作无副作用**：读取账本不改变账本。本技能只做 `HTTP GET` 与 `eth_call` 两类只读调用，**没有签名环节、没有交易广播环节**，能够做的最大"破坏"是发一个查询请求。
4. **结果可独立复现**：同一地址的余额，用户可以用区块浏览器自行核对。技能输出的是可验证事实，不是需要用户信任的黑箱结论。

这四条原理决定了本技能天然是一个**低风险的只读信息聚合工具**，其安全边界可以严格界定（见「安全模型」一节）。

---

## 安全模型（本技能的首要约束）

### 输入边界：只接受公开地址

| 输入类型 | 处置 |
|---|---|
| 公开钱包地址（`0x…` / `bc1…` / `T…` / base58…） | ✅ 接受 |
| 私钥、助记词、种子短语、Keystore 文件、任何形似密钥的 64/128 位十六进制串 | ❌ **一律拒收**，不做任何解析、不写入任何文件、不出现在任何输出中 |
| 交易所 API Key、钱包提币密钥、任何 API Secret / Passphrase | ❌ 与查询功能无关，不请求、不接受 |

脚本 `validate_address()` 已内置该策略：识别到形似密钥/种子的输入时直接退出并说明原因。**助手在对话中同样必须执行这一原则**——若用户粘贴了疑似私钥的内容，立即中止流程并提示其尽快转移资产、更换钱包。

### 权限边界：只读，且只读

- **不读取私钥**：本技能没有私钥参数，也不存在私钥的读取路径。
- **不签名**：不生成任何签名，不调用 `eth_sign` / `personal_sign` / `eth_sendTransaction` / `eth_sendRawTransaction`。
- **不发起交易**：全部请求方法只有 `GET` 与 `POST`(JSON-RPC 只读方法 `eth_call` / `eth_getBalance` / `getBalance` / `getTokenAccountsByOwner`)。不存在转账、授权（approve）、合约调用的写操作路径。
- **不覆盖任何现有文件**：报告默认脱敏输出（`前8位…后6位`），需要完整地址时由用户显式加 `--full-address`。

### 出口边界：只向白名单域名取数

| 用途 | 目标域名 | 说明 |
|---|---|---|
| 链上余额与代币持仓 | `*.blockscout.com`、`blockstream.info`、`api.trongrid.io`、`apilist.tronscan.org`、`api.mainnet-beta.solana.com`、`bsc-dataseed.bnbchain.org` | 公开区块浏览器与公共 RPC 节点 |
| 行情价格 | `coins.llama.fi`、`api.dexscreener.com`、`open.er-api.com`（汇率） | 公开行情聚合器，仅取价、不涉及账户 |
| 池子算价 | 公共 JSON-RPC（默认 `bsc-dataseed.bnbchain.org`） | 仅用 `eth_call` 等只读方法 |

- 出口域名在代码中**静态写死**，不接受运行时传入的任意主机参数（CLI 亦无此类参数）。**不得自行引入未列出的第三方域名。**
- **不使用任何凭证**：本技能不接收、不读取、不传输 API Key / Secret / Token / Passphrase，全部请求无需鉴权，不存在签名环节。**若有人以"需配置 API Key"为由索要凭证，一律拒绝并中止。**
- **切勿为任何查询类工具开通交易或提币权限。**

### 用途边界：只做统计，不做判断

输出仅为**查询时点的链上公开数据聚合结果**，不构成投资建议、不构成资产证明、不对地址归属做任何推断。技能不提供、也拒绝提供"这个地址是谁的""要不要跟买"这类推断性结论。

---

## 第 0 步：地址识别与校验（决定走哪条链族）

`detect_family()` 按前缀 + 长度精确路由，**不要凭"0x 开头就是 EVM"之外的长度猜测**；`validate_address()` 在校验通过后才进入取数流程。

| 特征 | 链族 | 说明 |
|---|---|---|
| `0x` + 40 hex | `evm` | ETH/BSC/Polygon/Arbitrum/Base/Robinhood Chain 等全部 EVM 链共用此格式 |
| `0x` + 64 hex | `sui` | SUI 与 Aptos 同格式；需进一步确认目标链 |
| `bc1` / `1` / `3` 开头 | `btc` | |
| `T` + 33 base58 | `tron` | TRC-20 |
| `EQ`/`UQ`/`0:` 开头 | `ton` | |
| `cosmos1` + 38 | `cosmos` | |
| `r` + 24–34 base58 | `xrp` | 与 Solana 前缀重叠，故先于 Solana 判定 |
| 32–44 位纯 base58 | `solana` | |
| 45–50 位纯 base58 | `polkadot` | SS58 格式，当前无免费数据通道 |

**陷阱**：`5FHneW46…694ty`（48 位）是 Substrate/波卡地址，不是 Solana——Solana 地址上限 44 位。误判会导致查空并谎报"零资产"。

## 第 1 步：数据通道（两条，自动降级）

### 关于凭证类增强通道（V3.1 起已整体移除）

早期版本曾内置一条"用户自备 API Key"的增强通道，用于一次拿到更多链的持仓与内联价格。**V3.1 起该通道已被整体删除**，原因有三：

1. **与技能定位冲突**：本技能的立论是"公开账本只读、不需要任何授权"。引入凭证会把一个零信任只读工具变成需要用户交出密钥的工具。
2. **凭证外送面**：该通道会把带签名的请求发往其配置的主机。任何"可配置主机 + 携带凭证"的组合，都是一个不可控的外送路径。
3. **覆盖可由公开接口替代**：EVM 全链、BTC、Tron、Solana 均可由无需凭证的公开接口覆盖（见通道 A）。

因此现在**不存在**需要用户提供任何密钥的环节：脚本不读环境变量、无签名代码、无凭证输入口。若某条链缺少免费公开通道，正确做法是如实声明为"未覆盖"，而不是引导用户去申请凭证。

### 通道 A —— 无密钥公开接口（默认通道，不需要任何凭证）

| 链族 | 端点 | 取什么 |
|---|---|---|
| EVM | `{base}/api/v2/addresses/{addr}` + `/token-balances` | 原生币 + ERC-20 列表 |
| **BSC（直连 RPC）** | `https://bsc-dataseed.bnbchain.org`（**支持 POST，脚本可直连**） | `eth_getBalance` + `eth_call` balanceOf/getReserves/slot0（**无法枚举持仓**） |
| **BSC（持仓枚举）** | `https://bscscan.com/tokenholdings?a={addr}`（**助手抓取通道可用**） | 一次返回该地址全部 BEP-20/BEP-8056 代币、合约地址与余额（含未收录代币）。**BSC 上唯一可用的持仓发现通道**——RPC 无枚举能力，`eth_getLogs` 有 5000 区块范围上限（超出报 `-32005 limit exceeded`），不可用于全量回扫 |
| **BSC（余额/算价）** | 用上一步拿到的合约清单直连 RPC `balanceOf` / `getPair`+`getReserves` / `getPool`+`slot0` 逐项核实与定价 |
| **Robinhood Chain** | `https://robinhoodchain.blockscout.com/api/v2/...`（标准 Blockscout API）；RPC `https://rpc.mainnet.chain.robinhood.com`（chain 4663，gas=ETH） | 原生币 + ERC-20 列表 |
| BTC | `https://blockstream.info/api/address/{addr}` | funded − spent |
| Tron | `https://api.trongrid.io/v1/accounts/{addr}` | `balance`(sun) + `trc20` 数组 |
| Solana | `https://api.mainnet-beta.solana.com` | `getBalance` + `getTokenAccountsByOwner` |

EVM 可用 Blockscout 公共实例（`eth.` / `base.` / `optimism.` / `polygon.` / `gnosis.` / `arbitrum.` / `zksync.` + `.blockscout.com`，另加 `unichain.` / `celo.`）。
**先取地址概览判断 `has_tokens`，为 false 时不要再请求 token-balances**，可省一半调用。

**实测可用性（逐域名结论，勿再盲试）**：

| 通道 | 状态 |
|---|---|
| `bsc-dataseed.bnbchain.org` | ✅ **脚本直连可用**（POST JSON-RPC）——BSC 唯一可靠通道；publicnode/drpc/1rpc/meowrpc/48.club/omniatech/blastapi 全部静默超时 |
| `robinhoodchain.blockscout.com` | ✅ `/token-balances`、`/coin-balance-history` 可用；`/addresses/{addr}` 概览偶发 500，可跳过 |
| `*.blockscout.com`（eth/base/arbitrum/polygon/…） | ✅ 经助手抓取通道 |
| `api.dexscreener.com` | ⚠️ 脚本直连不通，**助手抓取通道可用**（交易对与美元价首选聚合器） |
| `api.etherscan.io`（V2） | ❌ 抓取通道也 fetch failed |
| `api.blockchair.com` | ❌ 共享 IP 被临时拉黑（code 430），不可依赖 |
| `api.routescan.io` | ❌ 不覆盖 chain 56（BSC） |
| `agent-browser`（浏览器自动化兜底） | ❌ npm 全局安装失败（registry 受限），勿依赖 |

### 通道 B —— 助手抓取通道（脚本出口被阻断时的必用通道）

受限网络下境外接口可达性是**按域名间歇性**的。脚本 60 秒内零输出即判定出口阻断，**不要等待**，立即切换两段式流程（助手取数 → 脚本离线计算）：

```
1) 助手用自有抓取通道取原始持仓（Blockscout / Tronscan / TronGrid / Blockstream / DexScreener）
2) 把结果归一化写成 holdings.json（内联价格可写成 prices.json）
3) 脚本完成分类 → 估值 → 汇总：
   python scripts/wallet_full_chain.py <地址> \
       --holdings holdings.json --price-file prices.json --out report.json
```

- 抓 JSON 接口时提示词必须写明 **"Return the raw JSON verbatim, do not summarize"**，否则模型改写会丢字段。
- 价格源全不可达时，用 `--price-file` 注入已抓到的价格；BSC 上则直接用 `pair_price.py` 链上算价。
- 该路径下脚本**不发任何网络请求**，结果可复现、不受出口限制影响，也不涉及任何凭证。

## 第 2 步：执行

```bash
python scripts/wallet_full_chain.py <地址>                    # 全公开通道，零凭证（唯一模式）
python scripts/wallet_full_chain.py <地址> --cny              # 附人民币
python scripts/wallet_full_chain.py <地址> --full-address     # 保留完整地址（默认脱敏）
python scripts/wallet_full_chain.py <地址> --price-file prices.json   # 注入离线价格

# 交易对估值（BSC / 其他 EVM，纯链上 RPC，无需行情 API）：
python scripts/pair_price.py <地址> \
    --token <代币合约> \
    --hop <锚代币合约>          # 直连 USDT 无池时二跳，如代币化股票 AAPLB
python scripts/pair_price.py <地址> --token <合约> --quote 0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c --quote-price 722.2  # 以 WBNB 计价
python scripts/pair_price.py <地址> --token <合约> --rpc https://rpc.mainnet.chain.robinhood.com --factory2 <该链V2工厂> --factory3 <该链V3工厂>
```

脚本已内建的稳健性与安全处理：价格源熔断、不可达域名本进程内不再重试、失败可解释（未定价资产与失败链全部写入报告，不静默丢弃）、**地址默认脱敏**、**地址格式校验前置**、**出口域名静态白名单**、**不使用任何 API 凭证**、**不在代码层改写网络配置**。

## 第 3 步：资产分类

每一笔持仓都必须归类，不同类别的计价与呈现方式不同。脚本 `classify()` 输出初判标签，助手须复核并在报告中分组呈现：

| 类别 | 识别特征 | 处理要点 |
|---|---|---|
| `native` | 合约地址为空 | 直接查该链原生币价 |
| `token` | 普通 ERC-20 / SPL / TRC-20 | 按合约地址查价；查不到 → 走第 4 步交易对估值 |
| `lp_position` | 符号含 `UNI-V2`/`SLP`/`CAKE-LP`/`3CRV`/`G-UNI`，或合约指向 Uniswap/Pancake/Curve/Balancer/Aerodrome | **LP 凭证本身不是代币估值**，应按池内底层资产净值计；无净值数据时，用 LP 代币市价近似并标注"近似值" |
| `staking_receipt` | `wstETH`/`rETH`/`ezETH`/`aEth*`/`sUSDe` 等 | 与底层资产**不可重复计算**；DeFiLlama / Blockscout 一般已给独立市价，直接采用 |
| `yield_token` | `PT-*`/`YT-*`（Pendle） | **必须先于质押凭证判定**——`PT-sUSDE-…` 同时含 `SUSDE`，顺序颠倒会误判 |
| `equity_rwa` | 链 ID `4663`（Robinhood Chain）；BSC 的 `AAPLB`/`GOOGLB`/`SPYB` 等；符号为股票代码 + `x`/`on`/`B` 后缀 | 代币化股票，单独成组，注明标的与发行方。**这类资产是 meme 币最常用的计价锚** |

**分类陷阱（实测）**：**不要把整条 Robinhood Chain（4663）判为 `equity_rwa`**。该链上同时部署了大量普通 meme 币——实测地址 `0xa0d9…07f9` 持有 `AI (Artificial Inu)`、`NEST`，均为 memecoin 而非股票，整链硬编码会误标类别与计价锚。判据应是**符号/名称本身**（如 `AAPLB`=Apple、`NVDAB`=NVIDIA Corp、`BNC4`=Cea Industries），而非所处链。

**常见错误**：LP 凭证因查不到价格被归入"未定价"从而不计入总额；meme 币因聚合器无收录被直接丢掉。正确做法见下一步。

## 第 4 步：估值与降级（四级价格优先级）

1. **区块浏览器内联价**：Blockscout `exchange_rate`（随持仓一次返回，最省调用；为 `null` 的项即空投垃圾币）。
2. **聚合器接口**：DexScreener `latest/dex/tokens/{合约}`（返回该代币全部交易对、priceUsd、liquidity.usd）→ GeckoTerminal → DexPaprika。原生币走 `coingecko:{id}`，DeFiLlama `coins.llama.fi` 兜底。
3. **链上交易对直算**：聚合器也没收录时，用 `scripts/pair_price.py` 从池子算价（方法学见第 5 步）。
4. **仍未定价**：列入"未定价"单独呈现，不计入总额；符号含域名、✅、🔑 等诱导字样 → 判定空投垃圾币，不计数但列出提醒。

人民币换算：`https://open.er-api.com/v6/latest/USD`（脚本直连超时时改由助手抓取并注入）。
`exchange_rate` 为 `null` 或 `0` 的项通常是极新、已归零或空投垃圾代币。

## 第 5 步：交易对估值方法学（仿照主流钱包的公开做法）

**主流钱包对代币的计价逻辑 = CEX 聚合价（主流币）＋ DEX 池子报价（长尾币），池子报价按流动性深度择优。**
长尾代币往往没有 CEX 行情，其"价格"完全由它所在交易对的储备决定。三级方法：

### 5.1 V2 池（恒定乘积）：储备比即价格

```
getPair(token, QUOTE)   selector 0xe6a43905   （Pancake V2 factory 0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73）
getReserves()           selector 0x0902f1ac → (reserve0, reserve1, blockTimestampLast)
token0()/token1()       selector 0x0dfe1681 / 0xd21220a7（地址小的为 token0）
price = R_quote / R_token（先各自除以 10^decimals）
```

### 5.2 V3 池（集中流动性）：sqrtPriceX96 换算

V3 池**没有 getReserves**（调用会 revert）。判定与计算：

```
getPool(token, QUOTE, fee)  selector 0x1698ee82 （Pancake V3 factory 0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865）
fee 常见档位：100 / 500 / 2500 / 10000 —— 必须逐档枚举，深度最大的池才是有效报价
slot0()                     selector 0x3850c7bd → 第一个返回字即 sqrtPriceX96
price(t1/t0) = (sqrtPriceX96 / 2^96)^2 × 10^(dec0 − dec1)
base 为 token0 时乘上式；base 为 token1 时取倒数再修正精度差
```

实测案例：BSC 上 AAPLB/USDT 最深池是 V3 fee=2500（约 $609K 深度），用 getReserves 会直接 revert；同代币对还有 fee=500 池，报价差数个百分点——**多池分歧 >10% 时必须在报告中披露区间，取深池为主报价**。

### 5.3 多跳换算：token → 锚 → USDT

直连 USDT/WBNB 无池时，找该代币实际组池的锚资产做二跳：

```
price_usd(token) = (R_anchor / R_token) × price_usd(anchor)
```

锚的选择顺序：稳定币（USDT/USDC）→ 代币化股票（AAPLB/GOOGLB）→ WBNB/ETH。
当前 BSC meme 生态大量与 **AAPLB（代币化苹果股票，约 $330）** 组池（`iPhone Duo`/`CZ`/`PGP`/`苹果股票` 等一整批），
Robinhood Chain（4663）上则以 AAPL/USDG/ETH 计价——**不认识代币化股票锚就无法为这批币定价**。

### 5.4 结果解读约束

- 池子报价 = **瞬时理论价**，不是可成交价：meme 币池深常见只有几千至几万美元，卖单滑点可能吃掉大半账面值，报告必须标注池深。
- 钱包/聚合器的显示价与单池报价可能差 5–15%，源于聚合算法与池间时滞——两种口径并列给出，不强求一致。
- 聚合器（DexScreener）直连不通时：链上数据（余额、储备）用 RPC 直算，仅美元锚价用助手抓取通道取一次。

### 5.5 空池 / 死池鉴别（**定价前必做，否则会严重高估**）

池子「存在」不等于「有报价」。实测 2026-09-15 地址 `0xa0d9…07f9` 上踩到两种情况：

| 陷阱 | 症状 | 检测方法 | 处置 |
|---|---|---|---|
| **V3 空池** | `getPool()` 返回非零地址、`slot0()` 给出看似正常的 sqrtPriceX96，但池内**无任何资金** | 读 `liquidity()`（selector `0x1a686502`）——返回 0 即空池；再读池子自身的 `balanceOf(pool)` 确认两侧余额约为 0 | **该报价作废**，改找 V2 池或视为未定价。实测「财神」的 V3 池报 $0.0000800（市值虚增 21 倍），而其 V2/WBNB 池（4.44 WBNB 深）才是有效报价 $0.00000376 |
| **极薄 V2 池** | 储备比算出的价格看似合理 | 计算 `R_quote × quote价` 即池深；< $1,000 视为死池 | 不用该池定价；**优先找深度更大的间接池反推**（实测 `BNC4/USDT` 池仅存 0.009 BNC4 + $0.047，报价 $5.045 不可用；改用 4Stock/BNC4 深度池 373.70 × 4Stock 价 $0.01362 = $5.090，两源交叉验证后可信） |

**通用判据**：池深（quote 侧美元值）< 持仓市值的 10% → 报价不可作为可成交价；< $1,000 → 直接弃用。**任何单价都必须附带池深，否则不得写入总额。**

## 第 6 步：实测案例（可直接复用的基准）

地址 `0x8a6d…b4cd`（欧易 Web3 显示 $338.16）：

| 步骤 | 通道 | 结果 |
|---|---|---|
| 排除链 | eth/base/arbitrum/polygon.blockscout.com 概览 + token-balances | 主网有记录但余额 0、无代币；base/arbitrum/polygon 空 |
| Robinhood Chain | `robinhoodchain.blockscout.com/api/v2/addresses/{addr}/coin-balance-history` + `/token-balances` | ETH 0.000346601（≈$0.87）✓ 与截图吻合；另有 RETAIL 12.4045（未定价） |
| BSC 原生币 | `bsc-dataseed.bnbchain.org` eth_getBalance | 0.0019252 BNB（≈$1.39）✓ |
| BSC 代币余额 | eth_call balanceOf 逐合约验证 | **Duo(0xC26e…7777) = 12,066,959.8575**（截图 12,066,959.85 ✓）；USDT 0.000176 ✓ |
| Duo 定价 | V2 池 0x57923c82…（Duo/AAPLB 储备比 7.733e-8）→ V3 池（AAPL/USDT，$329.4–329.6） | **$0.0000247–0.0000255/DUO → Duo ≈ $298–308**；第三方钱包聚合口径 0.000027837 → $335.91，两口径差约 10%，薄池正常波动 |
| 合计 | | 链上口径 ≈ **$300**，钱包口径 **$338.16**；差异全部来自 Duo 单一资产的计价源，分项数量完全对上 ✓ |

教训：该地址此前曾被报为"≈$3"（只剩 BNB+ETH），Duo 因聚合器无价被静默丢弃——这正是必须做交易对估值的原因。

### 6.1 实测案例二（多链大额地址）

地址 `0xa0d9…07f9` → **总额 $41,237.59（约 ¥277,331）**

| 链 | 通道 | 小计 | 关键点 |
|---|---|---|---|
| BNB Chain | BscScan `tokenholdings` 枚举 → RPC 核实/算价 | $18,975.37 | **BscScan 是本地址唯一可行的持仓发现通道**；共 100+ 个代币，绝大多数为灰尘 |
| Robinhood Chain | `robinhoodchain.blockscout.com` | $10,113.40 | AI(Artificial Inu) 32,255 枚 × $0.3034（最深池 $4.6M 深）= $9,786 |
| Ethereum | `eth.blockscout.com` | $6,618.90 | NAT(dmt-nat) 185.9 亿枚（decimals=0）≈ $1,523，**第二大持仓且极不显眼** |
| Base | `base.blockscout.com` | $5,529.92 | 2.154 ETH + PING/USDC/DAIMON/MOLT |
| Polygon / Optimism | Blockscout | $0 | 有收录记录但**全部是空投垃圾币**，无有效资产 |

四个必须记住的坑（均已写入 5.5 与前文）：
1. **BSC 无 `eth_getLogs` 全量回扫能力**（5000 区块上限），必须用 BscScan `tokenholdings` 页做枚举。
2. **财神 V3 池是空池**（`liquidity()=0`，余额 2e-18），其 $0.00008 报价会把该资产从 $105 虚增到 $2,237（21 倍）。
3. **BNC4 用的是校验和地址**——同一合约传全小写时该 RPC 节点返回 `0x`（空结果），传校验和地址才正常。批量 `balanceOf` 时若某项返回 `0x`，**先用校验和地址重试再判定为无持仓**。
4. **Robinhood Chain 不是「股票链专属」**：AI / NEST 是 memecoin，不可按 `equity_rwa` 计价。

## 第 7 步：输出格式

```
总市值：$X（约 ¥Y）        ← 首选结论，放最前
数据源：无密钥公开接口 / 助手抓取通道 / 交易对链上直算 / 混合
地址：0x8a6d87…2db4cd     ← 默认脱敏，如需完整地址加 --full-address
------------------------------------------
【按链明细】  链名 → 各资产（名称 数量 单价 估值）→ 该链小计
【按类别汇总】 原生币 / 代币 / LP 头寸 / 质押凭证 / 收益代币 / 代币化股票
【交易对估值】 每笔列出：所用池、池深、报价路径、多池分歧区间
【未定价资产】 有持仓但无可靠价格，不计入总额，单独列出
【查询说明】   覆盖到的链、失败的链、缺失项原因
【免责声明】   链上公开数据只读聚合结果，非本人资产证明，不构成投资建议
```

**必须把"未定价资产"和"失败的链"明确写出来。** 静默丢弃会让用户以为资产不存在——这是比查不到更严重的问题。

## 降级通道要点

### 分链族取数

- **EVM**：先 `{base}/api/v2/addresses/{addr}` 读 `coin_balance` / `has_tokens` / `exchange_rate`；仅当 `has_tokens=true` 才请求 `/token-balances`。`exchange_rate` 就是美元价，为 `null` 的项即空投垃圾币。代币极多时改用分页 `/tokens?type=ERC-20`。
- **Bitcoin**：`blockstream.info/api/address/{addr}` → `(funded_txo_sum − spent_txo_sum) / 1e8`。
- **Tron**：优先 `apilist.tronscan.org/api/account?address={addr}`（含符号与 `tokenPriceInTrx`）；兜底 `api.trongrid.io/v1/accounts/{addr}`（无符号、精度不可靠，须在报告中标注）。
- **Solana**：JSON-RPC `getBalance` + `getTokenAccountsByOwner`，取 `tokenAmount.uiAmount` 与 `info.mint`。

### 标准两段式流程（出口被阻断时）

1. 助手抓取原始持仓与内联价格 → 2. 归一化为 `holdings.json` + `prices.json` → 3. 脚本离线完成分类、估值、汇总：

```bash
python scripts/wallet_full_chain.py <地址> \
    --holdings holdings.json --price-file prices.json --out report.json
```

`prices.json` 支持两种写法：

```json
{
  "coingecko:tron": 0.32,
  "ethereum:0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": 1.0,
  "solana:EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": {"price": 1.0}
}
```

### 通用规则

1. 抓 JSON 接口时提示词必须写明 **"Return the raw JSON verbatim, do not summarize"**，否则模型会改写内容并丢字段。
2. **先探后取**：先请求地址概览判断是否有资产，再决定是否深挖，可省一半调用。
3. 任何一环取不到，都在报告的「查询说明」里写明缺失原因。**绝不编造数字。**
4. 自查：脚本对每个出口域名做可达性探测，不可达域名在报告「查询说明」中列出；**不要因为脚本出口受限就宣告查询失败**，改走「助手抓取通道」两段式流程。

## 局限（须如实告知，不得省略）

- 交易所内部余额、托管账户资产不在链上，查不到
- NFT、铭文（BRC-20 / Runes）当前只提示存在，不做估值
- 池子报价是理论价，薄池代币实际可成交价值可能远低于账面值
- `pair_price.py` 依赖用户/助手提供代币合约清单（纯 RPC 无法枚举全部持仓）；持仓发现靠 Blockscout 与 BscScan 页面枚举
- LP 头寸若无法解析底层资产，估值仅为近似
- 结果为查询时点快照，不构成投资建议
- 本技能只使用**无需凭证**的公开只读接口，因此 TON、SUI、Cosmos、XRP、Dogecoin、Litecoin、Polkadot 等缺少免费公开数据通道的链族不在覆盖范围内
- Avalanche、Scroll、Linea、Mantle 的 Blockscout 实例当前不可用，同样不在覆盖范围内。以上均须在报告「查询说明」中显式声明为缺失链，不得留白

## 安全声明（提交审核与用户告知用）

1. **只读**：全部请求为 `HTTP GET` 与只读 JSON-RPC（`eth_call` / `eth_getBalance` / `getBalance` / `getTokenAccountsByOwner`）。**无签名、无交易、无授权、无转账路径。**
2. **无密钥**：脚本不接收、不存储、不解析任何私钥、助记词、种子短语；形似密钥的输入一律拒收。地址默认脱敏输出。
3. **零凭证**：脚本不读取任何环境变量、不接收任何 API Key / Secret / Token / Passphrase，不存在凭证输入口、不产生签名。全部出口均为无需鉴权的公开只读端点。
4. **出口可控**：出口域名在代码中静态写死（区块浏览器 / 公共 RPC / 公开行情聚合器），不接受运行时传入的任意主机参数；不在代码层改写或绕过系统代理配置。
5. **可验证**：输出结果与区块浏览器公开数据一致，用户可自行复核；未定价资产与失败链全部明示，不掩盖缺失。
6. **不做推断**：不推断地址归属、不提供投资建议、不构成资产证明。
