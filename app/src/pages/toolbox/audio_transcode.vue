<template>
  <v-container fluid class="pa-4">
    <!-- Page header -->
    <v-row class="mb-3" align="center">
      <v-col class="text-center">
        <span class="text-h5 font-weight-bold">音频批量转码</span>
      </v-col>
      <v-col cols="auto">
        <v-btn small color="error" @click="$router.go(-1)">
          <v-icon small left>mdi-close</v-icon>关闭
        </v-btn>
      </v-col>
    </v-row>

    <v-row justify="center">
      <v-col cols="12" md="8" lg="6">
        <v-card rounded="xl" outlined class="pa-6">
          <p class="mb-4 grey--text text--darken-1">
            把指定书 <code>.audio/</code> 目录里的 mp3 批量转成 m4a（AAC）。
            转码时洗掉 mp3 内嵌的杂乱标签（播音员名等），并做流式播放优化
            （faststart）。转码成功后自动删除对应 mp3，失败的 mp3 会保留。
          </p>

          <!-- 进行中的任务提示 -->
          <v-alert
            v-if="globalTask && globalTask.status === 'running'"
            type="info" dense text rounded="lg" class="mb-4"
          >
            当前有任务在跑：书 #{{ globalTask.book_id }}
            《{{ globalTask.book_title }}》
            {{ globalTask.done }}/{{ globalTask.total }}。等它完成后再开新的。
          </v-alert>

          <!-- 书 ID 输入 -->
          <v-text-field
            v-model="bookIdInput"
            label="书籍 ID"
            placeholder="例如 215（书详情页地址 /book/215 里的数字）"
            outlined dense clearable
            hide-details
            class="mb-3"
            :disabled="phase === 'running'"
            @keyup.enter="scan"
          ></v-text-field>

          <div class="d-flex align-center mb-4 flex-wrap">
            <v-btn
              color="primary" outlined small
              :loading="scanning"
              :disabled="!bookIdInput || phase === 'running'"
              @click="scan"
            >扫描单本</v-btn>
            <v-btn
              color="secondary" outlined small class="ml-2"
              :loading="scanningAll"
              :disabled="phase === 'running'"
              @click="scanAll"
            >扫描全库（批量）</v-btn>
            <span v-if="scanResult" class="ml-3 text-caption">
              《{{ scanResult.title }}》：{{ scanResult.mp3_count }} 个 mp3
            </span>
          </div>

          <!-- 现有音频概况：转码前先让用户看清「现在是什么样」 -->
          <v-card v-if="scanResult && scanResult.probe" flat outlined class="mb-4 pa-3">
            <div class="text-subtitle-2 mb-2">现有音频</div>
            <div class="text-body-2">
              {{ scanResult.probe.count }} 个 mp3 ·
              {{ fmtSize(scanResult.probe.total_size) }}
              <template v-if="scanResult.probe.avg_bitrate">
                · 平均 {{ Math.round(scanResult.probe.avg_bitrate / 1000) }} kbps
              </template>
              <template v-if="scanResult.probe.sample_rate">
                · {{ (scanResult.probe.sample_rate / 1000).toFixed(1) }} kHz
              </template>
              <template v-if="scanResult.probe.total_duration">
                · 总时长 {{ fmtDuration(scanResult.probe.total_duration) }}
              </template>
            </div>
            <div
              v-if="scanResult.probe.min_bitrate && scanResult.probe.max_bitrate
                    && scanResult.probe.min_bitrate !== scanResult.probe.max_bitrate"
              class="text-caption grey--text mt-1"
            >
              码率不均：最低 {{ Math.round(scanResult.probe.min_bitrate / 1000) }} kbps，
              最高 {{ Math.round(scanResult.probe.max_bitrate / 1000) }} kbps
            </div>
            <div v-if="scanResult.probe.sampled" class="text-caption grey--text mt-1">
              文件较多，以上为抽样 {{ scanResult.probe.sampled_count }} 个的估算
            </div>

            <!-- 白转预警：选的码率不低于源码率，等于没提升还占地方 -->
            <v-alert
              v-if="wastedWarning" type="warning" dense text rounded="lg" class="mt-2 mb-0"
            >{{ wastedWarning }}</v-alert>
          </v-card>

          <!-- 全库批量：多选列表 -->
          <template v-if="allBooks.length">
            <div class="d-flex align-center mb-2">
              <span class="text-subtitle-2">
                全库共 {{ allBooks.length }} 本含 mp3，已选 {{ selectedBooks.length }} 本
              </span>
              <v-spacer></v-spacer>
              <v-btn text x-small color="primary" @click="selectedBooks = allBooks.map(b => b.book_id)">全选</v-btn>
              <v-btn text x-small class="ml-1" @click="selectedBooks = []">清空</v-btn>
            </div>
            <v-card flat outlined class="mb-4">
              <div style="max-height:220px;overflow-y:auto">
                <v-checkbox
                  v-for="b in allBooks" :key="b.book_id"
                  v-model="selectedBooks"
                  :value="b.book_id"
                  :label="'#' + b.book_id + ' 《' + b.title + '》 ' + b.mp3_count + ' 个 mp3'"
                  hide-details dense class="ml-3"
                ></v-checkbox>
              </div>
            </v-card>
          </template>

          <!-- 文件列表 -->
          <v-card v-if="scanResult && scanResult.files.length" flat outlined class="mb-4">
            <div class="pa-2 text-caption grey--text" style="max-height:160px;overflow-y:auto">
              <div v-for="f in fileRows" :key="f.name" class="d-flex">
                <span class="flex-grow-1 text-truncate">{{ f.name }}</span>
                <span class="ml-3 text-no-wrap">{{ f.meta }}</span>
              </div>
            </div>
          </v-card>

          <v-alert
            v-if="scanResult && scanResult.mp3_count === 0"
            type="success" dense text rounded="lg" class="mb-4"
          >这本书没有 mp3（可能已经全部是 m4a），无需转码。</v-alert>

          <!-- 码率 -->
          <p class="mb-1 text-subtitle-2">AAC 码率</p>
          <v-radio-group v-model="bitrate" row hide-details class="mt-0 mb-4">
            <v-radio label="64k（语音推荐，体积小）" value="64k" dense></v-radio>
            <v-radio label="96k" value="96k" dense></v-radio>
            <v-radio label="128k（音乐类）" value="128k" dense></v-radio>
          </v-radio-group>
          <div v-if="sourceBitrate" class="text-caption grey--text mb-4">
            源文件平均 {{ Math.round(sourceBitrate / 1000) }} kbps；
            <span v-if="bitrateValue > sourceBitrate">
              当前选择高于源码率，体积会变大而音质不会提升。
            </span>
            <span v-else>当前选择不高于源码率，不会白转。</span>
          </div>

          <!-- 原文件处置 -->
          <v-checkbox
            v-model="deleteSource"
            label="转码成功后删除原 mp3"
            hide-details dense class="mt-2 mb-1"
          ></v-checkbox>
          <div class="text-caption grey--text mb-4">
            <template v-if="deleteSource">
              勾选：m4a 生成成功后才删对应 mp3（失败的一律保留）。
            </template>
            <template v-else>
              不勾选：原 mp3 全部保留，方便你试听对比后自己决定何时删。
              注意此时同一本书会同时存在 mp3 和 m4a，播放列表可能重复。
            </template>
          </div>

          <!-- 启动 -->
          <div class="d-flex justify-center">
            <v-btn
              color="primary"
              :loading="starting"
              :disabled="!canStart"
              @click="confirmStart = true"
            >开始转码</v-btn>
          </div>

          <!-- 进度 -->
          <template v-if="phase === 'running' || phase === 'done'">
            <div class="mt-6">
              <div class="d-flex text-caption mb-1">
                <span>
                  {{ task.book_title || ('书 #' + task.book_id) }}
                  <template v-if="(task.queue || []).length > 1">
                    （第 {{ task.queue_index + 1 }}/{{ task.queue.length }} 本）
                  </template>
                </span>
                <v-spacer></v-spacer>
                <span>{{ task.done }}/{{ task.total }}
                  <template v-if="task.failed">（失败 {{ task.failed }}）</template>
                </span>
              </div>
              <v-progress-linear
                :value="task.total ? (task.done / task.total) * 100 : 0"
                color="primary" height="8" rounded
              ></v-progress-linear>
              <div v-if="task.current" class="text-caption grey--text mt-1">
                正在转：{{ task.current }}
              </div>
            </div>
          </template>

          <!-- 结果 -->
          <v-alert
            v-if="phase === 'done'" dense text rounded="lg"
            :type="task.failed ? 'warning' : 'success'"
            class="mt-4 mb-0"
          >
            {{ task.message }}
            <div v-if="task.errors && task.errors.length" class="mt-2">
              <div v-for="(e, i) in task.errors" :key="i" class="text-caption">
                {{ e.file }}：{{ e.error }}
              </div>
            </div>
            <div class="text-caption mt-2">
              <template v-if="deleteSource">
                转码完成后到该书详情页点「有声书」确认能播放；m4a 已自动生成，对应 mp3 已删除。
              </template>
              <template v-else>
                转码完成后到该书详情页点「有声书」确认能播放；原 mp3 已按你的设置保留，
                试听满意后请自行删除，避免同一本书出现重复音轨。
              </template>
            </div>
          </v-alert>
        </v-card>
      </v-col>
    </v-row>

    <!-- 确认框 -->
    <!-- §必须防 null§ scanResult 初值就是 null，而 v-dialog 即使关闭也会渲染内容，
         所以这里不能直接读 scanResult.title，否则首屏就抛
         "Cannot read properties of null (reading 'title')"，整页白屏。 -->
    <v-dialog v-model="confirmStart" width="360">
      <v-card v-if="confirmStart" class="pa-4">
        <p v-if="selectedBooks.length">
          将把选中的 {{ selectedBooks.length }} 本书里所有 mp3 转成
          {{ bitrate }} 的 m4a，{{ deleteSource ? '成功后删除原 mp3' : '原 mp3 保留' }}。确认开始？
        </p>
        <p v-else-if="scanResult">
          将把《{{ scanResult.title }}》里 {{ scanResult.mp3_count }} 个 mp3
          转成 {{ bitrate }} 的 m4a，{{ deleteSource ? '成功后删除原 mp3' : '原 mp3 保留' }}。确认开始？
        </p>
        <p v-else>没有选中任何书，也没有扫描结果。</p>
        <div class="d-flex justify-end">
          <v-btn text small @click="confirmStart = false">取消</v-btn>
          <v-btn color="primary" small :loading="starting" @click="start">确认</v-btn>
        </div>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" timeout="3000">
      {{ snack.text }}
    </v-snackbar>
  </v-container>
</template>

<script>
// 音频批量转码工具：扫描 → 确认 → 后台 ffmpeg 逐个转 → 轮询进度。
// 后端逻辑见 webserver/services/audio_transcode.py。
export default {
  created() {
    this.$store.commit("navbar", true);
  },
  data() {
    return {
      bookIdInput: "",
      bitrate: "64k",
      deleteSource: true,   // 转码成功后删原 mp3（默认沿用旧行为）
      scanning: false,
      scanningAll: false,
      allBooks: [],
      selectedBooks: [],
      starting: false,
      confirmStart: false,
      scanResult: null,
      task: {},
      pollTimer: null,
      snack: { show: false, text: "", color: "info" },
    };
  },
  computed: {
    canStart() {
      if (this.phase === "running") return false;
      if (this.selectedBooks.length) return true;          // 批量模式
      return this.scanResult && this.scanResult.mp3_count > 0; // 单本模式
    },
    phase() {
      if (!this.task || !this.task.status) return "idle";
      if (this.task.status === "running") return "running";
      if (this.task.status === "done" || this.task.status === "error") return "done";
      return "idle";
    },
    globalTask() {
      return this.task && this.task.running ? this.task : null;
    },
    // 当前选中的码率（bps），用于与源码率比较
    bitrateValue() {
      const map = { "64k": 64000, "96k": 96000, "128k": 128000 };
      return map[this.bitrate] || 0;
    },
    // 源码平均码率：单本用探测结果；全库批量取所选书的样本中位数
    sourceBitrate() {
      if (this.scanResult && this.scanResult.probe) {
        return this.scanResult.probe.avg_bitrate || null;
      }
      if (this.selectedBooks.length && this.allBooks.length) {
        const vals = this.allBooks
          .filter((b) => this.selectedBooks.includes(b.book_id) && b.sample_bitrate)
          .map((b) => b.sample_bitrate);
        if (!vals.length) return null;
        vals.sort((a, b) => a - b);
        return vals[Math.floor(vals.length / 2)];
      }
      return null;
    },
    // 「白转」预警文案：码率不低于源码率时，转码不提升音质还占更多空间
    wastedWarning() {
      const src = this.sourceBitrate;
      if (!src || !this.bitrateValue) return "";
      if (this.bitrateValue <= src) return "";
      return `所选码率（${this.bitrate}）高于源文件平均码率（${Math.round(src / 1000)} kbps）：`
        + "转码后体积会变大，但音质不会提升。建议选择不高于源码率的档位，或直接不转。";
    },
    // 文件列表：把文件名与探测到的码率拼成一行
    fileRows() {
      const files = (this.scanResult && this.scanResult.files) || [];
      const details = (this.scanResult && this.scanResult.probe && this.scanResult.probe.files) || [];
      const byName = {};
      details.forEach((d) => { byName[d.name] = d; });
      return files.map((name) => {
        const d = byName[name];
        const bits = [];
        if (d && d.bitrate) bits.push(`${Math.round(d.bitrate / 1000)}kbps`);
        if (d && d.size) bits.push(this.fmtSize(d.size));
        return { name, meta: bits.join(" · ") };
      });
    },
  },
  mounted() {
    this.refreshProgress();
  },
  beforeDestroy() {
    if (this.pollTimer) clearInterval(this.pollTimer);
  },
  methods: {
    toast(text, color = "info") {
      this.snack = { show: true, text, color };
    },
    fmtSize(bytes) {
      if (!bytes) return "0 B";
      const units = ["B", "KB", "MB", "GB"];
      let v = bytes;
      let i = 0;
      while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
      return `${v >= 100 ? Math.round(v) : v.toFixed(1)} ${units[i]}`;
    },
    fmtDuration(sec) {
      if (!sec) return "0 分";
      const h = Math.floor(sec / 3600);
      const m = Math.round((sec % 3600) / 60);
      return h ? `${h} 小时 ${m} 分` : `${m} 分`;
    },
    async scan() {
      const id = parseInt(this.bookIdInput, 10);
      if (!id || id <= 0) {
        this.toast("请输入正确的书籍 ID", "warning");
        return;
      }
      this.scanning = true;
      try {
        const rsp = await this.$backend("/toolbox/audio_transcode/scan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ book_id: id }),
        });
        if (rsp.err !== "ok") {
          this.toast(rsp.msg || "扫描失败", "error");
          return;
        }
        this.scanResult = rsp.data;
        if (rsp.data.mp3_count === 0) {
          this.toast("这本书没有 mp3，无需转码", "success");
        }
      } finally {
        this.scanning = false;
      }
    },
    async scanAll() {
      this.scanningAll = true;
      try {
        const rsp = await this.$backend("/toolbox/audio_transcode/scan_all");
        if (rsp.err !== "ok") {
          this.toast(rsp.msg || "扫描失败", "error");
          return;
        }
        this.allBooks = rsp.data.books || [];
        this.selectedBooks = this.allBooks.map((b) => b.book_id);
        this.scanResult = null;
        if (!this.allBooks.length) this.toast("全库没有需要转码的 mp3", "success");
      } finally {
        this.scanningAll = false;
      }
    },
    async start() {
      this.starting = true;
      try {
        const payload = this.selectedBooks.length
          ? { book_ids: this.selectedBooks, bitrate: this.bitrate, delete_source: this.deleteSource }
          : { book_id: parseInt(this.bookIdInput, 10), bitrate: this.bitrate, delete_source: this.deleteSource };
        const rsp = await this.$backend("/toolbox/audio_transcode/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (rsp.err !== "ok") {
          this.toast(rsp.msg || "启动失败", "error");
          return;
        }
        this.confirmStart = false;
        this.toast(rsp.msg, "success");
        this.refreshProgress();
        if (this.pollTimer) clearInterval(this.pollTimer);
        this.pollTimer = setInterval(() => this.refreshProgress(), 2000);
      } finally {
        this.starting = false;
      }
    },
    async refreshProgress() {
      try {
        const rsp = await this.$backend("/toolbox/audio_transcode/progress");
        if (rsp.err !== "ok") return;
        this.task = rsp.data.task || {};
        if (this.phase === "done" && this.pollTimer) {
          clearInterval(this.pollTimer);
          this.pollTimer = null;
        }
      } catch (e) { /* 忽略轮询错误 */ }
    },
  },
};
</script>
