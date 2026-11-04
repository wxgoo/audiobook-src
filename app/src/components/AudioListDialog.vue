<template>
    <v-dialog :value="open" @input="$emit('update:open', $event)" persistent width="480">
        <v-card class="dialog-border">
            <v-toolbar flat dense dark color="#003153" class="dialog-toolbar">
                {{ $t('book.audioList') }}
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
            currentAudioFile: null,
            currentTime: 0,
            duration: 0,
            resumeMap: {},
            seekDragging: false,
            sliderPct: 0,
        };
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
                this.stopAudioFilePlayback();
            } else {
                // §打开时重载进度§ mounted 时 audios 往往还没到（父组件异步取），
                // 旧代码只在那时 loadResumeMap 一次 → 列表为空、resumeMap 永远
                // 是空，于是「有没有听过都从头」，而且后面 saveProgress 写入
                // 的 key 又和读取时不一致。打开弹窗时按最新列表重建一次。
                this.loadResumeMap();
            }
        },
        'audios.audios': {
            handler() { this.loadResumeMap(); },
            deep: false,
        },
        // bookId 也是异步来的（父组件 book && book.id）。它是进度 key 的一部分，
        // 晚到时 loadResumeMap 生成的 key 会与之后 saveProgress 的不一致，
        // 表现同样是「读过也像没读过」。
        bookId() { this.loadResumeMap(); },
    },
    beforeDestroy() {
        // 关闭时也要存一次，否则最后几秒的进度会丢
        this.saveProgress();
        if (typeof window !== 'undefined' && this._onHide) {
            window.removeEventListener('pagehide', this._onHide);
        }
        this.stopAudioFilePlayback();
    },
    methods: {
        // ---------- 进度存储 ----------
        _userId() {
            try {
                const st = this.$store && this.$store.state && this.$store.state.user;
                return (st && (st.id || st.username)) || 'guest';
            } catch (e) {
                return 'guest';
            }
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
            this.resumeMap = map;
        },
        saveProgress() {
            const idx = this.playing_audio_index;
            if (idx === null || !this.currentAudioFile) return;
            const key = this._keyOf(idx);
            if (!key) return;
            const t = this.currentAudioFile.currentTime || 0;
            const d = this.currentAudioFile.duration || 0;
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
        playAudioFile(audioItem, index) {
            if (this.playing_audio_index === index && this.currentAudioFile) {
                if (this.audio_paused) {
                    this.currentAudioFile.play();
                    this.audio_paused = false;
                } else {
                    this.saveProgress();
                    this.currentAudioFile.pause();
                    this.audio_paused = true;
                }
                return;
            }
            this.saveProgress();
            this.stopAudioFilePlayback();
            this.$emit('stop-sample-audio');
            this.audio_loading = true;
            this.playing_audio_index = index;
            this.currentTime = 0;
            this.duration = 0;
            const el = new Audio();
            // preload='auto' 而不是默认的 'metadata'：低码率 mp3（如 16kHz/32kbps
            // 的教材配套音频）边播边下时，metadata 模式会让浏览器频繁重新估算
            // 缓冲，Chrome 上表现为声音「发抖」。整段预取掉就没这问题（文件都很小）。
            el.preload = 'auto';
            el.src = audioItem.url;
            this.currentAudioFile = el;

            el.addEventListener('loadstart', () => { this.audio_loading = true; });
            // §先定位再播放§ 合并成一个 onReady：先应用续播 seek，再调 play()。
            // 旧写法在 canplay 里 seek：play() 请求已发出，seek 又触发新的 load
            // → 打断 play()（AbortError: interrupted by a new load request），
            // 随后 seek 完又 canplay → 再 seek → 无限循环（Console 里 canplay
            // 35.0/34.9 交替刷屏，表现为「一动不动」）。
            let played = false;
            const onReady = () => {
                if (this.currentAudioFile !== el || played) return;
                played = true;
                this.audio_loading = false;
                if (!el._resumeApplied) {
                    el._resumeApplied = true;
                    const saved = this.resumeMap[index];
                    if (saved && el.duration && saved < el.duration - 3 && saved >= 5) {
                        try {
                            el.currentTime = Math.floor(saved);
                            this.sliderPct = (Math.floor(saved) / el.duration) * 100;
                            this.currentTime = Math.floor(saved);
                        } catch (e) { /* 忽略 */ }
                    }
                }
                el.play().then(() => {
                    this.audio_paused = false;
                }).catch((err) => {
                    // 被新的切换打断属正常，不弹错误框
                    if (err && err.name === 'AbortError') return;
                    this.stopAudioFilePlayback();
                    this.$alert("error", this.$t('message.audioPlayFailed'));
                });
            };
            el.addEventListener('loadedmetadata', onReady, { once: true });
            el.addEventListener('canplay', () => {
                if (this.currentAudioFile !== el) return;
                this.audio_loading = false;
            });
            el.addEventListener('timeupdate', () => {
                this.currentTime = el.currentTime || 0;
                this.duration = el.duration || 0;
                // 播放推进时同步滑块；用户正在拖动时不要覆盖他的位置
                if (!this.seekDragging && this.duration) {
                    this.sliderPct = (this.currentTime / this.duration) * 100;
                }
            });
            el.addEventListener('ended', () => {
                const key = this._keyOf(index);
                try { if (key) localStorage.removeItem(key); } catch (e) { /* 忽略 */ }
                delete this.resumeMap[index];
                this.stopAudioFilePlayback();
            });
            el.addEventListener('error', () => {
                // 只处理「当前正在播」的实例报错；旧实例被 stop 时清 src/load()
                // 也会触发 error，别让它误停新播放器、误弹错误框
                if (this.currentAudioFile !== el) return;
                this.stopAudioFilePlayback();
                this.$alert("error", this.$t('message.audioLoadFailed'));
            });
            // 元数据可能已经就绪（如命中缓存），此时不会再有 loadedmetadata 事件
            if (el.readyState >= 1) {
                onReady();
            }
        },
        stopAudioFilePlayback() {
            if (this.currentAudioFile) {
                const el = this.currentAudioFile;
                // 先摘掉引用，让各事件回调的「是否当前实例」校验立刻失效，
                // 避免下面 pause/清 src 触发的事件打到新播放器上。
                this.currentAudioFile = null;
                try {
                    el.pause();
                    // 只清 src 不 load()：load() 会立刻触发 drained/error 并重新
                    // 初始化解码器，紧接着又 new 一个 Audio，短时间内两套解码器
                    // 叠加，AAC 上表现为爆音/电流声。浏览器在引用释放后自会回收。
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
            if (this.currentAudioFile && this.duration) {
                this.currentAudioFile.currentTime = (pct / 100) * this.duration;
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
