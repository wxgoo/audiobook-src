export const state = () => ({
    miniPlayer: {
        show: false, title: '', url: '',
        kind: 'stream', bookId: null, startTime: 0,
    },
    nav: true, loading: true, count: 0, searchLoading: false, user: {
        is_admin: false,
        is_login: false,
        // 后端 /user/info 下发：上传能力由用户 u 权限位决定（管理员恒为 true），
        // 与 sys.allow.upload（只表示访客能否上传）是两回事
        can_upload: false,
        nickname: "",
        kindle_email: "",
        avatar: "",
    }, alert: {
        to: "", msg: "", type: "", show: false,
    }, sys: {
        socials: [],
        allow: {
            physical_books: false,
            download_quota: false,
            upload: false,
            register: false,
            require_login: false,
            guest_read: false,
            guest_download: false,
            guest_upload: false,
            guest_push: false,
            guest_register: false,
            book_review: false
        },
        mynexus_enabled: false
    },
    site_title: "首页",
    site_title_template: "%s | MyBooks",
    showUserInfo: false,
    // 下面三个由 AppHeader 从 /user/info 的 sys 摊平而来，必须在这里声明：
    // 否则它们是"运行时新增字段"——既拿不到 Vue 的响应式，也只能靠 mutation 外
    // 直接赋值写入，而 dev 模式的 vuex strict 会直接抛错（首页变 error layout）。
    ai_enabled: false,
    default_page_size: 0,
    index_page: "",
    // 设置保存后自增：AppHeader 监听它重新拉 /user/info，让侧边栏等导航立即生效
    sysRefresh: 0
})

export const mutations = {
    miniPlayer_play(state, { title, url, kind, bookId, startTime }) {
        state.miniPlayer = { show: true, title, url, kind: kind || 'stream', bookId: bookId || null, startTime: startTime || 0 };
    }, miniPlayer_hide(state) {
        state.miniPlayer.show = false;
        state.miniPlayer.url = '';
    }, miniPlayer_toggle(state) {
        state.miniPlayer.show = !state.miniPlayer.show;
    }, loading(state) {
        state.loading = true;
    }, loaded(state) {
        state.loading = false;
    },
    // sys 的展示相关字段摊平到根 state。原先在 AppHeader 里直接改 $store.state，
    // dev 模式 store.strict=true 时会抛 "do not mutate vuex store state outside
    // mutation handlers"，整页落到 error layout —— 现象就是首页永远显示
    // 「服务正在启动中，稍后重试」。
    sync_sys(state, sys) {
        if (!sys) {
            return;
        }
        state.site_title_template = "%s | " + sys.title;
        state.ai_enabled = sys.aiEnabled;
        state.default_page_size = sys.defaultPageSize;
        state.index_page = sys.indexPage;
        state.showUserInfo = sys.showUserInfo;
    }, /*
    puremode(state, pure) {
        if (pure) {
            state.nav = false;
        } else {
            state.nav = true;
        }
    },
    */
    navbar(state, nav) {
        state.nav = nav;
    },
    search_loading(state, loading) {
        state.searchLoading = loading;
    }, increment(state) {
        state.count++
    }, login(state, data) {
        if (data != undefined) {
            if (data.sys) {
                state.sys = data.sys;
            }
            if (data.user) {
                state.user = data.user;
            }
        }
    }, alert(state, v) {
        state.alert.to = v.to;
        state.alert.type = v.type;
        state.alert.msg = v.msg;
        state.alert.show = true;
    }, close_alert(state) {
        state.alert.show = false;
    }, clear_user(state) {
        // 退出登录 / 会话过期（user.need_login）时统一走这里：
        // 全站守卫靠 user.is_login 走快路径，只清插件缓存不清 store 会让过期会话继续放行。
        state.user = {
            is_admin: false,
            is_login: false,
            can_upload: false,
            nickname: "",
            kindle_email: "",
            avatar: "",
        };
    }, settings_title(state, v) {
        state.site_title_template = ' %s | ' + v;
    }, set_sys(state, sys) {
        if (sys) state.sys = sys;
    }, refresh_sys(state) {
        state.sysRefresh += 1;
    }
}
