# VMM 迁移手册 — audiobook 从 DSM 容器迁到 Ubuntu 虚拟机

> 目的：彻底解决 RS2416+ 内核 3.10.108（Braswell 锁死）导致的 docx→pdf/epub 转换崩溃
> （glibc arc4random 无回退，容器内任何手段都绕不过，虚拟机换新内核即可）。
>
> 前置：VMM 已安装 ✓；**内存建议扩到 6GB 再开干**（DSM 自身吃 ~1.5GB，VM 分 3-4GB 才稳）。
> 预计耗时：一次装机 + 迁移约 1-2 小时。
>
> 纪律：一次只执行一条命令，只复制代码块里的命令行，**不要把文档整段贴进 SSH**。

---

## 0. 先记录现状（DSM SSH 上做）

先把旧容器当前的端口、数据位置记下来，后面照抄：

```sh
docker inspect audiobook-mybooks-1 --format '{{json .HostConfig.PortBindings}}'
ls /volume1/docker/audiobook-data
```

- 记下端口映射（例如 `8875->8875`），第 5 步要用。
- 确认数据目录里有：`books/`、`db/`（或 sqlite 文件）、模型缓存等。

**停写窗口**：真正迁移那一步前，先在 DSM 网页端暂停使用（不导新数据），避免两边数据分叉。

---

## 1. VMM 里创建 Ubuntu 虚拟机

1. VMM → 虚拟机 → 新增 →「创建虚拟机」。
2. 镜像：先去 Ubuntu 官网下载 **Ubuntu Server 24.04 LTS** ISO（`ubuntu-24.04.x-live-server-amd64.iso`），上传到 VMM 存储空间。
3. 配置建议：
   - vCPU：**2**（C2538 四核，留 2 核给 DSM）
   - 内存：**4096 MB**（6GB 内存到位后；内存没到之前先分 2048 只能跑起来不能转换）
   - 磁盘：**≥ 60 GB**（系统 + Docker 镜像 + 转换临时文件），Thin Provisioning 省空间
   - 网络：**默认（NAT）**先通，第 6 步改桥接
4. 安装 Ubuntu：语言选 English，一路默认；**勾选 Install OpenSSH server**；磁盘整盘使用，不加密。
5. 装完重启，登录后记下 VM 的 IP：

```sh
ip addr show
```

---

## 2. Ubuntu 里装 Docker

```sh
sudo apt update && sudo apt -y upgrade
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

退出重新登录（让 docker 组生效），验证：

```sh
docker run --rm hello-world
```

---

## 3. 把数据从 DSM 拷进 VM

推荐走 DSM 共享文件夹 + SCP（VM 能访问 DSM 即可，NAT 网络下 VM 可以主动连外网/局域网）。

先在 DSM 上建只读共享：控制面板 → 共享文件夹 → 新增 `vmm-migrate`，权限给 admin 读写，
然后 SSH 上 DSM 把数据复制进去（或直接把 `audiobook-data` 内容复制到该共享）：

```sh
cp -a /volume1/docker/audiobook-data/. /volume1/vmm-migrate/
```

回到 Ubuntu VM，从 DSM 拉数据（IP 换成你的 DSM 地址 10.140.81.11）：

```sh
sudo mkdir -p /srv/audiobook-data
rsync -av --progress admin@10.140.81.11:/volume1/vmm-migrate/ /srv/audiobook-data/
```

> rsync 会提示装 `rsync`，按提示 `sudo apt -y install rsync` 后重跑。

---

## 4. 拉源码、起容器

```sh
git clone https://gitee.com/wxgoo/audiobook-src.git ~/audiobook
cd ~/audiobook
```

编辑 `docker-compose.yml`：把数据挂载从 `audiobook-data` 改成 VM 本地路径
（原行类似 `/volume1/docker/audiobook-data:/data`，改为）：

```yaml
      - /srv/audiobook-data:/data
```

端口保持和 DSM 旧容器一致（第 0 步记的那个）。然后：

```sh
docker compose up -d
docker compose ps          # 应为 RUNNING
curl -s http://localhost:<端口>/ | head -c 200   # 有返回即通
```

---

## 5. VM 网络改桥接 + DSM 端口转发

VMM 的 NAT 网络从外部访问不了，要改成桥接：

1. 关掉 VM → VMM → 网络 → 编辑该虚拟机 → 选你的物理网卡（桥接模式）→ 开机。
2. 开机后 VM 拿到和 NAS 同网段的 IP（如 `10.140.81.x`），`ip addr show` 记下。
3. DSM：控制面板 → **门户/端口转发**（或外部访问 → 路由器配置），把原来的外部端口指向
   `10.140.81.x:<容器端口>`。内网直连也可以直接用 `http://10.140.81.x:<端口>`。

验证：浏览器打开 `http://10.140.81.x:<端口>`，登录，检查 49 本 epub、80 条阅读记录都在。

---

## 6. 验证转换功能（本次迁移的最终目的）

在网页端随便选一本 docx → 转 PDF，成功即大功告成。
（新内核 ≥ 3.17，glibc arc4random 正常走 getrandom，不会再 abort。）

也可在 VM 里快速自测：

```sh
uname -r                    # 应 ≥ 5.15
docker exec -it audiobook-mybooks-1 ebook-convert --version
```

---

## 7. 收尾

确认跑稳几天后：

1. DSM SSH 上停掉并删除旧容器：

```sh
cd /volume1/docker/audiobook && docker compose down
docker ps -a | grep mybooks   # 确认没有残留
```

2. 旧数据 `/volume1/docker/audiobook-data` **先保留 2 周**再删（VM 里 `/srv/audiobook-data` 已是主副本）。
3. 以后升级直接在 VM 里 `git pull && docker compose build && docker compose up -d`，
   或用 `scripts/upgrade.sh`（注意包路径是 VM 上的路径）。

## 常见坑

| 现象 | 处理 |
|---|---|
| VMM 分配内存后 DSM 卡顿 | 内存不够，等 6GB 到位，DSM 至少留 2GB |
| VM 桥接后拿不到 IP | VMM 网络 → 确认绑的是在用物理网卡，VLAN 不用开 |
| rsync 很慢 | 走 DSM 共享夹 + VM 拉取比 SMB 推快；数据几十 GB 耐心等 |
| 容器起来但页面 500 | 多半是数据没拷全，`ls /srv/audiobook-data` 对照第 0 步清单 |
| VM 磁盘满（转换失败） | Thin 磁盘扩容：VMM 支持在线扩，VM 里 `growpart` + `resize2fs` |
