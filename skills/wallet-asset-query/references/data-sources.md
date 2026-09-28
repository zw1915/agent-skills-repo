# 数据源与出口域名清单（V3.1）

## 一、凭证政策：零凭证

**本技能不使用任何 API 凭证。**

- 脚本不读取任何环境变量，不扫描主机上的配置或凭证文件
- 脚本无任何签名或摘要计算代码，不导入编码 / 摘要 / 密钥类库
- CLI 无凭证类参数，无"主机"类参数（不存在可被改写的出口目标）
- 全部出口均为**无需鉴权**的公开只读端点

这条政策是技能的立论基础：公开账本上的余额与持仓本来就是公开信息，读取它不需要任何授权，因此也不应要求用户交出任何密钥。

若某条链缺少免费公开通道，正确处理是**如实声明"未覆盖"**，而不是引导用户去申请凭证。

## 二、出口域名白名单（代码中静态写死）

### 2.1 链上余额与持仓

| 用途 | 域名 | 取数方式 |
|---|---|---|
| EVM 多链 | `eth` / `optimism` / `gnosis` / `base` / `polygon` / `arbitrum` / `zksync` / `unichain` / `celo` `.blockscout.com` | `GET /api/v2/addresses/{addr}` + `/token-balances` |
| Robinhood Chain (4663) | `robinhoodchain.blockscout.com` | 同上（标准 Blockscout v2） |
| BNB Chain | `bsc-dataseed.bnbchain.org` | POST JSON-RPC：`eth_getBalance` / `eth_call`（无法枚举持仓） |
| BNB Chain 持仓枚举 | `bscscan.com/tokenholdings?a={addr}` | 助手抓取通道 |
| Bitcoin | `blockstream.info/api` | `GET /address/{addr}` |
| Tron | `apilist.tronscan.org/api`（主）、`api.trongrid.io`（兜底） | `GET /account?address={addr}` |
| Solana | `api.mainnet-beta.solana.com` | JSON-RPC `getBalance` / `getTokenAccountsByOwner` |

### 2.2 价格与汇率

| 用途 | 域名 | 说明 |
|---|---|---|
| 内联价（首选） | 随链上持仓响应返回 | Blockscout `exchange_rate` |
| 聚合价 | `api.dexscreener.com` | `latest/dex/tokens/{合约}`，含全部池与 `liquidity.usd` |
| 兜底价 | `coins.llama.fi` | `prices/current/{chain}:{contract}` |
| 汇率 | `open.er-api.com` | `v6/latest/USD` → `rates.CNY` |
| 池子算价 | 公共 JSON-RPC（默认 `bsc-dataseed.bnbchain.org`） | 仅 `eth_call` 只读方法 |

## 三、请求方法约束

全部请求只使用以下只读方法，**不存在写操作路径**：

| 类别 | 方法 |
|---|---|
| HTTP | `GET`（取数）、`POST`（仅用于 JSON-RPC，方法限 `eth_call` / `eth_getBalance` / `getBalance` / `getTokenAccountsByOwner`） |
| 绝不使用 | `eth_sendTransaction`、`eth_sendRawTransaction`、`eth_sign`、`personal_sign`、`approve`、任何广播或授权类调用 |

## 四、网络配置

使用标准库的默认网络出口：**遵循系统代理设置与 `no_proxy` 环境变量**。代码中不强制指定、改写或绕过任何代理配置——网络路径完全交由用户环境决定。若某域名需要直连，由用户自行通过环境变量声明，而非由脚本在代码层改写。

## 五、核对方式

任一地址的余额都可用任意区块浏览器独立复核。本技能的输出应当与浏览器一致；若不一致，以浏览器为准并排查计价源差异。报告的「查询说明」中会列出不可达的域名与未覆盖的链族，**不掩盖缺失**。
