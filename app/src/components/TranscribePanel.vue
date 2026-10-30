<template>
  <div class="pl-6 mt-4">
    <div class="d-flex align-center transcribe-header" @click="toggle">
      <v-icon class="mr-2">mdi-text-recognition</v-icon>
      <span class="text-body-1">{{ $t("settings.transcribe") }}</span>
      <v-chip v-if="available === false" x-small color="grey" class="ml-2">{{ $t("settings.transcribe_unavailable_short") }}</v-chip>
      <v-icon class="ml-1">{{ expanded ? "mdi-chevron-down" : "mdi-chevron-right" }}</v-icon>
    </div>
    <div class="text-caption grey--text ml-8">{{ $t("settings.transcribe_tips") }}</div>
    <v-expand-transition>
    <div v-show="expanded" class="pl-8">
      <template v-if="available === null">
        <v-progress-circular indeterminate size="20"></v-progress-circular>
      </template>
      <template v-else-if="!available">
        <v-alert type="info" dense text>{{ $t("settings.transcribe_unavailable") }}</v-alert>
      </template>
      <template v-else>
        <!-- 运行状态 -->
        <div v-if="state.running" class="my-2">
          <div class="d-flex align-center">
            <v-progress-linear :value="state.progress" class="mr-4" rounded height="8"></v-progress-linear>
            <span class="text-caption grey--text nowrap">{{ state.progress }}%</span>
          </div>
          <div class="text-caption grey--text mt-1">
            {{ $t("settings.transcribe_progress", { done: state.done, failed: state.failed, total: state.total }) }}
            {{ state.note }}
          </div>
          <v-btn small color="error" outlined class="mt-2" @click="cancel">
            <v-icon left small>mdi-stop-circle</v-icon>{{ $t("settings.transcribe_cancel") }}
          </v-btn>
        </div>
        <!-- 发起任务 -->
        <template v-else>

          <v-textarea
            v-model="pathsText"
            :label="$t('settings.transcribe_paths')"
            :placeholder="$t('settings.transcribe_paths_placeholder')"
            outlined dense rows="3" auto-grow hide-details
            class="mt-2"
          ></v-textarea>
          <div class="text-caption grey--text">{{ $t("settings.transcribe_dir_hint") }}</div>
          <v-row dense align="center" class="mt-1">
            <v-col cols="12" sm="4">
              <v-select v-model="model" :items="modelItems" :label="$t('settings.transcribe_model')" dense hide-details outlined></v-select>
            </v-col>
            <v-col cols="12" sm="4">
              <v-text-field v-model="lang" :label="$t('settings.transcribe_lang')" placeholder="auto / zh / en ..." dense hide-details outlined></v-text-field>
            </v-col>
            <v-col cols="12" sm="4">
              <v-btn color="primary" block :loading="submitting" :disabled="!pathsText.trim()" @click="run">
                <v-icon left>mdi-play-circle</v-icon>{{ $t("settings.transcribe_run") }}
              </v-btn>
            </v-col>
          </v-row>
          <!-- 输出格式开关：.srt 字幕始终生成（播放器靠它做高亮跟随），
               .txt 纯文本全稿可选（全文搜索/复制做笔记/离线阅读用） -->
          <v-row dense align="center" class="mt-1">
            <v-col cols="12" sm="8">
              <v-checkbox
                v-model="keepTxt"
                :label="$t('settings.transcribe_keep_txt')"
                :hint="$t('settings.transcribe_keep_txt_hint')"
                persistent-hint
                dense
                hide-details="auto"
                class="mt-0"
              ></v-checkbox>
            </v-col>
            <v-col cols="12" sm="4" class="text-caption grey--text">
              <v-icon x-small>mdi-closed-caption</v-icon>
              {{ $t("settings.transcribe_srt_always") }}
            </v-col>
          </v-row>
          <v-row dense>
            <v-col cols="12">
              <v-btn text small color="primary" @click="openBrowser">
                <v-icon left small>mdi-folder-open</v-icon>{{ $t("settings.transcribe_browse") }}
              </v-btn>
              <span class="text-caption grey--text ml-2">{{ $t("settings.transcribe_browse_hint") }}</span>
            </v-col>
          </v-row>
          <div v-if="lastMsg" class="text-caption mt-1" :class="lastOk ? 'success--text' : 'error--text'">{{ lastMsg }}</div>
        </template>
      </template>
    </div>
    </v-expand-transition>

    <!-- 服务器目录浏览器 -->
    <v-dialog v-model="browser.show" max-width="640">
      <v-card>
        <v-card-title class="text-body-1">
          <v-icon class="mr-2" small>mdi-folder-open</v-icon>{{ $t("settings.transcribe_browser_title") }}
        </v-card-title>
        <v-card-text class="pt-0">
          <div class="text-caption grey--text mb-2">
            {{ $t("settings.transcribe_browser_path") }}: /{{ browser.path }}
          </div>
          <div style="max-height: 320px; overflow-y: auto;">
            <v-progress-circular v-if="browser.loading" indeterminate size="24" class="ma-4"></v-progress-circular>
            <template v-else>
              <v-list dense v-if="browser.parent !== null">
                <v-list-item @click="browse(browser.parent)">
                  <v-list-item-icon class="mr-3"><v-icon small>mdi-arrow-up-left</v-icon></v-list-item-icon>
                  <v-list-item-content class="text-caption grey--text">..</v-list-item-content>
                </v-list-item>
              </v-list>
              <v-list dense>
                <v-list-item v-for="e in browser.entries" :key="e.name" @click="entryClick(e)">
                  <v-list-item-icon class="mr-3">
                    <v-icon small :color="e.is_dir ? 'amber' : 'primary'">
                      {{ e.is_dir ? "mdi-folder" : "mdi-music-note" }}
                    </v-icon>
                  </v-list-item-icon>
                  <v-list-item-content>
                    <v-list-item-title class="text-body-2">{{ e.name }}</v-list-item-title>
                  </v-list-item-content>
                  <v-list-item-action v-if="e.is_dir">
                    <v-btn small text color="primary" @click.stop="addPath(browser.path ? browser.path + '/' + e.name : e.name)">
                      <v-icon left x-small>mdi-plus</v-icon>{{ $t("settings.transcribe_add_dir") }}
                    </v-btn>
                  </v-list-item-action>
                  <v-list-item-action v-else>
                    <v-btn small text color="primary" @click.stop="addPath(browser.path ? browser.path + '/' + e.name : e.name)">
                      <v-icon left x-small>mdi-plus</v-icon>{{ $t("settings.transcribe_add_file") }}
                    </v-btn>
                  </v-list-item-action>
                </v-list-item>
              </v-list>
              <div v-if="!browser.entries.length" class="text-caption grey--text ma-4">
                {{ $t("settings.transcribe_browser_empty") }}
              </div>
            </template>
          </div>
        </v-card-text>
        <v-card-actions>
          <span v-if="browser.error" class="text-caption error--text">{{ browser.error }}</span>
          <v-spacer></v-spacer>
          <v-btn text @click="browser.show = false">{{ $t("settings.cancel") }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script>
// 音频转写文稿面板（移植自 audiobook 的 Whisper 转写）。
// 自包含：自行探测 /api/admin/transcribe/available，未装 whisper 时整块提示不可用。
export default {
  name: "TranscribePanel",
  data: () => ({
    expanded: false,
    available: null,
    submitting: false,
    pathsText: "",
    model: "small",
    lang: "auto",
    // 是否额外输出 .txt 纯文本全稿（.srt 字幕始终生成）
    keepTxt: true,
    state: { running: false, done: 0, failed: 0, total: 0, progress: 0, note: "" },
    lastMsg: "",
    lastOk: false,
    pollTimer: null,
    browser: {
      show: false, loading: false, error: "",
      path: "", parent: null, entries: [],
      rootLocked: false,
    },
  }),
  computed: {
    modelItems() {
      return ["tiny", "base", "small", "medium", "large"];
    },
  },
  beforeDestroy() {
    this.stopPoll();
  },
  methods: {
    toggle() {
      this.expanded = !this.expanded;
      if (this.expanded) this.probe();
      else this.stopPoll();
    },
    async probe() {
      try {
        const rsp = await this.$backend("/admin/transcribe/available");
        this.available = rsp.available === true;
        // 用后端保存的配置初始化面板（没配过就沿用后端默认值）
        if (rsp.model) this.model = rsp.model;
        if (rsp.lang) this.lang = rsp.lang;
        if (typeof rsp.keep_txt === "boolean") this.keepTxt = rsp.keep_txt;
      } catch (err) {
        this.available = false;
      }
      if (this.available) await this.refresh();
    },
    async refresh() {
      try {
        const rsp = await this.$backend("/admin/transcribe/status");
        if (rsp.err === "ok") {
          this.state = rsp.state || this.state;
          if (this.state.running) this.startPoll();
          else this.stopPoll();
        }
      } catch (err) { /* 忽略轮询错误 */ }
    },
    startPoll() {
      if (this.pollTimer) return;
      this.pollTimer = setInterval(() => this.refresh(), 2000);
    },
    stopPoll() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer);
        this.pollTimer = null;
      }
    },
    async run() {
      const paths = this.pathsText.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean);
      if (!paths.length) return;
      this.submitting = true;
      try {
        const rsp = await this.$backend("/admin/transcribe/run", {
          method: "POST",
          body: JSON.stringify({
            paths,
            model: this.model,
            lang: this.lang,
            keep_txt: this.keepTxt,
          }),
        });
        if (rsp.err === "ok") {
          this.lastOk = true;
          this.lastMsg = this.$t("settings.transcribe_submitted");
          await this.refresh();
        } else {
          this.lastOk = false;
          this.lastMsg = rsp.msg || rsp.err;
        }
      } catch (err) {
        this.lastOk = false;
        this.lastMsg = String(err);
      }
      this.submitting = false;
    },
    async cancel() {
      try {
        await this.$backend("/admin/transcribe/cancel", { method: "POST" });
      } catch (err) { /* 忽略 */ }
      await this.refresh();
    },
    // ---------- 服务器目录浏览（复用服务端目录导入的浏览接口） ----------
    async openBrowser() {
      this.browser.show = true;
      if (this.browser.path === "" && !this.browser.entries.length) {
        await this.browse("");
      }
    },
    async browse(path) {
      this.browser.loading = true;
      this.browser.error = "";
      try {
        const rsp = await this.$backend(
          "/admin/server_files/list" + (path ? "?path=" + encodeURIComponent(path) : ""));
        if (rsp.err === "ok") {
          this.browser.path = rsp.path || "";
          this.browser.parent = rsp.path ? rsp.path.split("/").slice(0, -1).join("/") : null;
          this.browser.entries = rsp.entries || [];
        } else {
          this.browser.error = rsp.msg || rsp.err;
          this.browser.entries = [];
          this.browser.parent = null;
        }
      } catch (err) {
        this.browser.error = String(err);
      }
      this.browser.loading = false;
    },
    entryClick(e) {
      if (e.is_dir) {
        this.browse(this.browser.path ? this.browser.path + "/" + e.name : e.name);
      }
    },
    addPath(rel) {
      const full = rel.startsWith("/") ? rel : "/" + rel;
      const cur = this.pathsText.split(/\n/).map((s) => s.trim()).filter(Boolean);
      if (!cur.includes(full)) cur.push(full);
      this.pathsText = cur.join("\n");
    },
  },
};
</script>

<style scoped>
.transcribe-header { cursor: pointer; user-select: none; }
.nowrap { white-space: nowrap; }
</style>
