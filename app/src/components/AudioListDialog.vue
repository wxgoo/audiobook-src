<template>
    <v-dialog :value="open" @input="$emit('update:open', $event)" persistent width="480">
        <v-card class="dialog-border">
            <v-toolbar flat dense dark color="#003153" class="dialog-toolbar">
                {{ $t('book.audioList') }}
                <!-- 诊断入口：连点 5 次标题切换诊断模式，不占正常界面 -->
                <span class="ml-2" style="cursor:default" @click="diagTap">·</span>
                <span v-if="audios.status === audioStatus.PROCESSING && audios.progress && audios.progress.converted_chapters !== undefined"
                      class="ml-2 text-caption">
                    ({{ audios.progress.converted_chapters }}/{{ audios.progress.total_chapters }})
                </span>
                <v-spacer></v-spacer>
                <v-btn color="" text @click="$emit('update:open', false)">{{ $t('common.close') }}</v-btn>
            </v-toolbar>
            <div style="height: 16px;"></div>
            <v-card-text v-if="audios.status === audioStatus.PROCESSING">
                <p style="color: orange darken-4; font-weight: bold;">{{ $t('book.conversionInProgress') }}</p>
                <v-progress-linear
                    v-if="audios.progress && audios.progress.total_chapters > 0"
                    :value="(audios.progress.converted_chapters / audios.progress.total_chapters) * 100"
                    color="primary"
                    height="6"
                ></v-progress-linear>
            </v-card-text>
            <v-card-text v-if="audios.status === audioStatus.FAILED">
                <p style="color: red; font-weight: bold;">{{ $t('book.conversionFailed') }}</p>
                <p style="color: red; font-weight: bold;">
                    {{ audios.progress && audios.progress.error_message ? audios.progress.error_message : $t('book.defaultFailedReason') }}
                </p>
            </v-card-text>
            <v-card-text>
                <p>{{ $t('book.convertToAudioNote') }}</p>
                <div class="audio-scroll-container" style="max-height: 200px; overflow-y: auto; overflow-x: hidden; padding: 12px 12px 0 12px;">
                    <v-row v-for="(audio_item, idx) in audios.audios" :key="'audio-' + idx" class="mb-2">
                        <v-col class='py-0'>
                            <v-btn
                                icon
                                small
                                @click="playAudioFile(audio_item, idx)"
                                :loading="playing_audio_index === idx && audio_loading"
                                :color="playing_audio_index === idx ? 'primary' : 'default'"
                            >
                                <v-icon>{{ playing_audio_index === idx && !audio_paused ? 'mdi-pause' : 'mdi-play' }}</v-icon>
                            </v-btn>
                            <span class="ml-2">{{ audio_item.filename }}</span>
                            <!-- §诊断按钮§ 只在"诊断模式"下出现（弹窗里连按 5 次标题）。
                                 直接用原生 Audio 播同一个 url，绕开本组件所有状态与事件，
                                 用来区分「文件/网络问题」还是「组件状态打架」。 -->
                            <v-btn
                                v-if="diagMode"
                                x-small text color="orange"
                                class="ml-2"
                                @click="diagPlay(audio_item, idx)"
                            >裸播</v-btn>
                            <!-- 上次听到哪：只有存在进度且不是刚从头开始才显示 -->
                            <span v-if="resumeHint(idx)" class="ml-2 text-caption orange--text">
                                {{ $t('book.audioResumeAt') }} {{ fmtTime(resumeHint(idx)) }}
                            </span>
                        </v-col>
                    </v-row>
                </div>
            </v-card-text>
            <!-- 播放进度条：试听也能定位，不用拖整个文件 -->
            <v-card-text v-if="playing_audio_index !== null" class="pt-0">
                <v-slider
                    v-model="sliderPct"
                    @start="onSeekStart"
                    @end="onSeekEnd"
                    :min="0" :max="100" :step="0.1"
                    hide-details
                    dense
                    color="primary"
                ></v-slider>
                <div class="d-flex text-caption grey--text">
                    <span>{{ fmtTime(currentTime) }}</span>
                    <v-spacer></v-spacer>
                    <span>{{ fmtTime(duration) }}</span>
                </div>
            </v-card-text>
            <v-card-actions class="justify-center">
                <v-btn
                    v-if="audios.status === audioStatus.PROCESSING"
                    color="warning"
                    @click="$emit('clear-conversion')"
                >
                    {{ $t('book.cancelConversion') }}
                </v-btn>
                <v-btn
                    v-if="audios.status === audioStatus.CONVERTED"
                    color="error"
                    @click="$emit('clear-conversion')"
                >
                    {{ $t('common.clear') }}
                </v-btn>
                <v-btn
                    v-if="audios.status === audioStatus.CONVERTED && canGenerate"
                    color="primary"
                    @click="$emit('generate-audio')"
                >
                    {{ $t('common.restore') }}
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script>
// 小弹窗（详情页「有声书」）的定位是「试听/管理」，但试听也会听到一半关掉，
// 所以也做进度记忆，和正式播放器（/audio/:id）同一套思路：
//   localStorage 键 = audiobook_preview_<用户>_<书>_<章节url哈希>
// §为什么按章节而非按书§ 弹窗里每章是独立文件，不同章节时长差异大，
// 按书存一个进度会导致「听了第 3 章，再点第 1 章却从第 3 章的位置开始」。
export default {
    name: "AudioListDialog",
    props: {
        open: { type: Boolean, default: false },
        audios: { type: Object, required: true },
        audioStatus: { type: Object, required: true },
        // 书籍 id 与当前用户 id 用于隔离进度；拿不到就退化为不记忆（不强依赖）
        bookId: { type: [Number, String], default: null },
        // 能否「重新生成」：依赖有 EPUB。纯音频导入的书没有 epub，
        // 但列表照样要能看能播，所以只屏蔽生成按钮，不屏蔽整个弹窗。
        canGenerate: { type: Boolean, default: true },
    },
    data() {
        return {
            playing_audio_index: null,
            audio_loading: false,
            audio_paused: false,
            currentTime: 0,
            duration: 0,
            resumeMap: {},
            seekDragging: false,
            sliderPct: 0,
            // 上一次重建 resumeMap 时的列表签名，深比较的廉价替代
            _lastAudiosSig: null,
            // 诊断模式：连点标题 5 次开启，列表出现「裸播」按钮
            diagMode: false,
            _diagTaps: 0,
        };
    },
    created() {
        // §非响应式播放器实例§ 故意不放进 data：Audio 元素上的事件每秒刷新
        // 数次，一旦它成为响应式依赖，任何 timeupdate 都会让整棵子树重新求值，
        // 与 v-slider 的 v-model 互相踩，最后表现为进度被按住不动。
        this._el = null;
    },
    mounted() {
        this.loadResumeMap();
        // pagehide 比 beforeunload 在移动端更可靠（iOS Safari 不触发 beforeunload）
        this._onHide = () => this.saveProgress();
        if (typeof window !== 'undefined') {
            window.addEventListener('pagehide', this._onHide);
        }
    },
    watch: {
        open(val) {
            // §关弹窗即释放播放器§ 组件挂在书详情页上，关弹窗只是 v-dialog 隐藏，
            // 实例不销毁。若不停，音频在后台继续播、解码器一直被占；随后离开
            // 该页再回来，新的播放请求会和遗留的旧播放状态打架，表现就是
            // 「点了没动静，必须 Ctrl+F5」。
            if (!val) {
                this.saveProgress();
                this._teardown();
            } else {
                // §打开时重载进度§ mounted 时 audios 往往还没到（父组件异步取），
                // 旧代码只在那时 loadResumeMap 一次 → 列表为空、resumeMap 永远
                // 是空，于是「有没有听过都从头」，而且后面 saveProgress 写入
                // 的 key 又和读取时不一致。打开弹窗时按最新列表重建一次。
                this.loadResumeMap();
            }
        },
        // §只在列表内容真变了才重建§ 父组件 audios 是整体替换的对象，而且
        // 转换进度轮询每 10 秒会 this.audios = response.audios 重赋一次。若这里
        // 无条件 loadResumeMap()，会给 resumeMap 赋一个新对象引用 → 触发本组件
        // 重渲染 → v-dialog / v-slider 跟着重新计算 → 在播放中表现为 timeupdate
        // 与 canplay 互相打断（Console 里 playing/canplay 每秒钟几百次交替、
        // currentTime 卡在同一个值），即「点播放一动不动」。用签名比对规避。
        'audios.audios': {
            handler() {
                const sig = this._audiosSig();
                if (sig === this._lastAudiosSig) return;
                this._lastAudiosSig = sig;
                this.loadResumeMap();
            },
            deep: false,
        },
        // bookId 也是异步来的（父组件 book && book.id）。它是进度 key 的一部分，
        // 晚到时 loadResumeMap 生成的 key 会与之后 saveProgress 的不一致，
        // 表现同样是「读过也像没读过」。
        bookId(val, old) {
            if (val === old) return;
            this.loadResumeMap();
        },
    },
    beforeDestroy() {
        // 关闭时也要存一次，否则最后几秒的进度会丢
        this.saveProgress();
        if (typeof window !== 'undefined' && this._onHide) {
            window.removeEventListener('pagehide', this._onHide);
        }
        this._teardown();
    },
    methods: {
        // ---------- 诊断 ----------
        diagTap() {
            this._diagTaps += 1;
            if (this._diagTaps >= 5) {
                this._diagTaps = 0;
                this.diagMode = !this.diagMode;
                // eslint-disable-next-line no-console
                console.log('[DIAG] 诊断模式', this.diagMode ? '开启' : '关闭');
            }
        },
        diagPlay(item, idx) {
            // 完全绕开组件状态：原生 Audio 播同一个 url，把每个事件都打出来。
            // 如果这里能正常出声、currentTime 正常前进，就证明文件/网络/后端都没问题，
            // 问题 100% 在本组件的状态管理；反之就是更底层的原因。
            const el = new Audio();
            el.preload = 'auto';
            ['loadstart', 'loadedmetadata', 'canplay', 'playing', 'pause',
             'abort', 'emptied', 'stalled', 'waiting', 'error', 'ended'].forEach((t) => {
                el.addEventListener(t, () => {
                    // eslint-disable-next-line no-console
                    console.log(`[DIAG ${idx}] ${t} t=${(el.currentTime || 0).toFixed(1)} `
                        + `rs=${el.readyState} ns=${el.networkState} `
                        + `err=${el.error ? el.error.code : '-'}`);
                });
            });
            // §异常自检§ 若 currentTime 在连续多次 timeupdate 里都没前进，说明
            // 有东西在不断打断/回滚播放。此时打印调用栈供定位，只打一次免刷屏。
            let _stuckCount = 0;
            let _lastT = -1;
            el.addEventListener('timeupdate', () => {
                const _t = el.currentTime || 0;
                if (Math.abs(_t - _lastT) < 0.01 && !el.paused) {
                    _stuckCount += 1;
                } else {
                    _stuckCount = 0;
                }
                _lastT = _t;
                if (_stuckCount === 3) {
                    // eslint-disable-next-line no-console
                    console.warn('[PLAY] 卡住：t=' + _t.toFixed(2)
                        + ' rs=' + el.readyState + ' ns=' + el.networkState
                        + ' paused=' + el.paused
                        + ' 当前实例=' + (this._el === el)
                        + ' playing_idx=' + this.playing_audio_index
                        + ' stack=' + (new Error().stack || '').split('\n').slice(1, 6).join(' <- '));
                }
                // 每 2 秒打一次，避免刷屏
                this._diagLast = this._diagLast || 0;
                if (el.currentTime - this._diagLast >= 2) {
                    this._diagLast = el.currentTime;
                    // eslint-disable-next-line no-console
                    console.log(`[DIAG ${idx}] timeupdate t=${el.currentTime.toFixed(1)}`
                        + `/${(el.duration || 0).toFixed(1)}`);
                }
            });
            el.src = item.url;
            // eslint-disable-next-line no-console
            console.log('[DIAG] 裸播开始', item.url);
            return el.play().then(() => {
                // eslint-disable-next-line no-console
                console.log('[DIAG] play() 已 resolve');
            }).catch((e) => {
                // eslint-disable-next-line no-console
                console.log('[DIAG] play() 被拒:', e && e.name, e && e.message);
            });
        },
        // ---------- 进度存储 ----------
        _userId() {
            try {
                const st = this.$store && this.$store.state && this.$store.state.user;
                return (st && (st.id || st.username)) || 'guest';
            } catch (e) {
                return 'guest';
            }
        },
        // 列表签名：url 列表拼串。只有章节集合变了才需要重建 resumeMap。
        _audiosSig() {
            const list = (this.audios && this.audios.audios) || [];
            return list.map((it) => (it && it.url) || '').join('|');
        },
        _keyOf(index) {
            const item = (this.audios.audios || [])[index];
            if (!this.bookId || !item) return null;
            // 用 url 生成短哈希，避免把整条路径塞进 key
            const s = String(item.url || item.filename || index);
            let h = 0;
            for (let i = 0; i < s.length; i++) {
                h = (h * 31 + s.charCodeAt(i)) | 0;
            }
            return `audiobook_preview_${this._userId()}_${this.bookId}_${Math.abs(h)}`;
        },
        loadResumeMap() {
            const map = {};
            (this.audios.audios || []).forEach((item, idx) => {
                const key = this._keyOf(idx);
                if (!key) return;
                try {
                    const raw = localStorage.getItem(key);
                    if (!raw) return;
                    const v = JSON.parse(raw);
                    if (typeof v.t === 'number' && v.t > 1) map[idx] = v.t;
                } catch (e) { /* 坏数据忽略 */ }
            });
            this._lastAudiosSig = this._audiosSig();
            // §内容相同就别换引用§ 直接 this.resumeMap = map 每次都是一个新对象，
            // Vue 会认为依赖变了 → 模板重渲染 → 播放中的 v-slider/v-dialog 被
            // 重新求值，进而与 timeupdate 抢着改 currentTime。内容一致时保持原
            // 引用，彻底断掉这条自触发链。
            const old = this.resumeMap || {};
            const oldKeys = Object.keys(old);
            const same = oldKeys.length === Object.keys(map).length
                && Object.keys(map).every((k) => old[k] === map[k]);
            if (!same) this.resumeMap = map;
        },
        saveProgress() {
            const idx = this.playing_audio_index;
            if (idx === null || !this._el) return;
            const key = this._keyOf(idx);
            if (!key) return;
            const t = this._el.currentTime || 0;
            const d = this._el.duration;
            // duration 可能是 NaN（元数据未就绪），此时无法判断"是否听完"，
            // 直接不记，避免把 NaN 写进 localStorage 污染下次续播。
            if (!d || !isFinite(d)) return;
            try {
                // 听完（相差 3 秒内）就清掉，下次从头听；否则记位置。
                // 5 秒内也视为「没真听」——从这种位置续播既无意义，又容易让
                // 浏览器在文件开头附近 seek，AAC 上偶发解码杂音。
                if (d && t >= d - 3) {
                    localStorage.removeItem(key);
                    delete this.resumeMap[idx];
                } else if (t > 5) {
                    localStorage.setItem(key, JSON.stringify({ t: t }));
                    // §同步内存§ 只写 localStorage 不够：同一次打开会话里切走再
                    // 切回来，canplay 读的是内存 resumeMap（mounted 时加载的旧
                    // 值），不同步就会「重开页面才有记忆」。用展开重建保证响应式。
                    this.resumeMap = { ...this.resumeMap, [idx]: t };
                }
            } catch (e) { /* 隐私模式写不进去，忽略 */ }
        },
        resumeHint(idx) {
            return this.resumeMap[idx] || 0;
        },
        fmtTime(sec) {
            const s = Math.max(0, Math.floor(sec || 0));
            const m = Math.floor(s / 60);
            const r = s % 60;
            return `${m}:${String(r).padStart(2, '0')}`;
        },

        // ---------- 播放 ----------
        // §重写说明§ 旧实现把「正在播的元素」放在 data 里（currentAudioFile），
        // 每次 play/stop 都会让它变成响应式依赖，播放器事件又在高频改
        // currentTime/sliderPct，三者互相触发，最后就是 currentTime 被按住不动、
        // 状态灯疯狂闪烁。现在改成：
        //   1) 播放器实例存在组件实例上（非响应式 this._el），事件回调只做纯赋值；
        //   2) 只用一个 playing_audio_index 驱动 UI（谁在播/播放条是否显示）；
        //   3) 所有「换实例」都走 _teardown()，保证旧的先彻底摘干净。
        playAudioFile(audioItem, index) {
            // 点的是当前这条：切换暂停/继续，不动实例
            if (this.playing_audio_index === index && this._el) {
                if (this._el.paused) {
                    this._el.play().catch(() => { /* 忽略 */ });
                    this.audio_paused = false;
                } else {
                    this.saveProgress();
                    this._el.pause();
                    this.audio_paused = true;
                }
                return;
            }
            this.saveProgress();
            this._teardown();

            this.$emit('stop-sample-audio');
            this.playing_audio_index = index;
            this.audio_loading = true;
            this.currentTime = 0;
            this.duration = 0;
            this.sliderPct = 0;
            this.audio_paused = false;

            const el = new Audio();
            this._el = el;
            el.preload = 'auto';

            // §一次性事件载体§ 用 _el 比对，任何「已换实例」的回调立刻失效
            const alive = () => this._el === el;
            let ready = false;

            el.addEventListener('loadstart', () => {
                if (!alive()) return;
                this.audio_loading = true;
            });

            let pendingSeek = 0;
            el.addEventListener('loadedmetadata', () => {
                if (!alive() || ready) return;
                ready = true;
                this.audio_loading = false;
                this.duration = el.duration || 0;

                // 续播位置先记下，但【不在这里 seek】：从 0 直接播是整段 200
                // 请求、一定能出声；而「还没缓冲任何数据就 seek」会让浏览器
                // 立刻发一个中段 Range 请求，某些环境（nginx+网络盘）下这个
                // 请求会迟迟不回，元素永远停在 rs=1（有元数据没数据），表现
                // 就是「进度不动、也没声音」。改成先 play，等缓冲真正到了
                // （canplay / rs>=3）再跳到续播位置——那时浏览器对文件结构
                // 已经有概念，seek 又快又稳。
                const saved = this.resumeMap[index];
                if (saved && el.duration && saved >= 5 && saved < el.duration - 3) {
                    pendingSeek = Math.floor(saved);
                    this.currentTime = pendingSeek;
                    this.sliderPct = (pendingSeek / el.duration) * 100;
                }

                this._safePlay(index);
            });

            // 数据真正到了（可以往后播了）再落地续播 seek。对齐整秒，避免
            // AAC/m4a 从帧中间解码出爆音。
            const applyPendingSeek = () => {
                if (!alive() || !pendingSeek) return;
                if (el.readyState < 3) return; // 数据还没到位，再等等
                const pos = pendingSeek;
                pendingSeek = 0;
                try {
                    if (pos < el.duration - 3) {
                        el.currentTime = pos;
                        this.currentTime = pos;
                        this.sliderPct = (pos / el.duration) * 100;
                    }
                } catch (e) { /* 忽略 */ }
            };
            el.addEventListener('canplay', applyPendingSeek);
            el.addEventListener('playing', applyPendingSeek);

            // §停滞看门狗§ play() 之后 6 秒还没拿到可播数据（rs<3），打日志。
            // 只打一次，用来区分「网络/代理卡」还是「逻辑卡」。
            const watchdog = setTimeout(() => {
                if (alive() && !el.paused && el.readyState < 3) {
                    // eslint-disable-next-line no-console
                    console.warn('[AUDIO] 数据停滞：rs=' + el.readyState
                        + ' ns=' + el.networkState + ' buffered='
                        + (el.buffered.length ? el.buffered.end(0).toFixed(1) : '0')
                        + ' url=' + audioItem.url);
                }
            }, 6000);
            el.addEventListener('ended', () => clearTimeout(watchdog), { once: true });

            // canplay 只负责收 loading 态，绝不在这里 seek
            el.addEventListener('canplay', () => {
                if (!alive()) return;
                this.audio_loading = false;
            });

            el.addEventListener('timeupdate', () => {
                if (!alive()) return;
                const t = el.currentTime || 0;
                const d = el.duration || 0;
                this.currentTime = t;
                if (d && d !== this.duration) this.duration = d;
                if (!this.seekDragging && d) {
                    this.sliderPct = (t / d) * 100;
                }
            });

            el.addEventListener('ended', () => {
                if (!alive()) return;
                const key = this._keyOf(index);
                try { if (key) localStorage.removeItem(key); } catch (e) { /* 忽略 */ }
                this.resumeMap = { ...this.resumeMap, [index]: 0 };
                this._teardown();
            });

            el.addEventListener('error', () => {
                if (!alive()) return;
                const err = el.error;
                // 404/403 这类真错误才弹框；MEDIA_ERR_ABORTED(1) 是我们自己停的
                if (err && err.code !== 1) {
                    // eslint-disable-next-line no-console
                    console.error('[AUDIO] 加载失败', index, audioItem.url, err.code, err.message);
                    this._teardown();
                    this.$alert("error", this.$t('message.audioLoadFailed'));
                }
            });

            // 事件全部就位后才赋 src：否则 src 同步推进 readyState，后面那个
            // "readyState>=1 兜底" 会在事件还没绑好时抢跑。
            el.src = audioItem.url;
            // 命中缓存时可能已经同步就绪（readyState>=1），此时不一定再派发
            // loadedmetadata。手动补一次，但必须先确认 duration 有效，否则
            // 会在 NaN 上算进度。
            if (el.readyState >= 1) {
                if (isFinite(el.duration) && el.duration > 0) {
                    el.dispatchEvent(new Event('loadedmetadata'));
                } else {
                    // duration 还没算出来，等真正的 loadedmetadata
                    el.addEventListener('durationchange', () => {
                        if (alive() && !ready && isFinite(el.duration) && el.duration > 0) {
                            el.dispatchEvent(new Event('loadedmetadata'));
                        }
                    });
                }
            }
        },
        _safePlay(index) {
            const el = this._el;
            if (!el) return;
            const p = el.play();
            if (!p || !p.then) return;
            p.then(() => {
                if (this._el !== el) return;
                this.audio_paused = false;
                this.audio_loading = false;
            }).catch((err) => {
                if (this._el !== el) return;
                const name = err && err.name;
                // AbortError：被主动打断（换章节/关弹窗），属正常
                if (name === 'AbortError') return;
                // NotAllowedError：浏览器自动播放策略，等用户手势即可，不弹框
                if (name === 'NotAllowedError') {
                    this.audio_paused = true;
                    this.audio_loading = false;
                    return;
                }
                // eslint-disable-next-line no-console
                console.error('[AUDIO] play() 失败', index, name, err && err.message);
                this._teardown();
                this.$alert("error", this.$t('message.audioPlayFailed'));
            });
        },
        _teardown() {
            const el = this._el;
            if (el) {
                // 先摘引用，让所有 alive() 立即失效，后续事件全是空操作
                this._el = null;
                try {
                    el.pause();
                    // 只清 src 不调 load()：load() 会立刻重新初始化一遍解码器，
                    // 与紧接着新建的 Audio 叠加，AAC 上就是爆音/电流声。
                    el.removeAttribute('src');
                } catch (e) { /* 忽略 */ }
            }
            this.playing_audio_index = null;
            this.audio_loading = false;
            this.audio_paused = false;
            this.currentTime = 0;
            this.duration = 0;
            this.sliderPct = 0;
            this.seekDragging = false;
        },

        onSeekStart() {
            this.seekDragging = true;
        },
        onSeekEnd() {
            // v-model 已把最终百分比写进 sliderPct；松手时一次性 seek。
            // 拖动期间不实时 seek：高频 seek 大文件会打乱解码流（AAC 出杂音）。
            const pct = this.sliderPct;
            this.seekDragging = false;
            if (this._el && this.duration) {
                this._el.currentTime = (pct / 100) * this.duration;
            }
        },
    },
    computed: {
        progressPct() {
            return this.duration ? (this.currentTime / this.duration) * 100 : 0;
        },
    },
};
</script>
