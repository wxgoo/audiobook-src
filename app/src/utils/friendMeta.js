/**
 * 友情链接：类型由管理员在设置页显式选择（FRIENDS[].type），这里只负责
 * 把类型映射成图标，以及决定点击行为。
 *
 * 重要：**只有 radio（电台）才触发底部迷你播放条播放**，其余类型一律普通
 * 外链跳转。不再按 URL / 名称推断类型——build.22 之前那套推断会把大量普通
 * 友链猜成「电台」，点一下就意外开始播放。
 *
 * 老数据（没有 type 字段）在读取时按 website 呈现；管理员改选「电台」后才会
 * 恢复点击即播。
 */

export const FRIEND_TYPE_ICONS = {
    radio: 'mdi-radio',             // 电台 / 播客 / 音频直播
    website: 'mdi-web',             // 网站（默认）
    bbs: 'mdi-forum',               // 论坛 / BBS / 社区
    video: 'mdi-video',             // 视频 / 影视 / 短视频
    news: 'mdi-newspaper',          // 资讯 / 博客 / 新闻
    book: 'mdi-library-shelves',    // 书站 / 图书馆 / 阅读
    link: 'mdi-link-variant',       // 其它（非法值兜底）
}

export const DEFAULT_FRIEND_TYPE = 'website'
export const FALLBACK_FRIEND_TYPE = 'link'

// 历史/常见别名（与后端 webserver/friend_links.py 保持一致）
const TYPE_ALIASES = {
    stream: 'radio',
    podcast: 'radio',
    fm: 'radio',
    site: 'website',
    web: 'website',
    forum: 'bbs',
    community: 'bbs',
    blog: 'news',
    article: 'news',
    books: 'book',
    library: 'book',
    other: 'link',
}

/**
 * 把任意 type 值收敛到 FRIEND_TYPE_ICONS 的键。
 * 缺失 -> website；可识别别名 -> canonical；其它 -> link。
 */
export function normalizeFriendType(value) {
    if (value === null || value === undefined) return DEFAULT_FRIEND_TYPE
    if (typeof value !== 'string') return FALLBACK_FRIEND_TYPE
    const key = value.trim().toLowerCase()
    if (!key) return DEFAULT_FRIEND_TYPE
    if (Object.prototype.hasOwnProperty.call(FRIEND_TYPE_ICONS, key)) return key
    return TYPE_ALIASES[key] || FALLBACK_FRIEND_TYPE
}

export function getFriendMeta(friend) {
    const type = normalizeFriendType(friend && friend.type)
    return {
        type,
        icon: FRIEND_TYPE_ICONS[type],
        // 只有显式选择「电台」才播放，其它类型一律普通跳转
        isStream: type === 'radio',
    }
}
