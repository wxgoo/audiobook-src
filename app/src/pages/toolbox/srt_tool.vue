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
            <v-checkbox dense hide-details v-model="onlyMissing"
                        :label="$t('srtTool.missingOnly')" class="mt-0 mr-3"
                        :disabled="running"></v-checkbox>
            <v-btn small text color="primary" @click="toggleAll(true)">{{ $t('srtTool.selectAll') }}</v-btn>
            <v-btn small text @click="toggleAll(false)">{{ $t('srtTool.selectNone') }}</v-btn>
            <v-btn small text :disabled="loadingBooks" @click="loadBooks">
              <v-icon small left>mdi-refresh</v-icon>{{ $t('srtTool.reload') }}
            </v-btn>
          </div>
          <v-alert v-if="loaded && !filteredBooks.length && !loadingBooks" type="info" dense text rounded="lg">
            {{ onlyMissing && books.length ? $t('srtTool.noMissing') : $t('srtTool.noBooks') }}
          </v-alert>
          <v-sheet v-else-if="filteredBooks.length" max-height="320" class="overflow-y-auto rounded-lg pa-2 mb-4" outlined>
            <v-checkbox
              v-for="b in filteredBooks" :key="b.book_id"
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
                        v-model="model" :items="modelItems" :disabled="running"
                        @change="saveModelSelect"></v-select>
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

          <!-- 模型管理（借鉴外部「有声书字幕」工具：镜像源 + 按需下载/删除） -->
          <v-divider class="my-5"></v-divider>
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-1 font-weight-bold">{{ $t('srtTool.modelsTitle') }}</span>
            <v-spacer></v-spacer>
            <v-btn small text :disabled="loadingModels" @click="loadModels">
              <v-icon small left>mdi-refresh</v-icon>{{ $t('srtTool.reload') }}
            </v-btn>
          </div>
          <p class="text-caption grey--text mb-3">{{ $t('srtTool.modelsHint') }}</p>
          <v-row dense class="mb-2">
            <v-col cols="12" sm="8">
              <v-text-field dense outlined hide-details
                            :label="$t('srtTool.mirror')" v-model="mirror"
                            :disabled="modelDlRunning"></v-text-field>
            </v-col>
            <v-col cols="12" sm="4" class="d-flex align-center">
              <v-btn small color="primary" outlined :loading="mirrorSaving"
                     :disabled="modelDlRunning" @click="saveMirror">
                {{ $t('srtTool.mirrorSave') }}
              </v-btn>
            </v-col>
          </v-row>
          <v-simple-table dense class="rounded-lg outlined">
            <template v-slot:default>
              <thead>
                <tr>
                  <th class="text-left">{{ $t('srtTool.colModel') }}</th>
                  <th class="text-left">{{ $t('srtTool.colSize') }}</th>
                  <th class="text-left">{{ $t('srtTool.colStatus') }}</th>
                  <th class="text-right">{{ $t('srtTool.colAction') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in models" :key="m.model">
                  <td>{{ m.model }}</td>
                  <td>{{ m.size }}</td>
                  <td>
                    <v-icon small color="success" class="mr-1">mdi-check-circle</v-icon>
                    <span v-if="m.downloaded" class="text-caption">{{ $t('srtTool.dlDoneSize', { n: humanSize(m.bytes) }) }}</span>
                    <span v-else class="text-caption grey--text">{{ $t('srtTool.notDownloaded') }}</span>
                  </td>
                  <td class="text-right">
                    <v-btn v-if="!m.downloaded" x-small color="primary" outlined
                           :loading="dlBusy === m.model" :disabled="modelDlRunning || !available"
                           @click="downloadModel(m.model)">
                      {{ $t('srtTool.download') }}
                    </v-btn>
                    <v-btn v-else x-small color="error" text
                           :loading="deleting === m.model" :disabled="running || !!deleting"
                           @click="deleteModel(m.model)">
                      {{ $t('srtTool.delete') }}
                    </v-btn>
                  </td>
                </tr>
              </tbody>
            </template>
          </v-simple-table>
          <div v-if="modelDlRunning || modelDlLog" class="text-caption mt-2"
               :class="modelDlState === 'failed' ? 'red--text' : 'grey--text'"
               style="white-space:pre-wrap">{{ modelDlLog }}</div>
          <div class="text-caption grey--text mt-4">
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
    onlyMissing: false,
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
    // 模型管理（借鉴外部「有声书字幕」工具）
    models: [],
    mirror: '',
    loadingModels: false,
    mirrorSaving: false,
    modelDl: null,
    dlBusy: '',
    deleting: '',
    modelPollTimer: null,
    modelItems: ['tiny', 'base', 'small', 'medium', 'large-v3'],
    langItems: [
      { text: 'auto', value: 'auto' },
      { text: '中文 (zh)', value: 'zh' },
      { text: 'English (en)', value: 'en' },
      { text: '日本語 (ja)', value: 'ja' },
    ],
  }),
  computed: {
    filteredBooks() {
      if (!this.onlyMissing) return this.books;
      // 「只看缺字幕」：音频数 > 已有字幕数（借鉴外部工具的批量补字幕场景）
      return this.books.filter((b) => (b.audio_count || 0) > (b.srt_count || 0));
    },
    modelDlRunning() {
      return !!(this.modelDl && this.modelDl.state === 'running');
    },
    modelDlState() {
      return (this.modelDl && this.modelDl.state) || '';
    },
    modelDlLog() {
      if (!this.modelDl) return '';
      const m = this.modelDl;
      if (m.state === 'done') return m.log || this.$t('srtTool.dlDone');
      return m.log || '';
    },
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
    this.loadModels();
  },
  beforeDestroy() {
    this.stopPoll();
    this.stopModelPoll();
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
      this.picked = v ? this.filteredBooks.map((b) => b.book_id) : [];
    },
    start() {
      if (!this.picked.length) return;
      this.starting = true;
      this.$backend('/toolbox/srt_tool/start', {
        method: 'POST',
        // body 必须是 JSON 字符串：fetch 不会自动序列化对象（直接传对象会被
        // 拼成 "[object Object]"，后端 get_json_body 解析失败报 JSONDecodeError）
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
          const dl = this.task && this.task.model_dl;
          if (dl) {
            this.modelDl = dl;
            if (dl.state === 'done' || dl.state === 'failed') {
              this.dlBusy = '';
              this.loadModels();
            }
          }
          if (!this.running) {
            this.stopPoll();
            if (this.task && this.task.message) this.lastMessage = this.task.message;
            this.loadBooks();
          }
        });
    },
    loadModels() {
      this.loadingModels = true;
      this.$backend('/toolbox/srt_tool/models')
        .then((rsp) => {
          if (rsp.err === 'ok') {
            this.models = rsp.data.models || [];
            if (rsp.data.current_model) this.model = rsp.data.current_model;
            if (this.mirror === '') this.mirror = rsp.data.mirror || '';
            const sdl = rsp.data.model_dl || null;
            this.modelDl = sdl;
            // 兜底：只要后端已不在下载中（done/failed/状态被重置），就解除
            // dlBusy。轮询在状态切换的瞬间可能漏掉 done，导致 dlBusy 残留、
            // 按钮长期处于 loading 灰态；这里以 /models 的权威状态为准纠正。
            if (!sdl || sdl.state !== 'running') this.dlBusy = '';
          }
        })
        .catch(() => {})
        .then(() => { this.loadingModels = false; });
    },
    saveModelSelect(v) {
      // SrtMake 工具页下拉是 TRANSCRIBE_MODEL 的唯一选择点：与 AI 聊天
      // 麦克风语音输入共用，选择后立即保存，AI 语音输入同步跟随。
      this.$backend('/toolbox/srt_tool/model_select', {
        method: 'POST',
        body: JSON.stringify({ model: v }),
      })
        .then((rsp) => {
          if (rsp.err !== 'ok') this.$alert('error', rsp.msg || this.$t('srtTool.saveFailed'));
        })
        .catch(() => {});
    },
    downloadModel(name) {
      this.dlBusy = name;
      this.$backend('/toolbox/srt_tool/model_download', {
        method: 'POST',
        body: JSON.stringify({ model: name }),
      })
        .then((rsp) => {
          if (rsp.err !== 'ok') {
            this.$alert('error', rsp.msg || this.$t('srtTool.dlFailed'));
            this.dlBusy = '';
            return;
          }
          this.modelDl = { state: 'running', model: name };
          this.startModelPoll();
        })
        .catch(() => { this.dlBusy = ''; });
    },
    startModelPoll() {
      this.stopModelPoll();
      this.modelPollTimer = setInterval(() => this.pollModel(), 3000);
      this.pollModel();
    },
    stopModelPoll() {
      if (this.modelPollTimer) {
        clearInterval(this.modelPollTimer);
        this.modelPollTimer = null;
      }
    },
    pollModel() {
      this.$backend('/toolbox/srt_tool/status')
        .then((rsp) => {
          if (rsp.err !== 'ok') return;
          const dl = rsp.data.task && rsp.data.task.model_dl;
          if (!dl) { this.loadModels(); return; }
          this.modelDl = dl;
          if (dl.state === 'done' || dl.state === 'failed') {
            this.stopModelPoll();
            this.dlBusy = '';
            this.loadModels();
          }
        })
        .catch(() => {});
    },
    deleteModel(name) {
      if (!window.confirm(this.$t('srtTool.confirmDelete', { name }))) return;
      this.deleting = name;
      this.$backend('/toolbox/srt_tool/model_delete', {
        method: 'POST',
        body: JSON.stringify({ model: name }),
      })
        .then((rsp) => {
          if (rsp.err === 'ok') {
            this.$alert('success', rsp.msg || this.$t('srtTool.deleteDone'));
            // 用删除响应里带回的最新状态立即刷新，避免随后 GET 失败/缓存导致
            // 「提示释放成功但按钮仍是删除、再点报尚未下载」。
            if (rsp.data && rsp.data.models) this.models = rsp.data.models;
          } else {
            this.$alert('error', rsp.msg || this.$t('srtTool.deleteFailed'));
          }
          this.loadModels();
        })
        .catch(() => this.$alert('error', this.$t('srtTool.deleteFailed')))
        .then(() => { this.deleting = ''; });
    },
    saveMirror() {
      this.mirrorSaving = true;
      this.$backend('/toolbox/srt_tool/hf_mirror', {
        method: 'POST',
        body: JSON.stringify({ mirror: this.mirror }),
      })
        .then((rsp) => {
          if (rsp.err === 'ok') {
            this.$alert('success', rsp.msg || this.$t('srtTool.mirrorSaved'));
          } else {
            this.$alert('error', rsp.msg || this.$t('srtTool.mirrorSaved'));
          }
        })
        .catch(() => {})
        .then(() => { this.mirrorSaving = false; });
    },
    humanSize(n) {
      let v = n || 0;
      for (const unit of ['B', 'KB', 'MB', 'GB']) {
        if (v < 1024 || unit === 'GB') {
          return unit === 'B' ? `${v} ${unit}` : `${v.toFixed(1)} ${unit}`;
        }
        v /= 1024;
      }
      return `${v} GB`;
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
