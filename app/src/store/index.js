export const state = () => ({
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
    sysRefresh: 0,
    // 全局迷你播放条：唯一的播放状态源。
    // kind: 'stream'=友链电台（AppHeader 触发）；'audio'=有声书（播放页收起后交由全局条接管）。
    // audioId 只在 kind==='audio' 时有值，用于「回到播放页」。组件挂在 default 布局上，
    // 因此路由切换不会销毁它，播放不中断。
    miniPlayer: {
        visible: false,
        url: "",
        title: "",
        kind: "",
        audioId: null,
        playing: false,
        currentTime: 0,
        duration: 0,
        rate: 1,
        // 有声书播放列表：kind==='audio' 时由播放页 collapseToMini() 一次性灌入，
        // 迷你条靠它做「播完自动下一首」和上一首/下一首按钮（收起后播放页已销毁，
        // 页面里那套 nextTrack 逻辑这时没人执行，列表必须跟着状态一起搬过来）。
        // 元素：{ url, title, base }，base 是该集在整轨里的起始秒（start_time）。
        list: [],
        index: -1,
    }
})

export const mutations = {
    loading(state) {
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
        // 没有文案的告警在 default.vue 里会渲染成 persistent 空对话框，且关掉前挡住整页，
        // 从任何调用点漏进来都等于一次“假空白”，这里直接忽略。
        if (!v || !v.msg) {
            return;
        }
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
    },
    // AppHeader 里友链电台点击即用：commit('miniPlayer_play', {title, url, kind:'stream'})
    miniPlayer_play(state, v) {
        if (!v || !v.url) {
            return;
        }
        const mp = state.miniPlayer;
        mp.url = v.url;
        mp.title = v.title || "";
        mp.kind = v.kind || "stream";
        mp.audioId = v.audioId || null;
        mp.currentTime = v.startTime || 0;
        mp.duration = 0;
        mp.rate = v.rate || 1;
        mp.playing = v.playing !== false;
        mp.visible = true;
        // 播放列表只由播放页灌入；电台/其它音源（不带 list）必须把旧列表清掉，
        // 否则迷你条会拿上一本书的列表去"下一首"，串台。
        if (Array.isArray(v.list)) {
            mp.list = v.list;
            mp.index = (typeof v.index === "number" && v.index >= 0 && v.index < v.list.length)
                ? v.index : -1;
        } else {
            mp.list = [];
            mp.index = -1;
        }
    },
    // 迷你条切集：delta = +1 下一首 / -1 上一首。
    // 收起后播放页已销毁，只能由这条 mutation 改 url —— 组件侧监听 track.url 重新 attach。
    miniPlayer_step(state, delta) {
        const mp = state.miniPlayer;
        const n = Array.isArray(mp.list) ? mp.list.length : 0;
        if (mp.kind !== "audio" || n === 0) {
            return;
        }
        const next = (mp.index < 0 ? 0 : mp.index) + delta;
        if (next < 0 || next >= n) {
            return;
        }
        const item = mp.list[next] || {};
        if (!item.url) {
            return;
        }
        mp.index = next;
        mp.url = item.url;
        mp.title = item.title || mp.title;
        // currentTime 用绝对秒（含 start_time），与 collapseToMini 交接的口径一致：
        // 换成 base 正好是这一集的开头，加载后不会被 applyStart 定位到上一集的位置。
        mp.currentTime = item.base || 0;
        mp.duration = 0;
        mp.playing = true;
    },
    miniPlayer_pause(state) {
        state.miniPlayer.playing = false;
    },
    miniPlayer_resume(state) {
        if (state.miniPlayer.url) {
            state.miniPlayer.playing = true;
        }
    },
    miniPlayer_toggle(state) {
        if (!state.miniPlayer.url) {
            return;
        }
        state.miniPlayer.playing = !state.miniPlayer.playing;
    },
    miniPlayer_progress(state, v) {
        if (!v) {
            return;
        }
        state.miniPlayer.currentTime = v.currentTime || 0;
        state.miniPlayer.duration = v.duration || 0;
    },
    // 只更新时长（loadedmetadata 时补一次，让刚展开的进度条立刻可拖）
    miniPlayer_duration(state, v) {
        state.miniPlayer.duration = v || 0;
    },
    miniPlayer_close(state) {
        state.miniPlayer.visible = false;
        state.miniPlayer.playing = false;
        state.miniPlayer.url = "";
        state.miniPlayer.title = "";
        state.miniPlayer.kind = "";
        state.miniPlayer.audioId = null;
        state.miniPlayer.currentTime = 0;
        state.miniPlayer.duration = 0;
        state.miniPlayer.list = [];
        state.miniPlayer.index = -1;
    }
}
