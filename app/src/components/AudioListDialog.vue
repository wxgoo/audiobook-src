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
                    :value="progressPct"
                    @input="onSeekInput"
                    @start="seekDragging = true"
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
                } else if (t > 5) {
                    localStorage.setItem(key, JSON.stringify({ t: t }));
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
            el.addEventListener('canplay', () => {
                if (this.currentAudioFile !== el) return;
                this.audio_loading = false;
                // 恢复上次进度：只在真的拿到时长之后再设，否则会被浏览器的
                // 元数据刷新打回 0（这是 HTMLAudio 常见的坑）。
                // §只在暂停态恢复§ 若此时已经在播（play() 已 resolve），再 seek
                // 会打断解码器当前帧边界——AAC 从半帧开始解码就是「电流声」。
                // 所以仅在尚未开始播放时恢复。
                const saved = this.resumeMap[index];
                if (!saved || !el.duration || el.paused === false) return;
                if (saved >= el.duration - 3 || saved < 2) return;
                // 对齐到整秒，避免落在帧中间
                try { el.currentTime = Math.floor(saved); } catch (e) { /* 忽略 */ }
            });
            el.addEventListener('timeupdate', () => {
                this.currentTime = el.currentTime || 0;
                this.duration = el.duration || 0;
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
            el.play().then(() => {
                this.audio_loading = false;
                this.audio_paused = false;
            }).catch(() => {
                this.stopAudioFilePlayback();
                this.$alert("error", this.$t('message.audioPlayFailed'));
            });
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
        },
        onSeekInput(pct) {
            // §防回环§ Vuetify v-slider 在外部 :value 变化时也会 emit input：
            // 回环 emit 会被这里挡掉（非拖动状态一律忽略）。
            // §不实时 seek§ 拖动期间高频 seek 大文件会打乱解码流（表现为
            // 拖过一次之后出现电流声），所以拖动中只记录位置，松手才 seek。
            if (!this.seekDragging) return;
            this._pendingSeek = pct;
        },
        onSeekEnd() {
            this.seekDragging = false;
            const pct = this._pendingSeek;
            this._pendingSeek = null;
            if (pct !== null && pct !== undefined && this.currentAudioFile && this.duration) {
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
