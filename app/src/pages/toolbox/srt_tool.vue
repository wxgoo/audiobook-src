<template>
  <v-container fluid class="pa-4">
    <v-row class="mb-3" align="center">
      <v-col>
        <span class="text-h5 font-weight-bold">{{ $t('srtTool.title') }}</span>
        <div class="text-caption mt-1">{{ $t('srtTool.subtitle') }}</div>
      </v-col>
      <v-col cols="auto">
        <v-btn small color="error" @click="$router.go(-1)">
          <v-icon small left>mdi-close</v-icon>{{ $t('srtTool.close') }}
        </v-btn>
      </v-col>
    </v-row>

    <v-row justify="center">
      <v-col cols="12" md="10" lg="8">
        <!-- 依赖未安装：降级提示 + 一键安装 -->
        <v-alert v-if="loaded && !available" type="warning" dense text rounded="lg" class="mb-4">
          {{ $t('srtTool.unavailable') }}
          <div class="mt-2">
            <v-btn small color="primary" class="mr-2" :loading="installing"
                   :disabled="installState === 'running'" @click="installDeps">
              {{ $t('srtTool.installBtn') }}
            </v-btn>
            <v-btn v-if="installState === 'done'" small color="success"
                   :loading="restarting" @click="restartTornado">
              {{ $t('srtTool.restartBtn') }}
            </v-btn>
          </div>
          <div v-if="installLog" class="mt-2 text-caption grey--text"
               style="max-height:140px;overflow:auto;white-space:pre-wrap;font-family:monospace">{{ installLog }}</div>
          <div class="mt-2 text--secondary">{{ $t('srtTool.unavailableHint') }}</div>
        </v-alert>

        <v-card rounded="xl" outlined class="pa-6">
          <p class="text-body-2 mb-4">{{ $t('srtTool.description') }}</p>

          <!-- 书籍选择 -->
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-1 font-weight-bold">{{ $t('srtTool.pickBooks') }}</span>
            <v-spacer></v-spacer>
            <v-btn small text color="primary" @click="toggleAll(true)">{{ $t('srtTool.selectAll') }}</v-btn>
            <v-btn small text @click="toggleAll(false)">{{ $t('srtTool.selectNone') }}</v-btn>
            <v-btn small text :disabled="loadingBooks" @click="loadBooks">
              <v-icon small left>mdi-refresh</v-icon>{{ $t('srtTool.reload') }}
            </v-btn>
          </div>
          <v-alert v-if="loaded && !books.length && !loadingBooks" type="info" dense text rounded="lg">
            {{ $t('srtTool.noBooks') }}
          </v-alert>
          <v-sheet v-else-if="books.length" max-height="320" class="overflow-y-auto rounded-lg pa-2 mb-4" outlined>
            <v-checkbox
              v-for="b in books" :key="b.book_id"
              v-model="picked" :value="b.book_id" hide-details dense
              :disabled="running"
              class="mt-0"
            >
              <template #label>
                <span class="text-body-2">{{ b.title || ('#' + b.book_id) }}</span>
                <span class="text-caption grey--text ml-2">
                  {{ $t('srtTool.audioCount', { n: b.audio_count }) }}
                  <template v-if="b.srt_count">· {{ $t('srtTool.srtCount', { n: b.srt_count }) }}</template>
                </span>
              </template>
            </v-checkbox>
          </v-sheet>

          <!-- 参数 -->
          <v-row dense>
            <v-col cols="6" sm="3">
              <v-select dense outlined hide-details :label="$t('srtTool.model')"
                        v-model="model" :items="modelItems" :disabled="running"></v-select>
            </v-col>
            <v-col cols="6" sm="3">
              <v-select dense outlined hide-details :label="$t('srtTool.lang')"
                        v-model="lang" :items="langItems" :disabled="running"></v-select>
            </v-col>
            <v-col cols="6" sm="3">
              <v-select dense outlined hide-details :label="$t('srtTool.preset')"
                        v-model="preset" :items="presetItems" :disabled="running"></v-select>
            </v-col>
            <v-col cols="6" sm="3">
              <v-select dense outlined hide-details :label="$t('srtTool.script')"
                        v-model="script" :items="scriptItems" :disabled="running"></v-select>
            </v-col>
            <v-col cols="12" sm="8" class="d-flex align-center flex-wrap">
              <v-checkbox dense hide-details v-model="overwrite"
                          :label="$t('srtTool.overwrite')" :disabled="running"
                          class="mt-0 mr-4"></v-checkbox>
              <v-checkbox dense hide-details v-model="keepTxt"
                          :label="$t('srtTool.keepTxt')" :disabled="running"
                          class="mt-0 mr-4"></v-checkbox>
              <v-checkbox dense hide-details v-model="writeAss"
                          :label="$t('srtTool.writeAss')" :disabled="running"
                          class="mt-0"></v-checkbox>
            </v-col>
            <v-col cols="12" sm="4">
              <v-text-field dense outlined hide-details :label="$t('srtTool.hotwords')"
                            v-model="hotwords" :disabled="running"></v-text-field>
            </v-col>
          </v-row>

          <!-- 动作 -->
          <div class="d-flex align-center mt-4">
            <v-btn color="primary" rounded :disabled="!picked.length || running || !available"
                   :loading="starting" @click="start">
              <v-icon left>mdi-text-recognition</v-icon>{{ $t('srtTool.start') }}
            </v-btn>
            <v-btn v-if="running" color="error" rounded outlined class="ml-3" @click="cancel">
              <v-icon left>mdi-stop-circle-outline</v-icon>{{ $t('srtTool.stop') }}
            </v-btn>
            <v-spacer></v-spacer>
            <span v-if="picked.length" class="text-caption grey--text">
              {{ $t('srtTool.pickedHint', { n: picked.length }) }}
            </span>
          </div>

          <!-- 进度 -->
          <div v-if="task && task.state === 'running' || task && task.state === 'stopping'" class="mt-5">
            <div class="d-flex align-center mb-1">
              <span class="text-body-2 font-weight-medium">
                {{ $t('srtTool.progress', { done: task.files_done || 0, total: task.files_total || 0 }) }}
              </span>
              <v-spacer></v-spacer>
              <span class="text-caption grey--text">
                {{ $t('srtTool.counters', { skip: task.skipped || 0, fail: task.failed || 0 }) }}
              </span>
            </div>
            <v-progress-linear :value="pct" height="10" rounded color="primary"></v-progress-linear>
            <div class="text-caption grey--text mt-2">
              {{ task.current_book }} · {{ task.current_file }}
              <template v-if="task.current_pct">· {{ task.current_pct }}%</template>
            </div>
            <div v-if="task.message" class="text-caption orange--text text--darken-3 mt-1">{{ task.message }}</div>
          </div>
          <v-alert v-else-if="lastMessage" type="success" dense text rounded="lg" class="mt-5 mb-0">
            {{ lastMessage }}
          </v-alert>

          <div class="text-caption grey--text mt-6">
            {{ $t('srtTool.playNote') }}
          </div>
          <div class="text-caption grey--text mt-1">
            {{ $t('srtTool.pcFallback') }}
          </div>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
export default {
  data: () => ({
    loaded: false,
    available: false,
    loadingBooks: false,
    books: [],
    picked: [],
    model: 'base',
    lang: 'zh',
    preset: 'standard',
    script: 'original',
    writeAss: false,
    hotwords: '',
    overwrite: false,
    keepTxt: true,
    starting: false,
    running: false,
    task: null,
    lastMessage: '',
    pollTimer: null,
    installing: false,
    restarting: false,
    installState: '',
    installLog: '',
    modelItems: ['tiny', 'base', 'small', 'medium', 'large-v3'],
    langItems: [
      { text: 'auto', value: 'auto' },
      { text: '中文 (zh)', value: 'zh' },
      { text: 'English (en)', value: 'en' },
      { text: '日本語 (ja)', value: 'ja' },
    ],
  }),
  computed: {
    pct() {
      const t = this.task;
      if (!t || !t.files_total) return (t && t.state === 'running') ? 5 : 0;
      const base = ((t.files_done || 0) / t.files_total) * 100;
      const cur = (t.current_pct || 0) / t.files_total;
      return Math.min(100, Math.round(base + cur));
    },
    presetItems() {
      return [
        { text: this.$t('srtTool.presetShort'), value: 'short' },
        { text: this.$t('srtTool.presetStandard'), value: 'standard' },
        { text: this.$t('srtTool.presetLoose'), value: 'loose' },
      ];
    },
    scriptItems() {
      return [
        { text: this.$t('srtTool.scriptOriginal'), value: 'original' },
        { text: this.$t('srtTool.scriptSimplified'), value: 'simplified' },
        { text: this.$t('srtTool.scriptTraditional'), value: 'traditional' },
      ];
    },
  },
  created() {
    this.$store.commit('navbar', true);
    this.loadBooks();
  },
  beforeDestroy() {
    this.stopPoll();
  },
  methods: {
    loadBooks() {
      this.loadingBooks = true;
      this.$backend('/toolbox/srt_tool/books')
        .then((rsp) => {
          if (rsp.err !== 'ok') {
            this.$alert('error', rsp.msg || this.$t('srtTool.loadFailed'));
            return;
          }
          this.books = rsp.data.books || [];
          this.available = !!rsp.data.available;
          if (rsp.data.running) {
            this.running = true;
            this.task = rsp.data.task;
            this.startPoll();
          }
          this.loaded = true;
        })
        .catch(() => this.$alert('error', this.$t('srtTool.loadFailed')))
        .then(() => { this.loadingBooks = false; });
    },
    toggleAll(v) {
      this.picked = v ? this.books.map((b) => b.book_id) : [];
    },
    start() {
      if (!this.picked.length) return;
      this.starting = true;
      this.$backend('/toolbox/srt_tool/start', {
        method: 'POST',
        body: JSON.stringify({
          book_ids: this.picked, model: this.model, lang: this.lang,
          overwrite: this.overwrite, keep_txt: this.keepTxt,
          preset: this.preset, script: this.script,
          write_ass: this.writeAss, hotwords: this.hotwords,
        }),
      })
        .then((rsp) => {
          if (rsp.err !== 'ok') {
            this.$alert('error', rsp.msg || this.$t('srtTool.startFailed'));
            return;
          }
          this.lastMessage = '';
          this.running = true;
          this.startPoll();
        })
        .catch(() => this.$alert('error', this.$t('srtTool.startFailed')))
        .then(() => { this.starting = false; });
    },
    cancel() {
      this.$backend('/toolbox/srt_tool/cancel', { method: 'POST' })
        .then((rsp) => {
          if (rsp.err !== 'ok') this.$alert('error', rsp.msg);
        });
    },
    startPoll() {
      this.stopPoll();
      this.pollTimer = setInterval(() => this.poll(), 3000);
      this.poll();
    },
    stopPoll() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer);
        this.pollTimer = null;
      }
    },
    poll() {
      this.$backend('/toolbox/srt_tool/status')
        .then((rsp) => {
          if (rsp.err !== 'ok') return;
          this.task = rsp.data.task;
          this.available = !!rsp.data.available;
          this.running = !!rsp.data.running;
          const inst = this.task && this.task.install;
          if (inst) {
            this.installState = inst.state;
            this.installLog = inst.log || '';
          }
          if (!this.running) {
            this.stopPoll();
            if (this.task && this.task.message) this.lastMessage = this.task.message;
            this.loadBooks();
          }
        });
    },
    installDeps() {
      this.installing = true;
      this.$backend('/toolbox/srt_tool/install', { method: 'POST' })
        .then((rsp) => {
          if (rsp.err !== 'ok') {
            this.$alert('error', rsp.msg || this.$t('srtTool.startFailed'));
            this.installing = false;
            return;
          }
          this.installState = 'running';
          this.startPoll();
        })
        .catch(() => { this.installing = false; });
    },
    restartTornado() {
      this.restarting = true;
      this.$backend('/toolbox/srt_tool/restart', { method: 'POST' })
        .then(() => {
          // tornado 重启中，轮询会自动恢复
        })
        .catch(() => { this.restarting = false; });
    },
  },
  head() {
    return { title: this.$t('srtTool.title') };
  },
};
</script>
