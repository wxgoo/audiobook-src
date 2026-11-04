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
              <div v-for="f in scanResult.files" :key="f">{{ f }}</div>
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
              转码完成后到该书详情页点「有声书」确认能播放；m4a 已自动生成，对应 mp3 已删除。
            </div>
          </v-alert>
        </v-card>
      </v-col>
    </v-row>

    <!-- 确认框 -->
    <v-dialog v-model="confirmStart" width="360">
      <v-card class="pa-4">
        <p v-if="selectedBooks.length">
          将把选中的 {{ selectedBooks.length }} 本书里所有 mp3 转成
          {{ bitrate }} 的 m4a，成功后删除原 mp3。确认开始？
        </p>
        <p v-else>
          将把《{{ scanResult.title }}》里 {{ scanResult.mp3_count }} 个 mp3
          转成 {{ bitrate }} 的 m4a，成功后删除原 mp3。确认开始？
        </p>
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
          ? { book_ids: this.selectedBooks, bitrate: this.bitrate }
          : { book_id: parseInt(this.bookIdInput, 10), bitrate: this.bitrate };
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
