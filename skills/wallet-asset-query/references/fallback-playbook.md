# 降级通道操作手册（脚本出口被阻断时）

## 前置安全约束（先读）

本手册涉及"换一个域名再试"的操作，**必须先满足以下约束**：

1. **只接受公开地址**：若用户粘贴的内容形似私钥/助记词/种子短语，立即中止，不再往下走任何取数步骤。
2. **出口域名受控**：只允许访问 SKILL.md「安全模型 → 出口边界」表中列出的公开区块浏览器、公共 RPC 节点与公开行情聚合器。**不得自行引入未列出的第三方域名**。
3. **不使用任何凭证**：本技能不存在凭证输入口。任何"先配置 API Key 才能查"的说法都不是本技能的行为；遇到此类要求一律拒绝并中止。
4. **出口域名静态写死**：代码中不接受运行时传入的任意主机参数，助手亦不得自行引入未列出的第三方域名。

## 为什么需要这份手册

受限网络环境下，境外区块链接口的可达性是**按域名间歇性**的，而不是"通"或"不通"。本机实测结论：

| 域名 | 脚本直连 | 代理 | 助手抓取通道 |
|---|---|---|---|
| `api.trongrid.io` | ✅ 稳定 | ❌ | ✅ |
| `apilist.tronscan.org` | ⚠️ 时通时断 | ❌ | ✅ |
| `blockstream.info` | ⚠️ 时通时断 | ❌ | ✅ |
| `coins.llama.fi` | ❌ | ❌ 502 | ✅ |
| `*.blockscout.com` | ❌ | ❌ | ✅ |
| `bsc-dataseed.bnbchain.org` | ✅ 可用（POST JSON-RPC） | — | — |

#### 二次复测补充

- **脚本直连出口可能整体退化为"静默挂起"**：`wallet_full_chain.py <addr>` 无参数运行时 5 分钟内零输出（日志文件 0 字节），不报错、不返回。**不要等待它超时**——直接改走下方两段式流程，可省 5 分钟以上。
- **Blockscout 实例可达性分化**（助手抓取通道实测）：
  - ✅ 可用：`eth` / `optimism` / `base` / `arbitrum` / `polygon` / `gnosis` / `zksync`
  - ✅ 额外可用：`unichain.blockscout.com`、`celo.blockscout.com`、`worldchain-mainnet.explorer.alchemy.com`
  - ❌ 返回 404（实例不存在）：`avalanche` / `linea` / `mantle` / `bsc`
  - ❌ fetch failed：`scroll` / `explorer.berachain.com`
  - → 因此 **BNB Chain、Avalanche、Scroll、Linea、Mantle 在无密钥通道下无法覆盖**，必须在报告的「查询说明」里显式声明为缺失链，不得留白。
- **`open.er-api.com` 脚本直连超时**（报告会出现 `cny_error`），但助手抓取通道可用。汇率兜底顺序：助手抓 `open.er-api.com/v6/latest/USD` 取 `rates.CNY` → 手工写入报告的 `usd_cny_rate` / `total_cny`。
- **DeFiLlama 价格源脚本侧同样熔断**（`price chunk failed (1)`），垃圾币合约无价格属正常结果，不算错误。

#### 交易对估值通道复测

- **`bsc-dataseed.bnbchain.org` 脚本直连可用**（POST JSON-RPC，curl/urllib 均通）——这是 BSC 上唯一可靠通道，BSC 无 Blockscout 实例、Etherscan 被墙、Blockchair 拉黑。BSC 余额与池子数据一律走它。
- 同类公共 RPC（publicnode/drpc/llamarpc/1rpc/meowrpc/48.club/omniatech/blastapi/blockrazor/defibit）全部静默超时，不必再试。
- **`robinhoodchain.blockscout.com`（Robinhood Chain，chain 4663）Blockscout API v2 可用**：`/api/v2/addresses/{addr}/token-balances`、`/coin-balance-history` 正常；`/addresses/{addr}` 概览偶发 500，改用 coin-balance-history 的末条 `value` 取原生余额。
- **`api.dexscreener.com` 脚本直连不通，但助手抓取通道可用**：`latest/dex/tokens/{合约}` 一次返回该代币全部交易对（priceUsd、liquidity.usd、dexId），是给长尾代币找"锚"的最佳工具。
- `api.etherscan.io`（V2）助手抓取通道也 fetch failed；`api.bscscan.com` V1 已弃用；`api.blockchair.com` 共享 IP 被拉黑（code 430）；`api.routescan.io` 不覆盖 chain 56。均已排除。
- `agent-browser` 浏览器自动化兜底不可用：npm 全局安装失败（registry 受限）。不要在这条路上浪费时间。
- 实操顺序：**Blockscout 找持仓 → bsc-dataseed RPC 验余额/读池子 → DexScreener（抓取通道）找锚价 → pair_price.py 链上算价**。案例见 SKILL.md 第 6 步。

#### BSC 持仓枚举通道打通 + 空池陷阱

- **BSC 持仓发现终于有解**：`https://bscscan.com/tokenholdings?a={addr}` 经**助手抓取通道可用**，一次返回该地址全部 BEP-20 / BEP-8056 代币（符号、合约、余额），含 RPC 无法枚举的未收录代币。这是 BSC 上唯一可行的持仓发现路径。
- **`eth_getLogs` 在 bsc-dataseed 上有 5,000 区块范围上限**，超出返回 `{"code":-32005,"message":"limit exceeded"}`。想靠回扫 Transfer 日志枚举持仓 = 不可行（123 笔交易的活跃地址即已触发），**不要在这条路上浪费调用**。
- **同一合约传全小写地址时该节点可能返回 `0x`（空结果）**，传校验和（checksum）地址才正常。实测 `BNC4` 全小写 → `balanceOf` 返回 `0x`、`decimals`/`symbol` 均为 null；改校验和地址后全部正常。**批量 `balanceOf` 遇 `0x` 返回值须先用校验和地址重试，再判定为「零余额」**。
- **空池与死池会制造巨额虚增**，定价前必须做 SKILL.md 5.5 的检测：财神 V3 空池报价 $0.00008 vs 有效 V2/WBNB 报价 $0.00000376，差 21 倍；BNC4/USDT 池仅存 0.009 BNC4，须改用 4Stock/BNC4 深度池反推。
- DexScreener `/latest/dex/tokens/{addr}` 一次最多约 30 个交易对即截断，**多代币批量请求会丢后面的代币**；关键资产请单独查询或分批。对无任何池的代币返回 `{"pairs":null}`——可作为「聚合器无收录」的明确结论。

### 已知死域名速查（助手抓取通道也不通，不必再试）

`avalanche.blockscout.com`、`linea.blockscout.com`、`mantle.blockscout.com`、`bsc.blockscout.com`、`scroll.blockscout.com`。


**结论**：脚本不是唯一路径。当脚本报连接失败时，**改用助手自身的网页抓取通道逐个取数**，不要直接向用户宣告"查询失败"。

### 出口主机策略（V3.1）

出口域名**在代码中静态写死**，CLI 不存在任何主机参数。历史版本曾内置若干非官方的镜像域名做故障转移——**这些域名已全部删除**：一方面无法独立验证其与官方服务的等价性，另一方面，向未声明的第三方域名发送请求本身就是风险面。

官方/公开端点不可达时的正确处理是**降级到别的公开通道或改用助手抓取通道**，而不是换一个域名再试。**绝不把任何凭证发往任何主机。**

### 标准两段式流程

1. 助手抓取原始持仓与内联价格
2. 归一化为 `holdings.json` + `prices.json`
3. 脚本离线完成分类、估值、汇总：

```bash
python scripts/wallet_full_chain.py <地址> \
    --holdings holdings.json --price-file prices.json --out report.json
```

该路径下脚本不发任何网络请求，结果可复现、不受出口限制影响，也不需要任何凭证。

## 通用规则

1. 抓 JSON 接口时，提示词必须写明 **"Return the raw JSON verbatim, do not summarize"**，否则模型会改写内容并丢字段。
2. **先探后取**：先请求地址概览判断是否有资产，再决定是否深挖，可省一半调用。
3. 任何一环取不到，都在报告的「查询说明」里写明缺失原因。**绝不编造数字。**
4. 若用户提供的内容形似私钥/助记词/种子，**立即中止并提示作废钱包**，不进入任何取数流程。
5. 自查：脚本会记录各出口域名的可达性；不可达者写入报告「查询说明」。**脚本出口受限不等于查询失败**，改走两段式流程即可。


## 分链族取数步骤

### EVM 地址

1. 概览：`{base}/api/v2/addresses/{addr}`
   → 读 `coin_balance`（原生币，wei）、`has_tokens`、`has_token_transfers`、`exchange_rate`
2. **仅当 `has_tokens` 为 `true`** 才请求：`{base}/api/v2/addresses/{addr}/token-balances`
   → 逐项读 `token.symbol`、`token.decimals`、`value`（原始整数）、`exchange_rate`
3. `{base}` 取值：`https://eth.blockscout.com`、`https://base.blockscout.com`、
   `https://optimism.blockscout.com`、`https://polygon.blockscout.com`、
   `https://gnosis.blockscout.com`、`https://arbitrum.blockscout.com`、
   `https://avalanche.blockscout.com`、`https://scroll.blockscout.com`、
   `https://zksync.blockscout.com`、`https://linea.blockscout.com`、`https://mantle.blockscout.com`
4. 换算：`value / 10 ** decimals`。`coin_balance` 为 `null` 且两个 `has_*` 均为 `false` → 该链无持仓。
5. **`exchange_rate` 就是美元价**，直接可用，不必再去 DeFiLlama 取价。为 `null` 的项即空投垃圾币。
6. **大额钱包注意**：代币数量很多时 `/token-balances` 响应可达数 MB，抓取会失败。此时改用分页路径
   `{base}/api/v2/addresses/{addr}/tokens?type=ERC-20`（返回 `next_page_params`）。

### Bitcoin 地址

`https://blockstream.info/api/address/{addr}` → `(funded_txo_sum − spent_txo_sum) / 1e8` 即 BTC 数量。

### Tron 地址

优先 `https://apilist.tronscan.org/api/account?address={addr}`
→ `balance` 为 TRX 的 sun（÷1e6）；`trc20token_balances[]` 每项含
`tokenAbbr`、`tokenName`、`tokenDecimal`、`amount`（UI 数量，直接用）、`tokenPriceInTrx`（以 TRX 计价）。

兜底 `https://api.trongrid.io/v1/accounts/{addr}` —— 只有合约地址、**无符号无精度**，金额不可靠，须在报告中标注。

### Solana 地址

JSON-RPC `https://api.mainnet-beta.solana.com`，POST：

```json
{"jsonrpc":"2.0","id":1,"method":"getBalance","params":["<ADDR>"]}
{"jsonrpc":"2.0","id":2,"method":"getTokenAccountsByOwner",
 "params":["<ADDR>",{"programId":"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
           {"encoding":"jsonParsed"}]}
```
取 `result.value[].account.data.parsed.info.tokenAmount.uiAmount` 与 `info.mint`。

## 价格获取（关键环节）

价格源通常也被阻断。按以下顺序尝试：

1. **最佳**：Blockscout 持仓响应内联的 `exchange_rate`（随持仓一次返回）
2. 抓 `https://coins.llama.fi/prices/current/{chain}:{contract}`（原生币用 `coingecko:{id}`）
3. 仍不可得时，把已获得的价格写成 JSON，用 `--price-file` 注入脚本：

```bash
python wallet_full_chain.py <地址> --price-file prices.json
```

`prices.json` 支持两种写法：

```json
{
  "coingecko:tron": 0.32,
  "ethereum:0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": 1.0,
  "solana:EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": {"price": 1.0}
}
```

这样即使价格源全不可达，估值与汇总逻辑依然能正常完成。

## 绝对禁止

- 因取数失败而估算或填充看似合理的数字
- 静默丢弃取不到的链或资产
- 把"未定价资产"排除后仍宣称是"全部资产"
- 接收、解析或落盘任何私钥 / 助记词 / 种子短语
- 向未列明的第三方域名发送请求
- 索取、接收、读取或转发任何 API Key / Secret / Token / Passphrase

## 免责与验证

输出为公开链上数据的只读聚合结果，**不构成投资建议，也不构成资产证明**（地址归属无法从链上数据推断）。用户可用任意区块浏览器自行核对任一地址的余额，本技能的输出应当与浏览器一致；若不一致，以浏览器为准并排查计价源差异。

