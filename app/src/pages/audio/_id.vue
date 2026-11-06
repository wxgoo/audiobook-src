<template>
  <div class="audio-player-container">
    <!-- 上方区域 60% -->
    <div class="audio-upper-section">
      <!-- 左侧：封面 / 整篇字幕 双视图，可切换 -->
      <div class="cover-section" :class="{ 'lyrics-mode': showLyrics }">
        <!-- 视图切换按钮：带文字，否则图标贴在播放列表旁边会被当成列表控件 -->
        <v-btn
          v-if="subtitleCues.length > 0"
          small
          rounded
          class="view-toggle-btn"
          :title="showLyrics ? $t('audio.showCover') : $t('audio.showLyrics')"
          @click="toggleLyricsView"
        >
          <v-icon small left>{{ showLyrics ? 'mdi-image' : 'mdi-subtitles' }}</v-icon>
          <span class="toggle-label">{{ showLyrics ? $t('audio.showCover') : $t('audio.showLyrics') }}</span>
        </v-btn>

        <!-- 封面视图 -->
        <div v-show="!showLyrics" class="cover-container">
          <v-img
            :src="book.img"
            :aspect-ratio="3/4"
            class="book-cover"
            @click="gotoBookDetail()"
            contain
          ></v-img>
          <div class="book-info">
            <h2 class="book-title">{{ book.title }}</h2>
            <p v-if="shouldShowAuthors" class="book-author">{{ book.authors }}</p>
          </div>
        </div>

        <!-- 整篇字幕：全量渲染，当前句高亮并自动跟随滚动。
             以前是 20 行窗口，等于人为裁掉上下文，听书时想回看上一句很别扭。
             全量渲染的顾虑是上千行节点的布局开销，这里用
             content-visibility: auto 让浏览器跳过屏幕外行的排版，
             配合按需分段加载（见字幕分段逻辑）控制首屏规模。 -->
        <div v-show="showLyrics" class="lyrics-container" ref="lyricsBox">
          <div
            v-for="(cue, i) in renderedCues"
            :key="'cue-' + i"
            :ref="'cue-' + i"
            class="lyric-line"
            :class="{
              'active': i === currentCueIndex,
              'past': i < currentCueIndex
            }"
            @click="seekToCue(cue)"
          >{{ cue.text }}</div>
        </div>
      </div>

      <!-- 右侧音频列表 -->
      <div class="playlist-section">
        <div class="playlist-header">
          <h3>{{ $t('audio.playlist') }}</h3>
          <div class="playlist-controls">
            <v-chip v-if="audioFiles.length > 0" small outlined class="chapter-info">
              {{ currentTrackIndex + 1 }}/{{ audioFiles.length }}
            </v-chip>
            <v-btn
              v-if="!isPaid && audioFiles.length > 0"
              small
              color="orange darken-4"
              @click="showPurchaseDialogWithVipInfo"
              class="purchase-btn"
              :loading="purchaseLoading"
            >
              <v-icon small left>mdi-cart</v-icon>
              {{ $t('audio.purchase') }}
            </v-btn>
            <v-btn
              small
              outlined
              @click="downloadCollection"
              class="download-btn"
              :disabled="audioFiles.length === 0 || !isPaid"
              :loading="downloadLoading"
            >
              <v-icon small left>mdi-download</v-icon>
              {{ $t('audio.downloadCollection') }}
            </v-btn>
            <v-btn
              small
              outlined
              @click="closePlayer"
              class="close-btn"
            >
              <v-icon small left>mdi-close</v-icon>
              {{ $t('common.close') }}
            </v-btn>
          </div>
        </div>

        <div class="playlist-container" v-if="audioFiles.length > 0">
          <div
            v-for="(audio, index) in audioFiles"
            :key="index"
            class="playlist-item"
            :class="{
              'active': currentTrackIndex === index,
              'locked': !isPaid && index >= 5
            }"
            @click="selectTrack(index)"
          >
            <div class="track-number">{{ index + 1 }}</div>
            <div class="track-info">
              <div class="track-title">{{ getDisplayName(audio.filename) }}</div>
              <div class="track-duration">
                {{ formatFileSize(audio.size) }}
                <!-- 上次听到哪：与详情页弹窗同一份每集记忆 -->
                <span v-if="resumeHintOf(index) > 1
                            && !(currentTrackIndex === index && isPlaying)"
                      class="resume-hint">· 上次 {{ formatTime(resumeHintOf(index)) }}</span>
              </div>
            </div>
            <v-chip
              v-if="!isPaid && index >= 5"
              x-small
              color="blue darken-2"
              text-color="yellow"
              class="vip-badge"
            >
              VIP
            </v-chip>
            <v-icon v-else-if="currentTrackIndex === index && isPlaying" color="primary">
              mdi-volume-high
            </v-icon>
          </div>
        </div>

        <!-- 未购买提示信息 -->
        <div v-if="!isPaid && audioFiles.length > 0" class="purchase-hint">
          <v-alert
            type="info"
            outlined
            dense
            class="ma-2"
          >
            {{ $t('audio.purchaseHint') }}
          </v-alert>
        </div>

        <div  v-if="audioFiles.length == 0" class="no-audio-message">
          <v-icon large color="grey">mdi-headphones-off</v-icon>
          <p>{{ $t('audio.noAudioFiles') }}</p>
        </div>
      </div>
    </div>

    <!-- 下方播放控制条 40% -->
    <div class="audio-controls-section">
      <!-- 进度条 -->
      <div class="progress-section">
        <div class="time-display">
          <span>{{ formatTime(currentTime) }}</span>
          <span>{{ formatTime(duration) }}</span>
        </div>
        <v-slider
          ref="progressSlider"
          v-model="progress"
          :max="100"
          hide-details
          @change="seekTo"
          @start="isDragging = true"
          @end="isDragging = false"
          class="progress-slider"
        ></v-slider>
      </div>

      <!-- 控制按钮 -->
      <div class="controls-section">
        <div class="main-controls">
          <!-- 上一首 -->
          <v-btn
            icon
            large
            @click="previousTrack"
            :disabled="currentTrackIndex <= 0"
            class="control-btn nav-btn"
          >
            <v-icon>mdi-skip-previous</v-icon>
          </v-btn>

          <!-- 播放/暂停 -->
          <v-btn
            icon
            x-large
            @click="togglePlay"
            :disabled="!currentAudio"
            class="play-btn"
          >
            <v-icon>{{ isPlaying ? 'mdi-pause' : 'mdi-play' }}</v-icon>
          </v-btn>

          <!-- 下一首 -->
          <v-btn
            icon
            large
            @click="nextTrack"
            :disabled="currentTrackIndex >= audioFiles.length - 1"
            class="control-btn nav-btn"
          >
            <v-icon>mdi-skip-next</v-icon>
          </v-btn>
        </div>

        <div class="secondary-controls">
          <!-- 字幕开关 -->
          <v-btn
            v-if="subtitleCues.length > 0"
            icon
            large
            @click="toggleSubtitle"
            class="subtitle-btn"
            :color="showSubtitle ? 'primary' : ''"
          >
            <v-icon>{{ showSubtitle ? 'mdi-subtitles' : 'mdi-subtitles-outline' }}</v-icon>
          </v-btn>

          <!-- 倍速控制 -->
          <v-menu offset-y>
            <template v-slot:activator="{ on, attrs }">
              <v-btn
                icon
                large
                v-bind="attrs"
                v-on="on"
                class="speed-btn"
              >
                <v-icon>mdi-speedometer</v-icon>
                <span class="speed-text">{{ playbackRate }}x</span>
              </v-btn>
            </template>
            <v-list>
              <v-list-item
                v-for="rate in playbackRates"
                :key="rate"
                @click="setPlaybackRate(rate)"
              >
                <v-list-item-title>{{ rate }}x</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-menu>

          <!-- 定时关闭 -->
          <v-menu offset-y>
            <template v-slot:activator="{ on, attrs }">
              <v-btn
                icon
                large
                v-bind="attrs"
                v-on="on"
                class="timer-btn"
                :color="sleepTimer ? 'primary' : ''"
              >
                <v-icon>{{ sleepTimer ? 'mdi-timer' : 'mdi-timer-outline' }}</v-icon>
              </v-btn>
            </template>
            <v-list>
              <v-list-item @click="setSleepTimer(null)">
                <v-list-item-title>{{ $t('audio.timerOff') }}</v-list-item-title>
              </v-list-item>
              <v-list-item
                v-for="timer in sleepTimers"
                :key="timer.value"
                @click="setSleepTimer(timer)"
              >
                <v-list-item-title>{{ timer.label }}</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-menu>
        </div>
        <div>
          <v-btn color="error" @click="openDeleteDialog" class="delete-btn" style="margin-top: 10px;">
            <v-icon>mdi-delete</v-icon>{{ $t('audio.audioDelete') }}
          </v-btn>
        </div>
      </div>
    </div>

    <!-- 隐藏的音频元素 -->
    <audio
      ref="audioPlayer"
      @loadedmetadata="onLoadedMetadata"
      @timeupdate="onTimeUpdate"
      @ended="onTrackEnded"
      @play="onPlay"
      @pause="onPause"
      @error="onAudioError"
      @stalled="onAudioStalled"
      @progress="onAudioProgress"
      preload="auto"
    ></audio>

    <!-- VIP信息对话框 -->
    <AppDialog
      v-model="showVipDialog"
      :persistent="false"
      type="action"
      :title="vipDialogTitle"
      max-width="600px"
      :dismiss-label="$t('common.close')"
      hide-footer-button
    >
      <div v-html="vipDialogContent"></div>
    </AppDialog>

    <!-- 购买确认对话框 -->
    <AppDialog
      v-model="showPurchaseDialog"
      :persistent="false"
      type="confirm"
      :title="$t('audio.confirmPurchase')"
      color="orange darken-4"
      confirm-dark
      max-width="400px"
      :confirm-text="$t('audio.confirmPurchase')"
      :confirm-loading="purchaseLoading"
      @confirm="purchaseAudio"
    >
      <p>{{ $t('audio.purchaseDescription', { title: book.title }) }}</p>
      <p class="price-text">{{ $t('audio.price') }}1个额度</p>
    </AppDialog>

    <!-- 删除确认对话框 -->
    <AppDialog
      v-model="showDeleteDialog"
      :persistent="false"
      type="confirm"
      :title="$t('audio.audioDelete')"
      color="deep-orange"
      confirm-dark
      max-width="400px"
      :confirm-text="$t('common.delete')"
      :confirm-loading="deleteLoading"
      @confirm="deleteAudio"
    >
      <p>{{ $t('audio.deleteDescription', { title: book.title }) }}</p>
    </AppDialog>
  </div>
</template>

<script>
export default {
  async asyncData({ params, app }) {
    const bookId = params.id;

    try {
      // 获取书籍信息
      const bookResponse = await app.$backend(`/book/${bookId}`);
      if (bookResponse.err !== 'ok') {
        throw new Error(bookResponse.msg || '书籍不存在');
      }

      // 获取音频文件列表
      const audioResponse = await app.$backend(`/audio/${bookId}`);

      return {
        book: bookResponse.book,
        audioFiles: audioResponse.audios || [],
        audioStatus: audioResponse.status || 'unavailable',
        bookId: bookId,
        isPaid: audioResponse.is_paid || false
      };
    } catch (error) {
      console.error('Error loading audio data:', error);
      return {
        book: {},
        audioFiles: [],
        audioStatus: 'unavailable',
        bookId: params.id,
        isPaid: false
      };
    }
  },

  head() {
    return {
      title: `${this.book.title || ''} - ${this.$t('audio.audioBook')}`,
      bodyAttrs: {
        class: 'audio-player-page'
      }
    };
  },

  data() {
    return {
      // 播放状态
      isPlaying: false,
      currentTrackIndex: 0,
      currentTime: 0,
      duration: 0,
      progress: 0,
      isDragging: false,
      // 每集记忆（与详情页弹窗同一套 key）：{集序号: 相对秒}。
      // 弹窗是「每集一条」，播放页此前只有「整本一条」（audio_progress_*），
      // 切集就会把上一集的恢复点覆盖掉，两边也因此对不上。现在播放页
      // 切集/心跳时同步写每集 key，弹窗打开时即可读到（反之亦然）。
      trackResumeMap: {},

      // 音频设置
      playbackRate: 1,
      playbackRates: [0.5, 1, 1.25, 1.5, 2],

      // 字幕相关
      subtitleCues: [],
      currentCueIndex: -1,
      showSubtitle: true,
      subtitleCache: {},
      // 整篇字幕视图（覆盖封面位置，当前句高亮 + 自动跟随滚动）
      showLyrics: false,
      // 整篇字幕的分段加载：首屏渲染 SEGMENT_SIZE 行，当前句接近已渲染末尾时
      // 再追加一段。避免上千行一次性排版导致打开卡顿。
      renderLimit: 300,
      segmentSize: 300,

      // 定时器
      sleepTimer: null,
      sleepTimerInterval: null,
      sleepTimers: [
        { value: 'current', label: this.$t('audio.currentChapter') },
        { value: 15, label: this.$t('audio.timer15min') },
        { value: 30, label: this.$t('audio.timer30min') },
        { value: 60, label: this.$t('audio.timer1hour') }
      ],

      // 播放位置记录
      saveProgressInterval: null,
      bookId: null,

      // 下载相关
      downloadLoading: false,
      showVipDialog: false,
      vipDialogTitle: '',
      vipDialogContent: '',

      // 购买相关
      purchaseLoading: false,
      isPaid: false,
      showPurchaseDialog: false,

      // 删除相关
      deleteLoading: false,
      showDeleteDialog: false
    };
  },

  computed: {
    currentAudio() {
      return this.audioFiles[this.currentTrackIndex];
    },

    // 字幕窗口边界：当前句居中，上下各 (size-1)/2 行。
    // 还没定位到任何句（currentCueIndex=-1）时把窗口放在开头，避免一片空白。
    /** 整篇字幕：全量显示，不再裁成 20 行窗口。
     *
     * 分段加载：整章字幕可能上千行，一次性渲染会有明显卡顿（每行都要排版）。
     * 这里按 SEGMENT_SIZE 段渲染，当前句进入后段时再追加下一段——
     * 用户感觉不到，但首屏只排几百行。
     *
     * 关键：已渲染的段不回收。回收会让上方内容塌陷、滚动位置跳变，
     * 已经滚过去的内容应该留着（用户可能往回翻）。
     */
    renderedCues() {
      const end = Math.min(this.renderLimit, this.subtitleCues.length);
      return this.subtitleCues.slice(0, end);
    },

    currentCue() {
      if (this.currentCueIndex >= 0 && this.currentCueIndex < this.subtitleCues.length) {
        return this.subtitleCues[this.currentCueIndex];
      }
      return null;
    },

    shouldShowAuthors() {
      // 如果作者信息不存在，隐藏
      if (!this.book.authors) {
        return false;
      }

      // 如果作者只有一个元素且是 "Unknown"，隐藏
      if (this.book.authors[0] === 'Unknown') {
        return false;
      }

      return true;
    }
  },

  mounted() {
    // 非响应式内部状态（故意不放进 data，避免无谓重渲染）。
    // _posGen：loadTrack 的代数，用来作废在飞的位置重试回调。
    this._posGen = 0;
    this._positionAppliedFor = -1;
    this._wantPlay = false;
    this._wdStuckTicks = 0;
    this._wdReloads = 0;
    this.restoreSubtitlePreference();
    // 移动端没有封面视图，默认直接展示字幕整篇；用户手动关掉过的尊重用户选择
    if (this.$vuetify.breakpoint.smAndDown && process.client) {
      try {
        if (localStorage.getItem('audio_lyrics_view') === null) {
          this.showLyrics = true;
        }
      } catch (error) {
        this.showLyrics = true;
      }
    }
    // §顺序关键§ 必须先尝试恢复播放位置，再决定要不要从第 0 集开头加载。
    // 反过来会先 load 一遍再 seek 一遍，两次操作互相打断（见 loadTrack 注释）。
    const restored = this.restorePlaybackPosition();
    if (!restored) {
      this.loadTrack(0);
    }
    // 每集记忆（与弹窗互通）：进页读一次，之后随保存实时更新
    this._loadTrackResumeMap();
    // 4.6.0-19：服务端进度（跨设备续播）。本地没有记录、或本地的比服务端
    // 旧时，跳到服务端保存的位置——两台设备轮流听也能接上。
    this.tryRestoreFromServer(restored);
    this.startProgressSaving();
    this.escKeyListener = (event) => {
      if (event.key === 'Escape' || event.keyCode === 27) {
        this.closePlayer();
      }
    };
    window.addEventListener('keyup', this.escKeyListener);
    this._startWatchdog();
  },

  beforeDestroy() {
    this.savePlaybackPosition();
    this.pushServerProgress(true, true);  // 离开页面：keepalive，别被文档卸载取消
    this.clearSleepTimer();
    this.stopProgressSaving();
    this._stopWatchdog();
    this._wantPlay = false;
    if (this.$refs.audioPlayer) {
      // §顺序：先清 src 再 load()§ 只调 pause() 的话，进行中的媒体拉取不会
      // 中止，元素在页面销毁后还持有连接和解码器（网络盘上是很贵的资源）。
      const player = this.$refs.audioPlayer;
      player.pause();
      try {
        player.removeAttribute('src');
        player.load();   // 必须 load()，否则已发出的请求不会被中止
      } catch (e) { /* 忽略 */ }
    }
    window.removeEventListener('keyup', this.escKeyListener);
  },

  methods: {
    initializePlayer() {
      if (this.audioFiles.length > 0) {
        // §不再在这里 loadTrack§ 旧代码 initializePlayer() 先 loadTrack(0)，
        // 紧接着 restorePlaybackPosition() 又 loadTrack(同一集, 上次时间)：
        // 第二次进来 isSameFile 为 true，于是「刚 load() 就写 currentTime」，
        // 打断加载 → loadedmetadata 再触发 → 再写 currentTime … 播放器永远
        // 起不来，表现就是「点播放一动不动，必须 Ctrl+F5」。真正的首次加载
        // 交给 restorePlaybackPosition() 统一决定（有记录就恢复到该集该位置，
        // 没记录就从第 0 集开头）。
      }
    },

    // 真正的「切集/定位」入口。targetTime 是相对章节的秒数（不含 start_time）
    loadTrack(index, initialTime = null) {
      if (!(index >= 0 && index < this.audioFiles.length)) return;
      const player = this.$refs.audioPlayer;
      if (!player) return;

      // §换集先杀旧的重试链§ applyPosition 的重试是 setTimeout 递归，最多
      // 20×250ms=5s。旧代码只靠 `this.currentTrackIndex !== index` 守卫：
      // 用户在这 5s 内又切回同一集（上一集/下一集来回点）时守卫失效，
      // 旧链会把「上一轮的目标位置」写进新加载的媒体 → 定位错乱。
      // 用代数（_posGen）作废所有在飞的回调，比逐个 clearTimeout 可靠。
      this._posGen = (this._posGen || 0) + 1;
      const gen = this._posGen;

      this.currentTrackIndex = index;
      const audio = this.audioFiles[index];
      this.loadSubtitle(audio.subtitle);

      const base = audio.start_time || 0;
      const rel = (initialTime !== null && initialTime > 0) ? initialTime : 0;
      // 对齐整秒：非整秒位置会让 AAC/m4a 从帧中间解码，听感是爆音/电流声
      const targetTime = Math.floor(rel) + base;

      const curSrc = player.getAttribute('src') || '';
      const isSameFile = !!audio.url && curSrc === audio.url;

      // §统一的 seek 落地§ 与弹窗同策略：不在 loadedmetadata（rs=1，还没有
      // 任何数据）就 seek——那时 seek 会立刻发一个中段 Range 请求，网络盘
      // 环境下可能迟迟不回，元素永远 rs=1。等 canplay（rs>=3，真有数据了）
      // 再跳。play() 由调用方/用户手势触发，不在这里抢。
      //
      // §不能"试一次就扔"§ 这一版曾经只绑一次 canplay：只要那一下 readyState
      // 还没到 3（canplay 抢在数据到位前触发、或者中途被 seek/换源打断成 1），
      // applyPosition 就直接 return，监听器已经 auto-remove，续播位置永久丢失。
      // 用户看到的是「进度条 0:00，点播放从头开始」——而且这次失败没有任何日志。
      // 现在改成带重试的版本：失败不吞掉，退避重试，并给一个硬上限。
      let tries = 0;
      const applyPosition = () => {
        if (gen !== this._posGen) return;      // 已换集：本轮作废
        if (this.currentTrackIndex !== index) return;
        // 目标位置已经被别处设好了（用户已拖动过进度条），别再抢方向盘
        if (this._positionAppliedFor === index
            && Math.abs((player.currentTime || 0) - targetTime) > 2) {
          return;
        }
        if (player.readyState < 3) {
          // 数据还没到。别放弃：canplay 之后紧跟的 canplaythrough 会再来一次，
          // 这里再兜一层定时重试，覆盖「canplay 根本没再触发」的情况。
          if (tries++ < 20) {
            setTimeout(applyPosition, 250);
          }
          return;
        }
        try {
          if (targetTime > 0 && isFinite(player.duration)
              && targetTime < player.duration - 1) {
            player.currentTime = targetTime;
            // 把恢复的位置立刻反映到界面：暂停状态下进度条/时间也显示
            // 上次听到的地方，而不是 0:00（否则看起来像"没记忆"）。
            this.currentTime = Math.max(0, targetTime - base);
            if (this.duration > 0) {
              this.progress = (this.currentTime / this.duration) * 100;
            }
          }
          this._positionAppliedFor = index;
        } catch (e) { /* 忽略 */ }
        this.syncDurationFromAudio(audio, player);
      };

      if (isSameFile) {
        const alreadyThere = player.readyState >= 1
          && Math.abs((player.currentTime || 0) - targetTime) < 0.75;
        if (alreadyThere) {
          this.syncDurationFromAudio(audio, player);
          return;
        }
        if (player.readyState >= 3) {
          applyPosition();
        } else {
          player.addEventListener('canplay', applyPosition, { once: true });
          player.addEventListener('canplaythrough', applyPosition, { once: true });
          setTimeout(applyPosition, 400);
        }
        return;
      }

      this._positionAppliedFor = -1;
      player.addEventListener('canplay', applyPosition, { once: true });
      player.addEventListener('canplaythrough', applyPosition, { once: true });
      // 网络盘上 canplay 常常来得比数据早，先排一次兜底，别把定位赌在事件上
      setTimeout(applyPosition, 800);
      player.src = audio.url;
    },

    // 时长：优先用切片区间（start_time/end_time），否则用真实 duration
    syncDurationFromAudio(audio, player) {
      if (audio && audio.start_time !== undefined && audio.end_time !== undefined) {
        this.duration = audio.end_time - audio.start_time;
      } else {
        const d = player ? player.duration : 0;
        this.duration = (isFinite(d) && d > 0) ? d : 0;
      }
    },

    selectTrack(index) {
      // 检查是否为付费内容
      if (!this.isPaid && index >= 5) {
        return;
      }

      if (index !== this.currentTrackIndex) {
        // 保存当前播放位置：此刻元素与 index 仍指向旧集，先 flush 再切
        this.flushCurrentTrackProgress();
        this.savePlaybackPosition();

        this.loadTrack(index);
        // §等元素真的能动再 play§ 换集后 src 刚赋值，$nextTick 时 readyState
        // 还是 0，此刻 play() 要么被浏览器判成 NotAllowedError/AbortError 直接
        // 丢弃，要么 pending 到数据来了才开始——但用户中途点一下暂停就把它打断，
        // 于是既没播也没暂停，点多少下都没反应。这里等到 canplay 再播，并且
        // 认「播放意图」：只要用户是想播的，数据到了就一定要播起来。
        this._wantPlay = true;
        this._playWhenReady(index);
      } else {
        // 如果点击的是当前正在播放的音频，则切换播放/暂停状态
        this.togglePlay();
      }
    },

    // 数据就绪后执行播放意图。index 用于识别「这期间用户又换集了」的情况。
    _playWhenReady(index, tries = 0) {
      const player = this.$refs.audioPlayer;
      if (!player || !this._wantPlay) return;
      if (index !== undefined && index !== this.currentTrackIndex) return;
      if (player.readyState >= 3) {
        this.safePlay();
        return;
      }
      if (tries >= 40) return; // 10 秒还起不来就别一直重试
      setTimeout(() => this._playWhenReady(index, tries + 1), 250);
    },

    togglePlay() {
      const player = this.$refs.audioPlayer;
      if (!player) return;

      // §以元素为准，不以 isPlaying 为准§ isPlaying 靠 play/pause 事件异步
      // 回写。点得快一点（或换集后事件还没到）时，isPlaying 和元素真实状态
      // 是反的，于是「想播放」变成「再 pause 一次」——按钮闪一下就没声音，
      // 表现就是"点不动"。直接读 player.paused 是唯一可靠的判断依据。
      if (!player.paused) {
        this.pauseAndClearIntent();
      } else {
        this.safePlay();
      }
    },

    pauseAndClearIntent() {
      this._wantPlay = false;
      const player = this.$refs.audioPlayer;
      if (player) player.pause();
    },

    // §统一的安全播放§ 裸调 play() 不接 Promise 的后果是：被中断时抛
    // "play() request was interrupted by a new load request"，错误无人处理，
    // 播放器停在一个既没播也没暂停的状态 —— 点多少次都没反应。
    safePlay() {
      const player = this.$refs.audioPlayer;
      if (!player || !player.src) return;
      this._wantPlay = true;
      const p = player.play();
      if (!p || !p.then) return;
      p.catch((err) => {
        const name = err && err.name;
        if (name === 'NotAllowedError') {
          // 浏览器自动播放策略拦下，需要用户手势；清掉意图，别在后面偷偷重试
          this._wantPlay = false;
          return;
        }
        if (name === 'AbortError') {
          // 被新的加载/定位打断：只要还想播，就让 _playWhenReady 接着把它拉起来
          if (this._wantPlay) {
            this._playWhenReady(this.currentTrackIndex);
          }
          return;
        }
        console.error('[AUDIO] play() 失败', name, err && err.message);
      });
    },

    previousTrack() {
      if (this.currentTrackIndex > 0) {
        // 保存当前播放位置
        this.flushCurrentTrackProgress();
        this.savePlaybackPosition();

        const prev = this.currentTrackIndex - 1;
        this.loadTrack(prev);
        if (this.isPlaying) {
          this._wantPlay = true;
          this._playWhenReady(prev);
        }
      }
    },

    nextTrack(forcePlay = false) {
      if (this.currentTrackIndex < this.audioFiles.length - 1) {
        // §切集前先落盘旧集§ 只调一次、且在 index 改变之前。旧代码在
        // loadTrack 之后又保存一次：那时 index 已是新集、元素还是旧集数据，
        // 于是「旧集的秒数」被写进「新集的 key」——表现为上一集记忆消失、
        // 新集一打开就是旧集的位置（或反过来从头）。
        this.flushCurrentTrackProgress();
        this.savePlaybackPosition();

        const next = this.currentTrackIndex + 1;
        this.loadTrack(next);
        if (forcePlay || this.isPlaying) {
          // §不要 $nextTick 后裸 play()§ 换源后 readyState 还是 0，此刻 play()
          // 会被浏览器丢弃或挂起 pending，用户中途一点暂停就两边都不成立。
          // 与 selectTrack 统一走「认意图 + 等 canplay」的路径。
          this._wantPlay = true;
          this._playWhenReady(next);
        }
      }
    },

    seekTo(value) {
      if (this.$refs.audioPlayer && this.duration > 0) {
        const audio = this.currentAudio;
        let seekTime = (value / 100) * this.duration;
        if (audio && audio.start_time !== undefined) {
          seekTime += audio.start_time;
        }
        try {
          this.$refs.audioPlayer.currentTime = seekTime;
        } catch (e) { /* 元数据未就绪时赋值可能抛错，忽略 */ }
        // §落地后立刻同步界面§ onTimeUpdate 在 isDragging 期间是关闭的
        // （否则会和拖动抢 progress），松手后若等到下一次 timeupdate 才
        // 回写，滑块会「弹回原处再跳过去」。这里直接对齐。
        this.currentTime = (value / 100) * this.duration;
      }
      // @end 在部分交互路径（键盘方向键/点轨道）不触发，这里兜底复位，
      // 否则 isDragging 卡在 true，进度条从此不再跟随播放。
      this.isDragging = false;
    },

    setPlaybackRate(rate) {
      this.playbackRate = rate;
      if (this.$refs.audioPlayer) {
        this.$refs.audioPlayer.playbackRate = rate;
      }
    },

    setSleepTimer(timer) {
      this.clearSleepTimer();
      this.sleepTimer = timer;

      if (timer) {
        if (timer.value === 'current') {
          // 当前章节结束后停止
          this.sleepTimer.type = 'current';
        } else {
          // 定时停止
          this.sleepTimer.type = 'timeout';
          this.sleepTimer.endTime = Date.now() + (timer.value * 60 * 1000);
          this.sleepTimerInterval = setInterval(() => {
            if (Date.now() >= this.sleepTimer.endTime) {
              this.pauseAndClearTimer();
            }
          }, 1000);
        }
      }
    },

    clearSleepTimer() {
      if (this.sleepTimerInterval) {
        clearInterval(this.sleepTimerInterval);
        this.sleepTimerInterval = null;
      }
      this.sleepTimer = null;
    },

    pauseAndClearTimer() {
      this.$refs.audioPlayer.pause();
      this.clearSleepTimer();
    },

    // 音频事件处理
    onLoadedMetadata() {
      const player = this.$refs.audioPlayer;
      if (!player) return;
      this.syncDurationFromAudio(this.currentAudio, player);
      // 只在真正不一致时写，避免每次元数据变化都触发 ratechange 重排音频
      if (player.playbackRate !== this.playbackRate) {
        player.playbackRate = this.playbackRate;
      }
    },

    onTimeUpdate() {
      if (!this.isDragging && this.$refs.audioPlayer) {
        const audio = this.currentAudio;
        const playerTime = this.$refs.audioPlayer.currentTime;

        if (audio && audio.end_time !== undefined) {
          if (playerTime >= audio.end_time) {
            this.onTrackEnded();
            return;
          }
          this.currentTime = Math.max(0, playerTime - (audio.start_time || 0));
        } else {
          this.currentTime = playerTime;
        }

        if (this.duration > 0) {
          this.progress = (this.currentTime / this.duration) * 100;
        }

        this.syncSubtitle();
      }
    },

    onTrackEnded() {
      // §播完这一集：只清它自己的记忆§ 这里不调 savePlaybackPosition()——
      // 它会把「已到结尾」写进共享键，随后 nextTrack 又按新 index 覆盖，
      // 产生跨集污染。直接按元素真实集号清掉每集 key 即可。
      this._clearTrackMemoryByElement();

      // 检查定时器
      if (this.sleepTimer && this.sleepTimer.type === 'current') {
        this.pauseAndClearTimer();
        return;
      }

      // 自动播放下一首
      if (this.currentTrackIndex < this.audioFiles.length - 1) {
        this.nextTrack(true);
      } else {
        this.isPlaying = false;
        // 整本书播放完成，可以选择清除播放位置记录
        // this.clearPlaybackPosition();
      }
    },

    onAudioError() {
      const player = this.$refs.audioPlayer;
      const err = player && player.error;
      // code 1 = MEDIA_ERR_ABORTED，是我们主动换集/定位打断的，属正常
      if (err && err.code !== 1) {
        console.error('[AUDIO] 媒体错误', err.code, err.message,
          '第' + (this.currentTrackIndex + 1) + '集', this.currentAudio && this.currentAudio.url);
        this.isPlaying = false;
        // §不要在这里清 _wantPlay§ 看门狗靠这个意图做重拉自愈；错误后立刻清
        // 意图会让看门狗永久停摆（重拉后再次失败 → 意图没了 → 不再重试）。
        // 放弃的时机由看门狗的重拉上限（3 次）统一决定，那里会清意图并提示。
      }
    },

    // stalled 在网络卡顿时会触发。打出来便于区分「网络问题」还是「逻辑问题」，
    // 只记一条，不刷屏。
    onAudioStalled() {
      if (this._stalledLogged) return;
      this._stalledLogged = true;
      console.warn('[AUDIO] 网络停滞 stalled，第' + (this.currentTrackIndex + 1) + '集');
    },

    // §卡死看门狗（进展制，不是倒计时制）§
    // 第一版按固定 8 秒计时：网络盘上正常加载一集可能就要 20s+，固定阈值
    // 会把「慢」误判成「死」，反复 load() 打断正常加载，反而永远播不了。
    // 现在只看「有没有进展」，有任意一种进展就不动手：
    //   1. 时间在走（正在播）
    //   2. readyState 在爬升（元数据/数据陆续到位）
    //   3. buffered 在增长（字节还在到）——progress 事件时登记
    // 连续 STALL_TICKS 个周期（2s×6=12s）完全零进展才算真卡死，才重拉；
    // 且最多重拉 2 次，仍不行就明确报错提示，不再无限循环。
    _startWatchdog() {
      this._stopWatchdog();
      this._watchdog = setInterval(() => {
        const player = this.$refs.audioPlayer;
        if (!player || !this._wantPlay) return;
        const t = player.currentTime || 0;
        let progressing = false;
        if (!player.paused && t > (this._wdLastTime || 0) + 0.05) progressing = true;
        if (player.readyState > (this._wdLastReadyState || 0)) progressing = true;
        const bufEnd = player.buffered && player.buffered.length
          ? player.buffered.end(player.buffered.length - 1) : 0;
        if (bufEnd > (this._wdLastBufEnd || 0) + 0.01) progressing = true;
        this._wdLastTime = t;
        this._wdLastReadyState = player.readyState;
        this._wdLastBufEnd = bufEnd;
        if (progressing || player.readyState >= 3) {
          this._wdStuckTicks = 0;
          // 有进展就清空重拉计数：上一次卡死已被这次成功加载洗白，
          // 不然几集之后累积到 3 次，好端端的一集也被拒绝重拉。
          if (!player.paused && t > 0) this._wdReloads = 0;
          return;
        }
        this._wdStuckTicks = (this._wdStuckTicks || 0) + 1;
        if (this._wdStuckTicks < 6) return; // 6 × 2000ms 完全零进展
        this._wdStuckTicks = 0;
        this._wdReloads = (this._wdReloads || 0) + 1;
        if (this._wdReloads > 2) {
          this._stopWatchdog();
          this._wantPlay = false;
          console.error('[AUDIO] 连续 3 次重拉仍无进展，放弃并提示用户',
            this.currentAudio && this.currentAudio.url);
          if (this.$toast && typeof this.$toast.error === 'function') {
            this.$toast.error(this.$t('audio.playError', { n: this.currentTrackIndex + 1 }));
          }
          return;
        }
        console.warn('[AUDIO] 看门狗：12s 零进展，第 ' + this._wdReloads + ' 次重拉第'
          + (this.currentTrackIndex + 1) + '集');
        const keepReload = this.currentTrackIndex;
        try { player.load(); } catch (e) { /* 忽略 */ }
        this.loadTrack(keepReload);
        this._playWhenReady(keepReload);
      }, 2000);
    },

    // progress 事件：字节还在到，登记一下，看门狗据此不算卡死
    onAudioProgress() {
      const player = this.$refs.audioPlayer;
      if (player && player.buffered && player.buffered.length) {
        this._wdLastBufEnd = player.buffered.end(player.buffered.length - 1);
      }
    },

    _stopWatchdog() {
      if (this._watchdog) {
        clearInterval(this._watchdog);
        this._watchdog = null;
      }
      this._wdLastTime = 0;
      this._wdLastReadyState = 0;
      this._wdLastBufEnd = 0;
      this._wdStuckTicks = 0;
    },

    onPlay() {
      this.isPlaying = true;
    },

    onPause() {
      this.isPlaying = false;
    },

    // 字幕方法
    parseSRT(content) {
      const cues = [];
      // 兼容 SRT 的 HH:MM:SS,mmm 与 WebVTT 省略小时的 MM:SS.mmm
      const timeRe = /(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[,.](\d{1,3})\s*-->\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[,.](\d{1,3})/;
      const blocks = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim().split(/\n\n+/);
      for (const block of blocks) {
        const lines = block.split('\n');
        const timeLineIdx = lines.findIndex(l => timeRe.test(l));
        if (timeLineIdx === -1) continue;
        const m = lines[timeLineIdx].match(timeRe);
        const start = (+(m[1] || 0)) * 3600 + (+m[2]) * 60 + (+m[3]) + (+m[4].padEnd(3, '0')) / 1000;
        const end = (+(m[5] || 0)) * 3600 + (+m[6]) * 60 + (+m[7]) + (+m[8].padEnd(3, '0')) / 1000;
        const text = lines.slice(timeLineIdx + 1).join('\n').trim();
        if (text && end > start) {
          cues.push({ start, end, text });
        }
      }
      // 防御畸形文件：保证二分查找前提（按开始时间有序）
      cues.sort((a, b) => a.start - b.start);
      return cues;
    },

    async loadSubtitle(url) {
      this.subtitleCues = [];
      this.currentCueIndex = -1;
      this.renderLimit = this.segmentSize;
      // 切到没有字幕的轨道时，整篇字幕视图会是个空面板，退回封面
      // （不改持久化偏好：下一章有字幕时仍按用户习惯展开）
      if (!url) {
        this.showLyrics = false;
        return;
      }
      if (!process.client) return;

      if (this.subtitleCache[url]) {
        this.subtitleCues = this.subtitleCache[url];
        return;
      }

      try {
        const resp = await fetch(url, { credentials: 'include' });
        if (!resp.ok) return;
        const content = await resp.text();
        const cues = this.parseSRT(content);
        this.subtitleCache[url] = cues;
        // 防止快速切轨时旧请求覆盖新字幕
        const currentAudio = this.currentAudio;
        if (currentAudio && currentAudio.subtitle === url) {
          // 换章要重置分段进度，否则会沿用上一章已展开的行数
          this.renderLimit = Math.min(this.segmentSize, cues.length);
          this.subtitleCues = cues;
        }
      } catch (error) {
        console.error('Failed to load subtitle:', error);
      }
    },

    syncSubtitle() {
      if (!this.subtitleCues.length) return;
      // 使用播放器绝对时间：普通分章文件与 currentTime 一致；
      // m4b 内嵌章节共享整条音轨的外挂字幕时，字幕时间轴为绝对时间
      const player = this.$refs.audioPlayer;
      const t = player ? player.currentTime : this.currentTime;
      let lo = 0;
      let hi = this.subtitleCues.length - 1;
      let idx = -1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const c = this.subtitleCues[mid];
        if (t < c.start) {
          hi = mid - 1;
        } else if (t >= c.end) {
          lo = mid + 1;
        } else {
          idx = mid;
          break;
        }
      }
      if (idx !== this.currentCueIndex) {
        this.currentCueIndex = idx;
        this.scrollToActiveCue();
      }
    },

    /**
     * 整篇字幕跟随：当前句保持在可视区中上部，滚到就停。
     *
     * 与 20 行窗口的区别：不再强行居中。整篇模式下用户需要看到上下文，
     * 每句都居中会让画面持续上下跳（这正是之前「忽上忽下」的观感来源）。
     * 现在用「舒适区」策略：当前句落在可视区 35%~65% 之间就不动，
     * 越界才滚动到 45% 处（略偏上，给下文留更多空间）。
     */
    scrollToActiveCue() {
      this._followCue('lyricsBox', 'cue-');
    },

    _followCue(boxRef, cueRef) {
      if (this.currentCueIndex < 0) return;
      const box = this.$refs[boxRef];
      if (!box || !box.clientHeight) return;

      // 分段加载：当前句快接近已渲染末尾时，追加下一段
      if (this.currentCueIndex + 20 >= this.renderLimit
          && this.renderLimit < this.subtitleCues.length) {
        this.renderLimit = Math.min(this.renderLimit + this.segmentSize,
                                    this.subtitleCues.length);
        // 追加后 DOM 变了，等下一帧再定位
        this.$nextTick(() => this._followCue(boxRef, cueRef));
        return;
      }

      const el = this.$refs[cueRef + this.currentCueIndex];
      const node = Array.isArray(el) ? el[0] : el;
      if (!node) return;

      const boxH = box.clientHeight;
      const nodeTop = node.offsetTop;
      const nodeH = node.offsetHeight;
      const cur = box.scrollTop;

      // 舒适区：可视区 35% ~ 65%，在当前范围内就不动，避免持续抖动
      const upper = cur + boxH * 0.35;
      const lower = cur + boxH * 0.65;
      if (nodeTop >= upper && nodeTop + nodeH <= lower) return;

      // 越界后滚动到 45% 处（略偏上，下文多留一点）
      const maxScroll = box.scrollHeight - boxH;
      const target = Math.max(0, Math.min(maxScroll,
        nodeTop - boxH * 0.45 + nodeH / 2));
      box.scrollTop = target;
    },

    toggleLyricsView() {
      this.showLyrics = !this.showLyrics;
      if (process.client) {
        try {
          localStorage.setItem('audio_lyrics_view', this.showLyrics ? '1' : '0');
        } catch (error) {
          console.error('Error saving lyrics view preference:', error);
        }
      }
      // 展开后立刻定位到当前句
      if (this.showLyrics) {
        this.$nextTick(() => {
          const box = this.$refs.lyricsBox;
          if (box) box.scrollTop = 0;
          this._followCue('lyricsBox', 'cue-');
        });
      }
    },

    seekToCue(cue) {
      if (!cue || !this.$refs.audioPlayer) return;
      // 字幕时间为音轨绝对时间，直接设置即可（分章文件两者等价）
      this.$refs.audioPlayer.currentTime = cue.start;
    },

    toggleSubtitle() {
      this.showSubtitle = !this.showSubtitle;
      if (process.client) {
        try {
          localStorage.setItem('audio_subtitle_enabled', this.showSubtitle ? '1' : '0');
        } catch (error) {
          console.error('Error saving subtitle preference:', error);
        }
      }
      // 4.6.0-19：接上实际渲染。原来这个开关只改按钮颜色+存偏好，
      // 不控制任何东西（字幕视图实际由 showLyrics 管），是个无效开关。
      // 语义定为「要不要看字幕」：关 → 回封面视图；开 → 恢复上次的字幕视图偏好。
      if (!this.showSubtitle) {
        this.showLyrics = false;
      } else if (process.client) {
        try {
          const lyrics = localStorage.getItem('audio_lyrics_view');
          this.showLyrics = lyrics === null ? true : lyrics === '1';
        } catch (error) {
          this.showLyrics = true;
        }
      }
    },

    restoreSubtitlePreference() {
      if (!process.client) return;
      try {
        const saved = localStorage.getItem('audio_subtitle_enabled');
        if (saved !== null) {
          this.showSubtitle = saved === '1';
          // 字幕偏好为关时封面视图（原开关无实效，从不影响渲染）
          if (!this.showSubtitle) {
            this.showLyrics = false;
          }
        }
        // 整篇字幕视图的开关也是持久的：习惯看整篇的人不想每次都点一下
        const lyrics = localStorage.getItem('audio_lyrics_view');
        if (lyrics !== null && this.showSubtitle) {
          this.showLyrics = lyrics === '1';
        }
      } catch (error) {
        console.error('Error restoring subtitle preference:', error);
      }
    },

    // 工具方法
    getDisplayName(filename) {
      // 移除前缀（4个数字加下划线）
      return filename.replace(/^\d{4}_/, '');
    },

    formatTime(seconds) {
      if (!seconds || isNaN(seconds)) return '00:00';
      const mins = Math.floor(seconds / 60);
      const secs = Math.floor(seconds % 60);
      return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    },

    formatFileSize(bytes) {
      if (!bytes) return '';
      const mb = bytes / (1024 * 1024);
      return `${mb.toFixed(1)}MB`;
    },

    // 播放位置管理方法
    getStorageKey() {
      // 生成存储键：audio_progress_用户ID_书籍ID
      const userId = this.$store.state.user?.id || 'guest';
      return `audio_progress_${userId}_${this.bookId}`;
    },

    // §每集记忆键§ 与详情页弹窗（AudioListDialog._keyOf）完全同算法同格式：
    // audiobook_preview_<用户>_<书>_<url哈希>，值 { t: 相对该文件的秒 }。
    // url 带时效签名也没关系——同一次会话内 url 稳定，弹窗与本页读到的
    // 是同一个 key；跨会话签名变了会导致旧记忆失效，这与弹窗的现状一致。
    _trackKeyOf(index) {
      const item = this.audioFiles[index] || {};
      const s = String(item.url || item.filename || index);
      let h = 0;
      for (let i = 0; i < s.length; i++) {
        h = (h * 31 + s.charCodeAt(i)) | 0;
      }
      const userId = this.$store.state.user?.id || 'guest';
      return `audiobook_preview_${userId}_${this.bookId}_${Math.abs(h)}`;
    },

    // 进页时把所有集的已有记忆读出来，列表上显示「上次听到哪」
    _loadTrackResumeMap() {
      if (!process.client) return;
      const map = {};
      this.audioFiles.forEach((item, idx) => {
        try {
          const raw = localStorage.getItem(this._trackKeyOf(idx));
          if (!raw) return;
          const v = JSON.parse(raw);
          if (typeof v.t === 'number' && v.t > 1) map[idx] = v.t;
        } catch (e) { /* 坏数据忽略 */ }
      });
      this.trackResumeMap = map;
    },

    resumeHintOf(index) {
      return this.trackResumeMap[index] || 0;
    },

    savePlaybackPosition() {
      if (!process.client || !this.bookId) return;

      try {
        const idx = this.currentTrackIndex;
        // §以元素真实加载的文件为准§ 自动连播时 loadTrack 在切换中途
        // （index 已切到下一集、元素里还是上一集的数据），此时按 idx 写会把
        // 上一集的秒数记到下一集头上。用元素 src 反查真实集号，查不到才回退。
        const realIdx = this._indexOfSrc(this.$refs.audioPlayer);
        const writeIdx = realIdx >= 0 ? realIdx : idx;

        const progressData = {
          trackIndex: writeIdx,
          currentTime: this.currentTime,
          timestamp: Date.now(),
          bookTitle: this.book.title || '',
          totalTracks: this.audioFiles.length
        };

        localStorage.setItem(this.getStorageKey(), JSON.stringify(progressData));
        this._localProgressTs = progressData.timestamp;

        // §每集记忆§ 与弹窗同一套 key。注意 this.currentTime 是相对该文件
        // 的秒（不含 start_time 偏移），与弹窗存的语义一致。听完（差 3 秒内）
        // 清掉——下次从头听；不足 5 秒视为「没真听」，不记。
        // 切集途中（元素文件与 writeIdx 不符）不写，避免污染新集。
        const d = this.duration;
        const t = this.currentTime || 0;
        if (d && isFinite(d) && realIdx === writeIdx) {
          const key = this._trackKeyOf(writeIdx);
          try {
            if (t >= d - 3) {
              localStorage.removeItem(key);
              if (this.trackResumeMap[writeIdx] !== undefined) {
                const map = { ...this.trackResumeMap };
                delete map[writeIdx];
                this.trackResumeMap = map;
              }
            } else if (t > 5) {
              localStorage.setItem(key, JSON.stringify({ t: t }));
              if (this.trackResumeMap[writeIdx] !== t) {
                this.trackResumeMap = { ...this.trackResumeMap, [writeIdx]: t };
              }
            }
          } catch (e) { /* 隐私模式写不进去，忽略 */ }
        }

        // 4.6.0-19：同步到服务端（内部 15s 节流），换设备/换浏览器也能续播
        this.pushServerProgress();
      } catch (error) {
        console.error('Error saving playback position:', error);
      }
    },

    // 按元素的 src 反查集号（-1 表示查不到/未加载）
    _indexOfSrc(player) {
      const el = player || this.$refs.audioPlayer;
      if (!el) return -1;
      const src = el.getAttribute('src') || el.src || '';
      if (!src) return -1;
      const clean = (u) => String(u || '').split('?')[0].replace(/^https?:\/\/[^/]+/, '');
      const target = clean(src);
      if (!target) return -1;
      for (let i = 0; i < this.audioFiles.length; i++) {
        if (clean(this.audioFiles[i].url) === target) return i;
      }
      return -1;
    },

    // 按元素真实集号清掉「每集记忆」（听完时用）
    _clearTrackMemoryByElement() {
      const idx = this._indexOfSrc(this.$refs.audioPlayer);
      if (idx < 0) return;
      try {
        localStorage.removeItem(this._trackKeyOf(idx));
      } catch (e) { /* 忽略 */ }
      if (this.trackResumeMap[idx] !== undefined) {
        const map = { ...this.trackResumeMap };
        delete map[idx];
        this.trackResumeMap = map;
      }
    },

    // 切集前：把「正在播的那一集」的进度落盘（此时元素与 index 仍一致）
    flushCurrentTrackProgress() {
      const el = this.$refs.audioPlayer;
      if (!el || !el.getAttribute('src')) return;
      const realIdx = this._indexOfSrc(el);
      if (realIdx < 0) return;
      const d = el.duration;
      const t = el.currentTime || 0;
      if (!d || !isFinite(d)) return;
      try {
        const key = this._trackKeyOf(realIdx);
        if (t >= d - 3) {
          localStorage.removeItem(key);
          if (this.trackResumeMap[realIdx] !== undefined) {
            const map = { ...this.trackResumeMap };
            delete map[realIdx];
            this.trackResumeMap = map;
          }
        } else if (t > 5) {
          const rel = Math.max(0, t - ((this.audioFiles[realIdx] || {}).start_time || 0));
          localStorage.setItem(key, JSON.stringify({ t: rel }));
          this.trackResumeMap = { ...this.trackResumeMap, [realIdx]: rel };
        }
      } catch (e) { /* 忽略 */ }
    },

    // 返回 true 表示成功把播放器指到了上次的位置（调用方不要再 loadTrack(0)）
    restorePlaybackPosition() {
      if (!process.client || !this.bookId || this.audioFiles.length === 0) return false;

      try {
        const saved = localStorage.getItem(this.getStorageKey());
        if (!saved) return false;

        const progressData = JSON.parse(saved);

        // §同一设备上的「刚才」优先§（r9）详情页的试听弹窗与播放页共用这个
        // 键。若用户是刚从弹窗点过来的，弹窗关闭时已经把「正在听的第几章、
        // 听到第几秒」写进来了，时间戳就是刚刚；而这里的页面实例可能是
        // keep-alive 缓存下来的旧实例（还带着上一次的 currentTime），
        // 直接恢复自己的旧值就等于把弹窗的进度抹掉——用户体验上仍是
        // 「两个单独的进度」。此时以 localStorage 里的最新一份为准。
        const age = Date.now() - (progressData.timestamp || 0);
        this._freshFromDialog = age >= 0 && age < 30000;
        // 验证数据的有效性
        if (
          progressData.trackIndex >= 0 &&
          progressData.trackIndex < this.audioFiles.length &&
          progressData.currentTime >= 0
        ) {
          console.log('Restoring playback position:', progressData);
          this._localProgressTs = progressData.timestamp || 0;

          // loadTrack 内部会设置 currentTrackIndex，这里不用再赋一遍
          this.loadTrack(progressData.trackIndex, progressData.currentTime);

          if (progressData.currentTime > 10) {
            this.showRestoreMessage(progressData);
          }
          return true;
        }
        return false;
      } catch (error) {
        console.error('Error restoring playback position:', error);
        return false;
      }
    },

    showRestoreMessage(progressData) {
      // 可以在这里添加一个提示消息，告知用户已恢复播放位置
      const minutes = Math.floor(progressData.currentTime / 60);
      const seconds = Math.floor(progressData.currentTime % 60);
      const timeStr = `${minutes}:${seconds.toString().padStart(2, '0')}`;

      console.log(`已恢复到第${progressData.trackIndex + 1}章 ${timeStr} 的播放位置`);

      // 这里可以添加 toast 通知或其他 UI 提示
      // 例如：this.$toast.info(`已恢复到第${progressData.trackIndex + 1}章 ${timeStr} 的播放位置`);
    },

    startProgressSaving() {
      // 每5秒自动保存一次播放进度
      this.saveProgressInterval = setInterval(() => {
        if (this.isPlaying && this.currentTime > 0) {
          this.savePlaybackPosition();
        }
      }, 5000);
    },

    stopProgressSaving() {
      if (this.saveProgressInterval) {
        clearInterval(this.saveProgressInterval);
        this.saveProgressInterval = null;
      }
    },

    // §服务端进度（4.6.0-19）§ 进度此前只存 localStorage：换设备/换浏览器/
    // 清缓存即丢。这里节流上报（15s 一次，配合 5s 心跳；暂停/切集/离开页面
    // 用 force 立即推）。未登录或离线时静默失败，不影响本地记忆。
    //
    // §keepalive§ beforeDestroy 里的上报是「最后一个请求」：SPA 内跳转
    // （flush 模式下同一文档内换路由）时，普通 fetch 会被浏览器在文档卸载
    // 时取消，服务端收不到 → 跨设备续播偶尔失效。keepalive 让请求脱离文档
    // 生命周期，规范限制请求体 < 64KB，这里的 payload 只有几十字节。
    async pushServerProgress(force = false, keepalive = false) {
      if (!process.client || !this.bookId) return;
      const now = Date.now();
      if (!force && now - (this._lastServerPush || 0) < 15000) return;
      this._lastServerPush = now;
      try {
        const rsp = await this.$backend(`/audio/${this.bookId}/progress`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            track_index: this.currentTrackIndex || 0,
            position: this.currentTime || 0,
            duration: this.duration || null,
            // 这次进度产生的时刻。服务端据此只接受「更晚」的写入，
            // 避免另一台设备后到的旧心跳把新进度盖掉。
            client_ts: Date.now(),
          }),
          keepalive,
        });
        // §服务端进度比本地旧时不覆盖§ 上报带宽赛：设备 A 在 10:00 报过
        // position=100，设备 B 在 10:05 报过 position=50；若 A 在 10:06 又
        // 报一次（还是 100，因为 A 一直停在那儿），服务端就成了 100，B 那边
        // 的进度被抹掉。服务端用 X-Client-Ts（上次收下的客户端时间戳）判断，
        // 这里把它的值续下来，保证「时间上更晚的一次」才有写权。
        const serverTs = rsp && rsp.data && rsp.data.client_ts;
        if (serverTs) this._serverClientTs = serverTs;
      } catch (e) { /* 静默：进度上报失败不影响播放 */ }
    },

    // 服务端进度恢复：localRestored 表示本地已经恢复过（此时只有服务端
    // 更新时才跳转）。两台设备都听过时以「更晚保存」的一方为准。
    async tryRestoreFromServer(localRestored) {
      try {
        const rsp = await this.$backend(`/audio/${this.bookId}/progress`);
        if (!rsp || rsp.err !== "ok" || !rsp.data) return;
        const { track_index, position, updated_at } = rsp.data;
        if (!(track_index >= 0 && track_index < this.audioFiles.length && position >= 0)) return;
        const serverTs = updated_at ? Date.parse(updated_at) : 0;
        if (localRestored && serverTs <= (this._localProgressTs || 0)) return;
        // 服务端存的是「该集内的相对秒数」，与 currentTime 同量纲；
        // 但 loadTrack 内部还会叠 start_time（m4b 切片），这里直接传相对值。
        if (localRestored && track_index === this.currentTrackIndex
            && Math.abs(position - this.currentTime) < 5) {
          return;  // 和本地基本一致，不打断当前加载
        }
        console.log('Restoring playback position from server:', rsp.data);
        this.loadTrack(track_index, position);
      } catch (e) { /* 静默：拿不到服务端进度就走本地 */ }
    },

    clearPlaybackPosition() {
      // 清除播放位置记录（可用于"从头开始"功能）
      if (!process.client || !this.bookId) return;

      try {
        localStorage.removeItem(this.getStorageKey());
        console.log('Cleared playback position for book:', this.bookId);
      } catch (error) {
        console.error('Error clearing playback position:', error);
      }
    },

    startFromBeginning() {
      // 从头开始播放
      this.clearPlaybackPosition();
      this.currentTrackIndex = 0;
      this.currentTime = 0;
      this.loadTrack(0);

      console.log('Started from beginning');
    },

    async downloadCollection() {
      if (!this.bookId || this.audioFiles.length === 0) {
        return;
      }

      this.downloadLoading = true;

      try {
        const response = await this.$backend(`/audios/${this.bookId}/collection`);

        if (response.err === 'ok') {
          // 成功获取下载链接，直接下载
          const link = document.createElement('a');
          link.href = response.download_url;
          link.style.display = 'none';
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        } else {
          this.$alert('error', response.msg || this.$t('audio.downloadFailed'));
        }
      } catch (error) {
        console.error('Download collection error:', error);
        this.$alert('error', this.$t('audio.downloadFailed'));
      } finally {
        this.downloadLoading = false;
      }
    },

    async purchaseAudio() {
      if (!this.bookId) {
        return;
      }

      this.purchaseLoading = true;

      try {
        const response = await this.$backend(`/audio/${this.bookId}/purchase`, {
          method: 'POST',
          data: {
            price: 10.00
          }
        });

        if (response.err === 'ok') {
          this.isPaid = true;
          this.showPurchaseDialog = false;
          this.$alert('success', this.$t('audio.purchaseSuccess'));
        } else {
          this.$alert('error', response.msg || this.$t('audio.purchaseFailed'));
        }
      } catch (error) {
        console.error('Purchase audio error:', error);
        this.$alert('error', this.$t('audio.purchaseFailed'));
      } finally {
        this.purchaseLoading = false;
      }
    },

    gotoBookDetail() {
      this.$router.push("/book/" + this.bookId);
    },

    closePlayer() {
      // 停止播放并保存当前位置
      if (this.$refs.audioPlayer) {
        this.$refs.audioPlayer.pause();
      }
      this.savePlaybackPosition();

      // 退出播放界面
      this.$router.go(-1); // 返回上一页
    },

    openDeleteDialog() {
      this.showDeleteDialog = true;
    },

    async deleteAudio() {
      if (!this.bookId) {
        return;
      }

      this.deleteLoading = true;

      try {
        // 停止播放器
        if (this.$refs.audioPlayer) {
          this.$refs.audioPlayer.pause();
        }

        // 调用删除接口
        const response = await this.$backend(`/audio/${this.bookId}/delete`, {
          method: 'POST'
        });

        if (response.err === 'ok') {
          this.showDeleteDialog = false;
          this.$alert('success', this.$t('audio.deleteSuccess'));
          this.$router.go(-1);
        } else {
          this.$alert('error', response.msg || this.$t('audio.deleteFailed'));
        }
      } catch (error) {
        console.error('Delete audio error:', error);
        this.$alert('error', this.$t('audio.deleteFailed'));
      } finally {
        this.deleteLoading = false;
      }
    },

    async showPurchaseDialogWithVipInfo() {
      try {
        // 获取用户VIP信息
        const response = await this.$backend('/user/vip');
        if (response.err === 'ok') {
          // 使用临时变量存储当前查询的配额值
          this.vipquota = response.vipquota || 0;
          if (this.vipquota === 0) {
            this.$alert('error', this.$t('audio.vipQuotaInsufficient'));
          } else {
            this.showPurchaseDialog = true;
          }
        } else {
          // 如果获取VIP信息失败，直接显示购买对话框
          this.$alert('error', '无法获取账号信息，请稍后再试。');
        }
      } catch (error) {
        console.error('Error fetching VIP info:', error);
        // 如果网络错误，直接显示购买对话框
        this.$alert('error', '无法获取账号信息，请稍后再试。');
      }
    }
  }
};
</script>

<style scoped>
.audio-player-container {
  height: 100vh;
  background: linear-gradient(135deg, #2c2c2c 0%, #1a1a1a 100%);
  color: #ffffff;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.audio-upper-section {
  height: 60%;
  display: flex;
  padding: 20px;
  gap: 20px;
}

.cover-section {
  flex: 0 0 35%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;   /* 给切换按钮定位 */
  min-height: 0;        /* 让内部字幕区能正确计算 clientHeight */
}

/* 整篇字幕视图占满左栏（封面默认 35% 太窄，看整篇要宽一些） */
.cover-section.lyrics-mode {
  flex: 0 0 45%;
  align-items: stretch;
}

/* 封面/字幕 视图切换按钮 */
/* 视图切换按钮：原来的纯图标贴在播放列表左边，容易被当成列表控件，
   这里改成带文字的胶囊按钮，并往封面区内部再挪一点，和列表拉开距离 */
.view-toggle-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 2;
  background-color: rgba(64, 64, 64, 0.9) !important;
  color: #fff !important;
  text-transform: none !important;
  letter-spacing: 0 !important;
  font-size: 0.8rem !important;
  padding: 0 10px !important;
  border: 1px solid rgba(255, 255, 255, 0.25);
}

.view-toggle-btn:hover {
  background-color: rgba(156, 39, 176, 0.85) !important;
}

.view-toggle-btn .toggle-label {
  margin-left: 2px;
  white-space: nowrap;
}

/* 整篇字幕滚动区 */
/* 整篇字幕滚动区：自然流从上到下排，当前句高亮 + 跟随滚动。
   不再用 flex 居中（窗口模式下才需要），整篇模式要的是连续阅读。 */
.lyrics-container {
  flex: 1;
  width: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 24px 18px;
  /* 必须 relative：子句的 offsetTop 是相对 offsetParent 算的，不设这个会
     回溯到 .cover-section，滚动位置整体偏掉一整段 padding */
  position: relative;
  /* 上下渐隐，看起来像"滚进视野"而不是硬边缘切断 */
  -webkit-mask-image: linear-gradient(to bottom, transparent 0, #000 4%, #000 96%, transparent 100%);
  mask-image: linear-gradient(to bottom, transparent 0, #000 4%, #000 96%, transparent 100%);
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.25) transparent;
  /* 段落留白：首尾句也能滚到偏中位置（padding 计入 scrollHeight） */
  scroll-padding-block: 40% 45%;
}

/* 不做 CSS 居中：伪元素留白（flex:1 自适应）会随内容伸缩，让中线漂移、
   高亮句忽上忽下。居中完全由 _centerCueIn 精确设置 scrollTop 完成；
   首尾句要能滚到中线，靠容器 padding 撑出半屏留白（padding 计入 scrollHeight）。 */

.lyrics-container::-webkit-scrollbar {
  width: 6px;
}

.lyrics-container::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.25);
  border-radius: 3px;
}

/* 单句 */
.lyric-line {
  font-size: 1.05rem;
  line-height: 1.7;
  color: #8a8a8a;            /* 未播到的句子：暗 */
  padding: 7px 12px;
  border-radius: 8px;
  margin-bottom: 4px;
  cursor: pointer;
  white-space: pre-wrap;
  word-break: break-word;
  transition: color 0.25s ease, background 0.25s ease;
  box-sizing: border-box;
  /* 长列表优化：屏幕外的行跳过排版/绘制，上千行也不卡。
     contain-intrinsic-size 给出估算高度，避免滚动条长度跳动 */
  content-visibility: auto;
  contain-intrinsic-size: auto 2.55rem;
}

/* 当前句：高亮，稍微放大一点引导视线 */
.lyric-line:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #cfcfcf;
}

/* 已播过的句子：比未播略亮一点，但不抢当前句 */
.lyric-line.past {
  color: #6e6e6e;
}

/* 当前句：高亮 */
.lyric-line.active {
  color: #ffffff;
  background: rgba(156, 39, 176, 0.28);
  border-left: 3px solid #9C27B0;
  font-weight: 600;
  transform: scale(1.01);
  transform-origin: left center;
}

.lyric-line.active:hover {
  background: rgba(156, 39, 176, 0.38);
}

.cover-container {
  max-width: 300px;
  width: 100%;
  text-align: center;
}

.book-cover {
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  margin-bottom: 20px;
  cursor: pointer;
  transition: transform 0.3s ease, filter 0.3s ease;
}

.book-cover >>> .v-image__image {
  transition: transform 0.3s ease, filter 0.3s ease;
}

.book-cover:hover >>> .v-image__image {
  transform: scale(1.02);
  filter: brightness(1.1);
}

.book-title {
  font-size: 1.5rem;
  font-weight: bold;
  margin-bottom: 8px;
  color: #ffffff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.book-author {
  font-size: 1rem;
  color: #cccccc;
  margin: 0;
}

.playlist-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}

.playlist-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #404040;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 48px;
}

.playlist-header h3 {
  margin: 0;
  color: #ffffff;
  flex-shrink: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.playlist-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
  margin-left: auto;
}

.close-btn {
  background-color: #404040 !important;
  color: white !important;
  border-color: #666666 !important;
  white-space: nowrap;
  flex-shrink: 0;
}

.delete-btn {
  background: linear-gradient(135deg, #e53935 0%, #c62828 100%) !important;
  color: white !important;
  border: 1px solid #b71c1c !important;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.1);
  white-space: nowrap;
  flex-shrink: 0;
  transition: all 0.3s ease;
  margin-left: 8px;
}

.delete-btn:hover {
  background: linear-gradient(135deg, #c62828 0%, #b71c1c 100%) !important;
  box-shadow: 0 6px 8px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1);
  transform: translateY(-1px);
}

.delete-btn:active {
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.1);
  transform: translateY(0);
}

.download-btn {
  background-color: #404040 !important;
  color: white !important;
  border-color: #666666 !important;
  white-space: nowrap;
  flex-shrink: 0;
  margin-right: 8px;
}

.download-btn:hover {
  background-color: #9C27B0 !important;
}

.download-btn:disabled {
  background-color: #2a2a2a !important;
  color: #666666 !important;
}

.chapter-info {
  background-color: transparent !important;
  color: white !important;
  border-color: #666666 !important;
  margin-right: 8px;
  white-space: nowrap;
  font-weight: 500;
}

.chapter-info .v-chip__content {
  color: white !important;
  font-size: 13px;
}

.playlist-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  scrollbar-color: #555555 #2c2c2c;
}

.playlist-container::-webkit-scrollbar {
  width: 6px;
}

.playlist-container::-webkit-scrollbar-track {
  background: #2c2c2c;
}

.playlist-container::-webkit-scrollbar-thumb {
  background: #555555;
  border-radius: 3px;
}

.playlist-item {
  display: flex;
  align-items: center;
  padding: 12px;
  cursor: pointer;
  border-radius: 8px;
  margin-bottom: 4px;
  transition: all 0.2s;
  min-width: 0;
}

.playlist-item:hover {
  background-color: #404040;
}

.playlist-item.active {
  background-color: #9C27B0;
}

.track-number {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background-color: #555555;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  margin-right: 12px;
  flex-shrink: 0;
}

.playlist-item.active .track-number {
  background-color: rgba(255, 255, 255, 0.2);
}

.playlist-item.locked {
  opacity: 0.5;
  color: #aaa;
  cursor: not-allowed;
}

.playlist-item.locked:hover {
  background-color: transparent;
}

.vip-badge {
  margin-left: 8px;
}

.purchase-btn {
  margin-right: 8px;
}

.purchase-hint {
  margin-top: 8px;
}

.track-info {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.track-title {
  font-weight: 500;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.track-duration {
  font-size: 0.875rem;
  color: #cccccc;
}

.resume-hint {
  color: #ff9800;
  font-size: 0.75rem;
  margin-left: 4px;
}

.no-audio-message {
  text-align: center;
  padding: 40px 20px;
  color: #888888;
}

.audio-controls-section {
  height: 40%;
  background: #1a1a1a;
  border-top: 1px solid #404040;
  padding: 10px;
  display: flex;
  flex-direction: column;
}

.progress-section {
  margin-bottom: 20px;
}

.time-display {
  display: flex;
  justify-content: space-between;
  font-size: 0.875rem;
  color: #cccccc;
  margin-bottom: 8px;
}

.progress-slider {
  margin: 0;
}



.controls-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
}

.main-controls {
  display: flex;
  align-items: center;
  gap: 20px;
}

.control-btn {
  background-color: #404040 !important;
}

.nav-btn:not(:disabled) {
  background-color: #404040 !important;
  color: white !important;
}

.nav-btn:disabled {
  background-color: #2a2a2a !important;
  color: #666666 !important;
}

.play-btn {
  background-color: #9C27B0 !important;
  color: white !important;
}

.secondary-controls {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
  justify-content: center;
}

.speed-btn,
.timer-btn,
.subtitle-btn {
  background-color: #404040 !important;
  color: white !important;
  position: relative;
}

.speed-text {
  position: absolute;
  bottom: -2px;
  right: -2px;
  font-size: 10px;
  background-color: #9C27B0;
  border-radius: 50%;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.volume-slider {
  margin: 0;
}

/* 中等屏幕适配 (平板横屏) */
@media (max-width: 1024px) and (min-width: 769px) {
  .audio-upper-section {
    padding: 15px;
    gap: 15px;
  }

  .cover-container {
    max-width: 250px;
  }

  .playlist-header h3 {
    font-size: 1.3rem;
  }
}

/* 移动端适配 */
@media (max-width: 768px) {
  .audio-upper-section {
    flex-direction: column;
    height: 50%;
    padding: 10px;
  }

  .cover-section {
    display: none; /* 移动端隐藏封面 */
  }

  /* 但字幕整篇要留着：移动端本来就没封面可看，这块空间给字幕最合适。
     只在有字幕时显示，否则会留下一块空白把播放列表挤小。 */
  .cover-section.lyrics-mode {
    display: flex;
    flex: 1 1 auto;
  }

  .view-toggle-btn {
    display: none; /* 移动端没有封面视图，切换按钮没意义 */
  }

  .lyrics-container {
    padding: 20px 10px;
  }

  .lyric-line {
    font-size: 0.95rem;
    line-height: 1.6;
    padding: 6px 10px;
  }

  .playlist-section {
    flex: 1;
    min-height: 0;
  }

  .playlist-header {
    position: sticky;
    top: 0;
    background: #2c2c2c;
    z-index: 10;
    margin-bottom: 8px;
    padding: 8px 0;
  }

  .playlist-controls {
    flex-direction: row;
    gap: 8px;
    justify-content: flex-end; /* 保持右对齐 */
    flex-wrap: wrap; /* 允许换行 */
  }

  .chapter-info {
    order: 1;
  }

  .download-btn {
    order: 2;
    font-size: 12px;
    padding: 0 6px;
    min-width: auto;
  }

  .close-btn {
    order: 3;
  }

  .playlist-container {
    padding-top: 0;
  }

  .audio-controls-section {
    height: 50%;
    padding: 15px;
  }

  .secondary-controls {
    flex-direction: row;
    gap: 15px;
    justify-content: center;
  }

  .main-controls {
    gap: 15px;
  }

  .progress-section {
    margin-bottom: 15px;
  }
}

/* 竖屏专用样式 */
@media (max-width: 480px) and (orientation: portrait) {
  .audio-upper-section {
    height: 60%;
    padding: 8px;
  }

  .audio-controls-section {
    height: 40%;
    padding: 12px;
  }

  .playlist-header h3 {
    font-size: 1.1rem;
  }

  .playlist-controls {
    gap: 6px;
  }

  .chapter-info {
    font-size: 12px;
    height: 24px;
  }

  .download-btn {
    min-width: auto;
    padding: 0 6px;
    font-size: 11px;
  }

  .download-btn .v-icon {
    margin-right: 2px !important;
  }

  .close-btn {
    min-width: auto;
    padding: 0 8px;
  }

  .close-btn .v-icon {
    margin-right: 4px !important;
  }

  .track-title {
    font-size: 14px;
  }

  .track-duration {
    font-size: 12px;
  }
}

/* 全局样式覆盖 */
:global(body.audio-player-page) {
  background: #1a1a1a !important;
}

:global(.audio-player-page .v-application) {
  background: #1a1a1a !important;
}

:global(.audio-player-page .v-navigation-drawer),
:global(.audio-player-page .v-app-bar) {
  display: none !important;
}

:global(.audio-player-page .v-main) {
  padding: 0 !important;
}
</style>
