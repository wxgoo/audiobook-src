<template>
    <div class="mini-player-host">
        <!-- 音频元素必须常驻（不能放进 v-if 里）：
             条隐藏时元素若被销毁，再次展开时新元素没有 src，
             而 url 相关 watcher 已按“值变化”执行过一次，于是第二次收起无声。
             第一次能用只是因为当时元素恰好还在。 -->
        <audio
            ref="audio"
            preload="none"
            @timeupdate="onTimeUpdate"
            @loadedmetadata="onLoadedMetadata"
            @play="onPlay"
            @pause="onPause"
            @ended="onEnded"
            @error="onError"
        ></audio>
        <div v-if="track.visible" class="mini-player"
             :class="{ 'mini-player--dark': isDark, 'mini-player--skippable': canSkip }">
            <div class="mini-player-row">
                <v-icon size="18" class="mini-player-icon">{{ track.kind === 'stream' ? 'mdi-radio' : 'mdi-headphones' }}</v-icon>
                <span class="mini-player-title" :title="track.title">{{ track.title }}</span>
                <span class="mini-player-time" v-if="showTime">
                    {{ fmt(displayTime) }} / {{ fmt(track.duration) }}
                </span>
                <span class="mini-player-time" v-else-if="track.kind === 'stream'">{{ $t('miniPlayer.live') }}</span>
                <v-spacer></v-spacer>
                <!-- 上一首/下一首：只对有声书列表出现。收起后播放页已销毁，
                     这两个按钮就是唯一的切集入口（播完自动进下一首也走同一条 mutation）。 -->
                <v-btn v-if="canSkip" icon x-small class="mini-player-btn"
                       :disabled="track.index <= 0"
                       @click="step(-1)" :aria-label="$t('miniPlayer.prev')">
                    <v-icon>mdi-skip-previous</v-icon>
                </v-btn>
                <v-btn icon x-small class="mini-player-btn" @click="toggle"
                       :aria-label="track.playing ? $t('miniPlayer.pause') : $t('miniPlayer.play')">
                    <v-icon>{{ track.playing ? 'mdi-pause' : 'mdi-play' }}</v-icon>
                </v-btn>
                <v-btn v-if="canSkip" icon x-small class="mini-player-btn"
                       :disabled="track.index >= track.list.length - 1"
                       @click="step(1)" :aria-label="$t('miniPlayer.next')">
                    <v-icon>mdi-skip-next</v-icon>
                </v-btn>
                <v-btn v-if="track.kind === 'audio' && track.audioId" icon x-small class="mini-player-btn"
                       @click="goToPage" :aria-label="$t('miniPlayer.open')">
                    <v-icon>mdi-open-in-new</v-icon>
                </v-btn>
                <v-btn icon x-small class="mini-player-btn" @click="close" :aria-label="$t('miniPlayer.close')">
                    <v-icon>mdi-close</v-icon>
                </v-btn>
            </div>
            <div v-if="error" class="mini-player-error">{{ error }}</div>
            <!-- 可拖动进度条：整条 41px 都是拖拽热区（按钮 z-index 更高，不误触）；
                 电台/时长未知时退化为静态线，不提供无意义的拖动。 -->
            <div v-else-if="canSeek" ref="track" class="mini-player-track"
                 @pointerdown="onSeekStart" @pointermove="onSeekMove"
                 @pointerup="onSeekEnd" @pointercancel="onSeekEnd">
                <div class="mini-player-track-line"></div>
                <div class="mini-player-track-fill" :style="{ width: percent + '%' }"></div>
                <div class="mini-player-track-thumb" :style="{ left: percent + '%' }"></div>
            </div>
            <div v-else class="mini-player-track mini-player-track--idle">
                <div class="mini-player-track-line"></div>
            </div>
        </div>
    </div>
</template>

<script>
export default {
    name: 'MiniPlayer',
    data() {
        return {
            error: '',
            hls: null,
            intentPlay: false,
            lastEmit: 0,
            // 拖动状态：拖动期间显示/写回都以 dragPercent 为准，
            // 避免 timeupdate 把用户正在拖的值弹回旧位置
            dragging: false,
            dragPercent: 0,
            dragTime: 0,
            // play() 被 AbortError 打断后的重试计数（onPlay 里清零）
            playRetries: 0,
        }
    },
    computed: {
        track() {
            return this.$store.state.miniPlayer
        },
        // 站点支持深色主题（.theme--dark.v-application 会把继承色改成 #fff），
        // 底部条的底色必须跟着主题走，否则深色下就是白字白底，看着像“一片空白”
        isDark() {
            return !!(this.$vuetify && this.$vuetify.theme && this.$vuetify.theme.dark)
        },
        canSeek() {
            const d = this.track.duration
            return this.track.kind === 'audio' && !!d && isFinite(d) && d > 0
        },
        // 只有「有声书 + 播放页灌进来的多集列表」才显示切集按钮；
        // 电台（stream）和单集音频都不显示，避免出现不可点的按钮。
        canSkip() {
            const list = this.track.list
            return this.track.kind === 'audio' && Array.isArray(list)
                && list.length > 1 && this.track.index >= 0
        },
        showTime() {
            return this.track.kind !== 'stream' && this.track.duration > 0
        },
        displayTime() {
            return this.dragging ? this.dragTime : (this.track.currentTime || 0)
        },
        percent() {
            if (!this.canSeek) return 0
            const p = this.dragging
                ? this.dragPercent
                : ((this.track.currentTime || 0) / this.track.duration) * 100
            return Math.max(0, Math.min(100, p))
        },
    },
    watch: {
        'track.url'(url) {
            this.attach(url)
        },
        'track.playing'(playing) {
            if (playing) {
                this.resume()
            } else {
                this.suspend()
            }
        },
        'track.visible'(visible) {
            // 重新展开时元素是常驻的；这里只兜底“隐藏期间换过源但没拿到 ref”的极端情况
            if (visible && this.track.url) {
                this.$nextTick(() => {
                    const audio = this.$refs.audio
                    if (audio && !audio.getAttribute('src')) {
                        this.attach(this.track.url)
                    }
                })
            } else if (!visible) {
                this.dragging = false
            }
        },
    },
    mounted() {
        if (this.track.url) {
            this.attach(this.track.url)
        }
        // 移动端切后台/锁屏会把媒体挂起，回来时 store 还停在 playing，
        // 但元素是 paused —— 没有任何 watcher 会触发，表现就是「条在播、没声音」。
        // 这里在重新可见时补一次续播，并开看门狗兜住其它静默失败。
        if (process.client) {
            document.addEventListener('visibilitychange', this.onVisibility)
            window.addEventListener('pageshow', this.onVisibility)
        }
        this._startWatchdog()
    },
    beforeDestroy() {
        this._stopWatchdog()
        this.teardown()
        if (process.client) {
            document.removeEventListener('visibilitychange', this.onVisibility)
            window.removeEventListener('pageshow', this.onVisibility)
        }
    },
    methods: {
        fmt(sec) {
            const s = Math.max(0, Math.floor(sec || 0))
            const m = Math.floor(s / 60)
            const r = s % 60
            return m + ':' + (r < 10 ? '0' : '') + r
        },
        teardown() {
            if (this.hls) {
                try { this.hls.destroy() } catch (e) { /* 忽略 */ }
                this.hls = null
            }
        },
        // 换源：先销毁 HLS 实例再动 src，避免上一个 m3u8 继续拉流。
        // 普通音频直接给 src；m3u8 优先用 Safari/iOS 原生 HLS，其余走 hls.js
        async attach(url, retried) {
            const audio = this.$refs.audio
            if (!audio) {
                if (!retried) {
                    this.$nextTick(() => this.attach(url, true))
                }
                return
            }
            this.error = ''
            this.dragging = false
            this.teardown()
            this.intentPlay = true
            try {
                audio.pause()
                audio.removeAttribute('src')
                audio.load()
            } catch (e) { /* 忽略 */ }
            if (!url) return

            const applyStart = () => {
                if (this.track.currentTime > 0) {
                    try { audio.currentTime = this.track.currentTime } catch (e) { /* 忽略 */ }
                }
            }
            audio.addEventListener('loadedmetadata', applyStart, { once: true })

            const isHls = /\.m3u8(?:$|[?#])/i.test(url)
            if (!isHls) {
                audio.src = url
                this.syncPlay()
                return
            }
            const nativeHls = audio.canPlayType('application/vnd.apple.mpegurl')
            if (nativeHls) {
                audio.src = url
                this.syncPlay()
                return
            }
            try {
                const mod = await import('hls.js')
                const Hls = mod && (mod.default || mod)
                if (!Hls || typeof Hls.isSupported !== 'function' || !Hls.isSupported()) {
                    this.error = this.$t('miniPlayer.hlsError')
                    return
                }
                this.hls = new Hls({ enableWorker: true })
                this.hls.on(Hls.Events.ERROR, (evt, data) => {
                    if (data && data.fatal === true) {
                        this.error = this.$t('miniPlayer.error')
                        this.$store.commit('miniPlayer_pause')
                    }
                })
                this.hls.loadSource(url)
                this.hls.attachMedia(audio)
                this.hls.on(Hls.Events.MANIFEST_PARSED, () => {
                    this.syncPlay()
                })
            } catch (e) {
                this.error = this.$t('miniPlayer.hlsError')
            }
        },
        syncPlay() {
            const audio = this.$refs.audio
            if (!audio) return
            if (this.track.playing) {
                this.resume()
            } else {
                this.suspend()
            }
        },
        resume() {
            const audio = this.$refs.audio
            if (!audio) return
            // 见 attach 注释：元素常驻，但换源那一拍可能还没落到 DOM 上
            if (!audio.getAttribute('src') && this.track.url) {
                this.attach(this.track.url)
                return
            }
            this.intentPlay = true
            const p = audio.play()
            if (p && p.catch) {
                p.catch((e) => {
                    const name = e && e.name
                    if (name === 'AbortError') {
                        // 被新的 load/seek 打断：只要「想播」的意图还在，稍后再拉一次。
                        // 旧代码在这里直接 return，一旦被打断就永久静音（条仍显示播放中）。
                        if (this.intentPlay && this.playRetries < 3) {
                            this.playRetries += 1
                            if (this._retryTimer) clearTimeout(this._retryTimer)
                            this._retryTimer = setTimeout(() => {
                                this._retryTimer = null
                                if (this.intentPlay && this.track.playing) this.resume()
                            }, 250)
                        }
                        return
                    }
                    // 自动播放被拦截时不要静默：把状态回退给 store，条上显示为暂停
                    this.error = this.$t('miniPlayer.error')
                    this.$store.commit('miniPlayer_pause')
                })
            }
        },
        // 看门狗：只救「store 说在播、元素却没在走」的静默失败（被打断的 play、
        // 移动端挂起、seek 后停在 paused），正常播放时什么都不做。
        _startWatchdog() {
            this._stopWatchdog()
            this._watchdog = setInterval(() => {
                const audio = this.$refs.audio
                if (!audio) return
                if (!this.track.playing || this.error) {
                    this._stuckTicks = 0
                    return
                }
                if (!audio.getAttribute('src')) return
                if (!audio.paused) {
                    this._stuckTicks = 0
                    return
                }
                // 已播完（元素停在末尾）不算卡死：正常路径是 onEnded 自动进下一首。
                // 个别情况下 ended 事件没送达（页面切后台被打断、解码器停在末尾），
                // 这里补一刀，免得"条显示在播、其实停在最后一秒"永远不动。
                if (isFinite(audio.duration) && audio.duration > 0
                    && audio.currentTime >= audio.duration - 0.3) {
                    if (audio.ended === true && this.canSkip
                        && this.track.index < this.track.list.length - 1) {
                        this.step(1)
                    }
                    this._stuckTicks = 0
                    return
                }
                this._stuckTicks = (this._stuckTicks || 0) + 1
                if (this._stuckTicks < 2) return
                this._stuckTicks = 0
                // 连续救不起来（比如浏览器策略直接拒播）就别无限空转：
                // 10 次之后把状态退回暂停，让用户看到「暂停」并手动点一下
                this._wdRescues = (this._wdRescues || 0) + 1
                if (this._wdRescues > 10) {
                    this._wdRescues = 0
                    this.$store.commit('miniPlayer_pause')
                    return
                }
                this.intentPlay = true
                const p = audio.play()
                if (p && p.catch) p.catch(() => { /* 下一次 tick 再试 */ })
            }, 2000)
        },
        _stopWatchdog() {
            if (this._watchdog) {
                clearInterval(this._watchdog)
                this._watchdog = null
            }
            this._stuckTicks = 0
        },
        onVisibility() {
            if (!process.client || document.visibilityState !== 'visible') return
            if (!this.track.playing) return
            const audio = this.$refs.audio
            if (!audio) return
            if (!audio.getAttribute('src') && this.track.url) {
                this.attach(this.track.url)
                return
            }
            if (audio.paused) this.resume()
        },
        suspend() {
            const audio = this.$refs.audio
            if (!audio) return
            this.intentPlay = false
            audio.pause()
        },
        toggle() {
            this.$store.commit('miniPlayer_toggle')
        },
        // 上一首 / 下一首。收起后播放页已销毁，切集只能在这里做：
        // 改 store 里的 index/url/currentTime，由 track.url 的 watcher 重新 attach 起播。
        step(delta) {
            const list = this.track.list || []
            const next = (this.track.index < 0 ? 0 : this.track.index) + delta
            if (next < 0 || next >= list.length) return
            const prevUrl = this.track.url
            this.error = ''
            this.dragging = false
            this.$store.commit('miniPlayer_step', delta)
            // 相邻两集指向同一个文件（同轨切片）时 url 不变，watcher 不会触发，
            // 这里补一次 attach，否则表现为「点了下一首没反应」。
            if (this.track.url === prevUrl) {
                this.attach(this.track.url)
            }
        },
        close() {
            this.suspend()
            this.teardown()
            this.dragging = false
            const audio = this.$refs.audio
            if (audio) {
                try {
                    audio.removeAttribute('src')
                    audio.load()
                } catch (e) { /* 忽略 */ }
            }
            this.$store.commit('miniPlayer_close')
        },
        goToPage() {
            if (!this.track.audioId) return
            this.$router.push('/audio/' + this.track.audioId)
        },
        // 拖动热区与整条等高，按钮在更高层级，点按钮不会触发 seek
        percentFromEvent(e) {
            const track = this.$refs.track
            if (!track || !e) return this.dragPercent
            const rect = track.getBoundingClientRect()
            if (!rect.width) return this.dragPercent
            const p = ((e.clientX - rect.left) / rect.width) * 100
            return Math.max(0, Math.min(100, p))
        },
        onSeekStart(e) {
            if (!this.canSeek) return
            this.dragging = true
            this.dragPercent = this.percentFromEvent(e)
            this.dragTime = (this.dragPercent / 100) * (this.track.duration || 0)
            const track = this.$refs.track
            if (track && track.setPointerCapture && e.pointerId !== undefined) {
                try { track.setPointerCapture(e.pointerId) } catch (err) { /* 忽略 */ }
            }
        },
        onSeekMove(e) {
            if (!this.dragging) return
            this.dragPercent = this.percentFromEvent(e)
            this.dragTime = (this.dragPercent / 100) * (this.track.duration || 0)
        },
        onSeekEnd(e) {
            if (!this.dragging) return
            this.dragPercent = this.percentFromEvent(e)
            this.dragging = false
            const dur = this.track.duration || 0
            // 右端留 0.5s：拖到底不应触发 ended（否则刚拖完就自动暂停）
            const sec = Math.max(0, Math.min(Math.max(0, dur - 0.5), (this.dragPercent / 100) * dur))
            const audio = this.$refs.audio
            if (audio && dur > 0) {
                try { audio.currentTime = sec } catch (err) { /* 忽略 */ }
            }
            // 松手即写回 store：即使随后被切源/收起，进度也不会丢
            this.$store.commit('miniPlayer_progress', { currentTime: sec, duration: dur })
            this.error = ''
            if (this.track.playing) {
                this.resume()
            }
        },
        onTimeUpdate() {
            if (this.dragging) return
            const audio = this.$refs.audio
            if (!audio) return
            const now = Date.now()
            if (now - this.lastEmit < 1000) return
            this.lastEmit = now
            this.$store.commit('miniPlayer_progress', {
                currentTime: audio.currentTime || 0,
                duration: isFinite(audio.duration) ? audio.duration : 0,
            })
        },
        onLoadedMetadata() {
            const audio = this.$refs.audio
            if (!audio) return
            if (audio.playbackRate !== this.track.rate && this.track.rate) {
                audio.playbackRate = this.track.rate
            }
            // duration 只在这里补一次：timeupdate 一秒才来，刚展开时进度条需要立刻可拖
            this.$store.commit('miniPlayer_duration', isFinite(audio.duration) ? audio.duration : 0)
        },
        onPlay() {
            this.playRetries = 0
            this._stuckTicks = 0
            this._wdRescues = 0
            if (!this.intentPlay) {
                this.$store.commit('miniPlayer_resume')
            }
        },
        onPause() {
            if (this.intentPlay) {
                this.intentPlay = false
                return
            }
            if (this.track.playing) {
                this.$store.commit('miniPlayer_pause')
            }
        },
        onEnded() {
            this.intentPlay = false
            // 有声书：这一集播完自动进下一首（收起 / 最小化之后同样生效）。
            // 以前这里直接 miniPlayer_pause，所以最小化听完一集就再也不动了，
            // 而播放页里 onTrackEnded → nextTrack(true) 是好的 —— 差别就在这里。
            if (this.canSkip && this.track.index < this.track.list.length - 1) {
                this.step(1)
                return
            }
            this.$store.commit('miniPlayer_pause')
        },
        onError() {
            this.error = this.$t('miniPlayer.error')
            this.$store.commit('miniPlayer_pause')
        },
    },
}
</script>

<style scoped>
.mini-player-host {
    position: relative;
    z-index: 100;
}

/* 常驻音频元素：保留 1px 尺寸、透明，不用 display:none（个别移动端会因此暂停解码） */
.mini-player-host audio {
    position: absolute;
    width: 1px;
    height: 1px;
    opacity: 0;
    pointer-events: none;
}

.mini-player {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 100;
    background: #ffffff;
    color: rgba(0, 0, 0, 0.87);
    border-top: 1px solid rgba(0, 0, 0, 0.12);
    box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.12);
    padding-bottom: env(safe-area-inset-bottom, 0);
}

/* 深色主题：底色与文字色必须成对改，只改底色会变成白字白底。
   #1e1e1e 与 Vuetify 深色主题的 surface 同值；白字对它的对比度约 16.7:1。 */
.mini-player--dark {
    background: #1e1e1e;
    color: #ffffff;
    border-top-color: rgba(255, 255, 255, 0.12);
    box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.5);
}

/* Vuetify 自带 `.theme--dark.v-btn.v-btn--icon{color:#fff}` 和
   `.theme--dark.v-icon{color:#fff}`（见 69f3449.css），其权重与这里的 scoped
   选择器相同，纯 `inherit` 会随样式表加载顺序失效（按钮/图标依旧是白色）。
   所以必须 !important 强制跟随容器前景色，保证任何主题下前后景成对。 */
.mini-player ::v-deep .v-btn,
.mini-player ::v-deep .v-icon {
    color: inherit !important;
}

/* 高度构成：行 38px + 进度线 2px + 上边框 1px = 41px（与 layouts/default.vue
   给 v-main 补的 padding-bottom 一致，改这里必须同步改那里）。 */
.mini-player-row {
    display: flex;
    align-items: center;
    height: 38px;
    padding: 0 6px;
}

.mini-player-icon {
    margin-right: 4px;
    opacity: 0.7;
    flex: 0 0 auto;
}

.mini-player-title {
    flex: 0 1 auto;
    min-width: 0;
    font-size: 12px;
    font-weight: 500;
    line-height: 18px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 55vw;
}

/* 出现上一首/下一首时（多出一对 24px 按钮）给标题让位，避免手机上把时间挤没 */
.mini-player--skippable .mini-player-title {
    max-width: 44vw;
}

.mini-player-time {
    flex: 0 0 auto;
    font-size: 11px;
    opacity: 0.65;
    margin-left: 8px;
    white-space: nowrap;
}

/* x-small 默认 20x20，这里按 24px 的点击区收缩；权重与 Vuetify 的
   `.v-btn--icon.v-size--x-small{height:20px;width:20px}` 相同，用 !important 锁定，
   避免样式表加载顺序不同导致按钮尺寸漂移、把 38px 行撑破。 */
.mini-player ::v-deep .mini-player-btn {
    width: 24px !important;
    height: 24px !important;
    min-width: 24px !important;
    flex: 0 0 auto;
    margin: 0 1px;
    /* 进度条热区铺满整条，按钮必须压在上面；否则点播放/关闭会变成 seek */
    position: relative;
    z-index: 3;
}

/* 拖动热区：覆盖整条（含行），不改变 41px 布局；触摸时禁止页面滚动 */
.mini-player-track {
    position: absolute;
    left: 0;
    right: 0;
    top: 0;
    bottom: 1px;
    z-index: 2;
    cursor: pointer;
    touch-action: none;
}

/* 电台/时长未知：保留同高的静态线，但不接受手势 */
.mini-player-track--idle {
    cursor: default;
    pointer-events: none;
}

.mini-player-track-line {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 2px;
    background-color: rgba(0, 0, 0, 0.12);
}

.mini-player--dark .mini-player-track-line {
    background-color: rgba(255, 255, 255, 0.18);
}

.mini-player-track-fill {
    position: absolute;
    left: 0;
    bottom: 0;
    height: 2px;
    background: #1976d2;
}

.mini-player--dark .mini-player-track-fill {
    background: #90caf9;
}

.mini-player-track-thumb {
    position: absolute;
    bottom: -4px;
    width: 10px;
    height: 10px;
    margin-left: -5px;
    border-radius: 50%;
    background: #1976d2;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
}

.mini-player--dark .mini-player-track-thumb {
    background: #90caf9;
}

.mini-player-error {
    font-size: 12px;
    color: #d32f2f;
    padding: 0 12px 6px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
</style>
