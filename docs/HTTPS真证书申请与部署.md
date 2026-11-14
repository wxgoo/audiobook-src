# NAS 上申请真证书（无域名 → 买域名 → Let's Encrypt 全自动）

针对你的情况：**没有域名 + 运营商只放行了 88 端口**。
先说清楚为什么别的路走不通，再给唯一顺畅的那条。

## 0. 为什么没有域名就签不了免费证书

Let's Encrypt 2026 年起确实能给裸 IP 签证书（6 天短周期），
但验证只接受两种方式，端口都是硬性的：

| 验证方式 | 要求端口 | 你的情况 |
|---|---|---|
| HTTP-01 | 公网 **80** 必须可达 | 运营商封了 80，你只映射了 88 |
| TLS-ALPN-01 | 公网 **443** 必须可达 | 同样被封 |

88 端口不在允许范围内，所以纯 IP 这条路在你家走不通。
而**域名证书走 DNS 验证，跟端口完全无关**——这就是买域名值得的原因。

## 1. 买域名（一次性，约 5~30 元/年）

随便挑一家：阿里云万网、腾讯云 DNSPod 都行，`.top`/`.xyz`/`.cn` 首年几块钱。
买完不用备案也能用（你走 88 非标端口 + 家用宽带，运营商基本不拦；
但别把域名解析到 80/443 对外提供服务，那才会触发备案拦截）。

本文假设域名是 `book.example.com`（可以只用主域 `example.com` 加个子域名）。

## 2. 装 acme.sh（NAS 上，SSH 以管理员登录）

```bash
curl https://get.acme.sh | sh -s email=你的邮箱@example.com
source ~/.profile
# 默认 CA 是 ZeroSSL，改成 Let's Encrypt（IP 证书、稳定些）
acme.sh --set-default-ca --server letsencrypt
```

## 3. 拿 DNS API 密钥（只给 DNS 权限，不要用主账号密钥）

以阿里云为例：
1. 控制台 → RAM 访问控制 → 用户 → 创建用户（勾选「OpenAPI 调用」）
2. 授权：**AliyunDNSFullAccess**（只管 DNS，够用且最小化）
3. 拿到 `AccessKey ID` 和 `AccessKey Secret`

腾讯云 DNSPod 用 API Token（`DP_Id`/`DP_Key`）；Cloudflare 用 API Token（`CF_Token`，权限选 Zone-DNS-Edit）。

## 4. 一条命令签发 + 装进容器 + 挂自动续期

```bash
cd /volume1/docker/audiobook     # deploy-cert.sh 放这里
export Ali_Key=xxxxx Ali_Secret=xxxxx
sh deploy-cert.sh book.example.com
```

脚本会自动完成：DNS 验证签发 → 校验证书/私钥配对 → 备份旧版 →
写入 `/volume1/docker/audiobook-data/books/ssl/` → `nginx -t` → 热重载。
**全程不重启容器，正在看书/听书的人无感。**

## 5. 之后什么都不用做

acme.sh 装好后自带 cron（每 60 分钟检查一次），90 天证书到期前自动续期，
续完自动执行上面那套部署动作。偶尔想确认一眼：

```bash
sh deploy-cert.sh status    # 本地证书 + 容器内生效证书 + 续期任务状态
```

浏览器访问 `https://book.example.com:8443`（按你 compose 的 `"8443:443"` 映射；
想换端口改 compose 左边那个数字即可）。

## 6. 两个后续提醒

**动态公网 IP**：家宽 IP 可能重启光猫就变。证书不受影响（签的是域名），
但要「域名总能指向最新 IP」就需要 DDNS：DSM 控制面板 → 外部访问 → 新增 DDNS，
阿里云/腾讯云都有原生支持，5 分钟配完。没配的话 IP 一变，证书再真也连不上。

**密钥安全**：`Ali_Secret` 只 export 在当前会话，不要写进脚本提交到 git；
acme.sh 会自己把密钥存进 `~/.acme.sh/account.conf`（权限 600，它自己管）。
